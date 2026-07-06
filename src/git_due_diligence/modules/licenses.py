from __future__ import annotations

import json
import re
import tomllib

from git_due_diligence.ingest import RepoIngest
from git_due_diligence.models import Evidence, Finding, ModuleResult, Severity

MODULE = "licenses"

# Signature phrases -> SPDX-ish label, checked in order (AGPL before GPL).
# Non-OSI "fair-code"/source-available signatures come first: they are real
# M&A findings (redistribution restrictions, delayed open-source conversion,
# ambiguous acquirer usage rights), not routine license bookkeeping.
_LICENSE_SIGNATURES = [
    ("SUSTAINABLE USE LICENSE", "Sustainable Use License (fair-code, non-OSI)"),
    ("BUSINESS SOURCE LICENSE", "Business Source License / BSL (non-OSI)"),
    ("SERVER SIDE PUBLIC LICENSE", "Server Side Public License / SSPL (non-OSI)"),
    ("ELASTIC LICENSE", "Elastic License (non-OSI)"),
    ("FUNCTIONAL SOURCE LICENSE", "Functional Source License / FSL (non-OSI)"),
    ("GNU AFFERO GENERAL PUBLIC LICENSE", "AGPL-3.0"),
    ("GNU LESSER GENERAL PUBLIC LICENSE", "LGPL"),
    ("GNU GENERAL PUBLIC LICENSE", "GPL"),
    ("MIT LICENSE", "MIT"),
    ("APACHE LICENSE", "Apache-2.0"),
    ("BSD", "BSD"),
    ("MOZILLA PUBLIC LICENSE", "MPL-2.0"),
]

# Labels above that are NOT OSI-approved -- these plus "Unknown" get an
# elevated severity on the own-license finding rather than sitting at the
# same INFO level as a routine MIT/Apache/GPL classification.
_NON_OSI_LABELS = {label for _, label in _LICENSE_SIGNATURES if "(non-OSI" in label or "(fair-code" in label}

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


def _js_dependency_counts(ingest: RepoIngest) -> list[tuple[str, int]]:
    """Returns (package.json path, direct 'dependencies' count) pairs, across
    every tracked package.json -- root and any workspace/monorepo packages."""
    counts: list[tuple[str, int]] = []
    for path in ingest.list_files():
        if path.rsplit("/", 1)[-1] != "package.json":
            continue
        try:
            data = json.loads((ingest.repo_path / path).read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        counts.append((path, len(data.get("dependencies", {}))))
    return counts


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
    if own_license in _NON_OSI_LABELS:
        severity = Severity.MEDIUM
        summary = (
            f"The repository is licensed under {own_license}, not a standard OSI-approved "
            f"open-source license. Fair-code/source-available licenses commonly restrict "
            f"competing commercial use, may include a delayed open-source conversion "
            f"(a 'change date'), and can create ambiguity about an acquirer's usage and "
            f"redistribution rights. Legal review of the license terms and any separate "
            f"commercial/enterprise license variant is recommended before close."
        )
    elif own_license == "Unknown":
        severity = Severity.MEDIUM
        summary = (
            "The repository's license could not be classified against known OSI or "
            "fair-code license signatures. This may be a custom or unpublished license -- "
            "legal review of the actual license text is recommended before relying on any "
            "assumed usage or redistribution rights."
        )
    else:
        severity = Severity.INFO
        summary = f"The target repository itself is licensed under {own_license}."
    findings.append(Finding(
        module=MODULE,
        title=f"Repository license: {own_license}",
        severity=severity,
        summary=summary,
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

    # 3. JavaScript/TypeScript dependencies: counted across the repo (root +
    # any monorepo workspace packages) but not classified per-package. Real
    # per-package license data requires either a network/registry query or
    # an installed node_modules tree -- neither is available under this
    # engine's public-local-data-only constraint, and no npm ecosystem is
    # permissive-by-default enough to guess at safely, unlike Python's
    # curated PyPI list above. Honest about scope rather than guessing.
    js_manifests = _js_dependency_counts(ingest)
    js_dependency_count = sum(count for _, count in js_manifests)
    if js_dependency_count:
        findings.append(Finding(
            module=MODULE,
            title="JavaScript/TypeScript dependencies not license-classified",
            severity=Severity.INFO,
            summary=(
                f"Found {js_dependency_count} direct npm/yarn dependencies across "
                f"{len(js_manifests)} package.json manifest(s). Per-package license "
                f"classification requires an installed dependency tree or a registry "
                f"query, neither available under this engine's public-local-data-only "
                f"constraint; JS/TS dependency license risk was not assessed."
            ),
            evidence=[Evidence(description=f"{count} dependencies", path=path)
                      for path, count in js_manifests],
        ))

    # 4. Honest scope note for ecosystems we don't assess at all.
    unassessed = [f for f in files if f.endswith(("go.mod", "Cargo.toml", "Gemfile"))]
    if unassessed:
        findings.append(Finding(
            module=MODULE,
            title="Non-Python/JS manifests not assessed",
            severity=Severity.INFO,
            summary=f"Found {len(unassessed)} manifest(s) in other ecosystems; license scan covers Python and JS/TS only.",
            evidence=[Evidence(description="unassessed manifest", path=p) for p in unassessed],
        ))

    return ModuleResult(
        module=MODULE, status="ok", findings=findings,
        metrics={
            "own_license": own_license,
            "copyleft_dependency_count": copyleft_count,
            "js_dependency_count": js_dependency_count,
        },
    )
