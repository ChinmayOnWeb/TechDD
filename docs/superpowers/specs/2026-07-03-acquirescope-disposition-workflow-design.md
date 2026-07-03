# AcquireScope Disposition/Triage Workflow — Design Spec

**Date:** 2026-07-03
**Status:** Approved (user pre-authorized "yes to all"; decisions below are revisable)
**Motivating input:** Fable 5 strategic review of the n8n report (2026-07-02) — see the review's
"Next feature" recommendation. Directly follows three ad hoc credibility fixes made earlier the
same day: the founder-mislabeled-as-departed bug, and two security false-positive classes.
**Phases 1–3 + financial bridge:** shipped, merged to master, 76/76 tests passing at time of writing.

## Summary

The engine currently renders every auto-detected finding as final output with no human review
step. That produced real credibility problems on the n8n report: a founder mislabeled as a
"departed" contributor, priced into a retention-risk line item as real dollars; 308
undifferentiated MEDIUM hotspots with no materiality ranking. This spec adds a **disposition
workflow**: an analyst reviews each finding once (confirm / downgrade / dismiss-with-reason) in a
JSON file the tool reads, merges, and writes back; the report and the priced Excel model both
regenerate from the dispositioned findings, with dismissals shown in an appendix so the judgment
trail stays visible instead of findings silently vanishing.

This turns AcquireScope from "scanner that dumps output" into "tool that structures analyst
judgment" — closer to the original spec's thesis (translating engineering findings into dollars
requires judgment) than what the first three phases actually built.

## Design decisions (made autonomously, flagged for review)

1. **JSON, not YAML.** No new dependency (stdlib `json`); trades hand-editing comfort (no comments)
   for keeping the project's zero-new-required-dependency discipline intact. User-confirmed during
   brainstorming.
2. **IDs are computed, not stored on `Finding`.** A pure function derives a stable short hash from
   `(module, title, evidence paths/details)` on demand. `models.py` is untouched — every existing
   module, and every existing test that constructs a `Finding` directly, keeps working unchanged.
