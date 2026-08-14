"""Per-firm cache for the expensive point-in-time repo-metrics pass.

`quarterly_metrics` streams the full-history patch of a clone to score secrets,
which for a large monorepo (GitLab: ~550k commits) takes tens of minutes. Since
`panel build` recomputes every firm on each run, adding one firm would otherwise
re-pay that cost for every existing firm. We cache each firm's metrics keyed by
the clone's HEAD sha and the requested quarter-ends, so a firm is recomputed only
when its clone advances or its quarter grid changes.
"""
from __future__ import annotations

import dataclasses
import json
import subprocess
from datetime import date
from pathlib import Path
from typing import Callable

from git_due_diligence.panel.history import QuarterMetrics, quarterly_metrics


def _head_sha(repo_path: Path) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo_path), "rev-parse", "HEAD"],
        check=True, capture_output=True, text=True,
    )
    return result.stdout.strip()


def _serialize(metrics: list[QuarterMetrics]) -> list[dict]:
    rows = []
    for m in metrics:
        row = dataclasses.asdict(m)
        row["quarter_end"] = m.quarter_end.isoformat()
        rows.append(row)
    return rows


def _deserialize(rows: list[dict]) -> list[QuarterMetrics]:
    out = []
    for row in rows:
        row = dict(row)
        row["quarter_end"] = date.fromisoformat(row["quarter_end"])
        out.append(QuarterMetrics(**row))
    return out


def load_or_compute_metrics(
    slug: str,
    repo_path: Path,
    quarter_ends: list[date],
    cache_dir: Path,
    compute: Callable[[Path, list[date]], list[QuarterMetrics]] = quarterly_metrics,
) -> list[QuarterMetrics]:
    """Return cached metrics when the clone HEAD and quarter grid are unchanged,
    otherwise compute fresh and write the cache. `compute` is injectable for tests."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = cache_dir / f"metrics_{slug}.json"
    head = _head_sha(repo_path)
    grid = [q.isoformat() for q in quarter_ends]

    if cache_file.exists():
        cached = json.loads(cache_file.read_text(encoding="utf-8"))
        if cached.get("head") == head and cached.get("quarter_ends") == grid:
            return _deserialize(cached["metrics"])

    metrics = compute(repo_path, quarter_ends)
    cache_file.write_text(json.dumps({
        "head": head,
        "quarter_ends": grid,
        "metrics": _serialize(metrics),
    }), encoding="utf-8")
    return metrics
