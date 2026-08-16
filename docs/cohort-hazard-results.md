# Part C results: does repository health predict project survival?

Discrete-time dormancy hazard, predictors lagged 6 quarters, activity
controlled, standard errors clustered by repository. Full specification surface
in `cohort_results/hazard_results.txt`, regenerable via
`scripts/estimate_hazard.py`.

**Answer: yes, but the construct largely reduces to one component.**
Contributor count robustly predicts survival and replicates across two
independent ecosystems. The other index components do not survive
specification changes.

## Primary specification (PyPI)

15,469 repository-quarters after lagging, 2,755 repositories, 1,071 events.

| predictor (lagged 6q) | hazard ratio | 95% CI | p |
|---|---|---|---|
| **log contributors** | **0.438** | 0.362–0.528 | **<0.001** |
| top author share | 0.704 | 0.518–0.956 | 0.024 |
| bus factor | 0.799 | 0.662–0.964 | 0.019 |
| churn gini | 1.310 | 0.892–1.924 | 0.168 |
| log commit volume *(control)* | 0.821 | 0.766–0.880 | <0.001 |

A one-log-unit increase in contributors is associated with a **56% lower
quarterly dormancy hazard**, six quarters ahead, holding activity constant.

## The lag is what makes this predictive

`commit_volume` at quarter q counts commits over (q−4, q]. A dormancy event at
t requires zero volume at both t and t−1, so the event implies no commits across
(t−5, t]. A predictor at t−L spans (t−L−4, t−L]; requiring no overlap with the
interval the event itself determines gives **L ≥ 5**, and 6 is used.

Without the lag the model is **not estimable at all** — contemporaneous
`commit_volume = 0` perfectly separates the outcome and the Hessian is singular.
The descriptive note that "commit_volume separates near-tautologically"
understated the problem: it is complete separation, the statistical signature of
conditioning on a component of the outcome. Any published repository-health
model regressing dormancy on contemporaneous activity is measuring its own
definition.

## Only contributor count is robust

| specification | log contributors | top author share | bus factor | churn gini |
|---|---|---|---|---|
| A. primary | **0.438**\*\*\* | 0.704\* | 0.799\* | 1.310 |
| B. no activity control | **0.341**\*\*\* | 0.595\*\* | 0.863 | 0.741 |
| C. no contributor count | — | 1.300 | 0.512\*\*\* | 1.143 |
| D. multi-contributor only | **0.312**\*\*\* | 1.474 | 1.059 | 1.512 |
| F. **npm replication** | **0.455**\*\*\* | 0.470 | 1.002 | 0.914 |

`***` p<0.001, `**` p<0.01, `*` p<0.05

**Contributor count** holds its sign, magnitude and significance in every
specification and replicates in an independently-drawn ecosystem (0.438 vs
0.455). Nothing else does:

- **top author share** flips direction between specifications — protective at
  0.704 when contributor count is included, harmful at 1.300 when it is removed
  (spec C) and 1.474 among multi-contributor repositories (spec D). It is −0.72
  correlated with log contributors, so its coefficient is reporting whatever the
  contributor term leaves behind, not a mechanism.
- **bus factor** is significant only where it can proxy for contributor count.
  Remove that term and it strengthens to 0.512; restrict to multi-contributor
  repositories and it is null (1.059, p=0.56); in the npm replication it is
  null (1.002, p=0.88).
- **churn gini** is never significant in any specification.

## This corrects an earlier interpretation

The Gini decision document proposed an "ownership" mechanism — that a committed
lead maintainer sustains a project where casual contributors do not — to explain
why concentration measures pointed away from the bus-factor rationale.

**The hazard model does not support that mechanism.** Concentration terms are
specification-unstable in exactly the way collinearity produces, and they flip
sign when the contributor term is removed. The parsimonious reading is that
contributor count carries the signal and the concentration measures inherit
fragments of it, not that concentration has an independent protective effect.

The *decision* that followed from it — remove `contributor_gini` from the
composite index, assert no sign — is unchanged and, if anything, better
supported. Specification E is the clearest evidence: adding Gini to a model
already containing contributor count and top-author share produces a hazard
ratio of **15.19 with a confidence interval of [2.27, 101.6]**, and drags log
contributors to 0.096 and top author share to 0.178. A coefficient spanning two
orders of magnitude is not a finding; it is a collinear design failing loudly.

## What this means for the study

1. **Part C's construct-validity question is answered.** Repository metrics do
   predict a project's own outcome, well ahead of it, controlling for activity,
   with replication. A null in Part A can now be interpreted.
2. **But "repository health" is largely contributor count.** The multi-component
   index does not earn its complexity in this population: four of five
   components are unstable or null once contributor count is present. This is a
   deflationary result and should be reported as one.
3. **Part A's hypothesis should be read accordingly.** If health reduces to
   contributor count, H1 is in substance "is contributor count priced?" — a
   sharper and more testable question than the composite framing.

## Limitations

- Dormancy is one outcome. Contributor collapse is implemented but not yet
  estimated; security incidents need external data that is unreachable here.
- The npm replication rests on a smaller harvested sample (377 repositories,
  145 lagged events) than PyPI. The contributor-count result replicates
  cleanly; the null results on other terms are less well powered.
- Clone attrition (~19–20%) is missing-not-at-random and plausibly biases
  against detecting mortality. Unbounded.
- Single-ecosystem-family evidence: both frames are package registries for
  interpreted languages.
