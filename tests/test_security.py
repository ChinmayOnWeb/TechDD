import json
import subprocess
from pathlib import Path

from acquirescope.ingest import RepoIngest
from acquirescope.models import Severity
from acquirescope.modules import security


def _no_osv(monkeypatch):
    monkeypatch.setattr(security.shutil, "which", lambda _: None)


def test_planted_secret_found_in_history(fixture_repo, monkeypatch):
    _no_osv(monkeypatch)
    result = security.analyze(RepoIngest(Path(fixture_repo)))
    assert result.status == "ok"
    secrets = [f for f in result.findings if f.severity == Severity.CRITICAL]
    assert len(secrets) == 1
    assert "AWS access key" in secrets[0].title
    assert secrets[0].evidence[0].path == "config/settings.py"
    assert result.metrics["secret_count"] == 1


def test_secret_removed_from_head_still_flagged(fixture_repo, monkeypatch):
    _no_osv(monkeypatch)
    assert "AKIA" not in (Path(fixture_repo) / "config" / "settings.py").read_text(encoding="utf-8")
    result = security.analyze(RepoIngest(Path(fixture_repo)))
    assert result.metrics["secret_count"] == 1


def test_missing_policy_and_automation_flagged(fixture_repo, monkeypatch):
    _no_osv(monkeypatch)
    result = security.analyze(RepoIngest(Path(fixture_repo)))
    titles = [f.title for f in result.findings]
    assert "No security policy" in titles
    assert "No dependency update automation" in titles
    assert result.metrics["has_security_policy"] is False
    assert result.metrics["manifest_age_days"] == 17  # requirements 05-02 vs latest 05-19


def test_osv_absent_yields_honest_scope_note(fixture_repo, monkeypatch):
    _no_osv(monkeypatch)
    result = security.analyze(RepoIngest(Path(fixture_repo)))
    notes = [f for f in result.findings if f.title == "Vulnerability scan not available"]
    assert len(notes) == 1
    assert notes[0].severity == Severity.INFO
    assert result.metrics["vulnerability_count"] == -1


def test_osv_present_parses_canned_results(fixture_repo, monkeypatch):
    monkeypatch.setattr(security.shutil, "which", lambda _: "osv-scanner")
    canned = json.dumps({"results": [{"packages": [
        {"package": {"name": "mysqlclient"}, "vulnerabilities": [{}, {}]},
    ]}]})
    fake = subprocess.CompletedProcess(args=[], returncode=1, stdout=canned, stderr="")

    # Replace subprocess only inside the security module's namespace —
    # patching subprocess.run globally would break RepoIngest's git calls.
    class _FakeSubprocess:
        @staticmethod
        def run(*args, **kwargs):
            return fake

    monkeypatch.setattr(security, "subprocess", _FakeSubprocess())
    result = security.analyze(RepoIngest(Path(fixture_repo)))
    vulns = [f for f in result.findings if f.title.startswith("Vulnerable dependency")]
    assert len(vulns) == 1
    assert "mysqlclient" in vulns[0].title
    assert vulns[0].severity == Severity.HIGH
    assert result.metrics["vulnerability_count"] == 2
