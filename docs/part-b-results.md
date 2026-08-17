# Part B results: do acquirers price repository health?

Reproduce with `gitdd panel deals panel.csv -o panel_results` (primary) and
`gitdd panel deals panel_7firm.csv -o panel_results_7firm` (Confluent arm).
Deal register: `panel/deals.toml`. Every date and price in it is hand-collected
from an 8-K or press release and then reconciled against the daily price tape;
`tests/test_panel_deals.py` asserts the reconciliation.

## Read this first

**Part B has five deals.** Not fifty. Every number below rests on five events,
and no regression is run on them, because five observations do not support one.
What is run instead is a set of exact, distribution-free tests whose *smallest
attainable p-value* is computed and reported alongside every result. At these
counts that floor, not the data, is usually what decides the outcome, and the
reader is entitled to see the ceiling before seeing the result.

The study design already called B2 "the weakest of the three" and said it
"should be framed as suggestive." With five deals even that is generous.

## The sample

| firm | announced | acquirer | consideration | premium | announcement return |
|---|---|---|---|---|---|
| Hortonworks | 2018-10-03 | Cloudera | stock, 1.305x | **+1.9%** | +11.9% |
| Cloudera | 2021-06-01 | CD&R + KKR | cash $16.00 | +24.4% | +23.9% |
| HashiCorp | 2024-04-24 | IBM | cash $35.00 | **+42.6%** | +18.7% |
| Couchbase | 2025-06-20 | Haveli | cash $24.50 | +29.4% | +29.4% |
| Confluent | 2025-12-08 | IBM | cash $31.00 | +34.0% | +29.1% |

Three of these five premiums would be wrong under the convention the design
originally implied, and getting them right required looking at the tape rather
than at the calendar.

## Getting the denominator right is most of the work

A premium is an offer divided by an "unaffected" price, and the textbook rule --
the close on the day before announcement -- is wrong for two of the five deals
here and ambiguous for a third.

**HashiCorp: the news broke a day early.** Bloomberg reported the deal on
2024-04-23 and HCP closed **+18.7%** that session, before IBM's official
announcement on the 24th. The day-before-announcement close is therefore already
an affected price. Using it gives a premium of +20.1%; using the last genuinely
unaffected close (2024-04-22, $24.55) gives **+42.6%**. The conventional rule
would have halved the largest premium in the sample.

**Hortonworks: the news broke after the bell.** The merger was announced on
2018-10-03 but HDP moved only +1.8% that session and **+11.9%** the next, so
2018-10-03 is the last unaffected close and 2018-10-04 the first affected one.

**Couchbase: the buyer was already visible.** Haveli had announced a stake and
accumulated to 9.8% from 2025-03-28, and the stock re-rated then. The company
quotes both a 29% premium to the pre-deal close and a 67% premium to the
2025-03-27 close, before its eventual buyer was known to be building a position.
Both are reported (`premium`, `premium_preleak`) because there is no principled
way to choose, and the gap between them is wider than the spread across the rest
of the sample.

These are not edge cases to be tidied away. Three of five deals needed a
judgement the standard rule gets wrong, which is a finding about event-study
methodology at this sample size, and the register records the reasoning per deal
so a reader can disagree with any of it.

### The one stock deal is a different animal

Hortonworks/Cloudera was an all-stock merger of equals, and its terms say so:
valuing 1.305 CLDR shares at Cloudera's *unaffected* close gives $22.29 against
HDP's $21.88, a premium of **+1.9%** against a cash-tender sample averaging over
30%. Valuing the ratio at Cloudera's *post*-announcement close would give ~+14%,
which would fold the market's verdict on the deal into the deal's own terms.
Pooling this observation naively with the four cash tenders is a category error;
it is retained, flagged, and its influence on B2 is reported.

## B2 -- terms: nothing, and the four-deal version was noise

| specification | Spearman(repo health, premium) | exact p | floor |
|---|---|---|---|
| Primary, 4 deals in panel | −0.800 | 0.333 | **0.083** |
| With Confluent, 5 deals | **−0.200** | **0.783** | 0.017 |

On four deals the rank correlation is −0.800, which looks like something. It is
not: the exact floor at n = 4 is 2/24 = **0.083**, so a four-deal B2 cannot
reach 5% however cleanly the ranks line up. And when Confluent supplies a fifth
deal the correlation collapses to −0.200 at p = 0.783, because Confluent pairs
the *highest* pre-deal repo health in the sample with the *second-highest*
premium — exactly against the pattern the four-deal version suggested.

**B2 is a null and the honest reading is that it was never capable of being
anything else.** Note the shape of that story: a suggestive coefficient
evaporating when one more observation arrives is precisely what happened to Part
A's H2 when Cloudera was added. Twice now, at both ends of the study, the
borderline result has been the one that failed to replicate.

