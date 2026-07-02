# AcquireScope Security, Delivery & Narrative Implementation Plan (Phase 3 of 3)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete the engine with security-posture and delivery-health modules, price the "Security remediation" line item that Phase 2 stubbed as "Not assessed", and add an optional citation-verified LLM narrative to the markdown report.

**Architecture:** Two new pure modules follow the Phase 1 contract (`analyze(ingest) -> ModuleResult`); `RepoIngest` grows commit parents, `tags()`, and `full_patch_text()` to feed them. The narrative layer is a pure function taking an injected `complete: Callable[[str], str]` with citation verification against finding IDs; the Anthropic client is wired only in the CLI behind `analyze --narrative`. The fixture repo gains a committed-then-removed AWS key and two release tags (22 → 24 commits).

**Tech Stack:** Python 3.12, existing engine, `anthropic` as optional extra `llm` (lazy import), optional `osv-scanner` binary via subprocess (never required by tests).

**Spec:** `docs/superpowers/specs/2026-07-01-acquirescope-phase3-security-delivery-narrative-design.md`

## Global Constraints

- Python 3.12; source under `src/acquirescope/`, tests under `tests/`.
- Module failure degrades gracefully (report "Not assessed", exit 0); osv-scanner absence/failure is *within-module* degradation (INFO note), not a module failure.
- Narrative failure never blocks the report: warning to stderr, report written without the section, exit 0. Missing SDK/key with `--narrative` → stderr message, exit 1, before analysis.
- Tests never require osv-scanner or network; the Anthropic path is tested via monkeypatched `_anthropic_complete`.
- Anthropic model id: `claude-opus-4-8`, `max_tokens=2048` (short deliverable; do not downgrade tier for cost).
- All textual I/O `encoding="utf-8"`.
- `MODULES` registry order: bus_factor, licenses, hotspots, security, delivery.

## File Structure

```
tests/conftest.py                       # modify: +2 secret commits, +2 tags (24 commits)
tests/test_fixture.py                   # modify: counts, tags, secret-absent-at-HEAD
tests/test_ingest.py                    # modify count; add parents/tags/patch tests
src/acquirescope/ingest.py              # modify: %P parents, tags(), full_patch_text()
src/acquirescope/modules/security.py    # new module
src/acquirescope/modules/delivery.py    # new module
src/acquirescope/bridge/assumptions.py  # modify: security_fix_cost_usd
examples/assumptions.example.toml       # modify: security_fix_cost_usd
src/acquirescope/bridge/adjustments.py  # modify: price security line item
src/acquirescope/narrative.py           # new: build_prompt, verify_citations, generate_narrative
src/acquirescope/report.py              # modify: optional narrative section
src/acquirescope/cli.py                 # modify: registry + --narrative + _anthropic_complete
pyproject.toml                          # modify: optional-dependencies llm
tests/test_security.py                  # new
tests/test_delivery.py                  # new
tests/test_narrative.py                 # new
tests/test_valuation.py                 # modify: factory gains security_fix_cost_usd
tests/test_adjustments.py               # modify: factory + security pricing tests
tests/test_excel.py                     # modify: factory gains security_fix_cost_usd
tests/test_assumptions.py               # modify: assert new key loads
tests/test_report.py                    # modify: narrative section test
tests/test_cli.py                       # modify: narrative tests + e2e gate updates
```

---

### Task 1: Fixture — planted secret and release tags

**Files:**
- Modify: `tests/conftest.py`
- Modify: `tests/test_fixture.py`
- Modify: `tests/test_ingest.py` (count assertion only)

**Interfaces:**
- Consumes: existing `_commit` / `_git` helpers in conftest.
- Produces: `fixture_repo` now has 24 commits; tags `v0.1.0` (on the requirements commit, dated 2026-05-02) and `v0.2.0` (on the last engine commit, dated 2026-05-17); `config/settings.py` committed by bob containing `AWS_KEY = "AKIAIOSFODNN7EXAMPLE"` (2026-05-18), then the key removed (2026-05-19). Latest commit date is now 2026-05-19. Checked invariants: dave keeps ≥20% share (5/24), hotspot churn threshold still flags only `core/engine.py`.

- [ ] **Step 1: Add tags and secret commits to the fixture builder**

In `tests/conftest.py`, inside `fixture_repo`, add a tag right after the requirements commit:

```python
    # 1 commit: requirements.txt with planted GPL dep, by bob (recent)
    _commit(repo, "requirements.txt", "flask==3.0.0\nmysqlclient==2.2.0\n", bob, "2026-05-02T10:00:00")
    _git(repo, "tag", "v0.1.0")
```

Add a tag right after the engine-commit loop (after the `for i, author in enumerate(engine_authors):` block):

```python
    _git(repo, "tag", "v0.2.0")
```

Add at the end of the fixture, after the dave loop and before `return repo`:

```python
    # 2 commits: planted secret added then removed by bob (recent dates).
    # The key is gone at HEAD but remains recoverable from history.
    _commit(
        repo, "config/settings.py",
        'DEBUG = False\nAWS_KEY = "AKIAIOSFODNN7EXAMPLE"\n',
        bob, "2026-05-18T10:00:00",
    )
    _commit(
        repo, "config/settings.py",
        "DEBUG = False\n",
        bob, "2026-05-19T10:00:00",
    )
```

- [ ] **Step 2: Update the fixture shape test**

Replace the body of `tests/test_fixture.py` with:

```python
import subprocess


def test_fixture_repo_has_planted_shape(fixture_repo):
    out = subprocess.run(
        ["git", "-C", str(fixture_repo), "log", "--format=%ae"],
        check=True, capture_output=True, text=True,
    ).stdout.split()
    assert len(out) == 24
    assert out.count("dave@example.com") == 5
    assert (fixture_repo / "payments" / "billing.py").exists()
    assert "mysqlclient" in (fixture_repo / "requirements.txt").read_text(encoding="utf-8")

    # Planted secret is removed at HEAD but present in history
    head_settings = (fixture_repo / "config" / "settings.py").read_text(encoding="utf-8")
    assert "AKIA" not in head_settings
    log_p = subprocess.run(
        ["git", "-C", str(fixture_repo), "log", "-p"],
        check=True, capture_output=True, text=True,
    ).stdout
    assert "AKIAIOSFODNN7EXAMPLE" in log_p

    tags = subprocess.run(
        ["git", "-C", str(fixture_repo), "tag", "--list"],
        check=True, capture_output=True, text=True,
    ).stdout.split()
    assert sorted(tags) == ["v0.1.0", "v0.2.0"]
```