3. **Four disposition states, two of which are behaviorally identical.** `pending` and `confirmed`
   both pass a finding through unchanged; the distinction exists only for the analyst's own
   tracking (what's been reviewed vs. not), not for output filtering. This keeps `apply_dispositions`
   simple (a 2-way branch: filtered-out vs. passed-through-with-possible-severity-override) while
   still giving the analyst a real signal to track review progress, without building a "triage
   progress" report in this pass (deferred, out of scope below).
4. **Read-merge-write, not read-only.** Every run with `--dispositions PATH` rewrites `PATH` with
   the current finding set merged in (new findings added as `pending`, findings no longer detected
   dropped). This means the file is always a complete, current picture — the analyst never has to
   manually reconcile it against a re-run's new findings.
5. **Default is maximally conservative: nothing is hidden until an analyst says so.** A finding
   with no disposition entry, or an explicit `pending`/`confirmed` status, always renders. Only an
   explicit `dismissed` removes it from the main report. This means a partially-reviewed dispositions
   file can never silently suppress an unreviewed finding — the failure mode of a bug in this
   feature is "shows too much," never "hides something real."
6. **Fully backward compatible.** `--dispositions` is optional on both `analyze` and `model`. Omit
   it and behavior is byte-for-byte identical to today.

## Components

### 1. `src/acquirescope/dispositions.py` (new module)

```python
compute_finding_id(finding: Finding) -> str
```
SHA-256 of `module|title|evidence[i].path|evidence[i].detail` for each evidence item (joined,
order-preserved), truncated to 12 hex characters. Deterministic: same finding content -> same ID
across runs, regardless of which module produced it or dict/list ordering elsewhere in the pipeline.

```python
@dataclass(frozen=True)
class Disposition:
    status: str  # "pending" | "confirmed" | "downgraded" | "dismissed"
    severity_override: Severity | None
    note: str
    finding_title: str  # informational only, re-derived on every write; not authoritative
```

```python
load_dispositions(path: Path) -> dict[str, Disposition]
```
Parses the JSON file. Raises `ValueError` (caller turns this into exit 1) on malformed JSON, an
unknown `status` value, or a `severity_override` that isn't a valid `Severity` name.

```python
merge_dispositions(
    results: list[ModuleResult], existing: dict[str, Disposition]
) -> dict[str, Disposition]
```
For every finding across every `ModuleResult` with `status == "ok"`: if its computed ID is in
`existing`, keep that entry (refreshing `finding_title` to the current title text); otherwise add
a new `pending` entry. IDs present in `existing` but not among current findings are dropped (stale
— the finding no longer occurs, so there's nothing to disposition).

```python
save_dispositions(path: Path, target_name: str, dispositions: dict[str, Disposition]) -> None
```
Writes the merged dict back as pretty-printed JSON (`indent=2`), `encoding="utf-8"`.

```python
apply_dispositions(
    results: list[ModuleResult], dispositions: dict[str, Disposition]
) -> tuple[list[ModuleResult], list[tuple[Finding, Disposition]]]
```
Returns `(filtered_results, dismissed)`. For each `ModuleResult`, rebuilds its `findings` list:
- No entry, `pending`, or `confirmed` -> finding included unchanged.
- `downgraded` -> `dataclasses.replace(finding, severity=disposition.severity_override)`.
- `dismissed` -> excluded from the module's findings; `(finding, disposition)` appended to the
  `dismissed` list returned alongside.

A `ModuleResult` with `status == "failed"` passes through with its (empty) findings untouched —
dispositions only ever apply to real findings from a successful module run.

### 2. CLI wiring (`cli.py`)

New `--dispositions PATH` option on both `analyze` and `model`. Shared helper:

```python
def _resolve_dispositions(path: Path | None, results: list[ModuleResult]) -> tuple[list[ModuleResult], list[tuple[Finding, Disposition]]]:
```
- `path is None` -> return `(results, [])` unchanged (today's behavior).
- `path` given: `load_dispositions(path)` if it exists else `{}`; `merge_dispositions(results, existing)`;
  `save_dispositions(path, target_name, merged)`; return `apply_dispositions(results, merged)`.

Both commands call this immediately after `run_modules(...)` and before rendering/pricing. Invalid
dispositions file (malformed JSON, bad status/severity) -> caught, printed to stderr, exit 1,
*before* any report/model file is written — same fail-fast posture as invalid `assumptions.toml`.

### 3. Report change (`report.py`)

`render_markdown(repo_name, results, narrative=None, dismissed=None)`. When `dismissed` is
non-empty, appends a final section (after the disclaimer):

```markdown
## Appendix: Dismissed Findings (Analyst-Reviewed)

The findings below were reviewed and dismissed by the analyst. They do not appear in the report
body above or in the priced valuation adjustments.

### [ORIGINAL_SEVERITY] Original Title
Dismissed — {note}
```

### 4. Pricing integration

No changes needed to `adjustments.py` itself: `price_adjustments` already just consumes whatever
`list[ModuleResult]` it's handed. `model`'s CLI command calls `_resolve_dispositions` on the raw
`run_modules()` output *before* passing results into `price_adjustments`, so a dismissed
"departed key contributor"-style finding no longer counts toward `len(bus.findings)` in the
retention-cost line item, and a downgraded security finding drops below the CRITICAL/HIGH pricing
threshold automatically (severity-based filtering already exists there).

## Error handling

- Malformed dispositions JSON, unknown `status`, or invalid `severity_override` name -> `ValueError`
  from `load_dispositions`, caught in the CLI, printed to stderr, exit 1, nothing written.
- `status == "downgraded"` with a missing or `null` `severity_override` is also a `ValueError` at
  load time -- there is nothing to downgrade to. `severity_override` is otherwise optional and
  simply ignored (not an error) for any other status.
- A dispositions path that doesn't exist yet is not an error -- bootstraps a fresh all-`pending`
  file.
- Everything else (module failures, narrative failures) keeps its existing Phase 1/3 graceful
  degradation -- unaffected by this feature.

## Testing

- `compute_finding_id`: same finding content (even reconstructed independently) -> same ID;
  different title or evidence -> different ID.
- `merge_dispositions`: existing entries preserved (title refreshed), new findings added as
  `pending`, stale entries (no longer present) dropped.
- `apply_dispositions`: pending/confirmed pass through unchanged; downgraded overrides severity via
  `dataclasses.replace` (original finding object untouched); dismissed removed from results and
  captured with its disposition.
- `save_dispositions` / `load_dispositions` round-trip: write then read back, values match.
- Report: appendix section renders only when `dismissed` is non-empty; shows original severity,
  title, and note.
- CLI: `--dispositions` omitted -> byte-identical output to before this feature (regression guard);
  first run with a non-existent path bootstraps a `pending`-only file and applies as a no-op;
  second run with a hand-edited (dismissed) entry removes that finding from the report and, for
  `model`, from the priced adjustments; malformed dispositions file -> exit 1, no output written.
- End-to-end regression gate on the synthetic fixture: dismiss the planted "Key contributor
  inactive" finding via a dispositions file, verify it disappears from `analyze`'s report body,
  appears in the appendix with its note, and no longer contributes to `model`'s Key-person
  retention line item.

## Out of scope (this pass)

- A "triage progress" summary (N/M findings reviewed) -- the `confirmed` vs `pending` distinction
  is captured in the data model so this can be built later without a schema change, but isn't
  rendered anywhere yet.
- Any UI beyond hand-editing the JSON file -- no web form, no interactive CLI prompt loop.
- Materiality/path-classification severity weighting (core vs. integration-adapter vs. test vs.
  docs) -- a separate idea from Fable 5's review, not this feature. Disposition gives the analyst a
  manual override for exactly this kind of noise (e.g., dismissing an `assets/`-directory
  bus-factor finding) without the engine needing to know about path materiality itself.
- Bulk/pattern-based dispositioning (e.g., "dismiss all findings matching path glob X") -- every
  disposition is per-finding-ID in this pass; bulk operations are a natural follow-up once the
  single-finding mechanism is proven.
