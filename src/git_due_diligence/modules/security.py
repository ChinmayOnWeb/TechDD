from __future__ import annotations

import json
import re
import shutil
import subprocess

from git_due_diligence.ingest import RepoIngest
from git_due_diligence.models import Evidence, Finding, ModuleResult, Severity

MODULE = "security"
MANIFEST_STALE_DAYS = 180
OSV_TIMEOUT_SECONDS = 300

# label -> pattern; scanned over ADDED lines of the full history patch.
_SECRET_PATTERNS = [
    ("AWS access key", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("Private key block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("Hardcoded credential assignment",
     re.compile(r"(?i)\b(?:api_key|secret_key|token)\s*=\s*['\"][A-Za-z0-9/+_\-]{16,}['\"]")),
]

# Test suites for credential-handling code routinely commit synthetic secrets
# on purpose (AWS's own docs even publish a well-known example access key),
# and user-facing integration docs/onboarding snippets show example config
# values for the same reason. A hit under one of these path segments is real
# signal but not an actionable "must rotate" finding -- downgrade confidence
# instead of discarding it outright.
_LOW_CONFIDENCE_PATH_MARKERS = frozenset({
    "test", "tests", "testing", "__tests__", "spec", "specs",
    "fixture", "fixtures", "evaluation", "evaluations",
    "mock", "mocks", "example", "examples", "sample", "samples",
    "docs", "doc", "onboarding", "guide", "guides",
    "snippet", "snippets", "demo", "demos",
})

# Documentation file formats are prose by construction -- a matched pattern
# there is a usage example, not embedded key material.
_LOW_CONFIDENCE_EXTENSIONS = (".md", ".mdx")


def _looks_like_test_path(path: str | None) -> bool:
    if not path:
        return False
    segments = re.split(r"[/\\]", path.lower())
    if any(seg in _LOW_CONFIDENCE_PATH_MARKERS for seg in segments):
        return True
    filename = segments[-1]
    if filename.endswith(_LOW_CONFIDENCE_EXTENSIONS):
        return True
    # Python/pytest convention: test_foo.py or foo_test.py, no "test"
    # directory segment required.
    stem = filename.rsplit(".", 1)[0] if "." in filename else filename
    if stem.startswith("test_") or stem.endswith("_test"):
        return True
    return ".test." in filename or ".spec." in filename


_TEMPLATE_BINDING_ATTR_PREFIX = re.compile(r":[\w-]*$")


def _is_template_binding_mention(line: str, match: re.Match) -> bool:
    """Vue/Angular-style bound attributes (`:token="expr"`,
    `:initial-secret-token="initialSecretToken"`) place the credential
    keyword at the tail of a kebab-case attribute name introduced by a bare
    colon, with a JS/TS expression -- not a literal secret -- inside the
    quotes that follow the `=`. This matches the hardcoded-credential regex
    (keyword + `=` + 16+ alnum chars in quotes) despite containing no actual
    secret material. Walk back from the match to the start of the kebab-case
    identifier and check whether a bare `:` immediately precedes it."""
    return bool(_TEMPLATE_BINDING_ATTR_PREFIX.search(line[:match.start()]))


_MAX_PRIVATE_KEY_PROSE_CHARS = 20


def _is_private_key_prose_mention(line: str, match: re.Match) -> bool:
    """A genuine embedded PEM header carries little else on its line besides
    itself (maybe a quote/backtick/leading diff '+'). A header appearing
    mid-sentence in an error message or comment describing the expected
    format ("...must contain a PEM private key (-----BEGIN PRIVATE
    KEY-----).") is not real key material."""
    stripped = line.lstrip("+").strip()
    extra = stripped.replace(match.group(0), "", 1)
    extra_chars = len(re.sub(r"[\s'\"`,;)(.]", "", extra))
    return extra_chars > _MAX_PRIVATE_KEY_PROSE_CHARS


def _is_manifest(path: str) -> bool:
    name = path.rsplit("/", 1)[-1]
    if name.startswith("requirements") and name.endswith(".txt"):
        return True
    return name in ("pyproject.toml", "package.json", "go.mod", "Cargo.toml", "Gemfile")


def _secrets_in_history(ingest: RepoIngest) -> tuple[list[Finding], int, int]:
    """Returns (findings, high_confidence_count, low_confidence_count)."""
    findings: list[Finding] = []
    seen: set[str] = set()
    high_confidence = 0
    low_confidence = 0
    for record in ingest.iter_patch_records():
        if not record.startswith("COMMIT "):
            continue
        header, _, body = record.partition("\n")
        sha = header.removeprefix("COMMIT ").strip()
        current_path: str | None = None
        for line in body.splitlines():
            if line.startswith("+++ b/"):
                current_path = line[6:]
                continue
            if not line.startswith("+") or line.startswith("+++"):
                continue
            for label, pattern in _SECRET_PATTERNS:
                for match in pattern.finditer(line):
                    secret = match.group(0)
                    if secret in seen:
                        continue
                    seen.add(secret)
                    prose_mention = (
                        label == "Private key block"
                        and _is_private_key_prose_mention(line, match)
                    )
                    template_binding = (
                        label == "Hardcoded credential assignment"
                        and _is_template_binding_mention(line, match)
                    )
                    if prose_mention:
                        low_confidence += 1
                        title = f"Private key format mentioned in text (likely not a real key): {label}"
                        summary = (
                            "A private-key marker string appeared surrounded by other text on the "
                            "same line, consistent with an error message or comment describing the "
                            "expected format rather than an embedded key. Not excluded automatically "
                            "-- verify manually before dismissing."
                        )
                        severity = Severity.LOW
                    elif template_binding:
                        low_confidence += 1
                        title = f"Template attribute binding, likely not a real secret: {label}"
                        summary = (
                            "The credential keyword is immediately preceded by a colon and followed "
                            "by a quoted value, consistent with a Vue/Angular-style bound attribute "
                            "(e.g. :token=\"expression\") where the quotes wrap a JS/TS expression "
                            "reference rather than a literal secret. Not excluded automatically -- "
                            "verify manually before dismissing."
                        )
                        severity = Severity.LOW
                    elif _looks_like_test_path(current_path):
                        low_confidence += 1
                        title = f"Possible test-fixture secret in git history: {label}"
                        severity = Severity.LOW
                        summary = (
                            f"A {label.lower()} pattern was found in git history at a path that "
                            f"looks like a test or fixture location. Likely a synthetic value used "
                            f"to test credential-handling code rather than a genuine leak, but not "
                            f"excluded automatically -- verify manually before dismissing."
                        )
                    else:
                        high_confidence += 1
                        title = f"Secret in git history: {label}"
                        severity = Severity.CRITICAL
                        summary = (
                            f"A {label.lower()} was committed to git history and remains "
                            f"recoverable from it even if removed from the working tree. "
                            f"It must be rotated and the history scrubbed."
                        )
                    findings.append(Finding(
                        module=MODULE, title=title, severity=severity, summary=summary,
                        evidence=[Evidence(
                            description=f"introduced in commit {sha[:12]}",
                            path=current_path, detail=label,
                        )],
                    ))
    return findings, high_confidence, low_confidence


def _vulnerability_findings(ingest: RepoIngest) -> tuple[list[Finding], int]:
    unavailable = Finding(
        module=MODULE,
        title="Vulnerability scan not available",
        severity=Severity.INFO,
        summary=(
            "osv-scanner is not installed (or failed); dependency vulnerabilities were "
            "not assessed. Install osv-scanner to enable this check."
        ),
        evidence=[Evidence(description="osv-scanner not usable on PATH")],
    )
    if shutil.which("osv-scanner") is None:
        return [unavailable], -1
    try:
        # osv-scanner exits non-zero when vulnerabilities are found; don't check=True.
        result = subprocess.run(
            ["osv-scanner", "--format", "json", "-r", str(ingest.repo_path)],
            capture_output=True, text=True, encoding="utf-8", timeout=OSV_TIMEOUT_SECONDS,
        )
        data = json.loads(result.stdout)
    except Exception:
        return [unavailable], -1

    per_package: dict[str, int] = {}
    for res in data.get("results", []):
        for pkg in res.get("packages", []):
            name = pkg.get("package", {}).get("name", "unknown")
            per_package[name] = per_package.get(name, 0) + len(pkg.get("vulnerabilities", []))

    findings = [
        Finding(
            module=MODULE,
            title=f"Vulnerable dependency: {name}",
            severity=Severity.HIGH,
            summary=f"osv-scanner reports {count} known vulnerability advisories for '{name}'.",
            evidence=[Evidence(description=f"{count} OSV advisories", detail=name)],
        )
        for name, count in sorted(per_package.items())
    ]
    return findings, sum(per_package.values())


def analyze(ingest: RepoIngest) -> ModuleResult:
    files = ingest.list_files()
    fileset = set(files)
    findings: list[Finding] = []

    secret_findings, secret_count, low_confidence_secret_count = _secrets_in_history(ingest)
    findings.extend(secret_findings)

    has_policy = any(f.upper() == "SECURITY.MD" for f in files)
    if not has_policy:
        findings.append(Finding(
            module=MODULE, title="No security policy", severity=Severity.MEDIUM,
            summary="No SECURITY.md at the repository root; there is no documented vulnerability disclosure process.",
            evidence=[Evidence(description="expected SECURITY.md at repo root")],
        ))

    if not ({".github/dependabot.yml", "renovate.json"} & fileset):
        findings.append(Finding(
            module=MODULE, title="No dependency update automation", severity=Severity.LOW,
            summary="Neither dependabot nor renovate is configured; dependency updates rely on manual effort.",
            evidence=[Evidence(description="no .github/dependabot.yml or renovate.json")],
        ))

    commits = ingest.commits()
    latest = max(c.authored_at for c in commits)
    manifest_dates = [
        c.authored_at for c in commits for ch in c.changes if _is_manifest(ch.path)
    ]
    manifest_age_days = -1
    if manifest_dates:
        manifest_age_days = (latest - max(manifest_dates)).days
        if manifest_age_days > MANIFEST_STALE_DAYS:
            findings.append(Finding(
                module=MODULE, title="Stale dependency manifest", severity=Severity.MEDIUM,
                summary=(
                    f"No dependency manifest has been touched for {manifest_age_days} days; "
                    f"dependencies are likely unpatched."
                ),
                evidence=[Evidence(description=f"last manifest change {manifest_age_days} days before latest commit")],
            ))

    vuln_findings, vulnerability_count = _vulnerability_findings(ingest)
    findings.extend(vuln_findings)

    return ModuleResult(
        module=MODULE, status="ok", findings=findings,
        metrics={
            "secret_count": secret_count,
            "low_confidence_secret_count": low_confidence_secret_count,
            "has_security_policy": has_policy,
            "manifest_age_days": manifest_age_days,
            "vulnerability_count": vulnerability_count,
        },
    )
