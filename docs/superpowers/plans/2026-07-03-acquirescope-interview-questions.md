# AcquireScope Interview Questions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `acquirescope analyze --questions` generates one exploratory "question for management" per non-INFO finding via an LLM call, keyed to real finding IDs so hallucinated references can't leak into the report.

**Architecture:** A new `interview_questions.py` module mirrors `narrative.py`'s exact shape (build prompt → call → validate) but validates structurally (strict JSON, real finding IDs) rather than via citation-parsing, since a question isn't a factual claim needing citation. `report.py` gains an optional `questions` parameter rendered per-finding. `cli.py` renames the LLM-availability check to a name shared by both `--narrative` and `--questions`, and wires the new flag through the same fail-fast-on-missing-key / degrade-gracefully-on-call-failure posture already established for narrative.

**Tech Stack:** Python 3.12, existing `acquirescope[llm]` optional extra (no new dependency), reuses `compute_finding_id` from `acquirescope.dispositions`.

**Spec:** `docs/superpowers/specs/2026-07-03-acquirescope-interview-questions-design.md`

## Global Constraints

- Python 3.12; source under `src/acquirescope/`, tests under `tests/`.
- `--questions` requires the same `anthropic` package + `ANTHROPIC_API_KEY`/`ANTHROPIC_AUTH_TOKEN` check as `--narrative` — missing either fails fast (stderr message, exit 1) before any analysis runs.
- A question-generation failure after analysis has run must never lose the report: warning to stderr, report written without the questions section, exit 0.
- Only findings with `severity != Severity.INFO` get a question generated.
- A finding ID in the LLM's response that doesn't match a real finding is silently dropped, not an error. Structurally invalid JSON (not JSON at all, not an object, or non-string values) IS an error.
- `model` command is unaffected — no `--questions` flag there, no equivalent surface to attach a question to.

## File Structure

```
src/acquirescope/interview_questions.py   # new: build_questions_prompt, parse_questions_response, generate_questions
src/acquirescope/report.py                # modify: render_markdown gains questions param
src/acquirescope/cli.py                   # modify: rename to _llm_unavailable_reason, add --questions
tests/test_interview_questions.py         # new
tests/test_report.py                      # modify: question-line rendering tests
tests/test_cli.py                         # modify: rename references, --questions tests, e2e gate
```

---

### Task 1: Interview questions module

**Files:**
- Create: `src/acquirescope/interview_questions.py`
- Test: `tests/test_interview_questions.py`

**Interfaces:**
- Consumes: `compute_finding_id` from `acquirescope.dispositions`; `ModuleResult`, `Severity` from `acquirescope.models`.
- Produces (from `acquirescope.interview_questions`): `build_questions_prompt(repo_name: str, results: list[ModuleResult]) -> tuple[str, set[str]]`; `parse_questions_response(text: str, valid_ids: set[str]) -> dict[str, str]` (raises `ValueError` on structurally invalid JSON); `generate_questions(repo_name: str, results: list[ModuleResult], complete: Callable[[str], str]) -> dict[str, str]`. Task 3's CLI calls `generate_questions`; Task 2's report rendering consumes its `dict[str, str]` return shape (finding ID -> question).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_interview_questions.py`:

```python
import json

import pytest

from acquirescope.interview_questions import (
    build_questions_prompt,
    generate_questions,
    parse_questions_response,
)
from acquirescope.models import Finding, ModuleResult, Severity


def _results() -> list[ModuleResult]:
    return [
        ModuleResult(
            module="bus_factor", status="ok",
            findings=[
                Finding("bus_factor", "Single point of failure: payments/", Severity.HIGH, "one owner"),
            ],
        ),
        ModuleResult(
            module="licenses", status="ok",
            findings=[
                Finding("licenses", "Repository license: MIT", Severity.INFO, "MIT license"),
            ],
        ),
        ModuleResult(module="hotspots", status="failed", error="boom"),
    ]


def test_prompt_excludes_info_findings_and_failed_modules():
    prompt, valid_ids = build_questions_prompt("target", _results())
    assert len(valid_ids) == 1
    assert "Single point of failure: payments/" in prompt
    assert "Repository license: MIT" not in prompt


