from __future__ import annotations

import calendar
import tomllib
from dataclasses import dataclass
from datetime import date
from pathlib import Path

_REQUIRED_KEYS = ("name", "slug", "ticker", "cik", "repos", "fiscal_year_end_month", "listed_from")


# How tightly the firm's flagship repo maps to the whole company's engineering.
# "core": the product essentially IS the open repo (MongoDB, Elastic, GitLab).
# "adjacent": a significant public repo, but it captures only part of the
# value-generating engineering (measurement error in the health regressor is
# larger). Used to run the headline spec on the core subset and the broad panel
# as robustness.
_VALID_TIERS = ("core", "adjacent")


@dataclass(frozen=True)
class Firm:
    slug: str
    name: str
    ticker: str
    cik: str                    # zero-padded 10-digit EDGAR CIK
    repos: tuple[str, ...]
    fiscal_year_end_month: int  # 1-12; GitLab's Jan-31 fiscal year end -> 1
    listed_from: date
    listed_to: date | None = None
    notes: str = ""
    tier: str = "core"          # "core" | "adjacent"; see _VALID_TIERS


def load_universe(directory: Path) -> list[Firm]:
    firms: list[Firm] = []
    for path in sorted(directory.glob("*.toml")):
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
        missing = [k for k in _REQUIRED_KEYS if k not in raw]
        if missing:
            raise ValueError(f"{path.name}: missing required keys: {', '.join(missing)}")
        month = raw["fiscal_year_end_month"]
        if not (isinstance(month, int) and 1 <= month <= 12):
            raise ValueError(f"{path.name}: fiscal_year_end_month must be 1-12, got {month!r}")
        tier = raw.get("tier", "core")
        if tier not in _VALID_TIERS:
            raise ValueError(f"{path.name}: tier must be one of {_VALID_TIERS}, got {tier!r}")
        firms.append(Firm(
            slug=raw["slug"], name=raw["name"], ticker=raw["ticker"],
            cik=str(raw["cik"]).zfill(10),
            repos=tuple(raw["repos"]), fiscal_year_end_month=month,
            listed_from=raw["listed_from"], listed_to=raw.get("listed_to"),
            notes=raw.get("notes", ""), tier=tier,
        ))
    return firms


def fiscal_quarter_ends(fye_month: int, start: date, end: date) -> list[date]:
    """Fiscal quarter-end dates (last day of each quarter-end month implied by
    the fiscal-year-end month) falling within [start, end], ascending."""
    months = sorted({(fye_month - 1 + 3 * k) % 12 + 1 for k in range(4)})
    ends: list[date] = []
    for year in range(start.year, end.year + 1):
        for month in months:
            d = date(year, month, calendar.monthrange(year, month)[1])
            if start <= d <= end:
                ends.append(d)
    return ends
