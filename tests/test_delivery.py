from datetime import datetime, timedelta, timezone
from pathlib import Path

from acquirescope.ingest import Commit, RepoIngest
from acquirescope.models import Severity
from acquirescope.modules import delivery


class _StubIngest:
    """Minimal ingest stand-in for unit-level tests without git."""

    def __init__(self, commits, files=None, tags=None):
        self._commits, self._files, self._tags = commits, files or [], tags or []

    def commits(self):
        return self._commits

    def list_files(self):
        return self._files

    def tags(self):
        return self._tags


def _commit(days_ago: int, base=datetime(2026, 6, 1, tzinfo=timezone.utc)) -> Commit:
    return Commit(sha="x", author_email="a@example.com", author_name="a",
                  authored_at=base - timedelta(days=days_ago), changes=[])


def test_release_metrics_from_fixture_tags(fixture_repo):
    result = delivery.analyze(RepoIngest(Path(fixture_repo)))
    assert result.status == "ok"
    assert result.metrics["release_count"] == 2
    assert result.metrics["days_since_last_release"] == 2  # v0.2.0 05-17 vs latest 05-19
    assert not any(f.title == "No tagged releases" for f in result.findings)


def test_review_proxy_fires_on_merge_free_history(fixture_repo):
    result = delivery.analyze(RepoIngest(Path(fixture_repo)))
    proxies = [f for f in result.findings if "review" in f.title.lower()]
    assert len(proxies) == 1
    assert proxies[0].severity == Severity.LOW
    assert result.metrics["merge_commit_share"] == 0.0


def test_ci_absence_flagged(fixture_repo):
    result = delivery.analyze(RepoIngest(Path(fixture_repo)))
    assert any(f.title == "No CI configuration detected" for f in result.findings)
    assert result.metrics["ci_configured"] is False


def test_declining_activity_trend_unit():
    commits = [_commit(d) for d in (0, 10)] + [_commit(100 + d) for d in range(12)]
    result = delivery.analyze(_StubIngest(commits, files=[".github/workflows/ci.yml"]))
    declining = [f for f in result.findings if "declining" in f.title.lower()]
    assert len(declining) == 1
    assert result.metrics["commits_last_90d"] == 2
    assert result.metrics["ci_configured"] is True
