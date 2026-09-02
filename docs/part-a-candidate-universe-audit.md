# Part A candidate-universe and data-completeness audit

**Audit date:** 2026-09-02
**Status:** pre-regression qualification audit; no candidates admitted
**Scope:** 12 named controls/candidates; no repository metrics, regressions, panel build, or full-history clones were run

## 1. Executive summary

This audit applied the requested gates before looking at any regression result. It found **no GREEN candidates**, **three YELLOW candidates**, and **nine RED candidates**. The result is intentionally conservative: absence of a reported debt fact is not treated as zero, actual CRSP data was not available, and foundation participation was not treated as corporate attribution.

- **YELLOW:** Elastic, MongoDB, Confluent.
- **RED:** GitLab, HashiCorp, Couchbase, Cloudera, Hortonworks, Talend, MuleSoft, Pivotal, MariaDB.
- **No firm is GREEN**, principally because price coverage is only EXPECTED rather than verified and because every otherwise promising firm has either current-concept fundamental gaps or unresolved repository attribution.

The strongest Phase 2 qualification target is **Confluent**, but only after the pre-registered employee-commit plurality test for Apache Kafka and an actual CRSP identity/coverage check. Elastic and MongoDB remain usable controls, but neither passes the newly stated “essentially complete fundamentals/no major internal gaps” gate. GitLab is the most surprising control failure: current CompanyFacts plus the conservative `None`-versus-zero policy produce no debt-complete public quarter.

The counts below are not panel row counts. “Fundamental-usable quarters” means that the current extractor found revenue, cash, supported debt, and shares at a fiscal-quarter endpoint. It precedes the four-quarter LTM requirement, price matching, positive-EV test, and repository metrics; estimated final usable overlap is therefore left blank whenever CRSP was not inspected.

## 2. Pre-registered qualification methodology

The screen was fixed before any estimation:

1. **Corporate identity:** verify SEC reporting identity, CIK, fiscal year end, ticker, and public window from SEC submissions/filings and transaction materials.
2. **Repository attribution:** HIGH means a firm-controlled core upstream; MEDIUM means an economically relevant but distributed/foundation or multi-repository product; LOW means the repository is an incomplete or ambiguous proxy. Repository-host metadata was used only to establish ownership and cheap history overlap, not authorship dominance.
3. **Public grid:** generate fiscal quarter ends within the listing window using the same month-based convention as `fiscal_quarter_ends`; acquisition dates end the window. The common pilot cutoff remains 2026-06-30 and was not modified.
4. **Fundamentals:** retrieve SEC CompanyFacts and apply the current production extractor unchanged. Required EV/panel inputs are quarterly revenue, cash, supported debt, and shares; operating income is also audited but its absence yields a missing margin rather than immediate row deletion. Supported debt tags are only `LongTermDebt`, `LongTermDebtNoncurrent`, and `ConvertibleDebtNoncurrent`. No absent fact was imputed as zero and no candidate-specific fallback was introduced.
5. **Prices:** without the actual CRSP extract, an unambiguous listed ticker is **EXPECTED**, never VERIFIED. A reused ticker, missing permanent identifier, or no public security is UNKNOWN. No Yahoo/Stooq substitution was made.
6. **Verdict:** GREEN requires HIGH attribution, at least 12 likely usable quarters, essentially continuous fundamentals, clear security identity, and no major unexplained internal gap. YELLOW retains a plausible candidate with a specific resolvable qualification step. RED means expensive metric recovery should not begin under the present evidence.

All SEC completeness counts are reproducible from the CompanyFacts endpoints listed in Sources, accessed 2026-09-02. The raw audit payloads were temporary research inputs and were not admitted to the frozen pilot cache or manifest.

## 3. Master candidate table

