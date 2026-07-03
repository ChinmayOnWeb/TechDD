# AcquireScope Interview Questions — Design Spec

**Date:** 2026-07-03
**Status:** Approved (user pre-authorized "yes to all"; decisions below are revisable)
**Motivating input:** Fable 5 strategic review of the n8n report (2026-07-02) — "Reposition as
interview prep, not automated verdicts": *"every finding emits 'questions for management'... a
corp-dev VP doesn't want automated conclusions; they want to walk into the room already knowing
what to ask."*
**Depends on:** the disposition/triage workflow (shipped 2026-07-03) — questions are generated
from the post-disposition finding set, so a dismissed finding never gets a management question.

## Summary

`acquirescope analyze --questions` calls an LLM once with the report's (post-disposition) findings
and gets back one exploratory question per finding, keyed by the same stable finding ID the
disposition workflow already computes. Each rendered finding gains an optional "Question for
management" line. This is honest about what public-repo analysis can produce: not a verdict, but a
pre-read that arms an analyst walking into a real 2–4 week engagement with a few hours of
management access.

## Design decisions (made autonomously, flagged for review)

1. **Separate `--questions` flag, not bundled into `--narrative`.** User-confirmed during
   brainstorming. One Anthropic call either way; a user may want one feature without the other.
2. **LLM-generated, not templated.** User-confirmed, overriding my initial template-based
   recommendation. Accepted trade-off: this makes a report feature depend on the optional `[llm]`
   extra + API key, same as `--narrative` already does — the report is fully functional without it,
   just without this section.
3. **Structural validation, not citation-verification.** Narrative's citation mechanism guards
   against *fabricated facts* in flowing prose. A question isn't a factual claim — "ask whether X"
   is safe to surface even if imperfectly worded, since it prompts verification rather than
   asserting something. The only defense needed is against a **hallucinated finding reference**:
   the response must be strict JSON mapping real finding IDs to question text; any ID that doesn't
   match a real finding is dropped.
4. **Scoped to non-INFO findings.** INFO findings are routine/informational by construction
   (`Repository license: MIT`, scope notes) — a management question for one reads as absurd
   ("please explain your permissive MIT license"). Only CRITICAL/HIGH/MEDIUM/LOW findings get a
   question generated.
5. **Shared unavailability check.** `_narrative_unavailable_reason` (anthropic package + API key
   check) is renamed to `_llm_unavailable_reason` and used by both `--narrative` and `--questions`
   — same underlying requirement, no reason to duplicate the check.
6. **`model` command is unaffected.** Questions only apply to `analyze`'s rendered findings text;
   `model`'s Excel output has no equivalent "per-finding narrative" surface to attach a question to.

## Components

### 1. `src/acquirescope/interview_questions.py` (new module)

Mirrors `narrative.py`'s shape.

