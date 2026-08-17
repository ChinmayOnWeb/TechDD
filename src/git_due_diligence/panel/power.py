"""Minimum detectable effect for the Part A panel.

A null result is uninterpretable on its own. "No significant relationship"
means one thing if the design could have detected a coefficient of 0.05 and
something entirely different if it could only ever have detected 0.6. The study
design requires the minimum detectable effect to be stated up front; this module
computes it by simulation against the ACTUAL design matrix, so the answer
reflects this panel's real cluster structure, sample size and collinearity
rather than a textbook formula.

Method: plant a known coefficient in the data-generating process, simulate,
run the same pre-specified wild cluster bootstrap the headline results use, and
record how often it rejects. Power at each effect size is the rejection rate;
the MDE is the smallest effect reaching the target power (conventionally 80%).

The bootstrap is re-implemented here in closed form rather than reusing
`wild_cluster_pvalue`. Power estimation needs replicates x draws fits -- of
order ten million for a single curve -- and the formula-parsing path costs
milliseconds per fit. The linear algebra below is algebraically identical and
runs the whole curve in seconds; `test_panel_power.py` asserts it agrees with
the statsmodels path.
"""
from __future__ import annotations

from dataclasses import dataclass

_DEFAULT_EFFECTS = (0.05, 0.1, 0.15, 0.2, 0.3, 0.4, 0.5, 0.75, 1.0)
_DEFAULT_REPLICATES = 400
_DEFAULT_DRAWS = 499
_TARGET_POWER = 0.80
_ALPHA = 0.05


@dataclass(frozen=True)
class PowerPoint:
    effect: float
    power: float


@dataclass(frozen=True)
class PowerResult:
    curve: tuple[PowerPoint, ...]
    mde: float | None
    target_power: float
    alpha: float
    n_observations: int
    n_clusters: int
    outcome_sd: float

    def as_frame(self):
        import pandas as pd

        return pd.DataFrame([{"effect": p.effect, "power": p.power} for p in self.curve])


def _design(panel, formula: str, param: str, cluster_col: str | None = "firm",
            codes=None):
    """Return (y, X, param column index, cluster codes) for `formula`.

    Pass `codes` when the caller has already factorised the clusters, so both
    the statsmodels and closed-form paths group identically."""
    import numpy as np
    import pandas as pd
    import patsy

    y, X = patsy.dmatrices(formula, panel, return_type="dataframe")
    if param not in X.columns:
        raise ValueError(f"{param} not present in the design matrix")
    if codes is None:
        codes, _ = pd.factorize(panel[cluster_col])
    return (np.asarray(y).ravel(), np.asarray(X, dtype=float),
            list(X.columns).index(param), np.asarray(codes))


def _cluster_t(Y, projector, X, leverage, codes, param_index, n_clusters):
    """Cluster-robust t-statistics on `param_index` for every column of Y.

    Vectorised across simulated outcomes. For a single coefficient the sandwich
    reduces to se^2 = sum_g (sum_{i in g} h_i e_i)^2, where h = X (X'X)^-1 e_j,
    which avoids forming the full covariance matrix per fit.

    The finite-sample correction is omitted deliberately: it depends only on n,
    k and G, which are fixed across replications, so it cancels in the ratio of
    the bootstrap t to the observed t."""
    import numpy as np

    beta = projector @ Y                      # (p, m)
    resid = Y - X @ beta                      # (n, m)
    weighted = leverage[:, None] * resid      # (n, m)
    per_cluster = np.zeros((n_clusters, Y.shape[1]))
    np.add.at(per_cluster, codes, weighted)
    variance = (per_cluster ** 2).sum(axis=0)
    with np.errstate(divide="ignore", invalid="ignore"):
        return beta[param_index] / np.sqrt(variance)


def _bootstrap_p(y, X, projector, leverage, codes, param_index, n_clusters,
                 restricted_projector, restricted_X, weights, rng, draws):
    """Wild cluster bootstrap p-value for one outcome vector."""
    import numpy as np

    t_observed = _cluster_t(y[:, None], projector, X, leverage, codes,
                            param_index, n_clusters)[0]
    if not np.isfinite(t_observed):
        return float("nan")

    restricted_beta = restricted_projector @ y
    fitted = restricted_X @ restricted_beta
    resid = y - fitted

    signs = rng.choice(weights, size=(draws, n_clusters))
    Y = fitted[:, None] + resid[:, None] * signs[:, codes].T
    t_star = _cluster_t(Y, projector, X, leverage, codes, param_index, n_clusters)
    t_star = t_star[np.isfinite(t_star)]
    if not len(t_star):
        return float("nan")
    return float((np.sum(np.abs(t_star) >= abs(t_observed)) + 1) / (len(t_star) + 1))


def power_curve(panel, formula: str, param: str,
                effects: tuple[float, ...] = _DEFAULT_EFFECTS,
                replicates: int = _DEFAULT_REPLICATES,
                draws: int = _DEFAULT_DRAWS,
                alpha: float = _ALPHA,
                target_power: float = _TARGET_POWER,
                seed: int = 20260812) -> PowerResult:
    """Simulated power of the pre-specified bootstrap test across effect sizes."""
    import numpy as np

    from git_due_diligence.panel.regress import (
        _WEBB_MAX_CLUSTERS,
        _WEBB_POINTS,
        _drop_term,
    )

    y, X, param_index, codes = _design(panel, formula, param)
    n_clusters = int(codes.max()) + 1
    weights = np.array(_WEBB_POINTS if n_clusters <= _WEBB_MAX_CLUSTERS
                       else (-1.0, 1.0))

    gram_inverse = np.linalg.pinv(X.T @ X)
    projector = gram_inverse @ X.T
    leverage = X @ gram_inverse[:, param_index]

    _, restricted_X, _, _ = _design(panel, _drop_term(formula, param), "Intercept")
    restricted_projector = np.linalg.pinv(restricted_X.T @ restricted_X) @ restricted_X.T

    # Null-imposed fit of the real data supplies the baseline and the error
    # distribution the simulation resamples, so simulated outcomes inherit this
    # panel's actual residual scale and cluster structure.
    baseline = restricted_X @ (restricted_projector @ y)
    baseline_resid = y - baseline
    index_column = X[:, param_index]

    rng = np.random.default_rng(seed)
    points: list[PowerPoint] = []
    for effect in effects:
        rejections = 0
        usable = 0
        for _ in range(replicates):
            signs = rng.choice(weights, size=n_clusters)
            simulated = (baseline + effect * index_column
                         + baseline_resid * signs[codes])
            p_value = _bootstrap_p(
                simulated, X, projector, leverage, codes, param_index,
                n_clusters, restricted_projector, restricted_X, weights, rng,
                draws)
            if np.isfinite(p_value):
                usable += 1
                rejections += int(p_value <= alpha)
        points.append(PowerPoint(effect, rejections / usable if usable else float("nan")))

    mde = next((p.effect for p in points if p.power >= target_power), None)
    return PowerResult(tuple(points), mde, target_power, alpha,
                       len(y), n_clusters, float(np.std(y, ddof=1)))
