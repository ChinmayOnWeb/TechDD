# Repo-Health Pricing Panel Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the `panel/` subsystem that turns local git clones + free public financial data into a firm-quarter panel CSV and runs the H1 (pricing) / H2 (predictive) regressions from the 2026-07-06 panel-study spec.

**Architecture:** A new `src/git_due_diligence/panel/` subpackage with six units — universe config loader, point-in-time repo metric extractor, EDGAR XBRL fundamentals fetcher, Stooq price fetcher, panel assembler, regression runner — wired into the existing Typer CLI as a `gitdd panel` command group. Fetchers are cache-first with injectable fetch callables so the panel is rebuildable offline and tests never touch the network.

**Tech Stack:** Python 3.12+, Typer, pandas, statsmodels, numpy (via pandas), requests; existing `git_due_diligence.ingest`/`modules` code reused as a library.

**Spec:** `docs/superpowers/specs/2026-07-06-repo-health-pricing-panel-study-design.md`

## Global Constraints

- Python `>=3.12`; run everything with the project venv: `.venv/Scripts/python.exe -m pytest` (Windows).
- New dependencies go ONLY under a new optional extra `panel = ["pandas>=2.0", "statsmodels>=0.14", "requests>=2.31"]`. The base install (`pip install -e .`) must keep working: no module that `git_due_diligence.cli` imports at module level may import pandas/statsmodels/requests at module level — heavy imports live inside functions.
- No network access in tests. Every fetcher takes a `fetch: Callable[[str], str]` parameter defaulting to the real HTTP implementation; tests inject fakes. Fetchers write raw payloads to a cache directory and read the cache on subsequent calls.
- SEC fair-access policy requires a descriptive User-Agent: `"git-due-diligence research contact: chinmay.patil1@gmail.com"` on every EDGAR request.
- Bot authors are excluded from all repo metrics via the existing `git_due_diligence.modules.bus_factor._is_bot_author`.
- All repo metrics are trailing-window: window = `(quarter_end - 365 days, quarter_end]`.
- CLI naming: `gitdd panel build`, `gitdd panel regress`. Package path: `src/git_due_diligence/panel/`.
- Existing modules (`bus_factor`, `security`, etc.) must not change behavior; the panel code imports their private helpers (`_bus_factor`, `_gini`, `_is_bot_author`, `_SECRET_PATTERNS`, `_looks_like_test_path`, `_is_template_binding_mention`, `_is_private_key_prose_mention`) read-only.
- Commit after every task with the message given in the task's final step. All 119 existing tests must stay green throughout.

## File Structure

```
src/git_due_diligence/panel/
    __init__.py          (empty)
    universe.py          Firm dataclass, load_universe(), fiscal_quarter_ends()
    history.py           QuarterMetrics dataclass, quarterly_metrics()
    edgar.py             QuarterFundamentals dataclass, fetch_fundamentals()
    prices.py            quarter_end_prices()
    assemble.py          build_panel() -> pandas DataFrame, health indices
    regress.py           run_regressions() -> dict of fitted results
    cli.py               panel_app (Typer sub-app): build, regress
panel/universe/
    gitlab.toml          first real firm config
tests/
    test_panel_universe.py
    test_panel_history.py
    test_panel_edgar.py
    test_panel_prices.py
    test_panel_assemble.py
    test_panel_regress.py
    test_panel_cli.py
pyproject.toml           add [panel] extra
src/git_due_diligence/cli.py   mount panel_app
README.md                add panel-study section
```

---

### Task 1: Universe config — `Firm`, `load_universe`, `fiscal_quarter_ends`

**Files:**
- Modify: `pyproject.toml` (add `panel` extra)
- Create: `src/git_due_diligence/panel/__init__.py` (empty)
- Create: `src/git_due_diligence/panel/universe.py`
- Create: `panel/universe/gitlab.toml`
- Test: `tests/test_panel_universe.py`

**Interfaces:**
- Consumes: nothing from other tasks (stdlib `tomllib`, `calendar`, `datetime` only).
- Produces:
  - `@dataclass(frozen=True) Firm(slug: str, name: str, ticker: str, cik: str, repos: tuple[str, ...], fiscal_year_end_month: int, listed_from: date, listed_to: date | None = None, notes: str = "")` — `cik` is the zero-padded 10-digit EDGAR CIK string.
  - `load_universe(directory: Path) -> list[Firm]` — one TOML per firm, sorted by filename; raises `ValueError` on missing keys or invalid month.
  - `fiscal_quarter_ends(fye_month: int, start: date, end: date) -> list[date]` — ascending fiscal quarter-end dates within `[start, end]`.

- [ ] **Step 1: Add the `panel` extra and install**

In `pyproject.toml`, change the optional-dependencies section to:

```toml
[project.optional-dependencies]
dev = ["pytest>=8.0"]
llm = ["anthropic>=0.40"]
panel = ["pandas>=2.0", "statsmodels>=0.14", "requests>=2.31"]
```

Run: `.venv/Scripts/python.exe -m pip install -e ".[dev,panel]"`
Expected: installs pandas, statsmodels, requests without error.

- [ ] **Step 2: Write the failing tests**

Create `tests/test_panel_universe.py`:

```python
from datetime import date
from pathlib import Path

import pytest

from git_due_diligence.panel.universe import Firm, fiscal_quarter_ends, load_universe

GITLAB_TOML = """\
name = "GitLab Inc."
slug = "gitlab"
ticker = "GTLB"
cik = "0001653482"
repos = ["https://github.com/gitlabhq/gitlabhq.git"]
fiscal_year_end_month = 1
listed_from = 2021-10-14
notes = "IPO 2021-10-14; CE/EE monorepo merge 2019 predates listing."
"""


def _write(tmp_path: Path, name: str, body: str) -> Path:
    (tmp_path / name).write_text(body, encoding="utf-8")
    return tmp_path


def test_load_universe_parses_firm(tmp_path):
    firms = load_universe(_write(tmp_path, "gitlab.toml", GITLAB_TOML))
    assert len(firms) == 1
    firm = firms[0]
    assert firm == Firm(
        slug="gitlab", name="GitLab Inc.", ticker="GTLB", cik="0001653482",
        repos=("https://github.com/gitlabhq/gitlabhq.git",),
        fiscal_year_end_month=1, listed_from=date(2021, 10, 14),
        listed_to=None,
        notes="IPO 2021-10-14; CE/EE monorepo merge 2019 predates listing.",
    )


def test_cik_zero_padded_from_int(tmp_path):
    body = GITLAB_TOML.replace('cik = "0001653482"', "cik = 1653482")
    firms = load_universe(_write(tmp_path, "gitlab.toml", body))
    assert firms[0].cik == "0001653482"


def test_missing_key_raises(tmp_path):
    body = GITLAB_TOML.replace('ticker = "GTLB"\n', "")
    with pytest.raises(ValueError, match="ticker"):
        load_universe(_write(tmp_path, "gitlab.toml", body))


def test_bad_month_raises(tmp_path):
    body = GITLAB_TOML.replace("fiscal_year_end_month = 1", "fiscal_year_end_month = 13")
    with pytest.raises(ValueError, match="fiscal_year_end_month"):
        load_universe(_write(tmp_path, "gitlab.toml", body))


def test_fiscal_quarter_ends_january_fye():
    ends = fiscal_quarter_ends(1, date(2021, 10, 14), date(2022, 8, 1))
    assert ends == [date(2021, 10, 31), date(2022, 1, 31), date(2022, 4, 30), date(2022, 7, 31)]


def test_fiscal_quarter_ends_december_fye_handles_leap():
    ends = fiscal_quarter_ends(12, date(2024, 1, 1), date(2024, 12, 31))
    assert ends == [date(2024, 3, 31), date(2024, 6, 30), date(2024, 9, 30), date(2024, 12, 31)]
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_panel_universe.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'git_due_diligence.panel'`

- [ ] **Step 4: Implement**

Create empty `src/git_due_diligence/panel/__init__.py`, then `src/git_due_diligence/panel/universe.py`:

