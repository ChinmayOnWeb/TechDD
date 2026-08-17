"""Part B tests.

The most important tests here are not unit tests of arithmetic. They are audits
of the hand-coded dates in `panel/deals.toml` against the actual price series:
if a date labelled `unaffected` sits on a session that moved 19%, the label is
wrong and the premium built on it is wrong. Those run against the committed
production register, not fixtures, because the register is the research input.
"""
from datetime import date
from pathlib import Path

import pytest

from git_due_diligence.panel.crsp import load_crsp_prices
from git_due_diligence.panel.deals import (Deal, deal_terms, firm_level_exact_test,
                                           load_deals, offer_value, return_profile,
                                           spearman_exact)

REGISTER = Path("panel/deals.toml")
PRICES = Path("panel_cache/prices_delisted.csv")


@pytest.fixture(scope="module")
def prices():
    return {t: dict(s) for t, s in load_crsp_prices(PRICES).items()}


@pytest.fixture(scope="module")
def register():
    return load_deals(REGISTER)


def _deal(register, slug):
    return next(d for d in register if d.slug == slug)


# --- audits of the register against the tape -------------------------------

def test_every_deal_has_a_price_series_covering_its_window(register, prices):
    for deal in register:
        series = prices.get(deal.ticker.upper())
        assert series, f"{deal.ticker}: no price series"
        assert min(series) <= deal.unaffected, f"{deal.ticker}: series starts too late"
        assert max(series) >= deal.first_affected, f"{deal.ticker}: series ends too early"


def test_the_session_labelled_unaffected_moved_quietly(register, prices):
    """If the 'last close that cannot embed the news' jumped, it embedded the
    news and the premium denominator is contaminated. This is the check that
    caught HashiCorp: Bloomberg broke the story the day BEFORE the official
    announcement and the stock closed +18.7%, so the conventional
    day-before-announcement denominator was already an affected price."""
    for deal in register:
        profile = {d: r for d, _, r in return_profile(deal, prices)}
        move = profile.get(deal.unaffected)
        assert move is not None, f"{deal.ticker}: unaffected date not a trading session"
        assert abs(move) < 0.08, (
            f"{deal.ticker}: session labelled unaffected ({deal.unaffected}) "
            f"moved {move:+.1%} -- it is not unaffected")


def test_the_session_labelled_first_affected_actually_repriced(register, prices):
    """The converse. Every deal in this sample repriced the target by at least
    11% on its first affected session, so a quiet 'first affected' day would
    mean the date is wrong."""
    for deal in register:
        profile = {d: r for d, _, r in return_profile(deal, prices)}
        move = profile.get(deal.first_affected)
        assert move is not None and move > 0.10, (
            f"{deal.ticker}: session labelled first_affected ({deal.first_affected}) "
            f"moved {move:+.2%}, which is not a deal reprice")


def test_completion_dates_line_up_with_the_end_of_each_price_series(register, prices):
    """An independent check on the register: a completed take-private stops
    trading, so the last close must sit within a few sessions of the completion
    date. All five reconcile, which is a check on the price data and the deal
    dates simultaneously."""
    for deal in register:
        if deal.completed is None:
            continue
        last = max(prices[deal.ticker.upper()])
        gap = (deal.completed - last).days
        assert 0 <= gap <= 5, (
            f"{deal.ticker}: last close {last} vs completion {deal.completed} ({gap}d)")


def test_premiums_reconcile_with_the_figures_in_the_press_releases(register, prices):
    """Each issuer stated a premium. Recomputing it from the tape is how we know
    the dates and the price series agree with the filing."""
    expected = {           # slug -> premium claimed by the issuer, +/- 1pp
        "cloudera": 0.24,      # "24% premium to the closing price as of May 28, 2021"
        "couchbase": 0.29,     # "29% premium to ... June 18, 2025"
    }
    for slug, claimed in expected.items():
        terms = deal_terms(_deal(register, slug), prices)
        assert terms.premium == pytest.approx(claimed, abs=0.01), (
            f"{slug}: computed {terms.premium:.3f}, issuer said {claimed:.2f}")


def test_couchbase_reports_both_baselines_because_its_buyer_pre_announced(register, prices):
    """Haveli built a 9.8% stake from 2025-03-28 and the stock re-rated on that
    news, so the pre-deal close is not a clean baseline. The issuer quotes both
    29% and 67%; both must be computable, and they must differ materially."""
    terms = deal_terms(_deal(register, "couchbase"), prices)
    assert terms.premium is not None and terms.premium_preleak is not None
    assert terms.premium_preleak > terms.premium + 0.20


