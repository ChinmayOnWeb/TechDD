from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Callable

from git_due_diligence.panel.debt_evidence import DebtEvidence, resolve_debt

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
    debt_status: str = "UNRESOLVED"
    debt_concept: str | None = None
    debt_accession: str | None = None


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


def _merged_instant_sources(section: dict, tags: list[str], unit: str) -> dict[date, tuple[str, str | None]]:
    sources: dict[date, tuple[str, str | None]] = {}
    for tag in tags:
        for entry in section.get(tag, {}).get("units", {}).get(unit, []):
            if "start" not in entry:
                sources.setdefault(
                    date.fromisoformat(entry["end"]), (tag, entry.get("accn")))
    return sources


def _nearest_key(series: dict[date, object], target: date) -> date | None:
    if not series:
        return None
    best = min(series, key=lambda d: abs((d - target).days))
    return best if abs((best - target).days) <= _INSTANT_TOLERANCE_DAYS else None


def _shares_series(gaap: dict, dei: dict) -> dict[date, float]:
    """Prefer the DEI instant tag; fall back to a duration-tag (weighted-average
    share count from 10-Q/10-K) keyed by period end when the instant is absent."""
    instant = _instant_series(dei, _SHARES_INSTANT_TAGS, "shares")
    if instant:
        return instant
    for tag in _SHARES_DURATION_FALLBACK_TAGS:
        entries = gaap.get(tag, {}).get("units", {}).get("shares", [])
        series: dict[date, float] = {}
        for entry in entries:
            if entry.get("form") not in ("10-Q", "10-K"):
                continue
            series[date.fromisoformat(entry["end"])] = float(entry["val"])
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


def fetch_fundamentals(
    cik: str,
    cache_dir: Path,
    fetch: Callable[[str], str] = _default_fetch,
    *,
    firm_slug: str | None = None,
    debt_evidence: dict[tuple[str, date], DebtEvidence] | None = None,
) -> list[QuarterFundamentals]:
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
    debt = _merged_instant_series(gaap, _DEBT_TAGS, "USD")
    debt_sources = _merged_instant_sources(gaap, _DEBT_TAGS, "USD")
    shares = _shares_series(gaap, dei)

    rows = []
    for q_end, rev in sorted(revenue.items()):
        reported = _nearest(debt, q_end)
        evidence = debt_evidence.get((firm_slug, q_end)) if debt_evidence and firm_slug else None
        resolved, status = resolve_debt(reported, evidence)
        source_key = _nearest_key(debt_sources, q_end)
        source = debt_sources[source_key] if reported is not None and source_key else (None, None)
        rows.append(QuarterFundamentals(
            quarter_end=q_end,
            revenue=rev,
            operating_income=operating_income.get(q_end),
            cash=_nearest(cash, q_end),
            debt=resolved,
            shares_outstanding=_nearest(shares, q_end),
            debt_status=status,
            debt_concept=source[0],
            debt_accession=source[1] if source[1] else evidence.accession if evidence else None,
        ))
    return rows
