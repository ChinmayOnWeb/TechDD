from pathlib import Path

from acquirescope.ingest import RepoIngest
from acquirescope.models import Severity
from acquirescope.modules import licenses


def test_classifies_own_mit_license(fixture_repo):
    result = licenses.analyze(RepoIngest(Path(fixture_repo)))
    assert result.status == "ok"
    assert result.metrics["own_license"] == "MIT"


def test_flags_copyleft_dependency(fixture_repo):
    result = licenses.analyze(RepoIngest(Path(fixture_repo)))
    copyleft = [f for f in result.findings if f.severity == Severity.HIGH]
    assert len(copyleft) == 1
    assert "mysqlclient" in copyleft[0].summary
    assert copyleft[0].evidence[0].path == "requirements.txt"
    assert result.metrics["copyleft_dependency_count"] == 1


def test_clean_dependency_not_flagged(fixture_repo):
    result = licenses.analyze(RepoIngest(Path(fixture_repo)))
    assert not any("flask" in f.summary for f in result.findings)