- [ ] **Step 3: Update the ingest commit-count assertion**

In `tests/test_ingest.py::test_commits_parsed_with_authors_and_changes`, change `assert len(commits) == 22` to `assert len(commits) == 24`.

- [ ] **Step 4: Run the full suite to verify nothing else regressed**

Run: `pytest -v`
Expected: ALL 44 tests pass. (Bus factor: dave 5/24 ≈ 20.8% ≥ 20% still fires; hotspots: churn values {billing 6, engine 8, legacy 5, settings 2} → 75th pct 7.5, still flags only engine.)

- [ ] **Step 5: Commit**

```bash
git add tests/conftest.py tests/test_fixture.py tests/test_ingest.py
git commit -m "test: plant secret-in-history and release tags in fixture repo"
```

---

### Task 2: Ingest — parents, tags, patch text

**Files:**
- Modify: `src/acquirescope/ingest.py`
- Modify: `tests/test_ingest.py` (append tests)

**Interfaces:**
- Consumes: fixture (Task 1).
- Produces: `Commit` gains `parents: list[str]` (defaults to `[]`; empty for root commits, ≥2 entries for merges); `RepoIngest.tags() -> list[tuple[str, datetime]]` (tag name + commit author date, oldest first); `RepoIngest.full_patch_text() -> str` (cached `git log -p` where each commit record starts with `\x1eCOMMIT <sha>`). Tasks 3–4 call ONLY these plus the Phase 1 surface.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_ingest.py`:

```python
def test_commit_parents_populated(fixture_repo):
    commits = RepoIngest(Path(fixture_repo)).commits()
    # newest-first: the root commit is last and has no parents
    assert commits[-1].parents == []
    assert all(len(c.parents) == 1 for c in commits[:-1])  # linear history


def test_tags_with_dates_oldest_first(fixture_repo):
    tags = RepoIngest(Path(fixture_repo)).tags()
    assert [name for name, _ in tags] == ["v0.1.0", "v0.2.0"]
    assert tags[0][1] < tags[1][1]
    assert tags[0][1].year == 2026


def test_full_patch_text_contains_planted_secret(fixture_repo):
    ingest = RepoIngest(Path(fixture_repo))
    text = ingest.full_patch_text()
    assert "AKIAIOSFODNN7EXAMPLE" in text
    assert "\x1eCOMMIT " in text
    assert ingest.full_patch_text() is text  # cached
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_ingest.py -v`
Expected: the three new tests FAIL (`parents` attribute missing / `tags` method missing).

- [ ] **Step 3: Write the implementation**

In `src/acquirescope/ingest.py`:

1. Change the imports and log format:

```python
from dataclasses import dataclass, field

# %x1e = record separator between commits, %x1f = field separator within header
_LOG_FORMAT = "%x1e%H%x1f%ae%x1f%an%x1f%aI%x1f%P"
```

2. Add `parents` to `Commit`:

```python
@dataclass
class Commit:
    sha: str
    author_email: str
    author_name: str
    authored_at: datetime
    changes: list[FileChange]
    parents: list[str] = field(default_factory=list)
```

3. In `commits()`, the header now has five fields:

```python
            sha, email, name, iso_date, parents_raw = lines[0].split("\x1f")
```

and construct the commit with parents:

```python
            parsed.append(Commit(
                sha=sha, author_email=email, author_name=name,
                authored_at=datetime.fromisoformat(iso_date), changes=changes,
                parents=parents_raw.split(),
            ))
```

4. Initialize a patch cache in `__init__` (below `self._commits`):

```python
        self._patch_text: str | None = None
```

5. Add the two methods to `RepoIngest`:

```python
    def tags(self) -> list[tuple[str, datetime]]:
        """Tags with their commit author dates, oldest first."""
        names = [t for t in self._git("tag", "--list").splitlines() if t.strip()]
        result = []
        for name in names:
            iso = self._git("log", "-1", "--format=%aI", name).strip()
            result.append((name, datetime.fromisoformat(iso)))
        result.sort(key=lambda pair: pair[1])
        return result

    def full_patch_text(self) -> str:
        """git log -p output; each commit record starts with \\x1eCOMMIT <sha>. Cached."""
        if self._patch_text is None:
            self._patch_text = self._git("log", "-p", "--format=%x1eCOMMIT %H")
        return self._patch_text
```

- [ ] **Step 4: Run the ingest tests to verify they pass**

Run: `pytest tests/test_ingest.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add src/acquirescope/ingest.py tests/test_ingest.py
git commit -m "feat: ingest commit parents, tags, and full patch text"
```

---

### Task 3: Security posture module

**Files:**
- Create: `src/acquirescope/modules/security.py`
- Test: `tests/test_security.py`

**Interfaces:**
- Consumes: `RepoIngest.commits()/list_files()/full_patch_text()/repo_path` (Tasks 1–2), models.
- Produces: `analyze(ingest: RepoIngest) -> ModuleResult` with `module="security"`. Findings: CRITICAL per distinct secret in history; MEDIUM "No security policy"; LOW "No dependency update automation"; MEDIUM "Stale dependency manifest" (>180 days); HIGH per vulnerable package when osv-scanner is on PATH, else INFO "Vulnerability scan not available". Metrics: `secret_count` (int), `has_security_policy` (bool), `manifest_age_days` (int, -1 if no manifest), `vulnerability_count` (int, -1 when scan unavailable).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_security.py`:

