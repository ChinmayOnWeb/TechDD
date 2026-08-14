"""Draw and freeze the Part C repository sampling frame.

Run once. The output (cohort/frame.json) is committed so the drawn sample is
fixed even though PyPI's index keeps moving, and so every downstream number is
regenerable from the frozen draw.
"""
from __future__ import annotations

import sys
from pathlib import Path

from git_due_diligence.cohort.frame import (
    fetch_project_names,
    resolve_projects,
    sample_projects,
    write_frame,
)

SEED = 20260812
SAMPLE_SIZE = 8000
CACHE = Path("cohort_cache")
OUTPUT = Path("cohort/frame.json")


def main() -> int:
    names = fetch_project_names(CACHE)
    print(f"PyPI index snapshot: {len(names):,} projects", flush=True)

    sample = sample_projects(names, SAMPLE_SIZE, SEED)
    print(f"drawn: {len(sample):,} projects (seed={SEED})", flush=True)

    def progress(done: int, total: int) -> None:
        if done % 250 == 0:
            print(f"  resolved {done}/{total}", flush=True)

    entries = resolve_projects(sample, CACHE / "pypi", on_progress=progress,
                               delay_seconds=0.05)
    write_frame(entries, OUTPUT, meta={
        "source": "pypi-simple-complete-enumeration",
        "index_size": len(names),
        "seed": SEED,
        "sample_size": SAMPLE_SIZE,
        "resolved_repos": len(entries),
    })
    print(f"frame written: {len(entries):,} unique GitHub repos -> {OUTPUT}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
