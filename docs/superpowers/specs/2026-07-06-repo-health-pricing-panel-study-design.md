# Is Repository Health Priced? — Panel Study Design

**Date:** 2026-07-06
**Status:** Approved by user (design presented and accepted in brainstorming session)
**Venue target:** arXiv/SSRN preprint first; journal/conference submission later if results warrant
**Authorship:** Solo

## Motivation

The git-due-diligence pilot on GitLab produced the motivating fact: technical due-diligence
adjustments as conventionally priced (~$1M remediation/retention costs) came to ~0.014% of a
$6.9B blended enterprise value. Either technical health genuinely doesn't matter to valuation
at that scale, or it matters through channels the DD-adjustment framing can't see (growth
persistence, margin durability, delivery risk). Nobody has measured which. This study does.

The novel instrument is the one this repo already validated at scale: **git history permits
exact point-in-time reconstruction of technical-health metrics**. For any past quarter-end,
`git log` before that date yields the repository exactly as it stood — deterministic, free of
survivorship bias, and reproducible by anyone with a clone. That property is what makes a
panel study possible where survey- or snapshot-based software-quality research cannot go.

## Research question and hypotheses

**RQ:** Do technical-health signals reconstructed from a public company's open-source
repository carry pricing-relevant information beyond standard financial fundamentals?

- **H1 (contemporaneous pricing):** Repository health explains within-firm variation in
  EV/LTM-revenue multiples after controlling for revenue growth, margin, and scale.
  If supported: markets observe and price technical risk.
- **H2 (predictive):** Repository health at quarter *t* forecasts revenue growth (and/or
  multiple changes) over quarters *t+1…t+4*, controlling for current fundamentals.
  If H2 holds while H1 fails: observable technical risk is *not* priced — a market-efficiency
  finding, the more provocative result.

All four cells of the (H1, H2) outcome matrix are publishable, including the double null with
an honest power analysis, because no prior work has constructed this panel.

## Universe construction

**Inclusion rule (stated ex ante, applied mechanically):**

1. The company is or was listed on a US exchange with SEC quarterly filings (10-Q/10-K)
   available via EDGAR XBRL. Delisted and acquired firms are **included** for their listed
   window — this kills survivorship bias.
2. The company's flagship revenue-generating product is developed in one or more public git
   repositories, designated per firm before any metric is computed.
3. The repository history covers at least 8 quarters of the firm's listed window.

**Candidate firms** (final list fixed during implementation after checking each against the
rule): GitLab (GTLB), Elastic (ESTC), MongoDB (MDB), Confluent (CFLT, via apache/kafka —
see attribution note), HashiCorp (HCP, delisted 2025), Couchbase (BASE), MariaDB plc
(delisted), Chef (acquired 2020), Cloudera (taken private 2021), Hortonworks (merged 2019),
Talend (taken private 2021), Fastly/DigitalOcean/JFrog etc. evaluated and likely excluded
(closed core). Expected: **12–18 firms, ~350–500 firm-quarters.**

**Attribution note (Confluent/Kafka class):** where the flagship repo is a foundation
project the firm dominates rather than owns, the firm is included only if its employees
authored a plurality of commits over the sample window (measurable from author-email
domains); otherwise excluded. The rule is applied once, ex ante, and documented per firm
in the universe config.

## Data

### Financial variables (quarterly, per firm)

| Variable | Construction | Source |
|---|---|---|
| Revenue (quarterly, LTM) | XBRL `Revenues` / `RevenueFromContractWithCustomerExcludingAssessedTax` | SEC EDGAR `companyfacts` JSON API (free, covers delisted firms) |
| Revenue growth | YoY LTM growth | derived |
| Gross/operating margin | XBRL cost/expense tags ÷ revenue | EDGAR |
| Shares outstanding | XBRL `EntityCommonStockSharesOutstanding` / cover-page facts | EDGAR |
| Quarter-end price | daily close on/last-before quarter-end | Stooq CSV endpoint (free, has delisted tickers); yfinance fallback |
| Net debt | debt tags − cash & equivalents | EDGAR |
| **EV/LTM revenue** | (price × shares + net debt) ÷ LTM revenue | derived — the dependent variable |

Fiscal-quarter ends vary by firm (GitLab: Jan 31 FY-end); all repo metrics are computed at
each firm's own fiscal quarter-end dates, not calendar quarters.

### Repository metrics (trailing 4 quarters, computed at each fiscal quarter-end)

One pass per repo over full history (the streaming `iter_patch_records`/numstat machinery
already handles 117K-commit repos); commits bucketed by author date into fiscal quarters;
each metric computed on the trailing-4-quarter window ending at each quarter-end. Bot
authors excluded using the existing `_is_bot_author` filter.

| Metric | Definition (trailing 4Q unless noted) |
|---|---|
| `active_contributors` | distinct non-bot author emails |
| `top_author_share` | share of commits by the most active author |
| `contributor_gini` | Gini coefficient of per-author commit counts |
| `bus_factor_50` | min. number of authors covering ≥50% of commits |
| `churn_gini` | Gini of per-file lines-changed (churn concentration) |
| `release_cadence` | tags created in the window (annotated + lightweight, by tag date) |
| `merge_share` | merge commits ÷ all commits |
| `commit_volume` | total non-bot commits (log, used as activity scale) |
| `secret_incidence` | high-confidence secret findings introduced per 1,000 commits (confidence scoring as in the `security` module) |
| `repo_health_index` | first principal component (or equal-weight z-score mean; both reported) of the above, signed so higher = healthier |