```python
import json
import subprocess
from pathlib import Path

from acquirescope.ingest import RepoIngest
from acquirescope.models import Severity
from acquirescope.modules import security


def _no_osv(monkeypatch):
    monkeypatch.setattr(security.shutil, "which", lambda _: None)


def test_planted_secret_found_in_history(fixture_repo, monkeypatch):
    _no_osv(monkeypatch)
    result = security.analyze(RepoIngest(Path(fixture_repo)))
    assert result.status == "ok"
    secrets = [f for f in result.findings if f.severity == Severity.CRITICAL]
    assert len(secrets) == 1
    assert "AWS access key" in secrets[0].title
    assert secrets[0].evidence[0].path == "config/settings.py"
    assert result.metrics["secret_count"] == 1


def test_secret_removed_from_head_still_flagged(fixture_repo, monkeypatch):
    _no_osv(monkeypatch)
    assert "AKIA" not in (Path(fixture_repo) / "config" / "settings.py").read_text(encoding="utf-8")
    result = security.analyze(RepoIngest(Path(fixture_repo)))
    assert result.metrics["secret_count"] == 1


def test_missing_policy_and_automation_flagged(fixture_repo, monkeypatch):
    _no_osv(monkeypatch)
    result = security.analyze(RepoIngest(Path(fixture_repo)))
    titles = [f.title for f in result.findings]
    assert "No security policy" in titles
    assert "No dependency update automation" in titles
    assert result.metrics["has_security_policy"] is False
    assert result.metrics["manifest_age_days"] == 17  # requirements 05-02 vs latest 05-19


def test_osv_absent_yields_honest_scope_note(fixture_repo, monkeypatch):
    _no_osv(monkeypatch)
    result = security.analyze(RepoIngest(Path(fixture_repo)))
    notes = [f for f in result.findings if f.title == "Vulnerability scan not available"]
    assert len(notes) == 1
    assert notes[0].severity == Severity.INFO
    assert result.metrics["vulnerability_count"] == -1


def test_osv_present_parses_canned_results(fixture_repo, monkeypatch):
    monkeypatch.setattr(security.shutil, "which", lambda _: "osv-scanner")
    canned = json.dumps({"results": [{"packages": [
        {"package": {"name": "mysqlclient"}, "vulnerabilities": [{}, {}]},
    ]}]})
    fake = subprocess.CompletedProcess(args=[], returncode=1, stdout=canned, stderr="")
    monkeypatch.setattr(security.subprocess, "run", lambda *a, **k: fake)
    result = security.analyze(RepoIngest(Path(fixture_repo)))
    vulns = [f for f in result.findings if f.title.startswith("Vulnerable dependency")]
    assert len(vulns) == 1
    assert "mysqlclient" in vulns[0].title
    assert vulns[0].severity == Severity.HIGH
    assert result.metrics["vulnerability_count"] == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_security.py -v`
Expected: FAIL with `ImportError: cannot import name 'security'`

- [ ] **Step 3: Write the implementation**

Create `src/acquirescope/modules/security.py`:

```python
from __future__ import annotations

import json
import re
import shutil
import subprocess

from acquirescope.ingest import RepoIngest
from acquirescope.models import Evidence, Finding, ModuleResult, Severity

MODULE = "security"
MANIFEST_STALE_DAYS = 180
OSV_TIMEOUT_SECONDS = 300

# label -> pattern; scanned over ADDED lines of the full history patch.
_SECRET_PATTERNS = [
    ("AWS access key", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("Private key block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("Hardcoded credential assignment",
     re.compile(r"(?i)\b(?:api_key|secret_key|token)\s*=\s*['\"][A-Za-z0-9/+_\-]{16,}['\"]")),
]


def _is_manifest(path: str) -> bool:
    name = path.rsplit("/", 1)[-1]
    if name.startswith("requirements") and name.endswith(".txt"):
        return True
    return name in ("pyproject.toml", "package.json", "go.mod", "Cargo.toml", "Gemfile")


def _secrets_in_history(ingest: RepoIngest) -> list[Finding]:
    findings: list[Finding] = []
    seen: set[str] = set()
    for record in ingest.full_patch_text().split("\x1e"):
        if not record.startswith("COMMIT "):
            continue
        header, _, body = record.partition("\n")
        sha = header.removeprefix("COMMIT ").strip()
        current_path: str | None = None
        for line in body.splitlines():
            if line.startswith("+++ b/"):
                current_path = line[6:]
                continue
            if not line.startswith("+") or line.startswith("+++"):
                continue
            for label, pattern in _SECRET_PATTERNS:
                for match in pattern.finditer(line):
                    secret = match.group(0)
                    if secret in seen:
                        continue
                    seen.add(secret)
                    findings.append(Finding(
                        module=MODULE,
                        title=f"Secret in git history: {label}",
                        severity=Severity.CRITICAL,
                        summary=(
                            f"A {label.lower()} was committed to git history and remains "
                            f"recoverable from it even if removed from the working tree. "
                            f"It must be rotated and the history scrubbed."
                        ),
                        evidence=[Evidence(
                            description=f"introduced in commit {sha[:12]}",
                            path=current_path, detail=label,
                        )],
                    ))
    return findings


def _vulnerability_findings(ingest: RepoIngest) -> tuple[list[Finding], int]:
    unavailable = Finding(
        module=MODULE,
        title="Vulnerability scan not available",
        severity=Severity.INFO,
        summary=(
            "osv-scanner is not installed (or failed); dependency vulnerabilities were "
            "not assessed. Install osv-scanner to enable this check."
        ),
        evidence=[Evidence(description="osv-scanner not usable on PATH")],
    )
    if shutil.which("osv-scanner") is None:
        return [unavailable], -1
    try:
        # osv-scanner exits non-zero when vulnerabilities are found; don't check=True.
        result = subprocess.run(
            ["osv-scanner", "--format", "json", "-r", str(ingest.repo_path)],
            capture_output=True, text=True, encoding="utf-8", timeout=OSV_TIMEOUT_SECONDS,
        )
        data = json.loads(result.stdout)
    except Exception:
        return [unavailable], -1

    per_package: dict[str, int] = {}
    for res in data.get("results", []):
        for pkg in res.get("packages", []):
            name = pkg.get("package", {}).get("name", "unknown")
            per_package[name] = per_package.get(name, 0) + len(pkg.get("vulnerabilities", []))

    findings = [
        Finding(
            module=MODULE,
            title=f"Vulnerable dependency: {name}",
            severity=Severity.HIGH,
            summary=f"osv-scanner reports {count} known vulnerability advisories for '{name}'.",
            evidence=[Evidence(description=f"{count} OSV advisories", detail=name)],
        )
        for name, count in sorted(per_package.items())
    ]
    return findings, sum(per_package.values())


def analyze(ingest: RepoIngest) -> ModuleResult:
    files = ingest.list_files()
    fileset = set(files)
    findings: list[Finding] = []

    secret_findings = _secrets_in_history(ingest)
    findings.extend(secret_findings)

    has_policy = any(f.upper() == "SECURITY.MD" for f in files)
    if not has_policy:
        findings.append(Finding(
            module=MODULE, title="No security policy", severity=Severity.MEDIUM,
            summary="No SECURITY.md at the repository root; there is no documented vulnerability disclosure process.",
            evidence=[Evidence(description="expected SECURITY.md at repo root")],
        ))

    if not ({".github/dependabot.yml", "renovate.json"} & fileset):
        findings.append(Finding(
            module=MODULE, title="No dependency update automation", severity=Severity.LOW,
            summary="Neither dependabot nor renovate is configured; dependency updates rely on manual effort.",
            evidence=[Evidence(description="no .github/dependabot.yml or renovate.json")],
        ))

    commits = ingest.commits()
    latest = max(c.authored_at for c in commits)
    manifest_dates = [
        c.authored_at for c in commits for ch in c.changes if _is_manifest(ch.path)
    ]
    manifest_age_days = -1
    if manifest_dates:
        manifest_age_days = (latest - max(manifest_dates)).days
        if manifest_age_days > MANIFEST_STALE_DAYS:
            findings.append(Finding(
                module=MODULE, title="Stale dependency manifest", severity=Severity.MEDIUM,
                summary=(
                    f"No dependency manifest has been touched for {manifest_age_days} days; "
                    f"dependencies are likely unpatched."
                ),
                evidence=[Evidence(description=f"last manifest change {manifest_age_days} days before latest commit")],
            ))

    vuln_findings, vulnerability_count = _vulnerability_findings(ingest)
    findings.extend(vuln_findings)

    return ModuleResult(
        module=MODULE, status="ok", findings=findings,
        metrics={
            "secret_count": len(secret_findings),
            "has_security_policy": has_policy,
            "manifest_age_days": manifest_age_days,
            "vulnerability_count": vulnerability_count,
        },
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_security.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add src/acquirescope/modules/security.py tests/test_security.py
git commit -m "feat: add security posture module with secrets-history scan"
```

