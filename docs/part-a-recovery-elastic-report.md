# Part A Elastic metric recovery report

**STATUS: SUCCESS — REGENERATED WITH DETERMINISTIC RENAME SEMANTICS**

## Frozen target and producer

| Field | Frozen/recovered value |
|---|---|
| Firm | Elastic N.V. (`elastic`) |
| Canonical repository | `https://github.com/elastic/elasticsearch.git` |
| Frozen repository SHA | `b5935733cebf339c1a42d62862a189e2b4aee5b7` |
| Producing TechDD commit | `5ab4a50923ad426e2cf45c34af82990f5774f3ec` |
| Study cutoff | 2026-06-30 |
| First fiscal quarter end | 2018-10-31 |
| Last fiscal quarter end | 2026-04-30 |
| Quarter rows | 31 |
| Metric schema | `quarter-metrics-v1` |
| Bot-filter hash | `7e5c08213be8895660d2e21748ebf023a83d0022993462a21cfc1c3cdae6137b` |

The production command selected only Elastic, detached at the frozen manifest
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

The deterministic run completed in approximately 12 minutes 32 seconds. The working
clone occupied approximately 2.4 GiB and was removed successfully afterward.

| Artifact | SHA-256 |
|---|---|
| `panel_cache/metrics_elastic.json` | `1977c42f8899806164dde907898ae840c1a0b13942687d0003613b1193679c57` |
| `panel_cache/metrics_elastic.json.provenance.json` | `2226575b4f6c1ace166aaa289311e1254d64a0fd0f6975193dd391a758901618` |
| deterministic recovery bundle | `5a5f092087e5f7528cd3e379978a0668c11bfa24f5238aaf14ad3e392694e511` |

The artifact and provenance agree on the frozen repository HEAD, all 31
quarter-grid entries, and 31 metric rows spanning 2018-10-31 through
2026-04-30. Provenance records the producing commit, schema, build timestamp,
artifact hash, and expected bot-filter hash. Narrow validation returned only
`AVAILABLE`.

## Supersession and durable storage

The pre-deterministic artifact is **SUPERSEDED**. Its historical abbreviated
artifact/provenance/bundle hashes remain recorded in the release as `1721a16c… / d36ee2c6… / 6d909f85…`;
they are evidence only and are not authoritative.

The existing prerelease was replaced in place with the authoritative deterministic
bundle and restoration instructions:

<https://github.com/ChinmayOnWeb/TechDD/releases/tag/part-a-elastic-metrics-b5935733>

The release tag now targets the producing TechDD commit. A clean restore from the
published Base64 bundle reproduced its bundle hash and both files byte-for-byte.
The gitignored cache and source clone were not committed.

## Remaining blockers

Elastic repository metrics now satisfy the deterministic provenance contract.
Complete Part A validation still requires immutable CompanyFacts inputs, the
three-ticker CRSP export and provenance, and frozen metric recovery for
GitLab. No regression estimation was run.
