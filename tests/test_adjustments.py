from acquirescope.bridge.adjustments import price_adjustments
from acquirescope.bridge.assumptions import Assumptions, CompCompany
from acquirescope.models import Evidence, Finding, ModuleResult, Severity


def _assumptions() -> Assumptions:
    return Assumptions(
        target_name="t",
        revenue_low=1_000_000, revenue_mid=2_000_000, revenue_high=3_000_000,
        revenue_source="test",
        comps=[CompCompany("A", 6.0)],
        comps_source="test",
        dcf_years=1,
        growth_bear=0.25, growth_base=0.50, growth_bull=0.75,
        operating_margin=0.20, discount_rate=0.25, terminal_growth=0.05,
        engineer_month_usd=20_000, retention_package_usd=300_000,
        integration_cost_usd=500_000,
        security_fix_cost_usd=50_000,
        license_discount_per_finding=0.02, license_discount_cap=0.10,
    )


def _results() -> list[ModuleResult]:
    return [
        ModuleResult(
            module="bus_factor", status="ok",
            findings=[
                Finding("bus_factor", "Single point of failure: payments/",
                        Severity.HIGH, "s"),
                Finding("bus_factor", "Key contributor inactive: dave@example.com",
                        Severity.HIGH, "s"),
            ],
        ),
        ModuleResult(
            module="licenses", status="ok",
            findings=[Finding("licenses", "Copyleft dependency: mysqlclient",
                              Severity.HIGH, "s")],
            metrics={"copyleft_dependency_count": 1},
        ),
        ModuleResult(
            module="hotspots", status="ok",
            metrics={"remediation_months_low": 1.0, "remediation_months_mid": 2.0,
                     "remediation_months_high": 3.0, "hotspot_count": 1},
        ),
        ModuleResult(
            module="security", status="ok",
            findings=[Finding("security", "Secret in git history: AWS access key",
                              Severity.CRITICAL, "s")],
            metrics={"secret_count": 1},
        ),
    ]


def test_five_line_items_in_order():
    adjustments = price_adjustments(_results(), _assumptions(), pre_dd_ev_mid=10_000_000)
    assert [a.name for a in adjustments] == [
        "Remediation capex", "Key-person retention", "License-risk discount",
        "Integration cost", "Security remediation",
    ]


def test_remediation_uses_module_band():
    remediation = price_adjustments(_results(), _assumptions(), 10_000_000)[0]
    assert (remediation.low, remediation.mid, remediation.high) == (20_000, 40_000, 60_000)
    assert remediation.assessed


def test_retention_counts_findings():
    retention = price_adjustments(_results(), _assumptions(), 10_000_000)[1]
    assert retention.mid == 600_000          # 2 findings x 300k
    assert retention.low == 300_000
    assert retention.high == 900_000
    assert "dave@example.com" in "; ".join(retention.evidence)


def test_license_discount_fraction_of_ev_with_cap():
    license_adj = price_adjustments(_results(), _assumptions(), 10_000_000)[2]
    assert license_adj.mid == 200_000        # min(1 x 2%, 10%) x 10M
    results = _results()
    results[1].metrics["copyleft_dependency_count"] = 99
    capped = price_adjustments(results, _assumptions(), 10_000_000)[2]
    assert capped.mid == 1_000_000           # capped at 10% x 10M


def test_failed_module_prices_as_not_assessed():
    results = [r for r in _results() if r.module != "hotspots"]
    results.append(ModuleResult(module="hotspots", status="failed", error="boom"))
    remediation = price_adjustments(results, _assumptions(), 10_000_000)[0]
    assert not remediation.assessed
    assert (remediation.low, remediation.mid, remediation.high) == (0, 0, 0)
    assert "Not assessed" in remediation.basis


def test_security_priced_from_critical_and_high_findings():
    security = price_adjustments(_results(), _assumptions(), 10_000_000)[4]
    assert security.assessed
    assert security.mid == 50_000          # 1 CRITICAL finding x 50k
    assert security.low == 25_000
    assert security.high == 75_000
    assert "AWS access key" in "; ".join(security.evidence)


def test_security_not_assessed_when_module_missing():
    results = [r for r in _results() if r.module != "security"]
    security = price_adjustments(results, _assumptions(), 10_000_000)[4]
    assert not security.assessed
    assert security.mid == 0
    assert "Not assessed" in security.basis
