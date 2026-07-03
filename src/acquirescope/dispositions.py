from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from acquirescope.models import Finding, Severity

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
