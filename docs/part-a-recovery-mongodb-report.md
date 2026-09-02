# Part A MongoDB metric recovery report

**STATUS: SUCCESS**

## Frozen target and producer

| Field | Frozen/recovered value |
|---|---|
| Firm | MongoDB, Inc. (`mongodb`) |
| Canonical repository | `https://github.com/mongodb/mongo.git` |
| Frozen repository SHA | `d4089ca8721646c1dc944b2e81ca72cdbab5e5a2` |
| Producing TechDD commit | `5f55352148ac29873bf95d0cd1a2a375dadf21c5` |
| Study cutoff | 2026-06-30 |
| First fiscal quarter end | 2017-10-31 |
| Last fiscal quarter end | 2026-04-30 |
| Quarter rows | 35 |
| Metric schema | `quarter-metrics-v1` |

The exact upstream SHA was resolved before recovery by fetching that object with
`--depth=1` and comparing `FETCH_HEAD`. The run used the production
`gitdd panel recover-metrics --firm mongodb --build-end 2026-06-30` path. It
selected only MongoDB, cloned the canonical repository, detached at the manifest
SHA, and ran the full production metric implementation. Lite mode was not used.

## Runtime and disk behavior

The recovery completed successfully in approximately 23 minutes 6 seconds. The
filesystem had approximately 28 GiB free before the run and again after clone
cleanup. The checked-out working clone occupied approximately 2.2 GiB. The path
`panel_recovery_work/mongodb` was absent after completion, confirming cleanup.

Git warned that exhaustive rename detection was skipped because there were too
many files and suggested raising `diff.renameLimit` to at least 7,531. As required,
the run did not change that threshold, Git configuration, metric definitions, or
outputs in response.

## Recovered artifacts

| Artifact | Size | SHA-256 |
|---|---:|---|
| `panel_cache/metrics_mongodb.json` | 9,340 bytes | `56b7fbe6d0572c11acf1e7cafcbc46ce71d7224e893cefb5e6a5175f0a2b557d` |
| `panel_cache/metrics_mongodb.json.provenance.json` | 1,227 bytes | `b65635c44a294253a88d60a9ef93dfb05d3ca3e11e37c9a30734abc257909d55` |

The provenance records identity `mongodb`, the canonical source URL, exact frozen
source HEAD, producing TechDD commit, UTC build timestamp, metric schema, all 35
quarter ends, and the metrics artifact SHA-256. The artifact and provenance agree
on repository HEAD and quarter grid. The artifact contains 35 metric rows whose
dates exactly match the 35 grid entries from 2017-10-31 through 2026-04-30.

## Validation

Narrow MongoDB metric validation returned only `AVAILABLE`, with the expected
artifact SHA-256. Independent inspection found no repository-HEAD, quarter-grid,
row-count, date-range, provenance, or artifact-hash mismatch.

Full `gitdd panel validate-data` remains false as expected. The required CRSP
artifact and CompanyFacts files are absent, and GitLab metrics have not yet been
recovered. Elastic metrics were present and continued to validate under their
existing artifact/provenance contract. These unrelated missing inputs do not
invalidate the MongoDB metrics artifact.

## Durable storage

The recovered files are preserved using the established Elastic strategy in this
GitHub prerelease:

<https://github.com/ChinmayOnWeb/TechDD/releases/tag/part-a-mongodb-metrics-d4089ca8>

The prerelease targets the producing TechDD commit and embeds a deterministic
Base64-encoded `tar.gz` recovery bundle with restoration instructions. The bundle
SHA-256 is
`93bd5703325fd89da48ed0d15fe0daa8178fc927df6c26b6c33d67b6befdbdf9`.
A clean restore from the published release body reproduced both files byte for
byte and reproduced the artifact, sidecar, and bundle hashes.

The gitignored `panel_cache` files were not force-added, and neither the MongoDB
source clone nor any large raw repository data was committed.

## Remaining blockers

MongoDB repository metrics are no longer a recovery blocker. Complete Part A
validation still requires immutable CompanyFacts inputs, the three-ticker CRSP
export and provenance, and frozen metric recovery for GitLab. No regression
estimation was run.