def test_parse_drops_hallucinated_ids():
    _, valid_ids = build_questions_prompt("target", _results())
    [real_id] = valid_ids
    response = json.dumps({real_id: "Who owns payments/?", "bogus000000": "Fake question"})
    result = parse_questions_response(response, valid_ids)
    assert result == {real_id: "Who owns payments/?"}


def test_parse_rejects_malformed_json():
    with pytest.raises(ValueError, match="not valid JSON"):
        parse_questions_response("{not json", {"abc"})


def test_parse_rejects_wrong_shape():
    with pytest.raises(ValueError, match="string -> string"):
        parse_questions_response(json.dumps(["not", "an", "object"]), {"abc"})
    with pytest.raises(ValueError, match="string -> string"):
        parse_questions_response(json.dumps({"abc": 123}), {"abc"})


def test_generate_questions_orchestrates():
    def fake_complete(prompt: str) -> str:
        _, valid_ids = build_questions_prompt("target", _results())
        [real_id] = valid_ids
        assert real_id in prompt
        return json.dumps({real_id: "Who owns payments/?"})

    result = generate_questions("target", _results(), fake_complete)
    assert list(result.values()) == ["Who owns payments/?"]


def test_generate_questions_propagates_completer_exception():
    def boom(prompt: str) -> str:
        raise RuntimeError("api down")

    with pytest.raises(RuntimeError, match="api down"):
        generate_questions("target", _results(), boom)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_interview_questions.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'acquirescope.interview_questions'`

- [ ] **Step 3: Write the implementation**

Create `src/acquirescope/interview_questions.py`:

```python
from __future__ import annotations

import json
from typing import Callable

from acquirescope.dispositions import compute_finding_id
from acquirescope.models import ModuleResult, Severity

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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_interview_questions.py -v`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add src/acquirescope/interview_questions.py tests/test_interview_questions.py
git commit -m "feat: add LLM-generated interview questions with ID validation"
```

---

### Task 2: Report rendering

**Files:**
- Modify: `src/acquirescope/report.py`
- Modify: `tests/test_report.py`

**Interfaces:**
- Consumes: `compute_finding_id` from `acquirescope.dispositions` (already imports `Disposition` from there — extend the import).
- Produces: `render_markdown(repo_name, results, narrative=None, dismissed=None, questions=None)` — `questions: dict[str, str] | None = None`. Task 3's CLI passes `generate_questions`'s return value here.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_report.py`:

```python
def test_question_rendered_for_matching_finding():
    finding = _sample_results()[0].findings[0]
    from acquirescope.dispositions import compute_finding_id
    fid = compute_finding_id(finding)
    md = render_markdown("target-repo", _sample_results(), questions={fid: "Who owns this dependency risk?"})
    assert "**Question for management:** Who owns this dependency risk?" in md


def test_no_question_line_when_no_match():
    md = render_markdown("target-repo", _sample_results(), questions={"nonexistent000": "orphan question"})
    assert "Question for management" not in md


def test_dismissed_finding_never_shows_question():
    from acquirescope.dispositions import Disposition, compute_finding_id
    finding = _sample_results()[0].findings[0]
    fid = compute_finding_id(finding)
    disposition = Disposition(status="dismissed", severity_override=None, note="not real", finding_title=finding.title)
    md = render_markdown(
        "target-repo", _sample_results(), dismissed=[(finding, disposition)],
        questions={fid: "Should not appear"},
    )
    assert "Should not appear" not in md
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_report.py -v`
Expected: `test_question_rendered_for_matching_finding` and `test_dismissed_finding_never_shows_question` FAIL with `TypeError: render_markdown() got an unexpected keyword argument 'questions'`. `test_no_question_line_when_no_match` passes vacuously (no error, but not meaningfully testing anything yet) — that's expected at this stage.

- [ ] **Step 3: Write the implementation**

In `src/acquirescope/report.py`, update the import:

```python
from acquirescope.dispositions import Disposition, compute_finding_id
```

(Replace the existing `from acquirescope.dispositions import Disposition` line with the line above.)

Update the signature:

```python
def render_markdown(
    repo_name: str,
    results: list[ModuleResult],
    narrative: str | None = None,
    dismissed: list[tuple[Finding, Disposition]] | None = None,
    questions: dict[str, str] | None = None,
) -> str:
```

In the main findings-rendering loop, after the evidence lines and before the trailing `lines.append("")`, add the question line. The relevant block currently reads:

```python
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
```

Replace it with:

```python
        for finding in result.findings:
            lines.append(f"### [{finding.severity.value.upper()}] {finding.title}")
            lines.append("")
            lines.append(finding.summary)
            lines.append("")
            for ev in finding.evidence:
                location = f" (`{ev.path}`)" if ev.path else ""
                detail = f" — {ev.detail}" if ev.detail else ""
                lines.append(f"- Evidence: {ev.description}{location}{detail}")
            if questions and (question := questions.get(compute_finding_id(finding))):
                lines.append("")
                lines.append(f"**Question for management:** {question}")
            lines.append("")