| Firm | Ticker / CIK | Public window; FYE | Canonical repository | Attribution | Expected quarters | Current fundamental coverage | Price | Estimated overlap | Key caveat | Verdict |
|---|---|---|---|---:|---:|---|---|---|---|---|
| Elastic | ESTC / 0001707753 | 2018-10-05–cutoff; Apr | `elastic/elasticsearch` | HIGH | 31 | 21 input-complete | EXPECTED | UNKNOWN | Debt absent for first 10 grid dates | YELLOW |
| MongoDB | MDB / 0001441816 | 2017-10-19–cutoff; Jan | `mongodb/mongo` | HIGH | 35 | 19 input-complete | EXPECTED | UNKNOWN | Shares absent through 2020-04; debt absent after 2025-01 | YELLOW |
| GitLab | GTLB / 0001653482 | 2021-10-14–cutoff; Jan | `gitlab-org/gitlab` | HIGH | 19 | 0 input-complete | EXPECTED | 0 under current concepts | Supported debt absent throughout | RED |
| HashiCorp | HCP / 0001720671 | 2021-12-09–2025-02-27; Jan | `hashicorp/terraform` | HIGH | 13 | 0 input-complete | EXPECTED | 0 under current concepts | Supported debt absent throughout | RED |
| Couchbase | BASE / 0001845022 | 2021-07-22–2025-09-17; Jan | `couchbase/manifest` (coordination repo) | MEDIUM | 17 | 2 input-complete | EXPECTED | UNKNOWN | Core product is distributed; debt disappears after early filings | RED |
| Confluent | CFLT / 0001699838 | 2021-06-24–2026-03-17; Dec | `apache/kafka` | MEDIUM | 19 | 17 input-complete | EXPECTED | UNKNOWN | Foundation attribution not yet measured | YELLOW |
| Cloudera | CLDR / 0001535379 | 2017-04-28–2021-10-08; Jan | `apache/impala` | LOW | 18 | 4 input-complete | EXPECTED | UNKNOWN | One foundation repo does not proxy the full platform | RED |
| Hortonworks | HDP / 0001610532 | 2014-12-12–2019-01-03; Dec | `apache/ambari` | MEDIUM | 17 | 0 input-complete | EXPECTED | 0 under current concepts | Attribution unverified; supported debt absent | RED |
| Talend | TLND / 0001668105 | 2016-07-29–2021-07-30; Dec | not established | LOW | 20 | 8 input-complete | EXPECTED | UNKNOWN | No authoritative core upstream; major revenue gaps | RED |
| MuleSoft | MULE / 0001374684 | 2017-03-17–2018-05-02; Dec | `mulesoft/mule` | HIGH | 5 | 0 input-complete | EXPECTED | 0 under current concepts | Too short and no supported revenue series | RED |
| Pivotal | PVTL / 0001574135 | 2018-04-20–2019-12-30; Feb | `cloudfoundry/cloud_controller_ng` | LOW | 7 | 0 input-complete | EXPECTED | 0 under current concepts | Short window and foundation-distributed product | RED |
| MariaDB | none / none | no public window | `MariaDB/server` | HIGH | 0 | not applicable | UNKNOWN | 0 | Private-company acquisition is not a public listing | RED |

## 4. Candidate evidence

### Elastic (control) — YELLOW

SEC and the frozen manifest identify Elastic N.V., CIK 0001707753, ESTC, NYSE, April 30 year end, and an October 5, 2018 listing start. The firm-owned Elasticsearch upstream predates listing by years, is economically central, and its frozen metrics have already been recovered, supporting HIGH attribution and repository overlap. The fresh current-extractor audit found 31 public grid dates, but supported debt is missing for the first ten (2018-10 through 2021-01); only 21 dates have all valuation inputs. This is material internal attrition, so the control is not GREEN. CRSP remains EXPECTED, not verified.

### MongoDB (control) — YELLOW

MongoDB Inc., CIK 0001441816, MDB, Nasdaq, has a January 31 year end and a listing start of October 19, 2017. `mongodb/mongo` is firm-owned, predates listing, and has frozen metric provenance. Of 35 public grid dates, only 19 are input-complete: shares are missing through 2020-04 under the extractor, early debt is intermittent, and supported convertible debt ends at 2025-01. The later absence may reflect extinguished debt rather than unknown economics, but the current policy correctly refuses to infer zero. CRSP remains EXPECTED.

### GitLab (control) — RED

GitLab Inc., CIK 0001653482, GTLB, Nasdaq, uses a January 31 year end and listed October 14, 2021. The canonical upstream is the GitLab-hosted `gitlab-org/gitlab`, not the GitHub mirror; attribution and overlap are HIGH. Nevertheless, none of 19 grid dates has a supported debt fact. CompanyFacts contains investment-security concepts with “Debt” in their names, but these are assets, not borrowing, and are not a defensible replacement. Under the current conservative assembly policy the estimated overlap is zero before price checks. Expensive metric recovery has already occurred historically, but this audit would not authorize a new recovery until the balance-sheet semantics are resolved prospectively.

### HashiCorp — RED

HashiCorp Inc., CIK 0001720671, HCP, listed December 9, 2021 and was acquired by IBM on February 27, 2025. Terraform is a firm-controlled flagship upstream with history preceding the listing, giving HIGH attribution. The 13-quarter grid is long enough in principle, but none is input-complete because no currently supported borrowing concept is present; “debt securities” in CompanyFacts describe investments, not liabilities. The last grid date also lacks extracted revenue. HCP ticker reuse makes a permanent security identifier/CRSP entity check mandatory. Do not recover metrics until both issues are cleared.

