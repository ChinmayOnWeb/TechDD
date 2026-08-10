import json
from datetime import date

from git_due_diligence.panel.edgar import fetch_fundamentals


def _entry(start: str | None, end: str, val: float, form: str = "10-Q") -> dict:
    e = {"end": end, "val": val, "form": form}
    if start:
        e["start"] = start
    return e


def _canned_facts() -> dict:
    return {
        "cik": 1,
        "facts": {
            "dei": {"EntityCommonStockSharesOutstanding": {"units": {"shares": [
                _entry(None, "2024-05-05", 100_000_000.0),
                _entry(None, "2024-08-02", 101_000_000.0),
                _entry(None, "2024-11-04", 102_000_000.0),
                _entry(None, "2025-03-20", 103_000_000.0, form="10-K"),
            ]}}},
            "us-gaap": {
                "RevenueFromContractWithCustomerExcludingAssessedTax": {"units": {"USD": [
                    _entry("2024-02-01", "2024-04-30", 100.0),
                    _entry("2024-05-01", "2024-07-31", 110.0),
                    _entry("2024-08-01", "2024-10-31", 120.0),
                    _entry("2024-02-01", "2025-01-31", 460.0, form="10-K"),
                ]}},
                "OperatingIncomeLoss": {"units": {"USD": [
                    _entry("2024-02-01", "2024-04-30", 10.0),
                ]}},
                "CashAndCashEquivalentsAtCarryingValue": {"units": {"USD": [
                    _entry(None, "2024-04-30", 50.0),
                    _entry(None, "2024-07-31", 55.0),
                ]}},
            },
        },
    }


def _fake_fetch(calls: list[str]):
    def fetch(url: str) -> str:
        calls.append(url)
        return json.dumps(_canned_facts())
    return fetch


def test_quarterly_revenue_and_derived_q4(tmp_path):
    rows = fetch_fundamentals("0000000001", tmp_path, fetch=_fake_fetch([]))
    assert [r.quarter_end for r in rows] == [
        date(2024, 4, 30), date(2024, 7, 31), date(2024, 10, 31), date(2025, 1, 31),
    ]
    assert [r.revenue for r in rows] == [100.0, 110.0, 120.0, 130.0]


def test_instants_matched_within_tolerance(tmp_path):
    rows = fetch_fundamentals("0000000001", tmp_path, fetch=_fake_fetch([]))
    q1 = rows[0]
    assert q1.cash == 50.0
    assert q1.shares_outstanding == 100_000_000.0
    assert q1.operating_income == 10.0
    assert q1.debt is None
    q4 = rows[3]
    assert q4.shares_outstanding == 103_000_000.0
    assert q4.cash is None
    assert q4.operating_income is None


def test_companyfacts_cached_after_first_fetch(tmp_path):
    calls: list[str] = []
    fetch = _fake_fetch(calls)
    fetch_fundamentals("0000000001", tmp_path, fetch=fetch)
    fetch_fundamentals("0000000001", tmp_path, fetch=fetch)
    assert len(calls) == 1
    assert calls[0] == "https://data.sec.gov/api/xbrl/companyfacts/CIK0000000001.json"
    assert (tmp_path / "edgar_CIK0000000001.json").exists()
