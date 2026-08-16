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


# Cluster counts at or below this get an EXACT test by enumerating all 2^G sign
# vectors instead of sampling them. With a handful of firms that is a few dozen
# refits -- cheaper than a sampled bootstrap and free of simulation error.
_EXACT_ENUMERATION_MAX_CLUSTERS = 14
_DEFAULT_DRAWS = 9999


def wild_cluster_pvalue(model_formula: str, data, param: str, groups,
                        draws: int = _DEFAULT_DRAWS, seed: int = 20260812) -> dict:
    """Wild cluster bootstrap-t p-value for H0: coefficient on `param` == 0.

    Cameron, Gelbach & Miller (2008), 'Bootstrap-Based Improvements for
    Inference with Clustered Errors', ReStat 90(3). Uses the RESTRICTED (WCR)
    variant -- residuals are taken from the model with the null imposed -- which
    that literature finds better-behaved with few clusters than the unrestricted
    form, and Rademacher weights, which are the recommended default when the
    cluster count is small enough to enumerate.

    Why this is the headline test rather than a footnote: asymptotic
    cluster-robust standard errors are justified as the number of clusters grows,
    and this panel has a handful of firms. At that count the sandwich estimator
    is badly biased downward and its rank is capped at G-1, so its t-statistics
    reject far too often. The bootstrap re-derives the null distribution of the
    t-statistic from the data instead of assuming it.

    HARD LIMIT worth reporting alongside any p-value from this function: with G
    clusters there are only 2^G sign vectors, and the statistic is symmetric
    under flipping all of them, so the smallest attainable p-value is about
    2/2^G. At G=6 that is ~0.031 -- no result can be significant at the 1% level
    no matter how large the effect. That is a property of the design, not of the
    estimate, and the returned `min_attainable_p` states it explicitly."""
    import itertools

    import numpy as np
    import pandas as pd
    import statsmodels.formula.api as smf

    groups = pd.Series(groups).reset_index(drop=True)
    data = data.reset_index(drop=True)
    codes, _ = pd.factorize(groups)
    n_clusters = int(codes.max()) + 1

    def _fit(frame, formula):
        return smf.ols(formula, data=frame).fit(
            cov_type="cluster", cov_kwds={"groups": groups})

    unrestricted = _fit(data, model_formula)
    beta = float(unrestricted.params[param])
    se = float(unrestricted.bse[param])
    t_observed = beta / se if se > 0 and np.isfinite(se) else np.nan

    # Impose the null by dropping the regressor, then resample its residuals.
    restricted_formula = _drop_term(model_formula, param)
    restricted = smf.ols(restricted_formula, data=data).fit()
    fitted = np.asarray(restricted.fittedvalues, dtype=float)
    resid = np.asarray(restricted.resid, dtype=float)
    outcome = model_formula.split("~", 1)[0].strip()

    if n_clusters <= _EXACT_ENUMERATION_MAX_CLUSTERS:
        # Fix the first cluster's sign at +1: the t-statistic is invariant to
        # flipping every weight, so the other half of the 2^G vectors is an
        # exact mirror and contributes nothing.
        sign_vectors = [(1,) + rest for rest in
                        itertools.product((1, -1), repeat=n_clusters - 1)]
        exact = True
    else:
        rng = np.random.default_rng(seed)
        sign_vectors = rng.choice((-1, 1), size=(draws, n_clusters))
        exact = False

    boot = pd.DataFrame(data)
    t_stats: list[float] = []
    for signs in sign_vectors:
        weights = np.asarray(signs, dtype=float)[codes]
        boot[outcome] = fitted + weights * resid
        try:
            fit_b = _fit(boot, model_formula)
            se_b = float(fit_b.bse[param])
            if se_b > 0 and np.isfinite(se_b):
                t_stats.append(float(fit_b.params[param]) / se_b)
        except Exception:
            continue

    t_array = np.abs(np.asarray(t_stats, dtype=float))
    if not len(t_array) or not np.isfinite(t_observed):
        p_value = float("nan")
    else:
        # +1 in numerator and denominator: the observed sample is itself one
        # draw under the null, and omitting it yields p-values that can be 0.
        p_value = float((np.sum(t_array >= abs(t_observed)) + 1) / (len(t_array) + 1))

    return {
        "param": param,
        "coefficient": beta,
        "t_observed": t_observed,
        "p_value": p_value,
        "n_clusters": n_clusters,
        "replications": len(t_array),
        "exact_enumeration": exact,
        # The smallest p this procedure can return, given the +1 correction:
        # every replication would have to fall below the observed statistic.
        # Under exact enumeration the refit count is 2^(G-1), so with 5 clusters
        # the floor is 1/17 ~ 0.059 -- a 1% result is unreachable by
        # construction, however large the true effect.
        "min_attainable_p": 1.0 / (len(t_array) + 1) if len(t_array) else float("nan"),
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