```

Note this loop only ever touches `result.findings` (the main body) — the dismissed-appendix loop further down builds its own separate lines and never calls `questions.get(...)`, so a dismissed finding's ID matching an entry in `questions` has no effect there. This is what `test_dismissed_finding_never_shows_question` verifies.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_report.py -v`
Expected: 9 passed

- [ ] **Step 5: Commit**

```bash
git add src/acquirescope/report.py tests/test_report.py
git commit -m "feat: render per-finding interview questions in the markdown report"
```

---

### Task 3: CLI wiring and end-to-end regression gate

**Files:**
- Modify: `src/acquirescope/cli.py`
- Modify: `tests/test_cli.py`

**Interfaces:**
- Consumes: `generate_questions` (Task 1); `render_markdown(..., questions=...)` (Task 2).
- Produces: `_llm_unavailable_reason()` in `acquirescope.cli` (renamed from `_narrative_unavailable_reason`, same body); `--questions` boolean flag on `analyze`.

- [ ] **Step 1: Update existing tests for the rename, then write the new failing tests**

In `tests/test_cli.py`, every existing `monkeypatch.setattr(cli, "_narrative_unavailable_reason", ...)` call must become `monkeypatch.setattr(cli, "_llm_unavailable_reason", ...)`. There are three call sites — in `test_narrative_unavailable_exits_1`, `test_narrative_section_written_with_fake_completer`, and `test_narrative_api_failure_degrades_to_plain_report`. Update all three occurrences of the string `"_narrative_unavailable_reason"` to `"_llm_unavailable_reason"`.

Then append the new tests at the end of the file:

