from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

_CONTROLS = "growth_yoy + op_margin_ltm + log_rev"
_FIXED_EFFECTS = "C(firm) + C(period)"
_MIN_ROWS = 30
_MIN_FIRMS = 2   # firm-clustered SE degenerate with a single group
_H2_HORIZONS = range(1, 5)

# Days back from a fiscal quarter-end to land inside the quarter it covers.
# A fiscal quarter spans ~91 days, so ~45 days back is its midpoint.
_QUARTER_MIDPOINT_DAYS = 45


def calendar_period(quarter_end: date) -> str:
    """Calendar quarter containing the midpoint of the fiscal quarter ending
    `quarter_end`, e.g. date(2022, 1, 31) -> '2021Q4'.

    Time fixed effects must live on a grid that firms with DIFFERENT fiscal
    calendars actually share. Keying them to the raw fiscal quarter-end does
    not: a January-FYE firm reports quarter-ends on 01-31/04-30/07-31/10-31
    while a December-FYE firm reports 03-31/06-30/09-30/12-31, so the two sets
    are disjoint and no time dummy is ever identified off more than one fiscal
    calendar. Worse, every quarter-end of the lone December-FYE firm is unique
    to it, which makes that firm's dummy an exact linear combination of its own
    time dummies -- a rank-deficient design that statsmodels does not reject.
    It silently returned coefficients of ~1.3e10 with NaN standard errors, and
    an R^2 of 0.95 that was pure collinearity.

    The bug was invisible while the panel held only January-FYE firms (GitLab,
    MongoDB, Elastic); adding Hortonworks (FYE December) exposed it.

    Mapping by midpoint rather than by the quarter-end date itself aligns the
    periods by the economic time they actually cover: the fiscal quarter ending
    2022-01-31 spans Nov-Jan and the one ending 2021-12-31 spans Oct-Dec, so
    both belong in 2021Q4 -- one month apart in midpoint, not one quarter."""
    mid = quarter_end - timedelta(days=_QUARTER_MIDPOINT_DAYS)
    return f"{mid.year}Q{(mid.month - 1) // 3 + 1}"


def add_calendar_period(panel):
    """Return `panel` with the `period` column used for time fixed effects.

    `quarter_end` holds fiscal quarter-end dates in a real panel and is mapped
    onto the shared calendar grid. Values that are not dates are passed through
    unchanged: a synthetic panel may label periods directly ('q00', 'q01'), and
    such labels are already a common grid, so there is nothing to align."""
    import pandas as pd

    out = panel.copy()
    try:
        ends = pd.to_datetime(out["quarter_end"])
    except (ValueError, TypeError):
        out["period"] = out["quarter_end"].astype(str)
        return out
    out["period"] = [calendar_period(d.date()) for d in ends]
    return out


_FE_DIMENSIONS = ("firm", "period")


def drop_singletons(frame, dimensions: tuple[str, ...] = _FE_DIMENSIONS):
    """Iteratively drop observations that are alone in a fixed-effect group,
    repeating across dimensions until none remain. Returns (frame, n_dropped).

    Correia (2015), 'Singletons, Cluster-Robust Standard Errors and Fixed
    Effects: A Bad Mix' (Duke technical note; the procedure `reghdfe` applies by
    default). A singleton group has no within-group variation, so its fixed
    effect fits its lone observation exactly: it contributes nothing to the
    coefficient estimates, and dropping it leaves them unchanged. What it does
    change is inference -- retaining singletons inflates the small-sample
    correction and understates clustered standard errors, overstating
    significance precisely when fixed effects are nested within clusters, which
    is the case here (firm effects nested in firm clusters).

    Dropping must be iterative because removing a singleton in one dimension can
    strand an observation as a singleton in another.

    In this panel the binding case is Hortonworks: it delisted in 2018Q3, before
    MongoDB's panel opens in 2019Q2, so it shares no period with any other firm.
    Every one of its observations is alone in its period, its firm dummy is an
    exact sum of its own period dummies, and the design matrix is rank-deficient
    as a result. Those rows cannot identify the coefficient of interest under
    two-way fixed effects no matter how many of them there are; keeping them
    only made the standard errors look better than the data supports."""
    dropped = 0
    while True:
        before = len(frame)
        for dimension in dimensions:
            if dimension not in frame.columns:
                continue
            counts = frame[dimension].map(frame[dimension].value_counts())
            frame = frame[counts > 1]
        if len(frame) == before:
            break
        dropped += before - len(frame)
    return frame, dropped


