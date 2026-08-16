# Decision: flagship-repository attribution for Part A

**Status:** Decided — applied ex ante, before any metric was computed
**Date:** 2026-08-13
**Rule:** the study spec's own inclusion criterion, applied as a measurement:

> where the flagship repo is a foundation project the firm dominates rather than
> owns, the firm is included only if its employees authored a **plurality of
> commits** over the sample window (measurable from author-email domains);
> otherwise excluded.

Measured with `panel/attribution.py`, over each firm's listed window, with bots
excluded first (Apache projects carry heavy CI and Jira automation) and
unattributable authors reported rather than dropped.

## Measurements

| firm | repository | commits | firm share | unattributable | leading rival | verdict |
|---|---|---|---|---|---|---|
| Cloudera | apache/impala | 4,255 | **84.1%** | 15.0% | 0.4% | **include** |
| Couchbase | couchbase/kv_engine | 5,971 | **65.4%** | 29.2% | 0.9% | **include** |
| Hortonworks | apache/ambari | 15,918 | **61.2%** | 35.1% | 2.1% | **include** |
| HashiCorp | hashicorp/terraform | 4,718 | 22.5% | 58.9% | 12.9% | **include** (firm-owned; rule N/A) |
| **Confluent** | apache/kafka | 7,998 | **21.8%** | **65.6%** | 3.1% | **exclude** |

## Confluent is excluded, and the reason is the unattributable share

Confluent passes the *letter* of the test — 21.8% exceeds Aiven's 3.1%, so it
holds a technical plurality of identifiable employers. It fails the substance:
**65.6% of Kafka commits cannot be attributed to any employer** from git alone
(personal addresses, `users.noreply.github.com`, `apache.org`). A plurality
computed over one third of the data does not establish that the firm dominates
development; it establishes that among the minority who commit from corporate
addresses, Confluent leads.

The spec's rule exists precisely for this case and its default is explicit —
"otherwise excluded". Including Confluent on a 21.8% share would mean measuring
Apache Kafka's community and attributing its health to Confluent's valuation,
which is the repo-≠-firm error the rule was written to prevent.

**Alternative not taken:** Confluent owns `confluentinc/ksql`,
`confluentinc/schema-registry` and similar, where attribution is unambiguous.
Those are not the flagship — Confluent's product is managed Kafka — so
substituting one would trade an attribution problem for a relevance problem,
and quietly change what the firm's "repository health" means relative to every
other firm in the panel. Flagged for the analyst; not decided unilaterally.

## HashiCorp illustrates why the rule is scoped to foundation projects

HashiCorp's own share of its **own** repository is only 22.5%, with 58.9%
unattributable and a single personal domain at 12.9% (almost certainly an
employee committing from a personal address). If the plurality rule were applied
to firm-owned repositories it would exclude HashiCorp from its own product.

That is not a defect in the measurement — it is what open-source contribution
looks like from the outside. It does mean the rule must stay scoped to
foundation projects, where *ownership* is genuinely in question, and it is a
caution against reading any firm-share number as "how much of this project the
company builds".

## Consequence for the panel

Four of five delisted candidates carry a defensible flagship assignment. With
GitLab, MongoDB and Elastic already included, the universe reaches **7 firms**
once the EDGAR fundamentals for the four are re-supplied.

Cloudera additionally has a price-coverage gap (2020-11 → 2021-10 only, against
an April 2017 listing), so it contributes roughly 4 quarters rather than ~18
unless a wider export is obtained.
