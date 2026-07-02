import subprocess
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


def test_git_output_survives_invalid_utf8_bytes(tmp_path):
    """Real repos can contain non-UTF-8 bytes in a diff (binary blobs git
    misdetects as text, legacy-encoded fixtures, etc). A strict utf-8 decode
    of git's output must not crash — replace, don't raise."""
    repo = tmp_path / "badenc"
    subprocess.run(["git", "init", str(repo)], check=True, capture_output=True)
    (repo / "bad.txt").write_bytes(b"marker_before\n\xbf\xbf\xbf\nmarker_after\n")
    subprocess.run(["git", "-C", str(repo), "add", "bad.txt"], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@example.com",
         "commit", "-m", "add file with invalid utf-8 bytes"],
        check=True, capture_output=True,
    )
    ingest = RepoIngest(repo)
    text = ingest.full_patch_text()  # must not raise
    assert "marker_before" in text
    assert "marker_after" in text
