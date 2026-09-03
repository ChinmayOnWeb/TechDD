# Part A candidate-universe and data-completeness audit

**Audit date:** 2026-09-03
**Status:** pre-regression qualification audit; no candidates admitted
**Scope:** 12 controls/candidates; no repository recovery, regressions, panel build, or full-history clones

## 1. Executive summary

The corrected screen finds **no GREEN, eight YELLOW, and four RED firms**. The revision fixes two scientific errors in the first audit:

1. it separates raw-source quality from compatibility with TechDD's current concepts; and
2. it corrects MariaDB's public identity and Couchbase's acquisition endpoint.

Missing supported debt is not automatically bad source data. Primary filings support genuine zero-borrowing periods for GitLab, HashiCorp, Couchbase, Confluent, Elastic, Cloudera, Hortonworks, MuleSoft, and Pivotal. TechDD still correctly returns `None`: it has no general, provenance-bearing zero assertion mechanism. MongoDB additionally exposes a real perimeter question because finance-lease liabilities remain after its convertible notes convert.

- **YELLOW:** Elastic, MongoDB, GitLab, HashiCorp, Couchbase, Confluent, Hortonworks, MariaDB.
- **RED:** Cloudera, Talend, MuleSoft, Pivotal.
- **GREEN:** none, because CRSP is unverified and every candidate retains another gate.

The dedicated [debt-semantics audit](part-a-debt-semantics-audit.md) freezes the evidence, classifications, concept candidates, and recommended general rule. No production rule changes in this PR.

## 2. Qualification methodology

The gates were applied without using regression results:

1. **Corporate/security identity:** SEC CIK, ticker, fiscal year end, IPO/listing event, and acquisition/delisting event are recorded separately. Acquisition completion is not asserted to be the last trading date; CRSP must establish the latter.
2. **Repository attribution:** HIGH is a firm-controlled core upstream; MEDIUM is a distributed firm product or foundation project needing attribution; LOW is an incomplete/ambiguous economic proxy.
3. **Public grid:** fiscal month ends within the expected listed window, using the production grid convention. Open controls retain the frozen 2026-06-30 cutoff.
4. **Raw fundamentals:** `source_fundamental_status` assesses whether SEC filings/CompanyFacts provide the underlying accounting evidence, regardless of current code.
5. **Current compatibility:** `extractor_compatibility` assesses the unchanged production contract. `current_extractor_usable_quarters` counts endpoints with revenue, cash, a currently supported debt fact, and shares; it is **not** a source-completeness count.
6. **Prices:** actual CRSP was not available. `EXPECTED` means the security should ordinarily be identifiable but was not inspected; `UNKNOWN` means even entity mapping is unresolved. HCP is UNKNOWN because the ticker was reused and no PERMNO was verified.
7. **Verdict:** GREEN requires every gate. YELLOW includes viable underlying data blocked by an unresolved general method, attribution test, price verification, or a short legitimate window. RED requires an independent suitability failure, not merely `debt=None`.

The extractor counts precede four-quarter LTM construction, the 14-day price rule, positive EV, and repository metrics. Final usable overlap therefore remains blank unless all inputs are verified.

## 3. Master candidate table

