# AcquireScope Engine Core Implementation Plan (Phase 1 of 3)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A working Python CLI (`acquirescope analyze <repo>`) that runs three evidence-linked due-diligence analysis modules (bus factor, license risk, tech-debt hotspots) against any local git repository and writes a markdown DD report, with graceful per-module failure and an end-to-end regression test on a synthetic repo with planted issues.

**Architecture:** A thin ingestion layer (`RepoIngest`) shells out to `git log --numstat` / `git ls-files` and exposes typed commit history; each analysis module is a pure function `analyze(ingest) -> ModuleResult`; the CLI runs all modules in isolation (one failing module never kills the run) and a renderer turns results into markdown. All findings carry evidence references (paths, commits, dependency names).

**Tech Stack:** Python 3.12, Typer (CLI), lizard (cyclomatic complexity), tomllib (stdlib, pyproject parsing), pytest. Git is invoked via subprocess (no GitPython dependency — git is required on PATH anyway).

**Phasing note:** This is Phase 1 of the spec at `docs/superpowers/specs/2026-07-01-acquirescope-design.md`. Phase 2 (financial modelling bridge + Excel via openpyxl) and Phase 3 (security posture, delivery health, LLM narrative layer, published report series) get separate plans after this one ships. Phase 1 alone yields a usable open-source tool.

## Global Constraints

- Python 3.12; all source under `src/acquirescope/`, tests under `tests/`.
- Every quantified estimate MUST carry a confidence band — no naked point estimates (spec: "Error handling").
- A module failure MUST degrade gracefully: report marks the dimension "Not assessed", run continues, exit code 0 (spec: "Error handling").
- Every finding MUST link to concrete evidence: file path, commit, or dependency name (spec: "Deliverable 1").
- Public data only; no network calls anywhere in the engine (all analysis is local git + files).
- All file writes/reads use `encoding="utf-8"` explicitly (Windows default codepage breaks otherwise).

## File Structure

```
pyproject.toml                      # package metadata, deps, pytest config
src/acquirescope/__init__.py        # version marker
src/acquirescope/models.py          # Severity, Evidence, Finding, ModuleResult
src/acquirescope/ingest.py          # RepoIngest, Commit, FileChange
src/acquirescope/modules/__init__.py
src/acquirescope/modules/bus_factor.py
src/acquirescope/modules/licenses.py
src/acquirescope/modules/hotspots.py
src/acquirescope/report.py          # render_markdown()
src/acquirescope/cli.py             # Typer app, module registry
tests/conftest.py                   # fixture_repo: synthetic repo with planted issues
tests/test_fixture.py
tests/test_models.py
tests/test_ingest.py
tests/test_bus_factor.py
tests/test_licenses.py
tests/test_hotspots.py
tests/test_report.py
tests/test_cli.py                   # includes end-to-end planted-issue regression
```

---

### Task 1: Project scaffold + findings data model

**Files:**
- Create: `pyproject.toml`
- Create: `src/acquirescope/__init__.py`
- Create: `src/acquirescope/models.py`
- Test: `tests/test_models.py`

**Interfaces:**
- Consumes: nothing (first task).
- Produces: `Severity(str, Enum)` with members `INFO/LOW/MEDIUM/HIGH/CRITICAL`; `Evidence(description: str, path: str | None = None, detail: str | None = None)`; `Finding(module: str, title: str, severity: Severity, summary: str, evidence: list[Evidence] = [])`; `ModuleResult(module: str, status: str, findings: list[Finding] = [], error: str | None = None, metrics: dict = {})`. `status` is `"ok"` or `"failed"`. All are dataclasses importable from `acquirescope.models`.

- [ ] **Step 1: Create `pyproject.toml`**

```toml
[project]
name = "acquirescope"
version = "0.1.0"
description = "Technical due diligence engine for git repositories"
requires-python = ">=3.12"
dependencies = [
    "typer>=0.12",
    "lizard>=1.17",
]

[project.optional-dependencies]
dev = ["pytest>=8.0"]

[project.scripts]
acquirescope = "acquirescope.cli:app"

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

- [ ] **Step 2: Create the package and install editable**

Create `src/acquirescope/__init__.py`:

```python
__version__ = "0.1.0"
```

Run: `python -m venv .venv` then activate (`.venv\Scripts\Activate.ps1` on Windows) then `pip install -e .[dev]`
Expected: `Successfully installed acquirescope-0.1.0 ...`

- [ ] **Step 3: Write the failing test**

Create `tests/test_models.py`:

```python
from acquirescope.models import Evidence, Finding, ModuleResult, Severity


def test_finding_carries_evidence():
    f = Finding(
        module="licenses",
        title="GPL dependency in core",
        severity=Severity.HIGH,
        summary="mysqlclient is GPL-2.0 licensed",
        evidence=[Evidence(description="declared dependency", path="requirements.txt", detail="mysqlclient")],
    )
    assert f.severity == Severity.HIGH
    assert f.evidence[0].path == "requirements.txt"


def test_module_result_defaults():
    r = ModuleResult(module="bus_factor", status="ok")
    assert r.findings == []
    assert r.error is None
    assert r.metrics == {}