### Couchbase — RED

Couchbase Inc., CIK 0001845022, BASE, listed July 22, 2021 and was acquired in September 2025. Firm ownership is clear, but the server product is assembled across multiple repositories; `couchbase/manifest` coordinates those sources rather than representing a single complete codebase, so the one-repository proxy is MEDIUM. Only 2 of 17 grid dates are complete under current concepts: `LongTermDebtNoncurrent` appears around pre-IPO/early filings and then disappears. This could be genuine repayment, but zero cannot be assumed. Price identity is EXPECTED; fundamentals and repository definition block compute.

### Confluent — YELLOW

Confluent Inc., CIK 0001699838, CFLT, listed June 24, 2021 and was acquired by IBM in March 2026. Apache Kafka clearly predates and materially underlies Confluent's commercial product, but it is Apache-owned and community governed, so attribution is MEDIUM until the registered employee-domain plurality test passes. Fundamentals are strongest in the candidate set: 17 of 19 grid dates are complete, with supported convertible/long-term debt beginning after the first two dates. CRSP identity is EXPECTED but not inspected. This is the first Phase 2 qualification target, not an automatic admission.

### Cloudera — RED

Cloudera Inc., CIK 0001535379, CLDR, listed April 28, 2017 and became private October 8, 2021. Apache Impala is relevant but is Apache-owned and captures only part of Cloudera's Hadoop/data-platform economics; attribution is LOW for a single-repository health regressor. Only 4 of 18 grid dates are complete because supported debt begins late. The prior handoff also records a truncated historical price export; the present audit did not inspect CRSP. These are multiple independent blockers.

### Hortonworks — RED

Hortonworks Inc., CIK 0001610532, HDP, listed December 12, 2014 and combined with Cloudera on January 3, 2019. Apache Ambari is relevant but foundation-owned, so attribution is MEDIUM and employee plurality is unverified. The current extractor finds no supported debt on any of 17 public grid dates; the last grid date also lacks matched revenue. CompanyFacts does contain debt-*security* investment assets, which are not borrowings. No metric recovery is justified.

### Talend — RED

Talend S.A., CIK 0001668105, TLND, listed July 29, 2016 and was acquired in July 2021. The 20-quarter window is adequate, but no authoritative, durable canonical product repository was established in the cheap audit; the expected historical Talend Studio repository is not available at the presumed canonical GitHub path. Current concepts yield only 8 complete dates and large internal revenue gaps, including the early listed period. A Phase 2 source-history identification would be required before any compute, but the fundamental gaps already make this RED.

### MuleSoft — RED

MuleSoft Inc., CIK 0001374684, MULE, listed March 17, 2017 and was acquired by Salesforce on May 2, 2018. `mulesoft/mule` is firm-controlled and predates listing, so attribution is HIGH. The listed grid contains only five fiscal quarters and current supported revenue concepts yield no matched quarters. A short legitimate listing is not “dirty,” but it falls far below the 12-quarter production gate and adds no current-extractor observations.

### Pivotal — RED

Pivotal Software Inc., CIK 0001574135, PVTL, listed April 20, 2018 and was acquired by VMware on December 30, 2019. Cloud Foundry is economically relevant but foundation-distributed and Pivotal's product portfolio was broader than `cloud_controller_ng`, so attribution is LOW. The window has seven grid dates, and the current revenue concepts match none (the company reports concepts outside the current contract). Both short overlap and methodology-changing normalization would be required.

### MariaDB — RED

MariaDB plc controls the canonical MariaDB Server repository, so product attribution is HIGH. But this audit found no SEC CIK, listed ticker, or identifiable public-market window. K1's 2024 transaction materials describe an acquisition of the company rather than a public-company delisting. MariaDB therefore does not satisfy the public/historically-public gate and should not consume Part A recovery compute.

## 5. Data-completeness findings

The audit used the production tag priorities and matching tolerances, not a broader accounting search. This matters:

- **Best current-concept candidate:** Confluent, 17/19 endpoint-complete dates.
- **Partial controls:** Elastic 21/31 and MongoDB 19/35.
- **Current-policy zero overlap:** GitLab, HashiCorp, Hortonworks, MuleSoft, and Pivotal.
- **Sparse:** Couchbase 2/17, Cloudera 4/18, Talend 8/20.
- Operating-income absence was recorded but was not counted as a hard endpoint failure because assembly permits a missing margin. The table's completeness test requires revenue, cash, debt, and shares, matching EV construction.
- These endpoint counts still overstate final panel rows because four sequential revenue quarters, a price within 14 days, and positive EV are required.

