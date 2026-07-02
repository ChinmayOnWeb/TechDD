# AcquireScope Phase 3 — Security, Delivery Health & LLM Narrative Design Spec

**Date:** 2026-07-01
**Status:** Approved by default (standing "yes to all" authorization; decisions below are revisable)
**Parent spec:** `2026-07-01-acquirescope-design.md` (Deliverable 1 modules 5–6 + LLM narrative layer)
**Phases 1–2:** shipped — engine core + financial bridge, merged to master, 44/44 tests.

## Summary

Phase 3 completes the engine: a **security posture** module and a **delivery health**
module join the registry (bringing it to five), the Phase 2 "Security remediation"
line item finally prices instead of rendering "Not assessed", and an **optional LLM
narrative layer** synthesizes module outputs into an executive summary with
citation verification against ground truth. The engine keeps working fully without
the LLM layer.

## Design decisions (made autonomously, flagged for review)

1. **Security is local-first; osv-scanner is optional.** Secrets-history scan,
   policy maturity, and patch cadence run from local git/files only. Dependency
   vulnerability scanning shells out to `osv-scanner` *only when the binary is on
   PATH* (it calls the OSV.dev API — the engine's only permitted network touch, and
   only opt-in by installing the tool); when absent, the report carries an honest
   "vulnerability scan not available" note, mirroring the licenses module's
   non-Python scope note. Tests never require the binary.
2. **Delivery health uses local git proxies, honestly labeled.** True DORA metrics
   need the GitHub API; Phase 3 ships tag-based release cadence, commit-activity
   trend, merge-commit share (review-flow proxy), and CI-config presence. Each
   finding's text says it is a proxy. GitHub API integration is deferred.
3. **The narrative layer takes an injected `complete: Callable[[str], str]`.** The
   `anthropic` SDK is an optional extra (`pip install acquirescope[llm]`), wired
   only in the CLI behind `analyze --narrative`. Citation verification: the prompt
   tags every piece of evidence with an ID ([E1], [E2], …); any citation in the
   response that doesn't match a real ID is stripped and counted, and the narrative
   is annotated with the number of removed citations. Tests use a fake completer.
4. **Fixture grows 22 → 24 commits** to plant a committed-then-removed AWS key and
   gains two release tags; existing count assertions update. Planted-issue shifts
   were checked: dave's share stays ≥ 20% (5/24), the hotspot churn threshold still
   flags only `core/engine.py`.

## Components

### 1. Ingest extensions (`src/acquirescope/ingest.py`)

- `Commit` gains `parents: list[str]` (log format adds `%P`; enables merge detection).
- `RepoIngest.tags() -> list[tuple[str, datetime]]` — annotated/lightweight tags with
  their commit dates, oldest first (`git tag --format` / per-tag `git log -1`).
- `RepoIngest.full_patch_text() -> str` — `git log -p` output for secrets scanning
  (cached after first call, like `commits()`).

### 2. Security posture module (`src/acquirescope/modules/security.py`)

`analyze(ingest) -> ModuleResult`, `module="security"`. Findings:

| Signal | Rule | Finding |
|---|---|---|
| Secrets in history | regex over `full_patch_text()` added lines: AWS access keys (`AKIA[0-9A-Z]{16}`), private key blocks (`-----BEGIN ... PRIVATE KEY-----`), generic assignments (`(api_key|secret_key|token) = "<16+ chars>"`) | CRITICAL per distinct secret match, evidence = commit sha + path where first seen |
| Security policy | no `SECURITY.md` at repo root (case-insensitive) | MEDIUM "No security policy" |
| Dependency automation | none of: `.github/dependabot.yml`, `renovate.json` | LOW "No dependency update automation" |
| Patch cadence | newest commit touching a manifest (`requirements*.txt`, `pyproject.toml`, `package.json`, `go.mod`, `Cargo.toml`, `Gemfile`) older than 180 days vs latest commit | MEDIUM "Stale dependency manifest" |
| Vulnerabilities | `osv-scanner` on PATH: run `osv-scanner --format json -r <repo>`, HIGH per vulnerable package (deduplicated); not on PATH: INFO "Vulnerability scan not available (osv-scanner not installed)" | HIGH / INFO |

Metrics: `secret_count` (int), `has_security_policy` (bool),
`manifest_age_days` (int, -1 when no manifest), `vulnerability_count` (int, -1 when
scan unavailable). Secrets already removed from HEAD still count — history is what
leaks. A crash inside the optional osv-scanner subprocess degrades to the INFO note,
not a module failure.

### 3. Delivery health module (`src/acquirescope/modules/delivery.py`)

`analyze(ingest) -> ModuleResult`, `module="delivery"`. Findings:

| Signal | Rule | Finding |
|---|---|---|
| Release cadence | no tags → MEDIUM "No tagged releases"; newest tag older than 180 days vs latest commit → MEDIUM "Stale release cadence" | MEDIUM |
| Activity trend | commits in the 90 days before the latest commit < 50% of the 90 days prior (only when the earlier window had ≥ 10 commits) | MEDIUM "Contribution activity declining" |
| Review-flow proxy | merge commits (≥ 2 parents) < 10% of all commits AND repo has ≥ 20 commits | LOW "Little evidence of PR-based review flow (merge-commit proxy)" |
| CI maturity | none of: `.github/workflows/*` (any tracked file under that prefix), `.gitlab-ci.yml`, `Jenkinsfile`, `.circleci/config.yml` | MEDIUM "No CI configuration detected" |

