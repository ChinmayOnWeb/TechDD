"""Estimate the Part C dormancy hazard and write the specification table.

Reports the full surface rather than a single headline: the primary
specification, the diagnostics that show why it is specified that way, and the
robustness cuts. Every specification is printed whatever it shows.
"""
from __future__ import annotations

import sys
from pathlib import Path

import git_due_diligence.cohort.hazard as H
from git_due_diligence.cohort.hazard import fit_hazard, hazard_ratios, load_observations

CHECKPOINTS = {
    "pypi": Path("cohort_results/harvest_pypi.jsonl"),
    "npm": Path("cohort_results/harvest_npm.jsonl"),
}
OUTPUT = Path("cohort_results/hazard_results.txt")


def _spec(out, label, panel, structural=None, activity=True, note=""):
    original = H.STRUCTURAL[:]
    if structural is not None:
        H.STRUCTURAL = structural
    try:
        result = fit_hazard(panel, with_activity_control=activity)
        table = hazard_ratios(result)[["hazard_ratio", "ci_low", "ci_high", "p"]]
        out.append(f"\n--- {label} ---")
        if note:
            out.append(f"    {note}")
        out.append(table.round(3).to_string())
        out.append(f"    N={int(result.nobs):,}  repos={panel['slug'].nunique():,}"
                   f"  pseudo-R2={result.prsquared:.3f}")
    except Exception as exc:                     # separation, singularity, no data
        out.append(f"\n--- {label} ---\n    NOT ESTIMABLE: {type(exc).__name__}: {exc}")
    finally:
        H.STRUCTURAL = original


def main() -> int:
    out: list[str] = ["DORMANCY HAZARD — Part C", "=" * 60]
    available = {k: v for k, v in CHECKPOINTS.items() if v.exists()}
    panels = {k: load_observations({k: v}) for k, v in available.items()}

    for eco, panel in panels.items():
        lagged = panel.dropna(subset=["lag_log_contributors"])
        out.append(f"\n{eco}: {len(panel):,} repo-quarters, "
                   f"{panel['slug'].nunique():,} repos, {int(panel['event'].sum()):,} events"
                   f"  |  after {H.PREDICTOR_LAG_QUARTERS}q lag: {len(lagged):,} rows, "
                   f"{int(lagged['event'].sum()):,} events")

    primary = panels.get("pypi")
    if primary is not None:
        out.append("\n" + "=" * 60 + "\nPRIMARY SPECIFICATION (PyPI)")
        _spec(out, "A. full model", primary,
              note="predictors lagged, activity controlled, repo-clustered SEs")

        out.append("\n" + "=" * 60 + "\nDIAGNOSTICS")
        _spec(out, "B. without activity control", primary, activity=False,
              note="shows structural terms absorbing activity when it is omitted")
        _spec(out, "C. without contributor count", primary,
              structural=["top_author_share", "bus_factor_50", "churn_gini"],
              note="concentration terms alone; tests whether their sign is "
                   "conditional on contributor count")

        out.append("\n" + "=" * 60 + "\nROBUSTNESS")
        _spec(out, "D. multi-contributor repos only", primary[primary["lag_solo"] == 0],
              note="the subpopulation where concentration measures are identified")
        _spec(out, "E. with contributor_gini", primary[primary["lag_gini_identified"] == 1],
              structural=[*H.STRUCTURAL, "contributor_gini"],
              note="gini only where identified (>=2 contributors)")

    if "npm" in panels:
        out.append("\n" + "=" * 60 + "\nREPLICATION (npm, independent frame)")
        _spec(out, "F. full model, npm", panels["npm"])

    text = "\n".join(out)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(text, encoding="utf-8")
    print(text)
    print(f"\nwritten -> {OUTPUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
