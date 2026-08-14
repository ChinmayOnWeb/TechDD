"""Parse Investing.com historical-price pages saved as PDF.

WRDS/CRSP was unavailable for this project (the accessible subscription is
capped to 2012-2016), and Stooq/Yahoo drop delisted tickers, so the price
history for acquired firms arrived as printed Investing.com pages. This module
recovers a usable series from them.

Two properties of that format need care:

  - **Column order is Price, Open, High, Low** -- the CLOSE comes FIRST, not
    last. Stooq and most CSV feeds order OHLC with the close last, so a
    positional mapping written against that convention silently takes the
    day's OPEN as the close. The error is invisible downstream: prices stay
    plausible and only the valuation drifts.
  - Rows are extracted from a rendered web page, so sidebar content bleeds into
    the right-hand side of a line ("... -0.06% NBIS 259.20 +34.14% 63.54M").
    The parser anchors on the leading date and takes only the fields it
    expects, ignoring trailing debris.

Volumes carry K/M/B suffixes and prices carry thousands separators; both are
normalised. Only date and close are retained -- the panel needs a quarter-end
price level and nothing else.
"""
from __future__ import annotations

import re
from datetime import date, datetime
from pathlib import Path

# "Oct 07, 2021 15.99 15.98 16.00 15.98 13.30M +0.06%"
#  date         close open  high  low   volume  change
_ROW = re.compile(
    r"^(?P<date>[A-Z][a-z]{2} \d{1,2}, \d{4})\s+"
    r"(?P<close>[\d,]+\.?\d*)\s+"
    r"(?P<open>[\d,]+\.?\d*)\s+"
    r"(?P<high>[\d,]+\.?\d*)\s+"
    r"(?P<low>[\d,]+\.?\d*)\s+"
    r"(?P<volume>[\d,.]+[KMB]?|-)\s+"
    r"(?P<change>[+-]?[\d.]+%)"
)


def _parse_price(text: str) -> float:
    return float(text.replace(",", ""))


def parse_rows(text: str) -> list[tuple[date, float]]:
    """Extract (date, close) pairs from one page's extracted text."""
    out: list[tuple[date, float]] = []
    for line in text.splitlines():
        match = _ROW.match(line.strip())
        if not match:
            continue
        try:
            when = datetime.strptime(match.group("date"), "%b %d, %Y").date()
            close = _parse_price(match.group("close"))
        except ValueError:
            continue
        if close <= 0:
            continue
        # Sanity: the close must sit within the day's range. A violation means
        # the columns were misread (e.g. the Stooq ordering assumed), so the
        # row is dropped rather than silently trusted.
        low, high = _parse_price(match.group("low")), _parse_price(match.group("high"))
        if not (low - 1e-9 <= close <= high + 1e-9):
            continue
        out.append((when, close))
    return out


def extract_series(pdf_path: Path) -> list[tuple[date, float]]:
    """Full (date, close) series from an Investing.com PDF, ascending and
    de-duplicated (pages overlap when the table spans a page break)."""
    import pdfplumber

    seen: dict[date, float] = {}
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            for when, close in parse_rows(page.extract_text() or ""):
                seen.setdefault(when, close)
    return sorted(seen.items())
