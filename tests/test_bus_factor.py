import os
import subprocess
from pathlib import Path

from git_due_diligence.ingest import RepoIngest
from git_due_diligence.models import Severity
from git_due_diligence.modules import bus_factor


def _commit(repo: Path, path: str, content: str, author: str, date: str) -> None:
    file_path = repo / path
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(content, encoding="utf-8")
    name = author.split("@")[0]
    subprocess.run(["git", "-C", str(repo), "add", path], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(repo),
         "-c", f"user.name={name}", "-c", f"user.email={author}",
         "commit", "-m", f"update {path}", "--date", date],
        check=True, capture_output=True,
        env={**os.environ, "GIT_COMMITTER_DATE": date},
    )


def _tiny_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "target"
    subprocess.run(["git", "init", str(repo)], check=True, capture_output=True)
    return repo


def test_flags_single_owner_directory(fixture_repo):
    result = bus_factor.analyze(RepoIngest(Path(fixture_repo)))
    assert result.status == "ok"
    single_owner = [f for f in result.findings if "payments" in f.title]
    assert len(single_owner) == 1
    assert single_owner[0].severity == Severity.HIGH
    assert any(e.detail == "alice@example.com" for e in single_owner[0].evidence)


def test_flags_inactive_key_contributor(fixture_repo):
    result = bus_factor.analyze(RepoIngest(Path(fixture_repo)))
    inactive = [f for f in result.findings if "inactive" in f.title.lower()]
    assert len(inactive) == 1
    assert any(e.detail == "dave@example.com" for e in inactive[0].evidence)
    # Must not assert departure -- the engine can't verify that from commit
    # history alone (a founder moving to a non-coding role looks identical).
    assert "departed" not in inactive[0].title.lower()
    assert "may already be lost" not in inactive[0].summary


def test_concentration_metrics_present(fixture_repo):
    result = bus_factor.analyze(RepoIngest(Path(fixture_repo)))
    assert 0.0 <= result.metrics["contributor_gini"] <= 1.0
    assert 0.0 < result.metrics["top_author_share"] <= 1.0


def test_bot_account_does_not_trigger_single_point_of_failure(tmp_path):
    """A CI/automation account (e.g. gitlab-bot@gitlab.com, dependabot[bot]@...)
    dominating a directory's commits reflects automated churn, not a human
    knowledge-concentration risk. Real GitLab analysis showed 35/37 'single
    point of failure' findings were entirely gitlab-bot@gitlab.com commits,
    burying every genuine human-owned finding in noise."""
    repo = _tiny_repo(tmp_path)
    for i in range(6):
        _commit(repo, "i18n/locale.pot", f"msg{i}\n", "gitlab-bot@gitlab.com", f"2026-05-{3 + i:02d}T10:00:00")
    result = bus_factor.analyze(RepoIngest(repo))
    assert not any("i18n" in f.title for f in result.findings)


def test_bot_account_variants_recognized(tmp_path):
    repo = _tiny_repo(tmp_path)
    for i in range(6):
        _commit(repo, "deps/lock.json", f"v{i}\n",
                "49699333+dependabot[bot]@users.noreply.github.com", f"2026-05-{3 + i:02d}T10:00:00")
    result = bus_factor.analyze(RepoIngest(repo))
    assert not any("deps" in f.title for f in result.findings)


def test_bot_account_excluded_from_inactive_contributor_check(tmp_path):
    repo = _tiny_repo(tmp_path)
    for i in range(6):
        _commit(repo, f"file{i}.txt", f"v{i}\n", "gitlab-bot@gitlab.com", f"2024-01-{1 + i:02d}T10:00:00")
    # One recent human commit so `latest` reflects real activity.
    _commit(repo, "README.md", "hi\n", "alice@example.com", "2026-05-01T10:00:00")
    result = bus_factor.analyze(RepoIngest(repo))
    assert not any("gitlab-bot" in f.title for f in result.findings)


def test_bot_commits_excluded_from_concentration_metrics(tmp_path):
    repo = _tiny_repo(tmp_path)
    for i in range(20):
        _commit(repo, f"generated{i}.txt", f"v{i}\n", "gitlab-bot@gitlab.com", f"2026-05-{1 + i:02d}T10:00:00")
    _commit(repo, "README.md", "hi\n", "alice@example.com", "2026-06-01T10:00:00")
    result = bus_factor.analyze(RepoIngest(repo))
    # With bots excluded, alice is the only (human) author -- full concentration.
    assert result.metrics["top_author_share"] == 1.0
