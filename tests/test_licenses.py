import json
import subprocess
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


def _tiny_repo(tmp_path: Path, files: dict[str, str]) -> Path:
    repo = tmp_path / "target"
    subprocess.run(["git", "init", str(repo)], check=True, capture_output=True)
    for path, content in files.items():
        file_path = repo / path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")
        subprocess.run(["git", "-C", str(repo), "add", path], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@example.com",
         "commit", "-m", "init"],
        check=True, capture_output=True,
    )
    return repo


def test_fair_code_license_elevated_to_medium(tmp_path):
    """A recognized non-OSI 'fair-code' / source-available license is a real
    M&A concern (redistribution restrictions, delayed open-source conversion,
    ambiguous acquirer usage rights) -- it must not sit at the same INFO
    severity as a routine MIT/Apache classification."""
    repo = _tiny_repo(tmp_path, {
        "LICENSE.md": (
            "# License\n\n"
            "Content is available under the \"Sustainable Use License\" as defined below.\n\n"
            "## Sustainable Use License\n\nVersion 1.0\n\n### Acceptance\n..."
        ),
    })
    result = licenses.analyze(RepoIngest(repo))
    own = [f for f in result.findings if f.title.startswith("Repository license:")]
    assert len(own) == 1
    assert own[0].severity == Severity.MEDIUM
    assert "Sustainable Use License" in result.metrics["own_license"]
    assert "acquirer" in own[0].summary.lower()


def test_unknown_license_elevated_to_medium(tmp_path):
    """A license that matches no known signature is unclassifiable risk, not
    a clean bill of health -- INFO would bury it next to routine MIT/Apache
    findings."""
    repo = _tiny_repo(tmp_path, {"LICENSE": "Some completely custom text nobody recognizes.\n"})
    result = licenses.analyze(RepoIngest(repo))
    own = [f for f in result.findings if f.title.startswith("Repository license:")]
    assert own[0].severity == Severity.MEDIUM
    assert result.metrics["own_license"] == "Unknown"


def test_js_dependencies_counted_across_monorepo_workspaces(tmp_path):
    repo = _tiny_repo(tmp_path, {
        "package.json": json.dumps({"name": "root", "dependencies": {"express": "^4.0.0"}}),
        "packages/api/package.json": json.dumps(
            {"name": "api", "dependencies": {"lodash": "^4.0.0", "axios": "^1.0.0"}}
        ),
        "LICENSE": "MIT License\n",
    })
    result = licenses.analyze(RepoIngest(repo))
    assert result.metrics["js_dependency_count"] == 3
    js_finding = [f for f in result.findings if "JavaScript" in f.title]
    assert len(js_finding) == 1
    assert "3" in js_finding[0].summary
    assert len(js_finding[0].evidence) == 2  # one per package.json manifest


def test_js_dependency_count_zero_when_no_manifests(fixture_repo):
    result = licenses.analyze(RepoIngest(Path(fixture_repo)))
    assert result.metrics["js_dependency_count"] == 0
    assert not any("JavaScript" in f.title for f in result.findings)