| Firm | Ticker / CIK | Expected public window; FYE | Repository / attribution | Quarters | Source fundamentals | Extractor | Current usable | Price | Principal issue | Verdict |
|---|---|---|---|---:|---|---|---:|---|---|---|
| Elastic | ESTC / 0001707753 | 2018-10-05–cutoff; Apr | `elastic/elasticsearch`; HIGH | 31 | COMPLETE | PARTIAL | 21 | EXPECTED | Ten filing-supported zero-debt quarters need evidence records | YELLOW |
| MongoDB | MDB / 0001441816 | 2017-10-19–cutoff; Jan | `mongodb/mongo`; HIGH | 35 | COMPLETE | PARTIAL | 19 | EXPECTED | Early shares; one debt match; post-note finance-lease perimeter | YELLOW |
| GitLab | GTLB / 0001653482 | 2021-10-14–cutoff; Jan | `gitlab-org/gitlab`; HIGH | 19 | COMPLETE | BLOCKED | 0 | EXPECTED | All debt endpoints are filing-supported zeros, not encoded | YELLOW |
| HashiCorp | HCP / 0001720671 | 2021-12-09–2025-02-27; Jan | `hashicorp/terraform`; HIGH | 13 | PARTIAL | BLOCKED | 0 | UNKNOWN | Zero debt supported; final revenue and reused-ticker mapping unresolved | YELLOW |
| Couchbase | BASE / 0001845022 | 2021-07-22–2025-09-24; Jan | `couchbase/manifest`; MEDIUM | 17 | COMPLETE | BLOCKED | 2 | EXPECTED | Repaid debt; product source is distributed; last trade unknown | YELLOW |
| Confluent | CFLT / 0001699838 | 2021-06-24–2026-03-17; Dec | `apache/kafka`; MEDIUM | 19 | COMPLETE | PARTIAL | 17 | EXPECTED | Two pre-note zeros; Apache employee plurality untested | YELLOW |
| Cloudera | CLDR / 0001535379 | 2017-04-28–2021-10-08; Jan | `apache/impala`; LOW | 18 | COMPLETE | PARTIAL | 4 | EXPECTED | One Apache repo does not proxy the commercial platform | RED |
| Hortonworks | HDP / 0001610532 | 2014-12-12–2019-01-03; Dec | `apache/ambari`; MEDIUM | 17 | COMPLETE | BLOCKED | 0 | EXPECTED | Filing-supported zeros; foundation attribution unverified | YELLOW |
| Talend | TLND / 0001668105 | 2016-07-29–2021-08-09; Dec | not established; LOW | 20 | COMPLETE | BLOCKED | 8 | EXPECTED | No canonical product repo; 20-F→10-K compatibility seam | RED |
| MuleSoft | MULE / 0001374684 | 2017-03-17–2018-05-02; Dec | `mulesoft/mule`; HIGH | 5 | COMPLETE | BLOCKED | 0 | EXPECTED | Only five quarters; current revenue concepts do not match | RED |
| Pivotal | PVTL / 0001574135 | 2018-04-20–2019-12-30; Feb | Cloud Foundry controller; LOW | 7 | COMPLETE | BLOCKED | 0 | EXPECTED | Short window, portfolio/repo mismatch, revenue concepts | RED |
| MariaDB | MRDB / 0001929589 | 2022-12-19–~2024-08-23; Sep | `MariaDB/server`; HIGH | 7 | COMPLETE | PASS | 7 | EXPECTED | Short history; exact final trade/CRSP not verified | YELLOW |

The acquisition endpoints above are corporate completion/deregistration boundaries except MariaDB's SEC-indicated expected final-trading date. None is claimed as an exact market-data endpoint; CRSP must supply actual last observations.

## 4. Concise evidence by candidate

### Controls

- **Elastic — YELLOW.** Firm-owned core history and 31 expected quarters. Filings support no borrowing before the July 2021 notes: 10 `ZERO_SUPPORTED_BY_FILINGS`, one `REPORTED_ZERO`, then 20 `REPORTED_NONZERO`. Source data is complete; code compatibility is partial.
- **MongoDB — YELLOW.** Firm-owned core and 35 quarters. Supported notes cover most history, but early share extraction is incomplete, March 2018 issuance creates one match gap, and post-conversion finance leases require a general EV-debt definition. It is not a raw-source failure.
- **GitLab — YELLOW (was RED).** Canonical GitLab upstream and 19 quarters. Its pre-IPO line terminated unused; public balance sheets contain no borrowing. All 19 debt endpoints are `ZERO_SUPPORTED_BY_FILINGS`. The source is complete, while current extraction is blocked.

### Primary expansion candidates