```

- [ ] **Step 4: Run test to verify it fails**

Run: `pytest tests/test_models.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'acquirescope.models'`

- [ ] **Step 5: Write the implementation**

Create `src/acquirescope/models.py`:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Severity(str, Enum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class Evidence:
    description: str
    path: str | None = None
    detail: str | None = None


@dataclass
class Finding:
    module: str
    title: str
    severity: Severity
    summary: str
    evidence: list[Evidence] = field(default_factory=list)


@dataclass
class ModuleResult:
    module: str
    status: str  # "ok" | "failed"
    findings: list[Finding] = field(default_factory=list)
    error: str | None = None
    metrics: dict = field(default_factory=dict)
```

- [ ] **Step 6: Run test to verify it passes**

Run: `pytest tests/test_models.py -v`
Expected: 2 passed

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml src/acquirescope/__init__.py src/acquirescope/models.py tests/test_models.py
git commit -m "feat: scaffold acquirescope package with findings data model"
```

---

### Task 2: Synthetic fixture repository with planted issues

**Files:**
- Create: `tests/conftest.py`
- Test: `tests/test_fixture.py`

**Interfaces:**
- Consumes: nothing.
- Produces: pytest fixture `fixture_repo` (session-scoped) returning `pathlib.Path` to a git repo containing exactly these planted issues, which Tasks 4–6 and 9 assert against:
  1. `payments/billing.py` — 6 commits, ALL authored by alice only (bus factor 1).
  2. `requirements.txt` — contains `mysqlclient` (GPL-2.0 copyleft dependency).
  3. `core/engine.py` — 8 commits (churn hotspot) with cyclomatic complexity ≥ 5 per function.
  4. `core/legacy.py` — 5 commits by dave, all dated 2024 while every other commit is dated 2026 (departed key contributor, >20% of commits).
  5. Root `LICENSE` — MIT text.
- Authors used: `alice@example.com`, `bob@example.com`, `carol@example.com`, `dave@example.com`. Total commits: 22.

- [ ] **Step 1: Write the fixture builder in `tests/conftest.py`**

```python
import subprocess
from pathlib import Path

import pytest

MIT_TEXT = """MIT License

Copyright (c) 2026 Example

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction.
"""

# Complex enough that lizard reports cyclomatic complexity >= 5 per function.
ENGINE_TEMPLATE = """def route_v{n}(x, y, mode):
    if mode == "a":
        if x > 0 and y > 0:
            return x + y
        return x - y
    elif mode == "b":
        if x > y:
            return x * y
        elif x < y:
            return y - x
        return 0
    elif mode == "c":
        for i in range(x):
            if i % 2 == 0:
                y += i
        return y
    return -1
"""


def _git(repo: Path, *args: str, env: dict | None = None) -> None:
    full_env = {"GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_SYSTEM": "/dev/null"}
    import os

    merged = {**os.environ, **full_env, **(env or {})}
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, env=merged)


def _commit(repo: Path, path: str, content: str, author: str, date: str) -> None:
    file_path = repo / path
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(content, encoding="utf-8")
    name = author.split("@")[0]
    _git(repo, "add", path)
    _git(
        repo,
        "-c", f"user.name={name}",
        "-c", f"user.email={author}",
        "commit", "-m", f"update {path}",
        "--date", date,
        env={"GIT_COMMITTER_DATE": date},
    )


@pytest.fixture(scope="session")
def fixture_repo(tmp_path_factory) -> Path:
    repo = tmp_path_factory.mktemp("target-repo")
    subprocess.run(["git", "init", str(repo)], check=True, capture_output=True)

    alice, bob, carol, dave = (
        "alice@example.com", "bob@example.com", "carol@example.com", "dave@example.com",
    )

    # 2 commits: LICENSE + README by alice (recent)
    _commit(repo, "LICENSE", MIT_TEXT, alice, "2026-05-01T10:00:00")
    _commit(repo, "README.md", "# Target\n", alice, "2026-05-01T11:00:00")

    # 1 commit: requirements.txt with planted GPL dep, by bob (recent)
    _commit(repo, "requirements.txt", "flask==3.0.0\nmysqlclient==2.2.0\n", bob, "2026-05-02T10:00:00")

    # 6 commits: payments/billing.py by alice ONLY (planted bus-factor-1)
    for i in range(6):
        _commit(
            repo, "payments/billing.py",
            f"def bill_{i}():\n    return {i}\n",
            alice, f"2026-05-{3 + i:02d}T10:00:00",
        )

    # 8 commits: core/engine.py by alice(3)/bob(3)/carol(2) (planted churn hotspot)
    engine_authors = [alice, alice, alice, bob, bob, bob, carol, carol]
    for i, author in enumerate(engine_authors):
        body = "".join(ENGINE_TEMPLATE.format(n=k) for k in range(i + 1))
        _commit(repo, "core/engine.py", body, author, f"2026-05-{10 + i:02d}T10:00:00")

    # 5 commits: core/legacy.py by dave, OLD dates (planted departed contributor)
    for i in range(5):
        _commit(
            repo, "core/legacy.py",
            f"LEGACY = {i}\n",
            dave, f"2024-03-{10 + i:02d}T10:00:00",
        )

    return repo
```

- [ ] **Step 2: Write the failing verification test**

Create `tests/test_fixture.py`:

```python
import subprocess


def test_fixture_repo_has_planted_shape(fixture_repo):
    out = subprocess.run(
        ["git", "-C", str(fixture_repo), "log", "--format=%ae"],
        check=True, capture_output=True, text=True,
    ).stdout.split()
    assert len(out) == 22
    assert out.count("dave@example.com") == 5
    assert (fixture_repo / "payments" / "billing.py").exists()
    assert "mysqlclient" in (fixture_repo / "requirements.txt").read_text(encoding="utf-8")
