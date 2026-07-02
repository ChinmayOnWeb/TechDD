from __future__ import annotations

from acquirescope.models import ModuleResult

DISCLAIMER = (
    "*This report is an automated, educational analysis of publicly available "
    "data as of the run date. It is not investment advice, not a statement about "
    "any company's value or conduct, and findings are observations that may be "
    "incomplete or outdated.*"
)


def render_markdown(repo_name: str, results: list[ModuleResult]) -> str:
    lines = [f"# Technical Due Diligence Report: {repo_name}", ""]

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
            lines.append("")

    lines.append("---")
    lines.append("")
    lines.append(DISCLAIMER)
    lines.append("")
    return "\n".join(lines)