def _rank_check(fit, label: str) -> None:
    """Refuse to report a fit whose design matrix is rank-deficient.

    A rank-deficient design still 'estimates': statsmodels returns finite-looking
    numbers via the pseudo-inverse, with arbitrary coefficients along the null
    space and NaN standard errors. Those are not results, and reporting them as
    if they were is the failure mode this guard exists to prevent."""
    import numpy as np

    exog = np.asarray(fit.model.exog, dtype=float)
    rank = np.linalg.matrix_rank(exog)
    if rank < exog.shape[1]:
        raise ValueError(
            f"{label}: design matrix is rank-deficient ({rank} of "
            f"{exog.shape[1]} columns independent). Coefficients along the "
            f"null space are arbitrary and standard errors are undefined. "
            f"This usually means a firm's fixed effect is collinear with its "
            f"time dummies because no other firm is observed in those periods.")


# Webb's six-point weight distribution: +/-sqrt(1/2), +/-1, +/-sqrt(3/2), each
# with probability 1/6. The square roots are not decoration -- they make
# E[w] = 0 and E[w^2] = (0.5 + 1 + 1.5) * 2/6 = 1, which the weights must
# satisfy. The rounded values (+/-0.5, +/-1, +/-1.5) that circulate in informal
# summaries give E[w^2] = 7/6 and are not a valid wild bootstrap weight
# distribution.
_WEBB_POINTS = (-(1.5 ** 0.5), -1.0, -(0.5 ** 0.5), 0.5 ** 0.5, 1.0, 1.5 ** 0.5)

# Below this cluster count, Rademacher weights are too coarse and Webb weights
# are used instead. Webb (2023), 'Reworking wild bootstrap-based inference for
# clustered errors', Canadian Journal of Economics; the same threshold Stata's
# `wildbootstrap` applies (Webb at G <= 12, Rademacher at G >= 13).
_WEBB_MAX_CLUSTERS = 12
_DEFAULT_DRAWS = 9999


def wild_cluster_pvalue(model_formula: str, data, param: str, groups,
                        draws: int = _DEFAULT_DRAWS, seed: int = 20260812) -> dict:
    """Wild cluster bootstrap-t p-value for H0: coefficient on `param` == 0.

    Cameron, Gelbach & Miller (2008), 'Bootstrap-Based Improvements for
    Inference with Clustered Errors', ReStat 90(3). Uses the RESTRICTED (WCR)
    variant -- residuals are taken from the model with the null imposed -- which
    that literature finds better-behaved with few clusters than the unrestricted
    form.

    WEIGHTS: Webb's six-point distribution at 12 or fewer clusters, Rademacher
    above. This choice is not cosmetic at this panel's size. Rademacher weights
    are two-point, so with G clusters they admit only 2^G distinct draws, and
    the statistic is symmetric under flipping all of them -- at G = 5 that
    leaves 16 usable draws and a smallest attainable p-value of 1/17 = 0.059.
    A 5% test would then have ZERO power against any effect whatsoever, which is
    a property of the weight distribution rather than of the data. Webb's six
    points give 6^G draws (7,776 at G = 5), restoring a usable p-value grid.
    Webb (2023) and Stata's `wildbootstrap` both switch at G <= 12.

    Why this is the headline test rather than a footnote: asymptotic
    cluster-robust standard errors are justified as the number of clusters grows,
    and this panel has a handful of firms. At that count the sandwich estimator
    is badly biased downward and its rank is capped at G-1, so its t-statistics
    reject far too often. The bootstrap re-derives the null distribution of the
    t-statistic from the data instead of assuming it.

    The returned `min_attainable_p` states the resulting floor explicitly, so a
    null can be read against what the procedure could ever have detected.

    The resampling itself runs in closed form rather than through repeated
    formula fits: at 9,999 draws per model the statsmodels path costs minutes
    per hypothesis, and the design matrix never changes between draws -- only
    the outcome does. `panel/power.py` holds the vectorised kernel, and
    `test_panel_power.py` asserts it reproduces the statsmodels p-value and
    differs in t only by the finite-sample correction, which cancels in the
    bootstrap ratio."""
    import numpy as np
    import pandas as pd
    import statsmodels.formula.api as smf

    from git_due_diligence.panel.power import _bootstrap_p, _design

    groups = pd.Series(groups).reset_index(drop=True)
    data = data.reset_index(drop=True)
    codes, _ = pd.factorize(groups)
    n_clusters = int(codes.max()) + 1

    # One statsmodels fit, for the reported coefficient and standard error --
    # these are what appear in the summary tables, so they carry the same
    # finite-sample correction as the rest of the table.
    unrestricted = smf.ols(model_formula, data=data).fit(
        cov_type="cluster", cov_kwds={"groups": groups})
    beta = float(unrestricted.params[param])
    se = float(unrestricted.bse[param])
    t_observed = beta / se if se > 0 and np.isfinite(se) else np.nan

    webb = n_clusters <= _WEBB_MAX_CLUSTERS
    points = np.array(_WEBB_POINTS if webb else (-1.0, 1.0))

    y, X, param_index, _ = _design(data, model_formula, param, cluster_col=None,
                                   codes=codes)
    gram_inverse = np.linalg.pinv(X.T @ X)
    projector = gram_inverse @ X.T
    leverage = X @ gram_inverse[:, param_index]
    _, restricted_X, _, _ = _design(
        data, _drop_term(model_formula, param), "Intercept",
        cluster_col=None, codes=codes)
    restricted_projector = np.linalg.pinv(restricted_X.T @ restricted_X) @ restricted_X.T

    p_value = _bootstrap_p(y, X, projector, leverage, codes, param_index,
                           n_clusters, restricted_projector, restricted_X,
                           points, np.random.default_rng(seed), draws)
    replications = draws

    return {
        "param": param,
        "coefficient": beta,
        "t_observed": t_observed,
        "p_value": p_value,
        "n_clusters": n_clusters,
        "replications": replications,
        "weights": "webb" if webb else "rademacher",
        # The smallest p this procedure can return, given the +1 correction:
        # every replication would have to fall below the observed statistic.
        # Report it beside the p-value so a null can be read against what the
        # test could ever have detected.
        "min_attainable_p": 1.0 / (replications + 1),
    }


