# Part A MongoDB metric recovery report

**STATUS: SUCCESS — REGENERATED WITH DETERMINISTIC RENAME SEMANTICS**

## Frozen target and producer

| Field | Frozen/recovered value |
|---|---|
| Firm | MongoDB, Inc. (`mongodb`) |
| Canonical repository | `https://github.com/mongodb/mongo.git` |
| Frozen repository SHA | `d4089ca8721646c1dc944b2e81ca72cdbab5e5a2` |
| Producing TechDD commit | `5ab4a50923ad426e2cf45c34af82990f5774f3ec` |
| Study cutoff | 2026-06-30 |
| First fiscal quarter end | 2017-10-31 |
| Last fiscal quarter end | 2026-04-30 |
| Quarter rows | 35 |
| Metric schema | `quarter-metrics-v1` |
| Bot-filter hash | `7e5c08213be8895660d2e21748ebf023a83d0022993462a21cfc1c3cdae6137b` |

The production command selected only MongoDB, detached at the frozen manifest
SHA, and ran the full metric implementation. Lite mode was not used.

## Deterministic generation contract

Every history diff operation now explicitly uses `--find-renames -l0`: ordinary
Git rename detection with its default similarity threshold, and an unlimited
rename-attempt limit. The same arguments govern `git log --numstat`, buffered
`git log -p`, and streamed `git log -p`; ambient `diff.renames` and
`diff.renameLimit` configuration therefore cannot change these metric inputs.
The deterministic regeneration completed without a rename-limit warning.

The bot-filter identifier is a SHA-256 content hash over the actual
`_is_bot_author` implementation plus the sorted bot markers and automation-marker
constants. Frozen metrics validation requires that exact hash and fails closed if
it is absent or mismatched.

## Runtime and artifacts

The deterministic run completed in approximately 19 minutes 20 seconds. The working
clone occupied approximately 2.2 GiB and was removed successfully afterward.

| Artifact | SHA-256 |
|---|---|
| `panel_cache/metrics_mongodb.json` | `af12b72910c42fada9ca508d1fbc30bb1ad51baf3adc57cfe584d65bb6f0915c` |
| `panel_cache/metrics_mongodb.json.provenance.json` | `1590ff66326efa6a812c2623ed8de5a59d7e63957aba046c3a85414d65bf7382` |
| deterministic recovery bundle | `0ebec1a61a502c836c8621c14d05b59d73285a2afe70e6b6454def6e971084b7` |

The artifact and provenance agree on the frozen repository HEAD, all 35
quarter-grid entries, and 35 metric rows spanning 2017-10-31 through
2026-04-30. Provenance records the producing commit, schema, build timestamp,
artifact hash, and expected bot-filter hash. Narrow validation returned only
`AVAILABLE`.

## Supersession and durable storage

The pre-deterministic artifact is **SUPERSEDED**. Its historical abbreviated
artifact/provenance/bundle hashes remain recorded in the release as `56b7fbe6… / b65635c4… / 93bd5703…`;
they are evidence only and are not authoritative.

The existing prerelease was replaced in place with the authoritative deterministic
bundle and restoration instructions:

<https://github.com/ChinmayOnWeb/TechDD/releases/tag/part-a-mongodb-metrics-d4089ca8>

The release tag now targets the producing TechDD commit. A clean restore from the
published Base64 bundle reproduced its bundle hash and both files byte-for-byte.
The gitignored cache and source clone were not committed.

## Remaining blockers

MongoDB repository metrics now satisfy the deterministic provenance contract.
Complete Part A validation still requires immutable CompanyFacts inputs, the
three-ticker CRSP export and provenance, and frozen metric recovery for
GitLab. No regression estimation was run.