def test_the_stock_deal_is_valued_at_the_acquirers_unaffected_price(register, prices):
    """Hortonworks was all-stock at 1.305 CLDR. Valuing the ratio at Cloudera's
    post-announcement price would fold the market's verdict on the deal into the
    deal's own terms; Cloudera rose 11.5% on that session, which would inflate
    the premium from ~2% to ~14%."""
    deal = _deal(register, "hortonworks")
    unaffected_value = offer_value(deal, prices)
    assert unaffected_value == pytest.approx(1.305 * prices["CLDR"][date(2018, 10, 3)])
    affected_value = 1.305 * prices["CLDR"][date(2018, 10, 4)]
    assert affected_value > unaffected_value * 1.10


def test_the_merger_of_equals_carries_essentially_no_premium(register, prices):
    """Hortonworks/Cloudera was a merger of equals, and the terms say so: ~2%
    against a cash-tender sample averaging well over 25%. Pooling it naively
    with the others would be a category error, so the sign of that difference is
    asserted."""
    hdp = deal_terms(_deal(register, "hortonworks"), prices)
    cash = [deal_terms(d, prices).premium for d in register if not d.is_stock]
    assert hdp.premium < 0.05
    assert min(cash) > 0.20


# --- the exact tests, and their floors -------------------------------------

def test_exact_test_reports_a_floor_above_5_percent_at_this_sample_size():
    """The lesson Part A paid for. With four events among seven firms there are
    C(7,4)=35 label assignments, so the smallest two-sided p-value is 2/35 =
    0.057. A 5% test cannot reject, whatever the data say, and the code must
    announce that rather than reporting a null as if it were evidence."""
    health = {f"firm{i}": float(i) for i in range(7)}
    acquired = {"firm0", "firm1", "firm2", "firm3"}
    result = firm_level_exact_test(health, acquired)
    assert result.arrangements == 35
    assert result.min_attainable_p == pytest.approx(2 / 35)
    assert not result.can_reject_at_5pct


def test_exact_test_finds_perfect_separation_at_its_floor():
    """With perfect separation the p-value must land exactly on the floor --
    not below it, which is the property that makes the floor meaningful."""
    health = {"a": 10.0, "b": 11.0, "c": 12.0, "d": 0.0, "e": 1.0, "f": 2.0}
    result = firm_level_exact_test(health, {"a", "b", "c"})
    assert result.p_value == pytest.approx(result.min_attainable_p)


def test_exact_test_is_two_sided():
    """Reversing which group is high must not change the p-value."""
    high = firm_level_exact_test({"a": 5.0, "b": 6.0, "c": 0.0, "d": 1.0}, {"a", "b"})
    low = firm_level_exact_test({"a": 0.0, "b": 1.0, "c": 5.0, "d": 6.0}, {"a", "b"})
    assert high.p_value == pytest.approx(low.p_value)


def test_no_p_value_can_fall_below_the_stated_floor_with_unequal_groups():
    """The reason the statistic is a rank sum and not a difference in means.

    A mean-difference statistic is not symmetric when the two groups differ in
    size, so its most extreme arrangement can be unique -- which produced
    p = 1/56 = 0.018 against a stated floor of 2/56 = 0.036 on the real
    eight-firm sample. A p-value below its own floor is incoherent, and it
    would have overstated the one Part B result that clears 5%. The rank-sum
    null is exactly symmetric about k(n+1)/2, so the floor holds by
    construction. Asserted across every unequal split of eight firms."""
    values = {f"firm{i}": float(i) for i in range(8)}
    for k in range(1, 8):
        acquired = {f"firm{i}" for i in range(k)}
        result = firm_level_exact_test(values, acquired)
        assert result.p_value >= result.min_attainable_p - 1e-12, (
            f"k={k}: p={result.p_value} below floor {result.min_attainable_p}")
        # perfect separation, so it must land exactly ON the floor
        assert result.p_value == pytest.approx(result.min_attainable_p)


def test_the_eight_firm_floor_is_what_lets_b1_clear_five_percent():
    """Part B's only result that reaches 5% does so because of one extra firm.
    At seven firms and four events the floor is 0.057 and rejection is
    impossible; at eight and five it is 0.036 and rejection is possible. The
    result is therefore a fact about the sample size as much as the data."""
    seven = firm_level_exact_test({f"f{i}": float(i) for i in range(7)},
                                  {"f0", "f1", "f2", "f3"})
    eight = firm_level_exact_test({f"f{i}": float(i) for i in range(8)},
                                  {"f0", "f1", "f2", "f3", "f4"})
    assert not seven.can_reject_at_5pct and seven.min_attainable_p == pytest.approx(2 / 35)
    assert eight.can_reject_at_5pct and eight.min_attainable_p == pytest.approx(2 / 56)


