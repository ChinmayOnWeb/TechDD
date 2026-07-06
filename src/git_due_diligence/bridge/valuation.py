from __future__ import annotations

import statistics
from dataclasses import dataclass

from git_due_diligence.bridge.assumptions import Assumptions


@dataclass(frozen=True)
class Valuation:
    method: str
    low: int
    mid: int
    high: int


@dataclass(frozen=True)
class YearRow:
    year: int
    revenue: int
    fcf: int
    pv: int


@dataclass(frozen=True)
class DcfScenario:
    name: str
    growth: float
    years: list[YearRow]
    terminal_pv: int
    ev: int


@dataclass(frozen=True)
class SensitivityGrid:
    multiples: list[float]   # rows: min, median, max comp multiple
    revenues: list[int]      # columns: low, mid, high revenue
    pre_dd: list[list[int]]
    post_dd: list[list[int]]


def comps_multiples(a: Assumptions) -> tuple[float, float, float]:
    values = [c.ev_revenue_multiple for c in a.comps]
    return min(values), statistics.median(values), max(values)


def comps_valuation(a: Assumptions) -> Valuation:
    _, median_multiple, _ = comps_multiples(a)
    return Valuation(
        "comps",
        round(a.revenue_low * median_multiple),
        round(a.revenue_mid * median_multiple),
        round(a.revenue_high * median_multiple),
    )


def _scenario(a: Assumptions, name: str, growth: float) -> DcfScenario:
    years: list[YearRow] = []
    revenue = float(a.revenue_mid)
    fcf = 0.0
    ev = 0.0
    for year in range(1, a.dcf_years + 1):
        revenue *= 1 + growth
        fcf = revenue * a.operating_margin
        pv = fcf / (1 + a.discount_rate) ** year
        ev += pv
        years.append(YearRow(year, round(revenue), round(fcf), round(pv)))
    # Gordon terminal value on the final year's FCF, discounted back.
    terminal = fcf * (1 + a.terminal_growth) / (a.discount_rate - a.terminal_growth)
    terminal_pv = terminal / (1 + a.discount_rate) ** a.dcf_years
    ev += terminal_pv
    return DcfScenario(name, growth, years, round(terminal_pv), round(ev))


def dcf_scenarios(a: Assumptions) -> list[DcfScenario]:
    return [
        _scenario(a, "bear", a.growth_bear),
        _scenario(a, "base", a.growth_base),
        _scenario(a, "bull", a.growth_bull),
    ]


def dcf_valuation(a: Assumptions) -> Valuation:
    bear, base, bull = dcf_scenarios(a)
    return Valuation("dcf", bear.ev, base.ev, bull.ev)


def blended_pre_dd_ev_mid(comps: Valuation, dcf: Valuation) -> int:
    """Documented blend: simple mean of the comps and DCF mid estimates."""
    return round((comps.mid + dcf.mid) / 2)


def sensitivity_grid(a: Assumptions, total_adjustment_mid: int) -> SensitivityGrid:
    lo, med, hi = comps_multiples(a)
    multiples = [lo, med, hi]
    revenues = [a.revenue_low, a.revenue_mid, a.revenue_high]
    pre = [[round(m * r) for r in revenues] for m in multiples]
    post = [[cell - total_adjustment_mid for cell in row] for row in pre]
    return SensitivityGrid(multiples, revenues, pre, post)
