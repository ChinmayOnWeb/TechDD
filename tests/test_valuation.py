from git_due_diligence.bridge.assumptions import Assumptions, CompCompany
from git_due_diligence.bridge.valuation import (
    blended_pre_dd_ev_mid,
    comps_valuation,
    dcf_scenarios,
    dcf_valuation,
    sensitivity_grid,
)


def _assumptions() -> Assumptions:
    return Assumptions(
        target_name="t",
        revenue_low=1_000_000, revenue_mid=2_000_000, revenue_high=3_000_000,
        revenue_source="test",
        comps=[
            CompCompany("A", 4.0), CompCompany("B", 6.0), CompCompany("C", 8.0),
        ],
        comps_source="test",
        dcf_years=1,
        growth_bear=0.25, growth_base=0.50, growth_bull=0.75,
        operating_margin=0.20, discount_rate=0.25, terminal_growth=0.05,
        engineer_month_usd=20_000, retention_package_usd=300_000,
        integration_cost_usd=500_000,
        security_fix_cost_usd=50_000,
        license_discount_per_finding=0.02, license_discount_cap=0.10,
    )


def test_comps_valuation_uses_median_multiple():
    v = comps_valuation(_assumptions())
    assert (v.low, v.mid, v.high) == (6_000_000, 12_000_000, 18_000_000)
    assert v.method == "comps"


def test_dcf_valuation_hand_computed():
    v = dcf_valuation(_assumptions())
    assert (v.low, v.mid, v.high) == (2_500_000, 3_000_000, 3_500_000)


def test_dcf_scenario_detail():
    bear, base, bull = dcf_scenarios(_assumptions())
    assert base.name == "base"
    assert base.years[0].revenue == 3_000_000
    assert base.years[0].fcf == 600_000
    assert base.years[0].pv == 480_000
    assert base.terminal_pv == 2_520_000
    assert base.ev == 3_000_000
    assert bear.ev < base.ev < bull.ev


def test_blend_is_mean_of_mids():
    a = _assumptions()
    assert blended_pre_dd_ev_mid(comps_valuation(a), dcf_valuation(a)) == 7_500_000


def test_sensitivity_grid_shape_and_post_dd():
    grid = sensitivity_grid(_assumptions(), total_adjustment_mid=1_000_000)
    assert grid.multiples == [4.0, 6.0, 8.0]
    assert grid.revenues == [1_000_000, 2_000_000, 3_000_000]
    assert grid.pre_dd[1][1] == 12_000_000            # median multiple x mid revenue
    assert grid.post_dd[1][1] == 11_000_000           # pre minus adjustments
    assert all(len(row) == 3 for row in grid.pre_dd)
    assert len(grid.pre_dd) == 3
