# Decision: `contributor_gini` sign convention

**Status:** Decided — pre-registration item, frozen before estimation
**Date:** 2026-08-13
**Decision:** **Remove `contributor_gini` from the composite index. Do not assert
either sign.** Report it standalone, with both directions and the evidence below.

> **Revision note.** This document first concluded "keep `sign = -1`, the
> reversal is a small-sample artifact (Deltas 2003)". That conclusion was
> **refuted by the falsification test this document itself specified** — see
> §"The test that refuted it". The artifact evidence is still correct and is
> retained below, because it explains part of the pattern; it just is not
> sufficient. The reasoning is left visible rather than rewritten, since the
> sequence is the justification for the final position.

## The question

The cohort measurement found the opposite of what the health index assumes.
Dormant repositories have *lower* Gini, and it replicates across both
independently-drawn ecosystems:

| | dormant | still active |
|---|---|---|
| PyPI (n=2,755) | 0.112 | 0.240 |
| npm (n=1,043) | 0.049 | 0.323 |

Taken at face value this says concentrated contribution *protects* a project,
inverting the bus-factor rationale behind the index. Flipping the sign would be
the naive response. It would also be wrong.

## Evidence

**1. The Gini is downward-biased in small samples, and the bias depends on n.**

> "The Gini coefficient is a **downward-biased** measure of inequality in **small
> populations**... The small-sample bias has often led to **misperceptions about
> trends in industry concentration**."
> — Deltas, G. (2003), *The Small-Sample Bias of the Gini Coefficient: Results
> and Implications for Empirical Research*, Review of Economics and Statistics
> 85(1), 226–234.

Deltas names our exact failure mode. The paper's stated implications are for
"(i) the comparison of inequality among **subsamples, some of which may be
small**, and (ii) the use of the Gini in measuring firm size inequality in
markets with a **small number of firms**." Comparing Gini between repositories
with 1–2 contributors and repositories with 3+ is case (i) precisely.

**2. Our dormant repositories are exactly the small-n group.** Median active
contributors: 1.571 vs 2.000 (PyPI), 1.500 vs 2.000 (npm). Fewer contributors
means more downward bias, which produces lower Gini *independently of any true
difference in concentration*. At n = 1 the Gini is identically 0 — perfectly
"equal" and maximally fragile — so the metric is not merely biased but
undefined in the 38–41% of the population that is single-author.

**3. Our Gini values sit far below the range where the measure is informative.**
In Apache Software Foundation projects, 88.97% of Gini values fall between 0.6
and 0.9, and only 9.51% fall below 0.6 ([Inequalities in Open Source Software
Development, PLOS One](https://journals.plos.org/plosone/article?id=10.1371%2Fjournal.pone.0152976)).
Our cohort medians are 0.05–0.37 — almost entirely beneath that distribution,
consistent with a population where the estimator is dominated by small-n bias
rather than by genuine variation in participation.

**4. The conventional sign is the field's, and it is not in dispute.** "A higher
Gini value (closer to 1) indicates strong concentration of activity in a small
group, while a lower value reflects more balanced participation. Low Gini with
high bus factor represents healthy teams with distributed contributions."
The index's original orientation matches the established interpretation; what
fails is the *estimator* in this population, not the *concept*.

**5. Replication across ecosystems supports the artifact reading, not against
it.** A mechanical estimator bias should reproduce in any population with the
same small-n structure — which is what happened. Replication distinguishes real
effects from sampling noise; it does not distinguish real effects from
systematic measurement bias.

## The test that refuted it

The falsification condition stated above was: *does the association survive
within contributor-count strata?* It does — at every level:

| contributors | repos | Gini dormant | Gini active |
|---|---|---|---|
| 2 | 1,200 | 0.233 | 0.277 |
| 3 | 339 | 0.335 | 0.394 |
| 4–5 | 266 | 0.394 | 0.461 |
| 6–10 | 173 | 0.514 | 0.548 |
| 11+ | 187 | 0.579 | 0.643 |

Gini is also mechanically bounded by *total commits* (two authors with two
commits can only produce Gini 0), so conditioning on contributor count alone is
not enough. Conditioning on **both** contributor count and commit volume:

| contributors | volume quartile | repos | dormant | active | direction |
|---|---|---|---|---|---|
| 2 | Q1 (low) | 270 | 0.167 | 0.167 | none |
| 2 | Q2–Q4 | 930 | — | — | lower = dead |
| 3–5 | Q1 (low) | 151 | 0.299 | 0.288 | reversed |
| 3–5 | Q4 (high) | 152 | 0.419 | **0.505** | lower = dead |
| 6+ | Q1 (low) | 90 | 0.461 | 0.407 | reversed |
| 6+ | Q4 (high) | 90 | 0.627 | **0.728** | lower = dead |

Nine of twelve cells keep the association; the three exceptions are **all in the
lowest volume quartile**.

**This is the decisive diagnostic.** A small-sample estimator artifact would be
*strongest where measurement is worst*. The observed pattern is the exact
opposite: the association vanishes or reverses in the least-measurable cells
(low volume) and is **largest where Gini is best estimated** (6+ contributors,
high volume — a 0.101 gap). Artifact cannot explain a relationship that
strengthens with measurement quality.

## Revised decision

`contributor_gini` **leaves the composite index**, joining `release_cadence`,
`merge_share` and `commit_volume` as a descriptive column rather than a scored
component. Neither sign is asserted, because the evidence now supports two real
mechanisms operating in opposite directions at different scales:

- **Bus-factor risk** (the index's original rationale): concentration is
  dangerous because losing the key person kills the project. This is a *tail*
  risk over *long* horizons.
- **Ownership**: a project with a committed lead maintainer persists, while one
  where a few casual contributors each commit a little has nobody who will carry
  it. This dominates *dormancy within a few years* — which is what we measure.

Both are plausible and the data supports the second at our horizon. A composite
index must assert a sign; this metric does not have a stable one across scales,
so averaging it into the index would encode an arbitrary choice as a
measurement. Removing it is the honest option — the same reasoning already
applied to `release_cadence`.

Consequent handling, frozen now:

1. **Gini is not identified below 2 contributors** (identically 0 by
   construction, 43% of the cohort). Emitted as `None`, never `0.0`, with a
   `gini_identified` flag — enforced in `cohort/outcomes.py` so the artifact
   cannot silently re-enter an analysis.
2. **Never pooled across contributor counts or volume levels.** Both the naive
   pooled comparison and the conditioned one are reported.
3. The ownership-vs-bus-factor tension is reported as a **finding**, not
   smoothed away. It is a substantive result about repository-health indices:
   a metric widely assumed to have one healthy direction has a
   scale-dependent one.

## Sources

- Deltas, G. (2003). [The Small-Sample Bias of the Gini Coefficient](https://www.semanticscholar.org/paper/The-Small-Sample-Bias-of-the-Gini-Coefficient:-and-Deltas/a990000c874832229e9356a177f1ca64645b6c00). *Review of Economics and Statistics* 85(1), 226–234.
- [Inequalities in Open Source Software Development: Analysis of Contributor's Commits in Apache Software Foundation Projects](https://journals.plos.org/plosone/article?id=10.1371%2Fjournal.pone.0152976), PLOS One.
- [A Practical Guide to Proper Estimation and Inference of the Gini Index](https://link.springer.com/article/10.1007/s11205-026-03831-x), Social Indicators Research.
