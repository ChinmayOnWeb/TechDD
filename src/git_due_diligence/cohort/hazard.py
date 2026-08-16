"""Discrete-time hazard estimation for the Part C cohort study.

The outcome is observed quarterly, so a discrete-time hazard is the natural
specification: pool the repository-quarter rows and model

    P(event in quarter t | still at risk at t) = logit(f(duration) + b'X_t)

Each repository contributes one row per quarter it survives, and drops out of
the risk set once the event occurs or observation ends -- which is exactly what
`outcomes.observation_rows` emits. Right-censoring is handled by construction:
a censored repository simply contributes rows with `event = 0` and no final
event row, so it informs the baseline hazard without being counted as a
survivor forever.

Three specification constraints come from the measurement findings and are
enforced here rather than left to the caller:

  - **Predictors are time-varying.** Every project starts as one person's first
    commits, so baseline-quarter covariates are degenerate and a
    baseline-only specification finds nothing for reasons unrelated to the
    hypothesis.
  - **Activity is a control, never omitted.** Dormancy *is* the absence of
    commits, so `commit_volume` predicts it near-tautologically; without it in
    the model the structural coefficients simply absorb activity.
  - **Standard errors cluster by repository.** Rows within a repository are the
    same project observed repeatedly, not independent draws.

Duration enters as a spline-free set of dummies on the quarter index, binned so
that late, sparse durations do not each get their own parameter.
"""
from __future__ import annotations

from pathlib import Path

# Predictors that enter the structural specification. commit_volume is a
# CONTROL, not a health measure, and is listed separately so it cannot be
# dropped by accident.
STRUCTURAL = ["log_contributors", "top_author_share", "bus_factor_50", "churn_gini"]
ACTIVITY_CONTROL = "log_commit_volume"

# Durations beyond this are pooled into one bin: few repositories survive that
# long, and one dummy per quarter there is noise with a parameter attached.
_MAX_DURATION_BIN = 12

# Quarters by which predictors are lagged. This is derived, not chosen, and it
# is what makes the model predictive rather than circular.
#
# commit_volume at quarter q counts commits in (q-4, q] (a trailing 365-day
# window, ~4 quarters). A dormancy event at t requires commit_volume zero at
# both t and t-1, so the event implies no commits across (t-5, t]. A predictor
# measured at t-L covers (t-L-4, t-L]. Requiring that window to end at or
# before t-5 -- i.e. no overlap with the interval the event itself determines --
# gives L >= 5; we use 6 for a clear margin.
#
# Without this lag the model is not merely biased, it is unestimable: with
# contemporaneous covariates, commit_volume = 0 perfectly separates the outcome
# and the Hessian is singular. The mechanical relationship noted descriptively
# ("commit_volume separates near-tautologically") is in fact COMPLETE
# separation, which is the statistical signature of conditioning on a component
# of the outcome.
PREDICTOR_LAG_QUARTERS = 6


def load_observations(paths: dict[str, Path], outcome: str = "dormancy"):
    """Build the pooled repository-quarter risk set from harvest checkpoints.

    `paths` maps an ecosystem label to its JSONL checkpoint. The label is kept
    on every row so the model can be estimated per-ecosystem (they are never
    pooled without saying so -- see docs/cohort-exclusions.md)."""
    import json

    import numpy as np
    import pandas as pd

    from git_due_diligence.cohort.outcomes import (
        first_contributor_collapse,
        first_dormancy,
        observation_rows,
    )
    from git_due_diligence.panel.history import QuarterMetrics

    spell_fn = {"dormancy": first_dormancy,
                "contributor_collapse": first_contributor_collapse}[outcome]

    frames = []
    for ecosystem, path in paths.items():
        rows = []
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            record = json.loads(line)
            if record.get("status") != "ok":
                continue
            metrics = [
                QuarterMetrics(**{**m, "quarter_end": __import__("datetime").date.fromisoformat(
                    m["quarter_end"])})
                for m in record["metrics"]
            ]
            if not metrics:
                continue
            spell = spell_fn(record["slug"], metrics)
            rows.extend(observation_rows(record["slug"], metrics, spell))
        frame = pd.DataFrame(rows)
        if frame.empty:
            continue
        frame["ecosystem"] = ecosystem
        frames.append(frame)

    panel = pd.concat(frames, ignore_index=True)

    # Counts enter in logs: they are right-skewed across orders of magnitude, so
    # a linear term would let a handful of very large projects dominate.
    panel["log_contributors"] = np.log1p(panel["active_contributors"])
    panel["log_commit_volume"] = np.log1p(panel["commit_volume"])
    panel["duration_bin"] = panel["quarter_index"].clip(upper=_MAX_DURATION_BIN)
    panel["solo"] = (panel["active_contributors"] <= 1).astype(int)

    # Lag predictors clear of the window the event itself determines. Each
    # repository is shifted independently and rows without a full lag are
    # dropped, so no covariate is carried across a repository boundary.
    panel = panel.sort_values(["slug", "quarter_index"])
    lagged = [*STRUCTURAL, ACTIVITY_CONTROL, "contributor_gini",
              "gini_identified", "solo"]
    for column in lagged:
        panel[f"lag_{column}"] = panel.groupby("slug")[column].shift(
            PREDICTOR_LAG_QUARTERS)
    return panel.reset_index(drop=True)


def fit_hazard(panel, extra_terms: list[str] | None = None,
               with_activity_control: bool = True):
    """Pooled logit hazard with duration dummies and repository-clustered SEs.

    `with_activity_control=False` exists to demonstrate what omitting the
    control does to the structural coefficients -- it is a diagnostic, not a
    specification anyone should report as a result."""
    import statsmodels.formula.api as smf

    terms = [f"lag_{t}" for t in STRUCTURAL] + list(extra_terms or [])
    if with_activity_control:
        terms.append(f"lag_{ACTIVITY_CONTROL}")
    formula = f"event ~ {' + '.join(terms)} + C(duration_bin)"

    data = panel.dropna(subset=["event", *terms]).copy()
    return smf.logit(formula, data=data).fit(
        disp=False, cov_type="cluster", cov_kwds={"groups": data["slug"]})


def hazard_ratios(result, terms: list[str] | None = None):
    """Coefficients as hazard/odds ratios with clustered confidence intervals.

    Reported as ratios because a log-odds coefficient is not interpretable at a
    glance, and the sign question this study turns on is easiest to read as
    'above or below 1'."""
    import numpy as np
    import pandas as pd

    keep = [t for t in (terms or result.params.index)
            if not t.startswith("C(") and t != "Intercept"]
    conf = result.conf_int().loc[keep]
    return pd.DataFrame({
        "coef": result.params.loc[keep],
        "hazard_ratio": np.exp(result.params.loc[keep]),
        "ci_low": np.exp(conf[0]),
        "ci_high": np.exp(conf[1]),
        "p": result.pvalues.loc[keep],
    })
