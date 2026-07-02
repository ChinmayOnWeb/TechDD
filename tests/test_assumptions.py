from pathlib import Path

import pytest

from acquirescope.bridge.assumptions import load_assumptions

EXAMPLE = Path(__file__).parent.parent / "examples" / "assumptions.example.toml"


def _write(tmp_path, text):
    p = tmp_path / "a.toml"
    p.write_text(text, encoding="utf-8")
    return p

GOOD = EXAMPLE.read_text(encoding="utf-8")


def test_loads_example_file():
    a = load_assumptions(EXAMPLE)
    assert a.target_name == "target-repo"
    assert a.revenue_low == 8_000_000
    assert a.revenue_mid == 12_000_000
    assert a.revenue_high == 18_000_000
    assert len(a.comps) == 3
    assert a.comps[2].name == "GitLab"
    assert a.comps[2].ev_revenue_multiple == 8.5
    assert a.dcf_years == 5
    assert a.discount_rate == 0.18
    assert a.engineer_month_usd == 20_000
    assert a.security_fix_cost_usd == 50_000
    assert "press release" in a.revenue_source


def test_missing_section_rejected(tmp_path):
    bad = GOOD.replace("[costs]", "[nocosts]")
    with pytest.raises(ValueError, match=r"\[costs\]"):
        load_assumptions(_write(tmp_path, bad))


def test_revenue_ordering_rejected(tmp_path):
    bad = GOOD.replace("mid = 12_000_000", "mid = 99_000_000")
    with pytest.raises(ValueError, match="low <= mid <= high"):
        load_assumptions(_write(tmp_path, bad))


def test_empty_comps_rejected(tmp_path):
    import re
    bad = re.sub(r"companies = \[.*?\]\n", "companies = []\n", GOOD, flags=re.S)
    with pytest.raises(ValueError, match="companies"):
        load_assumptions(_write(tmp_path, bad))


def test_rate_out_of_range_rejected(tmp_path):
    bad = GOOD.replace("discount_rate = 0.18", "discount_rate = 1.5")
    with pytest.raises(ValueError, match="discount_rate"):
        load_assumptions(_write(tmp_path, bad))


def test_terminal_growth_must_be_below_discount_rate(tmp_path):
    bad = GOOD.replace("terminal_growth = 0.03", "terminal_growth = 0.30")
    with pytest.raises(ValueError, match="terminal_growth"):
        load_assumptions(_write(tmp_path, bad))
