import math
from datetime import date

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
        cash=50.0, debt=None, shares_outstanding=1_000_000.0,
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
    assert first["net_debt"] == -50.0
    assert first["ev"] == 20.0 * 1_000_000 - 50.0
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


def test_health_indices_present_and_standardized():
    panel = _panel()
    assert abs(panel["repo_health_index_z"].mean()) < 1e-9
    assert "repo_health_index_pca" in panel.columns
    assert panel["repo_health_index_z"].iloc[-1] > panel["repo_health_index_z"].iloc[0]


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
