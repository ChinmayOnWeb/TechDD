"""CRSP daily-stock ingestion for quarter-end prices.

Stooq and Yahoo drop delisted tickers, but the panel design deliberately
includes acquired/delisted firms for their listed window (that inclusion is
what kills survivorship bias). CRSP retains delisted securities with full
history, so a single CRSP daily export covers every firm in the universe --
live and dead -- from one file.

Expected export: a CSV from WRDS' CRSP Daily Stock File with at least the
columns `date`, `TICKER` (or `PERMNO` plus a ticker column), and `PRC`.
Column names are matched case-insensitively.

CRSP conventions handled here:
  - `PRC` is NEGATIVE when no closing trade occurred and the value is a
    bid/ask midpoint. The magnitude is the price estimate, so we take the
    absolute value rather than dropping or mis-signing the observation.
  - Blank/`C`/`B` price fields mean no valid quote; those rows are skipped.
  - Tickers are normalised to upper case for matching against Firm.ticker.

Only the price series is read here. Delisting returns (DSEDELIST) matter for
return-based studies but not for a quarter-end price level, so they are out of
scope for this loader.
"""
from __future__ import annotations

import csv
from datetime import date
from pathlib import Path


def _norm(name: str) -> str:
    return name.strip().lower()


def _parse_date(raw: str) -> date | None:
    text = raw.strip()
    if not text:
        return None
    # WRDS exports dates as YYYY-MM-DD or the compact CRSP YYYYMMDD form.
    try:
        if len(text) == 8 and text.isdigit():
            return date(int(text[:4]), int(text[4:6]), int(text[6:]))
        return date.fromisoformat(text)
    except ValueError:
        return None


def load_crsp_prices(csv_path: Path) -> dict[str, list[tuple[date, float]]]:
    """Parse a CRSP daily export into {TICKER: [(date, close), ...]} with each
    series sorted ascending. Rows without a usable ticker, date, or price are
    skipped rather than failing the whole load, since CRSP exports routinely
    carry halted/suspended rows."""
    by_ticker: dict[str, list[tuple[date, float]]] = {}
    with csv_path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            return {}
        columns = {_norm(name): name for name in reader.fieldnames}
        ticker_col = columns.get("ticker") or columns.get("tsymbol") or columns.get("symbol")
        date_col = columns.get("date") or columns.get("datadate")
        price_col = columns.get("prc") or columns.get("price") or columns.get("close")
        if not (ticker_col and date_col and price_col):
            raise ValueError(
                f"{csv_path.name}: CRSP export needs ticker, date and price columns; "
                f"found {reader.fieldnames}")
        for row in reader:
            ticker = (row.get(ticker_col) or "").strip().upper()
            when = _parse_date(row.get(date_col) or "")
            raw_price = (row.get(price_col) or "").strip()
            if not ticker or when is None or not raw_price:
                continue
            try:
                price = abs(float(raw_price))   # negative PRC = bid/ask midpoint
            except ValueError:
                continue                        # 'C'/'B' style non-numeric markers
            if price == 0.0:
                continue
            by_ticker.setdefault(ticker, []).append((when, price))
    for series in by_ticker.values():
        series.sort()
    return by_ticker
