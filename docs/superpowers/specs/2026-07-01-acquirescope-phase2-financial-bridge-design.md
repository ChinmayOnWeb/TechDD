# AcquireScope Phase 2 — Financial Modelling Bridge Design Spec

**Date:** 2026-07-01
**Status:** Approved by default (user pre-authorized "yes to all"; decisions below are revisable)
**Parent spec:** `2026-07-01-acquirescope-design.md` (Deliverable 2)
**Phase 1:** shipped — engine core (bus factor, licenses, hotspots), merged to master, 20/20 tests.

## Summary

Phase 2 turns Phase 1's engine findings into a real Excel valuation model. A new CLI
command `acquirescope model <repo> --assumptions <toml> --output <xlsx>` runs the
engine modules in-process, prices the DD findings as explicit line items, computes a
comps + scenario-DCF valuation, and writes a five-sheet `.xlsx` workbook whose headline
artifact is a sensitivity table showing enterprise value before vs. after diligence
findings.

**Scope decision:** tooling only. The bridge is tested end-to-end against the Phase 1
synthetic fixture repo with an example assumptions file. Real-target models (GitLab
validation anchor, PostHog-style reports) are analyst research work and follow as
separate efforts once the tooling exists.

## Design decisions (made autonomously, flagged for review)

1. **In-process bridge, no intermediate JSON.** `model` calls the same
   `MODULES` registry the `analyze` command uses. Alternatives considered: a two-stage
   `analyze --json` → `model` pipeline (more surface, no Phase 2 consumer for the JSON)
   and the parent spec's "hand-built template" (binary blob in git, not authorable or
   reviewable here). **Amends parent spec detail:** the template layout is code-defined
   in `excel.py`, not a checked-in `.xlsx`; the generated artifact is equivalent.
2. **TOML for assumptions** (`tomllib` is stdlib) — the only new runtime dependency in
   Phase 2 is `openpyxl`.
3. **Python is the computational source of truth.** The workbook also carries live Excel
   formulas for the traceable roll-ups (adjustment sums, adjusted EV, sensitivity cells);
   tests assert the Python-computed values and the presence/shape of the formulas.

## Components

All new code under `src/acquirescope/bridge/` plus one Excel writer and a CLI command.

### 1. `bridge/assumptions.py` — analyst inputs

`Assumptions` (frozen dataclass) loaded from a TOML file via
`load_assumptions(path) -> Assumptions`. Sections:

```toml
[target]
name = "target-repo"

[revenue]           # annual revenue estimate, USD — analyst-researched
low = 8_000_000
mid = 12_000_000
high = 18_000_000
source = "stated ARR press release 2026-03; pricing-page x headcount cross-check"

[comps]             # public OSS/devtools comparables
# list of { name, ev_revenue_multiple }
companies = [
  { name = "GitLab", ev_revenue_multiple = 8.5 },
  { name = "HashiCorp", ev_revenue_multiple = 6.2 },
]
source = "public filings as of 2026-06"

[dcf]
years = 5
growth_bear = 0.10
growth_base = 0.25
growth_bull = 0.40
operating_margin = 0.15          # steady-state
discount_rate = 0.18             # private-company WACC proxy
terminal_growth = 0.03

[costs]
engineer_month_usd = 20_000      # loaded cost, used to price remediation capex
retention_package_usd = 300_000  # per flagged key person
integration_cost_usd = 500_000   # flat integration estimate
license_discount_per_finding = 0.02   # fraction of pre-DD EV per copyleft finding
license_discount_cap = 0.10           # total license discount ceiling
```

Validation fails fast (`ValueError` with the offending key) on missing sections,
non-positive revenue, `low > mid > high` ordering violations, empty comps, or rates
outside (0, 1). No workbook is written if validation fails.

### 2. `bridge/adjustments.py` — pricing DD findings

`price_adjustments(results: list[ModuleResult], assumptions, pre_dd_ev_mid) ->
list[Adjustment]`.

`Adjustment` dataclass: `name`, `low`, `mid`, `high` (USD, stored as positive costs;
they are subtracted from EV everywhere they are applied), `basis` (one-line documented
formula), `evidence` (list of strings referencing module findings), `assessed` (bool).

Pricing rules (each documented in `basis`):

