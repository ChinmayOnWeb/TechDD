"""Full Part C harvest across both ecosystem frames.

Checkpointed per ecosystem, so this is safe to interrupt and resume; re-running
skips everything already measured. Peak disk is one repository at a time.
"""
from __future__ import annotations

import os
import sys
import time
from collections import Counter
from datetime import date
from pathlib import Path

from git_due_diligence.cohort.frame import read_frame
from git_due_diligence.cohort.harvest import harvest_frame_parallel

TODAY = date(2026, 8, 12)
WORKERS = int(os.environ.get("COHORT_WORKERS", "12"))

# Bounded run time. Long-lived background processes are not reliably kept alive
# between turns in this environment -- two multi-hour attempts were reaped
# mid-sweep -- so the sweep advances in resumable, time-boxed chunks instead of
# one long job. Progress is checkpointed per repository either way, so a chunk
# that ends early costs nothing.
TIME_BUDGET_S = float(os.environ.get("COHORT_TIME_BUDGET", "540"))

_ALL_FRAMES = {
    "pypi": (Path("cohort/frame.json"), Path("cohort_results/harvest_pypi.jsonl")),
    "npm": (Path("cohort/frame_npm.json"), Path("cohort_results/harvest_npm.jsonl")),
}
# Frames are drawn in RANDOM order (random.sample, order preserved through
# resolution), verified empirically: adjacent out-of-order pairs sit at 51%, and
# the first and second halves are indistinguishable on staleness and release
# count. Truncating a frame is therefore a random subsample rather than a biased
# prefix, so a partially-harvested ecosystem is still valid -- which lets effort
# be steered to whichever frame is currently thinner.
FRAMES = [(name, *_ALL_FRAMES[name])
          for name in os.environ.get("COHORT_FRAMES", "pypi,npm").split(",")
          if name in _ALL_FRAMES]


def main() -> int:
    for name, frame_path, checkpoint in FRAMES:
        entries = read_frame(frame_path)
        print(f"=== {name}: {len(entries):,} repos -> {checkpoint} ===", flush=True)
        counts: Counter = Counter()
        started = time.time()
        done = 0
        for result in harvest_frame_parallel(entries, Path("cohort_work"), checkpoint,
                                             TODAY, workers=WORKERS):
            counts[result.status] += 1
            done += 1
            if done % 200 == 0:
                rate = done / max(time.time() - started, 1)
                print(f"  {name} {done}/{len(entries)}  {rate:.1f}/s  {dict(counts)}",
                      flush=True)
            if time.time() - started > TIME_BUDGET_S:
                print(f"  {name}: time budget reached after {done} this run; "
                      f"re-run to resume", flush=True)
                return 0
        print(f"=== {name} complete: {dict(counts)} ===", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
