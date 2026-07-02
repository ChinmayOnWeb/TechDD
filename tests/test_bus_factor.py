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


def test_flags_departed_key_contributor(fixture_repo):
    result = bus_factor.analyze(RepoIngest(Path(fixture_repo)))
    departed = [f for f in result.findings if "departed" in f.title.lower()]
    assert len(departed) == 1
    assert any(e.detail == "dave@example.com" for e in departed[0].evidence)


def test_concentration_metrics_present(fixture_repo):
    result = bus_factor.analyze(RepoIngest(Path(fixture_repo)))
    assert 0.0 <= result.metrics["contributor_gini"] <= 1.0
    assert 0.0 < result.metrics["top_author_share"] <= 1.0
