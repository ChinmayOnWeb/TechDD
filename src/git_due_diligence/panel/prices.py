from __future__ import annotations

from bisect import bisect_right
from datetime import date
from pathlib import Path
from typing import Callable

STOOQ_URL = "https://stooq.com/q/d/l/?s={symbol}&i=d"
USER_AGENT = "git-due-diligence research contact: chinmay.patil1@gmail.com"
_MAX_STALENESS_DAYS = 14


def _default_fetch(url: str) -> str:
    import requests

    response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=60)
    response.raise_for_status()
    return response.text


def _load_closes(ticker: str, cache_dir: Path,
                 fetch: Callable[[str], str]) -> list[tuple[date, float]]:
    symbol = f"{ticker.lower()}.us"
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = cache_dir / f"stooq_{symbol}.csv"
    if not cache_file.exists():
        cache_file.write_text(fetch(STOOQ_URL.format(symbol=symbol)), encoding="utf-8")
    closes: list[tuple[date, float]] = []
    for line in cache_file.read_text(encoding="utf-8").splitlines()[1:]:
        parts = line.split(",")
        if len(parts) < 5:
            continue
        try:
            closes.append((date.fromisoformat(parts[0]), float(parts[4])))
        except ValueError:
            continue
    closes.sort()
    return closes


def quarter_end_prices(ticker: str, dates: list[date], cache_dir: Path,
                       fetch: Callable[[str], str] = _default_fetch) -> dict[date, float | None]:
    closes = _load_closes(ticker, cache_dir, fetch)
    close_dates = [d for d, _ in closes]
    out: dict[date, float | None] = {}
    for target in dates:
        idx = bisect_right(close_dates, target) - 1
        if idx < 0 or (target - close_dates[idx]).days > _MAX_STALENESS_DAYS:
            out[target] = None
        else:
            out[target] = closes[idx][1]
    return out
