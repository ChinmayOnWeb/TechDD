from datetime import date

from git_due_diligence.panel.prices import quarter_end_prices

CANNED_CSV = """Date,Open,High,Low,Close,Volume
2024-04-29,50,51,49,50.5,1000
2024-04-30,51,52,50,51.25,1200
2024-07-30,55,56,54,55.5,900
"""


def test_last_close_on_or_before_each_date(tmp_path):
    calls: list[str] = []

    def fake_fetch(url: str) -> str:
        calls.append(url)
        return CANNED_CSV

    prices = quarter_end_prices(
        "GTLB", [date(2024, 4, 30), date(2024, 7, 31), date(2024, 10, 31)],
        tmp_path, fetch=fake_fetch,
    )
    assert prices[date(2024, 4, 30)] == 51.25
    assert prices[date(2024, 7, 31)] == 55.5
    assert prices[date(2024, 10, 31)] is None
    assert calls == ["https://stooq.com/q/d/l/?s=gtlb.us&i=d"]


def test_prices_cached_after_first_fetch(tmp_path):
    calls: list[str] = []

    def fake_fetch(url: str) -> str:
        calls.append(url)
        return CANNED_CSV

    quarter_end_prices("GTLB", [date(2024, 4, 30)], tmp_path, fetch=fake_fetch)
    quarter_end_prices("GTLB", [date(2024, 4, 30)], tmp_path, fetch=fake_fetch)
    assert len(calls) == 1
    assert (tmp_path / "stooq_gtlb.us.csv").exists()


def test_malformed_rows_skipped(tmp_path):
    body = CANNED_CSV + "No Data\n,,,,,\n"
    prices = quarter_end_prices("GTLB", [date(2024, 7, 31)], tmp_path,
                                fetch=lambda url: body)
    assert prices[date(2024, 7, 31)] == 55.5
