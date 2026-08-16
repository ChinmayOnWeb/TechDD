# Part A results: repo health and firm value

Status: first statistically valid run of the firm-quarter panel. Supersedes any
earlier numbers, which came from a rank-deficient design (see "What was wrong
before").

## Sample

| | |
|---|---|
| Firms with fundamentals + prices + clones | 6 |
| Firm-quarters built | 112 |
| Firms identifying H1 after singleton dropping | **5** |
| Firm-quarters identifying H1 | **75** |
| Period grid | 2020Q2 - 2026Q1 (calendar quarters) |

Firms: Couchbase, Elastic, GitLab, HashiCorp, MongoDB. Hortonworks builds and
enters the dataset but drops out of estimation (below). Cloudera builds 3 fiscal
quarters, too few to survive the LTM revenue requirement, because its price
export starts 2020-11 against a 2017 listing.

## Headline

**No detectable relationship between the repo-health index and firm value, in
either the pricing or the predictive specification.**

| Model | Outcome | beta | asymptotic p | **bootstrap p** |
|---|---|---|---|---|
| H1 | log(EV/Rev) | -0.027 | 0.862 | **0.882** |
| H2 k=1 | growth t+1 | -0.048 | **0.000** | **0.235** |
| H2 k=2 | growth t+2 | -0.074 | **0.000** | **0.118** |
| H2 k=3 | growth t+3 | -0.075 | 0.000 | **0.235** |
| H2 k=4 | growth t+4 | -0.062 | 0.010 | **0.333** |

The bootstrap column is the headline, as the study design pre-specified.

## The asymptotic standard errors are not merely imprecise -- they are wrong

This is the result most worth carrying into the paper.

On H2 the asymptotic cluster-robust standard errors report t = -7.94 and
p < 0.001: a strongly significant *negative* predictive effect of repo health on
forward revenue growth. That result is an artifact. The wild cluster bootstrap
puts the same coefficient at p = 0.235.

The cause is the cluster count. Cluster-robust standard errors are justified as
the number of clusters grows; here there are five. The sandwich estimator's rank
is capped at G-1 = 4 while the design carries 31 parameters, so it is badly
biased downward and its t-statistics reject far too often. Cameron, Gelbach and
Miller (2008) document exactly this, which is why the design specified the
bootstrap as the headline test rather than a robustness footnote.

Had the bootstrap not been implemented, this panel would have reported a
significant, counterintuitively signed finding at p < 0.001.

**A discreteness limit belongs beside every p-value here.** With G clusters the
bootstrap enumerates 2^(G-1) sign vectors, so the smallest p it can return is
1/(2^(G-1)+1): 0.059 at five clusters, 0.111 at four. Significance at the 1%
level is unreachable by construction, whatever the true effect. This is a
property of the design, not of the estimates.

## What the controls say

The controls behave sensibly, which is the evidence that the panel measures
something real rather than noise:

- `growth_yoy` +2.06 (asymptotic p = 0.004) -- faster-growing firms carry higher
  revenue multiples, the expected direction and the dominant term.
- `op_margin_ltm` +1.73, `log_rev` -1.46, neither distinguishable from zero.

So the machinery recovers a well-known pricing relationship while finding
nothing for repo health. The null is not an artifact of a broken pipeline.

## What was wrong before

Three defects, all latent until the universe widened past the January-fiscal-year
firms. See `fix(panel): shared time grid, singleton dropping, wild cluster
bootstrap`.

1. **Time fixed effects on a per-firm grid.** Dummies were keyed to the raw
   fiscal quarter-end. January-FYE firms report 01-31/04-30/07-31/10-31;
   December-FYE Hortonworks reports 03-31/06-30/09-30/12-31. The two sets never
   intersect, so every Hortonworks quarter-end was unique to Hortonworks and its
   firm dummy became an exact sum of its own time dummies. The design was
   rank-deficient and was reported anyway: coefficients of ~1.3e10, NaN standard
   errors, R^2 = 0.95 that was pure collinearity. Periods are now the calendar
   quarter containing the fiscal quarter's midpoint, so both reporting calendars
   share one grid.

2. **Singletons retained.** Correia (2015) shows singleton groups leave
   coefficients untouched but shrink the small-sample correction and understate
   clustered standard errors, overstating significance -- precisely when fixed
   effects are nested within clusters, as firm effects are here. They are now
   dropped iteratively across both dimensions before clustering. Removing the 13
   singleton rows moved no point estimate, exactly as that paper predicts; it is
   asserted as a test.

3. **No bootstrap.** Implemented as above.

A rank guard now refuses to report any rank-deficient fit rather than emitting
numbers that look like results.

## Why Hortonworks cannot identify anything

Hortonworks delisted in 2018Q3. MongoDB, the earliest of the surviving firms,
opens in 2019Q2. They do not overlap, and neither does Hortonworks overlap any
other firm, so each of its nine observations sits alone in its period cell and
the two-way fixed effects fit it exactly. Those rows carry no identifying
variation regardless of how many there are.

This is a structural fact about the universe, not a data problem, and it is not
fixable by coarsening the time grid: with year effects the sets are still
disjoint (2016-2018 against 2019+). Restoring Hortonworks to the estimation
sample would require either dropping time fixed effects in favour of an explicit
macro control, or extending the universe with firms listed across the 2018-2019
gap.

## Honest reading

At five clusters this panel cannot support a headline claim in either
direction. The correct statement is that **the pre-specified test finds no
evidence that repo health is priced or predictive, and the design lacks the
power to rule out effects of the size that would matter.** The minimum
detectable effect should be stated explicitly before this is written up.

This converges with Part C, which found repo health largely reduces to
contributor headcount. Two independent designs, neither supporting an
incremental signal beyond what headcount and standard financials already carry.

## Open

- Cloudera contributes nothing until a price export covering 2017-2020 is
  obtained.
- Confluent remains excluded by the attribution rule (21.8% firm share, 65.6%
  unattributable); see `decision-repo-attribution.md`.
- Minimum detectable effect not yet computed.
- Look-ahead in the dependent variable (quarter-end price against LTM revenue
  not public until the 10-Q files) is still unaddressed; the design doc requires
  choosing one lag convention and applying it mechanically.
