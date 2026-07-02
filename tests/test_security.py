import json
import subprocess
from pathlib import Path

from acquirescope.ingest import RepoIngest
from acquirescope.models import Severity
from acquirescope.modules import security


def _no_osv(monkeypatch):
    monkeypatch.setattr(security.shutil, "which", lambda _: None)


def _tiny_repo(tmp_path: Path, path: str, content: str) -> Path:
    repo = tmp_path / "target"
    subprocess.run(["git", "init", str(repo)], check=True, capture_output=True)
    file_path = repo / path
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(content, encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", path], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@example.com",
         "commit", "-m", "add file"],
        check=True, capture_output=True,
    )
    return repo


def test_planted_secret_found_in_history(fixture_repo, monkeypatch):
    _no_osv(monkeypatch)
    result = security.analyze(RepoIngest(Path(fixture_repo)))
    assert result.status == "ok"
    secrets = [f for f in result.findings if f.severity == Severity.CRITICAL]
    assert len(secrets) == 1
    assert "AWS access key" in secrets[0].title
    assert secrets[0].evidence[0].path == "config/settings.py"
    assert result.metrics["secret_count"] == 1
    assert result.metrics["test_fixture_secret_count"] == 0


def test_secret_in_test_path_downgraded_to_low_confidence(tmp_path, monkeypatch):
    """Test suites for credential-handling code routinely commit synthetic
    secrets on purpose (e.g. AWS's own well-known example key). A secret
    found under a test/fixture path is real signal but not an actionable
    'must rotate' finding, so it must not inflate secret_count or CRITICAL
    severity the way a genuine leak does."""
    _no_osv(monkeypatch)
    repo = _tiny_repo(
        tmp_path, "src/__tests__/fixtures/leaked.txt",
        'AWS_KEY = "AKIAIOSFODNN7EXAMPLE"\n',
    )
    result = security.analyze(RepoIngest(repo))
    matches = [f for f in result.findings if "AWS access key" in f.title]
    assert len(matches) == 1
    assert matches[0].severity == Severity.LOW
    assert result.metrics["secret_count"] == 0
    assert result.metrics["test_fixture_secret_count"] == 1


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