def _drop_term(formula: str, term: str) -> str:
    """Remove one additive right-hand-side term, imposing that its coefficient
    is zero."""
    lhs, rhs = formula.split("~", 1)
    kept = [t.strip() for t in rhs.split("+") if t.strip() != term]
    return f"{lhs.strip()} ~ {' + '.join(kept)}"


def run_regressions(panel, output_dir: Path,
                    index_col: str = "repo_health_index_z",
                    bootstrap: bool = True) -> dict:
    import statsmodels.formula.api as smf

    n_firms = panel["firm"].nunique() if "firm" in panel.columns else 0
    if n_firms < _MIN_FIRMS:
        raise ValueError(
            f"panel has {n_firms} firm(s); firm fixed effects with firm-clustered "
            f"standard errors require at least {_MIN_FIRMS}. Add more firms to "
            f"panel/universe/ and rebuild.")

    output_dir.mkdir(parents=True, exist_ok=True)
    results: dict = {}
    diagnostics: dict = {}
    boot_rows: list[dict] = []

    panel = add_calendar_period(panel)
    base_cols = [index_col, "growth_yoy", "op_margin_ltm", "log_rev"]

    h1_formula = f"log_ev_rev ~ {index_col} + {_CONTROLS} + {_FIXED_EFFECTS}"
    h1_data = panel.dropna(subset=["log_ev_rev", *base_cols])
    h1_data, h1_dropped = drop_singletons(h1_data)
    diagnostics["h1_singletons_dropped"] = h1_dropped
    diagnostics["h1_firms"] = int(h1_data["firm"].nunique())
    diagnostics["h1_observations"] = int(len(h1_data))
    h1 = smf.ols(h1_formula, data=h1_data).fit(
        cov_type="cluster", cov_kwds={"groups": h1_data["firm"]})
    _rank_check(h1, "h1")
    results["h1"] = h1
    (output_dir / "h1_pricing.txt").write_text(h1.summary().as_text(), encoding="utf-8")
    if bootstrap:
        boot_rows.append({"model": "h1"} | wild_cluster_pvalue(
            h1_formula, h1_data, index_col, h1_data["firm"]))

    panel = panel.sort_values(["firm", "quarter_end"]).copy()
    for k in _H2_HORIZONS:
        outcome = f"growth_fwd_{k}"
        panel[outcome] = panel.groupby("firm")["growth_yoy"].shift(-k)
        sub = panel.dropna(subset=[outcome, *base_cols])
        sub, _ = drop_singletons(sub)
        if len(sub) < _MIN_ROWS:
            continue
        formula = f"{outcome} ~ {index_col} + {_CONTROLS} + {_FIXED_EFFECTS}"
        h2 = smf.ols(formula, data=sub).fit(
            cov_type="cluster", cov_kwds={"groups": sub["firm"]})
        _rank_check(h2, f"h2_k{k}")
        results[f"h2_k{k}"] = h2
        (output_dir / f"h2_growth_fwd_{k}.txt").write_text(
            h2.summary().as_text(), encoding="utf-8")
        if bootstrap:
            boot_rows.append({"model": f"h2_k{k}"} | wild_cluster_pvalue(
                formula, sub, index_col, sub["firm"]))

    if boot_rows:
        import pandas as pd

        frame = pd.DataFrame(boot_rows)
        frame.to_csv(output_dir / "wild_cluster_bootstrap.csv", index=False)
        diagnostics["bootstrap"] = frame
    results["diagnostics"] = diagnostics
    return results