| Line item | Source | Formula (mid; low/high from module bands or ±50%) |
|---|---|---|
| Remediation capex | hotspots `remediation_months_{low,mid,high}` | months × `engineer_month_usd` |
| Key-person retention | bus_factor findings (single-owner dirs + departed contributors) | count × `retention_package_usd`, band ±50% |
| License-risk discount | licenses `copyleft_dependency_count` | min(count × `license_discount_per_finding`, cap) × pre-DD EV, band ±50% |
| Integration cost | assumption only | `integration_cost_usd`, band ±50% |
| Security remediation | no module until Phase 3 | `assessed=False`, all zeros |

A module with `status="failed"` (or absent) prices its line item as `assessed=False`,
zeros, basis "Not assessed — module failed/not available". Run continues.

### 3. `bridge/valuation.py` — comps, DCF, sensitivity

Pure functions, no I/O:

- `comps_valuation(assumptions) -> Valuation` — EV = revenue × median comp multiple,
  banded by the three revenue scenarios.
- `dcf_valuation(assumptions) -> Valuation` — per scenario (bear/base/bull): project
  `years` of revenue from `mid` revenue at the scenario growth rate, free cash flow =
  revenue × operating margin, discount at `discount_rate`, Gordon terminal value at
  `terminal_growth`. Bear→low, base→mid, bull→high.
- `Valuation` dataclass: `method`, `low`, `mid`, `high`.
- `sensitivity_grid(assumptions, total_adjustment_mid) -> SensitivityGrid` — rows =
  comp multiples (min, median, max of comps set), columns = revenue scenarios
  (low/mid/high); each cell holds `(pre_dd_ev, post_dd_ev)` where post = pre − total
  adjustment.
- `pre_dd_ev_mid` = mean of comps mid and DCF mid (documented blend).

All money rounded to whole USD. Every output banded — no naked point estimates
(parent-spec invariant).

### 4. `excel.py` — workbook writer

`write_model(path, target_name, assumptions, results, adjustments, valuations,
grid)` builds the workbook with openpyxl. Five sheets:

1. **Assumptions** — every input with its value and the `source` note. Nothing in the
   model exists without a stated source.
2. **Comps** — comparables table, min/median/max multiple, implied EV per revenue
   scenario.
3. **DCF** — three scenario columns with year-by-year projected FCF, discount factors,
   terminal value, NPV.
4. **DD Adjustments** — one row per line item: low/mid/high, basis, evidence
   references; "Not assessed" rows visibly flagged. Total row uses a live
   `=SUM(...)` formula.
5. **Valuation Summary** — comps EV, DCF EV, blended pre-DD EV, total adjustments
   (cross-sheet formula referencing DD Adjustments total), post-DD EV (formula:
   pre − adjustments), and the headline pre-vs-post sensitivity table. Ends with the
   Phase 1 disclaimer text (educational analysis, not investment advice).

Formula policy: computed values are written by Python; the roll-up cells listed above
are written as Excel formulas so the model is auditable in an interview. Tests read the
workbook back with openpyxl and assert both the stored Python values and the formula
strings.

### 5. CLI

`acquirescope model REPO_PATH --assumptions PATH [--output model.xlsx]` in the existing
Typer app. Engine modules run with the same per-module try/except degradation as
`analyze` (shared helper extracted, used by both commands). Assumptions validation
errors exit code 1 with a clear message; module failures do not.

An example assumptions file ships at `examples/assumptions.example.toml`.

## Error handling

- Invalid/missing assumptions file → exit 1 before any analysis or file write.
- Engine module failure → line item "Not assessed", workbook still written, exit 0.
- Zero comps or degenerate DCF inputs are caught by assumptions validation.
- All file I/O `encoding="utf-8"` where textual; openpyxl handles the xlsx container.

## Testing

- Unit tests per component: assumptions loading/validation (good file, each failure
  mode), adjustment pricing (planted fixture results → expected line items, failed
  module → not-assessed), valuation math (hand-computed comps/DCF expectations,
  band ordering low < mid < high), sensitivity grid shape.
- Excel round-trip test: write workbook, reload with openpyxl, assert sheet names,
  key cells, formula strings, disclaimer presence.
- End-to-end regression (extends the Phase 1 gate): run `model` on the synthetic
  fixture repo with the example assumptions — planted issues appear as priced line
  items (remediation capex > 0, retention count ≥ 2, license discount > 0), post-DD
  EV < pre-DD EV, security row "Not assessed".

## Out of scope (Phase 2)

- Real-target research (GitLab validation, report targets) — follows separately.
- Security/delivery modules and the LLM narrative layer (Phase 3).
- Revenue scraping or any network access — revenue stays analyst-provided.
- Charts/images inside the workbook (tables only; charts can come with reports).
