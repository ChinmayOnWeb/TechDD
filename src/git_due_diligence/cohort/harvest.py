"""Streaming harvest of repository metrics across the Part C frame.

Disk, not CPU, is the binding constraint: the firm panel's three clones ran
2.2-3.9 GB each against ~22 GB free, so cloning thousands of repositories
concurrently is not viable. Each repository is therefore cloned, measured and
deleted in turn, making peak disk the size of the largest single repository
rather than the sum of the frame.

Clones are **bare** (`--bare --single-branch`): full commit history and trees,
no working copy. A partial clone (`--filter=blob:none`) would be smaller still,
but `git log --numstat` needs blob contents to compute per-file churn and would
lazily refetch them one commit at a time -- slower overall and unfriendly to the
host. Bare is the right trade.

Results append to a JSONL checkpoint as they are produced, so a sweep that dies
partway (disk, network, container recycle) resumes without re-cloning what it
already measured.
"""
from __future__ import annotations

import calendar
import dataclasses
import json
import shutil
import subprocess
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Callable, Iterable, Iterator

from git_due_diligence.cohort.frame import FrameEntry
from git_due_diligence.panel.history import QuarterMetrics, quarterly_metrics

CLONE_TIMEOUT_SECONDS = 300

# --- Exclusion thresholds -------------------------------------------------
#
# Both are deliberately DERIVED rather than chosen, because an arbitrary
# exclusion in a survival study is not a neutral data-quality filter: the
# repositories it removes are systematically the short-lived ones, which are
# exactly the events being modelled. Excluding them selects on the outcome.
#
# MIN_QUARTERS is the MECHANICAL floor -- a non-empty metric series -- and
# nothing more. An earlier version imposed a minimum follow-up on the theory
# that shorter histories cannot produce an event and so contribute only noise.
# Measurement refuted that on two counts:
#
#   1. Right-censoring already handles varying follow-up correctly. A repository
#      observed for three quarters without an event is censored at three
#      quarters, which is information a hazard model consumes, not noise.
#   2. The follow-up needed for an event is NOT a constant. Because the
#      trailing-365-day window is half-open, the first all-zero quarter lands at
#      index 3 or 4 depending on where in the quarter the first commit falls, so
#      an event can fire as early as quarter 5 (for a 2-quarter dormancy run).
#      A hand-derived threshold of 7 would have discarded 3 real events in a
#      400-repository pilot.
#
# Any threshold above the mechanical floor can therefore only lose events. The
# informational function below reports when events BECOME observable, for the
# paper's exposition -- it is deliberately not wired to an exclusion.
MIN_FIRST_ZERO_INDEX = 3        # measured by sweeping all first-commit dates

# MIN_COMMITS is the mechanical floor for the metrics to be computable, and
# nothing more. One commit already yields authorship and churn (the root commit
# diffs against the empty tree), so the floor is 1 -- i.e. no substantive
# exclusion at all. A higher threshold would be a population definition rather
# than a technical requirement, and would preferentially drop
# published-once-then-abandoned projects: the maximal-mortality cases, and the
# ones a survival study most needs. Repository size is instead carried as a
# covariate so the analysis can condition on it explicitly rather than by
# exclusion. See docs/cohort-exclusions.md for the measured sensitivity.
MIN_COMMITS = 1
MIN_QUARTERS = 1


def earliest_observable_event_quarters(dormancy_quarters: int) -> int:
    """Fewest quarters of follow-up in which a dormancy event CAN be observed.

    Informational: used to state in the paper when events become observable,
    and to justify why no minimum-follow-up exclusion is applied. Not used as a
    filter -- see the note above."""
    return MIN_FIRST_ZERO_INDEX + dormancy_quarters


@dataclass
class HarvestResult:
    slug: str
    status: str                 # ok | clone_failed | too_small | too_short
    commit_count: int
    first_commit: str           # ISO date, "" when unknown
    last_commit: str
    metrics: list[QuarterMetrics]
    error: str = ""


def calendar_quarter_ends(start: date, end: date) -> list[date]:
    """Calendar quarter-ends in [start, end]. Repositories have no fiscal year,
    so unlike the firm panel the cohort uses plain calendar quarters."""
    ends: list[date] = []
    for year in range(start.year, end.year + 1):
        for month in (3, 6, 9, 12):
            day = date(year, month, calendar.monthrange(year, month)[1])
            if start <= day <= end:
                ends.append(day)
    return ends


def _run(args: list[str], timeout: int) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, text=True, timeout=timeout)


