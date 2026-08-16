"""Tests for the estimation-side fixes: a shared time grid, singleton dropping,
the rank guard, and the wild cluster bootstrap."""
from datetime import date

import pandas as pd
import pytest

from git_due_diligence.panel.regress import (
    add_calendar_period,
    calendar_period,
    drop_singletons,
    run_regressions,
    wild_cluster_pvalue,
)


def test_fiscal_calendars_map_onto_a_shared_period_grid():
    """A January-FYE and a December-FYE firm report quarter-ends that never
    coincide. Keyed on the raw date their time dummies are disjoint, so the
    December firm's fixed effect becomes collinear with its own time dummies.
    Mapping by fiscal-quarter midpoint puts both on one grid."""
    # Quarter ending Jan 31 spans Nov-Jan; quarter ending Dec 31 spans Oct-Dec.
    assert calendar_period(date(2022, 1, 31)) == calendar_period(date(2021, 12, 31))
    assert calendar_period(date(2022, 4, 30)) == calendar_period(date(2022, 3, 31))
    assert calendar_period(date(2022, 7, 31)) == calendar_period(date(2022, 6, 30))
    assert calendar_period(date(2022, 10, 31)) == calendar_period(date(2022, 9, 30))
    # and successive quarters remain distinct
    assert calendar_period(date(2022, 1, 31)) != calendar_period(date(2022, 4, 30))


def test_calendar_period_labels_are_the_containing_quarter():
    assert calendar_period(date(2021, 12, 31)) == "2021Q4"
    assert calendar_period(date(2022, 1, 31)) == "2021Q4"
    assert calendar_period(date(2016, 6, 30)) == "2016Q2"


def _frame(rows):
    return pd.DataFrame(rows)


def test_drop_singletons_removes_a_firm_that_shares_no_period():
    """A firm observed only in periods no other firm occupies is absorbed by the
    two-way fixed effects and identifies nothing."""
    frame = _frame(
        [{"firm": "a", "period": f"2020Q{i}"} for i in (1, 2, 3)]
        + [{"firm": "b", "period": f"2020Q{i}"} for i in (1, 2, 3)]
        # 'lonely' sits in periods nobody else reaches
        + [{"firm": "lonely", "period": f"2016Q{i}"} for i in (1, 2, 3)]
    )
    kept, dropped = drop_singletons(frame)
    assert dropped == 3
    assert set(kept["firm"]) == {"a", "b"}


def test_drop_singletons_iterates_until_stable():
    """Removing a period singleton can strand its firm as a firm singleton, so
    one pass is not enough."""
    frame = _frame([
        {"firm": "a", "period": "2020Q1"},
        {"firm": "b", "period": "2020Q1"},
        {"firm": "a", "period": "2020Q2"},
        {"firm": "b", "period": "2020Q2"},
        # 'solo' has one row, alone in its period too: both dimensions
        {"firm": "solo", "period": "1999Q1"},
    ])
    kept, dropped = drop_singletons(frame)
    assert dropped == 1
    assert "solo" not in set(kept["firm"])
    # a second call is a no-op: the result is stable
    again, dropped_again = drop_singletons(kept)
    assert dropped_again == 0
    assert len(again) == len(kept)


def _panel(n_firms=5, n_periods=8, effect=0.0, seed=0):
    """Balanced synthetic panel; `effect` is the true coefficient on the index."""
    import numpy as np

    rng = np.random.default_rng(seed)
    rows = []
    for f in range(n_firms):
        for p in range(n_periods):
            index = rng.normal()
            rows.append({
                "firm": f"firm{f}",
                "quarter_end": pd.Timestamp(2020, 1, 31)
                + pd.DateOffset(months=3 * p),
                "repo_health_index_z": index,
                "growth_yoy": rng.normal(),
                "op_margin_ltm": rng.normal(),
                "log_rev": rng.normal(),
                "log_ev_rev": effect * index + rng.normal(scale=0.3) + f,
            })
    frame = pd.DataFrame(rows)
    frame["quarter_end"] = frame["quarter_end"].dt.date.astype(str)
    return frame


