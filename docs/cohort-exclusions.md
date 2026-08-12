# Part C: frame construction, exclusions, and dead ends

A log of what was tried, what worked, and what came back empty. Negative results
are recorded deliberately: several of the discarded routes look reasonable, and
without a record of why they were rejected they will be re-proposed — by a
reviewer, or by us in six months.

## 1. Ecosystem enumeration

The frame must be a **complete enumeration**, not a popularity ranking.
Sampling by stars, downloads or dependents conditions on success, and the
projects such rankings omit — dead ones — are precisely the events a survival
study exists to model.

### PyPI — works

`https://pypi.org/simple/` (JSON accept header) returns the full project index:
**869,695 projects**. Per-project metadata at `https://pypi.org/pypi/{name}/json`
carries `project_urls` / `home_page`, from which the source repository resolves.

### npm — works, but only via an indirect route

| Route | Result |
|---|---|
| `replicate.npmjs.com/_all_docs` (canonical CouchDB replication) | **unreachable** — not on the network allowlist |
| `skimdb.npmjs.com/registry/_all_docs` | **unreachable** — same |
| `registry.npmjs.org/-/all` | **404** — retired by npm |
| `registry.npmjs.org/-/v1/search` | reachable, but **rejected**: ranks by popularity/quality/maintenance and caps pagination, so a frame built from it would carry exactly the survivorship bias the design removes |
| `all-the-package-names` (a package *published to npm* whose payload is the full name list) | **works** — 4,333,020 names, arrives over the reachable registry host, refreshed daily |

The dependence on a third-party mirror package is a limitation: the list is only
as complete and current as that package's last publish. The frame metadata pins
the mirror version used (`2.0.2530`).

### crates.io — dead end

`crates.io/api/v1/...` returns 403 from this environment. `index.crates.io` *is*
reachable but the sparse index carries only names and versions — **no repository
URLs** — so crates cannot be resolved to repositories. Rust is therefore out of
scope, and that is a data-access limitation rather than a design choice.

### Repository aggregators — all dead ends

`repos.ecosyste.ms`, `libraries.io` and `api.deps.dev` are all unreachable.
These would have been the natural sources for pre-resolved repository URLs and
richer metadata; without them, resolution goes through each registry's own
package metadata.

## 2. Repository-URL matching

npm's `repository` field is far less disciplined than PyPI's: it appears as a
dict or a bare string, and the URL may be `git+https://`, `git://`,
`ssh://git@`, scp-style `git@github.com:owner/repo`, or the `github:owner/repo`
shorthand.

**This mattered more than it looks.** `git://` was npm's dominant convention
around 2011–2015, so packages using it skew old — and old packages skew
abandoned. An https-only matcher would have silently dropped a cohort of
disproportionately *dead* projects, biasing the frame toward survivors. Matching
is therefore scheme-agnostic.

**Audited the same blind spot on PyPI: it is empty.** Of 7,729 cached PyPI
packages, only **2 (0.03%)** contain a GitHub reference the https-only matcher
misses, both bare `github.com/...` strings. The PyPI resolver is deliberately
left unchanged — the frame is already frozen and committed, and perturbing a
pre-registered draw for a 0.03% gain is exactly the kind of undisciplined
adjustment the pre-registration exists to prevent.

## 3. Exclusion thresholds

Both thresholds are **derived**, not chosen. An arbitrary exclusion in a
survival study is not a neutral data-quality filter: the repositories it removes
are systematically the short-lived ones, which are the events being modelled.

### `MIN_QUARTERS` — derived from the measurement machinery

The minimum follow-up at which the primary outcome can be observed at all:

```
MIN_QUARTERS = 1 + TRAILING_WINDOW_QUARTERS + DORMANCY_QUARTERS
             = 1 + 4 + 2 = 7
```

- **1** quarter for the repository to enter the panel.
- **4** quarters because `commit_volume` is itself a *trailing 365-day* count, so
  the first all-zero quarter cannot occur until a full year after the last
  commit.
- **N** quarters for the dormancy run itself.

Shorter follow-up cannot produce an event, so including it adds pure censored
noise; longer would discard observable events. Because it is derived, changing
the dormancy threshold moves it automatically:

| `DORMANCY_QUARTERS` | implied `MIN_QUARTERS` |
|---|---|
| 1 | 6 |
| 2 (current) | 7 |
| 3 | 8 |
| 4 | 9 |

### `MIN_COMMITS` — reduced to its mechanical floor

Previously 10; now **1**. One commit already yields authorship and churn (the
root commit diffs against the empty tree), so 1 is the point below which metrics
are not computable. Any higher bar is a *population definition*, not a technical
requirement — and it removes published-once-then-abandoned projects, which are
the maximal-mortality cases a survival study most needs.

Repository size is instead carried as a covariate, so the analysis conditions on
it explicitly rather than by exclusion.

### Measured sensitivity

*(populated from `scripts/study_exclusions.py`, which harvests with thresholds
disabled so the excluded population can be characterised rather than assumed)*

The question is not how many repositories a filter drops, but whether it drops
**events at a different rate than non-events**. A filter that removes short-lived
projects selects on the outcome, and no sample size repairs that.

## 4. Known limitations carried forward

- **Single-ecosystem primary frame.** PyPI is primary; npm is the robustness
  ecosystem. Conclusions may not transfer to ecosystems with different packaging
  norms. Rust/Go/Maven are unreachable from here.
- **Clone attrition is missing-not-at-random.** ~20% of frame repositories fail
  to clone (deleted, renamed, or made private). Deleted repositories are
  plausibly *more* likely to be dead ones, so this attrition likely biases
  **against** detecting mortality. Reported as a rate; warrants a bounding
  exercise rather than silent exclusion.
- **Registry-to-repository resolution is lossy.** Projects with no GitHub URL are
  out of frame by construction (PyPI resolution rate ≈ 61%). Non-GitHub hosting
  (GitLab, Codeberg, self-hosted) is systematically excluded.
