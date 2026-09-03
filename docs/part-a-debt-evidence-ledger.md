# Part A filing-backed debt evidence ledger

## Purpose and boundary

`panel/debt_evidence.toml` is a versioned research input for firm-quarters where the supported CompanyFacts debt concepts do not themselves provide a number. It exists because missing CompanyFacts data is not economic evidence of zero. A numeric zero may be supplied only by an exact, reviewed `ZERO_SUPPORTED_BY_FILINGS` record pointing to a contemporaneous SEC filing.

The ledger is issuer-neutral data. It is not an exception list in extraction code, and no record is inferred from the absence of an XBRL concept.

## Schema version 1

The file has a top-level `schema_version = 1` and repeated `[[records]]`. Every record requires:

- `firm` and zero-padded `cik`;
- an exact TOML date `quarter_end`;
- `classification`;
- SEC `accession`, TOML `filing_date`, and `filing_form`;
- specific `evidence_location` and concise `evidence_note` fields;
- a `source_url` whose immutable SEC archive identity contains the accession;
- `immutable_evidence_id`, currently the normalized `sec-accession:<accession>` identity;
- `reviewer` and timezone-aware `reviewed_at` metadata.

The loader rejects missing or unknown fields, unknown firms/statuses, CIK mismatches, malformed dates/accessions, empty provenance, source identities that do not match the accession, and duplicate firm-quarter keys. Malformed evidence fails closed.

## Statuses and numeric policy

The frozen taxonomy is:

- `REPORTED_NONZERO`
- `REPORTED_ZERO`
- `ZERO_SUPPORTED_BY_FILINGS`
- `UNSUPPORTED_XBRL_CONCEPT`
- `NOTE_ONLY`
- `COMPANYFACTS_GAP`
- `MATCHING_GAP`
- `UNRESOLVED`

Only the first three can resolve to a production numeric value. `REPORTED_NONZERO` and `REPORTED_ZERO` originate from the supported CompanyFacts concepts. A ledger record can supply only the third route. Every other status remains missing.

Precedence is strict:

1. a reconciled supported CompanyFacts number is authoritative;
2. if that number is absent, an exact `ZERO_SUPPORTED_BY_FILINGS` record supplies `0.0`;
3. otherwise debt remains `None`.

A reported CompanyFacts zero remains a genuine reported zero. A ledger zero alongside a reported zero is compatible. A ledger zero alongside reported nonzero debt is a contradiction and aborts extraction rather than silently selecting either input.

## Adding a reviewed zero assertion

1. Review the filing for the exact balance-sheet date. Confirm that the balance sheet contains no interest-bearing borrowing liability and that every borrowing, credit-facility, loan, or note disclosure is explicitly undrawn, repaid, terminated, or zero at that instant.
2. Confirm no current-debt line, convertible instrument, unsupported borrowing tag, or note-only amount contradicts zero.
3. Add one exact-quarter record with the SEC accession, filed date/form, statement/note location, concise substantive evidence, archive URL/accession identity, reviewer, and review timestamp.
4. Run ledger, EDGAR, assembly, provenance, and CLI tests and `gitdd panel validate-data`.
5. Update `debt_evidence_sha256` in `panel/data_manifest.toml`. The ledger's SHA-256 and schema version are frozen input identity, so any byte change intentionally changes reproducibility metadata.

Coverage is not a quota. A firm-quarter with no sufficient filing remains unresolved; a statement is not extrapolated into later quarters merely to retain observations.

## Prohibited interpretations

The implementation must not infer zero from CompanyFacts absence, use issuer-name/CIK branches, allow a ledger assertion to override positive reported debt, use vague judgments such as “seems debt free,” add unsupported XBRL concepts without reconciliation, weaken cash/share/revenue/price requirements, or extrapolate an annual statement beyond established period coverage.

## Initial scope and remaining issues

The reviewed ledger contains 78 exact-quarter records: GitLab 18, Hortonworks 16, Couchbase 15, HashiCorp 12, Cloudera 10, Elastic 4, Confluent 2, and MongoDB 1. The evidence review removed eleven candidates rather than replacing them: four wrong-period Cloudera mappings, six Elastic quarters contradicted by a tenant-improvement loan/notes payable, and GitLab 2022-04-30, when its consolidated JiHu VIE had an investor loan. The last proposed HashiCorp 2025-01-31 and Hortonworks 2018-12-31 endpoints also remain unasserted because the preserved evidence has no exact-quarter filing for those acquisition-adjacent dates. These are intended fail-closed outcomes, not completeness targets.

MongoDB's post-conversion finance-lease liabilities remain outside numeric resolution until Part A preregisters whether finance leases belong in enterprise-value debt. MongoDB 2018-04-30 remains a matching/reconciliation question. Candidate current/combined debt and finance-lease concepts remain a separate extractor-reconciliation project because blindly merging totals and components can double count debt.

## Pilot endpoint completeness (read-only)

Using the preserved 2026-09-03 CompanyFacts bundle and applying only endpoint-level cash, debt, shares, and revenue availability (not CRSP, LTM, repository metrics, or regression eligibility):

| Firm | Expected | Old usable | New usable | Remaining endpoint blocks |
|---|---:|---:|---:|---|
| Elastic | 31 | 21 | 25 | Six early endpoints (2018-10 through 2020-01) remain blocked because contemporaneous filings report the tenant-improvement loan/notes payable. |
| MongoDB | 35 | 19 | 19 | 2017-10 and 2018-01 through 2020-04 lack supported shares (11 endpoints; 2018-04 also lacks debt); 2025-04 through 2026-04 have unresolved debt under the current concept/perimeter contract (5 endpoints). |
| GitLab | 19 | 0 | 18 | 2022-04 remains blocked because the reviewed filing reports the consolidated JiHu investor loan. |

These are not final panel-row counts. Four-quarter LTM matching, CRSP coverage, prices, and all other frozen assembly rules still apply, and no regressions were run.
