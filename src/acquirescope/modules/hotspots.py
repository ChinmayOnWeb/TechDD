from __future__ import annotations

import statistics
from collections import Counter

import lizard

from acquirescope.ingest import RepoIngest
from acquirescope.models import Evidence, Finding, ModuleResult, Severity

MODULE = "hotspots"
MIN_AVG_CCN = 5.0
SOURCE_EXTENSIONS = (".py", ".js", ".ts", ".tsx", ".jsx", ".go", ".java", ".rb", ".rs", ".c", ".cc", ".cpp", ".cs", ".php", ".swift", ".kt")

# Remediation model (documented assumption, spec requires a confidence band):
# a hotspot file costs (nloc / 2000) * (avg_ccn / 10) engineer-months to bring
# to maintainable state — i.e. a 2000-line file at CCN 10 ~ 1 engineer-month.
# Band is +/- 50% because the calibration is benchmark-based, not measured.
NLOC_PER_MONTH = 2000
CCN_BASELINE = 10
BAND = 0.5


def analyze(ingest: RepoIngest) -> ModuleResult:
    churn: Counter = Counter()
    for commit in ingest.commits():
        for change in commit.changes:
            churn[change.path] += 1

    tracked = set(ingest.list_files())
    source_churn = {
        path: count for path, count in churn.items()
        if path in tracked and path.endswith(SOURCE_EXTENSIONS)
    }
    if not source_churn:
        return ModuleResult(module=MODULE, status="ok", metrics={
            "hotspot_count": 0,
            "remediation_months_low": 0.0,
            "remediation_months_mid": 0.0,
            "remediation_months_high": 0.0,
        })

    churn_threshold = statistics.quantiles(list(source_churn.values()), n=4)[2]  # 75th pct

    findings: list[Finding] = []
    total_months = 0.0
    for path, count in sorted(source_churn.items(), key=lambda kv: -kv[1]):
        if count < churn_threshold:
            continue
        analysis = lizard.analyze_file(str(ingest.repo_path / path))
        functions = analysis.function_list
        if not functions:
            continue
        avg_ccn = sum(f.cyclomatic_complexity for f in functions) / len(functions)
        if avg_ccn < MIN_AVG_CCN:
            continue
        months = (analysis.nloc / NLOC_PER_MONTH) * (avg_ccn / CCN_BASELINE)
        total_months += months
        findings.append(Finding(
            module=MODULE,
            title=f"Tech-debt hotspot: {path}",
            severity=Severity.MEDIUM,
            summary=(
                f"{path} combines high change frequency ({count} commits) with high "
                f"complexity (avg CCN {avg_ccn:.1f} across {len(functions)} functions, "
                f"{analysis.nloc} NLOC). Estimated remediation: {months:.2f} engineer-months "
                f"(+/-50%)."
            ),
            evidence=[Evidence(
                description=f"churn={count} commits, avg_ccn={avg_ccn:.1f}, nloc={analysis.nloc}",
                path=path,
            )],
        ))

    return ModuleResult(
        module=MODULE, status="ok", findings=findings,
        metrics={
            "hotspot_count": len(findings),
            "remediation_months_low": round(total_months * (1 - BAND), 3),
            "remediation_months_mid": round(total_months, 3),
            "remediation_months_high": round(total_months * (1 + BAND), 3),
        },
    )