---

### Task 4: Delivery health module

**Files:**
- Create: `src/acquirescope/modules/delivery.py`
- Test: `tests/test_delivery.py`

**Interfaces:**
- Consumes: `RepoIngest.commits()/list_files()/tags()` (Task 2), `Commit.parents`, models.
- Produces: `analyze(ingest: RepoIngest) -> ModuleResult` with `module="delivery"`. Findings: MEDIUM "No tagged releases" / "Stale release cadence" (>180 days); MEDIUM "Contribution activity declining" (recent 90d < 50% of prior 90d, prior ≥ 10); LOW "Little evidence of PR-based review flow" (merge share < 10%, ≥ 20 commits); MEDIUM "No CI configuration detected". Metrics: `release_count` (int), `days_since_last_release` (int, -1 no tags), `merge_commit_share` (float), `commits_last_90d` (int), `ci_configured` (bool).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_delivery.py`:

```python
from datetime import datetime, timedelta, timezone
from pathlib import Path

from acquirescope.ingest import Commit, RepoIngest
from acquirescope.models import Severity
from acquirescope.modules import delivery


class _StubIngest:
    """Minimal ingest stand-in for unit-level tests without git."""

    def __init__(self, commits, files=None, tags=None):
        self._commits, self._files, self._tags = commits, files or [], tags or []

    def commits(self):
        return self._commits

    def list_files(self):
        return self._files

    def tags(self):
        return self._tags


def _commit(days_ago: int, base=datetime(2026, 6, 1, tzinfo=timezone.utc)) -> Commit:
    return Commit(sha="x", author_email="a@example.com", author_name="a",
                  authored_at=base - timedelta(days=days_ago), changes=[])


def test_release_metrics_from_fixture_tags(fixture_repo):
    result = delivery.analyze(RepoIngest(Path(fixture_repo)))
    assert result.status == "ok"
    assert result.metrics["release_count"] == 2
    assert result.metrics["days_since_last_release"] == 2  # v0.2.0 05-17 vs latest 05-19
    assert not any(f.title == "No tagged releases" for f in result.findings)


def test_review_proxy_fires_on_merge_free_history(fixture_repo):
    result = delivery.analyze(RepoIngest(Path(fixture_repo)))
    proxies = [f for f in result.findings if "review" in f.title.lower()]
    assert len(proxies) == 1
    assert proxies[0].severity == Severity.LOW
    assert result.metrics["merge_commit_share"] == 0.0


def test_ci_absence_flagged(fixture_repo):
    result = delivery.analyze(RepoIngest(Path(fixture_repo)))
    assert any(f.title == "No CI configuration detected" for f in result.findings)
    assert result.metrics["ci_configured"] is False


def test_declining_activity_trend_unit():
    commits = [_commit(d) for d in (0, 10)] + [_commit(100 + d) for d in range(12)]
    result = delivery.analyze(_StubIngest(commits, files=[".github/workflows/ci.yml"]))
    declining = [f for f in result.findings if "declining" in f.title.lower()]
    assert len(declining) == 1
    assert result.metrics["commits_last_90d"] == 2
    assert result.metrics["ci_configured"] is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_delivery.py -v`
Expected: FAIL with `ImportError: cannot import name 'delivery'`

- [ ] **Step 3: Write the implementation**

Create `src/acquirescope/modules/delivery.py`:

```python
from __future__ import annotations

