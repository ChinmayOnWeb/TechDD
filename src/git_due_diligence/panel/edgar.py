from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Callable

EDGAR_COMPANYFACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
USER_AGENT = "git-due-diligence research contact: chinmay.patil1@gmail.com"

_REVENUE_TAGS = [
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "Revenues",
    "SalesRevenueNet",
]
_OPERATING_INCOME_TAGS = ["OperatingIncomeLoss"]
_CASH_TAGS = ["CashAndCashEquivalentsAtCarryingValue"]
_DEBT_TAGS = ["LongTermDebt", "LongTermDebtNoncurrent", "ConvertibleDebtNoncurrent"]
_QUARTER_DAYS = (80, 100)
_ANNUAL_DAYS = (350, 380)
_INSTANT_TOLERANCE_DAYS = 70


@dataclass
class QuarterFundamentals:
    quarter_end: date
    revenue: float
    operating_income: float | None
    cash: float | None
    debt: float | None
    shares_outstanding: float | None


def _default_fetch(url: str) -> str:
    import requests

    response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=60)
    response.raise_for_status()
    return response.text


def fetch_companyfacts(cik: str, cache_dir: Path,
                       fetch: Callable[[str], str] = _default_fetch) -> dict:
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = cache_dir / f"edgar_CIK{cik}.json"
    if not cache_file.exists():
        cache_file.write_text(fetch(EDGAR_COMPANYFACTS_URL.format(cik=cik)), encoding="utf-8")
    return json.loads(cache_file.read_text(encoding="utf-8"))


def _duration_series(section: dict, tags: list[str],
                     day_range: tuple[int, int]) -> dict[date, float]:
    lo, hi = day_range
    for tag in tags:
        entries = section.get(tag, {}).get("units", {}).get("USD", [])
        series: dict[date, float] = {}
        for entry in entries:
            if "start" not in entry or entry.get("form") not in ("10-Q", "10-K"):
                continue
            start = date.fromisoformat(entry["start"])
            end = date.fromisoformat(entry["end"])
            if lo <= (end - start).days <= hi:
                series[end] = float(entry["val"])
        if series:
            return series
    return {}


def _derive_q4(quarterly: dict[date, float], annual: dict[date, float]) -> dict[date, float]:
    merged = dict(quarterly)
    for fy_end, fy_val in annual.items():
        if fy_end in merged:
            continue
        inside = [v for end, v in quarterly.items() if 0 < (fy_end - end).days < 290]
        if len(inside) == 3:
            merged[fy_end] = fy_val - sum(inside)
    return merged


def _instant_series(section: dict, tags: list[str], unit: str) -> dict[date, float]:
    for tag in tags:
        entries = section.get(tag, {}).get("units", {}).get(unit, [])
        series = {
            date.fromisoformat(e["end"]): float(e["val"])
            for e in entries if "start" not in e
        }
        if series:
            return series
    return {}


def _nearest(series: dict[date, float], target: date) -> float | None:
    if not series:
        return None
    best = min(series, key=lambda d: abs((d - target).days))
    if abs((best - target).days) > _INSTANT_TOLERANCE_DAYS:
        return None
    return series[best]


def fetch_fundamentals(cik: str, cache_dir: Path,
                       fetch: Callable[[str], str] = _default_fetch) -> list[QuarterFundamentals]:
    facts = fetch_companyfacts(cik, cache_dir, fetch)
    gaap = facts.get("facts", {}).get("us-gaap", {})
    dei = facts.get("facts", {}).get("dei", {})

    revenue = _derive_q4(
        _duration_series(gaap, _REVENUE_TAGS, _QUARTER_DAYS),
        _duration_series(gaap, _REVENUE_TAGS, _ANNUAL_DAYS),
    )
    operating_income = _derive_q4(
        _duration_series(gaap, _OPERATING_INCOME_TAGS, _QUARTER_DAYS),
        _duration_series(gaap, _OPERATING_INCOME_TAGS, _ANNUAL_DAYS),
    )
    cash = _instant_series(gaap, _CASH_TAGS, "USD")
    debt = _instant_series(gaap, _DEBT_TAGS, "USD")
    shares = _instant_series(dei, ["EntityCommonStockSharesOutstanding"], "shares")

    return [
        QuarterFundamentals(
            quarter_end=q_end,
            revenue=rev,
            operating_income=operating_income.get(q_end),
            cash=_nearest(cash, q_end),
            debt=_nearest(debt, q_end),
            shares_outstanding=_nearest(shares, q_end),
        )
        for q_end, rev in sorted(revenue.items())
    ]
