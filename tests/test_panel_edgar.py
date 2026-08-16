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


def test_shares_falls_back_to_weighted_average_when_dei_missing(tmp_path):
    facts = {"cik": 2, "facts": {
        "dei": {},
        "us-gaap": {
            "Revenues": {"units": {"USD": [
                _entry("2024-02-01", "2024-04-30", 100.0),
                _entry("2024-05-01", "2024-07-31", 110.0),
            ]}},
            "WeightedAverageNumberOfSharesOutstandingBasic": {"units": {"shares": [
                {"start": "2024-02-01", "end": "2024-04-30", "val": 50_000_000, "form": "10-Q"},
                {"start": "2024-05-01", "end": "2024-07-31", "val": 51_000_000, "form": "10-Q"},
            ]}},
        },
    }}
    import json as _json
    rows = fetch_fundamentals("0000000002", tmp_path,
                              fetch=lambda url: _json.dumps(facts))
    assert rows[0].shares_outstanding == 50_000_000.0
    assert rows[1].shares_outstanding == 51_000_000.0


def test_debt_merges_across_tags_priority_fill(tmp_path):
    # A sparse, stale LongTermDebt roll-up must not shadow a richer
    # ConvertibleDebtNoncurrent series on the dates it never reports.
    facts = {"cik": 3, "facts": {"dei": {}, "us-gaap": {
        "RevenueFromContractWithCustomerExcludingAssessedTax": {"units": {"USD": [
            _entry("2024-02-01", "2024-04-30", 100.0),
            _entry("2024-05-01", "2024-07-31", 110.0),
        ]}},
        "EntityCommonStockSharesOutstanding": {"units": {"shares": []}},
        "LongTermDebt": {"units": {"USD": [
            {"end": "2019-01-31", "val": 500.0},           # single stale point
        ]}},
        "ConvertibleDebtNoncurrent": {"units": {"USD": [
            {"end": "2024-04-30", "val": 1000.0},
            {"end": "2024-07-31", "val": 0.0},             # redeemed
        ]}},
    }}}
    import json as _json
    rows = fetch_fundamentals("0000000003", tmp_path, fetch=lambda url: _json.dumps(facts))
    by_end = {r.quarter_end: r for r in rows}
    assert by_end[date(2024, 4, 30)].debt == 1000.0        # from convertible series
    assert by_end[date(2024, 7, 31)].debt == 0.0           # redeemed, not None


def test_revenue_merges_across_the_asc606_tag_transition(tmp_path):
    """Firms listed before fiscal 2018 report early quarters under
    SalesRevenueNet and later ones under RevenueFromContractWithCustomer...,
    because ASC 606 changed revenue recognition. Taking the first non-empty tag
    returns only the post-transition fragment: Hortonworks dropped from 15
    quarters to 4."""
    facts = {"cik": 4, "facts": {"dei": {}, "us-gaap": {
        # priority tag: only the post-606 quarters
        "RevenueFromContractWithCustomerExcludingAssessedTax": {"units": {"USD": [
            _entry("2018-01-01", "2018-03-31", 300.0),
        ]}},
        # superseded tag: the earlier history
        "SalesRevenueNet": {"units": {"USD": [
            _entry("2016-01-01", "2016-03-31", 100.0),
            _entry("2017-01-01", "2017-03-31", 200.0),
            _entry("2018-01-01", "2018-03-31", 999.0),   # overlaps; must NOT win
        ]}},
        "EntityCommonStockSharesOutstanding": {"units": {"shares": []}},
    }}}
    import json as _json
    rows = fetch_fundamentals("0000000004", tmp_path, fetch=lambda url: _json.dumps(facts))
    by_end = {r.quarter_end: r.revenue for r in rows}
    assert by_end[date(2016, 3, 31)] == 100.0       # recovered from the older tag
    assert by_end[date(2017, 3, 31)] == 200.0
    assert by_end[date(2018, 3, 31)] == 300.0       # priority tag wins on overlap
    assert len(rows) == 3


def test_shares_merge_across_eras_not_first_source_wins(tmp_path):
    """Share-count coverage differs by ERA, not just by firm. MongoDB reports
    the DEI instant only from 2020 and weighted-average-basic only from 2021,
    with 2016-2019 under the combined basic-and-diluted tag. Preferring one
    source outright leaves years without share counts, and since the panel
    requires shares those quarters are dropped despite having revenue."""
    facts = {"cik": 5, "facts": {
        "dei": {"EntityCommonStockSharesOutstanding": {"units": {"shares": [
            {"end": "2024-04-30", "val": 90.0},          # recent era only
        ]}}},
        "us-gaap": {
            "RevenueFromContractWithCustomerExcludingAssessedTax": {"units": {"USD": [
                _entry("2018-02-01", "2018-04-30", 100.0),
                _entry("2024-02-01", "2024-04-30", 400.0),
            ]}},
            # the pre-2020 tag: singular "Share", used when basic == diluted
            "WeightedAverageNumberOfShareOutstandingBasicAndDiluted": {
                "units": {"shares": [
                    {"end": "2018-04-30", "val": 50.0, "form": "10-Q"},
                    {"end": "2024-04-30", "val": 99.0, "form": "10-Q"},  # must not win
                ]}},
        },
    }}
    import json as _json
    rows = fetch_fundamentals("0000000005", tmp_path, fetch=lambda url: _json.dumps(facts))
    shares = {r.quarter_end: r.shares_outstanding for r in rows}
    assert shares[date(2018, 4, 30)] == 50.0     # recovered from the era-specific tag
    assert shares[date(2024, 4, 30)] == 90.0     # DEI instant keeps priority


def test_companyfacts_cached_after_first_fetch(tmp_path):
    calls: list[str] = []
    fetch = _fake_fetch(calls)
    fetch_fundamentals("0000000001", tmp_path, fetch=fetch)
    fetch_fundamentals("0000000001", tmp_path, fetch=fetch)
    assert len(calls) == 1
    assert calls[0] == "https://data.sec.gov/api/xbrl/companyfacts/CIK0000000001.json"
    assert (tmp_path / "edgar_CIK0000000001.json").exists()
