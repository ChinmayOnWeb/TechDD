# AcquireScope Disposition/Triage Workflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** An analyst can review engine findings once via a JSON file (confirm / downgrade / dismiss-with-reason), and have both `acquirescope analyze` and `acquirescope model` regenerate from the dispositioned findings — with dismissals still visible in a report appendix and correctly excluded from priced valuation adjustments.

**Architecture:** A new standalone `dispositions.py` module (no changes to `models.py`) computes a stable hash-based ID per finding and provides pure `merge`/`apply` functions plus JSON load/save. The CLI inserts a single `_resolve_dispositions` call between `run_modules()` and everything downstream (report rendering, pricing) in both commands, gated behind an optional `--dispositions PATH` flag that is fully backward-compatible when omitted.

**Tech Stack:** Python 3.12, stdlib `json`/`hashlib`/`dataclasses` only — no new dependency.

**Spec:** `docs/superpowers/specs/2026-07-03-acquirescope-disposition-workflow-design.md`

## Global Constraints

- Python 3.12; source under `src/acquirescope/`, tests under `tests/`.
- `--dispositions` omitted on either command must produce byte-identical output to before this feature (regression guard, tested explicitly).
- Default is maximally conservative: no disposition entry, `pending`, or `confirmed` all render unchanged. Only explicit `dismissed` removes a finding from the report/pricing.
- Every run with `--dispositions PATH` rewrites `PATH` with the current finding set merged in (read-merge-write).
- Malformed dispositions JSON, an unknown `status`, an invalid `severity_override`, or `status == "downgraded"` with no `severity_override` are all load-time `ValueError`s → CLI catches, prints to stderr, exit 1, nothing written.
- All file I/O `encoding="utf-8"`.

## File Structure

```
src/acquirescope/dispositions.py    # new: IDs, Disposition, load/save/merge/apply
src/acquirescope/report.py          # modify: render_markdown gains dismissed appendix
src/acquirescope/cli.py             # modify: --dispositions flag on analyze + model
tests/test_dispositions.py          # new
tests/test_report.py                # modify: appendix rendering tests
tests/test_cli.py                   # modify: dispositions CLI tests + e2e gate
```

---

### Task 1: Finding IDs, Disposition dataclass, JSON load/save

**Files:**
- Create: `src/acquirescope/dispositions.py`
- Test: `tests/test_dispositions.py`

**Interfaces:**
- Consumes: `Finding`, `Evidence`, `Severity` from `acquirescope.models`.
- Produces (from `acquirescope.dispositions`): `compute_finding_id(finding: Finding) -> str` (12-hex-char deterministic hash); `Disposition` frozen dataclass with fields `status: str`, `severity_override: Severity | None`, `note: str`, `finding_title: str`; `load_dispositions(path: Path) -> dict[str, Disposition]` (raises `ValueError` on any validation failure); `save_dispositions(path: Path, target_name: str, dispositions: dict[str, Disposition]) -> None`. Tasks 2–6 import all of these.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_dispositions.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_dispositions.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'acquirescope.dispositions'`

- [ ] **Step 3: Write the implementation**

Create `src/acquirescope/dispositions.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_dispositions.py -v`
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add src/acquirescope/dispositions.py tests/test_dispositions.py
git commit -m "feat: add finding IDs and JSON disposition load/save"
```

---

### Task 2: Merge current findings with existing dispositions

**Files:**
- Modify: `src/acquirescope/dispositions.py`
- Modify: `tests/test_dispositions.py`

**Interfaces:**
- Consumes: `compute_finding_id`, `Disposition` (Task 1); `ModuleResult` from `acquirescope.models`.
- Produces: `merge_dispositions(results: list[ModuleResult], existing: dict[str, Disposition]) -> dict[str, Disposition]`. Task 5's `_resolve_dispositions` calls this.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_dispositions.py`:

```python
from acquirescope.dispositions import merge_dispositions
from acquirescope.models import ModuleResult


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_dispositions.py -v`
Expected: 4 new FAILs with `ImportError: cannot import name 'merge_dispositions'`

- [ ] **Step 3: Write the implementation**

