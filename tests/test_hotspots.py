from pathlib import Path

from acquirescope.ingest import RepoIngest
from acquirescope.models import Severity
from acquirescope.modules import hotspots


def test_flags_high_churn_complex_file(fixture_repo):
    result = hotspots.analyze(RepoIngest(Path(fixture_repo)))
    assert result.status == "ok"
    flagged_paths = [e.path for f in result.findings for e in f.evidence]
    assert "core/engine.py" in flagged_paths


def test_simple_churned_file_not_flagged(fixture_repo):
    # payments/billing.py has 6 commits (high churn) but trivial complexity.
    result = hotspots.analyze(RepoIngest(Path(fixture_repo)))
    flagged_paths = [e.path for f in result.findings for e in f.evidence]
    assert "payments/billing.py" not in flagged_paths


def test_remediation_estimate_has_confidence_band(fixture_repo):
    result = hotspots.analyze(RepoIngest(Path(fixture_repo)))
    low = result.metrics["remediation_months_low"]
    mid = result.metrics["remediation_months_mid"]
    high = result.metrics["remediation_months_high"]
    assert 0 < low < mid < high
    assert all(isinstance(f.severity, Severity) for f in result.findings)
