import math
from datetime import date

import numpy as np
import pytest

from git_due_diligence.panel.assemble import build_panel
from git_due_diligence.panel.edgar import QuarterFundamentals
from git_due_diligence.panel.history import QuarterMetrics
from git_due_diligence.panel.universe import Firm

QUARTERS = [date(2023, 3, 31), date(2023, 6, 30), date(2023, 9, 30), date(2023, 12, 31),
            date(2024, 3, 31), date(2024, 6, 30), date(2024, 9, 30), date(2024, 12, 31)]


def _inputs():
    firm = Firm(slug="acme", name="Acme", ticker="ACME", cik="0000000001",
                repos=("https://example.com/acme.git",),
                fiscal_year_end_month=12, listed_from=date(2023, 1, 1))
    metrics = [QuarterMetrics(
        quarter_end=q, active_contributors=5 + i, top_author_share=0.5 - 0.02 * i,
        contributor_gini=0.6, bus_factor_50=2 + (i % 3), churn_gini=0.7,
        release_cadence=2, merge_share=0.3, commit_volume=100 + 10 * i,
        secret_incidence=0.0,
    ) for i, q in enumerate(QUARTERS)]
    fundamentals = [QuarterFundamentals(
        quarter_end=q, revenue=100.0 + 5 * i, operating_income=10.0,
        cash=50.0, debt=100.0, shares_outstanding=1_000_000.0,
    ) for i, q in enumerate(QUARTERS)]
    prices = {q: 20.0 for q in QUARTERS}
    return firm, metrics, fundamentals, prices


def _panel():
    firm, metrics, fundamentals, prices = _inputs()
    return build_panel([firm], {"acme": metrics}, {"acme": fundamentals}, {"acme": prices})


def test_rows_require_full_ltm_window():
    panel = _panel()
    assert list(panel["quarter_end"]) == [q.isoformat() for q in QUARTERS[3:]]


def test_valuation_columns():
    first = _panel().iloc[0]
    assert first["revenue_ltm"] == 100 + 105 + 110 + 115
    assert first["market_cap"] == 20.0 * 1_000_000
    assert first["net_debt"] == 50.0
    assert first["ev"] == 20.0 * 1_000_000 + 50.0
    assert abs(first["ev_rev"] - first["ev"] / first["revenue_ltm"]) < 1e-9
    assert abs(first["op_margin_ltm"] - 40.0 / 430.0) < 1e-9


def test_growth_needs_eight_matched_quarters():
    panel = _panel()
    assert math.isnan(panel.iloc[0]["growth_yoy"])
    last = panel.iloc[-1]
    assert abs(last["growth_yoy"] - (510 / 430 - 1)) < 1e-9


def test_missing_price_drops_row():
    firm, metrics, fundamentals, prices = _inputs()
    prices[QUARTERS[4]] = None
    panel = build_panel([firm], {"acme": metrics}, {"acme": fundamentals}, {"acme": prices})
    assert QUARTERS[4].isoformat() not in list(panel["quarter_end"])


@pytest.mark.parametrize(("cash", "debt", "expected_net_debt"), [
    (50.0, 100.0, 50.0),
    (0.0, 0.0, 0.0),
    (0.0, 100.0, 100.0),
    (50.0, 0.0, -50.0),
])
def test_reported_cash_and_debt_values_are_used(cash, debt, expected_net_debt):
    firm, metrics, fundamentals, prices = _inputs()
    for row in fundamentals:
        row.cash = cash
        row.debt = debt

    panel = build_panel(
        [firm], {"acme": metrics}, {"acme": fundamentals}, {"acme": prices})

    assert len(panel) == len(QUARTERS) - 3
    assert (panel["net_debt"] == expected_net_debt).all()


@pytest.mark.parametrize(("cash", "debt"), [
    (None, 100.0),
    (50.0, None),
    (None, None),
])
def test_missing_cash_or_debt_drops_observation(cash, debt):
    """Missing balance-sheet facts must not be silently imputed as zero."""
    firm, metrics, fundamentals, prices = _inputs()
    for row in fundamentals:
        row.cash = cash
        row.debt = debt

    panel = build_panel(
        [firm], {"acme": metrics}, {"acme": fundamentals}, {"acme": prices})

    assert panel.empty


def test_health_indices_present_and_standardized():
    panel = _panel()
    assert "repo_health_index_pca" in panel.columns
    assert panel["repo_health_index_z"].iloc[-1] > panel["repo_health_index_z"].iloc[0]


def test_health_index_does_not_change_when_extreme_future_is_appended():
    firm, metrics, fundamentals, prices = _inputs()
    historical = build_panel(
        [firm], {"acme": metrics}, {"acme": fundamentals}, {"acme": prices})

    future_quarters = [date(2025, 3, 31), date(2025, 6, 30), date(2025, 9, 30)]
    future_metrics = [QuarterMetrics(
        quarter_end=q, active_contributors=10_000_000 + i,
        top_author_share=0.999, contributor_gini=0.999,
        bus_factor_50=1_000_000 + i, churn_gini=0.999,
        release_cadence=100_000, merge_share=0.999,
        commit_volume=100_000_000, secret_incidence=10_000.0,
    ) for i, q in enumerate(future_quarters)]
    future_fundamentals = [QuarterFundamentals(
        quarter_end=q, revenue=1_000_000.0, operating_income=1.0,
        cash=0.0, debt=0.0, shares_outstanding=1_000_000.0,
    ) for q in future_quarters]
    extended = build_panel(
        [firm], {"acme": metrics + future_metrics},
        {"acme": fundamentals + future_fundamentals},
        {"acme": prices | {q: 20.0 for q in future_quarters}})

    historical_from_extended = extended[
        extended["quarter_end"] <= QUARTERS[-1].isoformat()]
    assert np.allclose(
        historical["repo_health_index_z"],
        historical_from_extended["repo_health_index_z"],
    )


def test_components_without_a_stable_healthy_direction_are_excluded():
    from git_due_diligence.panel.assemble import INDEX_COMPONENTS
    names = [c for c, _ in INDEX_COMPONENTS]
    assert "release_cadence" not in names       # not comparable across firms
    assert "merge_share" not in names           # workflow, not health
    assert "commit_volume" not in names         # scale control
    assert "contributor_gini" not in names      # sign is scale-dependent
    assert "active_contributors" in names


def test_count_components_log_transformed():
    from git_due_diligence.panel.assemble import _LOG_COMPONENTS
    assert "active_contributors" in _LOG_COMPONENTS
    assert "bus_factor_50" in _LOG_COMPONENTS
    assert "top_author_share" not in _LOG_COMPONENTS   # already a ratio


def test_empty_inputs_yield_empty_frame():
    firm, *_ = _inputs()
    panel = build_panel([firm], {}, {}, {})
    assert panel.empty


def test_exact_filing_backed_zero_retains_only_eligible_endpoint():
    firm, metrics, fundamentals, prices = _inputs()
    fundamentals[4].debt = 0.0
    for index, row in enumerate(fundamentals):
        if index != 4:
            row.debt = None
    panel = build_panel([firm], {"acme": metrics}, {"acme": fundamentals}, {"acme": prices})
    assert list(panel["quarter_end"]) == [QUARTERS[4].isoformat()]


def test_debt_zero_does_not_weaken_cash_requirement():
    firm, metrics, fundamentals, prices = _inputs()
    fundamentals[4].debt = 0.0
    fundamentals[4].cash = None
    panel = build_panel([firm], {"acme": metrics}, {"acme": fundamentals}, {"acme": prices})
    assert QUARTERS[4].isoformat() not in set(panel["quarter_end"])