```python
build_questions_prompt(repo_name: str, results: list[ModuleResult]) -> tuple[str, set[str]]
```
Filters to findings with `severity != Severity.INFO` across all `status == "ok"` module results.
For each, computes its ID via `acquirescope.dispositions.compute_finding_id` and includes
`(id, module, severity, title, summary)` in the prompt. Instructs the model: for each listed
finding ID, write one concise, exploratory, non-accusatory question a DD analyst would ask the
target's management or engineering leadership about it; respond with **strict JSON only** — an
object mapping finding ID to question string, no other text, no markdown fencing. Returns the
prompt and the `set[str]` of valid finding IDs (matching `narrative.build_prompt`'s exact shape).

```python
parse_questions_response(text: str, valid_ids: set[str]) -> dict[str, str]
```
Attempts `json.loads` on the (whitespace-stripped) response text. Raises `ValueError` if it isn't
valid JSON or isn't an object of string-to-string — a malformed response is a real failure, not a
silent no-op, so it surfaces through the same CLI warning path as any other question-generation
failure (see Error handling). On success, returns only the entries whose key is in `valid_ids`;
unknown IDs are dropped without erroring (the model naming an ID that doesn't exist is expected
occasional noise, not a hard failure).

```python
generate_questions(
    repo_name: str, results: list[ModuleResult], complete: Callable[[str], str]
) -> dict[str, str]
```
Builds the prompt, calls `complete`, parses and validates the response. Raises nothing of its own
beyond what `parse_questions_response` raises; an exception from `complete` propagates to the
caller exactly like `generate_narrative` already does.

### 2. Report change (`report.py`)

`render_markdown(repo_name, results, narrative=None, dismissed=None, questions=None)` —
`questions: dict[str, str] | None`. For each rendered finding (main body only, not the dismissed
appendix), after the evidence lines: if `compute_finding_id(finding)` is a key in `questions`,
append a blank line then `**Question for management:** {question}`.

### 3. CLI (`cli.py`)

- Rename `_narrative_unavailable_reason` → `_llm_unavailable_reason` (same body, same check).
  Every existing call site and every existing test that monkeypatches this function by name is
  updated to the new name — there is no behavior change, purely a rename to reflect that two
  features now share it.
- New `--questions` boolean flag on `analyze`, checked with `_llm_unavailable_reason()` at the same
  point `--narrative` is checked (before any analysis runs, so a missing key/package fails fast).
- After dispositions are resolved and (if requested) the narrative is generated: if `--questions`,
  call `generate_questions(repo_path.name, results, _anthropic_complete)` in a `try/except
  Exception` — on failure, `typer.echo` a warning to stderr and continue with an empty question
  set; the report is never lost to a question-generation failure, same posture as narrative.
- `render_markdown(...)` call gains the `questions` argument.

## Error handling

- `--questions` requested but SDK/key unavailable → stderr message, exit 1, before any analysis
  (same as `--narrative`).
- Malformed JSON from the model, or a response that isn't an object of strings → `ValueError` from
  `parse_questions_response`, caught by the CLI's existing `except Exception`, degrades to a
  warning + report written without questions, exit 0.
- A hallucinated finding ID in an otherwise-valid response → silently dropped (not a failure — see
  design decision 3).
- `model` command: no changes, no new error paths.

## Testing

- `build_questions_prompt`: INFO findings excluded; CRITICAL/HIGH/MEDIUM/LOW findings included with
  their computed ID; returned `dict[str, str]` covers exactly the included findings.
- `parse_questions_response`: valid JSON with real + hallucinated IDs → only real IDs survive;
  malformed JSON → raises `ValueError`; valid JSON but wrong shape (e.g. a list, or non-string
  values) → raises `ValueError`.
- `generate_questions`: fake completer returning valid JSON → correct dict; fake completer raising
  → exception propagates.
- Report: a finding with a matching question renders the "Question for management" line; a finding
  with no entry in `questions` does not; a dismissed finding (in the appendix) never renders a
  question line even if `questions` happens to contain its ID.
- CLI: `--questions` without SDK/key → exit 1, no output written; malformed LLM response → report
  still written without questions section, exit 0, stderr warning; existing `--narrative` tests
  updated for the `_llm_unavailable_reason` rename, still passing unchanged in behavior.
- End-to-end regression gate on the synthetic fixture: monkeypatched completer returns a question
  for the "Single point of failure: payments/" finding's real computed ID plus one hallucinated ID;
  verify the real question renders next to that finding and the hallucinated entry is absent
  anywhere in the report.

## Out of scope (this pass)

- Batching/caching questions across repeated runs (every `--questions` run re-calls the LLM; no
  memoization by finding ID). A natural follow-up once real usage shows repeated-run cost matters.
- Questions for the `model`/Excel output — no per-finding narrative surface exists there to attach
  one to.
- Any UI for editing/curating generated questions beyond what the disposition workflow's `note`
  field already allows an analyst to capture informally.