```

- [ ] **Step 3: Run test to verify it passes**

Run: `pytest tests/test_fixture.py -v`
Expected: PASS (the fixture is test infrastructure; this test verifies the planted shape and guards against fixture drift)

- [ ] **Step 4: Commit**

```bash
git add tests/conftest.py tests/test_fixture.py
git commit -m "test: add synthetic fixture repo with planted DD issues"
```

---

### Task 3: Repo ingestion — typed commit history from git

**Files:**
- Create: `src/acquirescope/ingest.py`
- Test: `tests/test_ingest.py`

**Interfaces:**
- Consumes: `fixture_repo` fixture (Task 2).
- Produces: `FileChange(path: str, added: int, deleted: int)`; `Commit(sha: str, author_email: str, author_name: str, authored_at: datetime, changes: list[FileChange])`; `RepoIngest(repo_path: Path)` with methods `commits() -> list[Commit]` (newest first, cached after first call) and `list_files() -> list[str]` (tracked files at HEAD, forward-slash paths). Importable from `acquirescope.ingest`. Tasks 4–6 call ONLY these.

- [ ] **Step 1: Write the failing test**

Create `tests/test_ingest.py`:

```python
from pathlib import Path

from acquirescope.ingest import RepoIngest


def test_commits_parsed_with_authors_and_changes(fixture_repo):
    ingest = RepoIngest(Path(fixture_repo))
    commits = ingest.commits()
    assert len(commits) == 22
    newest = commits[0]
    assert newest.sha and newest.author_email.endswith("@example.com")
    dave_commits = [c for c in commits if c.author_email == "dave@example.com"]
    assert len(dave_commits) == 5
    assert all(c.authored_at.year == 2024 for c in dave_commits)
    assert any(ch.path == "core/legacy.py" for c in dave_commits for ch in c.changes)


def test_list_files_returns_tracked_paths(fixture_repo):
    ingest = RepoIngest(Path(fixture_repo))
    files = ingest.list_files()
    assert "payments/billing.py" in files
    assert "requirements.txt" in files
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_ingest.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'acquirescope.ingest'`

- [ ] **Step 3: Write the implementation**

Create `src/acquirescope/ingest.py`:

```python
from __future__ import annotations

import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

# %x1e = record separator between commits, %x1f = field separator within header
_LOG_FORMAT = "%x1e%H%x1f%ae%x1f%an%x1f%aI"


@dataclass
class FileChange:
    path: str
    added: int
    deleted: int


@dataclass
class Commit:
    sha: str
    author_email: str
    author_name: str
    authored_at: datetime
    changes: list[FileChange]


class RepoIngest:
    def __init__(self, repo_path: Path):
        self.repo_path = repo_path
        self._commits: list[Commit] | None = None

    def _git(self, *args: str) -> str:
        result = subprocess.run(
            ["git", "-C", str(self.repo_path), *args],
            check=True, capture_output=True, text=True, encoding="utf-8",
        )
        return result.stdout

    def commits(self) -> list[Commit]:
        if self._commits is not None:
            return self._commits
        raw = self._git("log", "--numstat", f"--format={_LOG_FORMAT}")
        parsed: list[Commit] = []
        for record in raw.split("\x1e")[1:]:
            lines = [ln for ln in record.strip("\n").split("\n") if ln.strip()]
            sha, email, name, iso_date = lines[0].split("\x1f")
            changes = []
            for line in lines[1:]:
                added_s, deleted_s, path = line.split("\t", 2)
                changes.append(FileChange(
                    path=path,
                    added=0 if added_s == "-" else int(added_s),
                    deleted=0 if deleted_s == "-" else int(deleted_s),
                ))
            parsed.append(Commit(
                sha=sha, author_email=email, author_name=name,
                authored_at=datetime.fromisoformat(iso_date), changes=changes,
            ))
        self._commits = parsed
        return parsed

    def list_files(self) -> list[str]:
        return [ln for ln in self._git("ls-files").splitlines() if ln.strip()]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_ingest.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add src/acquirescope/ingest.py tests/test_ingest.py
git commit -m "feat: add git-backed repo ingestion with typed commit history"
```

---

### Task 4: Bus factor & key-person risk module

**Files:**
- Create: `src/acquirescope/modules/__init__.py` (empty file)
- Create: `src/acquirescope/modules/bus_factor.py`
- Test: `tests/test_bus_factor.py`

**Interfaces:**
- Consumes: `RepoIngest.commits()` (Task 3), models (Task 1).
- Produces: `analyze(ingest: RepoIngest) -> ModuleResult` in `acquirescope.modules.bus_factor` with `module="bus_factor"`. Emits: HIGH finding per top-level directory with bus factor 1 (≥5 commits); HIGH finding per departed key contributor (≥20% of commits, inactive >180 days vs repo's latest commit). Metrics: `contributor_gini` (float), `top_author_share` (float).

- [ ] **Step 1: Write the failing test**

Create `tests/test_bus_factor.py`:

```python
from pathlib import Path

from acquirescope.ingest import RepoIngest
from acquirescope.models import Severity
from acquirescope.modules import bus_factor


def test_flags_single_owner_directory(fixture_repo):
    result = bus_factor.analyze(RepoIngest(Path(fixture_repo)))
    assert result.status == "ok"
    single_owner = [f for f in result.findings if "payments" in f.title]
    assert len(single_owner) == 1
    assert single_owner[0].severity == Severity.HIGH
    assert any(e.detail == "alice@example.com" for e in single_owner[0].evidence)


