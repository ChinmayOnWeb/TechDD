from datetime import date
from pathlib import Path

import pytest

from git_due_diligence.panel.universe import Firm, fiscal_quarter_ends, load_universe

GITLAB_TOML = """\
name = "GitLab Inc."
slug = "gitlab"
ticker = "GTLB"
cik = "0001653482"
repos = ["https://github.com/gitlabhq/gitlabhq.git"]
fiscal_year_end_month = 1
listed_from = 2021-10-14
notes = "IPO 2021-10-14; CE/EE monorepo merge 2019 predates listing."
"""


def _write(tmp_path: Path, name: str, body: str) -> Path:
    (tmp_path / name).write_text(body, encoding="utf-8")
    return tmp_path


def test_load_universe_parses_firm(tmp_path):
    firms = load_universe(_write(tmp_path, "gitlab.toml", GITLAB_TOML))
    assert len(firms) == 1
    firm = firms[0]
    assert firm == Firm(
        slug="gitlab", name="GitLab Inc.", ticker="GTLB", cik="0001653482",
        repos=("https://github.com/gitlabhq/gitlabhq.git",),
        fiscal_year_end_month=1, listed_from=date(2021, 10, 14),
        listed_to=None,
        notes="IPO 2021-10-14; CE/EE monorepo merge 2019 predates listing.",
    )


def test_cik_zero_padded_from_int(tmp_path):
    body = GITLAB_TOML.replace('cik = "0001653482"', "cik = 1653482")
    firms = load_universe(_write(tmp_path, "gitlab.toml", body))
    assert firms[0].cik == "0001653482"


def test_missing_key_raises(tmp_path):
    body = GITLAB_TOML.replace('ticker = "GTLB"\n', "")
    with pytest.raises(ValueError, match="ticker"):
        load_universe(_write(tmp_path, "gitlab.toml", body))


def test_bad_month_raises(tmp_path):
    body = GITLAB_TOML.replace("fiscal_year_end_month = 1", "fiscal_year_end_month = 13")
    with pytest.raises(ValueError, match="fiscal_year_end_month"):
        load_universe(_write(tmp_path, "gitlab.toml", body))


def test_fiscal_quarter_ends_january_fye():
    ends = fiscal_quarter_ends(1, date(2021, 10, 14), date(2022, 8, 1))
    assert ends == [date(2021, 10, 31), date(2022, 1, 31), date(2022, 4, 30), date(2022, 7, 31)]


def test_fiscal_quarter_ends_december_fye_handles_leap():
    ends = fiscal_quarter_ends(12, date(2024, 1, 1), date(2024, 12, 31))
    assert ends == [date(2024, 3, 31), date(2024, 6, 30), date(2024, 9, 30), date(2024, 12, 31)]
