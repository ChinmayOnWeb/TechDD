# Part C Pre-registration v0

**Study:** Repository Health: Does It Matter, and to Whom?  
**Part:** C — construct validity at repository level  
**Status:** Frozen before confirmatory estimation  
**Code baseline:** `875907f6094323c43d795a7316cadc2d42dd7cac` on `master`  
**Primary ecosystem:** PyPI  
**Replication ecosystem:** npm

This document freezes the confirmatory Part C analysis before any hazard-model
coefficient, p-value, confidence interval, or model-selection result is inspected.
Descriptive cohort summaries already recorded in
`docs/cohort-preliminary-findings.md` are treated as pilot/measurement evidence,
not confirmatory inference.

## 1. Research question

Do repository-health characteristics measured at quarter `t` predict subsequent
repository dormancy after conditioning on recent development activity?

The confirmatory claim is predictive/construct-validity, not causal. No coefficient
is interpreted as the causal effect of changing a repository metric.

## 2. Unit of analysis and risk set

The unit is repository-quarter.

A repository enters the risk set when its first analyzable quarter is observed and
remains at risk until the first dormancy event or the end of the observation window.
Quarters after the first event are excluded. Repositories without an event are
right-censored at their final observable quarter.

No minimum follow-up exclusion is applied. No minimum-commit exclusion above the
mechanical floor is applied. These decisions are already frozen in
`docs/cohort-exclusions.md`.

## 3. Primary outcome

The primary endpoint is **dormancy** as implemented by
`cohort.outcomes.first_dormancy` at the frozen code baseline.

A dormancy event occurs when `DORMANCY_QUARTERS = 2` consecutive quarterly metric
rows have `commit_volume == 0`.

Because `commit_volume` is measured over a trailing 365-day window, this definition
corresponds to roughly 18 months of inactivity rather than six months. The event is
dated at the end of the qualifying silent run, not its beginning.

The dormancy definition must not be changed after confirmatory estimation begins.

## 4. Secondary outcome

**Contributor collapse** is secondary and must not be used to rescue a null primary
result.

It is defined exactly as implemented at the frozen baseline:
- active contributors fall by at least 50%;
- comparison horizon is four quarters;
- the base quarter must have at least two contributors.

Results for contributor collapse are reported separately from dormancy.

## 5. Primary estimator

The primary estimator is a **discrete-time hazard model** fit to repository-quarter
rows.

Primary link: complementary log-log.

The model includes an explicit baseline-hazard term for repository age in quarters.
Repository age is represented categorically where computationally practical; if the
number of age levels makes this unstable, a pre-specified low-dimensional spline or
piecewise age function may be used, but that choice must be documented before
examining predictor significance.

Standard errors are clustered by repository.

A Cox proportional-hazards model with time-varying covariates is a registered
robustness analysis, not the primary estimator.

## 6. Time ordering

All predictors are time-varying.

Predictor values at quarter `t` may use only repository history available through
quarter `t`. No baseline-only specification is confirmatory.

Rows after an event are excluded from the risk set. No post-event metric may enter a
predictor or control.

## 7. Primary structural predictors

The primary structural predictor block is:

1. `log1p(active_contributors)`
2. `top_author_share`
3. `log1p(bus_factor_50)`
4. `churn_gini`

Predictors are entered individually in the primary model rather than collapsed into
a single repository-health index. This avoids importing large-company index sign
assumptions into a registry-scale population where some components are structurally
degenerate.

For interpretation, signs expected to represent healthier structure are:
- more active contributors: lower hazard;
- lower top-author share: lower hazard;
- larger bus factor: lower hazard.

No confirmatory directional claim is registered for `churn_gini`; its coefficient
is reported two-sided.

## 8. Contributor Gini

`contributor_gini` is **not a primary predictor**.

Pilot measurement established that it is unidentified for single-contributor
quarters and its marginal sign reverses across scale. It remains a registered
secondary analysis restricted to observations where
`gini_identified == 1`, with contributor count retained in the model.

Both coefficient sign and uncertainty must be reported. The analysis must not choose
a sign convention based on which direction is statistically significant.

## 9. Required activity control

`log1p(commit_volume)` is included in every confirmatory dormancy model.

This is mandatory because the outcome is defined by future inactivity and recent
activity is therefore near-mechanically predictive. The substantive question is
whether structural repository characteristics predict dormancy conditional on
recent activity.

