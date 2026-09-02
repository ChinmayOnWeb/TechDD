# Part A Elastic metric recovery report

**STATUS: SUCCESS**

## Frozen target and producer

| Field | Frozen/recovered value |
|---|---|
| Firm | Elastic N.V. (`elastic`) |
| Canonical repository | `https://github.com/elastic/elasticsearch.git` |
| Frozen repository SHA | `b5935733cebf339c1a42d62862a189e2b4aee5b7` |
| Producing TechDD commit | `04787f966b34ee9499b42f6b419176d9ca99f06c` |
| Study cutoff | 2026-06-30 |
| First fiscal quarter end | 2018-10-31 |
| Last fiscal quarter end | 2026-04-30 |
| Quarter rows | 31 |
| Metric schema | `quarter-metrics-v1` |

The upstream SHA was resolved before recovery by fetching that exact object with
`--depth=1` and comparing `FETCH_HEAD`. The run used the production
`gitdd panel recover-metrics --firm elastic --build-end 2026-06-30` path. It
cloned only Elastic, detached at the manifest SHA, and ran the full metric
implementation; lite mode was not used.

## Runtime result

The recovery completed successfully in approximately 11 minutes 19 seconds. The
machine had approximately 28 GiB free before the run. The working clone occupied
approximately 2.4 GiB after checkout, and `panel_recovery_work/elastic` was absent
after completion, confirming cleanup. The run emitted Git's warning that
exhaustive rename detection was skipped because of the number of files; no
threshold, Git configuration, metric definition, or output was changed in
response.

## Recovered artifacts

| Artifact | Size | SHA-256 |
|---|---:|---|
| `panel_cache/metrics_elastic.json` | 8,330 bytes | `1721a16c7f07a4b5239aaed9a71f06c68d880eef8587673ba18f3b64f13daedc` |
| `panel_cache/metrics_elastic.json.provenance.json` | 1,155 bytes | `d36ee2c670dba9635767ca901ec4eb9dddbb52953d7a7db8608ba7f4b424b296` |

The provenance records identity `elastic`, the canonical source URL, exact source
HEAD, producing TechDD commit, build timestamp, metric schema, all 31 quarter
ends, and the metrics artifact hash. The artifact's own HEAD and quarter grid
match the provenance and frozen manifest exactly.

## Validation

Narrow Elastic metric validation returned only `AVAILABLE`, with the expected
artifact SHA-256. Independent inspection confirmed 31 metric rows and 31 quarter
grid entries spanning 2018-10-31 through 2026-04-30, with no grid mismatch and an
exact provenance/source-HEAD match.

Full `gitdd panel validate-data` remains false as expected: all three firms still
lack the required CRSP artifact; the CompanyFacts artifacts are absent from this
runtime; and GitLab and MongoDB metric artifacts have not yet been recovered.
Those unrelated missing inputs do not invalidate the recovered Elastic metric
artifact.

## Durable storage

The recovered files are preserved in the repository's GitHub prerelease:

<https://github.com/ChinmayOnWeb/TechDD/releases/tag/part-a-elastic-metrics-b5935733>

The release targets the producing TechDD commit and embeds a deterministic
Base64-encoded `tar.gz` recovery bundle with restoration instructions. The bundle
SHA-256 is
`6d909f85ef12fd338de03802b647cf5bee3142becba695a313db87cac1ffb4bb`.
A clean restore from the published release body reproduced both files byte for
byte and reproduced both hashes above.

Direct GitHub release-asset upload was attempted first, but the upload endpoint
returned `HTTP 400: Bad Content-Length` from this execution environment. A secret
Gist fallback was also unavailable because the token lacked Gist access. Embedding
the small checksummed archive in the versioned prerelease keeps it durable without
force-adding the gitignored runtime cache or committing a source clone.

## Remaining blockers

Elastic repository metrics are no longer a recovery blocker. Complete Part A
validation still requires immutable CompanyFacts inputs, the three-ticker CRSP
export and provenance, and frozen metric recovery for GitLab and MongoDB. No
regression estimation was run.
