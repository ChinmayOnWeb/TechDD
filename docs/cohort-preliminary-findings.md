# Part C: preliminary measurement findings

From the first ~800 PyPI repositories of the full sweep. **Descriptive only** —
the hazard model on the complete cohort is the actual test. Recorded now because
three of these findings change how the estimation should be specified, and one
of them challenges an assumption baked into the health index.

## 1. A third of the population is single-author

| peak contributors ever | repos | share |
|---|---|---|
| 1 (solo) | 274 | **34.5%** |
| 2 | 209 | 26.3% |
| 3–5 | 167 | 21.0% |
| 6–10 | 69 | 8.7% |
| 11+ | 75 | 9.4% |

For the 35% that never exceed one contributor, `bus_factor_50 = 1`,
`top_author_share = 1.0` and `contributor_gini = 0` **by construction** — four of
the six index components are constants, so the health construct is only
partially identified in that subpopulation.

This is a consequence of sampling the ecosystem honestly. The index was designed
against large corporate repositories (GitLab peaks around 1,360 contributors);
the median randomly-sampled PyPI package is a one-person project. Solo projects
are *not* excluded — that would be the selection-on-outcome error again — but
results should be reported **stratified by solo / multi-contributor**, since the
two subpopulations support different amounts of identification.

## 2. Baseline-quarter predictors are degenerate — use time-varying covariates

Comparing predictors at each repository's *first* observed quarter shows no
difference whatsoever between projects that later died and those that did not:
every project starts as one person's first commits. A baseline-covariate
specification would therefore find nothing, for a reason that has nothing to do
with the hypothesis.

The predictors must enter as **time-varying covariates** across all
repository-quarters, which is what `observation_rows()` emits. Measured over each
repository's active quarters, the differences appear:

| predictor (median over active quarters) | dormant | still active | ratio |
|---|---|---|---|
| active_contributors | 1.67 | 2.00 | 0.83× |
| contributor_gini | 0.139 | 0.254 | 0.55× |
| churn_gini | 0.650 | 0.690 | 0.94× |
| commit_volume | 18.0 | 38.2 | **0.47×** |
| bus_factor_50 | 1.00 | 1.00 | 1.00× |

Restricted to multi-contributor repositories the pattern holds and sharpens on
volume (23.5 vs 56.8, 0.41×).

## 3. `commit_volume` separates strongly — but near-tautologically

Volume shows the largest gap, and it is the least interesting one: dormancy *is*
the absence of commits, so a low-activity project being more likely to become a
no-activity project is close to definitional rather than a finding.

The substantive question is whether the **structural** metrics — contributor
count, concentration, bus factor — predict dormancy *conditional on* activity
level. Activity must therefore enter the hazard model as a control, not be
omitted, or the structural coefficients will simply absorb it.

## 4. `contributor_gini` may carry the wrong sign for this population

The health index treats **lower** Gini as healthier (`sign = -1`), on the
reasoning that concentrated contribution is a bus-factor risk. In this
population the association runs the other way: dormant repositories have
*lower* Gini (0.139 vs 0.254), and the direction survives restricting to
multi-contributor repositories (0.278 vs 0.375).

The likely explanation is mechanical rather than substantive: **Gini is
confounded with contributor count.** A one-author project has Gini 0 by
definition — perfectly "equal", and also maximally fragile. Inequality cannot
exist until there are several contributors, so low Gini here is a proxy for
*few contributors*, not for equitable participation.

Consequences:

- The index's sign assumptions were derived from large corporate repositories
  and should not be assumed to transfer to a randomly-sampled ecosystem.
- Gini should be reported both raw and conditional on contributor count.
- This is a **pre-registration decision**: freeze the sign convention before
  estimation, and report the alternative as robustness rather than choosing the
  sign after seeing which one works.

## Open item

Whether these directions survive in the hazard model with activity controlled is
the actual test, and is not answered here. The full sweep (PyPI + npm, ~9,000
repositories) is required before estimating anything.