```python
from __future__ import annotations

import calendar
import tomllib
from dataclasses import dataclass
from datetime import date
from pathlib import Path

_REQUIRED_KEYS = ("name", "slug", "ticker", "cik", "repos", "fiscal_year_end_month", "listed_from")


@dataclass(frozen=True)
class Firm:
    slug: str
    name: str
    ticker: str
    cik: str                    # zero-padded 10-digit EDGAR CIK
    repos: tuple[str, ...]
    fiscal_year_end_month: int  # 1-12; GitLab's Jan-31 fiscal year end -> 1
    listed_from: date
    listed_to: date | None = None
    notes: str = ""


def load_universe(directory: Path) -> list[Firm]:
    firms: list[Firm] = []
    for path in sorted(directory.glob("*.toml")):
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
        missing = [k for k in _REQUIRED_KEYS if k not in raw]
        if missing:
            raise ValueError(f"{path.name}: missing required keys: {', '.join(missing)}")
        month = raw["fiscal_year_end_month"]
        if not (isinstance(month, int) and 1 <= month <= 12):
            raise ValueError(f"{path.name}: fiscal_year_end_month must be 1-12, got {month!r}")
        firms.append(Firm(
            slug=raw["slug"], name=raw["name"], ticker=raw["ticker"],
            cik=str(raw["cik"]).zfill(10),
            repos=tuple(raw["repos"]), fiscal_year_end_month=month,
            listed_from=raw["listed_from"], listed_to=raw.get("listed_to"),
            notes=raw.get("notes", ""),
        ))
    return firms


def fiscal_quarter_ends(fye_month: int, start: date, end: date) -> list[date]:
    """Fiscal quarter-end dates (last day of each quarter-end month implied by
    the fiscal-year-end month) falling within [start, end], ascending."""
    months = sorted({(fye_month - 1 + 3 * k) % 12 + 1 for k in range(4)})
    ends: list[date] = []
    for year in range(start.year, end.year + 1):
        for month in months:
            d = date(year, month, calendar.monthrange(year, month)[1])
            if start <= d <= end:
                ends.append(d)
    return ends
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_panel_universe.py -v`
Expected: 6 PASS

- [ ] **Step 6: Add the first real firm config**

Create `panel/universe/gitlab.toml` with exactly the `GITLAB_TOML` content from Step 2 (same keys, same values). Before committing, verify the CIK: open `https://www.sec.gov/cgi-bin/browse-edgar?company=gitlab&type=10-K&action=getcompany` and confirm GitLab Inc.'s CIK is 1653482; if it differs, fix the TOML and the test constant.

- [ ] **Step 7: Run the full suite and commit**

Run: `.venv/Scripts/python.exe -m pytest -q`
Expected: 125 passed (119 existing + 6 new)

```bash
git add pyproject.toml src/git_due_diligence/panel/ panel/universe/gitlab.toml tests/test_panel_universe.py
git commit -m "feat(panel): universe config loader and fiscal quarter calendar"
```

---

### Task 2: Point-in-time repo metrics — `history.py`

**Files:**
- Create: `src/git_due_diligence/panel/history.py`
- Test: `tests/test_panel_history.py`

**Interfaces:**
- Consumes: `git_due_diligence.ingest.RepoIngest` (`.commits() -> list[Commit]` where `Commit` has `sha, author_email, authored_at: datetime, changes: list[FileChange], parents: list[str]`; `.tags() -> list[tuple[str, datetime]]`; `.iter_patch_records()` yielding `"COMMIT <sha>\n<diff>"` strings); `git_due_diligence.modules.bus_factor._bus_factor(Counter) -> int`, `._gini(list[int]) -> float`, `._is_bot_author(str) -> bool`; `git_due_diligence.modules.security._SECRET_PATTERNS`, `._looks_like_test_path`, `._is_template_binding_mention`, `._is_private_key_prose_mention`.
- Produces:
  - `@dataclass QuarterMetrics(quarter_end: date, active_contributors: int, top_author_share: float, contributor_gini: float, bus_factor_50: int, churn_gini: float, release_cadence: int, merge_share: float, commit_volume: int, secret_incidence: float)`
  - `quarterly_metrics(repo_path: Path, quarter_ends: list[date]) -> list[QuarterMetrics]` — one row per input date, in input order; empty windows produce an all-zero row.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_panel_history.py`:

```python
import os
import subprocess
from datetime import date
from pathlib import Path

import pytest

from git_due_diligence.panel.history import quarterly_metrics

QUARTER_ENDS = [date(2024, 9, 30), date(2025, 3, 31), date(2025, 6, 30)]


def _git(repo: Path, *args: str, date_str: str | None = None) -> None:
    env = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull}
    if date_str:
        env["GIT_AUTHOR_DATE"] = date_str
        env["GIT_COMMITTER_DATE"] = date_str
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, env=env)


def _commit(repo: Path, path: str, content: str, author: str, date_str: str) -> None:
    file_path = repo / path
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(content, encoding="utf-8")
    _git(repo, "add", path)
    _git(repo, "-c", f"user.name={author.split('@')[0]}", "-c", f"user.email={author}",
         "commit", "-m", f"update {path}", date_str=date_str)


@pytest.fixture(scope="module")
def panel_repo(tmp_path_factory) -> Path:
    """Planted timeline (all human commits unless noted):
    Q ending 2025-03-31 window: alice x3 (Jan/Feb/Mar 2025).
    Q ending 2025-06-30 window: those 3 + bob x3 (incl. one high-confidence
    secret) + carol's merge commit = 7; a bot commit (excluded); tag v1.0
    on the merge (in-window release)."""
    repo = tmp_path_factory.mktemp("panel-repo")
    subprocess.run(["git", "init", "-b", "main", str(repo)], check=True, capture_output=True)
    alice, bob, carol = "alice@example.com", "bob@example.com", "carol@example.com"
    bot = "dependabot[bot]@users.noreply.github.com"

    _commit(repo, "a.py", "A = 1\n", alice, "2025-01-15T10:00:00")
    _commit(repo, "a.py", "A = 2\n", alice, "2025-02-15T10:00:00")
    _commit(repo, "a.py", "A = 3\n", alice, "2025-03-15T10:00:00")
    _commit(repo, "b.py", "B = 1\n", bob, "2025-05-10T10:00:00")
    _commit(repo, "deps.txt", "dep==1\n", bot, "2025-05-11T10:00:00")
    _commit(repo, "config/settings.py", 'KEY = "AKIAIOSFODNN7EXAMPLE"\n', bob,
            "2025-05-12T10:00:00")
    _git(repo, "checkout", "-b", "feature")
    _commit(repo, "feature.py", "F = 1\n", bob, "2025-06-10T10:00:00")
    _git(repo, "checkout", "main")
    _git(repo, "-c", "user.name=carol", "-c", f"user.email={carol}",
         "merge", "--no-ff", "-m", "merge feature", "feature",
         date_str="2025-06-15T10:00:00")
    _git(repo, "tag", "v1.0")
    return repo


def test_one_row_per_quarter_end_in_order(panel_repo):
    rows = quarterly_metrics(panel_repo, QUARTER_ENDS)
    assert [r.quarter_end for r in rows] == QUARTER_ENDS


def test_empty_window_yields_zero_row(panel_repo):
    row = quarterly_metrics(panel_repo, QUARTER_ENDS)[0]   # 2024-09-30: repo not born yet
    assert row.commit_volume == 0
    assert row.active_contributors == 0
    assert row.top_author_share == 0.0
    assert row.secret_incidence == 0.0


def test_trailing_window_contributor_metrics(panel_repo):
    rows = quarterly_metrics(panel_repo, QUARTER_ENDS)
    q1 = rows[1]   # window (2024-03-31, 2025-03-31]: alice's 3 commits only
    assert q1.commit_volume == 3
    assert q1.active_contributors == 1
    assert q1.top_author_share == 1.0
    assert q1.bus_factor_50 == 1

    q2 = rows[2]   # window (2024-06-30, 2025-06-30]: all 7 human commits
    assert q2.commit_volume == 7            # bot commit excluded
    assert q2.active_contributors == 3
    assert q2.top_author_share == round(3 / 7, 4)
    assert q2.bus_factor_50 == 2            # alice(3)+bob(3) cover >= 50% of 7