Metrics: `release_count` (int), `days_since_last_release` (int, -1 when no tags),
`merge_commit_share` (float), `commits_last_90d` (int), `ci_configured` (bool).

### 4. Security remediation pricing (bridge changes)

- `[costs]` gains required key `security_fix_cost_usd` (example: 50_000) —
  `examples/assumptions.example.toml`, `Assumptions` dataclass, and loader update.
- `price_adjustments`: the "Security remediation" line item becomes
  `count(CRITICAL and HIGH security findings) x security_fix_cost_usd`, band ±50%,
  evidence = finding titles; "Not assessed" only when the security module failed or
  is absent from results.

### 5. LLM narrative layer (`src/acquirescope/narrative.py`)

- `build_prompt(repo_name, results) -> tuple[str, set[str]]` — renders findings and
  metrics with stable evidence IDs `E1..En` (one per finding, in module order);
  returns the prompt and the valid ID set. The prompt instructs: executive summary
  for an acquirer, 200–400 words, every factual claim cites `[En]`, no claims
  without a citation.
- `verify_citations(text, valid_ids) -> tuple[str, int]` — strips `[E<k>]` citations
  not in the valid set, returns cleaned text and removed-count.
- `generate_narrative(repo_name, results, complete: Callable[[str], str]) -> str` —
  builds prompt, calls `complete`, verifies citations; if any were removed, appends
  the line `"(N unverifiable citation(s) removed.)"`. Raises nothing of its own;
  a `complete` exception propagates to the caller (CLI turns it into a warning).

### 6. CLI + report integration

- `render_markdown(repo_name, results, narrative: str | None = None)` — when
  provided, an "## Executive narrative (LLM-generated, citation-verified)" section
  appears directly after the title.
- `analyze` gains `--narrative` flag: requires the `anthropic` package (optional
  extra `llm`) and `ANTHROPIC_API_KEY` in the environment; missing either →
  clear stderr message, exit 1, before any analysis runs. An API/SDK error during
  generation degrades: report is still written without the narrative section, a
  warning is echoed, exit 0 (module results are never lost to a narrative failure).
- The Anthropic call lives in one function `_anthropic_complete(prompt) -> str`
  (lazy import of the `anthropic` SDK), using `model="claude-opus-4-8"` (current
  Anthropic-recommended default; per API guidance we do not downgrade tiers for
  cost on the user's behalf) with `max_tokens=2048` — the narrative is a
  deliberately short 200–400-word output.
- `MODULES` registry order: bus_factor, licenses, hotspots, security, delivery.

### 7. Fixture additions (`tests/conftest.py`)

- Two commits by bob (recent dates): add `config/settings.py` containing
  `AWS_KEY = "AKIAIOSFODNN7EXAMPLE"`, then remove the line — planted
  secret-in-history that is absent at HEAD. Total commits: 24.
- Tags: `v0.1.0` after the requirements commit, `v0.2.0` after the last engine
  commit (both via `git tag <name> <sha-or-HEAD>` at build time).
- Existing planted issues unchanged; `test_fixture.py` / `test_ingest.py` counts
  update to 24.

## Error handling

- Security/delivery modules follow the Phase 1 contract: unexpected exception →
  `status="failed"`, report says "Not assessed", run continues, exit 0.
- osv-scanner absence or failure is *within-module* degradation (INFO note), not a
  module failure.
- Narrative failure never blocks the report (see CLI section). Citation
  verification guarantees no fabricated evidence references survive to output.
- No new required network access; `ANTHROPIC_API_KEY` and osv-scanner are opt-in.

## Testing

- Ingest: parents populated (merge commit in a throwaway repo or parent-count ≥ 1
  assertion on fixture), tags returned with dates, patch text contains planted key.
- Security: planted AWS key found with commit evidence (and not flagged at HEAD-only
  scan — the finding must cite history); SECURITY.md absence flagged; osv path
  tested by monkeypatching `shutil.which` (absent → INFO note; present →
  monkeypatched subprocess returns canned JSON → HIGH findings).
- Delivery: fixture tags → release metrics; fixture has no merge commits and 24
  commits → review-proxy finding fires; no CI files → CI finding; activity trend
  tested on synthetic `Commit` lists (unit-level, no git).
- Adjustments: security line item priced from findings; failed security module →
  "Not assessed" (updated Phase 2 tests).
- Narrative: fake completer returns text with one valid and one invalid citation →
  invalid stripped, annotation appended; prompt contains every finding title and ID.
- CLI: `--narrative` without SDK/key exits 1; with a monkeypatched
  `_anthropic_complete` the report gains the narrative section; narrative exception
  → report written without section, exit 0.
- E2E gate extension: planted secret appears as CRITICAL finding in the report;
  model workbook prices Security remediation > 0 with the example assumptions.

## Out of scope (Phase 3 tooling)

- GitHub API metrics (real PR lead time, review coverage) — future work.
- SBOM generation (syft/ORT) — osv-scanner path covers the vulnerability signal.
- Published reports, GitLab validation run — analyst work, not tooling.
- Narrative support for non-Anthropic providers.