def clone_bare(clone_url: str, target: Path,
               timeout: int = CLONE_TIMEOUT_SECONDS) -> tuple[bool, str]:
    """Clone bare, converting a timeout into a recorded failure.

    subprocess.run raises TimeoutExpired rather than returning non-zero, so an
    uncaught timeout propagates and kills the whole sweep -- one oversized
    repository (ccxt/ccxt) ended a 4,850-repo run after 866. A timeout is a
    property of that repository, not of the sweep, so it is recorded and the
    sweep continues."""
    try:
        result = _run(
            ["git", "clone", "--bare", "--single-branch", "--quiet", clone_url, str(target)],
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return False, f"__timeout__ clone exceeded {timeout}s"
    if result.returncode != 0:
        return False, (result.stderr or "").strip()[:300]
    return True, ""


def free_disk_gb() -> float:
    return shutil.disk_usage("/").free / 1e9


def _commit_dates(repo: Path) -> list[date]:
    result = _run(["git", "-C", str(repo), "log", "--format=%aI"], timeout=120)
    if result.returncode != 0:
        return []
    out: list[date] = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(date.fromisoformat(line[:10]))
        except ValueError:
            continue
    return out


def harvest_repo(entry: FrameEntry, workdir: Path, today: date,
                 clone: Callable[[str, Path], tuple[bool, str]] | None = None,
                 measure: Callable[[Path, list[date]], list[QuarterMetrics]] | None = None,
                 min_commits: int = MIN_COMMITS,
                 min_quarters: int | None = None,
                 ) -> HarvestResult:
    """Clone, measure and delete one repository. The clone is removed even when
    measurement raises, so a failure mid-sweep cannot strand gigabytes on disk."""
    clone = clone or (lambda url, target: clone_bare(url, target))
    measure = measure or (lambda path, ends: quarterly_metrics(path, ends, lite=True))
    if min_quarters is None:
        min_quarters = MIN_QUARTERS

    target = workdir / f"{entry.owner}__{entry.repo}.git"
    if target.exists():
        shutil.rmtree(target, ignore_errors=True)
    workdir.mkdir(parents=True, exist_ok=True)
    try:
        ok, error = clone(entry.clone_url, target)
        if not ok:
            # Timeouts are tracked separately from 404s: they are almost always
            # very large repositories, which skew ACTIVE, so this attrition
            # biases toward higher measured mortality and must be reported as
            # its own rate rather than folded into generic clone failures.
            status = "clone_timeout" if error.startswith("__timeout__") else "clone_failed"
            return HarvestResult(entry.slug, status, 0, "", "", [], error)
        dates = _commit_dates(target)
        if len(dates) < min_commits:
            return HarvestResult(entry.slug, "too_small", len(dates), "", "", [])
        first, last = min(dates), max(dates)
        # The observation window runs to the study end, NOT to the last commit.
        # Ending it at the last commit would make dormancy unobservable by
        # construction -- dormancy *is* the absence of commits, so the silent
        # quarters that constitute the event would all be truncated away and
        # every repository would come back censored. It would also drop
        # short-lived projects below MIN_QUARTERS, reinstating precisely the
        # survivorship bias the complete-enumeration frame exists to avoid.
        quarter_ends = calendar_quarter_ends(first, today)
        if len(quarter_ends) < min_quarters:
            return HarvestResult(entry.slug, "too_short", len(dates),
                                 first.isoformat(), last.isoformat(), [])
        metrics = measure(target, quarter_ends)
        return HarvestResult(entry.slug, "ok", len(dates),
                             first.isoformat(), last.isoformat(), metrics)
    finally:
        shutil.rmtree(target, ignore_errors=True)


def completed_slugs(checkpoint: Path) -> set[str]:
    if not checkpoint.exists():
        return set()
    done: set[str] = set()
    for line in checkpoint.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            done.add(json.loads(line)["slug"])
        except (json.JSONDecodeError, KeyError):
            continue        # a torn final line from an interrupted run
    return done


def append_result(checkpoint: Path, result: HarvestResult) -> None:
    checkpoint.parent.mkdir(parents=True, exist_ok=True)
    row = dataclasses.asdict(result)
    row["metrics"] = [
        {**dataclasses.asdict(m), "quarter_end": m.quarter_end.isoformat()}
        for m in result.metrics
    ]
    with checkpoint.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row) + "\n")


def harvest_frame(entries: Iterable[FrameEntry], workdir: Path, checkpoint: Path,
                  today: date,
                  on_result: Callable[[HarvestResult], None] | None = None,
                  min_free_gb: float = 3.0,
                  **kwargs) -> Iterator[HarvestResult]:
    """Harvest every frame entry not already in the checkpoint, yielding as it
    goes. Safe to re-run: completed slugs are skipped.

    Stops cleanly if free disk falls below `min_free_gb`. Because progress is
    checkpointed per repository, stopping loses nothing -- a resumed run picks
    up where this one left off, which is far preferable to filling the volume
    and failing every subsequent write."""
    done = completed_slugs(checkpoint)
    for entry in entries:
        if entry.slug in done:
            continue
        if free_disk_gb() < min_free_gb:
            raise RuntimeError(
                f"stopping: {free_disk_gb():.1f} GB free, below the {min_free_gb} GB "
                f"floor. Progress is checkpointed; free space and re-run to resume.")
        result = harvest_repo(entry, workdir, today, **kwargs)
        append_result(checkpoint, result)
        if on_result:
            on_result(result)
        yield result
