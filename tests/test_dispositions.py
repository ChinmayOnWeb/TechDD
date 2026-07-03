import json

import pytest

from acquirescope.dispositions import Disposition, compute_finding_id, load_dispositions, save_dispositions
from acquirescope.models import Evidence, Finding, Severity


def _finding(title="Some finding", path="a/b.py", detail="x") -> Finding:
    return Finding(
        module="bus_factor", title=title, severity=Severity.HIGH, summary="s",
        evidence=[Evidence(description="d", path=path, detail=detail)],
    )


def test_id_is_deterministic_for_same_content():
    assert compute_finding_id(_finding()) == compute_finding_id(_finding())


def test_id_changes_with_title():
    assert compute_finding_id(_finding(title="A")) != compute_finding_id(_finding(title="B"))


def test_id_changes_with_evidence():
    assert compute_finding_id(_finding(path="a/b.py")) != compute_finding_id(_finding(path="c/d.py"))


def test_save_and_load_round_trip(tmp_path):
    path = tmp_path / "dispositions.json"
    original = {
        "abc123": Disposition(status="dismissed", severity_override=None, note="not real", finding_title="X"),
        "def456": Disposition(status="downgraded", severity_override=Severity.LOW, note="minor", finding_title="Y"),
    }
    save_dispositions(path, "target-repo", original)
    loaded = load_dispositions(path)
    assert loaded == original


def test_load_rejects_unknown_status(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text(json.dumps({"dispositions": {
        "x": {"status": "maybe", "severity_override": None, "note": "", "finding_title": ""},
    }}), encoding="utf-8")
    with pytest.raises(ValueError, match="unknown disposition status"):
        load_dispositions(path)


def test_load_rejects_downgraded_without_severity(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text(json.dumps({"dispositions": {
        "x": {"status": "downgraded", "severity_override": None, "note": "", "finding_title": ""},
    }}), encoding="utf-8")
    with pytest.raises(ValueError, match="no severity_override"):
        load_dispositions(path)


def test_load_rejects_malformed_json(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text("{not valid json", encoding="utf-8")
    with pytest.raises(ValueError, match="invalid dispositions JSON"):
        load_dispositions(path)
