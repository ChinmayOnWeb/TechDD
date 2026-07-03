from pathlib import Path

from acquirescope.ingest import RepoIngest
from acquirescope.models import Severity
from acquirescope.modules import bus_factor


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
