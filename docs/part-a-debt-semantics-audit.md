# Part A debt-semantics audit

**Audit date:** 2026-09-03

## 1. Research question

This pre-regression audit asks what `debt = None` means in the Part A pipeline. It distinguishes absent borrowing, unsupported concepts, note-only disclosure, CompanyFacts omissions, and matching failures. It does not change extraction, assembly, the frozen pilot, or any result.

The audit covers Elastic, MongoDB, GitLab, HashiCorp, Couchbase, Confluent, Cloudera, Hortonworks, MariaDB, and—because their audit records were affected by fundamental compatibility—Talend, MuleSoft, and Pivotal.

## 2. Current TechDD behavior

`edgar.py` recognizes only `LongTermDebt`, `LongTermDebtNoncurrent`, and `ConvertibleDebtNoncurrent`. It priority-merges available instants and returns `None` when no supported instant is within 70 days. `assemble.py` then omits a firm-quarter if cash or debt is `None`. This is conservative and must remain unchanged until a separately reviewed implementation exists.

`None` is not an economic category. The same value currently represents:

- an issuer with an undrawn or terminated facility and affirmatively zero borrowings;
- an issuer with debt disclosed under an unsupported current/combined/lease concept;
- a note disclosure not surfaced as an appropriate CompanyFacts fact;
- a taxonomy or matching gap; or
- genuinely unresolved data.

Debt-security investments held as assets are explicitly excluded. Concepts such as `AvailableForSaleSecuritiesDebtSecurities` are not corporate borrowing.

## 3. Debt-status taxonomy

| Status | Meaning | Acceptable evidence |
|---|---|---|
| `REPORTED_NONZERO` | A supported borrowing fact is positive. | CompanyFacts fact tied to a filed form. |
| `REPORTED_ZERO` | A supported borrowing fact explicitly reports zero. | CompanyFacts fact tied to a filed form. |
| `ZERO_SUPPORTED_BY_FILINGS` | No supported fact, but the contemporaneous filed balance sheet and borrowing note affirmatively show no outstanding borrowing. | Immutable filing accession plus period and reviewer/audit record. |
| `UNSUPPORTED_XBRL_CONCEPT` | Borrowing exists under a legitimate concept outside the current set. | CompanyFacts/inline XBRL plus statement/note context. |
| `NOTE_ONLY` | Borrowing is disclosed in a note but no reliable CompanyFacts instant represents it. | Filed note and period. |
| `COMPANYFACTS_GAP` | Filed XBRL contains an appropriate fact that the aggregated endpoint omits. | Filing instance compared with CompanyFacts. |
| `MATCHING_GAP` | A valid fact exists but TechDD's date/tolerance selection misses it. | Fact dates and target quarter. |
| `UNRESOLVED` | Evidence does not distinguish absence from missing data. | Retain `None`. |

These categories are evidence states, not instructions to sum every tagged liability.

## 4. Firm-by-firm evidence

### GitLab

**Pattern:** 19 `ZERO_SUPPORTED_BY_FILINGS` quarters, 2021-10-31 through 2026-04-30.

GitLab's fiscal-2022 10-K states that its $15 million line was terminated April 30, 2021 and that no advance had ever been taken. The public-period balance sheets contain operating lease liabilities but no borrowing line; later 10-Ks no longer contain a debt-financing note. Investment “debt securities” are assets. The raw source is substantively complete; TechDD lacks a general zero-assertion channel.

### HashiCorp

**Pattern:** 13 `ZERO_SUPPORTED_BY_FILINGS` quarters, 2022-01-31 through 2025-01-31.

The fiscal-2022 10-K states that the revolving facility had no balance at January 31, 2022 and 2021. Later filed balance sheets show no borrowing liability and the fiscal-2024 filing discusses debt financing prospectively. This supports zero borrowing, not an unsupported positive debt concept. The last expected quarter has a separate revenue-availability problem because the transaction closed before another annual filing.

### Couchbase

**Pattern:** 1 `REPORTED_NONZERO` (2021-07-31), 1 `REPORTED_ZERO` (2022-01-31), and 15 `ZERO_SUPPORTED_BY_FILINGS` thereafter.

