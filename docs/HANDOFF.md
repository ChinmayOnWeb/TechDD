# Handoff — repo-health research pipeline

State as of 2026-08-13. Everything below is committed on
`claude/session-planning-40wqkl` and pushed. 233 tests green.

## Where the study stands

The design is a three-part study (`docs/2026-08-12-repo-health-study-design.md`),
which **supersedes** the original 2026-07-06 panel spec:

| part | question | status |
|---|---|---|
| **C** | Does repo health predict a project's own outcomes? | **ANSWERED.** See `docs/cohort-hazard-results.md`. |
| **A** | Do public markets price it? | 3 firms live (76 firm-quarters); 4 more attributed and configured, blocked only on re-supplying their EDGAR JSONs. |
| **B** | Do acquirers price it? | Not started. |

The order matters and is not cosmetic: without C, a null in A cannot distinguish
"markets ignore technical risk" from "we measured nothing real". C also carries
the statistical weight — **41,596 repository-quarters** against Part A's ~68
firm-quarters — which is what makes the small-N firm panel survivable.

## Part C — done, ready to estimate

- Frames frozen and committed: `cohort/frame.json` (PyPI, 4,850 repos),
  `cohort/frame_npm.json` (npm, 4,125). Drawn by seeded random sample from
  **complete** registry enumerations, so dead projects enter at population rate.
- Harvested: `cohort_results/harvest_{pypi,npm}.jsonl` — 3,798 usable
  repositories, 41,596 repository-quarters. Gitignored; regenerable via
  `scripts/harvest_cohort.py` (checkpointed, resumable, time-boxed).
- Findings: `docs/cohort-preliminary-findings.md`. All replicate across both
  ecosystems.

**Next step:** the discrete-time hazard / Cox model. `cohort/outcomes.py` already
emits the repository-quarter rows with time-varying covariates and explicit
right-censoring. Three specification constraints are non-negotiable and
documented: predictors must be **time-varying** (baseline quarters are
degenerate), **activity must be a control** (`commit_volume` predicts dormancy
near-tautologically), and results must be **stratified by solo /
multi-contributor** (~40% of the population is single-author).

## Part A — attribution DONE; blocked only on data

Universe is now 7 firms. Cloudera, Couchbase, Hortonworks and HashiCorp have
TOMLs written and clones in place; they build the moment their EDGAR
`companyfacts` JSONs are re-supplied to `panel_cache/edgar_CIK<cik>.json`.
Confluent is excluded by the attribution rule — see
`docs/decision-repo-attribution.md`.

### Superseded section below (attribution now measured)

Working: 3 firms (GitLab, MongoDB, Elastic) → 68 firm-quarters.

Staged but not yet in the universe: prices and EDGAR fundamentals for
**CFLT, HCP, BASE, CLDR, HDP** (`panel_cache/`). What's missing is a
`panel/universe/<slug>.toml` for each, and that needs a decision the spec
already specifies:

> Where the flagship repo is a foundation project the firm dominates rather than
> owns, include the firm only if its employees authored a **plurality of
> commits** over the sample window (measurable from author-email domains).

- **HashiCorp** (`hashicorp/terraform`) and **Couchbase** — unambiguous, firm-owned.
- **Confluent** (Kafka), **Cloudera** (Impala/Hadoop), **Hortonworks** (Hadoop/Ambari)
  — foundation projects. **Run the plurality test; do not assign by assumption.**

Known gap: the CLDR price export covers only 2020-11 → 2021-10, though Cloudera
listed in 2017. Re-export wider or accept ~4 quarters instead of ~18.

Inference note: at ~10–15 firms, **wild-cluster bootstrap** p-values are the
headline, not asymptotic clustered SEs. Not yet implemented.

## Decisions already frozen (do not silently revisit)

| decision | where |
|---|---|
| `contributor_gini` removed from the index; **neither sign asserted** | `docs/decision-gini-sign-convention.md` |
| `release_cadence` removed — tagging convention, not velocity | `assemble.py` |
| Count components log1p-transformed before z-scoring | `assemble.py` |
| No minimum-follow-up or minimum-commit exclusion | `docs/cohort-exclusions.md` |
| PyPI primary / npm robustness; frames never pooled | `docs/cohort-exclusions.md` |

**Pre-registration is stage 0 of the plan and has not been done.** Freeze
definitions at a pinned commit before estimating anything. The pilot showed
measured health moving materially with bot-filter, XBRL-tag and index choices,
so the forking-paths risk here is demonstrated, not hypothetical.

## Traps that already cost time — don't rediscover them

1. **`pkill -f harvest_cohort` kills the calling shell** (its own command line
   matches). Filter on `/proc/PID/comm` instead.
2. **Long background processes get reaped between turns.** Use the time-boxed
   chunked runner; it is checkpointed so nothing is lost.
3. **Observation windows must run to the study end, not the last commit.**
   Dormancy *is* the absence of commits; truncating at the last commit makes the
   primary outcome unobservable and censors every repository.
4. **XBRL tags shadow each other.** Both debt and revenue needed merging with
   priority fill. Revenue splits at the **ASC 606** transition (fiscal 2018), so
   first-non-empty selection silently drops pre-2018 history — Hortonworks lost
   11 of 15 quarters, MongoDB lost 4.
5. **Investing.com PDFs order columns Price, Open, High, Low** — close *first*,
   opposite to Stooq. A positional parse takes the open as the close and nothing
   downstream catches it.
6. **`github.com/gitlabhq/gitlabhq` is a bot-authored mirror.** Real GitLab
   authorship is `gitlab.com/gitlab-org/gitlab`.
7. **Ticker reuse is a live hazard**: HCP was also Healthpeak (a REIT). Resolve
   securities by PERMNO or verify the entity name in the filing.

## Environment

- Network: PyPI, npm registry, GitHub and `api.github.com` reachable. **Blocked:**
  `sec.gov`/`data.sec.gov`, Stooq, WRDS, crates.io API, and all repo aggregators
  (ecosyste.ms, libraries.io, deps.dev). EDGAR and price data must be supplied
  manually.
- Python 3.12 venv at `/tmp/venv` (the system Python is 3.11 and the project
  requires ≥3.12).
- `cohort_cache/`, `cohort_results/`, `panel_cache/`, `panel.csv`,
  `panel_results/` are gitignored — regenerable, deliberately not committed.
