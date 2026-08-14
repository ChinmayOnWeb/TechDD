"""Sampling frame for the repository-level cohort study (Part C).

The frame is the study's biggest threat to validity: sampling repositories by
popularity (stars, dependents, "awesome" lists) conditions on success and biases
every survival estimate, because the projects that died are exactly the ones such
lists omit. So the frame is drawn from a **complete enumeration** instead.

PyPI publishes its full project index (~870k projects, live and dead alike) at
`/simple/`. We draw a seeded random sample from that index, then resolve each
sampled project to a source repository via its PyPI metadata. Dead, abandoned and
never-popular projects enter the sample at exactly their population rate.

Reproducibility: the sample is a deterministic function of (index snapshot, seed,
size). The resolved frame is written once and committed, so the drawn sample is
frozen even though PyPI's index keeps moving.

Known limitation, to be stated in the paper: this is a single-ecosystem frame
(Python). Conclusions may not transfer to ecosystems with different packaging
norms; npm/crates are the natural robustness ecosystems. crates.io's API is not
reachable from this environment, and the sparse index carries no repository URLs.
"""
from __future__ import annotations

import json
import random
import re
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Iterable

PYPI_SIMPLE_URL = "https://pypi.org/simple/"
PYPI_PROJECT_URL = "https://pypi.org/pypi/{project}/json"
USER_AGENT = "git-due-diligence research contact: chinmay.patil1@gmail.com"

# Politeness delay between PyPI project-metadata requests. PyPI has no published
# hard rate limit for the JSON API, so we self-throttle rather than discover one.
_REQUEST_DELAY_SECONDS = 0.1

_GITHUB_REPO_RE = re.compile(
    r"https?://(?:www\.)?github\.com/([A-Za-z0-9._-]+)/([A-Za-z0-9._-]+)",
    re.IGNORECASE,
)
# Owner namespaces that are never a single project's source repository.
_NON_REPO_OWNERS = frozenset({"sponsors", "orgs", "users", "about", "features"})


@dataclass(frozen=True)
class FrameEntry:
    """One sampled repository, with the pre-clone metadata needed to
    post-stratify by age and activity without re-fetching PyPI."""
    project: str            # PyPI project that resolved to this repo
    owner: str
    repo: str
    clone_url: str
    release_count: int      # proxy for project maturity
    first_release: str      # ISO date or "" when PyPI reports none
    last_release: str

    @property
    def slug(self) -> str:
        return f"{self.owner}/{self.repo}"


def _default_fetch(url: str) -> str:
    import requests

    response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=60)
    response.raise_for_status()
    return response.text


def fetch_project_names(cache_dir: Path,
                        fetch: Callable[[str], str] = _default_fetch) -> list[str]:
    """Complete PyPI project index, cached so the drawn sample is reproducible
    against a fixed snapshot rather than a moving index."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = cache_dir / "pypi_simple_index.json"
    if not cache_file.exists():
        cache_file.write_text(fetch(PYPI_SIMPLE_URL), encoding="utf-8")
    payload = json.loads(cache_file.read_text(encoding="utf-8"))
    return [entry["name"] for entry in payload.get("projects", [])]


def sample_projects(names: Iterable[str], size: int, seed: int) -> list[str]:
    """Seeded simple random sample without replacement. Sorted first so the draw
    depends on the index contents, not on server response ordering."""
    pool = sorted(set(names))
    if size >= len(pool):
        return pool
    return random.Random(seed).sample(pool, size)


def extract_github_repo(metadata: dict) -> tuple[str, str] | None:
    """Find the project's GitHub repository in PyPI metadata.

    project_urls keys are free text ("Source", "Source Code", "Repository",
    "Homepage", "Code", "GitHub", ...), so we scan values rather than trusting
    any key name, preferring source-ish labels before falling back to any
    GitHub URL present."""
    info = metadata.get("info") or {}
    project_urls = info.get("project_urls") or {}
    preferred_order = sorted(
        project_urls.items(),
        key=lambda kv: 0 if re.search(r"source|repo|code|git", kv[0] or "", re.I) else 1,
    )
    candidates = [value for _, value in preferred_order]
    candidates.append(info.get("home_page") or "")
    candidates.append(info.get("download_url") or "")
    for candidate in candidates:
        if not candidate:
            continue
        match = _GITHUB_REPO_RE.search(candidate)
        if not match:
            continue
        owner, repo = match.group(1), match.group(2)
        if owner.lower() in _NON_REPO_OWNERS:
            continue
        if repo.lower().endswith(".git"):
            repo = repo[: -len(".git")]
        return owner, repo
    return None


def _release_stats(metadata: dict) -> tuple[int, str, str]:
    releases = metadata.get("releases") or {}
    upload_times: list[str] = []
    for files in releases.values():
        for file_info in files or []:
            stamp = file_info.get("upload_time_iso_8601") or file_info.get("upload_time")
            if stamp:
                upload_times.append(stamp[:10])
    if not upload_times:
        return len(releases), "", ""
    upload_times.sort()
    return len(releases), upload_times[0], upload_times[-1]


def resolve_projects(projects: list[str], cache_dir: Path,
                     fetch: Callable[[str], str] = _default_fetch,
                     delay_seconds: float = _REQUEST_DELAY_SECONDS,
                     on_progress: Callable[[int, int], None] | None = None,
                     ) -> list[FrameEntry]:
    """Resolve sampled PyPI projects to unique GitHub repositories.

    Projects with no GitHub URL are dropped (they are genuinely out of frame for
    a git-history study, and that attrition is reported). Multiple projects
    frequently share one repository -- a monorepo publishing several packages --
    so repositories are de-duplicated, keeping the first project encountered."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    resolved: dict[str, FrameEntry] = {}
    for index, project in enumerate(projects, start=1):
        if on_progress:
            on_progress(index, len(projects))
        cache_file = cache_dir / f"pypi_{project.replace('/', '_')}.json"
        if cache_file.exists():
            raw = cache_file.read_text(encoding="utf-8")
        else:
            try:
                raw = fetch(PYPI_PROJECT_URL.format(project=project))
            except Exception:
                continue        # deleted/yanked projects 404; not a frame failure
            cache_file.write_text(raw, encoding="utf-8")
            if delay_seconds:
                time.sleep(delay_seconds)
        try:
            metadata = json.loads(raw)
        except json.JSONDecodeError:
            continue
        found = extract_github_repo(metadata)
        if not found:
            continue
        owner, repo = found
        key = f"{owner.lower()}/{repo.lower()}"
        if key in resolved:
            continue
        release_count, first_release, last_release = _release_stats(metadata)
        resolved[key] = FrameEntry(
            project=project, owner=owner, repo=repo,
            clone_url=f"https://github.com/{owner}/{repo}.git",
            release_count=release_count,
            first_release=first_release, last_release=last_release,
        )
    return list(resolved.values())


def write_frame(entries: list[FrameEntry], path: Path, meta: dict) -> None:
    """Freeze the drawn frame. `meta` records the draw parameters (seed, sample
    size, index snapshot size) so the sample is auditable after the fact."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "meta": meta,
        "entries": [asdict(e) for e in entries],
    }, indent=2), encoding="utf-8")


def read_frame(path: Path) -> list[FrameEntry]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [FrameEntry(**row) for row in payload["entries"]]