from acquirescope.ingest import RepoIngest
from acquirescope.models import Evidence, Finding, ModuleResult, Severity

MODULE = "delivery"
STALE_RELEASE_DAYS = 180
TREND_WINDOW_DAYS = 90
TREND_MIN_PRIOR_COMMITS = 10
MERGE_SHARE_MIN = 0.10
MIN_COMMITS_FOR_REVIEW_PROXY = 20
CI_FILES = (".gitlab-ci.yml", "Jenkinsfile", ".circleci/config.yml")


def analyze(ingest: RepoIngest) -> ModuleResult:
    commits = ingest.commits()
    files = ingest.list_files()
    findings: list[Finding] = []
    latest = max(c.authored_at for c in commits)

    # 1. Release cadence from tags.
    tags = ingest.tags()
    days_since_last_release = -1
    if not tags:
        findings.append(Finding(
            module=MODULE, title="No tagged releases", severity=Severity.MEDIUM,
            summary="The repository has no git tags; release cadence cannot be established from history.",
            evidence=[Evidence(description="git tag list is empty")],
        ))
    else:
        last_name, last_date = tags[-1]
        days_since_last_release = (latest - last_date).days
        if days_since_last_release > STALE_RELEASE_DAYS:
            findings.append(Finding(
                module=MODULE, title="Stale release cadence", severity=Severity.MEDIUM,
                summary=(
                    f"The newest tag {last_name} predates the latest commit by "
                    f"{days_since_last_release} days; releases appear to have stalled."
                ),
                evidence=[Evidence(description=f"tag {last_name} dated {last_date.date()}", detail=last_name)],
            ))

    # 2. Contribution activity trend (windows anchored at the latest commit).
    recent = [c for c in commits if 0 <= (latest - c.authored_at).days < TREND_WINDOW_DAYS]
    prior = [c for c in commits
             if TREND_WINDOW_DAYS <= (latest - c.authored_at).days < 2 * TREND_WINDOW_DAYS]
    if len(prior) >= TREND_MIN_PRIOR_COMMITS and len(recent) < 0.5 * len(prior):
        findings.append(Finding(
            module=MODULE, title="Contribution activity declining", severity=Severity.MEDIUM,
            summary=(
                f"{len(recent)} commits in the last {TREND_WINDOW_DAYS} days vs {len(prior)} in "
                f"the prior window — activity has more than halved."
            ),
            evidence=[Evidence(description=f"{len(recent)} recent vs {len(prior)} prior commits")],
        ))

    # 3. Review-flow proxy: merge-commit share. Honest label — squash flows hide review.
    merges = [c for c in commits if len(c.parents) >= 2]
    merge_share = len(merges) / len(commits)
    if len(commits) >= MIN_COMMITS_FOR_REVIEW_PROXY and merge_share < MERGE_SHARE_MIN:
        findings.append(Finding(
            module=MODULE,
            title="Little evidence of PR-based review flow",
            severity=Severity.LOW,
            summary=(
                f"Only {merge_share:.0%} of commits are merge commits (proxy metric; "
                f"squash/rebase merge strategies can hide a real review process)."
            ),
            evidence=[Evidence(description=f"{len(merges)}/{len(commits)} merge commits")],
        ))

    # 4. CI maturity: presence of any known CI configuration.
    fileset = set(files)
    ci_configured = (
        any(f.startswith(".github/workflows/") for f in files)
        or any(ci in fileset for ci in CI_FILES)
    )
    if not ci_configured:
        findings.append(Finding(
            module=MODULE, title="No CI configuration detected", severity=Severity.MEDIUM,
            summary="No GitHub Actions, GitLab CI, Jenkins, or CircleCI configuration is tracked in the repository.",
            evidence=[Evidence(description="no known CI config paths present")],
        ))

    return ModuleResult(
        module=MODULE, status="ok", findings=findings,
        metrics={
            "release_count": len(tags),
            "days_since_last_release": days_since_last_release,
            "merge_commit_share": round(merge_share, 3),
            "commits_last_90d": len(recent),
            "ci_configured": ci_configured,
        },
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_delivery.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add src/acquirescope/modules/delivery.py tests/test_delivery.py
git commit -m "feat: add delivery health module with local git proxies"
```

---

### Task 5: Price the security remediation line item

**Files:**
- Modify: `src/acquirescope/bridge/assumptions.py`
- Modify: `examples/assumptions.example.toml`
- Modify: `src/acquirescope/bridge/adjustments.py`
- Modify: `tests/test_assumptions.py`, `tests/test_adjustments.py`, `tests/test_valuation.py`, `tests/test_excel.py`

**Interfaces:**
- Consumes: `ModuleResult` for module `"security"` (Task 3 shape), `Severity`.
- Produces: `Assumptions` gains `security_fix_cost_usd: float` (required `[costs]` key); the 5th `Adjustment` ("Security remediation") is priced `count(CRITICAL|HIGH security findings) × security_fix_cost_usd`, band ±50%, evidence = finding titles; `_not_assessed` only when the security module failed or is absent.

- [ ] **Step 1: Write/adjust the failing tests**

In `tests/test_assumptions.py::test_loads_example_file`, add:

```python
    assert a.security_fix_cost_usd == 50_000
```

In `tests/test_adjustments.py`:

1. Add to the `_assumptions()` factory (after `integration_cost_usd=500_000,`):

```python
        security_fix_cost_usd=50_000,
```

2. Append to the list returned by `_results()`:

```python
        ModuleResult(
            module="security", status="ok",
            findings=[Finding("security", "Secret in git history: AWS access key",
                              Severity.CRITICAL, "s")],
            metrics={"secret_count": 1},
        ),
```

3. Replace `test_security_always_not_assessed_in_phase2` with:

```python
def test_security_priced_from_critical_and_high_findings():
    security = price_adjustments(_results(), _assumptions(), 10_000_000)[4]
    assert security.assessed
    assert security.mid == 50_000          # 1 CRITICAL finding x 50k
    assert security.low == 25_000
    assert security.high == 75_000
    assert "AWS access key" in "; ".join(security.evidence)


def test_security_not_assessed_when_module_missing():
    results = [r for r in _results() if r.module != "security"]
    security = price_adjustments(results, _assumptions(), 10_000_000)[4]
    assert not security.assessed
    assert security.mid == 0
    assert "Not assessed" in security.basis
```

In `tests/test_valuation.py` and `tests/test_excel.py`, add the same line to each `_assumptions()` factory (after `integration_cost_usd=500_000,`):

```python
        security_fix_cost_usd=50_000,
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_adjustments.py tests/test_assumptions.py -v`
Expected: FAIL with `TypeError: Assumptions.__init__() got an unexpected keyword argument 'security_fix_cost_usd'` and/or missing-key errors.

- [ ] **Step 3: Write the implementation**

1. `src/acquirescope/bridge/assumptions.py` — add to the `Assumptions` dataclass (after `integration_cost_usd: float`):

```python
    security_fix_cost_usd: float
```

and to the `load_assumptions` return (after `integration_cost_usd=...`):

```python
        security_fix_cost_usd=_positive(costs, "costs", "security_fix_cost_usd"),
```

2. `examples/assumptions.example.toml` — add to `[costs]` (after `integration_cost_usd`):

```toml
security_fix_cost_usd = 50_000    # per critical/high security finding
```

3. `src/acquirescope/bridge/adjustments.py` — replace the security block (`# 5. Security remediation — module ships in Phase 3.` and the line after it) with:

```python
    # 5. Security remediation — priced from CRITICAL/HIGH security findings.
    sec = by_module.get("security")
    if sec is None:
        adjustments.append(_not_assessed("Security remediation", "security module failed or missing"))
    else:
        serious = [f for f in sec.findings if f.severity in (Severity.CRITICAL, Severity.HIGH)]
        low, mid, high = _banded(len(serious) * assumptions.security_fix_cost_usd)
        adjustments.append(Adjustment(
            "Security remediation", low, mid, high,
            f"{len(serious)} critical/high security finding(s) x "
            f"${assumptions.security_fix_cost_usd:,.0f} remediation cost, +/-50%",
            [f.title for f in serious],
        ))
```

- [ ] **Step 4: Run the affected tests**

Run: `pytest tests/test_adjustments.py tests/test_assumptions.py tests/test_valuation.py tests/test_excel.py tests/test_cli.py -v`
Expected: ALL pass. (The Phase 2 e2e still shows security "NOT ASSESSED" because the `MODULES` registry doesn't include security until Task 7.)

- [ ] **Step 5: Commit**

```bash
git add src/acquirescope/bridge/assumptions.py examples/assumptions.example.toml src/acquirescope/bridge/adjustments.py tests/test_assumptions.py tests/test_adjustments.py tests/test_valuation.py tests/test_excel.py
git commit -m "feat: price security remediation from security module findings"
```

---

### Task 6: Narrative layer with citation verification

**Files:**
- Create: `src/acquirescope/narrative.py`
- Test: `tests/test_narrative.py`

**Interfaces:**
- Consumes: `ModuleResult`/`Finding` (Phase 1 models). No I/O, no SDK.
- Produces (from `acquirescope.narrative`): `build_prompt(repo_name: str, results: list[ModuleResult]) -> tuple[str, set[str]]` (evidence IDs `E1..En` assigned per finding in module order); `verify_citations(text: str, valid_ids: set[str]) -> tuple[str, int]` (cleaned text, removed count); `generate_narrative(repo_name: str, results: list[ModuleResult], complete: Callable[[str], str]) -> str` (appends `"(N unverifiable citation(s) removed.)"` when any were stripped; exceptions from `complete` propagate).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_narrative.py`:

```python
from acquirescope.models import Finding, ModuleResult, Severity
from acquirescope.narrative import build_prompt, generate_narrative, verify_citations


def _results() -> list[ModuleResult]:
    return [
        ModuleResult(
            module="bus_factor", status="ok",
            findings=[Finding("bus_factor", "Single point of failure: payments/",
                              Severity.HIGH, "one owner")],
            metrics={"top_author_share": 0.4},
        ),
        ModuleResult(
            module="licenses", status="ok",
            findings=[Finding("licenses", "Copyleft dependency: mysqlclient",
                              Severity.HIGH, "GPL dep")],
        ),
        ModuleResult(module="hotspots", status="failed", error="boom"),
    ]


def test_prompt_carries_findings_and_stable_ids():
    prompt, valid_ids = build_prompt("target", _results())
    assert valid_ids == {"E1", "E2"}
    assert "[E1]" in prompt and "[E2]" in prompt
    assert "Single point of failure: payments/" in prompt
    assert "not assessed: boom" in prompt
    assert "target" in prompt


def test_verify_strips_unknown_citations():
    cleaned, removed = verify_citations("Fine [E1] but bogus [E9].", {"E1"})
    assert cleaned == "Fine [E1] but bogus ."
    assert removed == 1


def test_generate_appends_removal_note():
    text = generate_narrative("t", _results(), lambda p: "Risk [E1]. Fabricated [E42].")
    assert "[E1]" in text
    assert "[E42]" not in text
    assert text.endswith("(1 unverifiable citation(s) removed.)")


def test_generate_clean_when_all_citations_valid():
    text = generate_narrative("t", _results(), lambda p: "Risk [E1] and [E2].")
    assert "unverifiable" not in text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_narrative.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'acquirescope.narrative'`

- [ ] **Step 3: Write the implementation**

Create `src/acquirescope/narrative.py`:

```python
from __future__ import annotations

import re
from typing import Callable

from acquirescope.models import ModuleResult

_CITATION = re.compile(r"\[E(\d+)\]")

_INSTRUCTIONS = (
    "You are writing the executive summary of a technical due-diligence report "
    "for a potential acquirer. Using ONLY the findings below, write 200-400 words "
    "of narrative for a non-technical deal team. Every factual claim MUST cite "
    "its finding id in square brackets, e.g. [E1]. Do not make any claim without "
    "a citation and do not invent findings."
)


def build_prompt(repo_name: str, results: list[ModuleResult]) -> tuple[str, set[str]]:
    lines = [_INSTRUCTIONS, "", f"Target repository: {repo_name}", ""]
    valid_ids: set[str] = set()
    counter = 0
    for result in results:
        lines.append(f"Module {result.module} ({result.status}):")
        if result.status != "ok":
            lines.append(f"  not assessed: {result.error}")
        for finding in result.findings:
            counter += 1
            eid = f"E{counter}"
            valid_ids.add(eid)
            lines.append(f"  [{eid}] ({finding.severity.value}) {finding.title}: {finding.summary}")
        if result.metrics:
            lines.append(f"  metrics: {result.metrics}")
        lines.append("")
    return "\n".join(lines), valid_ids


def verify_citations(text: str, valid_ids: set[str]) -> tuple[str, int]:
    """Strip [En] citations that don't correspond to real findings."""
    removed = 0

    def _check(match: re.Match) -> str:
        nonlocal removed
        if f"E{match.group(1)}" in valid_ids:
            return match.group(0)
        removed += 1
        return ""

    return _CITATION.sub(_check, text), removed


def generate_narrative(
    repo_name: str, results: list[ModuleResult], complete: Callable[[str], str]
) -> str:
    prompt, valid_ids = build_prompt(repo_name, results)
    text, removed = verify_citations(complete(prompt), valid_ids)
    if removed:
        text += f"\n\n({removed} unverifiable citation(s) removed.)"
    return text
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_narrative.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add src/acquirescope/narrative.py tests/test_narrative.py
git commit -m "feat: add citation-verified LLM narrative layer (engine-independent)"
```

---

### Task 7: CLI wiring — new modules in registry, --narrative flag, report section

**Files:**
- Modify: `pyproject.toml`
- Modify: `src/acquirescope/report.py`
- Modify: `src/acquirescope/cli.py`
- Modify: `tests/test_report.py` (append one test), `tests/test_cli.py` (append three tests)

**Interfaces:**
- Consumes: everything above.
- Produces: `render_markdown(repo_name, results, narrative: str | None = None)`; `MODULES` includes `("security", security.analyze)` and `("delivery", delivery.analyze)` after hotspots; `analyze --narrative` flag; `_narrative_unavailable_reason() -> str | None` and `_anthropic_complete(prompt: str) -> str` in `acquirescope.cli` (monkeypatch points for tests); optional dependency group `llm = ["anthropic>=0.40"]`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_report.py`:

```python
def test_narrative_section_rendered_when_provided():
    md = render_markdown("target-repo", _sample_results(), narrative="Summary claim [E1].")
    assert "## Executive narrative (LLM-generated, citation-verified)" in md
    assert "Summary claim [E1]." in md
    assert md.index("Executive narrative") < md.index("## Module:")
```

Append to `tests/test_cli.py`:

```python
def test_narrative_unavailable_exits_1(fixture_repo, tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "_narrative_unavailable_reason", lambda: "no key")
    out = tmp_path / "r.md"
    result = runner.invoke(cli.app, ["analyze", str(fixture_repo), "--output", str(out), "--narrative"])
    assert result.exit_code == 1
    assert not out.exists()


def test_narrative_section_written_with_fake_completer(fixture_repo, tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "_narrative_unavailable_reason", lambda: None)
    monkeypatch.setattr(cli, "_anthropic_complete",
                        lambda prompt: "Key-person risk dominates [E1]. Fake [E99].")
    out = tmp_path / "r.md"
    result = runner.invoke(cli.app, ["analyze", str(fixture_repo), "--output", str(out), "--narrative"])
    assert result.exit_code == 0
    md = out.read_text(encoding="utf-8")
    assert "## Executive narrative" in md
    assert "[E1]" in md
    assert "[E99]" not in md
    assert "1 unverifiable citation(s) removed" in md


def test_narrative_api_failure_degrades_to_plain_report(fixture_repo, tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "_narrative_unavailable_reason", lambda: None)

    def boom(prompt):
        raise RuntimeError("api down")

    monkeypatch.setattr(cli, "_anthropic_complete", boom)
    out = tmp_path / "r.md"
    result = runner.invoke(cli.app, ["analyze", str(fixture_repo), "--output", str(out), "--narrative"])
    assert result.exit_code == 0
    md = out.read_text(encoding="utf-8")
    assert "Executive narrative" not in md
    assert "# Technical Due Diligence Report:" in md
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_report.py tests/test_cli.py -v`
Expected: new tests FAIL (`render_markdown` has no `narrative` kwarg; `cli` has no `_narrative_unavailable_reason`; `--narrative` unknown option → exit 2).

- [ ] **Step 3: Write the implementation**

1. `pyproject.toml` — extend optional dependencies:

```toml
[project.optional-dependencies]
dev = ["pytest>=8.0"]
llm = ["anthropic>=0.40"]
```

2. `src/acquirescope/report.py` — change the signature and title block:

```python
def render_markdown(
    repo_name: str, results: list[ModuleResult], narrative: str | None = None
) -> str:
    lines = [f"# Technical Due Diligence Report: {repo_name}", ""]
    if narrative:
        lines.append("## Executive narrative (LLM-generated, citation-verified)")
        lines.append("")
        lines.append(narrative)
        lines.append("")
```

(the rest of the function is unchanged).

3. `src/acquirescope/cli.py`:

Add imports (`os` to stdlib imports; extend the modules import; add narrative):

```python
import os
```

```python
from acquirescope.modules import bus_factor, delivery, hotspots, licenses, security
from acquirescope.narrative import generate_narrative
```

Extend the registry:

```python
MODULES: list[tuple[str, Callable[[RepoIngest], ModuleResult]]] = [
    ("bus_factor", bus_factor.analyze),
    ("licenses", licenses.analyze),
    ("hotspots", hotspots.analyze),
    ("security", security.analyze),
    ("delivery", delivery.analyze),
]
```

Add the two helpers (above `analyze`):

```python
def _narrative_unavailable_reason() -> str | None:
    try:
        import anthropic  # noqa: F401
    except ImportError:
        return "--narrative requires the anthropic package: pip install acquirescope[llm]"
    if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
        return "--narrative requires ANTHROPIC_API_KEY (or ANTHROPIC_AUTH_TOKEN) in the environment"
    return None


def _anthropic_complete(prompt: str) -> str:
    import anthropic

    client = anthropic.Anthropic()
    response = client.messages.create(
        model="claude-opus-4-8",
        max_tokens=2048,
        messages=[{"role": "user", "content": prompt}],
    )
    return "".join(block.text for block in response.content if block.type == "text")
```

Replace the `analyze` command with:

```python
@app.command()
def analyze(
    repo_path: Path = typer.Argument(..., exists=True, file_okay=False, help="Path to a local git repository"),
    output: Path = typer.Option(Path("dd-report.md"), "--output", "-o", help="Report output path"),
    narrative: bool = typer.Option(False, "--narrative", help="Prepend an LLM-generated, citation-verified executive narrative (requires acquirescope[llm] and an Anthropic API key)"),
) -> None:
    """Run all due-diligence modules against REPO_PATH and write a markdown report."""
    if narrative:
        reason = _narrative_unavailable_reason()
        if reason:
            typer.echo(reason, err=True)
            raise typer.Exit(code=1)
    results = run_modules(RepoIngest(repo_path))
    narrative_text: str | None = None
    if narrative:
        try:
            narrative_text = generate_narrative(repo_path.name, results, _anthropic_complete)
        except Exception as exc:  # report must never be lost to a narrative failure
            typer.echo(f"Warning: narrative generation failed ({exc}); writing report without it.", err=True)
    output.write_text(render_markdown(repo_path.name, results, narrative_text), encoding="utf-8")
    typer.echo(f"Report written to {output}")
```

- [ ] **Step 4: Run the report and CLI tests**

Run: `pytest tests/test_report.py tests/test_cli.py -v`
Expected: report tests pass (4); CLI narrative tests pass; **the Phase 2 e2e model test now FAILS** on `adj["E6"].value == "NOT ASSESSED"` because the security module is registered and prices. That failure is expected and fixed by Task 8 — do not fix it here.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml src/acquirescope/report.py src/acquirescope/cli.py tests/test_report.py tests/test_cli.py
git commit -m "feat: register security/delivery modules and add --narrative flag"
```

---

### Task 8: End-to-end regression gate for Phase 3

**Files:**
- Modify: `tests/test_cli.py` (update the two e2e tests)

**Interfaces:**
- Consumes: the full five-module pipeline and the fixture's planted issues.
- Produces: the Phase 3 regression gate — planted secret detected and priced; new modules render in report and workbook honestly.

- [ ] **Step 1: Update the report e2e test**

In `test_all_planted_issues_detected_end_to_end`, add a `monkeypatch` parameter and these lines. First line of the test body (keeps the run hermetic if osv-scanner happens to be installed):

```python
    monkeypatch.setattr("acquirescope.modules.security.shutil.which", lambda _: None)
```

Append at the end of the test:

```python
    # Phase 3 planted issue: committed-then-removed AWS key
    assert "Secret in git history: AWS access key" in md
    # New modules render, honest about proxies and scope
    assert "## Module: security" in md
    assert "## Module: delivery" in md
    assert "Vulnerability scan not available" in md
    assert "No CI configuration detected" in md
```

- [ ] **Step 2: Update the model e2e test**

In `test_planted_issues_priced_in_model_end_to_end`, add a `monkeypatch` parameter and the same `shutil.which` line at the top. Then replace:

```python
    assert adj["E6"].value == "NOT ASSESSED"          # security honest about scope
```

with:

```python
    assert adj["E6"].value == "yes"                   # security now assessed
    assert adj["C6"].value == 50_000                  # 1 CRITICAL secret x 50k
    assert "AWS access key" in adj["G6"].value        # evidence reaches the workbook
```

- [ ] **Step 3: Run the full suite**

Run: `pytest -v`
Expected: ALL tests pass (65 total: Phase 1+2's 44 grown by +3 ingest, +5 security, +4 delivery, +1 adjustments net, +4 narrative, +1 report, +3 CLI). If only an e2e fails, its module's unit tests localize the regression.

- [ ] **Step 4: Commit**

```bash
git add tests/test_cli.py
git commit -m "test: extend e2e gates to security, delivery, and priced secret findings"
```

---

## Self-review notes

- **Spec coverage:** ingest extensions ✓ (Task 2), security module with all five signals ✓ (Task 3; osv optional + monkeypatched tests), delivery module with four proxy signals ✓ (Task 4), security pricing replacing the Phase 2 stub ✓ (Task 5, including the deliberate temporary e2e break noted in Task 7 and fixed in Task 8), narrative build/verify/generate with injected completer ✓ (Task 6), CLI `--narrative` + registry + report section + optional dep ✓ (Task 7), fixture 24 commits + tags + secret ✓ (Task 1), e2e gates ✓ (Task 8).
- **Type consistency:** `Commit.parents: list[str]` default `[]` (Task 2) matches Task 4's stub omitting it; `tags() -> list[tuple[str, datetime]]` consumed as `tags[-1]` unpack; `security_fix_cost_usd` spelled identically in dataclass, loader, TOML, and all four test factories; `render_markdown(..., narrative=None)` keyword matches CLI call; monkeypatch targets `cli._narrative_unavailable_reason` / `cli._anthropic_complete` match the module-level names defined in Task 7.
- **Ordering hazards made explicit:** Task 5 keeps the Phase 2 e2e green (registry unchanged); Task 7 knowingly breaks one e2e assertion and says so; Task 8 restores it. Executors following task order see no surprise failures.
- **Anthropic usage:** `claude-opus-4-8`, `max_tokens=2048`, plain `messages.create`, lazy import — per current API guidance; no downgrade to a cheaper tier on the user's behalf.
