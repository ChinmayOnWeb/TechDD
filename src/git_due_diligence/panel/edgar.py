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
# Some issuers omit the dei.EntityCommonStockSharesOutstanding cover-fact instant
# entirely and only report weighted-average share counts on the income statement.
# We fall back to the basic weighted-average shares (duration fact, keyed by
# period end) when no instant is available.
_SHARES_INSTANT_TAGS = ["EntityCommonStockSharesOutstanding", "CommonStockSharesOutstanding"]
_SHARES_DURATION_FALLBACK_TAGS = [
    "WeightedAverageNumberOfSharesOutstandingBasic",
    "WeightedAverageNumberOfDilutedSharesOutstanding",
    # Singular "Share", not a typo: firms reporting a loss have identical basic
    # and diluted counts and file this combined tag instead. It is what MongoDB
    # used before 2020, and omitting it left every pre-2020 quarter without a
    # share count -- which silently truncated the panel by three years even
    # after the revenue history had been recovered.
    "WeightedAverageNumberOfShareOutstandingBasicAndDiluted",
]
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
    # Date this quarter's revenue FIRST reached the public, i.e. the earliest
    # 10-Q/10-K filing carrying it. Pairing a quarter-end price with revenue
    # that files a median of ~36 days later would use information the market
    # did not have; see `revenue_filed_dates`.
    revenue_filed: date | None = None


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
    """Union of several tags' duration facts, filled in priority order: an
    earlier tag wins for period-ends it covers, later tags fill the rest.

    Selecting the first non-empty tag outright (the previous behaviour) breaks
    on the ASC 606 transition. Revenue recognition changed for fiscal 2018, so
    firms listed before then report early quarters under `SalesRevenueNet` and
    later ones under `RevenueFromContractWithCustomer...`. Taking the first
    non-empty tag returns only the post-2018 fragment and silently discards the
    earlier history -- for Hortonworks that meant 4 quarters instead of 15
    (earliest 2017-06 rather than 2014-03), and MongoDB lost 4 quarters back to
    2016.

    Known limitation: ASC 606 changed *recognition*, so pre- and post-transition
    figures are not perfectly comparable and splicing them leaves a
    methodological seam at fiscal 2018. Firms generally restated comparatives,
    but the superseded tags may carry pre-restatement values. Documented in the
    study design rather than silently smoothed; losing 11 of 15 quarters is
    plainly worse than a documented seam."""
    lo, hi = day_range
    merged: dict[date, float] = {}
    for tag in tags:
        for entry in section.get(tag, {}).get("units", {}).get("USD", []):
            if "start" not in entry or entry.get("form") not in ("10-Q", "10-K"):
                continue
            start = date.fromisoformat(entry["start"])
            end = date.fromisoformat(entry["end"])
            if lo <= (end - start).days <= hi:
                merged.setdefault(end, float(entry["val"]))
    return merged


def revenue_filed_dates(section: dict, tags: list[str],
                        day_range: tuple[int, int] = _QUARTER_DAYS) -> dict[date, date]:
    """Earliest filing date per period end, across the same merged tag set.

    XBRL repeats a fact in every later filing that shows it as a comparative,
    so the same quarter appears with filing dates spanning years. Only the
    EARLIEST matters: that is when the number became public and the market could
    act on it. Taking any other would understate the information lag."""
    lo, hi = day_range
    earliest: dict[date, date] = {}
    for tag in tags:
        for entry in section.get(tag, {}).get("units", {}).get("USD", []):
            if ("start" not in entry or "filed" not in entry
                    or entry.get("form") not in ("10-Q", "10-K")):
                continue
            start = date.fromisoformat(entry["start"])
            end = date.fromisoformat(entry["end"])
            if not (lo <= (end - start).days <= hi):
                continue
            filed = date.fromisoformat(entry["filed"])
            if end not in earliest or filed < earliest[end]:
                earliest[end] = filed
    return earliest


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


def _merged_instant_series(section: dict, tags: list[str], unit: str) -> dict[date, float]:
    """Union of several tags' instant series, filled in priority order: an
    earlier tag's value wins for dates it covers, later tags fill remaining
    dates. Unlike _instant_series (first non-empty tag wins outright), this
    stops a sparse high-priority roll-up (e.g. a single stale LongTermDebt
    point) from shadowing a richer component series (ConvertibleDebtNoncurrent)
    on the dates the roll-up never reports."""
    merged: dict[date, float] = {}
    for tag in tags:
        entries = section.get(tag, {}).get("units", {}).get(unit, [])
        for e in entries:
            if "start" in e:
                continue
            when = date.fromisoformat(e["end"])
            merged.setdefault(when, float(e["val"]))
    return merged


def _shares_series(gaap: dict, dei: dict) -> dict[date, float]:
    """Share counts merged across sources by period end, in priority order.

    The DEI cover-page instant is preferred where present, with weighted-average
    counts filling the rest. Merging rather than taking the first non-empty
    source matters because coverage differs by era, not just by firm: MongoDB
    reports the DEI instant only from 2020 and weighted-average-basic only from
    2021, while its 2016-2019 quarters sit under the combined
    basic-and-diluted tag. Preferring one source outright therefore left three
    years without share counts -- and since the panel requires shares, those
    quarters were dropped even though revenue and prices were available."""
    merged: dict[date, float] = dict(_instant_series(dei, _SHARES_INSTANT_TAGS, "shares"))
    for tag in _SHARES_DURATION_FALLBACK_TAGS:
        for entry in gaap.get(tag, {}).get("units", {}).get("shares", []):
            if entry.get("form") not in ("10-Q", "10-K"):
                continue
            merged.setdefault(date.fromisoformat(entry["end"]), float(entry["val"]))
    return merged


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
    filed = revenue_filed_dates(gaap, _REVENUE_TAGS)
    annual_filed = revenue_filed_dates(gaap, _REVENUE_TAGS, _ANNUAL_DAYS)
    # A derived Q4 becomes public with the 10-K it was backed out of.
    for fy_end, when in annual_filed.items():
        filed.setdefault(fy_end, when)

    cash = _instant_series(gaap, _CASH_TAGS, "USD")
    debt = _merged_instant_series(gaap, _DEBT_TAGS, "USD")
    shares = _shares_series(gaap, dei)

    return [
        QuarterFundamentals(
            quarter_end=q_end,
            revenue=rev,
            operating_income=operating_income.get(q_end),
            cash=_nearest(cash, q_end),
            debt=_nearest(debt, q_end),
            shares_outstanding=_nearest(shares, q_end),
            revenue_filed=filed.get(q_end),
        )
        for q_end, rev in sorted(revenue.items())
    ]
