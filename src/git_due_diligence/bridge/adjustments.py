from __future__ import annotations

from dataclasses import dataclass, field

from git_due_diligence.bridge.assumptions import Assumptions
from git_due_diligence.models import ModuleResult, Severity

BAND = 0.5  # +/-50% band where the source module provides no band of its own


@dataclass(frozen=True)
class Adjustment:
    name: str
    low: int
    mid: int
    high: int
    basis: str
    evidence: list[str] = field(default_factory=list)
    assessed: bool = True


def _banded(mid: float) -> tuple[int, int, int]:
    return round(mid * (1 - BAND)), round(mid), round(mid * (1 + BAND))


def _not_assessed(name: str, reason: str) -> Adjustment:
    return Adjustment(name, 0, 0, 0, f"Not assessed — {reason}", [], False)


def price_adjustments(
    results: list[ModuleResult], assumptions: Assumptions, pre_dd_ev_mid: int
) -> list[Adjustment]:
    by_module = {r.module: r for r in results if r.status == "ok"}
    adjustments: list[Adjustment] = []

    # 1. Remediation capex — the hotspot module already carries its own band.
    hotspots = by_module.get("hotspots")
    if hotspots is None:
        adjustments.append(_not_assessed("Remediation capex", "hotspots module failed or missing"))
    else:
        cost = assumptions.engineer_month_usd
        adjustments.append(Adjustment(
            "Remediation capex",
            round(hotspots.metrics["remediation_months_low"] * cost),
            round(hotspots.metrics["remediation_months_mid"] * cost),
            round(hotspots.metrics["remediation_months_high"] * cost),
            f"remediation engineer-months x ${cost:,.0f}/month loaded cost",
            [f.title for f in hotspots.findings],
        ))

    # 2. Key-person retention — one package per flagged key-person risk.
    bus = by_module.get("bus_factor")
    if bus is None:
        adjustments.append(_not_assessed("Key-person retention", "bus_factor module failed or missing"))
    else:
        count = len(bus.findings)
        low, mid, high = _banded(count * assumptions.retention_package_usd)
        adjustments.append(Adjustment(
            "Key-person retention", low, mid, high,
            f"{count} flagged key-person risk(s) x ${assumptions.retention_package_usd:,.0f} "
            f"retention package, +/-50%",
            [f.title for f in bus.findings],
        ))

    # 3. License-risk discount — fraction of pre-DD EV, capped.
    lic = by_module.get("licenses")
    if lic is None:
        adjustments.append(_not_assessed("License-risk discount", "licenses module failed or missing"))
    else:
        count = lic.metrics["copyleft_dependency_count"]
        fraction = min(count * assumptions.license_discount_per_finding,
                       assumptions.license_discount_cap)
        low, mid, high = _banded(fraction * pre_dd_ev_mid)
        adjustments.append(Adjustment(
            "License-risk discount", low, mid, high,
            f"min({count} copyleft finding(s) x {assumptions.license_discount_per_finding:.0%}, "
            f"cap {assumptions.license_discount_cap:.0%}) of pre-DD EV ${pre_dd_ev_mid:,.0f}, +/-50%",
            [f.title for f in lic.findings if f.severity == Severity.HIGH],
        ))

    # 4. Integration cost — assumption-driven, always assessed.
    low, mid, high = _banded(assumptions.integration_cost_usd)
    adjustments.append(Adjustment(
        "Integration cost", low, mid, high,
        "flat integration estimate from assumptions, +/-50%", [],
    ))

    # 5. Security remediation — priced from CRITICAL/HIGH security findings.
    sec = by_module.get("security")
    if sec is None:
        adjustments.append(_not_assessed("Security remediation", "security module failed or missing"))
    else:
        serious = [f for f in sec.findings if f.severity in (Severity.CRITICAL, Severity.HIGH)]
        low, mid, high = _banded(len(serious) * assumptions.security_fix_cost_usd)
        adjustments.append(Adjustment(
            "Security remediation", low, mid, high,
            f"{len(serious)} critical/high security finding(s) x "
            f"${assumptions.security_fix_cost_usd:,.0f} remediation cost, +/-50%",
            [f.title for f in serious],
        ))

    return adjustments
