"""Measure what the Part C exclusion thresholds would actually remove.

Runs the harvest with thresholds disabled, so the excluded population can be
characterised rather than assumed. The question that matters is not "how many
repositories does the filter drop" but "does it drop events at a different rate
than it drops non-events" -- a filter that removes short-lived projects is
selecting on the outcome, which no amount of sample size repairs.

Checkpointed, so it is safe to interrupt and resume.
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

from git_due_diligence.cohort.frame import read_frame
from git_due_diligence.cohort.harvest import harvest_frame

TODAY = date(2026, 8, 12)
SAMPLE = 400
CHECKPOINT = Path("cohort_results/exclusion_study.jsonl")


def main() -> int:
    frame = read_frame(Path("cohort/frame.json"))[:SAMPLE]
    done = 0
    for result in harvest_frame(frame, Path("cohort_work"), CHECKPOINT, TODAY,
                                min_commits=1, min_quarters=1):
        done += 1
        if done % 25 == 0:
            print(f"  {done} harvested ({result.status})", flush=True)
    print(f"complete: {done} newly harvested -> {CHECKPOINT}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