Couchbase's fiscal-2022 filing reports repayment of the $25 million facility balance on September 1, 2021 and zero at January 31, 2022. Fiscal-2023 reports no amounts outstanding; fiscal-2025 reports no debt outstanding under its replacement facility and no finance leases. This is a temporal transition from borrowing to affirmatively undrawn facilities, not a CompanyFacts-quality failure.

### Confluent

**Pattern:** 2 `ZERO_SUPPORTED_BY_FILINGS` quarters (2021-06-30 and 2021-09-30), followed by 17 `REPORTED_NONZERO` quarters.

Confluent issued $1.1 billion of convertible senior notes in December 2021. Its supported `ConvertibleDebtNoncurrent`/`LongTermDebt` sequence begins at 2021-12-31 and remains continuous. Pre-issuance filed statements support zero. This is a clean financing transition.

### Elastic

**Pattern:** 10 `ZERO_SUPPORTED_BY_FILINGS` quarters through 2021-01-31, 1 `REPORTED_ZERO` at 2021-04-30, and 20 `REPORTED_NONZERO` quarters thereafter.

Pre-notes balance sheets omit borrowing and discuss any future debt financing prospectively. The fiscal-2021 supported fact reports zero. Elastic issued $575 million of senior notes in July 2021; subsequent supported facts are continuous. The early `None` values are an absent-zero representation problem, not a positive-debt tag gap.

### MongoDB

**Pattern:** 25 `REPORTED_NONZERO`, 3 `REPORTED_ZERO`, 1 `ZERO_SUPPORTED_BY_FILINGS` (2017-10-31), 1 `MATCHING_GAP` (2018-04-30), and 5 `UNSUPPORTED_XBRL_CONCEPT` quarters after 2025-01-31.

MongoDB issued convertible notes in March 2018, creating a timing gap before the first supported quarter-end instant. The convertible notes were converted during fiscal 2025; supported facts report zero in 2024-10 and 2025-01, and the 2025 balance sheet shows no convertible-note liability. However, `FinanceLeaseLiabilityCurrent` and `FinanceLeaseLiabilityNoncurrent` continue. Whether finance leases belong in Part A “debt” is a general enterprise-value perimeter decision; treating post-conversion `None` as zero while ignoring those liabilities would silently decide it. These quarters therefore remain unresolved for production and are classified `UNSUPPORTED_XBRL_CONCEPT` for the present concept contract.

### Hortonworks

**Pattern:** 17 `ZERO_SUPPORTED_BY_FILINGS` quarters.

Annual filings disclose a revolving facility while repeatedly stating no outstanding borrowings (including December 31, 2017). Filed balance sheets do not show a borrowing liability. The debt-like CompanyFacts concepts are investment assets. Source quality is adequate; TechDD cannot currently encode the affirmative zero.

### Cloudera

**Pattern:** 14 `ZERO_SUPPORTED_BY_FILINGS`, 1 `REPORTED_ZERO`, and 3 `REPORTED_NONZERO` quarters.

Pre-financing balance sheets contain no borrowing liability. The supported series reports zero at 2020-01-31. Cloudera then entered a $500 million term loan in December 2020; the 2021-01, 2021-04, and 2021-07 supported noncurrent values are approximately $487–485 million. The apparent 2020 intra-year `None` values precede the loan and are filing-supported zeros, not missing positive balances.

### MariaDB

**Pattern:** 7 `REPORTED_NONZERO` public quarters, 2022-12-31 through 2024-06-30.

CIK 0001929589 reports borrowing continuously under supported `LongTermDebt`/`LongTermDebtNoncurrent`; `DebtCurrent` and `DebtLongtermAndShorttermCombinedAmount` also appear and overlap. TechDD's current debt value is populated for every public grid date. MariaDB demonstrates why the prior audit's “not public” conclusion was a factual error, not a data-quality finding.

### Other debt-affected audit records

- **Talend:** `LongTermDebtNoncurrent`, `LongTermDebtCurrent`, `DebtCurrent`, and `DebtLongtermAndShorttermCombinedAmount` appear. The current extractor gets eight rows after Talend switched from 20-F to 10-K reporting; the production duration helper excludes 20-F. The eight is an extractor result, not raw-source completeness.
- **MuleSoft:** its filed balance sheet does not show interest-bearing borrowing during the five-quarter listed window. Revenue concept compatibility, not debt, is the binding extractor problem.
- **Pivotal:** it repaid a $35 million revolving-facility balance during fiscal 2019 and reported no amount outstanding at February 1, 2019. Revenue concept compatibility, short listing history, and repository attribution—not debt—drive its RED verdict.