def test_merge_release_and_secret_metrics(panel_repo):
    rows = quarterly_metrics(panel_repo, QUARTER_ENDS)
    q2 = rows[2]
    assert q2.merge_share == round(1 / 7, 4)
    assert q2.release_cadence == 1                       # v1.0 tagged in-window
    assert q2.secret_incidence == round(1000 * 1 / 7, 4)  # 1 high-confidence secret / 7 commits

    q1 = rows[1]
    assert q1.release_cadence == 0
    assert q1.secret_incidence == 0.0
    assert q1.merge_share == 0.0


def test_gini_metrics_bounded(panel_repo):
    q2 = quarterly_metrics(panel_repo, QUARTER_ENDS)[2]
    assert 0.0 <= q2.contributor_gini <= 1.0
    assert 0.0 <= q2.churn_gini <= 1.0
    assert q2.churn_gini > 0.0    # churn is concentrated in a.py
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_panel_history.py -v`
Expected: FAIL — `ImportError: cannot import name 'quarterly_metrics'` (or ModuleNotFoundError for `history`)

- [ ] **Step 3: Implement**

Create `src/git_due_diligence/panel/history.py`:

```python
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

from git_due_diligence.ingest import RepoIngest
from git_due_diligence.modules.bus_factor import _bus_factor, _gini, _is_bot_author
from git_due_diligence.modules.security import (
    _SECRET_PATTERNS,
    _is_private_key_prose_mention,
    _is_template_binding_mention,
    _looks_like_test_path,
)

TRAILING_DAYS = 365   # trailing-4-quarter window, approximated as one year


@dataclass
class QuarterMetrics:
    quarter_end: date
    active_contributors: int
    top_author_share: float
    contributor_gini: float
    bus_factor_50: int
    churn_gini: float
    release_cadence: int
    merge_share: float
    commit_volume: int
    secret_incidence: float   # high-confidence secrets introduced per 1,000 commits


def _zero_row(quarter_end: date) -> QuarterMetrics:
    return QuarterMetrics(quarter_end, 0, 0.0, 0.0, 0, 0.0, 0, 0.0, 0, 0.0)


def _high_confidence_secret_shas(ingest: RepoIngest) -> Counter:
    """sha -> count of newly introduced high-confidence secrets; one pass over
    the streamed full-history patch, mirroring the security module's
    confidence scoring (test paths, prose mentions, template bindings are
    low-confidence and not counted)."""
    counts: Counter = Counter()
    seen: set[str] = set()
    for record in ingest.iter_patch_records():
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
                    low_confidence = (
                        (label == "Private key block"
                         and _is_private_key_prose_mention(line, match))
                        or (label == "Hardcoded credential assignment"
                            and _is_template_binding_mention(line, match))
                        or _looks_like_test_path(current_path)
                    )
                    if not low_confidence:
                        counts[sha] += 1
    return counts


def quarterly_metrics(repo_path: Path, quarter_ends: list[date]) -> list[QuarterMetrics]:
    """One QuarterMetrics per requested fiscal quarter-end, in input order.
    Each row is computed over the trailing window (quarter_end - 365d,
    quarter_end], from a single ingest pass over the repo."""
    ingest = RepoIngest(repo_path)
    commits = [c for c in ingest.commits() if not _is_bot_author(c.author_email)]
    tag_dates = [dt.date() for _, dt in ingest.tags()]
    secrets_by_sha = _high_confidence_secret_shas(ingest)

    rows: list[QuarterMetrics] = []
    for q_end in quarter_ends:
        start = q_end - timedelta(days=TRAILING_DAYS)
        window = [c for c in commits if start < c.authored_at.date() <= q_end]
        if not window:
            rows.append(_zero_row(q_end))
            continue
        n = len(window)
        author_counts = Counter(c.author_email for c in window)
        churn: Counter = Counter()
        for c in window:
            for change in c.changes:
                churn[change.path] += change.added + change.deleted
        merges = sum(1 for c in window if len(c.parents) > 1)
        releases = sum(1 for d in tag_dates if start < d <= q_end)
        secrets = sum(secrets_by_sha.get(c.sha, 0) for c in window)
        rows.append(QuarterMetrics(
            quarter_end=q_end,
            active_contributors=len(author_counts),
            top_author_share=round(author_counts.most_common(1)[0][1] / n, 4),
            contributor_gini=round(_gini(list(author_counts.values())), 4),
            bus_factor_50=_bus_factor(author_counts),
            churn_gini=round(_gini(list(churn.values())), 4),
            release_cadence=releases,
            merge_share=round(merges / n, 4),
            commit_volume=n,
            secret_incidence=round(1000.0 * secrets / n, 4),
        ))
    return rows
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_panel_history.py -v`
Expected: 5 PASS

- [ ] **Step 5: Commit**

```bash
git add src/git_due_diligence/panel/history.py tests/test_panel_history.py
git commit -m "feat(panel): point-in-time trailing-window repo metrics"
```

---

### Task 3: EDGAR fundamentals — `edgar.py`

**Files:**
- Create: `src/git_due_diligence/panel/edgar.py`
- Test: `tests/test_panel_edgar.py`

**Interfaces:**
- Consumes: nothing from other tasks (stdlib + lazy `requests`).
- Produces:
  - `@dataclass QuarterFundamentals(quarter_end: date, revenue: float, operating_income: float | None, cash: float | None, debt: float | None, shares_outstanding: float | None)`
  - `fetch_fundamentals(cik: str, cache_dir: Path, fetch: Callable[[str], str] = _default_fetch) -> list[QuarterFundamentals]` — sorted ascending by `quarter_end`; `cik` is the zero-padded string from `Firm.cik`.
  - Cache file name (Task 7's offline CLI test depends on it): `cache_dir / f"edgar_CIK{cik}.json"`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_panel_edgar.py`:

```python
import json
from datetime import date

from git_due_diligence.panel.edgar import fetch_fundamentals


def _entry(start: str | None, end: str, val: float, form: str = "10-Q") -> dict:
    e = {"end": end, "val": val, "form": form}
    if start:
        e["start"] = start
    return e


def _canned_facts() -> dict:
    return {
        "cik": 1,
        "facts": {
            "dei": {"EntityCommonStockSharesOutstanding": {"units": {"shares": [
                _entry(None, "2024-05-05", 100_000_000.0),
                _entry(None, "2024-08-02", 101_000_000.0),
                _entry(None, "2024-11-04", 102_000_000.0),
                _entry(None, "2025-03-20", 103_000_000.0, form="10-K"),
            ]}}},
            "us-gaap": {
                "RevenueFromContractWithCustomerExcludingAssessedTax": {"units": {"USD": [
                    _entry("2024-02-01", "2024-04-30", 100.0),
                    _entry("2024-05-01", "2024-07-31", 110.0),
                    _entry("2024-08-01", "2024-10-31", 120.0),
                    _entry("2024-02-01", "2025-01-31", 460.0, form="10-K"),  # FY -> Q4 = 130
                ]}},
                "OperatingIncomeLoss": {"units": {"USD": [
                    _entry("2024-02-01", "2024-04-30", 10.0),
                ]}},
                "CashAndCashEquivalentsAtCarryingValue": {"units": {"USD": [
                    _entry(None, "2024-04-30", 50.0),
                    _entry(None, "2024-07-31", 55.0),
                ]}},
            },
        },
    }


def _fake_fetch(calls: list[str]):
    def fetch(url: str) -> str:
        calls.append(url)
        return json.dumps(_canned_facts())
    return fetch


def test_quarterly_revenue_and_derived_q4(tmp_path):
    rows = fetch_fundamentals("0000000001", tmp_path, fetch=_fake_fetch([]))
    assert [r.quarter_end for r in rows] == [
        date(2024, 4, 30), date(2024, 7, 31), date(2024, 10, 31), date(2025, 1, 31),
    ]
    assert [r.revenue for r in rows] == [100.0, 110.0, 120.0, 130.0]


def test_instants_matched_within_tolerance(tmp_path):
    rows = fetch_fundamentals("0000000001", tmp_path, fetch=_fake_fetch([]))
    q1 = rows[0]
    assert q1.cash == 50.0
    assert q1.shares_outstanding == 100_000_000.0   # instant dated 5 days after quarter end
    assert q1.operating_income == 10.0
    assert q1.debt is None                          # no debt tag reported at all
    q4 = rows[3]
    assert q4.shares_outstanding == 103_000_000.0   # 48 days after, inside 70-day tolerance
    assert q4.cash is None                          # nearest cash instant is ~6 months away
    assert q4.operating_income is None              # only Q1 op income reported


def test_companyfacts_cached_after_first_fetch(tmp_path):
    calls: list[str] = []
    fetch = _fake_fetch(calls)
    fetch_fundamentals("0000000001", tmp_path, fetch=fetch)
    fetch_fundamentals("0000000001", tmp_path, fetch=fetch)
    assert len(calls) == 1
    assert calls[0] == "https://data.sec.gov/api/xbrl/companyfacts/CIK0000000001.json"
    assert (tmp_path / "edgar_CIK0000000001.json").exists()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_panel_edgar.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'git_due_diligence.panel.edgar'`

