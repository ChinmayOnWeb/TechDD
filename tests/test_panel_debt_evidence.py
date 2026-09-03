from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from git_due_diligence.panel.debt_evidence import (
    load_debt_evidence,
    resolve_debt,
)
from git_due_diligence.panel.recovery import sha256_file


IDENTITIES = {"acme": "0000000001"}


def _ledger(**changes) -> str:
    fields = {
        "firm": '"acme"',
        "cik": '"0000000001"',
        "quarter_end": "2024-03-31",
        "classification": '"ZERO_SUPPORTED_BY_FILINGS"',
        "accession": '"0000000001-24-000001"',
        "filing_date": "2024-05-01",
        "filing_form": '"10-Q"',
        "evidence_location": '"Balance sheet and debt note"',
        "evidence_note": '"Facility explicitly had no outstanding balance."',
        "source_url": '"https://www.sec.gov/Archives/edgar/data/1/000000000124000001/"',
        "immutable_evidence_id": '"sec-accession:0000000001-24-000001"',
        "reviewer": '"Researcher"',
        "reviewed_at": "2024-05-02T00:00:00Z",
    }
    fields.update(changes)
    return "schema_version = 1\n\n[[records]]\n" + "".join(
        f"{key} = {value}\n" for key, value in fields.items())


def _load(tmp_path: Path, body: str | None = None):
    path = tmp_path / "debt.toml"
    path.write_text(body or _ledger(), encoding="utf-8")
    return load_debt_evidence(path, IDENTITIES)


def test_valid_zero_supported_by_filings_record_loads(tmp_path):
    records = _load(tmp_path)
    record = records[("acme", date(2024, 3, 31))]
    assert record.classification == "ZERO_SUPPORTED_BY_FILINGS"
    assert record.accession == "0000000001-24-000001"


def test_duplicate_firm_quarter_rejected(tmp_path):
    record = _ledger().split("[[records]]\n", 1)[1]
    with pytest.raises(ValueError, match="duplicate debt evidence"):
        _load(tmp_path, _ledger() + "\n[[records]]\n" + record)


def test_invalid_status_rejected(tmp_path):
    with pytest.raises(ValueError, match="unknown status"):
        _load(tmp_path, _ledger(classification='"DEBT_FREEISH"'))


def test_malformed_quarter_rejected(tmp_path):
    with pytest.raises(ValueError, match="malformed quarter_end"):
        _load(tmp_path, _ledger(quarter_end='"March 2024"'))


def test_cik_mismatch_rejected(tmp_path):
    with pytest.raises(ValueError, match="CIK mismatch"):
        _load(tmp_path, _ledger(cik='"0000000002"'))


def test_missing_required_provenance_rejected(tmp_path):
    body = _ledger().replace('evidence_location = "Balance sheet and debt note"\n', "")
    with pytest.raises(ValueError, match="missing fields: evidence_location"):
        _load(tmp_path, body)


@pytest.mark.parametrize("source_url", [
    '"http://www.sec.gov/Archives/edgar/data/1/000000000124000001/"',
    '"https://sec.gov/Archives/edgar/data/1/000000000124000001/"',
    '"https://www.sec.gov.example/Archives/edgar/data/1/000000000124000001/"',
    '"https://www.sec.gov/Archives/edgar/data/2/000000000124000001/"',
    '"https://www.sec.gov/Archives/edgar/data/1/999999999924000001/000000000124000001/"',
])
def test_noncanonical_sec_source_url_rejected(tmp_path, source_url):
    with pytest.raises(ValueError, match="canonical SEC Archives path"):
        _load(tmp_path, _ledger(source_url=source_url))


def test_immutable_evidence_id_must_exactly_match_accession(tmp_path):
    with pytest.raises(ValueError, match="immutable_evidence_id must equal"):
        _load(tmp_path, _ledger(
            immutable_evidence_id='"prefix:0000000001-24-000001:suffix"'))


@pytest.mark.parametrize(("reported", "status", "expected"), [
    (100.0, None, 100.0),
    (0.0, None, 0.0),
    (0.0, "ZERO_SUPPORTED_BY_FILINGS", 0.0),
    (None, "ZERO_SUPPORTED_BY_FILINGS", 0.0),
    (None, None, None),
    (None, "UNRESOLVED", None),
    (None, "UNSUPPORTED_XBRL_CONCEPT", None),
])
def test_numeric_debt_semantics(tmp_path, reported, status, expected):
    record = None
    if status:
        record = next(iter(_load(tmp_path, _ledger(classification=f'"{status}"')).values()))
    assert resolve_debt(reported, record)[0] == expected


def test_reported_nonzero_conflicts_with_zero_ledger(tmp_path):
    record = next(iter(_load(tmp_path).values()))
    with pytest.raises(ValueError, match="ledger says zero"):
        resolve_debt(100.0, record)


def test_ledger_hash_is_deterministic_and_content_sensitive(tmp_path):
    path = tmp_path / "debt.toml"
    path.write_text(_ledger(), encoding="utf-8")
    first = sha256_file(path)
    assert sha256_file(path) == first
    path.write_text(_ledger(evidence_note='"Different reviewed evidence."'), encoding="utf-8")
    assert sha256_file(path) != first
