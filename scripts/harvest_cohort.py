"""Full Part C harvest across both ecosystem frames.

Checkpointed per ecosystem, so this is safe to interrupt and resume; re-running
skips everything already measured. Peak disk is one repository at a time.
"""
from __future__ import annotations

import sys
import time
from collections import Counter
from datetime import date
from pathlib import Path

from git_due_diligence.cohort.frame import read_frame
from git_due_diligence.cohort.harvest import harvest_frame

TODAY = date(2026, 8, 12)
FRAMES = [
    ("pypi", Path("cohort/frame.json"), Path("cohort_results/harvest_pypi.jsonl")),
    ("npm", Path("cohort/frame_npm.json"), Path("cohort_results/harvest_npm.jsonl")),
]


def main() -> int:
    for name, frame_path, checkpoint in FRAMES:
        entries = read_frame(frame_path)
        print(f"=== {name}: {len(entries):,} repos -> {checkpoint} ===", flush=True)
        counts: Counter = Counter()
        started = time.time()
        done = 0
        for result in harvest_frame(entries, Path("cohort_work"), checkpoint, TODAY):
            counts[result.status] += 1
            done += 1
            if done % 200 == 0:
                rate = done / max(time.time() - started, 1)
                print(f"  {name} {done}/{len(entries)}  {rate:.1f}/s  {dict(counts)}",
                      flush=True)
        print(f"=== {name} complete: {dict(counts)} ===", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