def test_bootstrap_enumerates_exactly_and_reports_the_p_value_floor():
    """With few clusters the test enumerates all 2^(G-1) sign vectors rather
    than sampling, and the smallest p it can return is bounded by that count."""
    data = add_calendar_period(_panel(n_firms=5))
    result = wild_cluster_pvalue(
        "log_ev_rev ~ repo_health_index_z + growth_yoy + op_margin_ltm + log_rev "
        "+ C(firm) + C(period)",
        data, "repo_health_index_z", data["firm"])
    assert result["exact_enumeration"] is True
    assert result["n_clusters"] == 5
    assert result["replications"] == 2 ** 4      # first cluster's sign fixed
    assert result["min_attainable_p"] == pytest.approx(1 / 17)
    assert 0.0 < result["p_value"] <= 1.0


def test_bootstrap_separates_a_real_effect_from_no_effect():
    """A large true coefficient must yield a smaller p-value than pure noise.
    This is the sanity check that the resampling is wired the right way round --
    an inverted sign or a mis-imposed null would break it."""
    formula = ("log_ev_rev ~ repo_health_index_z + growth_yoy + op_margin_ltm "
               "+ log_rev + C(firm) + C(period)")
    # Eight clusters, so the enumeration floor is 1/129 and a 0.05 threshold
    # sits well above it. At six clusters the attainable p-values are multiples
    # of 1/33 and the smallest is 0.030, which would make the assertion a test
    # of the discreteness floor rather than of the effect.
    null = add_calendar_period(_panel(n_firms=8, n_periods=10, effect=0.0, seed=1))
    strong = add_calendar_period(_panel(n_firms=8, n_periods=10, effect=3.0, seed=1))
    p_null = wild_cluster_pvalue(formula, null, "repo_health_index_z",
                                 null["firm"])["p_value"]
    p_strong = wild_cluster_pvalue(formula, strong, "repo_health_index_z",
                                   strong["firm"])["p_value"]
    assert p_strong < p_null
    assert p_strong <= 0.05


def test_singleton_dropping_leaves_coefficients_unchanged():
    """Correia (2015): singletons carry no within-group variation, so removing
    them changes inference but must NOT move the point estimates."""
    base = _panel(n_firms=5, n_periods=8, effect=0.8, seed=3)
    # add a firm observed only in periods nobody else reaches
    orphan = _panel(n_firms=1, n_periods=3, effect=0.8, seed=9)
    orphan["firm"] = "orphan"
    orphan["quarter_end"] = ["2005-01-31", "2005-04-30", "2005-07-31"]

    with_orphan = pd.concat([base, orphan], ignore_index=True)
    only_base = run_regressions(base, __import__("pathlib").Path("/tmp/_p1"),
                                bootstrap=False)
    combined = run_regressions(with_orphan, __import__("pathlib").Path("/tmp/_p2"),
                               bootstrap=False)
    assert combined["diagnostics"]["h1_singletons_dropped"] == 3
    assert (combined["h1"].params["repo_health_index_z"]
            == pytest.approx(only_base["h1"].params["repo_health_index_z"]))


def test_rank_deficient_design_is_rejected_not_reported():
    """The failure this guards against returned coefficients of ~1e10 with NaN
    standard errors and an R^2 of 0.95, all of it collinearity. It must raise
    rather than emit numbers that look like results."""
    import git_due_diligence.panel.regress as regress

    base = _panel(n_firms=4, n_periods=6, effect=0.5, seed=5)
    orphan = _panel(n_firms=1, n_periods=4, effect=0.5, seed=7)
    orphan["firm"] = "orphan"
    orphan["quarter_end"] = ["2005-01-31", "2005-04-30", "2005-07-31", "2005-10-31"]
    frame = pd.concat([base, orphan], ignore_index=True)

    # Bypass singleton dropping to recreate the degenerate design directly.
    original = regress.drop_singletons
    regress.drop_singletons = lambda f, dimensions=None: (f, 0)
    try:
        with pytest.raises(ValueError, match="rank-deficient"):
            run_regressions(frame, __import__("pathlib").Path("/tmp/_p3"),
                            bootstrap=False)
    finally:
        regress.drop_singletons = original
