# Part A Data Recovery and Reproducibility Plan

**Status:** Data-engineering protocol  
**Purpose:** Make the public-company panel reproducible without relying on any
single local workstation or ephemeral Codex Cloud filesystem.

## 1. Principle

Part A must be rebuildable from a small committed manifest plus externally sourced
raw inputs. Local clones, caches, and assembled panels are runtime artifacts, not
the source of truth.

The pipeline should follow:

`manifest -> raw inputs -> validated cache -> point-in-time repo metrics -> panel.csv -> model outputs`

Every stage records provenance and hashes.

## 2. Required artifacts

### A. Repository source histories

For each included firm, record in a committed manifest:
- firm slug;
- canonical repository URL;
- expected hosting service;
- sample start/end dates;
- exact commit SHA used as clone HEAD for a frozen build;
- whether the repository is firm-owned or foundation-owned;
- attribution status for foundation projects.

Large clones are **not** committed. In cloud execution they are cloned one at a
time, analyzed, cached as compact metrics, and deleted before the next large clone.

Configured core firms currently include:
- Elastic — `elastic/elasticsearch`
- GitLab — canonical upstream `gitlab-org/gitlab`, not the GitHub bot mirror
- MongoDB — `mongodb/mongo`

Staged firms documented in the handoff:
- Confluent
- HashiCorp
- Couchbase
- Cloudera
- Hortonworks

Foundation-project firms must pass the pre-specified employee-commit plurality test
before inclusion.

## 3. EDGAR CompanyFacts cache

For every firm, preserve the exact raw CompanyFacts payload used by the build.

Expected naming convention:
`panel_cache/edgar_CIK<10-digit-cik>.json`

At minimum the recovery set needs:
- `edgar_CIK0001707753.json` — Elastic
- `edgar_CIK0001653482.json` — GitLab
- `edgar_CIK0001441816.json` — MongoDB
- corresponding raw CompanyFacts for every staged/included firm

Each cached file must have:
- source URL;
- retrieval timestamp;
- SHA-256;
- CIK;
- company name;
- HTTP/source metadata where available.

Raw payloads should be immutable once used for a frozen analysis.

## 4. Price data

Primary source for Part A should be CRSP where available because the design requires
delisted-company coverage.

For each firm preserve:
- source identity (CRSP or fallback);
- ticker plus permanent security identifier where available;
- date coverage;
- raw input filename;
- retrieval/export date;
- SHA-256;
- explicit entity verification for reused tickers.

Stooq may remain a fallback for live tickers only. Sources must not be spliced
within a firm's headline price series.

Known special case:
- Cloudera's previously staged export covered only roughly 2020-11 through 2021-10;
  recovery should obtain the full listed window or explicitly document the shorter
  coverage.

## 5. Repo-health metrics cache

After each source clone is analyzed, store compact point-in-time quarter metrics
separately from the clone.

Each metrics artifact must record:
- firm/repo slug;
- source repo URL;
- clone HEAD SHA;
- quarter grid;
- code commit SHA that produced the metrics;
- bot-filter version/hash;
- metric schema version;
- SHA-256 of the metrics file.

This cache is the durable bridge between expensive repository history processing and
cheap panel assembly.

## 6. Historical panel

A frozen `panel.csv` used for any reported result must be preserved as a derived
artifact with:
- build timestamp;
- source-manifest hash;
- all raw-input hashes;
- code commit SHA;
- row count;
- firm count;
- column schema;
- SHA-256.

The previously documented ~68 firm-quarter panel is not currently reproducible
because its runtime inputs were lost. It should be treated as historical pilot
evidence until regenerated.

## 7. Staged-firm cache files

The recovery build should restore or regenerate raw fundamentals and prices for:
- CFLT — Confluent
- HCP — HashiCorp
- BASE — Couchbase
- CLDR — Cloudera
- HDP — Hortonworks

Do not add the three foundation-project firms to the analysis universe until the
employee-commit plurality rule is measured and recorded.

## 8. Storage strategy without local disk

The project should not depend on the user's local machine.

Recommended execution model:
1. Cloud job starts from a clean checkout.
2. Download/restore raw financial caches from durable artifact storage.
3. Clone one large source repository.
4. Compute quarter metrics.
5. Upload/store the compact metrics artifact.
6. Delete the source clone.
7. Repeat for the next firm.
8. Assemble `panel.csv` from compact metrics + financial caches.
9. Store the frozen panel and run manifest.
10. Run estimation from the frozen panel, not directly from live web sources.

Suitable durable storage can be GitHub Actions artifacts/releases, an object store,
or another versioned artifact service. Large raw clones should not be stored unless
necessary; canonical upstream Git plus a pinned HEAD is the recoverable source.

## 9. Committed manifest

Add a machine-readable manifest such as:

`panel/data_manifest.toml`

For every firm, include:
- slug/name;
- ticker and permanent identifier;
- CIK;
- canonical repo URL;
- repo attribution tier/status;
- listing window;
- financial source;
- price source;
- expected raw artifact names;
- known coverage caveats.

A second generated lock file should record exact hashes for a frozen build.

## 10. Validation gates

A professional Part A build should fail closed when:
- raw financial input is missing;
- price coverage is incomplete without an explicit waiver;
- cash/debt/share/revenue semantics are unresolved;
- repo attribution is unverified where required;
- source hashes differ from a frozen lock file;
- a ticker resolves to the wrong entity;
- a derived artifact cannot identify its producing code SHA.

Missing data must never be converted to zero merely to retain rows.

## 11. Recovery sequence

### Phase 1 — configured firms
Regenerate Elastic, GitLab, and MongoDB from scratch and reproduce or explain the
historical ~68-row panel.

### Phase 2 — attrition audit
Run the old-vs-conservative missing-fundamentals comparison using the regenerated raw
inputs. Quantify cash/debt missingness by firm and quarter.

### Phase 3 — staged firms
Recover CFLT/HCP/BASE/CLDR/HDP financial inputs and prices. Run the repo-attribution
test before activating foundation projects.

### Phase 4 — freeze
Create a versioned data manifest + lock file and preserve the resulting `panel.csv`
with hashes.

### Phase 5 — estimation
Only after the frozen panel exists, implement/execute the registered small-cluster
inference for Part A.

## 12. What is needed now

To restore the missing historical runtime state exactly, any surviving copies of the
following would be useful:
- old `panel_cache/`;
- old `panel.csv`;
- old CRSP/price exports;
- old staged CFLT/HCP/BASE/CLDR/HDP raw files;
- any repo-health metrics caches.

However, **none of these are required to continue professionally**. If they are gone,
the preferred solution is to regenerate them from the committed universe/manifest,
canonical repositories, EDGAR/financial sources, and price sources, then freeze the
new reproducible build. The old ~68-row panel should not be reconstructed by hand.