- [ ] **Step 3: Implement**

Create `src/git_due_diligence/panel/edgar.py`:

```python
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Callable

EDGAR_COMPANYFACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
# SEC fair-access policy requires a descriptive User-Agent with contact info.
USER_AGENT = "git-due-diligence research contact: chinmay.patil1@gmail.com"

# First tag with any usable data wins. Firms that switch tags mid-history are
# a known v1 limitation, documented in the spec's threats table.
_REVENUE_TAGS = [
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "Revenues",
    "SalesRevenueNet",
]
_OPERATING_INCOME_TAGS = ["OperatingIncomeLoss"]
_CASH_TAGS = ["CashAndCashEquivalentsAtCarryingValue"]
_DEBT_TAGS = ["LongTermDebt", "LongTermDebtNoncurrent", "ConvertibleDebtNoncurrent"]
_QUARTER_DAYS = (80, 100)     # duration facts this long are one fiscal quarter
_ANNUAL_DAYS = (350, 380)
_INSTANT_TOLERANCE_DAYS = 70  # balance-sheet/cover instants vs quarter end


@dataclass
class QuarterFundamentals:
    quarter_end: date
    revenue: float
    operating_income: float | None
    cash: float | None
    debt: float | None
    shares_outstanding: float | None


def _default_fetch(url: str) -> str:
    import requests

    response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=60)
    response.raise_for_status()
    return response.text


def fetch_companyfacts(cik: str, cache_dir: Path,
                       fetch: Callable[[str], str] = _default_fetch) -> dict:
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = cache_dir / f"edgar_CIK{cik}.json"
    if not cache_file.exists():
        cache_file.write_text(fetch(EDGAR_COMPANYFACTS_URL.format(cik=cik)), encoding="utf-8")
    return json.loads(cache_file.read_text(encoding="utf-8"))


def _duration_series(section: dict, tags: list[str],
                     day_range: tuple[int, int]) -> dict[date, float]:
    lo, hi = day_range
    for tag in tags:
        entries = section.get(tag, {}).get("units", {}).get("USD", [])
        series: dict[date, float] = {}
        for entry in entries:
            if "start" not in entry or entry.get("form") not in ("10-Q", "10-K"):
                continue
            start = date.fromisoformat(entry["start"])
            end = date.fromisoformat(entry["end"])
            if lo <= (end - start).days <= hi:
                series[end] = float(entry["val"])  # later (amended) filings overwrite
        if series:
            return series
    return {}


def _derive_q4(quarterly: dict[date, float], annual: dict[date, float]) -> dict[date, float]:
    """10-Ks report full-year durations; Q4 = FY minus the three quarterly
    values whose period-ends fall inside that fiscal year."""
    merged = dict(quarterly)
    for fy_end, fy_val in annual.items():
        if fy_end in merged:
            continue
        inside = [v for end, v in quarterly.items() if 0 < (fy_end - end).days < 290]
        if len(inside) == 3:
            merged[fy_end] = fy_val - sum(inside)
    return merged


def _instant_series(section: dict, tags: list[str], unit: str) -> dict[date, float]:
    for tag in tags:
        entries = section.get(tag, {}).get("units", {}).get(unit, [])
        series = {
            date.fromisoformat(e["end"]): float(e["val"])
            for e in entries if "start" not in e
        }
        if series:
            return series
    return {}


def _nearest(series: dict[date, float], target: date) -> float | None:
    if not series:
        return None
    best = min(series, key=lambda d: abs((d - target).days))
    if abs((best - target).days) > _INSTANT_TOLERANCE_DAYS:
        return None
    return series[best]


def fetch_fundamentals(cik: str, cache_dir: Path,
                       fetch: Callable[[str], str] = _default_fetch) -> list[QuarterFundamentals]:
    facts = fetch_companyfacts(cik, cache_dir, fetch)
    gaap = facts.get("facts", {}).get("us-gaap", {})
    dei = facts.get("facts", {}).get("dei", {})

    revenue = _derive_q4(
        _duration_series(gaap, _REVENUE_TAGS, _QUARTER_DAYS),
        _duration_series(gaap, _REVENUE_TAGS, _ANNUAL_DAYS),
    )
    operating_income = _derive_q4(
        _duration_series(gaap, _OPERATING_INCOME_TAGS, _QUARTER_DAYS),
        _duration_series(gaap, _OPERATING_INCOME_TAGS, _ANNUAL_DAYS),
    )
    cash = _instant_series(gaap, _CASH_TAGS, "USD")
    debt = _instant_series(gaap, _DEBT_TAGS, "USD")
    shares = _instant_series(dei, ["EntityCommonStockSharesOutstanding"], "shares")

    return [
        QuarterFundamentals(
            quarter_end=q_end,
            revenue=rev,
            operating_income=operating_income.get(q_end),
            cash=_nearest(cash, q_end),
            debt=_nearest(debt, q_end),
            shares_outstanding=_nearest(shares, q_end),
        )
        for q_end, rev in sorted(revenue.items())
    ]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_panel_edgar.py -v`
Expected: 3 PASS

- [ ] **Step 5: Commit**

```bash
git add src/git_due_diligence/panel/edgar.py tests/test_panel_edgar.py
git commit -m "feat(panel): EDGAR XBRL quarterly fundamentals fetcher, cache-first"
```

---

### Task 4: Quarter-end prices — `prices.py`

**Files:**
- Create: `src/git_due_diligence/panel/prices.py`
- Test: `tests/test_panel_prices.py`

**Interfaces:**
- Consumes: nothing from other tasks (stdlib + lazy `requests`).
- Produces:
  - `quarter_end_prices(ticker: str, dates: list[date], cache_dir: Path, fetch: Callable[[str], str] = _default_fetch) -> dict[date, float | None]` — last daily close on or before each date; `None` when no close within 14 calendar days (pre-IPO, delisted, symbol gap).
  - Cache file name (Task 7 depends on it): `cache_dir / f"stooq_{ticker.lower()}.us.csv"`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_panel_prices.py`:

```python
from datetime import date

from git_due_diligence.panel.prices import quarter_end_prices

CANNED_CSV = """Date,Open,High,Low,Close,Volume
2024-04-29,50,51,49,50.5,1000
2024-04-30,51,52,50,51.25,1200
2024-07-30,55,56,54,55.5,900
"""


def test_last_close_on_or_before_each_date(tmp_path):
    calls: list[str] = []

    def fake_fetch(url: str) -> str:
        calls.append(url)
        return CANNED_CSV

    prices = quarter_end_prices(
        "GTLB", [date(2024, 4, 30), date(2024, 7, 31), date(2024, 10, 31)],
        tmp_path, fetch=fake_fetch,
    )
    assert prices[date(2024, 4, 30)] == 51.25   # exact-date close
    assert prices[date(2024, 7, 31)] == 55.5    # last close, one day earlier
    assert prices[date(2024, 10, 31)] is None   # nothing within 14 days
    assert calls == ["https://stooq.com/q/d/l/?s=gtlb.us&i=d"]


