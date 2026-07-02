from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CompCompany:
    name: str
    ev_revenue_multiple: float


@dataclass(frozen=True)
class Assumptions:
    target_name: str
    revenue_low: int
    revenue_mid: int
    revenue_high: int
    revenue_source: str
    comps: list[CompCompany]
    comps_source: str
    dcf_years: int
    growth_bear: float
    growth_base: float
    growth_bull: float
    operating_margin: float
    discount_rate: float
    terminal_growth: float
    engineer_month_usd: float
    retention_package_usd: float
    integration_cost_usd: float
    security_fix_cost_usd: float
    license_discount_per_finding: float
    license_discount_cap: float


def _section(data: dict, name: str) -> dict:
    if name not in data:
        raise ValueError(f"assumptions file missing [{name}] section")
    return data[name]


def _require(section: dict, section_name: str, key: str):
    if key not in section:
        raise ValueError(f"assumptions file missing '{key}' in [{section_name}]")
    return section[key]


def _rate(section: dict, section_name: str, key: str) -> float:
    value = float(_require(section, section_name, key))
    if not 0 < value < 1:
        raise ValueError(
            f"'{key}' in [{section_name}] must be between 0 and 1 exclusive, got {value}"
        )
    return value


def _positive(section: dict, section_name: str, key: str) -> float:
    value = float(_require(section, section_name, key))
    if value <= 0:
        raise ValueError(f"'{key}' in [{section_name}] must be positive, got {value}")
    return value


def load_assumptions(path: Path) -> Assumptions:
    with open(path, "rb") as fh:
        data = tomllib.load(fh)

    target = _section(data, "target")
    revenue = _section(data, "revenue")
    comps_sec = _section(data, "comps")
    dcf = _section(data, "dcf")
    costs = _section(data, "costs")

    low = _positive(revenue, "revenue", "low")
    mid = _positive(revenue, "revenue", "mid")
    high = _positive(revenue, "revenue", "high")
    if not low <= mid <= high:
        raise ValueError(f"revenue must satisfy low <= mid <= high, got {low} / {mid} / {high}")

    raw_comps = _require(comps_sec, "comps", "companies")
    if not raw_comps:
        raise ValueError("'companies' in [comps] must not be empty")
    comps = [CompCompany(str(c["name"]), float(c["ev_revenue_multiple"])) for c in raw_comps]
    for comp in comps:
        if comp.ev_revenue_multiple <= 0:
            raise ValueError(f"comp '{comp.name}' ev_revenue_multiple must be positive")

    discount_rate = _rate(dcf, "dcf", "discount_rate")
    terminal_growth = _rate(dcf, "dcf", "terminal_growth")
    if terminal_growth >= discount_rate:
        raise ValueError(
            f"'terminal_growth' must be below discount_rate, got {terminal_growth} >= {discount_rate}"
        )

    return Assumptions(
        target_name=str(_require(target, "target", "name")),
        revenue_low=round(low),
        revenue_mid=round(mid),
        revenue_high=round(high),
        revenue_source=str(_require(revenue, "revenue", "source")),
        comps=comps,
        comps_source=str(_require(comps_sec, "comps", "source")),
        dcf_years=int(_positive(dcf, "dcf", "years")),
        growth_bear=_rate(dcf, "dcf", "growth_bear"),
        growth_base=_rate(dcf, "dcf", "growth_base"),
        growth_bull=_rate(dcf, "dcf", "growth_bull"),
        operating_margin=_rate(dcf, "dcf", "operating_margin"),
        discount_rate=discount_rate,
        terminal_growth=terminal_growth,
        engineer_month_usd=_positive(costs, "costs", "engineer_month_usd"),
        retention_package_usd=_positive(costs, "costs", "retention_package_usd"),
        integration_cost_usd=_positive(costs, "costs", "integration_cost_usd"),
        security_fix_cost_usd=_positive(costs, "costs", "security_fix_cost_usd"),
        license_discount_per_finding=_rate(costs, "costs", "license_discount_per_finding"),
        license_discount_cap=_rate(costs, "costs", "license_discount_cap"),
    )