No alternative tag was adopted. Apparent zero-debt companies are a cross-cutting design issue: liability absence cannot become numeric zero without a separately registered, filing-supported rule. Investment concepts such as `AvailableForSaleSecuritiesDebtSecurities` must not be mistaken for corporate borrowing.

## 6. Repository-attribution findings

- **HIGH:** Elastic, MongoDB, GitLab, HashiCorp, MuleSoft, MariaDB.
- **MEDIUM:** Couchbase (distributed firm-owned source set), Confluent (Apache Kafka), Hortonworks (Apache Ambari).
- **LOW:** Cloudera (one Apache project does not capture the platform), Talend (canonical upstream not established), Pivotal (foundation-distributed and portfolio mismatch).

Git hosting ownership is evidence, not sufficient proof of economic attribution. For Confluent and Hortonworks, Phase 2 must measure employee-authored plurality during the public window without changing the frozen bot filter. Couchbase needs an ex-ante rule for aggregating its product's coordinated repositories; selecting a convenient single repo after inspecting metrics would create researcher discretion.

## 7. Decisions and compute gate

### GREEN

None.

### YELLOW

- **Confluent:** run a cheap employee-domain plurality audit and obtain a verified CRSP mapping before repository metric recovery.
- **Elastic and MongoDB:** retain as controls, but report their fundamental attrition and do not describe their panel inputs as complete.

### RED

GitLab, HashiCorp, Couchbase, Cloudera, Hortonworks, Talend, MuleSoft, Pivotal, and MariaDB. They should not receive new expensive recovery compute on current evidence.

## 8. Production expansion order

This is an evidence-gated sequence, not an instruction to admit firms:

1. **Confluent qualification only:** employee-domain plurality on Apache Kafka; immutable CompanyFacts; CRSP PERMNO/entity and full-window coverage. Recover metrics only if all pass.
2. **Resolve the cross-cutting no-debt semantics prospectively:** determine whether SEC filings can support a general, pre-registered numeric-zero rule without inventing issuer-specific tags. Re-run the cheap fundamental audit afterward. This affects GitLab, HashiCorp, Couchbase, and Hortonworks.
3. **Couchbase repository-set definition:** establish whether one reproducible source graph can represent the server product before any history scan.
4. Do not queue Cloudera, Hortonworks, Talend, MuleSoft, Pivotal, or MariaDB absent materially new evidence that clears their independent RED gates.

## 9. Explicit uncertainties

- No CRSP file or PERMNO mapping was available; every listed security is EXPECTED rather than VERIFIED. HCP is especially sensitive to ticker reuse.
- Repository creation metadata and remote existence establish cheap plausibility, not earliest commit date, untruncated history, or employee authorship. Those require Phase 2 lightweight ancestry/attribution checks or, only after admission, frozen recovery.
- Acquisition completion dates are used as public-window endpoints; the last actually traded date may differ by a trading day and must be resolved from CRSP.
- CompanyFacts changes as amendments/new filings arrive. This audit records an access date but does not freeze these temporary payloads as production artifacts.
- Fiscal grids use the pipeline's month-end convention; issuer fiscal dates can differ by several days and depend on the existing ten-day join tolerance.
- `fundamental_usable_quarters` does not imply four-quarter LTM usability or positive EV.
- MariaDB's legal/entity history is complex, but no evidence found in this audit establishes a U.S. public reporting window.

## 10. Sources

Sources are mapped to the claims they support and were accessed 2026-09-02 unless noted.

### SEC identity and accounting evidence