CCN-based hotspot metrics require a worktree checkout per firm-quarter (~450 checkouts ×
lizard); **excluded from v1**, listed as a robustness extension.

### Econometric specification

Primary (H1):

```
log(EV/Rev)_it = α_i + τ_t + β·RepoHealth_it + γ1·Growth_it + γ2·Margin_it
                 + γ3·log(Rev)_it + ε_it
```

- α_i firm fixed effects (identification from within-firm changes — the credible version),
  τ_t calendar-quarter fixed effects (absorbs the 2021–22 multiple compression and all
  market-wide movements), standard errors clustered by firm.
- Reported alongside: pooled OLS without FE (descriptive), and individual-metric versions
  in place of the composite index.

Predictive (H2):

```
Growth_i,t+k = α_i + τ_t + β·RepoHealth_it + γ·Controls_it + ε_it   for k ∈ {1..4}
```

plus the same with Δlog(EV/Rev)_{t→t+k} as the outcome. Implementation: statsmodels OLS
with dummy FE and `cov_type="cluster"`; no exotic machinery. A small-sample power note
(minimum detectable effect at n≈400, ~15 clusters; wild-cluster bootstrap as robustness
given few clusters) goes in the paper.

## Threats to validity (named before reviewers do)

| Threat | Mitigation |
|---|---|
| Squash-merge / workflow policy changes shifting `merge_share`, commit counts | firm FE absorb level shifts; flag known policy-change dates per firm; robustness excluding `merge_share` |
| Monorepo migrations (GitLab CE/EE merge 2019 — a break in our own pilot firm) | per-firm structural-break notes in universe config; robustness with post-break subsamples |
| History rewrites / force pushes destroying point-in-time fidelity | compare clone commit counts against GH API; document; rewrites are rare on flagship repos |
| Bot/automation drift over time | existing bot filter; robustness with stricter filter (exclude authors >N commits/day) |
| Repo ≠ firm (Confluent/Kafka) | ex-ante plurality-of-commits attribution rule |
| Few clusters (~15 firms) | cluster-robust + wild-cluster bootstrap p-values; honest power analysis |
| Reverse causality (rich firms hire more contributors) | H2 lead-lag design; framed as association, not causal, for H1 |

## Engineering plan

New subpackage `src/git_due_diligence/panel/` plus a `gitdd panel` CLI command group.
Existing modules remain untouched; the panel code reuses `ingest` streaming and the
security-module secret patterns as a library.

| Unit | Responsibility | Interface |
|---|---|---|
| `panel/universe.py` + `panel/universe/*.toml` | per-firm config: ticker, CIK, repo URL(s), fiscal-year-end month, listed window, structural-break notes | `load_universe(dir) -> list[Firm]` |
| `panel/history.py` | one-pass point-in-time metric extraction from a local clone | `quarterly_metrics(repo_path, quarter_ends, ...) -> list[QuarterMetrics]` |
| `panel/edgar.py` | EDGAR companyfacts fetch + XBRL tag resolution to quarterly fundamentals | `fetch_fundamentals(cik) -> list[QuarterFundamentals]` (cached to disk; honest User-Agent per SEC policy) |
| `panel/prices.py` | quarter-end close prices incl. delisted tickers | `quarter_end_prices(ticker, dates) -> dict[date, float]` (Stooq, cached) |
| `panel/assemble.py` | join metrics × fundamentals × prices → tidy firm-quarter table | `build_panel(...) -> panel.csv` |
| `panel/regress.py` | H1/H2 specifications, FE, clustered SE, output tables (text + LaTeX) | `run_regressions(panel.csv) -> results/` |
| CLI | `gitdd panel build --universe dir --clones dir -o panel.csv`; `gitdd panel regress panel.csv -o results/` | Typer sub-app |

New dependencies under an optional extra `[panel]`: `pandas`, `statsmodels`, `requests`.
Network code is cache-first: every fetched payload is written to `panel_cache/` and reused,
so the panel is rebuildable offline and the published dataset ships with the cache.

**Testing strategy:** unit tests per unit — quarterly bucketing and trailing-window metrics
against a synthetic fixture repo with commits planted in known quarters; EDGAR/price
fetchers against canned JSON/CSV fixtures (no network in tests); assembler against tiny
in-memory frames; regression runner against a synthetic panel with a known planted
coefficient recovered within tolerance. Network paths get a thin integration smoke test
marked `@pytest.mark.network`, skipped by default.

## Deliverables

1. **Open dataset:** `panel.csv` (firm-quarter observations, all variables) + the fetch
   cache — published in the repo or a companion repo. The dataset is itself a contribution.
2. **Reproduction code:** the `panel/` subsystem, fully tested, runnable end-to-end from
   public sources.
3. **Preprint:** working title *“Is Repository Health Priced? Point-in-Time Software
   Metrics and the Valuation of Open-Source Companies”* — arXiv (q-fin.GN / cs.SE
   cross-list) and SSRN.

## Out of scope (v1)

- CCN/complexity-based hotspot metrics (per-quarter checkouts) — robustness extension.
- Non-US-listed firms (SUSE etc.) — no EDGAR coverage; revisit later.
- Acquisition event study (approach B from brainstorming) — separate follow-on.
- Any LLM-dependent features; the panel pipeline is fully deterministic.
- Writing the paper itself — this spec covers the data/analysis pipeline; drafting the
  preprint is a subsequent work item once results exist.