Append to `src/acquirescope/dispositions.py`:

```python
from dataclasses import replace

from acquirescope.models import ModuleResult
```

(Add these two imports near the top, alongside the existing `from acquirescope.models import Finding, Severity` — combine into `from acquirescope.models import Finding, ModuleResult, Severity` and add `replace` to the `dataclasses` import line: `from dataclasses import dataclass, replace`.)

Then append the function at the end of the file:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_dispositions.py -v`
Expected: 11 passed

- [ ] **Step 5: Commit**

```bash
git add src/acquirescope/dispositions.py tests/test_dispositions.py
git commit -m "feat: merge current findings with existing dispositions"
```

---

### Task 3: Apply dispositions to filter and transform findings

**Files:**
- Modify: `src/acquirescope/dispositions.py`
- Modify: `tests/test_dispositions.py`

**Interfaces:**
- Consumes: `Disposition`, `compute_finding_id` (Task 1); `Finding`, `ModuleResult` (models).
- Produces: `apply_dispositions(results: list[ModuleResult], dispositions: dict[str, Disposition]) -> tuple[list[ModuleResult], list[tuple[Finding, Disposition]]]`. Task 5's `_resolve_dispositions` calls this; the second element feeds `render_markdown`'s `dismissed` parameter (Task 4).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_dispositions.py`:

```python
from acquirescope.dispositions import apply_dispositions


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_dispositions.py -v`
Expected: 5 new FAILs with `ImportError: cannot import name 'apply_dispositions'`

- [ ] **Step 3: Write the implementation**

Append to `src/acquirescope/dispositions.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_dispositions.py -v`
Expected: 16 passed

- [ ] **Step 5: Commit**

```bash
git add src/acquirescope/dispositions.py tests/test_dispositions.py
git commit -m "feat: apply dispositions to filter, downgrade, and dismiss findings"
```

---

### Task 4: Report appendix for dismissed findings

**Files:**
- Modify: `src/acquirescope/report.py`
- Modify: `tests/test_report.py`

**Interfaces:**
- Consumes: `Disposition` (Task 1), `Finding` (models).
- Produces: `render_markdown(repo_name, results, narrative=None, dismissed=None)` — `dismissed: list[tuple[Finding, Disposition]] | None = None`. Task 5's CLI wiring passes `apply_dispositions`'s second return value here.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_report.py`:

```python
from acquirescope.dispositions import Disposition


def test_dismissed_appendix_rendered_after_disclaimer():
    finding = Finding(module="bus_factor", title="Key contributor inactive: x@example.com",
                       severity=Severity.HIGH, summary="s")
    disposition = Disposition(status="dismissed", severity_override=None,
                               note="Founder, confirmed active in leadership",
                               finding_title=finding.title)
    md = render_markdown("target-repo", _sample_results(), dismissed=[(finding, disposition)])
    assert "## Appendix: Dismissed Findings (Analyst-Reviewed)" in md
    assert "Key contributor inactive: x@example.com" in md
    assert "Founder, confirmed active in leadership" in md
    assert md.index("educational analysis") < md.index("Appendix: Dismissed")