def test_prices_cached_after_first_fetch(tmp_path):
    calls: list[str] = []

    def fake_fetch(url: str) -> str:
        calls.append(url)
        return CANNED_CSV

    quarter_end_prices("GTLB", [date(2024, 4, 30)], tmp_path, fetch=fake_fetch)
    quarter_end_prices("GTLB", [date(2024, 4, 30)], tmp_path, fetch=fake_fetch)
    assert len(calls) == 1
    assert (tmp_path / "stooq_gtlb.us.csv").exists()


def test_malformed_rows_skipped(tmp_path):
    body = CANNED_CSV + "No Data\n,,,,,\n"
    prices = quarter_end_prices("GTLB", [date(2024, 7, 31)], tmp_path,
                                fetch=lambda url: body)
    assert prices[date(2024, 7, 31)] == 55.5
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_panel_prices.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'git_due_diligence.panel.prices'`

- [ ] **Step 3: Implement**

Create `src/git_due_diligence/panel/prices.py`:

```python
from __future__ import annotations

from bisect import bisect_right
from datetime import date
from pathlib import Path
from typing import Callable

STOOQ_URL = "https://stooq.com/q/d/l/?s={symbol}&i=d"
USER_AGENT = "git-due-diligence research contact: chinmay.patil1@gmail.com"
_MAX_STALENESS_DAYS = 14   # beyond this, treat the quarter as unpriced


def _default_fetch(url: str) -> str:
    import requests

    response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=60)
    response.raise_for_status()
    return response.text


def _load_closes(ticker: str, cache_dir: Path,
                 fetch: Callable[[str], str]) -> list[tuple[date, float]]:
    symbol = f"{ticker.lower()}.us"
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = cache_dir / f"stooq_{symbol}.csv"
    if not cache_file.exists():
        cache_file.write_text(fetch(STOOQ_URL.format(symbol=symbol)), encoding="utf-8")
    closes: list[tuple[date, float]] = []
    for line in cache_file.read_text(encoding="utf-8").splitlines()[1:]:
        parts = line.split(",")
        if len(parts) < 5:
            continue
        try:
            closes.append((date.fromisoformat(parts[0]), float(parts[4])))
        except ValueError:
            continue
    closes.sort()
    return closes


def quarter_end_prices(ticker: str, dates: list[date], cache_dir: Path,
                       fetch: Callable[[str], str] = _default_fetch) -> dict[date, float | None]:
    """Last close on or before each date; None when no close within 14 days
    (pre-IPO, post-delisting, or a data gap)."""
    closes = _load_closes(ticker, cache_dir, fetch)
    close_dates = [d for d, _ in closes]
    out: dict[date, float | None] = {}
    for target in dates:
        idx = bisect_right(close_dates, target) - 1
        if idx < 0 or (target - close_dates[idx]).days > _MAX_STALENESS_DAYS:
            out[target] = None
        else:
            out[target] = closes[idx][1]
    return out
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_panel_prices.py -v`
Expected: 3 PASS

- [ ] **Step 5: Commit**

```bash
git add src/git_due_diligence/panel/prices.py tests/test_panel_prices.py
git commit -m "feat(panel): Stooq quarter-end price fetcher, cache-first"
```

---

### Task 5: Panel assembler — `assemble.py`

**Files:**
- Create: `src/git_due_diligence/panel/assemble.py`
- Test: `tests/test_panel_assemble.py`

**Interfaces:**
- Consumes: `Firm` (Task 1), `QuarterMetrics` (Task 2), `QuarterFundamentals` (Task 3); pandas/numpy (lazy, inside the function).
- Produces:
  - `build_panel(firms: list[Firm], metrics_by_slug: dict[str, list[QuarterMetrics]], fundamentals_by_slug: dict[str, list[QuarterFundamentals]], prices_by_slug: dict[str, dict[date, float | None]]) -> pandas.DataFrame`
  - Columns: `firm, ticker, quarter_end` (ISO string), `revenue_ltm, growth_yoy, op_margin_ltm, market_cap, net_debt, ev, ev_rev, log_ev_rev, log_rev`, the nine `QuarterMetrics` fields, `repo_health_index_z, repo_health_index_pca`.
  - Row rule: a firm-quarter appears only if all 4 LTM fundamentals quarters matched, a price and shares exist, `revenue_ltm > 0`, and `ev > 0`. `growth_yoy` is NaN until 8 matched quarters exist.
  - `INDEX_COMPONENTS: list[tuple[str, int]]` — metric name and healthy-direction sign; `merge_share` and `commit_volume` are deliberately excluded (workflow/scale controls, not health).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_panel_assemble.py`:

```python
import math
from datetime import date

from git_due_diligence.panel.assemble import build_panel
from git_due_diligence.panel.edgar import QuarterFundamentals
from git_due_diligence.panel.history import QuarterMetrics
from git_due_diligence.panel.universe import Firm

QUARTERS = [date(2023, 3, 31), date(2023, 6, 30), date(2023, 9, 30), date(2023, 12, 31),
            date(2024, 3, 31), date(2024, 6, 30), date(2024, 9, 30), date(2024, 12, 31)]


def _inputs():
    firm = Firm(slug="acme", name="Acme", ticker="ACME", cik="0000000001",
                repos=("https://example.com/acme.git",),
                fiscal_year_end_month=12, listed_from=date(2023, 1, 1))
    metrics = [QuarterMetrics(
        quarter_end=q, active_contributors=5 + i, top_author_share=0.5 - 0.02 * i,
        contributor_gini=0.6, bus_factor_50=2 + (i % 3), churn_gini=0.7,
        release_cadence=2, merge_share=0.3, commit_volume=100 + 10 * i,
        secret_incidence=0.0,
    ) for i, q in enumerate(QUARTERS)]
    fundamentals = [QuarterFundamentals(
        quarter_end=q, revenue=100.0 + 5 * i, operating_income=10.0,
        cash=50.0, debt=None, shares_outstanding=1_000_000.0,
    ) for i, q in enumerate(QUARTERS)]
    prices = {q: 20.0 for q in QUARTERS}
    return firm, metrics, fundamentals, prices


def _panel():
    firm, metrics, fundamentals, prices = _inputs()
    return build_panel([firm], {"acme": metrics}, {"acme": fundamentals}, {"acme": prices})


def test_rows_require_full_ltm_window():
    panel = _panel()
    # first 3 quarters lack a full trailing-4Q fundamentals window
    assert list(panel["quarter_end"]) == [q.isoformat() for q in QUARTERS[3:]]


def test_valuation_columns():
    first = _panel().iloc[0]                    # quarter index 3
    assert first["revenue_ltm"] == 100 + 105 + 110 + 115
    assert first["market_cap"] == 20.0 * 1_000_000
    assert first["net_debt"] == -50.0           # no debt, 50 cash
    assert first["ev"] == 20.0 * 1_000_000 - 50.0
    assert abs(first["ev_rev"] - first["ev"] / first["revenue_ltm"]) < 1e-9
    assert abs(first["op_margin_ltm"] - 40.0 / 430.0) < 1e-9


def test_growth_needs_eight_matched_quarters():
    panel = _panel()
    assert math.isnan(panel.iloc[0]["growth_yoy"])
    last = panel.iloc[-1]                       # index 7: LTM 510 vs prior LTM 430
    assert abs(last["growth_yoy"] - (510 / 430 - 1)) < 1e-9


def test_missing_price_drops_row():
    firm, metrics, fundamentals, prices = _inputs()
    prices[QUARTERS[4]] = None
    panel = build_panel([firm], {"acme": metrics}, {"acme": fundamentals}, {"acme": prices})
    assert QUARTERS[4].isoformat() not in list(panel["quarter_end"])


def test_health_indices_present_and_standardized():
    panel = _panel()
    assert abs(panel["repo_health_index_z"].mean()) < 1e-9
    assert "repo_health_index_pca" in panel.columns
    # more contributors + lower top-author share as i grows => health rises
    assert panel["repo_health_index_z"].iloc[-1] > panel["repo_health_index_z"].iloc[0]


def test_empty_inputs_yield_empty_frame():
    firm, *_ = _inputs()
    panel = build_panel([firm], {}, {}, {})
    assert panel.empty
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_panel_assemble.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'git_due_diligence.panel.assemble'`

