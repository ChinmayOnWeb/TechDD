from datetime import date

import pytest

from git_due_diligence.panel.crsp import load_crsp_prices
from git_due_diligence.panel.prices import quarter_end_prices_from_series

CRSP_CSV = """PERMNO,date,TICKER,PRC,VOL
14593,2024-04-29,GTLB,50.5,1000
14593,2024-04-30,GTLB,-51.25,0
14593,2024-07-30,GTLB,55.5,900
90001,2024-04-30,HCP,88.0,500
90001,2024-07-31,HCP,,0
90001,2024-10-31,HCP,C,0
"""


def _write(tmp_path, body=CRSP_CSV):
    path = tmp_path / "crsp.csv"
    path.write_text(body, encoding="utf-8")
    return path


def test_negative_price_is_bid_ask_midpoint_not_dropped(tmp_path):
    prices = load_crsp_prices(_write(tmp_path))
    gtlb = dict(prices["GTLB"])
    assert gtlb[date(2024, 4, 30)] == 51.25       # abs() of -51.25, not skipped


def test_blank_and_nonnumeric_prices_skipped(tmp_path):
    prices = load_crsp_prices(_write(tmp_path))
    hcp = dict(prices["HCP"])
    assert hcp == {date(2024, 4, 30): 88.0}       # blank and 'C' rows dropped


def test_series_sorted_and_grouped_by_ticker(tmp_path):
    prices = load_crsp_prices(_write(tmp_path))
    assert set(prices) == {"GTLB", "HCP"}
    assert [d for d, _ in prices["GTLB"]] == sorted(d for d, _ in prices["GTLB"])


def test_compact_yyyymmdd_dates_parsed(tmp_path):
    body = CRSP_CSV.replace("2024-04-29", "20240429")
    prices = load_crsp_prices(_write(tmp_path, body))
    assert date(2024, 4, 29) in dict(prices["GTLB"])


def test_missing_required_columns_raises(tmp_path):
    body = "PERMNO,date,VOL\n1,2024-04-30,100\n"
    with pytest.raises(ValueError, match="ticker"):
        load_crsp_prices(_write(tmp_path, body))


def test_delisted_ticker_resolves_quarter_ends_then_goes_none(tmp_path):
    """A firm acquired mid-sample keeps prices through its listed window and
    reports None afterwards -- the behaviour the panel needs for delisted firms."""
    prices = load_crsp_prices(_write(tmp_path))
    resolved = quarter_end_prices_from_series(
        prices["HCP"], [date(2024, 4, 30), date(2024, 7, 31), date(2025, 1, 31)])
    assert resolved[date(2024, 4, 30)] == 88.0
    assert resolved[date(2024, 7, 31)] is None    # >14d stale after last valid quote
    assert resolved[date(2025, 1, 31)] is None