## B1 -- selection: the acquired firms really were different

| | acquired | still independent |
|---|---|---|
| firms (primary / with Confluent) | 4 / 5 | 3 / 3 |
| mean repo health, last independent quarter | −0.578 / −0.476 | +0.600 / +0.592 |

The separation is **perfect** in both arms: every acquired firm sits below every
firm that stayed independent, on the last quarter in which it was still valued
as a standalone company.

| arm | firms | events | arrangements | exact p | floor |
|---|---|---|---|---|---|
| Primary | 7 | 4 | 35 | 0.057 | **0.057** |
| With Confluent | 8 | 5 | 56 | **0.036** | 0.036 |

Both land exactly on their floors, which is what perfect separation means: the
data are as extreme as the test can represent. And the floor is what decides
whether that clears 5%. At seven firms it is 2/35 = 0.057 and rejection is
*impossible*; at eight it is 2/56 = 0.036 and rejection is possible. **The one
Part B result that reaches conventional significance does so because the sample
went from seven firms to eight.** That is a fact about sample size at least as
much as about data, and it should be stated that way or not at all.

### And it is not a result about repository health

This is the check that matters, and it goes against the headline. The same exact
test, on the same firms, run over every other firm-level variable available:

| variable | exact p (8 firms) | separates perfectly? |
|---|---|---|
| active contributors | 0.036 | **yes** |
| bus factor | 0.036 | **yes** |
| **operating margin** | **0.036** | **yes** |
| repo health index | 0.036 | **yes** |
| top-author share | 0.036 | **yes** |
| log revenue | 0.071 | no |
| revenue growth | 0.571 | no |
| EV/Revenue | 1.000 | no |

**Operating margin separates the groups exactly as cleanly as the repo-health
index, and it requires no repository analysis whatsoever.** So do raw contributor
count and bus factor, which are components of the index rather than independent
evidence for it.

At eight firms a rank test cannot distinguish between these. The parsimonious
reading of B1 is the least surprising fact in mergers and acquisitions: the
companies that got bought were the smaller, less profitable ones. Repository
health is correlated with that, and the design has no way to show it adds
anything on top. Reporting "repo health predicts acquisition, p = 0.036" without
this table would be a straightforwardly misleading use of a true number.

The `deals` command prints this scan directly beneath the B1 result, with a
warning, so the confound cannot be omitted by accident.

### The asymptotic model reproduces Part A's failure exactly

For comparison only, a discrete-time hazard logit over the firm-quarter risk set:

| arm | firm-quarters | events | beta | asymptotic p |
|---|---|---|---|---|
| Primary | 122 | 4 | −2.038 | **0.047** |
| With Confluent | 137 | 5 | −1.496 | 0.056 |

The primary arm's logit reports p = 0.047 -- conventionally significant -- while
the valid exact test on the same data reports 0.057 and *cannot* reject. The
logit gets there by treating 122 serially correlated firm-quarters as
independent observations of what are really four firm-level events. It is the
same error as Part A's asymptotic cluster-robust standard errors, in a different
model, pointing the same way: **toward a publishable result that is not there.**
Controls are deliberately omitted; with four events the budget under the
ten-events-per-parameter convention is less than half a parameter, and adding
growth, margin and size produces separation rather than a better-specified model.

## What Part B contributes

1. **A clean null on deal terms** (B2), with the four-deal near-miss shown to be
   noise by the fifth deal.
2. **A perfectly separating but uninterpretable selection result** (B1): real,
   exact, significant in one arm -- and indistinguishable from operating margin.
3. **A third instance of the study's recurring methodological lesson.** Part A's
   cluster-robust SEs, Part A's Rademacher bootstrap floor, and now Part B's
   hazard logit all produced or would have produced significance where an exact
   or valid test finds none. Three independent occurrences in one project is no
   longer an anecdote.

Part B does **not** support a claim that acquirers price repository health. It
supports the weaker and duller claim that acquired open-source firms were
smaller and less profitable, which nobody needed a git-history tool to discover.

## Open

- The risk set contains only firms already in the Part A universe. The design
  named a wider candidate set (Talend, Chef, MariaDB, Splunk, New Relic, Sumo
  Logic, Instructure); each additional firm lowers the exact floor, which is the
  only thing that would give B1 room to say something.
- Announcement returns are **raw, not market-adjusted**: no index series is
  available offline. Over a one- to two-session window the market component is
  second-order, but it is an acknowledged approximation and the CAR column
  should be labelled as such in any write-up.
- Delisting returns (CRSP `DSEDELIST`) are still out of scope, so the terminal
  return of each deal is approximated by the last traded close.