- **HashiCorp — YELLOW (was RED).** Terraform is a HIGH-attribution core. Filed statements affirm no balance under its facility. The source is viable, but the zero ledger, final revenue, and reused-HCP security identity remain unresolved.
- **Couchbase — YELLOW (was RED).** The $25 million balance was repaid September 1, 2021; later filings explicitly report no debt outstanding. Acquisition completed **2025-09-24**, not September 17. Its exact last trade is pending CRSP. The distributed source graph—not financial source quality—is the other gate.
- **Confluent — YELLOW.** Seventeen supported nonzero quarters follow two filing-supported pre-note zeros. Fundamentals are strong; Apache Kafka employee plurality and CRSP remain unverified.

### Historical/secondary candidates

- **Cloudera — RED.** Fourteen filing-supported zeros precede the late supported term loan. Debt is understandable, but LOW economic attribution for a single Apache repository independently fails.
- **Hortonworks — YELLOW (was RED).** Its facilities repeatedly had no outstanding borrowings, so 17 missing supported facts are evidence-backed zeros. It remains conditional on Apache employee plurality and price verification.
- **Talend — RED.** Raw filings are available, including debt under supported and current/combined tags. The eight current-extractor quarters are reproducible: Talend transitioned from 20-F to 10-K, and the production helper accepts 10-Q/10-K but not 20-F. LOW repository attribution remains decisive.
- **MuleSoft — RED.** HIGH product attribution and filing-supported zero borrowing do not overcome a five-quarter public window and incompatible revenue concepts.
- **Pivotal — RED.** Its facility was repaid and year-end debt explicitly zero. The short window, LOW single-repository attribution, and revenue incompatibility remain independent failures.
- **MariaDB — YELLOW (was RED).** MariaDB plc **was public**: CIK **0001929589**, ticker **MRDB**, NYSE trading began **2022-12-19**, and SEC transaction materials anticipated final trading around **2024-08-23**. The September-year-end grid has seven quarters. All seven pass current fundamentals, including supported nonzero debt. The core repository predates listing. Its short legitimate history and unverified CRSP endpoint keep it YELLOW.

## 5. Data-completeness and debt findings

Raw source quality and code compatibility differ materially:

- **Source COMPLETE, extractor debt-blocked:** GitLab, Couchbase, Hortonworks.
- **Source PARTIAL, extractor blocked:** HashiCorp because the terminal revenue period is unavailable, despite supported zero debt.
- **Source COMPLETE, extractor partial:** Elastic, MongoDB, Confluent, Cloudera.
- **Extractor PASS:** MariaDB, seven of seven endpoints.
- **Other compatibility blockers:** Talend, MuleSoft, and Pivotal primarily involve form/revenue concepts, not debt.

The evidence supports a general rule only when an immutable filing affirmatively establishes zero borrowing. Missing CompanyFacts alone can never trigger zero. See the methodology note for required ledger fields and the concept inventory.

## 6. Repository-attribution findings

- **HIGH:** Elastic, MongoDB, GitLab, HashiCorp, MuleSoft, MariaDB.
- **MEDIUM:** Couchbase, Confluent, Hortonworks.
- **LOW:** Cloudera, Talend, Pivotal.

Couchbase requires a fixed source-graph definition. Confluent and Hortonworks require the preregistered employee-domain plurality test. Foundation ownership is not corporate attribution.

## 7. Decisions

### GREEN

None.

### YELLOW

Elastic, MongoDB, GitLab, HashiCorp, Couchbase, Confluent, Hortonworks, MariaDB.

### RED

Cloudera, Talend, MuleSoft, Pivotal.

## 8. Evidence-gated production order

1. Implement and review the general filing-backed debt-evidence ledger—without issuer-name rules—and preregister the finance-lease perimeter.
2. Verify CRSP/PERMNO identity and full-window coverage. HCP must remain UNKNOWN until its reused ticker is resolved.
3. Run cheap attribution/source-definition gates for Confluent, Hortonworks, and Couchbase.
4. Only then consider expensive recovery for candidates that remain YELLOW. Confluent is strongest on current accounting compatibility; MariaDB is clean but contributes only seven quarters.
5. Do not recover Cloudera, Talend, MuleSoft, or Pivotal absent evidence clearing their independent RED gates.