- [SEC Company Tickers](https://www.sec.gov/files/company_tickers.json) — current SEC ticker/title/CIK identity for still-listed controls.
- SEC submissions JSON for [Elastic](https://data.sec.gov/submissions/CIK0001707753.json), [MongoDB](https://data.sec.gov/submissions/CIK0001441816.json), [GitLab](https://data.sec.gov/submissions/CIK0001653482.json), [HashiCorp](https://data.sec.gov/submissions/CIK0001720671.json), [Couchbase](https://data.sec.gov/submissions/CIK0001845022.json), [Confluent](https://data.sec.gov/submissions/CIK0001699838.json), [Cloudera](https://data.sec.gov/submissions/CIK0001535379.json), [Hortonworks](https://data.sec.gov/submissions/CIK0001610532.json), [Talend](https://data.sec.gov/submissions/CIK0001668105.json), [MuleSoft](https://data.sec.gov/submissions/CIK0001374684.json), and [Pivotal](https://data.sec.gov/submissions/CIK0001574135.json) — legal identity, filing history, exchange/ticker where current, and fiscal year end.
- SEC CompanyFacts for [Elastic](https://data.sec.gov/api/xbrl/companyfacts/CIK0001707753.json), [MongoDB](https://data.sec.gov/api/xbrl/companyfacts/CIK0001441816.json), [GitLab](https://data.sec.gov/api/xbrl/companyfacts/CIK0001653482.json), [HashiCorp](https://data.sec.gov/api/xbrl/companyfacts/CIK0001720671.json), [Couchbase](https://data.sec.gov/api/xbrl/companyfacts/CIK0001845022.json), [Confluent](https://data.sec.gov/api/xbrl/companyfacts/CIK0001699838.json), [Cloudera](https://data.sec.gov/api/xbrl/companyfacts/CIK0001535379.json), [Hortonworks](https://data.sec.gov/api/xbrl/companyfacts/CIK0001610532.json), [Talend](https://data.sec.gov/api/xbrl/companyfacts/CIK0001668105.json), [MuleSoft](https://data.sec.gov/api/xbrl/companyfacts/CIK0001374684.json), and [Pivotal](https://data.sec.gov/api/xbrl/companyfacts/CIK0001574135.json) — concept-level continuity and the reported completeness counts.

### Canonical repositories and project governance

- [Elastic Elasticsearch](https://github.com/elastic/elasticsearch), [MongoDB Server](https://github.com/mongodb/mongo), [GitLab upstream](https://gitlab.com/gitlab-org/gitlab), [HashiCorp Terraform](https://github.com/hashicorp/terraform), [Couchbase manifest](https://github.com/couchbase/manifest), [Mule runtime](https://github.com/mulesoft/mule), and [MariaDB Server](https://github.com/MariaDB/server) — canonical organization ownership and product/repository identity.
- [Apache Kafka](https://github.com/apache/kafka), [Apache Impala](https://github.com/apache/impala), [Apache Ambari](https://github.com/apache/ambari), and [Cloud Foundry Cloud Controller](https://github.com/cloudfoundry/cloud_controller_ng) — foundation/community ownership underlying the MEDIUM/LOW attribution decisions.

### Public windows and acquisitions

- Terminal transaction filings: HashiCorp [February 27, 2025 Form 8-K](https://www.sec.gov/Archives/edgar/data/1720671/000119312525037910/d898526d8k.htm), Couchbase [September 17, 2025 Form 8-K](https://www.sec.gov/Archives/edgar/data/1845022/000114036125035242/ef20055583_8k.htm), Confluent [March 17, 2026 Form 8-K](https://www.sec.gov/Archives/edgar/data/1699838/000110465926029071/tm268826d6_8k.htm), Cloudera [October 8, 2021 Form 8-K](https://www.sec.gov/Archives/edgar/data/1535379/000119312521294924/d223205d8k.htm), Hortonworks [January 3, 2019 Form 8-K](https://www.sec.gov/Archives/edgar/data/1610532/000162828019000078/hdp8-k.htm), Talend [July 30, 2021 Form 8-K](https://www.sec.gov/Archives/edgar/data/1668105/000110465921097973/tm218950d30_8k.htm), MuleSoft [May 2, 2018 Form 8-K](https://www.sec.gov/Archives/edgar/data/1374684/000119312518147738/d571994d8k.htm), and Pivotal [December 30, 2019 Form 8-K](https://www.sec.gov/Archives/edgar/data/1574135/000110465919076595/tm1917575d25_8k.htm) — completion/delisting context and public-window endpoints.
- [K1 announcement of its MariaDB acquisition](https://www.k1.com/news/k1-investment-management-completes-acquisition-of-mariadb) — private acquisition context, not evidence of a public listing.

### Project-local methodological evidence

- `panel/data_manifest.toml` — frozen pilot identities, cutoffs, repository locks, and unresolved permanent security identifiers.
- `src/git_due_diligence/panel/edgar.py` — exact supported concepts and fact matching used for this audit.
- `src/git_due_diligence/panel/assemble.py` — hard row requirements, four-quarter LTM construction, and conservative cash/debt semantics.
- `src/git_due_diligence/panel/crsp.py` and `prices.py` — price identity/quote parsing and quarter-end staleness contract.
- `docs/part-a-data-recovery-plan.md` and existing per-firm recovery reports — frozen provenance contract and prior runtime evidence.
