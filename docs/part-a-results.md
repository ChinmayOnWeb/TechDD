# Part A results: repo health and firm value

Status: first statistically valid run of the firm-quarter panel. Supersedes any
earlier numbers, which came from a rank-deficient design (see "What was wrong
before").

## Sample

| | |
|---|---|
| Firms with fundamentals + prices + clones | 7 |
| Firm-quarters built | 127 |
| Firms identifying H1 after singleton dropping | **6** |
| Firm-quarters identifying H1 | **88** |
| Period grid | 2019Q2 - 2026Q1 (28 calendar quarters) |

Firms: Cloudera, Couchbase, Elastic, GitLab, HashiCorp, MongoDB. Hortonworks
builds and enters the dataset but drops out of estimation (below).

Cloudera entered on 2026-08-17, when a price export covering its full listing
(2017-05-01 -> 2021-10-07, its last trading day) replaced one that started
2020-11-02. The two agree to the cent on all 235 overlapping dates. It is the
single most valuable firm in the universe for identification: it is the only
one bridging 2019-2021, and it takes H1 from 5 identifying firms to 6 and from
75 firm-quarters to 88.

## Headline

**No detectable relationship between the repo-health index and firm value, in
either the pricing or the predictive specification.**

| Model | Outcome | beta | **bootstrap p** |
|---|---|---|---|
| H1 | log(EV/Rev) | +0.022 | **0.794** |
| H2 k=1 | growth t+1 | -0.008 | **0.796** |
| H2 k=2 | growth t+2 | -0.034 | **0.484** |
| H2 k=3 | growth t+3 | -0.054 | **0.152** |
| H2 k=4 | growth t+4 | -0.055 | **0.140** |

### The sixth firm dissolved the H2 result

Worth recording, because it is the cleanest out-of-sample check this design
will ever get. On five firms, H2 at k=1 estimated beta = -0.048 with an
asymptotic p < 0.001 and a bootstrap p of 0.115 -- borderline enough to be
tempting. Adding Cloudera, which was added for coverage and not because of
anything to do with H2, moved that coefficient to -0.008 at p = 0.796. It was
noise. The longer horizons (k = 3, 4) shrank too but held their sign and remain
the least uninteresting cells in the table.

A coefficient that collapses on the arrival of one more cluster was never a
finding. That is the small-N problem stated as a fact rather than as a caveat.

The bootstrap column is the headline, as the study design pre-specified: 9,999
replications, Webb six-point weights, restricted residuals, firm clusters.

## The asymptotic standard errors are not merely imprecise -- they are wrong

This is the result most worth carrying into the paper.

On the five-firm sample the asymptotic cluster-robust standard errors reported
t = -7.94 and p < 0.001 for H2 at k = 1: a strongly significant *negative*
predictive effect of repo health on forward revenue growth. That result was an
artifact. The wild cluster bootstrap put the same coefficient at p = 0.115, and
the sixth firm then took the coefficient itself to roughly zero -- so the
bootstrap was right and the asymptotic test was wrong, confirmed twice over.

The cause is the cluster count. Cluster-robust standard errors are justified as
the number of clusters grows; there were five. The sandwich estimator's rank is
capped at G-1 = 4 while the design carries 31 parameters, so it is badly biased
downward and its t-statistics reject far too often. Cameron, Gelbach and
Miller (2008) document exactly this, which is why the design specified the
bootstrap as the headline test rather than a robustness footnote.

Had the bootstrap not been implemented, this panel would have reported a
significant, counterintuitively signed finding at p < 0.001 -- one that a single
additional firm has since erased.

### The weight distribution had to change, or the test could never reject

The first implementation used Rademacher (two-point) weights and enumerated all
sign vectors exactly. That is defensible at moderate cluster counts and wrong
here. Rademacher weights admit only 2^G distinct draws, and the t-statistic is
symmetric under flipping all of them, so at five clusters just 16 usable draws
remain and the smallest attainable p-value is 1/17 = 0.059. Six clusters do not
rescue it: 32 draws, floor 1/33 = 0.030, which technically clears 5% but leaves
a test with essentially no resolution.

**A 5% test built on those weights has exactly zero power against any effect of
any size.** It cannot reject, ever. That is a property of the weight
distribution, not of the data, and it would have made the reported null
meaningless.

Webb's six-point distribution -- +/-sqrt(1/2), +/-1, +/-sqrt(3/2), each with
probability 1/6 -- gives 6^G draws (46,656 at G = 6) and a floor of 1/(B+1) =
0.0001 at 9,999 replications. Webb (2023) and Stata's `wildbootstrap` both
switch to it at G <= 12, which is the rule now implemented.

The square roots matter and are easy to get wrong: informal summaries often
quote the points as +/-0.5, +/-1, +/-1.5, which gives E[w^2] = 7/6 rather than
1 and is not a valid wild bootstrap weight distribution. A test asserts the
moments.

With the corrected weights the null stands on its own terms rather than being
forced by granularity: every p-value remains above 0.13.

## Minimum detectable effect: the null is uninformative

Simulated against the actual H1 design (88 firm-quarters, 6 clusters, the real
collinearity structure), running the same pre-specified bootstrap, 400
replicates per point:

| true beta | power |
|---|---|
| 0.05 | 1.8% |
| 0.10 | 5.3% |
| 0.15 | 6.5% |
| 0.20 | 11.5% |
| 0.30 | 22.0% |
| 0.40 | 38.3% |
| 0.50 | 59.0% |
| **0.75** | **80.8%** |
| 1.00 | 90.3% |

**MDE at 80% power, alpha = 0.05: beta ~ 0.75.**

Read that against the outcome's scale. `log_ev_rev` has a standard deviation of
0.679 in this sample, and the index is z-scored. A detectable effect therefore
requires a one-standard-deviation improvement in repo health to move the
revenue multiple by a factor of e^0.75, roughly **2.1x** -- and to do so net of
firm and period fixed effects, growth, margin and size.

No plausible mechanism produces that. Against effects of the size actually
estimated (beta = +0.022), the design has **under 2% power**.

The sixth firm nearly halved the MDE, from ~1.4 to 0.75. That is the return to
one additional cluster at this sample size, and it is the strongest argument
for spending effort on universe coverage rather than on specification: at six
clusters the binding constraint is still G, not n.

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

## Look-ahead in the dependent variable: fixed

`log(EV/Rev)` paired a quarter-end price with LTM revenue that the market could
not see until the 10-Q filed. Measured across this universe, the earliest filing
lands a **median of 36-40 days after the quarter ends** (min 24). Forming the
multiple at the quarter-end price therefore asked whether prices reflected
information that had not yet been published.

The design doc offered two fixes -- lag the price to the filing date, or lag
fundamentals a quarter. EDGAR supports a third and more precise one: every XBRL
fact carries its filing date, so the multiple can be formed on the exact day the
revenue became public, with no assumed lag. That is now the headline definition.

One subtlety: XBRL repeats each fact in every later filing that shows it as a
comparative, so a single quarter carries filing dates spanning years (median 392
days if taken naively). Only the **earliest** is the publication date. Taking
any other silently understates the lag; a test asserts this.

All 127 rows are priced at their true filing date (median 37 days after quarter
end, max 75). The quarter-end variant is retained as `log_ev_rev_qend`:

| | beta | bootstrap p |
|---|---|---|
| H1, priced at filing (headline) | +0.022 | 0.794 |
| H1, priced at quarter end (robustness) | +0.001 | 0.987 |

The two measures correlate 0.94 and differ by 0.19 in logs on average, so the
correction is material even though the conclusion does not move. H2 is unchanged
by construction: its outcome is forward revenue growth, which contains no price.

### The filing date is a property of the filing, not of the revenue tag

Restricting the search for "when did this quarter become public" to the revenue
tags makes the answer hostage to tag choice, and firms change tags. Cloudera
reported total revenue as `SalesRevenueServicesNet` before ASC 606, a tag the
revenue reader does not use, so its FY2018 quarters carried no fact under the
tags searched until the FY2019 10-K restated them as comparatives. That dated
the quarter ending 2018-01-31 to **2019-03-29 -- a lag of 422 days** -- and
priced it with a stock price set fourteen months after the fact. Look-ahead of
the most direct kind, introduced by the fix for look-ahead.

The publication date belongs to the filing: whichever 10-Q or 10-K first
reports *any* fact for a period is the filing that made that period public. The
scan now covers every us-gaap duration fact. Checked against all eight
companyfacts payloads in `panel_cache/`, this changes Cloudera (422 -> 63 days)
and **nothing else** -- every other firm tagged revenue consistently, so the
generalisation costs nothing and removes a whole class of failure.

A second guard is still needed. companyfacts begins at a firm's first XBRL
periodic report, so pre-IPO quarters exist only as comparatives inside a later
filing; their real publication was the S-1, which companyfacts does not carry.
Every firm in the universe shows one such period end at a lag near 400 days. A
first-publication lag is bounded by statute -- a newly public company is a
non-accelerated filer, with 90 days for a 10-K and 45 for a 10-Q, plus 15 more
under Rule 12b-25 -- so 105 days is the outer legitimate limit and anything
beyond 120 is rejected outright. Those rows get no filing date and fall back to
the quarter-end price with `priced_at_filing = 0`.

After both fixes, all 127 rows price at a real filing date with a maximum lag of
75 days, and no row falls back. Neither fix moves a coefficient: the affected
quarters were dropped by the four-quarter LTM requirement anyway. They are
correctness guarantees, not results.

Repository metrics need no equivalent treatment -- git history is public as it
happens.

## What the controls say

The controls behave sensibly, which is the evidence that the panel measures
something real rather than noise:

- `growth_yoy` +1.24 (asymptotic p = 0.073) -- faster-growing firms carry higher
  revenue multiples, the expected direction and the dominant term.
- `log_rev` -0.92 (p = 0.11) -- larger firms on lower multiples, also the
  expected direction.
- `op_margin_ltm` -0.24 (p = 0.60), indistinguishable from zero.

(Asymptotic p-values, for shape only. Per the section above they are not
inference at six clusters; they are quoted here because the question is whether
the signs and relative magnitudes are sane, not whether the controls are
significant.)

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
   dropped iteratively across both dimensions before clustering. Removing the
   singleton rows -- 11 on the current universe -- moved no point estimate,
   exactly as that paper predicts; it is asserted as a test.

3. **No bootstrap.** Implemented as above.

A rank guard now refuses to report any rank-deficient fit rather than emitting
numbers that look like results.

## Why Hortonworks cannot identify anything

Hortonworks delisted in 2018Q3, and its panel rows span 2015Q3-2018Q3.

Cloudera *does* now overlap it in the raw panel (Cloudera opens 2017Q4), which
looked like it might rescue Hortonworks. It does not, and the reason is worth
recording. H1 requires `growth_yoy`, which needs eight matched quarters of
fundamentals, so Cloudera's estimation sample does not begin until 2019Q2 --
after Hortonworks is gone. The overlap exists in the data and is destroyed by
the control. Hortonworks' rows are therefore still singletons in the period
dimension and still drop, along with Cloudera's own 2018Q4 and 2019Q1.

This is a structural fact about the universe, not a data problem, and it is not
fixable by coarsening the time grid: with year effects the sets are still
disjoint. Restoring Hortonworks would require either dropping time fixed effects
in favour of an explicit macro control, or extending the universe with a firm
listed across the 2018-2019 gap that also has four prior years of fundamentals.

## Honest reading

At six clusters this panel cannot support a headline claim in either direction.
The pre-specified test finds no evidence that repo health is priced or
predictive, and -- per the MDE above -- it could only ever have detected effects
roughly thirty times larger than the one estimated. That is a null with no
evidential content.

The H2 collapse is the sharpest version of the point. A coefficient that halved
its way to zero when one firm arrived was never measuring anything; the same
must be assumed of every other cell in the table until the cluster count is
several times larger.

This converges with Part C, which found repo health largely reduces to
contributor headcount. Two independent designs, neither supporting an
incremental signal beyond what headcount and standard financials already carry.

## Open

- **Cloudera: resolved 2026-08-17.** A full-listing price export was supplied
  and reconciled against the prior one to the cent on all 235 overlapping
  dates. It now identifies.
- Confluent remains excluded by the attribution rule (21.8% firm share, 65.6%
  unattributable); see `decision-repo-attribution.md`. It is the only remaining
  candidate for a seventh cluster, and the MDE section is the argument for
  revisiting that decision explicitly rather than leaving it frozen.
- Hortonworks needs a bridging firm, not a better estimator.
