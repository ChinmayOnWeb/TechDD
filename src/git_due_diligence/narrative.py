from __future__ import annotations

import re
from typing import Callable

from git_due_diligence.models import ModuleResult

_CITATION = re.compile(r"\[E(\d+)\]")

_INSTRUCTIONS = (
    "You are writing the executive summary of a technical due-diligence report "
    "for a potential acquirer. Using ONLY the findings below, write 200-400 words "
    "of narrative for a non-technical deal team. Every factual claim MUST cite "
    "its finding id in square brackets, e.g. [E1]. Do not make any claim without "
    "a citation and do not invent findings."
)


def build_prompt(repo_name: str, results: list[ModuleResult]) -> tuple[str, set[str]]:
    lines = [_INSTRUCTIONS, "", f"Target repository: {repo_name}", ""]
    valid_ids: set[str] = set()
    counter = 0
    for result in results:
        lines.append(f"Module {result.module} ({result.status}):")
        if result.status != "ok":
            lines.append(f"  not assessed: {result.error}")
        for finding in result.findings:
            counter += 1
            eid = f"E{counter}"
            valid_ids.add(eid)
            lines.append(f"  [{eid}] ({finding.severity.value}) {finding.title}: {finding.summary}")
        if result.metrics:
            lines.append(f"  metrics: {result.metrics}")
        lines.append("")
    return "\n".join(lines), valid_ids


def verify_citations(text: str, valid_ids: set[str]) -> tuple[str, int]:
    """Strip [En] citations that don't correspond to real findings."""
    removed = 0

    def _check(match: re.Match) -> str:
        nonlocal removed
        if f"E{match.group(1)}" in valid_ids:
            return match.group(0)
        removed += 1
        return ""

    return _CITATION.sub(_check, text), removed


def generate_narrative(
    repo_name: str, results: list[ModuleResult], complete: Callable[[str], str]
) -> str:
    prompt, valid_ids = build_prompt(repo_name, results)
    text, removed = verify_citations(complete(prompt), valid_ids)
    if removed:
        text += f"\n\n({removed} unverifiable citation(s) removed.)"
    return text
