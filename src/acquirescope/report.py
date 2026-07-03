from __future__ import annotations

from acquirescope.dispositions import Disposition, compute_finding_id
from acquirescope.models import Finding, ModuleResult

DISCLAIMER = (
    "*This report is an automated, educational analysis of publicly available "
    "data as of the run date. It is not investment advice, not a statement about "
    "any company's value or conduct, and findings are observations that may be "
    "incomplete or outdated.*"
)


def render_markdown(
    repo_name: str,
    results: list[ModuleResult],
    narrative: str | None = None,
    dismissed: list[tuple[Finding, Disposition]] | None = None,
    questions: dict[str, str] | None = None,
) -> str:
    lines = [f"# Technical Due Diligence Report: {repo_name}", ""]
    if narrative:
        lines.append("## Executive narrative (LLM-generated, citation-verified)")
        lines.append("")
        lines.append(narrative)
        lines.append("")

    for result in results:
        lines.append(f"## Module: {result.module}")
        lines.append("")
        if result.status == "failed":
            lines.append(f"**Not assessed** — module failed: `{result.error}`")
            lines.append("")
            continue
        if result.metrics:
            lines.append("**Metrics:** " + ", ".join(f"{k}={v}" for k, v in result.metrics.items()))
            lines.append("")
        if not result.findings:
            lines.append("No findings.")
            lines.append("")
            continue
        for finding in result.findings:
            lines.append(f"### [{finding.severity.value.upper()}] {finding.title}")
            lines.append("")
            lines.append(finding.summary)
            lines.append("")
            for ev in finding.evidence:
                location = f" (`{ev.path}`)" if ev.path else ""
                detail = f" — {ev.detail}" if ev.detail else ""
                lines.append(f"- Evidence: {ev.description}{location}{detail}")
            if questions and (question := questions.get(compute_finding_id(finding))):
                lines.append("")
                lines.append(f"**Question for management:** {question}")
            lines.append("")

    lines.append("---")
    lines.append("")
    lines.append(DISCLAIMER)
    lines.append("")

    if dismissed:
        lines.append("## Appendix: Dismissed Findings (Analyst-Reviewed)")
        lines.append("")
        lines.append(
            "The findings below were reviewed and dismissed by the analyst. They do not "
            "appear in the report body above or in the priced valuation adjustments."
        )
        lines.append("")
        for finding, disposition in dismissed:
            lines.append(f"### [{finding.severity.value.upper()}] {finding.title}")
            lines.append("")
            lines.append(f"Dismissed — {disposition.note}")
            lines.append("")

    return "\n".join(lines)