def test_separation_scan_flags_a_confound_that_separates_just_as_well():
    """The check that stops B1 being reported as a finding about repo health.
    If a plain financial variable separates the groups exactly as cleanly, the
    test cannot attribute the separation to the repo index."""
    from git_due_diligence.panel.deals import separation_scan
    firms = [f"f{i}" for i in range(8)]
    acquired = set(firms[:5])
    scan = separation_scan({
        "repo_health_index_z": {f: float(i) for i, f in enumerate(firms)},
        "op_margin_ltm": {f: float(i) * 0.1 for i, f in enumerate(firms)},
        "noise": {f: float((i * 5) % 8) for i, f in enumerate(firms)},
    }, acquired)
    perfect = {name for name, _, is_perfect in scan if is_perfect}
    assert perfect == {"repo_health_index_z", "op_margin_ltm"}
    assert dict((n, t.p_value) for n, t, _ in scan)["noise"] > 0.05


def test_separation_scan_skips_variables_with_missing_values():
    """A variable observed for only some firms cannot be compared on the same
    footing, so it is dropped rather than silently tested on a subset."""
    from git_due_diligence.panel.deals import separation_scan
    firms = [f"f{i}" for i in range(6)]
    scan = separation_scan({
        "ok": {f: float(i) for i, f in enumerate(firms)},
        "partial": {f: (float("nan") if i == 2 else float(i)) for i, f in enumerate(firms)},
    }, set(firms[:3]))
    assert [name for name, _, _ in scan] == ["ok"]


def test_spearman_exact_matches_a_known_perfect_correlation():
    result = spearman_exact([1.0, 2.0, 3.0, 4.0, 5.0], [10.0, 20.0, 30.0, 40.0, 50.0])
    assert result.statistic == pytest.approx(1.0)
    assert result.p_value == pytest.approx(2 / 120)
    assert result.arrangements == 120


def test_spearman_exact_floor_blocks_rejection_at_four_pairs():
    """Four deals give 24 permutations and a floor of 0.083. B2 on four deals
    cannot reach 5% even with a perfect rank correlation."""
    result = spearman_exact([1.0, 2.0, 3.0, 4.0], [1.0, 2.0, 3.0, 4.0])
    assert result.min_attainable_p == pytest.approx(2 / 24)
    assert not result.can_reject_at_5pct


# --- register validation ---------------------------------------------------

def test_loader_rejects_a_cash_deal_without_a_price(tmp_path):
    path = tmp_path / "d.toml"
    path.write_text('[[deal]]\nslug="x"\nticker="X"\nannounced=2020-01-02\n'
                    'first_affected=2020-01-02\nunaffected=2020-01-01\n'
                    'consideration="cash"\nacquirer="Y"\n', encoding="utf-8")
    with pytest.raises(ValueError, match="offer_price"):
        load_deals(path)


def test_loader_rejects_an_unaffected_date_after_the_first_affected_one(tmp_path):
    path = tmp_path / "d.toml"
    path.write_text('[[deal]]\nslug="x"\nticker="X"\nannounced=2020-01-02\n'
                    'first_affected=2020-01-02\nunaffected=2020-01-03\n'
                    'consideration="cash"\noffer_price=10.0\nacquirer="Y"\n',
                    encoding="utf-8")
    with pytest.raises(ValueError, match="must precede"):
        load_deals(path)


def test_stock_deal_without_an_acquirer_ticker_is_rejected(tmp_path):
    path = tmp_path / "d.toml"
    path.write_text('[[deal]]\nslug="x"\nticker="X"\nannounced=2020-01-02\n'
                    'first_affected=2020-01-02\nunaffected=2020-01-01\n'
                    'consideration="stock"\nexchange_ratio=1.5\nacquirer="Y"\n',
                    encoding="utf-8")
    with pytest.raises(ValueError, match="acquirer_ticker"):
        load_deals(path)


def test_cash_offer_value_ignores_prices_entirely():
    deal = Deal(slug="x", ticker="X", announced=date(2020, 1, 2),
                first_affected=date(2020, 1, 2), unaffected=date(2020, 1, 1),
                completed=None, consideration="cash", acquirer="Y", offer_price=42.0)
    assert offer_value(deal, {}) == 42.0
