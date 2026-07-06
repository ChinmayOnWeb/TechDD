import json

import pytest

from git_due_diligence.dispositions import (
    Disposition,
    apply_dispositions,
    compute_finding_id,
    load_dispositions,
    merge_dispositions,
    save_dispositions,
)
from git_due_diligence.models import Evidence, Finding, ModuleResult, Severity


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


def test_merge_adds_new_findings_as_pending():
    results = [ModuleResult(module="bus_factor", status="ok", findings=[_finding()])]
    merged = merge_dispositions(results, {})
    assert len(merged) == 1
    [disposition] = merged.values()
    assert disposition.status == "pending"
    assert disposition.finding_title == "Some finding"


def test_merge_preserves_existing_and_refreshes_title():
    finding = _finding()
    fid = compute_finding_id(finding)
    existing = {fid: Disposition(status="dismissed", severity_override=None,
                                  note="stale note", finding_title="Old Title")}
    results = [ModuleResult(module="bus_factor", status="ok", findings=[finding])]
    merged = merge_dispositions(results, existing)
    assert merged[fid].status == "dismissed"
    assert merged[fid].note == "stale note"
    assert merged[fid].finding_title == "Some finding"


def test_merge_drops_stale_entries_for_findings_no_longer_present():
    existing = {"nolongerexists": Disposition(status="confirmed", severity_override=None,
                                               note="", finding_title="Gone")}
    results = [ModuleResult(module="bus_factor", status="ok", findings=[])]
    merged = merge_dispositions(results, existing)
    assert merged == {}


def test_merge_skips_failed_modules():
    results = [ModuleResult(module="hotspots", status="failed", error="boom")]
    merged = merge_dispositions(results, {})
    assert merged == {}


def test_apply_pending_and_confirmed_pass_through():
    finding = _finding()
    fid = compute_finding_id(finding)
    results = [ModuleResult(module="bus_factor", status="ok", findings=[finding])]
    dispositions = {fid: Disposition(status="confirmed", severity_override=None,
                                      note="", finding_title=finding.title)}
    filtered, dismissed = apply_dispositions(results, dispositions)
    assert filtered[0].findings == [finding]
    assert dismissed == []


def test_apply_downgraded_overrides_severity():
    finding = _finding()  # HIGH
    fid = compute_finding_id(finding)
    results = [ModuleResult(module="bus_factor", status="ok", findings=[finding])]
    dispositions = {fid: Disposition(status="downgraded", severity_override=Severity.LOW,
                                      note="minor", finding_title=finding.title)}
    filtered, dismissed = apply_dispositions(results, dispositions)
    assert filtered[0].findings[0].severity == Severity.LOW
    assert filtered[0].findings[0].title == finding.title
    assert finding.severity == Severity.HIGH  # original object untouched


def test_apply_dismissed_removed_and_captured():
    finding = _finding()
    fid = compute_finding_id(finding)
    results = [ModuleResult(module="bus_factor", status="ok", findings=[finding])]
    disposition = Disposition(status="dismissed", severity_override=None,
                               note="not real", finding_title=finding.title)
    filtered, dismissed = apply_dispositions(results, {fid: disposition})
    assert filtered[0].findings == []
    assert dismissed == [(finding, disposition)]


def test_apply_no_entry_passes_through():
    finding = _finding()
    results = [ModuleResult(module="bus_factor", status="ok", findings=[finding])]
    filtered, dismissed = apply_dispositions(results, {})
    assert filtered[0].findings == [finding]
    assert dismissed == []


def test_apply_failed_module_untouched():
    results = [ModuleResult(module="hotspots", status="failed", error="boom")]
    filtered, dismissed = apply_dispositions(results, {})
    assert filtered[0].status == "failed"
    assert filtered[0].error == "boom"
    assert dismissed == []