## 5. Candidate XBRL borrowing concepts

This table is a research inventory only. No concept is added by this PR.

| Concept | Economic meaning | Observed firms/periods | Additive or overlapping? | Double-count risk | Recommended status |
|---|---|---|---|---|---|
| `LongTermDebtCurrent` | Current portion of long-term borrowing | Cloudera 2020–2021; Talend 2018–2021; MariaDB 2022–2023 | Usually additive to a *noncurrent-only* fact, but overlaps a total | High | Evaluate with an explicit total-vs-components hierarchy. |
| `DebtCurrent` | Current interest-bearing debt | Talend 2017–2019; MariaDB 2023–2024 | May overlap `LongTermDebtCurrent` and combined debt | High | Candidate only after reconciliation tests. |
| `DebtLongtermAndShorttermCombinedAmount` | Combined current and noncurrent debt | Talend 2017–2019; MariaDB 2023–2024 | Total; do not add components | Very high | Prefer as a total when filing context verifies scope. |
| `DebtInstrumentCarryingAmount` | Carrying amount of a particular debt instrument | MongoDB 2019; Couchbase 2021–2022; Confluent 2021–2025; Cloudera 2021 | Often duplicates a notes total | Very high | Note-context fallback only, never blindly summed. |
| `FinanceLeaseLiability` | Total finance-lease obligation | MongoDB 2019–2026 | Total may overlap current/noncurrent components | High | Requires a preregistered EV debt-perimeter decision. |
| `FinanceLeaseLiabilityCurrent` | Current finance-lease liability | MongoDB 2019–2026 | Additive only with noncurrent component if no total | High | Same policy decision; paired hierarchy required. |
| `FinanceLeaseLiabilityNoncurrent` | Noncurrent finance-lease liability | MongoDB 2019–2026 | Additive only with current component if no total | High | Same policy decision; paired hierarchy required. |
| `ConvertibleDebtCurrent` / issuer convertible-note concepts | Current convertible borrowing | Not a recurring cross-firm standard fact in this snapshot | Can overlap total/noncurrent facts | High | Search/reconcile in a future extractor audit; no generic sum. |
| `ShortTermBorrowings` / `ShortTermDebtCurrent` | Standalone short-term borrowing | Not consistently observed across this candidate snapshot | May overlap combined/current debt | High | Keep on candidate list; require cross-issuer fixtures. |

Operating-lease liabilities and investment debt securities are outside this candidate table. Including operating leases would change the enterprise-value definition; investment securities are assets.

## 6. Is a general zero-debt rule defensible?

**Yes as an auditable evidence rule; no as an automatic inference from CompanyFacts absence.**

A prospective issuer-neutral rule can accept zero only when an immutable contemporaneous filing establishes all of the following:

1. the balance sheet has no interest-bearing borrowing liability;
2. every disclosed credit/loan/note facility is explicitly undrawn, repaid, terminated, or has a reported zero balance at the relevant instant;
3. no borrowing note, current-debt line, convertible instrument, or note-only balance contradicts zero;
4. the debt perimeter (especially finance leases) is fixed before applying the rule; and
5. the assertion records CIK, quarter, accession, evidence location, reviewer/build timestamp, and a hash in a machine-readable ledger.

The rule is observable, issuer-neutral, prospective, and auditable. It is not reliably machine-checkable from the mere absence of a US-GAAP concept: omission practices vary, prose can carry the decisive evidence, and different totals/components overlap. Automated extraction may propose assertions, but production zero assertions require deterministic evidence validation and should fail closed.

## 7. Recommended general policy

A later implementation PR should preserve the current supported-fact path and add a separate immutable **debt-evidence ledger**:

- `REPORTED_NONZERO` and `REPORTED_ZERO` continue to come directly from reconciled CompanyFacts facts.
- `ZERO_SUPPORTED_BY_FILINGS` may become numeric zero only through a filing-backed ledger record satisfying the five gates above.
- Unsupported, note-only, CompanyFacts-gap, matching-gap, and unresolved cases remain `None` until reconciled.
- The extractor should use a documented priority hierarchy: verified total debt first; otherwise compatible current + noncurrent components; never priority-merge or add overlapping totals without reconciliation.
- Finance leases must remain unresolved until the EV debt perimeter is explicitly preregistered.

No firm-name exception is permitted. A ledger record is data provenance, not an issuer-specific extraction rule.

## 8. Unresolved cases

- MongoDB's post-conversion finance leases require the debt-perimeter decision.
- MongoDB 2018-04 requires exact filing-instant reconciliation before choosing between `MATCHING_GAP` and a note-only value.
- HashiCorp's final revenue quarter remains unavailable under the present raw filing window.
- Exact acquisition-era last trading dates and all CRSP coverage remain unverified.
- The cheap audit did not prove that every quarterly filing between sampled annual filings repeats the same zero language. A production ledger must cite each quarter or a filing statement whose period coverage is explicit.

## 9. Implications for the candidate universe

Missing supported debt does not by itself show poor source data. GitLab, HashiCorp, Couchbase, and Hortonworks move from RED to YELLOW because their filings support zero-debt periods but TechDD cannot yet consume that evidence. MariaDB moves from RED to YELLOW after correction of its public identity and passes the current extractor for all seven public quarters. Cloudera remains RED because repository attribution—not debt—fails. Talend, MuleSoft, and Pivotal remain RED for independent gates.

No firm becomes GREEN: CRSP is still unverified, and every candidate retains at least one qualification issue.

## 10. Primary sources and snapshot provenance

CompanyFacts payloads were retrieved 2026-09-03. The exact deterministic bundle is durably stored as Git tag `part-a-debt-audit-companyfacts-2026-09-03`, which points to Git blob `326c38fe244a83589c2da7cf7bc10634224684a4`. Restore it with `git fetch --tags` followed by `git show part-a-debt-audit-companyfacts-2026-09-03^{blob} > companyfacts.tar.gz`; its SHA-256 is `6c72b93f3db358d1d21b080d41cda89b33ee7896664bcf01bc652f44b1905a68`. A clean restore was byte-identical. This evidence bundle is not a frozen-pilot or production panel input. Per-file SHA-256 values identify each payload:

| CIK | Entity | CompanyFacts SHA-256 |
|---|---|---|
| 0001374684 | MuleSoft | `e3353c606c83bc19cd4a4c830b6f39fd3a0e9f61ce19507b63e8651ea5fe63d5` |
| 0001441816 | MongoDB | `8947052d6912d9ac6b35470f5e331ef6fe1f4b4cf782fab20822c9cb66738997` |
| 0001535379 | Cloudera | `11b98616f323587131d894ed8011a7867343064d74d4cd5d047701d4a1e414f2` |
| 0001574135 | Pivotal | `0b5b85d4e7e5ff9a769872fb9f9e6aba8fcf33cbf38553ac4ab2191f3e5a2fd4` |
| 0001610532 | Hortonworks | `d73d36051fc33592037172f2d5b8664e52a8b01155f268e724db57b88fd65fc5` |
| 0001653482 | GitLab | `5f900199621c5922f358c542d0fb942df930d4fe391724686f2625149fc1ee54` |
| 0001668105 | Talend | `b71f448d6a6b639e9670aa5629ba4e3fcf514af75247bc49fc9b6a5196eb0a6f` |
| 0001699838 | Confluent | `ec400a28470ff4da0a4cb4f2715b2531ddf7c0225df0a11cfef70f3c7ffabcb4` |
| 0001707753 | Elastic | `bf67dc8bc9dd23758c9e2dc067477dca9ae9f8041beaa79a7143ad61919b1e29` |
| 0001720671 | HashiCorp | `3a0b2bb93c828150f5da0e9f115697901214cd02539ab13c6deb24d7b8179a54` |
| 0001845022 | Couchbase | `989a30651e5ea026733d30504a3de799cc68d9d0dbe0b87f5c35b19a67c629fe` |
| 0001929589 | MariaDB | `74bd65ab23721b5646c7c665ac85f5734872f8a30ce792ee2c1bc76c67e7d079` |

