import os
import subprocess
from datetime import date
from pathlib import Path

import pytest

from git_due_diligence.panel.history import quarterly_metrics

QUARTER_ENDS = [date(2024, 9, 30), date(2025, 3, 31), date(2025, 6, 30)]


def _git(repo: Path, *args: str, date_str: str | None = None) -> None:
    env = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull}
    if date_str:
        env["GIT_AUTHOR_DATE"] = date_str
        env["GIT_COMMITTER_DATE"] = date_str
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, env=env)


def _commit(repo: Path, path: str, content: str, author: str, date_str: str) -> None:
    file_path = repo / path
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(content, encoding="utf-8")
    _git(repo, "add", path)
    _git(repo, "-c", f"user.name={author.split('@')[0]}", "-c", f"user.email={author}",
         "commit", "-m", f"update {path}", date_str=date_str)


@pytest.fixture(scope="module")
def panel_repo(tmp_path_factory) -> Path:
    repo = tmp_path_factory.mktemp("panel-repo")
    subprocess.run(["git", "init", "-b", "main", str(repo)], check=True, capture_output=True)
    alice, bob, carol = "alice@example.com", "bob@example.com", "carol@example.com"
    bot = "dependabot[bot]@users.noreply.github.com"

    _commit(repo, "a.py", "A = 1\n", alice, "2025-01-15T10:00:00")
    _commit(repo, "a.py", "A = 2\n", alice, "2025-02-15T10:00:00")
    _commit(repo, "a.py", "A = 3\n", alice, "2025-03-15T10:00:00")
    _commit(repo, "b.py", "B = 1\n", bob, "2025-05-10T10:00:00")
    _commit(repo, "deps.txt", "dep==1\n", bot, "2025-05-11T10:00:00")
    _commit(repo, "config/settings.py", 'KEY = "AKIAIOSFODNN7EXAMPLE"\n', bob,
            "2025-05-12T10:00:00")
    _git(repo, "checkout", "-b", "feature")
    _commit(repo, "feature.py", "F = 1\n", bob, "2025-06-10T10:00:00")
    _git(repo, "checkout", "main")
    _git(repo, "-c", "user.name=carol", "-c", f"user.email={carol}",
         "merge", "--no-ff", "-m", "merge feature", "feature",
         date_str="2025-06-15T10:00:00")
    _git(repo, "tag", "v1.0")
    return repo


def test_one_row_per_quarter_end_in_order(panel_repo):
    rows = quarterly_metrics(panel_repo, QUARTER_ENDS)
    assert [r.quarter_end for r in rows] == QUARTER_ENDS


def test_empty_window_yields_zero_row(panel_repo):
    row = quarterly_metrics(panel_repo, QUARTER_ENDS)[0]
    assert row.commit_volume == 0
    assert row.active_contributors == 0
    assert row.top_author_share == 0.0
    assert row.secret_incidence == 0.0


def test_trailing_window_contributor_metrics(panel_repo):
    rows = quarterly_metrics(panel_repo, QUARTER_ENDS)
    q1 = rows[1]
    assert q1.commit_volume == 3
    assert q1.active_contributors == 1
    assert q1.top_author_share == 1.0
    assert q1.bus_factor_50 == 1

    q2 = rows[2]
    assert q2.commit_volume == 7
    assert q2.active_contributors == 3
    assert q2.top_author_share == round(3 / 7, 4)
    assert q2.bus_factor_50 == 2


def test_merge_release_and_secret_metrics(panel_repo):
    rows = quarterly_metrics(panel_repo, QUARTER_ENDS)
    q2 = rows[2]
    assert q2.merge_share == round(1 / 7, 4)
    assert q2.release_cadence == 1
    assert q2.secret_incidence == round(1000 * 1 / 7, 4)

    q1 = rows[1]
    assert q1.release_cadence == 0
    assert q1.secret_incidence == 0.0
    assert q1.merge_share == 0.0


def test_gini_metrics_bounded(panel_repo):
    q2 = quarterly_metrics(panel_repo, QUARTER_ENDS)[2]
    assert 0.0 <= q2.contributor_gini <= 1.0
    assert 0.0 <= q2.churn_gini <= 1.0
    assert q2.churn_gini > 0.0