## 9. Explicit uncertainties

- No CRSP extract was inspected; acquisition completion dates are not exact last-trade claims.
- CompanyFacts is a changing aggregation. Exact payload hashes are recorded in the debt audit, while immutable filing accessions preserve primary evidence. Production must preserve its own raw snapshot.
- A production zero ledger must cite quarter-specific evidence; annual examples alone cannot authorize every quarter automatically.
- Finance-lease inclusion remains a methodology decision, not an extraction convenience.
- Expected grids use TechDD's fiscal-month-end approximation and ten-day fundamentals join.
- Current-extractor endpoint counts are not LTM panel rows or usable-price counts.

## 10. Sources

The debt audit maps CompanyFacts hashes and immutable filing links to each debt claim. Additional identity/transaction evidence:

- SEC submissions: [MariaDB](https://data.sec.gov/submissions/CIK0001929589.json), [Couchbase](https://data.sec.gov/submissions/CIK0001845022.json), [HashiCorp](https://data.sec.gov/submissions/CIK0001720671.json), [Confluent](https://data.sec.gov/submissions/CIK0001699838.json), [Cloudera](https://data.sec.gov/submissions/CIK0001535379.json), [Hortonworks](https://data.sec.gov/submissions/CIK0001610532.json), [Talend](https://data.sec.gov/submissions/CIK0001668105.json), [MuleSoft](https://data.sec.gov/submissions/CIK0001374684.json), and [Pivotal](https://data.sec.gov/submissions/CIK0001574135.json).
- Transaction filings: Couchbase [2025-09-24 Form 8-K](https://www.sec.gov/Archives/edgar/data/1845022/000114036125035929/ef20055964_8k.htm); HashiCorp [2025-02-27 Form 8-K](https://www.sec.gov/Archives/edgar/data/1720671/000119312525037910/d898526d8k.htm); Confluent [2026-03-17 Form 8-K](https://www.sec.gov/Archives/edgar/data/1699838/000110465926029071/tm268826d6_8k.htm); Cloudera [2021-10-08 Form 8-K](https://www.sec.gov/Archives/edgar/data/1535379/000119312521294924/d223205d8k.htm); Hortonworks [2019-01-03 Form 8-K](https://www.sec.gov/Archives/edgar/data/1610532/000162828019000078/hdp8-k.htm); MuleSoft [2018-05-02 Form 8-K](https://www.sec.gov/Archives/edgar/data/1374684/000119312518147738/d571994d8k.htm); Pivotal [2019-12-30 Form 8-K](https://www.sec.gov/Archives/edgar/data/1574135/000110465919076595/tm1917575d25_8k.htm); MariaDB [2024-08-16 Form 8-K](https://www.sec.gov/Archives/edgar/data/1929589/000114036124037687/ef20034338_8k.htm).
- Canonical upstream metadata: [Elastic](https://github.com/elastic/elasticsearch), [MongoDB](https://github.com/mongodb/mongo), [GitLab](https://gitlab.com/gitlab-org/gitlab), [Terraform](https://github.com/hashicorp/terraform), [Couchbase manifest](https://github.com/couchbase/manifest), [Apache Kafka](https://github.com/apache/kafka), [Apache Impala](https://github.com/apache/impala), [Apache Ambari](https://github.com/apache/ambari), [Mule](https://github.com/mulesoft/mule), [Cloud Foundry controller](https://github.com/cloudfoundry/cloud_controller_ng), and [MariaDB Server](https://github.com/MariaDB/server).
- Project contracts: `panel/data_manifest.toml`, `src/git_due_diligence/panel/edgar.py`, `src/git_due_diligence/panel/assemble.py`, and `src/git_due_diligence/panel/crsp.py`.
