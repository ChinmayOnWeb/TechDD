"""npm ecosystem frame construction (Part C robustness ecosystem).

Getting a *complete* npm enumeration from this environment took some doing, and
the route matters for validity, so it is recorded here:

  - `replicate.npmjs.com` / `skimdb.npmjs.com` (the CouchDB replication
    endpoints, the canonical way to enumerate npm) are not reachable — only
    `registry.npmjs.org` is on the network allowlist.
  - `registry.npmjs.org/-/all` was retired by npm and returns 404.
  - `registry.npmjs.org/-/v1/search` IS reachable, but ranks results by
    popularity/quality/maintenance and caps pagination. Building a frame from it
    would reintroduce precisely the survivorship bias the complete-enumeration
    design exists to remove, so it is deliberately NOT used.
  - `all-the-package-names` is a package *published to npm* whose payload is the
    full package-name list, so it arrives over the reachable registry host and
    is refreshed daily. That is the route used here (~4.3M names).

The dependence on a third-party mirror package is a documented limitation: the
list is only as complete and current as that package's last publish, which the
frame metadata records.
"""
from __future__ import annotations

import io
import json
import re
import tarfile
import time
from pathlib import Path
from typing import Callable

from git_due_diligence.cohort.frame import FrameEntry, _GITHUB_REPO_RE, _NON_REPO_OWNERS

NPM_PACKAGE_URL = "https://registry.npmjs.org/{package}"
NPM_NAMES_PACKAGE_URL = "https://registry.npmjs.org/all-the-package-names"
USER_AGENT = "git-due-diligence research contact: chinmay.patil1@gmail.com"
_REQUEST_DELAY_SECONDS = 0.05

# npm repository fields also use the shorthand "github:owner/repo".
_GITHUB_SHORTHAND_RE = re.compile(r"^github:([A-Za-z0-9._-]+)/([A-Za-z0-9._-]+)$", re.I)

# Scheme-agnostic GitHub matcher. The PyPI regex requires https?://, but npm
# repository fields predate that convention: `git://github.com/o/r.git` was the
# dominant form around 2011-2015 and `git@github.com:o/r.git` scp-syntax is also
# common. Matching only https:// would drop those packages -- and because the
# git:// era skews old, those packages skew ABANDONED, so the omission would
# quietly bias the frame toward survivors.
_GITHUB_ANY_SCHEME_RE = re.compile(
    r"github\.com[/:]([A-Za-z0-9._-]+)/([A-Za-z0-9._-]+)", re.IGNORECASE)


def _default_fetch(url: str) -> str:
    import requests

    response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=120)
    response.raise_for_status()
    return response.text


def _default_fetch_bytes(url: str) -> bytes:
    import requests

    response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=300)
    response.raise_for_status()
    return response.content


def fetch_package_names(cache_dir: Path,
                        fetch: Callable[[str], str] = _default_fetch,
                        fetch_bytes: Callable[[str], bytes] = _default_fetch_bytes,
                        ) -> tuple[list[str], str]:
    """Complete npm package-name list plus the mirror version it came from.

    Returns (names, version) so the frame metadata can pin which snapshot of the
    mirror package the draw was made against."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    names_file = cache_dir / "npm_all_names.json"
    version_file = cache_dir / "npm_all_names_version.txt"
    if names_file.exists() and version_file.exists():
        return (json.loads(names_file.read_text(encoding="utf-8")),
                version_file.read_text(encoding="utf-8").strip())

    metadata = json.loads(fetch(NPM_NAMES_PACKAGE_URL))
    version = metadata["dist-tags"]["latest"]
    tarball_url = metadata["versions"][version]["dist"]["tarball"]
    payload = fetch_bytes(tarball_url)

    with tarfile.open(fileobj=io.BytesIO(payload), mode="r:gz") as archive:
        member = archive.extractfile("package/names.json")
        if member is None:
            raise ValueError("all-the-package-names tarball has no package/names.json")
        names = json.loads(member.read().decode("utf-8"))

    names_file.write_text(json.dumps(names), encoding="utf-8")
    version_file.write_text(version, encoding="utf-8")
    return names, version


def extract_github_repo(metadata: dict) -> tuple[str, str] | None:
    """Resolve an npm packument to a GitHub repo.

    npm's `repository` field is far less disciplined than PyPI's: it appears as
    a dict or a bare string, and the URL may be `git+https://`, `git://`,
    `ssh://git@`, or the `github:owner/repo` shorthand. All are handled."""
    latest_version = (metadata.get("dist-tags") or {}).get("latest")
    versions = metadata.get("versions") or {}
    sources: list = [metadata.get("repository"), metadata.get("homepage")]
    if latest_version and latest_version in versions:
        version_doc = versions[latest_version]
        sources.insert(0, version_doc.get("repository"))
        sources.append(version_doc.get("homepage"))

    for source in sources:
        if not source:
            continue
        text = source.get("url") if isinstance(source, dict) else source
        if not isinstance(text, str) or not text:
            continue
        shorthand = _GITHUB_SHORTHAND_RE.match(text.strip())
        if shorthand:
            owner, repo = shorthand.group(1), shorthand.group(2)
        else:
            match = _GITHUB_ANY_SCHEME_RE.search(text)
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
    times = {k: v for k, v in (metadata.get("time") or {}).items()
             if k not in ("created", "modified")}
    versions = metadata.get("versions") or {}
    if not times:
        return len(versions), "", ""
    stamps = sorted(value[:10] for value in times.values() if isinstance(value, str))
    if not stamps:
        return len(versions), "", ""
    return len(versions), stamps[0], stamps[-1]


def resolve_packages(packages: list[str], cache_dir: Path,
                     fetch: Callable[[str], str] = _default_fetch,
                     delay_seconds: float = _REQUEST_DELAY_SECONDS,
                     on_progress: Callable[[int, int], None] | None = None,
                     ) -> list[FrameEntry]:
    """Resolve sampled npm packages to unique GitHub repositories, mirroring the
    PyPI resolver's semantics (drop unresolvable, de-duplicate shared repos)."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    resolved: dict[str, FrameEntry] = {}
    for index, package in enumerate(packages, start=1):
        if on_progress:
            on_progress(index, len(packages))
        safe = package.replace("/", "__").replace("@", "_at_")
        cache_file = cache_dir / f"npm_{safe}.json"
        if cache_file.exists():
            raw = cache_file.read_text(encoding="utf-8")
        else:
            try:
                raw = fetch(NPM_PACKAGE_URL.format(package=package))
            except Exception:
                continue        # unpublished/removed packages 404
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
            project=package, owner=owner, repo=repo,
            clone_url=f"https://github.com/{owner}/{repo}.git",
            release_count=release_count,
            first_release=first_release, last_release=last_release,
        )
    return list(resolved.values())