def test_no_appendix_when_nothing_dismissed():
    md = render_markdown("target-repo", _sample_results())
    assert "Appendix: Dismissed" not in md
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_report.py -v`
Expected: `test_dismissed_appendix_rendered_after_disclaimer` FAILs with `TypeError: render_markdown() got an unexpected keyword argument 'dismissed'`

- [ ] **Step 3: Write the implementation**

In `src/acquirescope/report.py`, add the import and update the signature and body:

```python
from acquirescope.dispositions import Disposition
from acquirescope.models import Finding, ModuleResult
```

(Replace the existing `from acquirescope.models import ModuleResult` line with the two lines above.)

```python
def render_markdown(
    repo_name: str,
    results: list[ModuleResult],
    narrative: str | None = None,
    dismissed: list[tuple[Finding, Disposition]] | None = None,
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_report.py -v`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add src/acquirescope/report.py tests/test_report.py
git commit -m "feat: render a dismissed-findings appendix in the markdown report"
```

---

### Task 5: CLI wiring — `--dispositions` on `analyze` and `model`

**Files:**
- Modify: `src/acquirescope/cli.py`
- Modify: `tests/test_cli.py`

**Interfaces:**
- Consumes: `load_dispositions`, `merge_dispositions`, `save_dispositions`, `apply_dispositions`, `Disposition` (Tasks 1–3); `render_markdown(..., dismissed=...)` (Task 4).
- Produces: `_resolve_dispositions(path: Path | None, target_name: str, results: list[ModuleResult]) -> tuple[list[ModuleResult], list[tuple[Finding, Disposition]]]` in `acquirescope.cli`; `--dispositions PATH` option on both `analyze` and `model` commands.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_cli.py`:

```python
import json


def test_dispositions_bootstrap_creates_pending_file(fixture_repo, tmp_path, monkeypatch):
    monkeypatch.setattr("acquirescope.modules.security.shutil.which", lambda _: None)
    out = tmp_path / "report.md"
    disp_path = tmp_path / "dispositions.json"
    result = runner.invoke(cli.app, [
        "analyze", str(fixture_repo), "--output", str(out), "--dispositions", str(disp_path),
    ])
    assert result.exit_code == 0
    assert disp_path.exists()
    data = json.loads(disp_path.read_text(encoding="utf-8"))
    assert data["dispositions"]
    assert all(v["status"] == "pending" for v in data["dispositions"].values())


def test_malformed_dispositions_file_exits_1(fixture_repo, tmp_path):
    out = tmp_path / "report.md"
    disp_path = tmp_path / "bad.json"
    disp_path.write_text("{not valid", encoding="utf-8")
    result = runner.invoke(cli.app, [
        "analyze", str(fixture_repo), "--output", str(out), "--dispositions", str(disp_path),
    ])
    assert result.exit_code == 1
    assert not out.exists()


def test_dispositions_omitted_behaves_identically_to_before(fixture_repo, tmp_path, monkeypatch):
    monkeypatch.setattr("acquirescope.modules.security.shutil.which", lambda _: None)
    out = tmp_path / "report.md"
    result = runner.invoke(cli.app, ["analyze", str(fixture_repo), "--output", str(out)])
    assert result.exit_code == 0
    md = out.read_text(encoding="utf-8")
    assert "Appendix: Dismissed" not in md
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_cli.py -v`
Expected: `test_dispositions_bootstrap_creates_pending_file` and `test_malformed_dispositions_file_exits_1` FAIL with exit code 2 (unknown option `--dispositions`)

- [ ] **Step 3: Write the implementation**

In `src/acquirescope/cli.py`, update imports:

```python
from acquirescope.dispositions import (
    Disposition,
    apply_dispositions,
    load_dispositions,
    merge_dispositions,
    save_dispositions,
)
from acquirescope.models import Finding, ModuleResult
```

(Replace the existing `from acquirescope.models import ModuleResult` line with the second line above, and add the `dispositions` import block near the other local imports.)

Add the helper function (above the `analyze` command):

```python
def _resolve_dispositions(
    path: Path | None, target_name: str, results: list[ModuleResult]
) -> tuple[list[ModuleResult], list[tuple[Finding, Disposition]]]:
    if path is None:
        return results, []
    existing = load_dispositions(path) if path.exists() else {}
    merged = merge_dispositions(results, existing)
    save_dispositions(path, target_name, merged)
    return apply_dispositions(results, merged)
```

Replace the `analyze` command with:

```python
@app.command()
def analyze(
    repo_path: Path = typer.Argument(..., exists=True, file_okay=False, help="Path to a local git repository"),
    output: Path = typer.Option(Path("dd-report.md"), "--output", "-o", help="Report output path"),
    narrative: bool = typer.Option(False, "--narrative", help="Prepend an LLM-generated, citation-verified executive narrative (requires acquirescope[llm] and an Anthropic API key)"),
    dispositions: Path = typer.Option(None, "--dispositions", help="Analyst disposition file (JSON) -- confirm/downgrade/dismiss findings; bootstrapped on first use"),
) -> None:
    """Run all due-diligence modules against REPO_PATH and write a markdown report."""
    if narrative:
        reason = _narrative_unavailable_reason()
        if reason:
            typer.echo(reason, err=True)
            raise typer.Exit(code=1)
    results = run_modules(RepoIngest(repo_path))
    try:
        results, dismissed = _resolve_dispositions(dispositions, repo_path.name, results)
    except ValueError as exc:
        typer.echo(f"Invalid dispositions file: {exc}", err=True)
        raise typer.Exit(code=1)
    narrative_text: str | None = None
    if narrative:
        try:
            narrative_text = generate_narrative(repo_path.name, results, _anthropic_complete)
        except Exception as exc:  # report must never be lost to a narrative failure
            typer.echo(f"Warning: narrative generation failed ({exc}); writing report without it.", err=True)
    output.write_text(render_markdown(repo_path.name, results, narrative_text, dismissed), encoding="utf-8")
    typer.echo(f"Report written to {output}")
```

Replace the `model` command with:

```python
@app.command()
def model(
    repo_path: Path = typer.Argument(..., exists=True, file_okay=False, help="Path to a local git repository"),
    assumptions_file: Path = typer.Option(..., "--assumptions", "-a", exists=True, dir_okay=False, help="Analyst assumptions TOML"),
    output: Path = typer.Option(Path("dd-model.xlsx"), "--output", "-o", help="Excel model output path"),
    dispositions: Path = typer.Option(None, "--dispositions", help="Analyst disposition file (JSON) -- confirm/downgrade/dismiss findings before pricing"),
) -> None:
    """Run the engine, price the findings, and write the Excel valuation model."""
    try:
        assumptions = load_assumptions(assumptions_file)
    except ValueError as exc:
        typer.echo(f"Invalid assumptions: {exc}", err=True)
        raise typer.Exit(code=1)

    results = run_modules(RepoIngest(repo_path))
    try:
        results, _dismissed = _resolve_dispositions(dispositions, repo_path.name, results)
    except ValueError as exc:
        typer.echo(f"Invalid dispositions file: {exc}", err=True)
        raise typer.Exit(code=1)
    comps = comps_valuation(assumptions)
    dcf = dcf_valuation(assumptions)
    pre_dd_ev_mid = blended_pre_dd_ev_mid(comps, dcf)
    adjustments = price_adjustments(results, assumptions, pre_dd_ev_mid)
    total_adjustment_mid = sum(adj.mid for adj in adjustments)
    grid = sensitivity_grid(assumptions, total_adjustment_mid)
    write_model(output, assumptions, adjustments, comps, dcf,
                dcf_scenarios(assumptions), grid)
    typer.echo(f"Model written to {output}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_cli.py -v`
Expected: all pass, including the 3 new dispositions tests

- [ ] **Step 5: Commit**

```bash
git add src/acquirescope/cli.py tests/test_cli.py
git commit -m "feat: wire --dispositions into analyze and model commands"
```

---

### Task 6: End-to-end dismiss-workflow regression gate

**Files:**
- Modify: `tests/test_cli.py`

**Interfaces:**
- Consumes: the full pipeline from Tasks 1–5 and the fixture's planted "Key contributor inactive: dave@example.com" finding (bus_factor).
- Produces: the spec's mandated regression gate — a two-run dismiss workflow correctly removes a finding from the report body, shows it in the appendix, and drops its contribution to priced Key-person retention.

- [ ] **Step 1: Write the regression tests**

Append to `tests/test_cli.py`:

```python
def _dismiss_dave_inactive_finding(disp_path: Path) -> None:
    data = json.loads(disp_path.read_text(encoding="utf-8"))
    target_id = next(
        fid for fid, v in data["dispositions"].items()
        if v["finding_title"] == "Key contributor inactive: dave@example.com"
    )
    data["dispositions"][target_id]["status"] = "dismissed"
    data["dispositions"][target_id]["note"] = "Confirmed still active via LinkedIn"
    disp_path.write_text(json.dumps(data), encoding="utf-8")


def test_dismissed_disposition_removes_finding_from_report(fixture_repo, tmp_path, monkeypatch):
    monkeypatch.setattr("acquirescope.modules.security.shutil.which", lambda _: None)
    out = tmp_path / "report.md"
    disp_path = tmp_path / "dispositions.json"
    # First run: bootstrap the dispositions file (all pending).
    runner.invoke(cli.app, ["analyze", str(fixture_repo), "--output", str(out), "--dispositions", str(disp_path)])
    _dismiss_dave_inactive_finding(disp_path)

    # Second run: apply the analyst's dismissal.
    result = runner.invoke(cli.app, ["analyze", str(fixture_repo), "--output", str(out), "--dispositions", str(disp_path)])
    assert result.exit_code == 0
    md = out.read_text(encoding="utf-8")
    body, _, appendix = md.partition("## Appendix: Dismissed Findings")
    assert "Key contributor inactive: dave@example.com" not in body
    assert "Key contributor inactive: dave@example.com" in appendix
    assert "Confirmed still active via LinkedIn" in appendix


def test_dismissed_finding_excluded_from_model_pricing(fixture_repo, tmp_path, monkeypatch):
    from openpyxl import load_workbook

    monkeypatch.setattr("acquirescope.modules.security.shutil.which", lambda _: None)
    example = Path(__file__).parent.parent / "examples" / "assumptions.example.toml"
    out = tmp_path / "report.md"
    disp_path = tmp_path / "dispositions.json"
    runner.invoke(cli.app, ["analyze", str(fixture_repo), "--output", str(out), "--dispositions", str(disp_path)])
    _dismiss_dave_inactive_finding(disp_path)

    xlsx_out = tmp_path / "model.xlsx"
    result = runner.invoke(cli.app, [
        "model", str(fixture_repo), "--assumptions", str(example),
        "--output", str(xlsx_out), "--dispositions", str(disp_path),
    ])
    assert result.exit_code == 0
    wb = load_workbook(xlsx_out)
    adj = wb["DD Adjustments"]
    # Fixture's bus_factor produces exactly 2 findings normally (payments/
    # single-owner + dave inactive); with dave dismissed, only 1 remains,
    # so retention prices at 1 x $300,000 instead of 2 x $300,000.
    assert adj["C3"].value == 300_000
```

- [ ] **Step 2: Run the full suite**

Run: `pytest -v`
Expected: ALL tests pass (99 total: 76 before this feature + 16 in test_dispositions.py + 2 in test_report.py + 5 in test_cli.py). If only these two e2e tests fail, a task 1–5 unit test localizes which layer regressed.

- [ ] **Step 3: Commit**

```bash
git add tests/test_cli.py
git commit -m "test: add end-to-end dismiss-workflow regression gate"
```

---

## Self-review notes

- **Spec coverage:** stable finding IDs ✓ (Task 1), JSON load/save with all four validation rules ✓ (Task 1, including the downgraded-without-severity ambiguity fix from spec self-review), merge (new/keep/drop) ✓ (Task 2), apply (pending/confirmed pass-through, downgrade, dismiss) ✓ (Task 3), report appendix positioned after the disclaimer ✓ (Task 4), CLI wiring on both `analyze` and `model` with fail-fast error handling and full backward compatibility when `--dispositions` is omitted ✓ (Task 5), pricing integration verified end-to-end ✓ (Task 6). Out-of-scope items (triage progress summary, bulk dispositioning, materiality weighting) are correctly not present anywhere in this plan.
- **Type consistency:** `apply_dispositions` and `_resolve_dispositions` both return `tuple[list[ModuleResult], list[tuple[Finding, Disposition]]]` identically; `render_markdown`'s `dismissed` parameter type matches that second tuple element exactly; `Disposition` field names (`status`, `severity_override`, `note`, `finding_title`) are identical across Tasks 1–6's every usage.
- **Backward-compatibility guard is explicit:** Task 5's `test_dispositions_omitted_behaves_identically_to_before` and Task 6's fixture math (2 bus_factor findings baseline, confirmed against existing Phase 1 tests `test_flags_single_owner_directory` + `test_flags_inactive_key_contributor`) both directly verify the spec's "byte-identical when omitted" and "conservative default" requirements rather than assuming them.
