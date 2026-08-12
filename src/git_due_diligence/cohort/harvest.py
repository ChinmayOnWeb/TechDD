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
# Below this, a repository cannot support a trailing-window panel: the metrics
# need a year of history plus room for an outcome to occur afterwards.
MIN_COMMITS = 10
MIN_QUARTERS = 8


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
    result = _run(
        ["git", "clone", "--bare", "--single-branch", "--quiet", clone_url, str(target)],
        timeout=timeout,
    )
    if result.returncode != 0:
        return False, (result.stderr or "").strip()[:300]
    return True, ""


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
                 ) -> HarvestResult:
    """Clone, measure and delete one repository. The clone is removed even when
    measurement raises, so a failure mid-sweep cannot strand gigabytes on disk."""
    clone = clone or (lambda url, target: clone_bare(url, target))
    measure = measure or (lambda path, ends: quarterly_metrics(path, ends, lite=True))

    target = workdir / f"{entry.owner}__{entry.repo}.git"
    if target.exists():
        shutil.rmtree(target, ignore_errors=True)
    workdir.mkdir(parents=True, exist_ok=True)
    try:
        ok, error = clone(entry.clone_url, target)
        if not ok:
            return HarvestResult(entry.slug, "clone_failed", 0, "", "", [], error)
        dates = _commit_dates(target)
        if len(dates) < MIN_COMMITS:
            return HarvestResult(entry.slug, "too_small", len(dates), "", "", [])
        first, last = min(dates), max(dates)
        quarter_ends = calendar_quarter_ends(first, min(last, today))
        if len(quarter_ends) < MIN_QUARTERS:
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
                  **kwargs) -> Iterator[HarvestResult]:
    """Harvest every frame entry not already in the checkpoint, yielding as it
    goes. Safe to re-run: completed slugs are skipped."""
    done = completed_slugs(checkpoint)
    for entry in entries:
        if entry.slug in done:
            continue
        result = harvest_repo(entry, workdir, today, **kwargs)
        append_result(checkpoint, result)
        if on_result:
            on_result(result)
        yield result