Live endpoints: SEC CompanyFacts for [GitLab](https://data.sec.gov/api/xbrl/companyfacts/CIK0001653482.json), [HashiCorp](https://data.sec.gov/api/xbrl/companyfacts/CIK0001720671.json), [Couchbase](https://data.sec.gov/api/xbrl/companyfacts/CIK0001845022.json), [Confluent](https://data.sec.gov/api/xbrl/companyfacts/CIK0001699838.json), [Elastic](https://data.sec.gov/api/xbrl/companyfacts/CIK0001707753.json), [MongoDB](https://data.sec.gov/api/xbrl/companyfacts/CIK0001441816.json), [Hortonworks](https://data.sec.gov/api/xbrl/companyfacts/CIK0001610532.json), [Cloudera](https://data.sec.gov/api/xbrl/companyfacts/CIK0001535379.json), [Talend](https://data.sec.gov/api/xbrl/companyfacts/CIK0001668105.json), [MuleSoft](https://data.sec.gov/api/xbrl/companyfacts/CIK0001374684.json), [Pivotal](https://data.sec.gov/api/xbrl/companyfacts/CIK0001574135.json), and [MariaDB](https://data.sec.gov/api/xbrl/companyfacts/CIK0001929589.json).

Key immutable filing evidence:

- GitLab [fiscal-2022 10-K, Note 7](https://www.sec.gov/Archives/edgar/data/1653482/000162828022008836/gtlb-20220131.htm).
- HashiCorp [fiscal-2022 10-K](https://www.sec.gov/Archives/edgar/data/1720671/000095017022004668/hcp-20220131.htm) and [fiscal-2024 10-K](https://www.sec.gov/Archives/edgar/data/1720671/000162828024012350/hcp-20240131.htm).
- Couchbase [fiscal-2022 10-K](https://www.sec.gov/Archives/edgar/data/1845022/000184502222000031/base-20220131.htm), [fiscal-2023 10-K](https://www.sec.gov/Archives/edgar/data/1845022/000184502223000038/base-20230131.htm), and [fiscal-2025 10-K](https://www.sec.gov/Archives/edgar/data/1845022/000184502225000026/base-20250131.htm).
- Confluent [fiscal-2021 10-K, convertible-notes note](https://www.sec.gov/Archives/edgar/data/1699838/000095017022002008/cflt-20211231.htm).
- Elastic [fiscal-2019](https://www.sec.gov/Archives/edgar/data/1707753/000156459019024066/estc-10k_20190430.htm), [fiscal-2020](https://www.sec.gov/Archives/edgar/data/1707753/000162828020009982/estc-20200430.htm), and [fiscal-2021](https://www.sec.gov/Archives/edgar/data/1707753/000170775321000026/estc-20210430.htm) 10-Ks.
- MongoDB [fiscal-2025](https://www.sec.gov/Archives/edgar/data/1441816/000144181625000057/mdb-20250131.htm) and [fiscal-2026](https://www.sec.gov/Archives/edgar/data/1441816/000162828026016799/mdb-20260131.htm) 10-Ks.
- Hortonworks [fiscal-2017 10-K, Note 8](https://www.sec.gov/Archives/edgar/data/1610532/000119312518084131/d506884d10k.htm).
- Cloudera [fiscal-2020](https://www.sec.gov/Archives/edgar/data/1535379/000162828020004231/cldr-20200131.htm) and [fiscal-2021](https://www.sec.gov/Archives/edgar/data/1535379/000162828021005632/cldr-20210131.htm) 10-Ks.
- MariaDB [fiscal-2023 10-K](https://www.sec.gov/Archives/edgar/data/1929589/000192958923000010/mrdb-20230930.htm) and [K1 transaction 8-K](https://www.sec.gov/Archives/edgar/data/1929589/000114036124037687/ef20034338_8k.htm).
- Pivotal [fiscal-2019 10-K, revolving-facility note](https://www.sec.gov/Archives/edgar/data/1574135/000157413519000009/pvtl-20190201x10k.htm).

The durable bundle makes the extractor counts reproducible, its hashes make drift detectable, and the immutable accession documents preserve the underlying filed evidence. The eventual production evidence ledger must still register its own reviewed raw inputs rather than silently treating this audit snapshot as panel data.