def test_flags_departed_key_contributor(fixture_repo):
    result = bus_factor.analyze(RepoIngest(Path(fixture_repo)))
    departed = [f for f in result.findings if "departed" in f.title.lower()]
    assert len(departed) == 1
    assert any(e.detail == "dave@example.com" for e in departed[0].evidence)


def test_concentration_metrics_present(fixture_repo):
    result = bus_factor.analyze(RepoIngest(Path(fixture_repo)))
    assert 0.0 <= result.metrics["contributor_gini"] <= 1.0
    assert 0.0 < result.metrics["top_author_share"] <= 1.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_bus_factor.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'acquirescope.modules'`

- [ ] **Step 3: Write the implementation**

Create empty `src/acquirescope/modules/__init__.py`, then `src/acquirescope/modules/bus_factor.py`:

```python
from __future__ import annotations

from collections import Counter, defaultdict

from acquirescope.ingest import RepoIngest
from acquirescope.models import Evidence, Finding, ModuleResult, Severity

MIN_DIR_COMMITS = 5       # directories with fewer commits are too small to judge
DEPARTED_SHARE = 0.20     # author owns >= 20% of all commits
DEPARTED_DAYS = 180       # and has been inactive this long vs latest commit
MODULE = "bus_factor"


def _bus_factor(author_counts: Counter) -> int:
    """Smallest number of authors covering >= 50% of a directory's commits."""
    total = sum(author_counts.values())
    covered, k = 0, 0
    for _, count in author_counts.most_common():
        covered += count
        k += 1
        if covered * 2 >= total:
            return k
    return k


def _gini(values: list[int]) -> float:
    if not values or sum(values) == 0:
        return 0.0
    sorted_vals = sorted(values)
    n = len(sorted_vals)
    cum = sum((i + 1) * v for i, v in enumerate(sorted_vals))
    return (2 * cum) / (n * sum(sorted_vals)) - (n + 1) / n


