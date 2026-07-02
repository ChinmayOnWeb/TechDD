from __future__ import annotations

import re
import tomllib

from acquirescope.ingest import RepoIngest
from acquirescope.models import Evidence, Finding, ModuleResult, Severity

MODULE = "licenses"

# Signature phrases -> SPDX-ish label, checked in order (AGPL before GPL).
_LICENSE_SIGNATURES = [
    ("GNU AFFERO GENERAL PUBLIC LICENSE", "AGPL-3.0"),
    ("GNU LESSER GENERAL PUBLIC LICENSE", "LGPL"),
    ("GNU GENERAL PUBLIC LICENSE", "GPL"),
    ("MIT LICENSE", "MIT"),
    ("APACHE LICENSE", "Apache-2.0"),
    ("BSD", "BSD"),
    ("MOZILLA PUBLIC LICENSE", "MPL-2.0"),
]

# Known-copyleft PyPI packages (curated, extensible). Names lowercased.
COPYLEFT_PYPI = {
    "mysqlclient": "GPL-2.0",
    "pyqt5": "GPL-3.0",
    "pyqt6": "GPL-3.0",
    "python-vlc": "LGPL-2.1",
    "rpy2": "GPL-2.0",
    "pygraphviz": "BSD",  # not copyleft; kept out below — see test for flask
}
# Only these licenses trigger a finding.
_COPYLEFT_PREFIXES = ("GPL", "AGPL", "LGPL")

_REQ_NAME = re.compile(r"^\s*([A-Za-z0-9._-]+)")


def _classify_license_text(text: str) -> str:
    upper = text.upper()
    for signature, label in _LICENSE_SIGNATURES:
        if signature in upper:
            return label
    return "Unknown"


def _python_dependencies(ingest: RepoIngest) -> list[tuple[str, str]]:
    """Returns (package_name_lowercased, manifest_path) pairs."""
    deps: list[tuple[str, str]] = []
    files = set(ingest.list_files())
    if "requirements.txt" in files:
        text = (ingest.repo_path / "requirements.txt").read_text(encoding="utf-8")
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith(("#", "-")):
                continue
            match = _REQ_NAME.match(line)
            if match:
                deps.append((match.group(1).lower(), "requirements.txt"))
    if "pyproject.toml" in files:
        data = tomllib.loads((ingest.repo_path / "pyproject.toml").read_text(encoding="utf-8"))
        for spec in data.get("project", {}).get("dependencies", []):
            match = _REQ_NAME.match(spec)
            if match:
                deps.append((match.group(1).lower(), "pyproject.toml"))
    return deps


def analyze(ingest: RepoIngest) -> ModuleResult:
    findings: list[Finding] = []
    files = ingest.list_files()

    # 1. The target's own license.
    own_license = "None found"
    license_files = [f for f in files if f.upper().startswith("LICENSE")]
    if license_files:
        text = (ingest.repo_path / license_files[0]).read_text(encoding="utf-8", errors="replace")
        own_license = _classify_license_text(text)
    findings.append(Finding(
        module=MODULE,
        title=f"Repository license: {own_license}",
        severity=Severity.INFO,
        summary=f"The target repository itself is licensed under {own_license}.",
        evidence=[Evidence(description="root license file", path=license_files[0] if license_files else None)],
    ))

    # 2. Copyleft dependencies in Python manifests.
    copyleft_count = 0
    for name, manifest in _python_dependencies(ingest):
        license_label = COPYLEFT_PYPI.get(name)
        if license_label and license_label.startswith(_COPYLEFT_PREFIXES):
            copyleft_count += 1
            findings.append(Finding(
                module=MODULE,
                title=f"Copyleft dependency: {name}",
                severity=Severity.HIGH,
                summary=(
                    f"Dependency '{name}' is {license_label} licensed. Copyleft obligations "
                    f"can restrict proprietary distribution and are a diligence red flag."
                ),
                evidence=[Evidence(description=f"declared in {manifest}", path=manifest, detail=name)],
            ))

    # 3. Honest scope note for ecosystems we don't assess yet.
    unassessed = [f for f in files if f.endswith(("package.json", "go.mod", "Cargo.toml", "Gemfile"))]
    if unassessed:
        findings.append(Finding(
            module=MODULE,
            title="Non-Python manifests not assessed",
            severity=Severity.INFO,
            summary=f"Found {len(unassessed)} non-Python manifest(s); license scan covers Python only in this version.",
            evidence=[Evidence(description="unassessed manifest", path=p) for p in unassessed],
        ))

    return ModuleResult(
        module=MODULE, status="ok", findings=findings,
        metrics={"own_license": own_license, "copyleft_dependency_count": copyleft_count},
    )
