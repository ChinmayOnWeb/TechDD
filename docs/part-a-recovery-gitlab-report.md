# Part A GitLab metric recovery report

**STATUS: SUCCESS — REGENERATED AND DURABLY PUBLISHED**

## Frozen target and producer

| Field | Frozen/recovered value |
|---|---|
| Firm | GitLab Inc. (`gitlab`) |
| Canonical repository | `https://gitlab.com/gitlab-org/gitlab.git` |
| Frozen repository SHA | `94b75fd34b533575dacfea444813f95f9e681155` |
| Producing TechDD commit | `51f5df6cbad89f4cd3d3ae3aa4de35696f11fd83` |
| Study cutoff | 2026-06-30 |
| First fiscal quarter end | 2021-10-31 |
| Last fiscal quarter end | 2026-04-30 |
| Quarter rows | 19 |
| Metric schema | `quarter-metrics-v1` |
| Bot-filter hash | `7e5c08213be8895660d2e21748ebf023a83d0022993462a21cfc1c3cdae6137b` |

Before scanning, the frozen SHA was resolved directly from GitLab.com. The
workspace had approximately 30 GiB free, and the production command selected only
GitLab. No GitHub mirror was queried or used. The repository was checked out at a
detached frozen HEAD, and the full production metric implementation ran without
lite mode.

## Deterministic generation contract

All relevant history diff operations used `--find-renames -l0`, including
`git log --numstat` and the streamed full-history patch scan. The recovery retained
the existing bot filter, exact manifest quarter grid, full metric schema, and
missing-data behavior. GitLab's configured history produced zero release tags;
`release_cadence` remains a descriptive field excluded from the composite index,
as required by the existing release-cadence caveat.

## Runtime, disk, and artifacts

The end-to-end production command took approximately 68 minutes, including the
canonical full clone, checkout, full-history scans, artifact generation, and clone
cleanup. Preflight reported about 30 GiB free. Peak clone usage was not separately
instrumented, so no retrospective peak-size estimate is asserted. The one allowed
working clone and its checkout were removed successfully; only the compact,
gitignored cache files remained.

| Artifact | SHA-256 |
|---|---|
| `panel_cache/metrics_gitlab.json` | `2038c7731f5d57af9e36ae320de4d6fd058bcd2aaba6221937832e7998b58ff0` |
| `panel_cache/metrics_gitlab.json.provenance.json` | `42051a9221bf932229f7d75e9526a2833b74d05cb8927929e03f7a1f569cad96` |
| deterministic recovery bundle | `f8a7f1cdfd10cb7df29396cd93e97cb6415a7217f6e5c8c4747a369ee2667e39` |

The artifact and provenance agree on identity, canonical source, frozen repository
HEAD, all 19 quarter-grid entries, and 19 metric rows spanning 2021-10-31 through
2026-04-30. Provenance records the producing TechDD commit, metric schema, build
timestamp, artifact hash, and expected bot-filter hash. Narrow GitLab validation
returned only `AVAILABLE`.

## Durable storage and clean restore

The deterministic Base64 recovery bundle and restoration instructions are
published in this prerelease, whose tag targets the producing TechDD commit:

<https://github.com/ChinmayOnWeb/TechDD/releases/tag/part-a-gitlab-metrics-94b75fd3>

A clean restore from the published release body reproduced the bundle SHA-256 and
both cache files byte-for-byte. Neither the large source clone nor the gitignored
`panel_cache` files are committed.

## Validation and remaining blockers

`gitdd panel validate-data` identified the GitLab metric artifact as `AVAILABLE`
with the artifact hash above. Overall validation remains false solely because the
clean checkout lacks the immutable CompanyFacts inputs, the shared three-ticker
CRSP export, and the separately published Elastic and MongoDB metric caches.
Those financial/cache inputs remain blockers to complete Part A validation and
panel assembly. No methodology, universe, date, repository lock, or regression
change was made, and no regression estimation was run.
