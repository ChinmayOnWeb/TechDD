# Repository Health: Does It Matter, and to Whom? — Three-Part Study Design

**Date:** 2026-08-12
**Status:** Draft for review — supersedes `2026-07-06-repo-health-pricing-panel-study-design.md`
**Venue target:** working paper (arXiv/SSRN) first; see *Venue and packaging*
**Authorship:** Solo

## Why this supersedes the 2026-07-06 spec

The original design is sound and most of it survives intact — the point-in-time
reconstruction instrument, the ex-ante universe rule, the H1/H2 specifications, the
threats table. Three things forced a restructure.

**1. A load-bearing data assumption was false.** The original data table lists the
quarter-end price source as "Stooq CSV endpoint (free, **has delisted tickers**)".
It does not. Neither does Yahoo. Since the universe rule deliberately includes
acquired and delisted firms *for their listed window* — the rule that removes
survivorship bias — the free sources cannot implement the design as written. This
was not discovered until the pilot build. Resolution: CRSP (see
`panel-data-sourcing.md`); `--crsp` ingestion is built and tested.

**2. Universe attrition accelerated.** Confluent (IBM, Mar 2026), Couchbase
(Haveli, Sep 2025) and HashiCorp (IBM) all left the public market after the spec
was written; GitLab is a rumoured Datadog target. Restricting to *currently* listed
firms would leave ~3–10 firms and would silently reintroduce selection on the
outcome — firms exit the sample precisely when acquired, and acquisition is
plausibly correlated with the thing being studied. With CRSP the original 12–18
firm target is recoverable.

**3. Power was always the binding constraint, and the original design had no
answer to it.** ~15 clusters is below where cluster-robust inference behaves. The
spec acknowledged this honestly ("wild-cluster bootstrap; honest power analysis")
but that mitigates rather than solves. The restructure solves it: a high-powered
repo-level study establishes the construct, so the firm-level result is no longer
the paper's only load-bearing evidence.

### Pilot findings that change the metric definitions

Running the pipeline against real repositories invalidated several v1 choices:

| Finding | Consequence |
|---|---|
| `github.com/gitlabhq/gitlabhq` is a bot-authored mirror post-2019 | Flagship repos must be verified as the true authorship stream, not a mirror. GitLab now points at `gitlab.com/gitlab-org/gitlab`. |
| Release-tag counts are dominated by tagging convention (MongoDB ~113/window from backport tags, Elastic ~34, GitLab 0 — its tags sit on unfetchable stable branches) | `release_cadence` **removed** from the composite index; retained as a descriptive column. |
| `active_contributors` and `bus_factor_50` scale with project size, letting scale dominate the index | Both **log1p-transformed** before standardisation. |
| GitLab omits `dei:EntityCommonStockSharesOutstanding` entirely | Weighted-average-shares fallback added; CRSP `SHROUT` preferred where available. |
| A single stale 2019 `LongTermDebt` fact shadowed MongoDB's `ConvertibleDebtNoncurrent` series, dropping ~$1.1bn of notes and understating EV | Debt merged across tags by date with priority fill. |
| Automation accounts without a `bot` token (`delivery-team+release-tools@gitlab.com`, `elasticsearchmachine@…`, ~3k commits/yr) | Bot filter extended; **this class of decision is a researcher degree of freedom and must be frozen ex ante** (see *Pre-registration*). |

---

## The through-line

One instrument, three questions, escalating in who is supposed to be doing the
pricing:

> Repository health is measurable point-in-time, deterministically, for any
> project with a public git history. **Does it matter — and if so, to whom?**

- **Part C — does it matter at all?** Repo health predicts a project's own
  outcomes (abandonment, contributor collapse, security incidents). *N in the
  thousands.*
- **Part A — do public markets price it?** Repo health explains EV/Revenue
  multiples beyond fundamentals. *~15 firms.*
- **Part B — do sophisticated buyers price it?** Repo health predicts acquisition
  likelihood and premium, among parties who perform exactly this diligence.
  *~20–40 deals.*

**Written order is C → A → B, not the order they were conceived.** The reason is
inferential, not stylistic: without C, a null in A is uninterpretable — it cannot
distinguish "the market ignores technical risk" from "we measured nothing real."
C establishes construct validity, so A and B interrogate a signal already shown to
have consequences. C also carries the statistical weight, which is what stops A's
~15 clusters from being the paper's only support.

The genuinely interesting outcomes are the **divergences**:

| C | A | B | Reading |
|---|---|---|---|
| ✓ | ✗ | ✓ | Signal is real; acquirers use it, public markets don't. **Market-inefficiency finding — the strongest result available.** |
| ✓ | ✓ | ✓ | Health is priced everywhere. Confirms DD practice has economic content. |
| ✓ | ✗ | ✗ | Health matters technically but carries no valuation information. Sharpens what DD can and cannot claim. |
| ✗ | — | — | The construct does not predict outcomes. Publishable as a negative result about a widely assumed metric family; A/B become moot. |

---

## Part C — Construct validity at scale

**RQ:** Do point-in-time repository-health metrics predict a project's subsequent
technical outcomes?

