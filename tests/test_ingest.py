from pathlib import Path

from acquirescope.ingest import RepoIngest


def test_commits_parsed_with_authors_and_changes(fixture_repo):
    ingest = RepoIngest(Path(fixture_repo))
    commits = ingest.commits()
    assert len(commits) == 24
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


def test_commit_parents_populated(fixture_repo):
    commits = RepoIngest(Path(fixture_repo)).commits()
    # newest-first: the root commit is last and has no parents
    assert commits[-1].parents == []
    assert all(len(c.parents) == 1 for c in commits[:-1])  # linear history


def test_tags_with_dates_oldest_first(fixture_repo):
    tags = RepoIngest(Path(fixture_repo)).tags()
    assert [name for name, _ in tags] == ["v0.1.0", "v0.2.0"]
    assert tags[0][1] < tags[1][1]
    assert tags[0][1].year == 2026


def test_full_patch_text_contains_planted_secret(fixture_repo):
    ingest = RepoIngest(Path(fixture_repo))
    text = ingest.full_patch_text()
    assert "AKIAIOSFODNN7EXAMPLE" in text
    assert "\x1eCOMMIT " in text
    assert ingest.full_patch_text() is text  # cached
