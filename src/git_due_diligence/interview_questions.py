from __future__ import annotations

import json
from typing import Callable

from git_due_diligence.dispositions import compute_finding_id
from git_due_diligence.models import ModuleResult, Severity

_INSTRUCTIONS = (
    "You are preparing interview questions for a technical due-diligence engagement. "
    "For each finding listed below, write ONE concise, exploratory, non-accusatory "
    "question a DD analyst would ask the target company's management or engineering "
    "leadership about it. Respond with STRICT JSON ONLY: an object mapping each "
    "finding id to its question string. No markdown fencing, no other text."
)


def build_questions_prompt(repo_name: str, results: list[ModuleResult]) -> tuple[str, set[str]]:
    lines = [_INSTRUCTIONS, "", f"Target repository: {repo_name}", ""]
    valid_ids: set[str] = set()
    for result in results:
        if result.status != "ok":
            continue
        for finding in result.findings:
            if finding.severity == Severity.INFO:
                continue
            fid = compute_finding_id(finding)
            valid_ids.add(fid)
            lines.append(f"[{fid}] ({finding.severity.value}) {finding.title}: {finding.summary}")
    return "\n".join(lines), valid_ids


def parse_questions_response(text: str, valid_ids: set[str]) -> dict[str, str]:
    try:
        data = json.loads(text.strip())
    except json.JSONDecodeError as exc:
        raise ValueError(f"question response was not valid JSON: {exc}") from exc
    if not isinstance(data, dict) or not all(
        isinstance(k, str) and isinstance(v, str) for k, v in data.items()
    ):
        raise ValueError("question response must be a JSON object of string -> string")
    return {fid: question for fid, question in data.items() if fid in valid_ids}


def generate_questions(
    repo_name: str, results: list[ModuleResult], complete: Callable[[str], str]
) -> dict[str, str]:
    prompt, valid_ids = build_questions_prompt(repo_name, results)
    return parse_questions_response(complete(prompt), valid_ids)
