import os
import subprocess
from datetime import date
from pathlib import Path

from git_due_diligence.panel.attribution import attribute

WINDOW = (date(2020, 1, 1), date(2024, 1, 1))


def _repo(tmp_path: Path, authors: list[str]) -> Path:
    repo = tmp_path / "r"
    repo.mkdir()
    env = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull}
    subprocess.run(["git", "init", "-b", "main", str(repo)], check=True, capture_output=True)
    for i, email in enumerate(authors):
        (repo / "f.txt").write_text(f"v{i}\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(repo), "add", "."], check=True, capture_output=True)
        stamp = f"2021-0{1 + i % 9}-15T10:00:00"
        subprocess.run(
            ["git", "-C", str(repo), "-c", "user.name=x", "-c", f"user.email={email}",
             "commit", "-m", f"c{i}"], check=True, capture_output=True,
            env={**env, "GIT_AUTHOR_DATE": stamp, "GIT_COMMITTER_DATE": stamp})
    return repo


def test_firm_domain_commits_counted_including_subdomains(tmp_path):
    repo = _repo(tmp_path, ["a@acme.com", "b@eng.acme.com", "c@rival.com"])
    r = attribute(repo, ["acme.com"], *WINDOW)
    assert r.firm_commits == 2
    assert r.total_commits == 3


def test_bots_excluded_before_counting(tmp_path):
    """Apache projects carry heavy CI automation; counting bots would attribute
    commits to whichever organisation hosts the bot.

    Note the limit deliberately accepted here: the shared bot filter matches
    'bot' tokens and a short automation list, so `jenkins@` is NOT excluded.
    Adding it was considered and rejected -- Jenkins is also a surname, and the
    filter's standing rule is to never risk dropping a human."""
    repo = _repo(tmp_path, ["a@acme.com", "ci-bot@acme.com",
                            "build-bot@rival.com", "b@rival.com"])
    r = attribute(repo, ["acme.com"], *WINDOW)
    assert r.total_commits == 2                 # both bots dropped
    assert r.firm_commits == 1


def test_personal_domains_are_unattributable_not_rivals(tmp_path):
    """A gmail address carries no employer signal. Counting it as a rival would
    understate the firm; counting it as the firm would overstate it."""
    repo = _repo(tmp_path, ["a@acme.com", "b@gmail.com",
                            "c@users.noreply.github.com", "d@apache.org"])
    r = attribute(repo, ["acme.com"], *WINDOW)
    assert r.unattributable_commits == 3
    assert r.top_other == ()
    assert r.unattributable_share == 0.75


def test_plurality_is_against_identifiable_employers(tmp_path):
    repo = _repo(tmp_path, ["a@acme.com", "b@acme.com", "c@rival.com"])
    r = attribute(repo, ["acme.com"], *WINDOW)
    assert r.has_plurality is True


def test_no_plurality_when_a_rival_leads(tmp_path):
    repo = _repo(tmp_path, ["a@acme.com", "b@rival.com", "c@rival.com"])
    r = attribute(repo, ["acme.com"], *WINDOW)
    assert r.has_plurality is False


def test_zero_firm_commits_is_not_a_plurality(tmp_path):
    repo = _repo(tmp_path, ["b@gmail.com", "c@other.com"])
    r = attribute(repo, ["acme.com"], *WINDOW)
    assert r.has_plurality is False


def test_high_unattributable_share_is_surfaced(tmp_path):
    """The Confluent/Kafka case: a firm can hold a technical plurality while
    most commits are unattributable, which makes the plurality uninformative.
    The share must be reported so that can be judged."""
    repo = _repo(tmp_path, ["a@acme.com", "a2@acme.com"]
                 + ["x@gmail.com"] * 8 + ["b@rival.com"])
    r = attribute(repo, ["acme.com"], *WINDOW)
    assert r.has_plurality is True               # firm 2 > rival 1
    assert r.unattributable_share >= 0.7         # ...but most commits are unknown
    assert r.firm_share <= 0.2                   # and the firm authored under a fifth


def test_commits_outside_the_window_are_excluded(tmp_path):
    repo = _repo(tmp_path, ["a@acme.com", "b@acme.com"])
    r = attribute(repo, ["acme.com"], date(2030, 1, 1), date(2031, 1, 1))
    assert r.total_commits == 0
    assert r.firm_share == 0.0
