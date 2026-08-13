# Part C: measurement findings

From the harvested cohort: **3,798 usable repositories, 41,596 repository-quarters**
across two independently-drawn ecosystem frames. **Descriptive only** — the
hazard model is the actual test. Recorded because three of these findings change
how the estimation must be specified, and one challenges an assumption baked
into the health index.

Both frames are random subsamples of their complete-enumeration draws (frame
order is random: 51% adjacent out-of-order pairs, halves indistinguishable on
staleness and release count), so partial harvests are unbiased rather than
biased prefixes.

## Cohort summary

| | PyPI (primary) | npm (robustness) |
|---|---|---|
| attempted | 3,485 | 1,369 |
| usable | 2,755 | 1,043 |
| repository-quarters | 29,973 | 11,623 |
| clone-failure rate | 19% | 20% |
| dormancy event rate | **60%** | **67%** |
| solo (never >1 contributor) | **38%** | **41%** |

npm is the deader ecosystem on both frame staleness (47% vs 38% with no release
since 2023) and realised mortality (67% vs 60%), consistent between the two
independent measurements.

## 1. Findings replicate across both ecosystems

Every predictor separates in the same direction in both frames — the point of
carrying a robustness ecosystem rather than pooling:

| predictor (median over active quarters) | PyPI dormant | PyPI active | npm dormant | npm active | same direction |
|---|---|---|---|---|---|
| active_contributors | 1.571 | 2.000 | 1.500 | 2.000 | ✅ |
| contributor_gini | 0.112 | 0.240 | 0.049 | 0.323 | ✅ |
| churn_gini | 0.632 | 0.685 | 0.695 | 0.783 | ✅ |
| commit_volume | 15.200 | 32.091 | 12.000 | 51.000 | ✅ |

## 2. Roughly 40% of the population is single-author

38% (PyPI) and 41% (npm) of repositories never exceed one contributor. For
those, `bus_factor_50 = 1`, `top_author_share = 1.0` and `contributor_gini = 0`
**by construction** — four of the six index components are constants, so the
health construct is only partially identified in that subpopulation.

This follows from sampling the ecosystem honestly. The index was designed
against large corporate repositories (GitLab peaks around 1,360 contributors);
the median randomly-sampled package is a one-person project. Solo projects are
*not* excluded — that would repeat the selection-on-outcome error — but results
should be reported **stratified by solo / multi-contributor**.

## 3. Baseline-quarter predictors are degenerate — use time-varying covariates

Comparing predictors at each repository's *first* observed quarter shows no
difference at all between projects that later died and those that did not: every
project starts as one person's first commits. A baseline-covariate specification
would find nothing, for a reason unrelated to the hypothesis. Predictors must
enter as **time-varying covariates** across all repository-quarters, which is
what `observation_rows()` emits.

## 4. `commit_volume` separates strongly — but near-tautologically

Volume shows the largest gap in both ecosystems (PyPI 0.47×, npm 0.24×) and is
the least interesting: dormancy *is* the absence of commits, so a low-activity
project being more likely to become a no-activity project is close to
definitional.

The substantive question is whether the **structural** metrics predict dormancy
*conditional on* activity. Activity must therefore enter the hazard model as a
control, or the structural coefficients will simply absorb it.

## 5. `contributor_gini` carries the wrong sign for this population

The health index treats **lower** Gini as healthier (`sign = -1`), reasoning that
concentrated contribution is a bus-factor risk. In both ecosystems the
association runs the other way, and strongly: dormant repositories have *lower*
Gini (PyPI 0.112 vs 0.240; npm 0.049 vs 0.323).

The explanation is mechanical rather than substantive: **Gini is confounded with
contributor count.** A one-author project has Gini 0 by definition — perfectly
"equal", and also maximally fragile. Inequality cannot exist until there are
several contributors, so low Gini here proxies for *few contributors*, not for
equitable participation.

Consequences:

- The index's sign assumptions were derived from large corporate repositories
  and do not transfer to a randomly-sampled ecosystem.
- Gini should be reported both raw and conditional on contributor count.
- **Pre-registration decision:** freeze the sign convention before estimation and
  report the alternative as robustness, rather than choosing the sign after
  seeing which one works. This is the single most important open item.

## 6. Clone attrition is missing-not-at-random

19–20% of frame repositories fail to clone (deleted, renamed, or made private),
consistent across both ecosystems. Deleted repositories are plausibly *more*
likely to be dead ones, so this attrition likely biases **against** detecting
mortality. Reported as a rate; warrants a bounding exercise rather than silent
exclusion.

## Open item

Whether these directions survive in the hazard model with activity controlled is
the actual test, and is not answered here.
