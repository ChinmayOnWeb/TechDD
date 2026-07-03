from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from pathlib import Path

from acquirescope.models import Finding, ModuleResult, Severity

_VALID_STATUSES = {"pending", "confirmed", "downgraded", "dismissed"}


def compute_finding_id(finding: Finding) -> str:
    """Deterministic short hash of a finding's identity: module, title, and
    evidence paths/details. Stable across re-runs as long as the finding's
    substance doesn't change; independent of list ordering elsewhere."""
    parts = [finding.module, finding.title]
    for e in finding.evidence:
        parts.append(e.path or "")
        parts.append(e.detail or "")
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
    return digest[:12]


@dataclass(frozen=True)
class Disposition:
    status: str  # "pending" | "confirmed" | "downgraded" | "dismissed"
    severity_override: Severity | None
    note: str
    finding_title: str  # informational only, refreshed on every merge


def load_dispositions(path: Path) -> dict[str, Disposition]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid dispositions JSON in {path}: {exc}") from exc

    result: dict[str, Disposition] = {}
    for finding_id, entry in data.get("dispositions", {}).items():
        status = entry.get("status")
        if status not in _VALID_STATUSES:
            raise ValueError(f"unknown disposition status '{status}' for finding {finding_id}")

        raw_override = entry.get("severity_override")
        severity_override: Severity | None = None
        if raw_override is not None:
            try:
                severity_override = Severity(raw_override)
            except ValueError as exc:
                raise ValueError(
                    f"invalid severity_override '{raw_override}' for finding {finding_id}"
                ) from exc

        if status == "downgraded" and severity_override is None:
            raise ValueError(f"finding {finding_id} is 'downgraded' but has no severity_override")

        result[finding_id] = Disposition(
            status=status,
            severity_override=severity_override,
            note=entry.get("note", ""),
            finding_title=entry.get("finding_title", ""),
        )
    return result


def save_dispositions(path: Path, target_name: str, dispositions: dict[str, Disposition]) -> None:
    payload = {
        "target": target_name,
        "dispositions": {
            finding_id: {
                "status": d.status,
                "severity_override": d.severity_override.value if d.severity_override else None,
                "note": d.note,
                "finding_title": d.finding_title,
            }
            for finding_id, d in dispositions.items()
        },
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def merge_dispositions(
    results: list[ModuleResult], existing: dict[str, Disposition]
) -> dict[str, Disposition]:
    """Combine the current finding set with previously-saved dispositions.
    Existing entries are kept (with finding_title refreshed); new findings
    are added as 'pending'; entries for findings no longer detected are
    dropped -- there is nothing left to disposition."""
    merged: dict[str, Disposition] = {}
    for result in results:
        if result.status != "ok":
            continue
        for finding in result.findings:
            finding_id = compute_finding_id(finding)
            prior = existing.get(finding_id)
            if prior is not None:
                merged[finding_id] = replace(prior, finding_title=finding.title)
            else:
                merged[finding_id] = Disposition(
                    status="pending", severity_override=None, note="", finding_title=finding.title,
                )
    return merged


def apply_dispositions(
    results: list[ModuleResult], dispositions: dict[str, Disposition]
) -> tuple[list[ModuleResult], list[tuple[Finding, Disposition]]]:
    """Filter/transform findings per their disposition. pending/confirmed/no
    entry -> unchanged; downgraded -> severity replaced; dismissed -> removed
    from the module's findings and returned separately for the report
    appendix. status="failed" modules pass through untouched."""
    dismissed: list[tuple[Finding, Disposition]] = []
    new_results: list[ModuleResult] = []
    for result in results:
        if result.status != "ok":
            new_results.append(result)
            continue
        kept: list[Finding] = []
        for finding in result.findings:
            disposition = dispositions.get(compute_finding_id(finding))
            if disposition is None or disposition.status in ("pending", "confirmed"):
                kept.append(finding)
            elif disposition.status == "downgraded":
                kept.append(replace(finding, severity=disposition.severity_override))
            elif disposition.status == "dismissed":
                dismissed.append((finding, disposition))
        new_results.append(replace(result, findings=kept))
    return new_results, dismissed
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