def analyze(ingest: RepoIngest) -> ModuleResult:
    commits = ingest.commits()
    findings: list[Finding] = []

    # Per top-level directory: which authors touch it, how often.
    dir_authors: dict[str, Counter] = defaultdict(Counter)
    for commit in commits:
        touched_dirs = {
            change.path.split("/", 1)[0] if "/" in change.path else "<root>"
            for change in commit.changes
        }
        for d in touched_dirs:
            dir_authors[d][commit.author_email] += 1

    for directory, counts in sorted(dir_authors.items()):
        total = sum(counts.values())
        if total < MIN_DIR_COMMITS:
            continue
        if _bus_factor(counts) == 1:
            owner, owner_count = counts.most_common(1)[0]
            findings.append(Finding(
                module=MODULE,
                title=f"Single point of failure: {directory}/",
                severity=Severity.HIGH,
                summary=(
                    f"One contributor accounts for the majority of all {total} commits "
                    f"touching {directory}/ ({owner_count} commits). Loss of this person "
                    f"strands the component."
                ),
                evidence=[Evidence(
                    description=f"{owner_count}/{total} commits in {directory}/",
                    path=directory, detail=owner,
                )],
            ))

    # Departed key contributors.
    author_totals = Counter(c.author_email for c in commits)
    total_commits = len(commits)
    latest = max(c.authored_at for c in commits)
    last_seen = {}
    for c in commits:
        prev = last_seen.get(c.author_email)
        if prev is None or c.authored_at > prev:
            last_seen[c.author_email] = c.authored_at
    for author, count in author_totals.items():
        share = count / total_commits
        inactive_days = (latest - last_seen[author]).days
        if share >= DEPARTED_SHARE and inactive_days > DEPARTED_DAYS:
            findings.append(Finding(
                module=MODULE,
                title=f"Departed key contributor: {author}",
                severity=Severity.HIGH,
                summary=(
                    f"{author} authored {share:.0%} of all commits but has been inactive "
                    f"for {inactive_days} days. Their knowledge may already be lost."
                ),
                evidence=[Evidence(
                    description=f"{count}/{total_commits} commits; last active {last_seen[author].date()}",
                    detail=author,
                )],
            ))

    top_share = author_totals.most_common(1)[0][1] / total_commits
    return ModuleResult(
        module=MODULE, status="ok", findings=findings,
        metrics={
            "contributor_gini": round(_gini(list(author_totals.values())), 3),
            "top_author_share": round(top_share, 3),
        },
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_bus_factor.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add src/acquirescope/modules/__init__.py src/acquirescope/modules/bus_factor.py tests/test_bus_factor.py
git commit -m "feat: add bus factor and key-person risk analysis module"
```

---

### Task 5: License risk module

**Files:**
- Create: `src/acquirescope/modules/licenses.py`
- Test: `tests/test_licenses.py`

**Interfaces:**
- Consumes: `RepoIngest.list_files()`, `RepoIngest.repo_path` (Task 3), models (Task 1).
- Produces: `analyze(ingest: RepoIngest) -> ModuleResult` in `acquirescope.modules.licenses` with `module="licenses"`. Emits: INFO finding for the repo's own root license classification; HIGH finding per copyleft dependency found in `requirements.txt` or `pyproject.toml` (matched against a built-in map); INFO finding when non-Python manifests exist but aren't assessed (honest scope note). Metrics: `own_license` (str), `copyleft_dependency_count` (int).

- [ ] **Step 1: Write the failing test**

Create `tests/test_licenses.py`:

```python
from pathlib import Path

from acquirescope.ingest import RepoIngest
from acquirescope.models import Severity
from acquirescope.modules import licenses


def test_classifies_own_mit_license(fixture_repo):
    result = licenses.analyze(RepoIngest(Path(fixture_repo)))
    assert result.status == "ok"
    assert result.metrics["own_license"] == "MIT"


def test_flags_copyleft_dependency(fixture_repo):
    result = licenses.analyze(RepoIngest(Path(fixture_repo)))
    copyleft = [f for f in result.findings if f.severity == Severity.HIGH]
    assert len(copyleft) == 1
    assert "mysqlclient" in copyleft[0].summary
    assert copyleft[0].evidence[0].path == "requirements.txt"
    assert result.metrics["copyleft_dependency_count"] == 1


def test_clean_dependency_not_flagged(fixture_repo):
    result = licenses.analyze(RepoIngest(Path(fixture_repo)))
    assert not any("flask" in f.summary for f in result.findings)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_licenses.py -v`
Expected: FAIL with `ImportError: cannot import name 'licenses'`

- [ ] **Step 3: Write the implementation**

Create `src/acquirescope/modules/licenses.py`:

```python
from __future__ import annotations

import re
import tomllib

from acquirescope.ingest import RepoIngest
from acquirescope.models import Evidence, Finding, ModuleResult, Severity

MODULE = "licenses"

# Signature phrases -> SPDX-ish label, checked in order (AGPL before GPL).
_LICENSE_SIGNATURES = [
    ("GNU AFFERO GENERAL PUBLIC LICENSE", "AGPL-3.0"),
    ("GNU LESSER GENERAL PUBLIC LICENSE", "LGPL"),
    ("GNU GENERAL PUBLIC LICENSE", "GPL"),
    ("MIT LICENSE", "MIT"),
    ("APACHE LICENSE", "Apache-2.0"),
    ("BSD", "BSD"),
    ("MOZILLA PUBLIC LICENSE", "MPL-2.0"),
]

# Known-copyleft PyPI packages (curated, extensible). Names lowercased.
COPYLEFT_PYPI = {
    "mysqlclient": "GPL-2.0",
    "pyqt5": "GPL-3.0",
    "pyqt6": "GPL-3.0",
    "python-vlc": "LGPL-2.1",
    "rpy2": "GPL-2.0",
    "pygraphviz": "BSD",  # not copyleft; kept out below — see test for flask
}
# Only these licenses trigger a finding.
_COPYLEFT_PREFIXES = ("GPL", "AGPL", "LGPL")

_REQ_NAME = re.compile(r"^\s*([A-Za-z0-9._-]+)")


def _classify_license_text(text: str) -> str:
    upper = text.upper()
    for signature, label in _LICENSE_SIGNATURES:
        if signature in upper:
            return label
    return "Unknown"


def _python_dependencies(ingest: RepoIngest) -> list[tuple[str, str]]:
    """Returns (package_name_lowercased, manifest_path) pairs."""
    deps: list[tuple[str, str]] = []
    files = set(ingest.list_files())
    if "requirements.txt" in files:
        text = (ingest.repo_path / "requirements.txt").read_text(encoding="utf-8")
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith(("#", "-")):
                continue
            match = _REQ_NAME.match(line)
            if match:
                deps.append((match.group(1).lower(), "requirements.txt"))
    if "pyproject.toml" in files:
        data = tomllib.loads((ingest.repo_path / "pyproject.toml").read_text(encoding="utf-8"))
        for spec in data.get("project", {}).get("dependencies", []):
            match = _REQ_NAME.match(spec)
            if match:
                deps.append((match.group(1).lower(), "pyproject.toml"))
    return deps


def analyze(ingest: RepoIngest) -> ModuleResult:
    findings: list[Finding] = []
    files = ingest.list_files()

    # 1. The target's own license.
    own_license = "None found"
    license_files = [f for f in files if f.upper().startswith("LICENSE")]
    if license_files:
        text = (ingest.repo_path / license_files[0]).read_text(encoding="utf-8", errors="replace")
        own_license = _classify_license_text(text)
    findings.append(Finding(
        module=MODULE,
        title=f"Repository license: {own_license}",
        severity=Severity.INFO,
        summary=f"The target repository itself is licensed under {own_license}.",
        evidence=[Evidence(description="root license file", path=license_files[0] if license_files else None)],
    ))

    # 2. Copyleft dependencies in Python manifests.
    copyleft_count = 0
    for name, manifest in _python_dependencies(ingest):
        license_label = COPYLEFT_PYPI.get(name)
        if license_label and license_label.startswith(_COPYLEFT_PREFIXES):
            copyleft_count += 1
            findings.append(Finding(
                module=MODULE,
                title=f"Copyleft dependency: {name}",
                severity=Severity.HIGH,
                summary=(
                    f"Dependency '{name}' is {license_label} licensed. Copyleft obligations "
                    f"can restrict proprietary distribution and are a diligence red flag."
                ),
                evidence=[Evidence(description=f"declared in {manifest}", path=manifest, detail=name)],
            ))

    # 3. Honest scope note for ecosystems we don't assess yet.
    unassessed = [f for f in files if f.endswith(("package.json", "go.mod", "Cargo.toml", "Gemfile"))]
    if unassessed:
        findings.append(Finding(
            module=MODULE,
            title="Non-Python manifests not assessed",
            severity=Severity.INFO,
            summary=f"Found {len(unassessed)} non-Python manifest(s); license scan covers Python only in this version.",
            evidence=[Evidence(description="unassessed manifest", path=p) for p in unassessed],
        ))

    return ModuleResult(
        module=MODULE, status="ok", findings=findings,
        metrics={"own_license": own_license, "copyleft_dependency_count": copyleft_count},
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_licenses.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add src/acquirescope/modules/licenses.py tests/test_licenses.py
git commit -m "feat: add license risk module with copyleft dependency detection"
```

---

### Task 6: Tech-debt hotspot module with remediation estimate

**Files:**
- Create: `src/acquirescope/modules/hotspots.py`
- Test: `tests/test_hotspots.py`

**Interfaces:**
- Consumes: `RepoIngest.commits()`, `RepoIngest.list_files()`, `RepoIngest.repo_path` (Task 3), models (Task 1), `lizard` library.
- Produces: `analyze(ingest: RepoIngest) -> ModuleResult` in `acquirescope.modules.hotspots` with `module="hotspots"`. Emits: MEDIUM finding per hotspot file (churn ≥ 75th percentile AND average cyclomatic complexity ≥ 5). Metrics: `hotspot_count` (int), `remediation_months_low`, `remediation_months_mid`, `remediation_months_high` (floats — the mandatory confidence band). Formula (documented in code): per hotspot file `months = (nloc / 2000) * (avg_ccn / 10)`; band = mid × 0.5 / mid × 1.5.

- [ ] **Step 1: Write the failing test**

Create `tests/test_hotspots.py`:

```python
from pathlib import Path

from acquirescope.ingest import RepoIngest
from acquirescope.models import Severity
from acquirescope.modules import hotspots


def test_flags_high_churn_complex_file(fixture_repo):
    result = hotspots.analyze(RepoIngest(Path(fixture_repo)))
    assert result.status == "ok"
    flagged_paths = [e.path for f in result.findings for e in f.evidence]
    assert "core/engine.py" in flagged_paths


def test_simple_churned_file_not_flagged(fixture_repo):
    # payments/billing.py has 6 commits (high churn) but trivial complexity.
    result = hotspots.analyze(RepoIngest(Path(fixture_repo)))
    flagged_paths = [e.path for f in result.findings for e in f.evidence]
    assert "payments/billing.py" not in flagged_paths


def test_remediation_estimate_has_confidence_band(fixture_repo):
    result = hotspots.analyze(RepoIngest(Path(fixture_repo)))
    low = result.metrics["remediation_months_low"]
    mid = result.metrics["remediation_months_mid"]
    high = result.metrics["remediation_months_high"]
    assert 0 < low < mid < high
    assert all(isinstance(f.severity, Severity) for f in result.findings)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_hotspots.py -v`
Expected: FAIL with `ImportError: cannot import name 'hotspots'`

- [ ] **Step 3: Write the implementation**

Create `src/acquirescope/modules/hotspots.py`:

```python
from __future__ import annotations

import statistics
from collections import Counter

import lizard

from acquirescope.ingest import RepoIngest
from acquirescope.models import Evidence, Finding, ModuleResult, Severity

MODULE = "hotspots"
MIN_AVG_CCN = 5.0
SOURCE_EXTENSIONS = (".py", ".js", ".ts", ".tsx", ".jsx", ".go", ".java", ".rb", ".rs", ".c", ".cc", ".cpp", ".cs", ".php", ".swift", ".kt")

# Remediation model (documented assumption, spec requires a confidence band):
# a hotspot file costs (nloc / 2000) * (avg_ccn / 10) engineer-months to bring
# to maintainable state — i.e. a 2000-line file at CCN 10 ~ 1 engineer-month.
# Band is +/- 50% because the calibration is benchmark-based, not measured.
NLOC_PER_MONTH = 2000
CCN_BASELINE = 10
BAND = 0.5


def analyze(ingest: RepoIngest) -> ModuleResult:
    churn: Counter = Counter()
    for commit in ingest.commits():
        for change in commit.changes:
            churn[change.path] += 1

    tracked = set(ingest.list_files())
    source_churn = {
        path: count for path, count in churn.items()
        if path in tracked and path.endswith(SOURCE_EXTENSIONS)
    }
    if not source_churn:
        return ModuleResult(module=MODULE, status="ok", metrics={
            "hotspot_count": 0,
            "remediation_months_low": 0.0,
            "remediation_months_mid": 0.0,
            "remediation_months_high": 0.0,
        })

    churn_threshold = statistics.quantiles(list(source_churn.values()), n=4)[2]  # 75th pct

    findings: list[Finding] = []
    total_months = 0.0
    for path, count in sorted(source_churn.items(), key=lambda kv: -kv[1]):
        if count < churn_threshold:
            continue
        analysis = lizard.analyze_file(str(ingest.repo_path / path))
        functions = analysis.function_list
        if not functions:
            continue
        avg_ccn = sum(f.cyclomatic_complexity for f in functions) / len(functions)
        if avg_ccn < MIN_AVG_CCN:
            continue
        months = (analysis.nloc / NLOC_PER_MONTH) * (avg_ccn / CCN_BASELINE)
        total_months += months
        findings.append(Finding(
            module=MODULE,
            title=f"Tech-debt hotspot: {path}",
            severity=Severity.MEDIUM,
            summary=(
                f"{path} combines high change frequency ({count} commits) with high "
                f"complexity (avg CCN {avg_ccn:.1f} across {len(functions)} functions, "
                f"{analysis.nloc} NLOC). Estimated remediation: {months:.2f} engineer-months "
                f"(+/-50%)."
            ),
            evidence=[Evidence(
                description=f"churn={count} commits, avg_ccn={avg_ccn:.1f}, nloc={analysis.nloc}",
                path=path,
            )],
        ))

    return ModuleResult(
        module=MODULE, status="ok", findings=findings,
        metrics={
            "hotspot_count": len(findings),
            "remediation_months_low": round(total_months * (1 - BAND), 3),
            "remediation_months_mid": round(total_months, 3),
            "remediation_months_high": round(total_months * (1 + BAND), 3),
        },
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_hotspots.py -v`
Expected: 3 passed. If `test_remediation_estimate_has_confidence_band` fails with `low == 0`: the fixture's engine.py must produce months > 0 — verify lizard sees it (`python -c "import lizard; print(lizard.analyze_file('<fixture>/core/engine.py').nloc)"`).

- [ ] **Step 5: Commit**

```bash
git add src/acquirescope/modules/hotspots.py tests/test_hotspots.py
git commit -m "feat: add churn-vs-complexity hotspot module with banded remediation estimate"
```

---

### Task 7: Markdown report renderer

**Files:**
- Create: `src/acquirescope/report.py`
- Test: `tests/test_report.py`

**Interfaces:**
- Consumes: models (Task 1).
- Produces: `render_markdown(repo_name: str, results: list[ModuleResult]) -> str` in `acquirescope.report`. Failed modules render a "Not assessed" section containing the error. Findings render grouped by module with severity tags and evidence lines. Ends with a disclaimer paragraph (spec's legal guardrail).

- [ ] **Step 1: Write the failing test**

Create `tests/test_report.py`:

```python
from acquirescope.models import Evidence, Finding, ModuleResult, Severity
from acquirescope.report import render_markdown


def _sample_results():
    return [
        ModuleResult(
            module="licenses", status="ok",
            findings=[Finding(
                module="licenses", title="Copyleft dependency: mysqlclient",
                severity=Severity.HIGH, summary="GPL-2.0 dependency.",
                evidence=[Evidence(description="declared in requirements.txt", path="requirements.txt", detail="mysqlclient")],
            )],
            metrics={"copyleft_dependency_count": 1},
        ),
        ModuleResult(module="hotspots", status="failed", error="lizard exploded"),
    ]


def test_report_contains_findings_and_severity():
    md = render_markdown("target-repo", _sample_results())
    assert "# Technical Due Diligence Report: target-repo" in md
    assert "Copyleft dependency: mysqlclient" in md
    assert "[HIGH]" in md
    assert "requirements.txt" in md


def test_failed_module_marked_not_assessed():
    md = render_markdown("target-repo", _sample_results())
    assert "Not assessed" in md
    assert "lizard exploded" in md


def test_report_ends_with_disclaimer():
    md = render_markdown("target-repo", _sample_results())
    assert "educational analysis" in md.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_report.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'acquirescope.report'`

- [ ] **Step 3: Write the implementation**

Create `src/acquirescope/report.py`:

```python
from __future__ import annotations

from acquirescope.models import ModuleResult

_DISCLAIMER = (
    "*This report is an automated, educational analysis of publicly available "
    "data as of the run date. It is not investment advice, not a statement about "
    "any company's value or conduct, and findings are observations that may be "
    "incomplete or outdated.*"
)


def render_markdown(repo_name: str, results: list[ModuleResult]) -> str:
    lines = [f"# Technical Due Diligence Report: {repo_name}", ""]

    for result in results:
        lines.append(f"## Module: {result.module}")
        lines.append("")
        if result.status == "failed":
            lines.append(f"**Not assessed** — module failed: `{result.error}`")
            lines.append("")
            continue
        if result.metrics:
            lines.append("**Metrics:** " + ", ".join(f"{k}={v}" for k, v in result.metrics.items()))
            lines.append("")
        if not result.findings:
            lines.append("No findings.")
            lines.append("")
            continue
        for finding in result.findings:
            lines.append(f"### [{finding.severity.value.upper()}] {finding.title}")
            lines.append("")
            lines.append(finding.summary)
            lines.append("")
            for ev in finding.evidence:
                location = f" (`{ev.path}`)" if ev.path else ""
                detail = f" — {ev.detail}" if ev.detail else ""
                lines.append(f"- Evidence: {ev.description}{location}{detail}")
            lines.append("")

    lines.append("---")
    lines.append("")
    lines.append(_DISCLAIMER)
    lines.append("")
    return "\n".join(lines)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_report.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add src/acquirescope/report.py tests/test_report.py
git commit -m "feat: add markdown DD report renderer with not-assessed degradation"
```

---

### Task 8: CLI with graceful module failure

**Files:**
- Create: `src/acquirescope/cli.py`
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: everything above. Module registry: `MODULES: list[tuple[str, Callable]]` = bus_factor, licenses, hotspots `analyze` functions.
- Produces: Typer app `app` in `acquirescope.cli`; command `analyze REPO_PATH --output PATH` (default `dd-report.md`) that writes the markdown report and exits 0 even when a module raises. Installed as console script `acquirescope` (Task 1's pyproject already declares it).

- [ ] **Step 1: Write the failing test**

Create `tests/test_cli.py`:

```python
from pathlib import Path

from typer.testing import CliRunner

from acquirescope import cli

runner = CliRunner()


def test_analyze_writes_report(fixture_repo, tmp_path):
    out = tmp_path / "report.md"
    result = runner.invoke(cli.app, [str(fixture_repo), "--output", str(out)])
    assert result.exit_code == 0
    assert out.exists()
    md = out.read_text(encoding="utf-8")
    assert "# Technical Due Diligence Report:" in md


def test_module_crash_degrades_gracefully(fixture_repo, tmp_path, monkeypatch):
    def explode(ingest):
        raise RuntimeError("boom")

    monkeypatch.setitem(dict(), "unused", None)  # keep monkeypatch fixture engaged
    monkeypatch.setattr(cli, "MODULES", [("hotspots", explode)] + [m for m in cli.MODULES if m[0] != "hotspots"])
    out = tmp_path / "report.md"
    result = runner.invoke(cli.app, [str(fixture_repo), "--output", str(out)])
    assert result.exit_code == 0
    md = out.read_text(encoding="utf-8")
    assert "Not assessed" in md
    assert "boom" in md
    # other modules still ran
    assert "Module: bus_factor" in md
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_cli.py -v`
Expected: FAIL with `ModuleNotFoundError` / `ImportError` on `acquirescope.cli`

- [ ] **Step 3: Write the implementation**

Create `src/acquirescope/cli.py`:

```python
from __future__ import annotations

from pathlib import Path
from typing import Callable

import typer

from acquirescope.ingest import RepoIngest
from acquirescope.models import ModuleResult
from acquirescope.modules import bus_factor, hotspots, licenses
from acquirescope.report import render_markdown

app = typer.Typer(add_completion=False)

MODULES: list[tuple[str, Callable[[RepoIngest], ModuleResult]]] = [
    ("bus_factor", bus_factor.analyze),
    ("licenses", licenses.analyze),
    ("hotspots", hotspots.analyze),
]


@app.command()
def analyze(
    repo_path: Path = typer.Argument(..., exists=True, file_okay=False, help="Path to a local git repository"),
    output: Path = typer.Option(Path("dd-report.md"), "--output", "-o", help="Report output path"),
) -> None:
    """Run all due-diligence modules against REPO_PATH and write a markdown report."""
    ingest = RepoIngest(repo_path)
    results: list[ModuleResult] = []
    for name, analyze_fn in MODULES:
        try:
            results.append(analyze_fn(ingest))
        except Exception as exc:  # graceful degradation is a spec requirement
            results.append(ModuleResult(module=name, status="failed", error=str(exc)))
    output.write_text(render_markdown(repo_path.name, results), encoding="utf-8")
    typer.echo(f"Report written to {output}")


if __name__ == "__main__":
    app()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_cli.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add src/acquirescope/cli.py tests/test_cli.py
git commit -m "feat: add analyze CLI with per-module graceful failure"
```

---

### Task 9: End-to-end planted-issue regression test

**Files:**
- Modify: `tests/test_cli.py` (append one test)

**Interfaces:**
- Consumes: the full pipeline (Tasks 1–8) and the fixture's planted issues (Task 2).
- Produces: the spec's mandated regression gate — "the engine must find all planted issues."

- [ ] **Step 1: Write the failing-or-passing regression test**

Append to `tests/test_cli.py`:

```python
def test_all_planted_issues_detected_end_to_end(fixture_repo, tmp_path):
    """Spec regression gate: every planted issue in the synthetic repo is found."""
    out = tmp_path / "e2e-report.md"
    result = runner.invoke(cli.app, [str(fixture_repo), "--output", str(out)])
    assert result.exit_code == 0
    md = out.read_text(encoding="utf-8")

    # Planted issue 1: payments/ single-owner module
    assert "Single point of failure: payments/" in md
    # Planted issue 2: GPL dependency in requirements.txt
    assert "Copyleft dependency: mysqlclient" in md
    # Planted issue 3: churn+complexity hotspot
    assert "Tech-debt hotspot: core/engine.py" in md
    # Planted issue 4: departed key contributor
    assert "Departed key contributor: dave@example.com" in md
    # Confidence band present in metrics line
    assert "remediation_months_low" in md
```

- [ ] **Step 2: Run the full suite**

Run: `pytest -v`
Expected: ALL tests pass (17 total). If the e2e test alone fails, a module regressed — its own unit tests localize which.

- [ ] **Step 3: Commit**

```bash
git add tests/test_cli.py
git commit -m "test: add end-to-end planted-issue regression gate"
```

---

## Self-review notes

- **Spec coverage (Phase 1 scope):** engine core modules (bus factor ✓ Task 4, licenses ✓ Task 5, tech debt ✓ Task 6), evidence-linked findings ✓ (models + all modules), graceful degradation ✓ (Task 8), confidence bands ✓ (Task 6 metrics, tested), synthetic planted-issue regression repo ✓ (Tasks 2 + 9), CLI ✓ (Task 8). Deliberately deferred to Phase 2/3 plans: financial bridge/Excel, security posture, delivery health, LLM narrative, GitLab validation, published reports.
- **Known scope cuts made honest in-product:** license scan is Python-manifest-only in Phase 1 and says so in the report (Task 5 finding #3); SBOM via syft/ORT arrives with Phase 3's security module.
- **Type consistency check:** `analyze(ingest: RepoIngest) -> ModuleResult` uniform across modules; `MODULES` registry names match module `MODULE` constants; renderer consumes only `ModuleResult`/`Finding`/`Evidence` fields defined in Task 1.