`merge_share` is descriptive/robustness-only unless explicitly required by a
registered sensitivity specification.

## 10. Solo and multi-contributor strata

The population is not pooled naively.

A repository is classified as **solo** if it never exceeds one active contributor
during its observed history; otherwise it is **multi-contributor**.

Primary structural inference is reported for the multi-contributor stratum, where
ownership/concentration measures are identified.

Solo repositories remain in the study and receive a separate hazard analysis focused
on activity, churn, and age. They are never excluded from population counts or event
rates.

A pooled model with a solo indicator and registered interactions may be reported as
robustness, but it cannot replace the stratified headline results.

## 11. Ecosystems

PyPI is the primary confirmatory ecosystem.

npm is an independent replication ecosystem. The two frames are analyzed separately
and are not pooled for the headline result.

A result is called replicated only when the corresponding coefficient direction is
consistent across ecosystems and uncertainty is reported in both. Statistical
significance in only one ecosystem is not described as replication.

## 12. Missingness

Missing predictor values are never silently converted to zero.

Confirmatory models use complete cases for the variables required by that specific
model. The number and fraction of rows/repositories removed for missingness are
reported by variable and ecosystem.

No predictor is dropped or imputed after seeing its coefficient merely to increase
sample size or significance.

## 13. Clone attrition

Registry entries whose repository cannot be cloned remain part of the documented
sampling frame but cannot enter the measured hazard sample.

Clone-failure rates are reported separately for PyPI and npm. Because deletion or
privatization is plausibly related to dormancy, clone attrition is treated as
missing-not-at-random.

A registered bounding/sensitivity analysis must compare plausible extreme outcomes
for failed clones; failed clones must not be silently treated as healthy survivors.

## 14. Confirmatory models

For each ecosystem, report at minimum:

### Model C1 — activity baseline
- baseline hazard / repository age
- `log1p(commit_volume)`

### Model C2 — structural model
- all C1 terms
- `log1p(active_contributors)`
- `top_author_share`
- `log1p(bus_factor_50)`
- `churn_gini`

C2 on the multi-contributor stratum is the primary structural test.

### Model C3 — Gini secondary
- C2 terms
- `contributor_gini`
- only rows where `gini_identified == 1`

C3 is secondary regardless of statistical significance.

## 15. Registered robustness surface

The following must be reported regardless of outcome:

- Cox model with time-varying covariates;
- pooled solo/multi model with a solo indicator and pre-specified interactions;
- contributor-collapse secondary endpoint;
- alternative dormancy threshold of 1 and 3 consecutive zero-commit quarters;
- models with and without `churn_gini`;
- clone-attrition bounding analysis;
- npm replication of all primary PyPI models.

No additional specification becomes headline because it produces a smaller p-value.

## 16. Multiplicity and reporting

The primary inferential family is the four structural coefficients in PyPI Model C2.

Report raw two-sided p-values and a family-wise or false-discovery adjustment across
those four coefficients. The adjustment method must be chosen in code before results
are printed and applied mechanically.

Effect sizes and confidence intervals are primary reporting objects; statistical
significance alone is not treated as evidence of practical importance.

All registered null results are reported.

## 17. Diagnostics

Before interpretation, report:

- number of repositories;
- number of repository-quarters;
- number of dormancy events;
- censoring fraction;
- solo/multi counts;
- rows removed by missingness;
- distribution of repository age;
- event rate by ecosystem;
- coefficient stability under the registered robustness surface;
- proportional-hazards diagnostics for the Cox robustness model.

No model is replaced solely because a diagnostic is inconvenient; deviations from
this registration require a dated amendment explaining the reason before inspecting
the replacement model's result.

## 18. Reproducibility

Confirmatory estimation must record:

- Git commit SHA;
- frame file hashes;
- harvest file hashes;
- Python/package versions;
- exact model command;
- random seeds where applicable;
- output artifact hashes.

Generated model outputs are immutable evidence for that run and must not be manually
edited.

## 19. Interpretation rule

Part C succeeds as construct-validation evidence when structural repository metrics
show stable predictive content for subsequent dormancy after controlling for recent
activity, with directionally consistent replication in npm.

A PyPI null is reported as a null. An npm-only result does not rescue a PyPI null.
If structural metrics fail while activity predicts dormancy strongly, the conclusion
is that the proposed structural health construct adds little predictive information
beyond activity under this design.
