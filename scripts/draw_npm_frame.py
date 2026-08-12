"""Draw and freeze the npm robustness frame (Part C, second ecosystem).

Mirrors the PyPI draw exactly -- same seed, same sample size, same
complete-enumeration principle -- so that any difference in results between the
two ecosystems is attributable to the ecosystems rather than to sampling design.
"""
from __future__ import annotations

import sys
from pathlib import Path

from git_due_diligence.cohort.frame import sample_projects, write_frame
from git_due_diligence.cohort.npm import fetch_package_names, resolve_packages

SEED = 20260812
SAMPLE_SIZE = 8000
CACHE = Path("cohort_cache")
OUTPUT = Path("cohort/frame_npm.json")


def main() -> int:
    names, mirror_version = fetch_package_names(CACHE)
    print(f"npm index snapshot: {len(names):,} packages "
          f"(all-the-package-names {mirror_version})", flush=True)

    sample = sample_projects(names, SAMPLE_SIZE, SEED)
    print(f"drawn: {len(sample):,} packages (seed={SEED})", flush=True)

    def progress(done: int, total: int) -> None:
        if done % 250 == 0:
            print(f"  resolved {done}/{total}", flush=True)

    entries = resolve_packages(sample, CACHE / "npm", on_progress=progress,
                               delay_seconds=0.05)
    write_frame(entries, OUTPUT, meta={
        "source": "npm-all-the-package-names-complete-enumeration",
        "mirror_package_version": mirror_version,
        "index_size": len(names),
        "seed": SEED,
        "sample_size": SAMPLE_SIZE,
        "resolved_repos": len(entries),
    })
    print(f"frame written: {len(entries):,} unique GitHub repos -> {OUTPUT}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
