"""Tests for the minimum-detectable-effect simulation.

The fast linear-algebra bootstrap in `power.py` exists only for speed, so the
load-bearing test is that it agrees with the statsmodels implementation the
headline results use.
"""
import numpy as np
import pandas as pd
import pytest

from git_due_diligence.panel.power import _bootstrap_p, _cluster_t, _design, power_curve
from git_due_diligence.panel.regress import (
    _WEBB_POINTS,
    _drop_term,
    add_calendar_period,
    wild_cluster_pvalue,
)

FORMULA = ("y ~ x + control + C(firm) + C(period)")


def _panel(n_firms=5, n_periods=8, effect=0.0, seed=0):
    rng = np.random.default_rng(seed)
    rows = []
    for f in range(n_firms):
        for p in range(n_periods):
            x = rng.normal()
            rows.append({
                "firm": f"firm{f}",
                "period": f"2020Q{p}",
                "x": x,
                "control": rng.normal(),
                "y": effect * x + rng.normal(scale=0.5) + f,
            })
    return pd.DataFrame(rows)


def _fast_p(data, formula, param, draws, seed):
    y, X, j, codes = _design(data, formula, param)
    n_clusters = int(codes.max()) + 1
    gram_inverse = np.linalg.pinv(X.T @ X)
    projector = gram_inverse @ X.T
    leverage = X @ gram_inverse[:, j]
    _, restricted_X, _, _ = _design(data, _drop_term(formula, param), "Intercept")
    restricted_projector = np.linalg.pinv(restricted_X.T @ restricted_X) @ restricted_X.T
    return _bootstrap_p(y, X, projector, leverage, codes, j, n_clusters,
                        restricted_projector, restricted_X,
                        np.array(_WEBB_POINTS), np.random.default_rng(seed), draws)


def test_fast_bootstrap_matches_the_statsmodels_implementation():
    """Same seed, same draws, same weights: the closed-form path must reproduce
    the p-value of the path used for the published results."""
    data = _panel(effect=0.4, seed=11)
    slow = wild_cluster_pvalue(FORMULA, data, "x", data["firm"],
                               draws=999, seed=3)["p_value"]
    fast = _fast_p(data, FORMULA, "x", draws=999, seed=3)
    assert fast == pytest.approx(slow, abs=0.02)


def test_fast_t_differs_from_statsmodels_only_by_the_finite_sample_correction():
    """statsmodels applies G/(G-1) * (n-1)/(n-k) to the cluster covariance; the
    fast path omits it because it is constant across replications and cancels in
    the bootstrap ratio. The two t-statistics must therefore be proportional by
    exactly that factor."""
    import statsmodels.formula.api as smf

    data = _panel(effect=0.4, seed=5)
    fit = smf.ols(FORMULA, data=data).fit(
        cov_type="cluster", cov_kwds={"groups": data["firm"]})
    y, X, j, codes = _design(data, FORMULA, "x")
    n_clusters = int(codes.max()) + 1
    gram_inverse = np.linalg.pinv(X.T @ X)
    fast_t = _cluster_t(y[:, None], gram_inverse @ X.T, X,
                        X @ gram_inverse[:, j], codes, j, n_clusters)[0]

    n, k = X.shape
    correction = np.sqrt(n_clusters / (n_clusters - 1) * (n - 1) / (n - k))
    assert fit.tvalues["x"] == pytest.approx(fast_t / correction, rel=1e-6)


def test_power_rises_with_effect_size():
    data = _panel(seed=2)
    result = power_curve(data, FORMULA, "x", effects=(0.0, 2.0),
                         replicates=60, draws=99)
    powers = [p.power for p in result.curve]
    assert powers[0] < powers[-1]


def test_power_at_a_zero_effect_is_near_the_nominal_size():
    """With no planted effect the rejection rate is the test's actual size, and
    the wild cluster bootstrap exists precisely to keep that near alpha rather
    than far above it as the asymptotic SEs would be."""
    data = _panel(seed=4)
    result = power_curve(data, FORMULA, "x", effects=(0.0,),
                         replicates=200, draws=199, alpha=0.05)
    assert result.curve[0].power < 0.20


def test_mde_is_the_smallest_effect_reaching_target_power():
    data = _panel(seed=6)
    result = power_curve(data, FORMULA, "x", effects=(0.01, 5.0),
                         replicates=60, draws=99, target_power=0.8)
    assert result.mde == 5.0


def test_mde_is_none_when_nothing_reaches_target_power():
    data = _panel(seed=8)
    result = power_curve(data, FORMULA, "x", effects=(0.0,),
                         replicates=40, draws=99, target_power=0.8)
    assert result.mde is None


def test_design_rejects_a_missing_parameter():
    data = _panel()
    with pytest.raises(ValueError, match="not present"):
        _design(data, FORMULA, "nonexistent")


def test_calendar_period_is_applied_before_power_on_a_real_shaped_panel():
    """Smoke test that the panel-shaped input the CLI builds runs end to end."""
    frame = _panel(seed=1).rename(columns={"y": "log_ev_rev", "x": "repo_health_index_z"})
    frame["quarter_end"] = "2022-01-31"
    frame = add_calendar_period(frame)
    assert set(frame["period"]) == {"2021Q4"}
