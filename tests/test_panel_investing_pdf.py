from datetime import date

from git_due_diligence.panel.investing_pdf import parse_rows

PAGE = """\
Cloudera Inc (CLDR)
Date Price Open High Low Vol. Change %
Oct 07, 2021 15.99 15.98 16.00 15.98 13.30M +0.06%
Oct 06, 2021 15.98 15.98 15.99 15.98 1.46M -0.06%
Oct 04, 2021 15.98 15.97 15.99 15.97 4.85M -0.06% NBIS 259.20 +34.14% 63.54M
Sep 30, 2021 15.97 15.97 15.99 15.96 7.13M -0.06% Top Brokers
55% OFF: August Sale Sign In / Free Sign Up
"""


def test_close_is_the_first_numeric_column_not_the_fourth():
    """Investing.com orders columns Price, Open, High, Low -- the CLOSE comes
    FIRST. A parser written against the Stooq convention (close last) would
    silently return the day's LOW as the close."""
    rows = dict(parse_rows(PAGE))
    assert rows[date(2021, 10, 7)] == 15.99      # Price column
    assert rows[date(2021, 10, 6)] == 15.98


def test_sidebar_debris_after_the_row_is_ignored():
    rows = dict(parse_rows(PAGE))
    assert rows[date(2021, 10, 4)] == 15.98      # "NBIS 259.20 ..." trailing junk
    assert rows[date(2021, 9, 30)] == 15.97      # "Top Brokers" trailing junk


def test_page_chrome_produces_no_rows():
    assert parse_rows("55% OFF: August Sale\nAdd to Watchlist\nMarkets News") == []


def test_thousands_separators_parsed():
    rows = dict(parse_rows("Jan 03, 2022 1,234.50 1,230.00 1,240.00 1,229.00 2.10M +0.5%"))
    assert rows[date(2022, 1, 3)] == 1234.50


def test_row_is_dropped_when_close_falls_outside_the_day_range():
    """A close outside [low, high] means the columns were misread. Dropping is
    safer than trusting: a mis-mapped price stays plausible and would corrupt
    the valuation invisibly."""
    bad = "Oct 07, 2021 99.99 15.98 16.00 15.98 13.30M +0.06%"
    assert parse_rows(bad) == []


def test_close_equal_to_range_bounds_is_kept():
    assert dict(parse_rows("Oct 07, 2021 16.00 15.98 16.00 15.98 1M +0.1%"))[
        date(2021, 10, 7)] == 16.00
    assert dict(parse_rows("Oct 07, 2021 15.98 15.99 16.00 15.98 1M +0.1%"))[
        date(2021, 10, 7)] == 15.98


def test_missing_volume_dash_is_tolerated():
    rows = dict(parse_rows("Oct 07, 2021 15.99 15.98 16.00 15.98 - +0.06%"))
    assert rows[date(2021, 10, 7)] == 15.99