- [ ] **Step 3: Implement**

Create `src/git_due_diligence/panel/assemble.py`:

```python
from __future__ import annotations

from datetime import date

from git_due_diligence.panel.edgar import QuarterFundamentals
from git_due_diligence.panel.history import QuarterMetrics
from git_due_diligence.panel.universe import Firm

# metric -> sign such that a positive signed value = healthier repo.
# merge_share and commit_volume stay out of the index: they are workflow and
# scale variables (kept as panel columns for use as controls), not health.
INDEX_COMPONENTS: list[tuple[str, int]] = [
    ("active_contributors", 1),
    ("top_author_share", -1),
    ("contributor_gini", -1),
    ("bus_factor_50", 1),
    ("churn_gini", -1),
    ("release_cadence", 1),
    ("secret_incidence", -1),
]

# fiscal month-end quarter dates vs XBRL period ends (52/53-week calendars
# can differ by a few days)
_FUNDAMENTALS_JOIN_TOLERANCE_DAYS = 10


def _match_fundamentals(by_end: dict[date, QuarterFundamentals],
                        target: date) -> QuarterFundamentals | None:
    if not by_end:
        return None
    best = min(by_end, key=lambda d: abs((d - target).days))
    if abs((best - target).days) > _FUNDAMENTALS_JOIN_TOLERANCE_DAYS:
        return None
    return by_end[best]


def build_panel(firms: list[Firm],
                metrics_by_slug: dict[str, list[QuarterMetrics]],
                fundamentals_by_slug: dict[str, list[QuarterFundamentals]],
                prices_by_slug: dict[str, dict[date, float | None]]):
    import numpy as np
    import pandas as pd

    rows: list[dict] = []
    for firm in firms:
        quarters = sorted(metrics_by_slug.get(firm.slug, []), key=lambda m: m.quarter_end)
        by_end = {f.quarter_end: f for f in fundamentals_by_slug.get(firm.slug, [])}
        prices = prices_by_slug.get(firm.slug, {})
        matched = [_match_fundamentals(by_end, m.quarter_end) for m in quarters]
        for i, m in enumerate(quarters):
            if i < 3:
                continue
            window = matched[i - 3:i + 1]
            if any(f is None for f in window):
                continue
            revenue_ltm = sum(f.revenue for f in window)
            price = prices.get(m.quarter_end)
            shares = window[-1].shares_outstanding
            if revenue_ltm <= 0 or price is None or shares is None:
                continue
            ops = [f.operating_income for f in window]
            op_margin_ltm = (sum(ops) / revenue_ltm
                             if all(v is not None for v in ops) else np.nan)
            growth_yoy = np.nan
            if i >= 7:
                prior = matched[i - 7:i - 3]
                if all(f is not None for f in prior):
                    prior_ltm = sum(f.revenue for f in prior)
                    if prior_ltm > 0:
                        growth_yoy = revenue_ltm / prior_ltm - 1
            market_cap = price * shares
            net_debt = (window[-1].debt or 0.0) - (window[-1].cash or 0.0)
            ev = market_cap + net_debt
            if ev <= 0:
                continue
            rows.append({
                "firm": firm.slug,
                "ticker": firm.ticker,
                "quarter_end": m.quarter_end.isoformat(),
                "revenue_ltm": revenue_ltm,
                "growth_yoy": growth_yoy,
                "op_margin_ltm": op_margin_ltm,
                "market_cap": market_cap,
                "net_debt": net_debt,
                "ev": ev,
                "ev_rev": ev / revenue_ltm,
                "log_ev_rev": float(np.log(ev / revenue_ltm)),
                "log_rev": float(np.log(revenue_ltm)),
                "active_contributors": m.active_contributors,
                "top_author_share": m.top_author_share,
                "contributor_gini": m.contributor_gini,
                "bus_factor_50": m.bus_factor_50,
                "churn_gini": m.churn_gini,
                "release_cadence": m.release_cadence,
                "merge_share": m.merge_share,
                "commit_volume": m.commit_volume,
                "secret_incidence": m.secret_incidence,
            })
    panel = pd.DataFrame(rows)
    if panel.empty:
        return panel
    signed = {}
    for column, sign in INDEX_COMPONENTS:
        std = panel[column].std(ddof=0)
        signed[column] = sign * (panel[column] - panel[column].mean()) / (std if std > 0 else 1.0)
    z = pd.DataFrame(signed)
    panel["repo_health_index_z"] = z.mean(axis=1)
    matrix = z.to_numpy()
    _, _, vt = np.linalg.svd(matrix - matrix.mean(axis=0), full_matrices=False)
    pc1 = matrix @ vt[0]
    corr = np.corrcoef(pc1, panel["repo_health_index_z"])[0, 1]
    if np.isfinite(corr) and corr < 0:
        pc1 = -pc1
    panel["repo_health_index_pca"] = pc1
    return panel
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_panel_assemble.py -v`
Expected: 6 PASS

- [ ] **Step 5: Commit**

```bash
git add src/git_due_diligence/panel/assemble.py tests/test_panel_assemble.py
git commit -m "feat(panel): firm-quarter panel assembler with health indices"
```

---

### Task 6: Regression runner — `regress.py`

**Files:**
- Create: `src/git_due_diligence/panel/regress.py`
- Test: `tests/test_panel_regress.py`

**Interfaces:**
- Consumes: a pandas DataFrame with (at least) columns `firm, quarter_end, log_ev_rev, growth_yoy, op_margin_ltm, log_rev, repo_health_index_z` — the Task 5 output schema.
- Produces:
  - `run_regressions(panel, output_dir: Path, index_col: str = "repo_health_index_z") -> dict[str, statsmodels RegressionResults]` — keys `"h1"` and `"h2_k1"…"h2_k4"` (an H2 horizon is skipped if fewer than 30 usable rows). Writes `h1_pricing.txt` and `h2_growth_fwd_{k}.txt` summaries into `output_dir`.
  - Both specifications include firm and calendar-quarter fixed effects (`C(firm) + C(quarter_end)`) and cluster standard errors by firm.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_panel_regress.py`:

```python
import numpy as np
import pandas as pd

from git_due_diligence.panel.regress import run_regressions


def _synthetic_panel(n_firms=12, n_quarters=30, beta_h1=0.5, beta_h2=0.3, seed=0) -> pd.DataFrame:
    """Planted data-generating process: log multiple = 1 + 0.5*index + firm FE
    + quarter FE + tiny noise; growth at t = 0.3*index at t-1 + tiny noise.
    Controls are pure noise with zero true coefficients."""
    rng = np.random.default_rng(seed)
    firm_fe = rng.normal(0, 0.5, n_firms)
    quarter_fe = rng.normal(0, 0.3, n_quarters)
    index = rng.normal(0, 1, (n_firms, n_quarters))
    rows = []
    for i in range(n_firms):
        for t in range(n_quarters):
            growth = (beta_h2 * index[i, t - 1] if t > 0 else 0.0) + rng.normal(0, 0.01)
            rows.append({
                "firm": f"firm{i:02d}",
                "quarter_end": f"q{t:02d}",
                "repo_health_index_z": index[i, t],
                "growth_yoy": growth,
                "op_margin_ltm": rng.normal(0, 0.1),
                "log_rev": rng.normal(5, 0.5),
                "log_ev_rev": (1.0 + beta_h1 * index[i, t]
                               + firm_fe[i] + quarter_fe[t] + rng.normal(0, 0.01)),
            })
    return pd.DataFrame(rows)


def test_h1_recovers_planted_coefficient(tmp_path):
    results = run_regressions(_synthetic_panel(), tmp_path)
    assert abs(results["h1"].params["repo_health_index_z"] - 0.5) < 0.02
    assert (tmp_path / "h1_pricing.txt").exists()