```python
def test_questions_unavailable_exits_1(fixture_repo, tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "_llm_unavailable_reason", lambda: "no key")
    out = tmp_path / "r.md"
    result = runner.invoke(cli.app, ["analyze", str(fixture_repo), "--output", str(out), "--questions"])
    assert result.exit_code == 1
    assert not out.exists()


def test_questions_rendered_with_fake_completer(fixture_repo, tmp_path, monkeypatch):
    monkeypatch.setattr("acquirescope.modules.security.shutil.which", lambda _: None)
    monkeypatch.setattr(cli, "_llm_unavailable_reason", lambda: None)

    def fake_complete(prompt: str) -> str:
        import re
        real_id = re.search(r"\[([0-9a-f]{12})\] .*Single point of failure: payments/", prompt).group(1)
        return json.dumps({real_id: "Who owns payments/ if the current maintainer is unavailable?",
                            "bogus000000": "Should be dropped"})

    monkeypatch.setattr(cli, "_anthropic_complete", fake_complete)
    out = tmp_path / "r.md"
    result = runner.invoke(cli.app, ["analyze", str(fixture_repo), "--output", str(out), "--questions"])
    assert result.exit_code == 0
    md = out.read_text(encoding="utf-8")
    assert "**Question for management:** Who owns payments/ if the current maintainer is unavailable?" in md
    assert "Should be dropped" not in md


def test_questions_failure_degrades_to_plain_report(fixture_repo, tmp_path, monkeypatch):
    monkeypatch.setattr("acquirescope.modules.security.shutil.which", lambda _: None)
    monkeypatch.setattr(cli, "_llm_unavailable_reason", lambda: None)

    def boom(prompt: str) -> str:
        raise RuntimeError("api down")

    monkeypatch.setattr(cli, "_anthropic_complete", boom)
    out = tmp_path / "r.md"
    result = runner.invoke(cli.app, ["analyze", str(fixture_repo), "--output", str(out), "--questions"])
    assert result.exit_code == 0
    md = out.read_text(encoding="utf-8")
    assert "Question for management" not in md
    assert "# Technical Due Diligence Report:" in md
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_cli.py -v`
Expected: the three renamed tests FAIL (monkeypatch target `_llm_unavailable_reason` doesn't exist yet on `cli`, so `setattr` raises `AttributeError`); the three new `--questions` tests FAIL with exit code 2 (unknown option).

- [ ] **Step 3: Write the implementation**

In `src/acquirescope/cli.py`, add the import:

```python
from acquirescope.interview_questions import generate_questions
```

(Add this alongside the existing `from acquirescope.narrative import generate_narrative` line.)

Rename the function:

```python
def _llm_unavailable_reason() -> str | None:
    try:
        import anthropic  # noqa: F401
    except ImportError:
        return "this feature requires the anthropic package: pip install acquirescope[llm]"
    if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
        return "this feature requires ANTHROPIC_API_KEY (or ANTHROPIC_AUTH_TOKEN) in the environment"
    return None
```

Replace the `analyze` command with:

```python
@app.command()
def analyze(
    repo_path: Path = typer.Argument(..., exists=True, file_okay=False, help="Path to a local git repository"),
    output: Path = typer.Option(Path("dd-report.md"), "--output", "-o", help="Report output path"),
    narrative: bool = typer.Option(False, "--narrative", help="Prepend an LLM-generated, citation-verified executive narrative (requires acquirescope[llm] and an Anthropic API key)"),
    questions: bool = typer.Option(False, "--questions", help="Generate an LLM-written 'question for management' per finding (requires acquirescope[llm] and an Anthropic API key)"),
    dispositions: Path = typer.Option(None, "--dispositions", help="Analyst disposition file (JSON) -- confirm/downgrade/dismiss findings; bootstrapped on first use"),
) -> None:
    """Run all due-diligence modules against REPO_PATH and write a markdown report."""
    if narrative or questions:
        reason = _llm_unavailable_reason()
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
    questions_map: dict[str, str] = {}
    if questions:
        try:
            questions_map = generate_questions(repo_path.name, results, _anthropic_complete)
        except Exception as exc:  # report must never be lost to a question-generation failure
            typer.echo(f"Warning: question generation failed ({exc}); writing report without them.", err=True)
    output.write_text(
        render_markdown(repo_path.name, results, narrative_text, dismissed, questions_map),
        encoding="utf-8",
    )
    typer.echo(f"Report written to {output}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_cli.py -v`
Expected: all pass, including the 3 renamed and 3 new tests.

- [ ] **Step 5: Run the full suite**

Run: `pytest -v`
Expected: ALL tests pass (111 total: 99 before this feature + 6 in test_interview_questions.py + 3 in test_report.py + 3 new in test_cli.py -- the 3 renamed tests are edits to existing tests, not additions).

- [ ] **Step 6: Commit**

```bash
git add src/acquirescope/cli.py tests/test_cli.py
git commit -m "feat: wire --questions into analyze; share LLM-availability check with --narrative"
```

---

## Self-review notes

- **Spec coverage:** prompt building excludes INFO findings and failed modules ✓ (Task 1), structural JSON validation (malformed -> error, wrong shape -> error, unknown ID -> silently dropped) ✓ (Task 1), orchestration with exception propagation ✓ (Task 1), report rendering only for main-body findings never the dismissed appendix ✓ (Task 2), shared `_llm_unavailable_reason` rename ✓ (Task 3), `--questions` fail-fast-before-analysis and degrade-gracefully-after-analysis ✓ (Task 3). `model` command correctly untouched anywhere in this plan.
- **Type consistency:** `generate_questions` returns `dict[str, str]` (finding ID -> question), matching exactly what `render_markdown`'s new `questions` parameter and the CLI's `questions_map` variable expect. `build_questions_prompt`'s `tuple[str, set[str]]` return matches `narrative.build_prompt`'s existing shape, so `parse_questions_response(text, valid_ids)` and `narrative.verify_citations(text, valid_ids)` take the same `set[str]` shape for their second argument -- consistent with the established pattern in this codebase.
- **Rename blast radius double-checked:** grepped the plan's own tests for every prior reference to `_narrative_unavailable_reason` (three call sites in `test_cli.py`) and confirmed Task 3 Step 1 updates all three before Task 3 Step 3 removes the old name -- otherwise Task 3's Step 2 "run to verify failure" would show failures for the wrong reason (AttributeError from a stale monkeypatch target, not the intended missing-flag error).
