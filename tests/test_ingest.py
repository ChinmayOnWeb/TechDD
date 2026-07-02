from pathlib import Path

from acquirescope.ingest import RepoIngest


def test_commits_parsed_with_authors_and_changes(fixture_repo):
    ingest = RepoIngest(Path(fixture_repo))
    commits = ingest.commits()
    assert len(commits) == 22
    newest = commits[0]
    assert newest.sha and newest.author_email.endswith("@example.com")
    dave_commits = [c for c in commits if c.author_email == "dave@example.com"]
    assert len(dave_commits) == 5
    assert all(c.authored_at.year == 2024 for c in dave_commits)
    assert any(ch.path == "core/legacy.py" for c in dave_commits for ch in c.changes)


def test_list_files_returns_tracked_paths(fixture_repo):
    ingest = RepoIngest(Path(fixture_repo))
    files = ingest.list_files()
    assert "payments/billing.py" in files
    assert "requirements.txt" in files
