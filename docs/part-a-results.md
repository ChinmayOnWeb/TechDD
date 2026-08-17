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
| H1 | log(EV/Rev) | -0.027 | 0.862 | **0.918** |
| H2 k=1 | growth t+1 | -0.048 | **0.000** | **0.115** |
| H2 k=2 | growth t+2 | -0.074 | **0.000** | **0.090** |
| H2 k=3 | growth t+3 | -0.075 | 0.000 | **0.176** |
| H2 k=4 | growth t+4 | -0.062 | 0.010 | **0.150** |

The bootstrap column is the headline, as the study design pre-specified: 9,999
replications, Webb six-point weights, restricted residuals, firm clusters.

## The asymptotic standard errors are not merely imprecise -- they are wrong

This is the result most worth carrying into the paper.

On H2 the asymptotic cluster-robust standard errors report t = -7.94 and
p < 0.001: a strongly significant *negative* predictive effect of repo health on
forward revenue growth. That result is an artifact. The wild cluster bootstrap
puts the same coefficient at p = 0.115.

The cause is the cluster count. Cluster-robust standard errors are justified as
the number of clusters grows; here there are five. The sandwich estimator's rank
is capped at G-1 = 4 while the design carries 31 parameters, so it is badly
biased downward and its t-statistics reject far too often. Cameron, Gelbach and
Miller (2008) document exactly this, which is why the design specified the
bootstrap as the headline test rather than a robustness footnote.

Had the bootstrap not been implemented, this panel would have reported a
significant, counterintuitively signed finding at p < 0.001.

### The weight distribution had to change, or the test could never reject

The first implementation used Rademacher (two-point) weights and enumerated all
sign vectors exactly. That is defensible at moderate cluster counts and wrong
here. Rademacher weights admit only 2^G distinct draws, and the t-statistic is
symmetric under flipping all of them, so at five clusters just 16 usable draws
remain and the smallest attainable p-value is 1/17 = 0.059.

**A 5% test built on those weights has exactly zero power against any effect of
any size.** It cannot reject, ever. That is a property of the weight
distribution, not of the data, and it would have made the reported null
meaningless.

Webb's six-point distribution -- +/-sqrt(1/2), +/-1, +/-sqrt(3/2), each with
probability 1/6 -- gives 6^G draws (7,776 at G = 5) and a floor of 1/(B+1) =
0.0001 at 9,999 replications. Webb (2023) and Stata's `wildbootstrap` both
switch to it at G <= 12, which is the rule now implemented.

The square roots matter and are easy to get wrong: informal summaries often
quote the points as +/-0.5, +/-1, +/-1.5, which gives E[w^2] = 7/6 rather than
1 and is not a valid wild bootstrap weight distribution. A test asserts the
moments.

With the corrected weights the null stands on its own terms rather than being
forced by granularity: every p-value remains above 0.09.

## Minimum detectable effect: the null is uninformative

Simulated against the actual H1 design (75 firm-quarters, 5 clusters, the real
collinearity structure), running the same pre-specified bootstrap, 400
replicates per point:

| true beta | power |
|---|---|
| 0.05 | 1.2% |
| 0.10 | 2.5% |
| 0.20 | 4.5% |
| 0.50 | 14.2% |
| 1.00 | 61.8% |
| 1.25 | 76.2% |
| **1.50** | **86.8%** |
| 2.00 | 95.0% |

**MDE at 80% power, alpha = 0.05: beta ~ 1.4.**

Read that against the outcome's scale. `log_ev_rev` has a standard deviation of
0.637 in this sample, and the index is z-scored. A detectable effect therefore
requires a one-standard-deviation improvement in repo health to move the
revenue multiple by a factor of e^1.4, roughly **4x** -- and to do so net of
firm and period fixed effects, growth, margin and size.

No plausible mechanism produces that. Against effects of the size actually
estimated (beta = -0.027), the design has **1-2% power**.

So the correct reading of Part A is not "repo health does not predict value."
It is: **this panel cannot distinguish any realistic effect from zero.** The
null is a statement about the design, not about the world. Reporting it as
evidence of absence would be wrong.

This is why the small-N concern raised early in the project was well founded,
and why Part C -- 3,798 repositories, 41,596 repository-quarters -- carries the
empirical weight. Part A is best framed as a demonstration of the measurement
pipeline on audited firm data, with its power limits stated, rather than as a
test of the hypothesis.

Reproduce with `gitdd panel power panel.csv`.

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
direction. The pre-specified test finds no evidence that repo health is priced
or predictive, and -- per the MDE above -- it could only ever have detected
effects roughly fifty times larger than the one estimated. That is a null with
no evidential content.

This converges with Part C, which found repo health largely reduces to
contributor headcount. Two independent designs, neither supporting an
incremental signal beyond what headcount and standard financials already carry.

## Open

- Cloudera contributes nothing until a price export covering 2017-2020 is
  obtained.
- Confluent remains excluded by the attribution rule (21.8% firm share, 65.6%
  unattributable); see `decision-repo-attribution.md`.
- Look-ahead in the dependent variable (quarter-end price against LTM revenue
  not public until the 10-Q files) is still unaddressed; the design doc requires
  choosing one lag convention and applying it mechanically.
