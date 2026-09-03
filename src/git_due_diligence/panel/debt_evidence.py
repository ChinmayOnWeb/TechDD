"""Validated, filing-backed evidence for debt classifications.

The ledger is deliberately separate from CompanyFacts extraction.  In
particular, a missing CompanyFacts concept is never interpreted as zero.
"""
from __future__ import annotations

import re
import csv
import tomllib
from urllib.parse import urlsplit
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Mapping

DEBT_EVIDENCE_SCHEMA_VERSION = 1
DEBT_STATUSES = frozenset({
    "REPORTED_NONZERO",
    "REPORTED_ZERO",
    "ZERO_SUPPORTED_BY_FILINGS",
    "UNSUPPORTED_XBRL_CONCEPT",
    "NOTE_ONLY",
    "COMPANYFACTS_GAP",
    "MATCHING_GAP",
    "UNRESOLVED",
})
NUMERIC_DEBT_STATUSES = frozenset({
    "REPORTED_NONZERO", "REPORTED_ZERO", "ZERO_SUPPORTED_BY_FILINGS",
})
_ACCESSION = re.compile(r"^\d{10}-\d{2}-\d{6}$")


@dataclass(frozen=True)
class DebtEvidence:
    firm: str
    cik: str
    quarter_end: date
    classification: str
    accession: str
    filing_date: date
    filing_form: str
    evidence_location: str
    evidence_note: str
    source_url: str
    immutable_evidence_id: str
    reviewer: str
    reviewed_at: datetime


_REQUIRED = frozenset(DebtEvidence.__dataclass_fields__)


def load_firm_identities(path: Path) -> dict[str, str]:
    """Load the canonical slug/CIK identity columns from the candidate audit."""
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows or not {"slug", "cik"}.issubset(rows[0]):
        raise ValueError(f"identity file {path} must contain slug and cik columns")
    identities: dict[str, str] = {}
    for row in rows:
        if row["slug"] in identities:
            raise ValueError(f"duplicate identity slug: {row['slug']}")
        identities[row["slug"]] = str(row["cik"]).zfill(10)
    return identities


def load_debt_evidence(
    path: Path, identities: Mapping[str, str],
) -> dict[tuple[str, date], DebtEvidence]:
    """Load and strictly validate a debt ledger, indexed by firm and quarter."""
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ValueError(f"invalid debt evidence ledger {path}: {exc}") from exc
    if raw.get("schema_version") != DEBT_EVIDENCE_SCHEMA_VERSION:
        raise ValueError(
            f"debt evidence schema_version must be {DEBT_EVIDENCE_SCHEMA_VERSION}")

    result: dict[tuple[str, date], DebtEvidence] = {}
    for number, entry in enumerate(raw.get("records", []), start=1):
        missing = sorted(_REQUIRED - entry.keys())
        if missing:
            raise ValueError(
                f"debt evidence record {number} missing fields: {', '.join(missing)}")
        extra = sorted(entry.keys() - _REQUIRED)
        if extra:
            raise ValueError(
                f"debt evidence record {number} has unknown fields: {', '.join(extra)}")
        status = entry["classification"]
        if status not in DEBT_STATUSES:
            raise ValueError(f"debt evidence record {number} has unknown status {status!r}")
        quarter = entry["quarter_end"]
        filing_date = entry["filing_date"]
        reviewed_at = entry["reviewed_at"]
        if not isinstance(quarter, date) or isinstance(quarter, datetime):
            raise ValueError(f"debt evidence record {number} has malformed quarter_end")
        if not isinstance(filing_date, date) or isinstance(filing_date, datetime):
            raise ValueError(f"debt evidence record {number} has malformed filing_date")
        if not isinstance(reviewed_at, datetime) or reviewed_at.tzinfo is None:
            raise ValueError(f"debt evidence record {number} has malformed reviewed_at")
        firm = entry["firm"]
        cik = str(entry["cik"]).zfill(10)
        expected_cik = identities.get(firm)
        if expected_cik is None:
            raise ValueError(f"debt evidence record {number} has unknown firm {firm!r}")
        if cik != str(expected_cik).zfill(10):
            raise ValueError(
                f"debt evidence CIK mismatch for {firm}: expected "
                f"{str(expected_cik).zfill(10)}, found {cik}")
        accession = entry["accession"]
        if not isinstance(accession, str) or not _ACCESSION.fullmatch(accession):
            raise ValueError(f"debt evidence record {number} has malformed accession")
        for field in (
            "filing_form", "evidence_location", "evidence_note", "source_url",
            "immutable_evidence_id", "reviewer",
        ):
            if not isinstance(entry[field], str) or not entry[field].strip():
                raise ValueError(
                    f"debt evidence record {number} has empty provenance field {field}")
        expected_evidence_id = f"sec-accession:{accession}"
        if entry["immutable_evidence_id"] != expected_evidence_id:
            raise ValueError(
                f"debt evidence record {number} immutable_evidence_id must equal "
                f"{expected_evidence_id!r}")
        source = urlsplit(entry["source_url"])
        expected_prefix = (
            "/Archives/edgar/data/"
            f"{int(cik)}/{accession.replace('-', '')}/"
        )
        if (source.scheme != "https" or source.netloc != "www.sec.gov"
                or not source.path.startswith(expected_prefix)
                or source.query or source.fragment):
            raise ValueError(
                f"debt evidence record {number} source_url must identify the canonical "
                f"SEC Archives path {expected_prefix!r}")
        key = (firm, quarter)
        if key in result:
            raise ValueError(f"duplicate debt evidence for {firm} {quarter.isoformat()}")
        result[key] = DebtEvidence(**{**entry, "cik": cik})
    return result


def resolve_debt(
    reported_value: float | None, evidence: DebtEvidence | None,
) -> tuple[float | None, str]:
    """Apply the fail-closed CompanyFacts/ledger precedence contract."""
    if reported_value is not None:
        if (evidence is not None
                and evidence.classification == "ZERO_SUPPORTED_BY_FILINGS"
                and reported_value != 0.0):
            raise ValueError(
                f"debt evidence conflict for {evidence.firm} "
                f"{evidence.quarter_end.isoformat()}: ledger says zero but "
                f"CompanyFacts reports {reported_value}")
        return reported_value, "REPORTED_ZERO" if reported_value == 0.0 else "REPORTED_NONZERO"
    if evidence is not None and evidence.classification == "ZERO_SUPPORTED_BY_FILINGS":
        return 0.0, "ZERO_SUPPORTED_BY_FILINGS"
    return None, evidence.classification if evidence is not None else "UNRESOLVED"