def test_h2_recovers_planted_predictive_coefficient(tmp_path):
    results = run_regressions(_synthetic_panel(), tmp_path)
    assert abs(results["h2_k1"].params["repo_health_index_z"] - 0.3) < 0.05
    assert (tmp_path / "h2_growth_fwd_1.txt").exists()


def test_all_h2_horizons_run(tmp_path):
    results = run_regressions(_synthetic_panel(), tmp_path)
    assert {"h1", "h2_k1", "h2_k2", "h2_k3", "h2_k4"} <= set(results)


def test_rows_with_missing_values_dropped_not_fatal(tmp_path):
    panel = _synthetic_panel()
    panel.loc[panel.index[:5], "growth_yoy"] = np.nan
    results = run_regressions(panel, tmp_path)
    assert "h1" in results
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_panel_regress.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'git_due_diligence.panel.regress'`

- [ ] **Step 3: Implement**

Create `src/git_due_diligence/panel/regress.py`:

```python
from __future__ import annotations

from pathlib import Path

_CONTROLS = "growth_yoy + op_margin_ltm + log_rev"
_FIXED_EFFECTS = "C(firm) + C(quarter_end)"
_MIN_ROWS = 30
_H2_HORIZONS = range(1, 5)


def run_regressions(panel, output_dir: Path,
                    index_col: str = "repo_health_index_z") -> dict:
    """H1: log(EV/Rev) on repo health + Rule-of-40 controls, firm + quarter
    fixed effects, firm-clustered SEs. H2: forward growth at horizons 1-4
    quarters on the same right-hand side."""
    import statsmodels.formula.api as smf

    output_dir.mkdir(parents=True, exist_ok=True)
    results: dict = {}

    base_cols = [index_col, "growth_yoy", "op_margin_ltm", "log_rev"]
    h1_data = panel.dropna(subset=["log_ev_rev", *base_cols])
    h1 = smf.ols(
        f"log_ev_rev ~ {index_col} + {_CONTROLS} + {_FIXED_EFFECTS}", data=h1_data,
    ).fit(cov_type="cluster", cov_kwds={"groups": h1_data["firm"]})
    results["h1"] = h1
    (output_dir / "h1_pricing.txt").write_text(h1.summary().as_text(), encoding="utf-8")

    panel = panel.sort_values(["firm", "quarter_end"]).copy()
    for k in _H2_HORIZONS:
        outcome = f"growth_fwd_{k}"
        panel[outcome] = panel.groupby("firm")["growth_yoy"].shift(-k)
        sub = panel.dropna(subset=[outcome, *base_cols])
        if len(sub) < _MIN_ROWS:
            continue
        h2 = smf.ols(
            f"{outcome} ~ {index_col} + {_CONTROLS} + {_FIXED_EFFECTS}", data=sub,
        ).fit(cov_type="cluster", cov_kwds={"groups": sub["firm"]})
        results[f"h2_k{k}"] = h2
        (output_dir / f"h2_growth_fwd_{k}.txt").write_text(
            h2.summary().as_text(), encoding="utf-8")
    return results
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_panel_regress.py -v`
Expected: 4 PASS

- [ ] **Step 5: Commit**

```bash
git add src/git_due_diligence/panel/regress.py tests/test_panel_regress.py
git commit -m "feat(panel): H1/H2 fixed-effects regressions with clustered SEs"
```

---

### Task 7: CLI wiring — `gitdd panel build` / `gitdd panel regress` + README

**Files:**
- Create: `src/git_due_diligence/panel/cli.py`
- Modify: `src/git_due_diligence/cli.py` (two lines: import + `app.add_typer`)
- Modify: `README.md` (new section)
- Test: `tests/test_panel_cli.py`

**Interfaces:**
- Consumes: everything from Tasks 1–6 — `load_universe`, `fiscal_quarter_ends`, `quarterly_metrics`, `fetch_fundamentals`, `quarter_end_prices`, `build_panel`, `run_regressions`, plus the exact cache file names from Tasks 3–4 (`edgar_CIK{cik}.json`, `stooq_{ticker.lower()}.us.csv`).
- Produces: `panel_app: typer.Typer` mounted on the main app as command group `panel`. Heavy imports stay inside command bodies so `gitdd analyze`/`model` keep working without the `[panel]` extra.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_panel_cli.py`:

```python
import json
import subprocess
from pathlib import Path

from typer.testing import CliRunner

from git_due_diligence.cli import app

runner = CliRunner()

_QUARTER_PERIODS = [
    ("2023-01-01", "2023-03-31"), ("2023-04-01", "2023-06-30"),
    ("2023-07-01", "2023-09-30"), ("2023-10-01", "2023-12-31"),
    ("2024-01-01", "2024-03-31"), ("2024-04-01", "2024-06-30"),
    ("2024-07-01", "2024-09-30"), ("2024-10-01", "2024-12-31"),
]

ACME_TOML = """\
name = "Acme"
slug = "acme"
ticker = "ACME"
cik = "0000000001"
repos = ["https://example.com/acme.git"]
fiscal_year_end_month = 12
listed_from = 2023-01-01
listed_to = 2024-12-31
"""

STOOQ_CSV = "Date,Open,High,Low,Close,Volume\n" + "\n".join(
    f"{d},20,21,19,20.0,1000" for d in
    ["2023-03-31", "2023-06-30", "2023-09-29", "2023-12-29",
     "2024-03-28", "2024-06-28", "2024-09-30", "2024-12-31"]) + "\n"


def _canned_edgar() -> dict:
    revenue = [{"start": s, "end": e, "val": 100.0 + 5 * i, "form": "10-Q"}
               for i, (s, e) in enumerate(_QUARTER_PERIODS)]
    ends = [e for _, e in _QUARTER_PERIODS]
    return {"cik": 1, "facts": {
        "dei": {"EntityCommonStockSharesOutstanding": {"units": {"shares": [
            {"end": e, "val": 1_000_000.0, "form": "10-Q"} for e in ends]}}},
        "us-gaap": {
            "Revenues": {"units": {"USD": revenue}},
            "OperatingIncomeLoss": {"units": {"USD": [
                {**entry, "val": 10.0} for entry in revenue]}},
            "CashAndCashEquivalentsAtCarryingValue": {"units": {"USD": [
                {"end": e, "val": 50.0} for e in ends]}},
        },
    }}


def test_panel_help_lists_commands():
    result = runner.invoke(app, ["panel", "--help"])
    assert result.exit_code == 0
    assert "build" in result.output
    assert "regress" in result.output


def test_panel_build_runs_offline_from_cache(tmp_path):
    universe = tmp_path / "universe"
    universe.mkdir()
    (universe / "acme.toml").write_text(ACME_TOML, encoding="utf-8")

    clones = tmp_path / "clones"
    repo = clones / "acme"
    repo.mkdir(parents=True)
    subprocess.run(["git", "init", "-b", "main", str(repo)], check=True, capture_output=True)
    (repo / "a.py").write_text("A = 1\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "a.py"], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@example.com",
         "commit", "-m", "init", "--date", "2023-02-01T10:00:00"],
        check=True, capture_output=True,
    )

    cache = tmp_path / "cache"
    cache.mkdir()
    (cache / "edgar_CIK0000000001.json").write_text(json.dumps(_canned_edgar()), encoding="utf-8")
    (cache / "stooq_acme.us.csv").write_text(STOOQ_CSV, encoding="utf-8")

    output = tmp_path / "panel.csv"
    result = runner.invoke(app, [
        "panel", "build", "--universe", str(universe), "--clones", str(clones),
        "--cache", str(cache), "-o", str(output),
    ])
    assert result.exit_code == 0, result.output
    import pandas as pd
    panel = pd.read_csv(output)
    assert len(panel) == 5                      # quarters 4-8 have a full LTM window
    assert "repo_health_index_z" in panel.columns
    assert set(panel["firm"]) == {"acme"}


def test_panel_build_skips_firm_without_clone(tmp_path):
    universe = tmp_path / "universe"
    universe.mkdir()
    (universe / "acme.toml").write_text(ACME_TOML, encoding="utf-8")
    clones = tmp_path / "clones"
    clones.mkdir()
    output = tmp_path / "panel.csv"
    result = runner.invoke(app, [
        "panel", "build", "--universe", str(universe), "--clones", str(clones),
        "--cache", str(tmp_path / "cache"), "-o", str(output),
    ])
    assert result.exit_code == 0
    assert "skipping acme" in result.output


def test_panel_regress_writes_result_tables(tmp_path):
    import numpy as np
    import pandas as pd
    rng = np.random.default_rng(0)
    rows = []
    for i in range(10):
        for t in range(20):
            idx = rng.normal()
            rows.append({
                "firm": f"f{i}", "quarter_end": f"q{t:02d}",
                "repo_health_index_z": idx,
                "growth_yoy": rng.normal(0, 0.01),
                "op_margin_ltm": rng.normal(0, 0.1),
                "log_rev": rng.normal(5, 0.5),
                "log_ev_rev": 1.0 + 0.5 * idx + rng.normal(0, 0.01),
            })
    csv_path = tmp_path / "panel.csv"
    pd.DataFrame(rows).to_csv(csv_path, index=False)
    out_dir = tmp_path / "results"
    result = runner.invoke(app, ["panel", "regress", str(csv_path), "-o", str(out_dir)])
    assert result.exit_code == 0, result.output
    assert (out_dir / "h1_pricing.txt").exists()
    assert "h1" in result.output
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_panel_cli.py -v`
Expected: FAIL — `test_panel_help_lists_commands` fails because `panel` is not a registered command (exit code 2, "No such command").