**Unit:** repository-quarter. **Target N:** low thousands of repositories.

**Candidate outcomes** (each defined ex ante, all observable from git + public
registries):

- *Dormancy / abandonment* — no non-bot commit for k consecutive quarters.
- *Contributor collapse* — active-contributor count falls ≥50% over four quarters.
- *Maintainer turnover* — the top-share author at t contributes nothing by t+4.
- *Security incident* — a published advisory/CVE attributable to the project.
- *Hard fork* — a divergent fork accumulates independent commits (the
  Elasticsearch→OpenSearch, Terraform→OpenTofu pattern).

**Design:** discrete-time hazard / Cox proportional-hazards for time-to-event
outcomes; panel logit or linear probability with repo and period fixed effects for
recurring ones. Power here is not a constraint, so the specification can be
conservative.

**Sampling frame — must be fixed ex ante and is the main threat.** Selecting
repositories on popularity (stars, dependents) conditions on success and will bias
survival estimates. Preferred: a registry-derived frame (package-ecosystem
dependency graphs) stratified by size and age, drawn once, documented, frozen —
including the dead projects, which is the entire point.

**Engineering constraints — measured, not estimated.** The full-history patch scan
(`iter_patch_records`, which powers `secret_incidence`) ran **37 min for GitLab's
551k commits** and ~16 min for MongoDB + Elastic (~206k) — roughly 15k commits/min.
Clones ran 2.2–3.9 GB each against ~22 GB free disk. Consequences for C:

1. **Streaming.** Clone → analyse → delete per repo; peak disk is the largest
   single repo, not the sum. Cloning thousands of repos concurrently is not viable.
2. **Two metric tiers.** The commit-metadata metrics (contributors, ginis, bus
   factor, merge share) come from `git log --numstat` and are cheap.
   `secret_incidence` needs the full patch stream and dominates runtime. Propose a
   **lite tier** (metadata only, `--filter=blob:none` partial clone — far smaller
   and faster) across the full frame, plus the **full tier** on a stratified
   random subsample, with the subsample used to check that lite-tier conclusions
   are unchanged.
3. Per-repo metrics cache already exists (`metrics_cache.py`, keyed on clone HEAD
   and quarter grid) and extends to this without change.

*Architecture prototype deferred pending review of this document.*

---

## Part A — Is repository health priced?

The 2026-07-06 study, restored. **Unchanged:** the RQ, H1/H2 hypotheses, the
ex-ante universe inclusion rule, fiscal-quarter alignment, the econometric
specifications, and the threats table. **Changed** as follows.

**Prices:** CRSP daily stock file, covering delisted securities for their listed
window; Stooq retained as fallback for live tickers only. Sources are never spliced
within a firm's series.

**Universe:** the original candidate list is viable again — GitLab, Elastic,
MongoDB, Confluent, HashiCorp, Couchbase, MariaDB, Cloudera, Talend, Hortonworks,
Chef. Target 12–18 firms, ~350–500 firm-quarters.

