# Handoff — repo-health research pipeline

State as of 2026-08-17. Everything below is committed on
`claude/session-planning-40wqkl` and pushed. 276 tests green.

**Part A now runs end to end and is estimated.** See `docs/part-a-results.md`
for results, and read the minimum-detectable-effect section before quoting any
Part A number: the design has under 2% power against realistic effects, so its
null is a statement about the design rather than about the world.

## Where the study stands

The design is a three-part study (`docs/2026-08-12-repo-health-study-design.md`),
which **supersedes** the original 2026-07-06 panel spec:

| part | question | status |
|---|---|---|
| **C** | Does repo health predict a project's own outcomes? | **ANSWERED.** See `docs/cohort-hazard-results.md`. |
| **A** | Do public markets price it? | **ESTIMATED.** 7 firms build (127 firm-quarters), 6 identify H1 (88). No detectable effect -- but underpowered by ~30x. See `docs/part-a-results.md`. |
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

## Part A — estimated

All EDGAR payloads are now **committed** under `panel_cache/`, along with the
price exports. They are no longer re-suppliable by hand (EDGAR and the price
vendors are blocked by the network policy), so `panel_cache/*.json` and the
price CSVs are tracked in git deliberately — see the note in `.gitignore`.
Losing them again would cost another manual fetch.

Universe is 7 firms; Confluent is excluded by the attribution rule
(`docs/decision-repo-attribution.md`). Of the remainder:

- **Estimating (6):** Cloudera, Couchbase, Elastic, GitLab, HashiCorp, MongoDB.
- **Builds but absorbed (1):** Hortonworks. It delisted 2018Q3, before MongoDB
  opens 2019Q2, so it overlaps no other firm and every observation is a
  singleton under two-way fixed effects. Dropped per Correia (2015); this does
  not move any coefficient.
Cloudera's full-listing price history arrived 2026-08-17 and it now identifies.
That one firm nearly halved the minimum detectable effect (1.4 -> 0.75) and
dissolved the H2 k=1 coefficient (-0.048 -> -0.008, bootstrap p 0.115 -> 0.796).
**At this size the binding constraint is the number of firms, not the number of
quarters** -- adding a cluster beats any amount of respecification.

Rebuild and estimate:

```
gitdd panel build --universe panel/universe --clones /home/user/clones \
    --cache panel_cache --crsp panel_cache/prices_delisted.csv -o panel.csv
gitdd panel regress panel.csv -o panel_results
gitdd panel power   panel.csv          # minimum detectable effect
```

Three estimation defects were found and fixed while doing this, all latent until
the universe widened past the January-fiscal-year firms: time fixed effects keyed
to per-firm fiscal calendars (rank-deficient design, coefficients of ~1.3e10
reported as results), singletons retained, and no bootstrap. Details in
`docs/part-a-results.md`.

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

(Resolved 2026-08-17: the CLDR export now covers the full listing, 2017-05-01 →
2021-10-07, and reconciles to the cent with the old one on all 235 overlapping
dates.)

Inference note: at this firm count, **wild-cluster bootstrap** p-values are the
headline, not asymptotic clustered SEs. **Now implemented** (`regress.py`), with
Webb six-point weights below 13 clusters — Rademacher weights are too coarse
there and would pin the smallest attainable p-value above 0.05, giving a 5% test
zero power against any effect. This is not a footnote: the asymptotic SEs report
p < 0.001 for an H2 coefficient the bootstrap puts at p = 0.115 — and which one
extra firm has since taken to zero.

## Decisions already frozen (do not silently revisit)

| decision | where |
|---|---|
| `contributor_gini` removed from the index; **neither sign asserted** | `docs/decision-gini-sign-convention.md` |
| `release_cadence` removed — tagging convention, not velocity | `assemble.py` |
| Count components log1p-transformed before z-scoring | `assemble.py` |
| No minimum-follow-up or minimum-commit exclusion | `docs/cohort-exclusions.md` |
| PyPI primary / npm robustness; frames never pooled | `docs/cohort-exclusions.md` |
| Time FE on the calendar quarter of the fiscal-quarter midpoint | `regress.py` |
| Singletons dropped iteratively before clustering (Correia 2015) | `regress.py` |
| Webb weights at <= 12 clusters, Rademacher above (Webb 2023) | `regress.py` |
| Confluent excluded from the universe by the attribution rule | `docs/decision-repo-attribution.md` |

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