- [ ] **Step 3: Implement the panel CLI**

Create `src/git_due_diligence/panel/cli.py`:

```python
from __future__ import annotations

from datetime import date
from pathlib import Path

import typer

panel_app = typer.Typer(
    add_completion=False,
    help="Firm-quarter panel: build the dataset, run the H1/H2 regressions",
)

_EXTRA_HINT = "panel commands require the panel extra: pip install git-due-diligence[panel]"


def _require_panel_extra() -> None:
    try:
        import pandas  # noqa: F401
        import statsmodels  # noqa: F401
    except ImportError:
        typer.echo(_EXTRA_HINT, err=True)
        raise typer.Exit(code=1)


@panel_app.command()
def build(
    universe: Path = typer.Option(..., "--universe", exists=True, file_okay=False,
                                  help="Directory of per-firm TOML configs"),
    clones: Path = typer.Option(..., "--clones", exists=True, file_okay=False,
                                help="Directory with one local clone per firm, named by slug"),
    output: Path = typer.Option(Path("panel.csv"), "--output", "-o"),
    cache: Path = typer.Option(Path("panel_cache"), "--cache",
                               help="Cache directory for EDGAR/price payloads (reused offline)"),
) -> None:
    """Build the firm-quarter panel CSV from local clones + EDGAR + prices."""
    _require_panel_extra()
    from git_due_diligence.panel.assemble import build_panel
    from git_due_diligence.panel.edgar import fetch_fundamentals
    from git_due_diligence.panel.history import quarterly_metrics
    from git_due_diligence.panel.prices import quarter_end_prices
    from git_due_diligence.panel.universe import fiscal_quarter_ends, load_universe

    firms = load_universe(universe)
    metrics_by_slug: dict = {}
    fundamentals_by_slug: dict = {}
    prices_by_slug: dict = {}
    kept = []
    for firm in firms:
        clone = clones / firm.slug
        if not clone.exists():
            typer.echo(f"warning: no clone at {clone}; skipping {firm.slug}", err=True)
            continue
        quarter_ends = fiscal_quarter_ends(
            firm.fiscal_year_end_month, firm.listed_from, firm.listed_to or date.today())
        typer.echo(f"{firm.slug}: {len(quarter_ends)} fiscal quarters")
        metrics_by_slug[firm.slug] = quarterly_metrics(clone, quarter_ends)
        fundamentals_by_slug[firm.slug] = fetch_fundamentals(firm.cik, cache)
        prices_by_slug[firm.slug] = quarter_end_prices(firm.ticker, quarter_ends, cache)
        kept.append(firm)
    panel = build_panel(kept, metrics_by_slug, fundamentals_by_slug, prices_by_slug)
    panel.to_csv(output, index=False)
    n_firms = panel["firm"].nunique() if len(panel) else 0
    typer.echo(f"Panel written to {output}: {len(panel)} firm-quarters across {n_firms} firms")


@panel_app.command()
def regress(
    panel_csv: Path = typer.Argument(..., exists=True, dir_okay=False),
    output_dir: Path = typer.Option(Path("panel_results"), "--output", "-o"),
) -> None:
    """Run the H1 (pricing) and H2 (predictive) regressions on a built panel."""
    _require_panel_extra()
    import pandas as pd

    from git_due_diligence.panel.regress import run_regressions

    panel = pd.read_csv(panel_csv)
    results = run_regressions(panel, output_dir)
    for name, res in results.items():
        coefficient = res.params.get("repo_health_index_z")
        typer.echo(f"{name}: repo_health_index_z = {coefficient:+.4f}")
    typer.echo(f"Wrote {len(results)} summary tables to {output_dir}")
```

Then in `src/git_due_diligence/cli.py`, after the existing imports add:

```python
from git_due_diligence.panel.cli import panel_app
```

and directly under `app = typer.Typer(add_completion=False)` add:

```python
app.add_typer(panel_app, name="panel")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_panel_cli.py -v`
Expected: 4 PASS

- [ ] **Step 5: Add the README section**

In `README.md`, insert this section between "## Validating the methodology" and "## Development":

````markdown
## Research: is repository health priced?

The `gitdd panel` command group builds a firm-quarter research dataset for public companies
whose flagship product is developed in an open repository, and runs the panel regressions
behind the study *"Is Repository Health Priced?"* (design doc:
`docs/superpowers/specs/2026-07-06-repo-health-pricing-panel-study-design.md`).

```bash
pip install -e ".[panel]"

# one local clone per firm, directory name = firm slug from panel/universe/*.toml
gitdd panel build --universe panel/universe --clones /path/to/clones -o panel.csv
gitdd panel regress panel.csv -o panel_results/
```

`build` reconstructs each repo's health metrics as they stood at every fiscal quarter-end
(trailing one-year window, bot authors excluded), fetches quarterly fundamentals from SEC
EDGAR XBRL and quarter-end prices from Stooq (both cached to `panel_cache/`, so rebuilds
are offline and reproducible), and joins everything into one tidy CSV. `regress` estimates
whether repo health explains EV/Revenue multiples beyond growth/margin/scale (firm and
quarter fixed effects, firm-clustered standard errors) and whether it forecasts revenue
growth one to four quarters ahead.
````

- [ ] **Step 6: Run the full suite**

Run: `.venv/Scripts/python.exe -m pytest -q`
Expected: 150 passed (119 existing + 31 new across Tasks 1–7), no failures.

- [ ] **Step 7: Commit**

```bash
git add src/git_due_diligence/panel/cli.py src/git_due_diligence/cli.py README.md tests/test_panel_cli.py
git commit -m "feat(panel): gitdd panel build/regress CLI and README research section"
```

---

## Post-plan notes (not tasks)

- **Data collection is analyst work, not code:** cloning the 12–18 firm repos, writing their universe TOMLs (verifying each CIK on EDGAR, fiscal-year-end month, listing window, attribution rule for Confluent/Kafka), and running `gitdd panel build` for real happens after this plan ships. The GitLab clone already exists at `/d/ac-clones/gitlab`.
- **Known v1 limitations carried from the spec (do not "fix" during implementation):** first-matching-XBRL-tag revenue resolution, priority-first debt tag, no CCN hotspot metrics, US filers only.
- The `panel_cache/` and generated `panel.csv`/`panel_results/` outputs at repo root should be gitignored when first produced (`panel_cache/`, `panel.csv`, `panel_results/`) — they are per-run artifacts; the *published* dataset will be committed deliberately once the universe is final.