**Tiering (new):** each firm is tagged `core` (the product *is* the repo) or
`adjacent` (a significant public repo capturing only part of the value-generating
engineering — Datadog's agent, Cloudflare's runtime, Rapid7's Metasploit). Repo↔firm
measurement error attenuates β **toward zero**, so a broad-panel null is
uninterpretable on its own. Therefore: **headline specification runs on the `core`
subset; the broad panel is robustness.** Agreement across both is evidence; a result
that appears only in the broad panel is the attenuation artefact talking.

**Index definition (revised per pilot):** six components — `active_contributors`
(log1p), `bus_factor_50` (log1p), `top_author_share`, `contributor_gini`,
`churn_gini`, `secret_incidence` — equal-weight z-score mean and PC1 both reported.
`release_cadence`, `merge_share`, `commit_volume` retained as descriptive columns
and controls, excluded from the index.

**Inference:** wild-cluster bootstrap (Cameron–Gelbach–Miller) as the *headline*
p-values, not a robustness footnote. Asymptotic cluster-robust SEs are reported
alongside and explicitly flagged as unreliable at this cluster count. Minimum
detectable effect stated up front. `regress.py` currently refuses panels with <2
firms; the bootstrap is not yet implemented.

**New threat — look-ahead in the dependent variable.** `log(EV/Rev)` pairs a
quarter-end price with LTM revenue that is not public until the 10-Q files weeks
later. Fix: either lag the price to the filing date, or lag fundamentals by one
quarter. Decide once, apply mechanically, report the alternative as robustness.

---

## Part B — Do acquirers price it?

**RQ:** Does repository health predict which open-source companies are acquired,
and on what terms?

The universe attrition that damaged Part A *is* Part B's sample. Every firm lost —
Confluent, HashiCorp, Couchbase, Cloudera, Talend, Hortonworks, Chef, MariaDB, and
the wider set (Splunk, New Relic, Sumo Logic, Instructure) — is an observation with
a dated, observable event.

**B1 — Selection.** Discrete-time hazard model over the full listed OSS universe:
does repo health at t predict acquisition announcement in t+1? Risk set is every
listed firm-quarter, so this uses Part A's panel directly and needs no new
financial data.

**B2 — Terms.** Cross-sectional regression of deal premium (offer price vs
unaffected price) and cumulative abnormal announcement return on pre-announcement
repo health, controlling for growth, margin, scale, and deal characteristics.

**Additional data:** announcement dates, deal values, acquirer identity, and
consideration type — hand-collectable from 8-K/DEFM14A filings and press releases
for public targets; CRSP `DSEDELIST` for delisting returns (explicitly out of scope
for the price loader, needed here).

**Honest limits:** N is ~20–40 and the sample conditions on completed deals —
withdrawn and never-approached firms are the counterfactual B1 partially addresses
and B2 cannot. Private-target deal values are often undisclosed. B2 is the weakest
of the three; it should be framed as suggestive.

---

## Pre-registration and researcher degrees of freedom

This is the threat most likely to sink the paper, and the pilot demonstrated it
empirically rather than hypothetically: measured health moved materially with
bot-filter definitions, XBRL tag-selection order, index composition, and count
transformation. With three parts, two index variants, five H2 horizons, and
core/broad splits, the multiple-comparisons surface is large enough that an
unconstrained search would find *something* significant.

**Before any Part A or B estimation is run:**

1. Freeze the index definition, the bot filter, and the tag-resolution order —
   version-pinned, with the frozen commit referenced in the paper.
2. Declare the single primary specification per part, and the primary index variant
   (proposal: equal-weight z-score; PCA as robustness).
3. Register the full robustness surface to be reported *regardless of outcome*.
4. Pre-commit to reporting all four (C, A, B) outcome cells, including nulls.

The pipeline's determinism is a genuine asset here: given the same clones and a
pinned commit, every number regenerates exactly. That should be stated as a
reproducibility claim and shipped with the dataset.

---

## Threats to validity — additions to the 2026-07-06 table

The original table stands. New entries:

| Threat | Mitigation |
|---|---|
| **Employee vs external contributors.** Metrics count all non-bot authors, so for a popular project they may measure *community vitality*, not the firm's engineering capacity — arguably a different economic object than the one being priced. | Add an employee-share covariate from corporate email domains; report the index split by employee/external. Acknowledge domain inference is noisy. |
| **Look-ahead in EV/Rev** (price known, revenue not yet filed). | Lag price to filing date or lag fundamentals; decide once, report the alternative. |
| **Repo↔firm measurement error** (adjacent-tier firms). | Core/adjacent tiering; headline on core only. |
| **Metric-definition fragility** (demonstrated in pilot). | Pre-registration; frozen definitions at a pinned commit. |
| **Part C sampling-frame selection** (popularity conditions on success). | Registry-derived stratified frame drawn once, including dead projects. |
| **Part B conditions on completed deals.** | B1 hazard model over the full risk set; B2 framed as suggestive. |
| **Licence-change / fork shocks** (MongoDB SSPL 2018, Elastic SSPL 2021 → AGPL 2024, OpenSearch fork 2021) mechanically move contributor counts for governance reasons, not engineering decline. | Per-firm structural-break dates in universe config; robustness excluding break windows. Potentially a *feature* — these are candidate natural experiments for future causal work. |

---

## Sequencing and decision gates

Strictly sequential. Three studies run in parallel finish as zero studies.

| Stage | Work | Gate |
|---|---|---|
| **0** | Pre-registration document; freeze definitions at a pinned commit | Nothing estimated before this |
| **1** | Part C: sampling frame, streaming architecture, lite/full metric tiers | *Awaiting review of this document* |
| **2** | Part C estimation | **If C is null, stop and rewrite.** A/B are moot against an invalid construct |
| **3** | Part A: CRSP export → restore delisted firms → wild-cluster bootstrap | Needs CRSP export (user-supplied) |
| **4** | Part B: deal collection, delisting returns, B1/B2 | Reuses Part A panel as risk set |
| **5** | Dataset + tool release; write-up | — |

Stage 3 is unblocked by data, not code, and can proceed in parallel with stage 1
if the CRSP export arrives early — it is the one exception to strict sequencing,
because its remaining work is mechanical.

## Venue and packaging

A three-part paper is harder to place than a focused one. Two viable shapes:

- **Single working paper** (SSRN/arXiv, q-fin.GN + cs.SE) presenting C→A→B as one
  arc. Best fit for the market-inefficiency narrative, which needs all three legs.
- **Lead paper + companion.** Part C alone is a natural empirical-software-engineering
  submission (MSR/EMSE); A+B as the finance paper citing it. Lower risk per venue,
  and C's dataset is independently citable.

Recommendation: draft as one working paper, then split if referees push back. The
dataset and tool release is independently valuable and should not be gated on any
of the three results.

## Open questions for review

1. **Part C outcome variable** — which of the five candidates is primary? Dormancy
   is cleanest to define; security incidents are most relevant to due diligence.
2. **Part C sampling frame** — which registry, and what stratification?
3. **Look-ahead fix for Part A** — lag price to filing date, or lag fundamentals?
4. **Employee-share covariate** — worth the noisy domain inference, or note as a
   limitation and move on?
5. **Packaging** — one paper or lead + companion?
