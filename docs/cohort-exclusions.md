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

### `MIN_QUARTERS` — no follow-up exclusion at all

**A derivation was attempted and measurement refuted it.** The reasoning was
that a repository needs `1 (entry) + 4 (trailing window) + N (dormancy run)`
quarters before an event can occur, giving 7, and that anything shorter
contributes only censored noise. Both halves were wrong:

1. **The lag is not constant.** The trailing-365-day window is half-open, so the
   first all-zero quarter lands at index **3 or 4** depending on where in the
   quarter the first commit falls (measured by sweeping all 366 possible
   first-commit dates). A 2-quarter dormancy run can therefore fire by quarter
   **5**, not 7.
2. **Short follow-up is not noise.** Right-censoring is exactly the mechanism
   survival analysis uses for varying follow-up. A repository observed for three
   quarters without an event is censored at three quarters — information the
   hazard model consumes correctly.

Measured against the 400-repository pilot (328 harvested, 191 dormancy events):

| threshold | repos kept | events kept | **events lost** |
|---|---|---|---|
| 1 (adopted) | 328 | 191 | **0** |
| 2–6 | 304–258 | 191 | **0** |
| 7 *(the hand-derivation)* | 249 | 188 | **3** |
| 8 *(the original value)* | 243 | 184 | **7** |

Every threshold above the mechanical floor can only lose events, so the floor is
what is used. `earliest_observable_event_quarters()` is retained as an
*informational* function for the paper's exposition, deliberately not wired to
any filter.

### `MIN_COMMITS` — reduced to its mechanical floor

Previously 10; now **1**. One commit already yields authorship and churn (the
root commit diffs against the empty tree), so 1 is the point below which metrics
are not computable. Any higher bar is a *population definition*, not a technical
requirement — and it removes published-once-then-abandoned projects, which are
the maximal-mortality cases a survival study most needs.

Repository size is instead carried as a covariate, so the analysis conditions on
it explicitly rather than by exclusion.

### Measured sensitivity

From `scripts/study_exclusions.py`, which harvests with thresholds disabled so
the excluded population is characterised rather than assumed. Pilot: the first
400 frame entries; 328 harvested (16% clone failures), 191 dormancy events (58%).

The question is not how many repositories a filter drops, but whether it drops
**events at a different rate than non-events**:

| commit threshold | repos kept | events kept | event rate, kept | event rate, **dropped** |
|---|---|---|---|---|
| 1 (adopted) | 328 | 191 | 58% | — |
| 3 | 314 | 181 | 58% | **71%** |
| 5 | 302 | 175 | 58% | **62%** |
| 10 *(the original value)* | 272 | 154 | 57% | **66%** |
| 25 | 209 | 108 | 52% | **70%** |
| 50 | 166 | 82 | 49% | **67%** |

The dropped set has a **higher event rate than the kept set at every
threshold**, and the effect grows as the threshold rises. This is selection on
the outcome, measured rather than argued: `MIN_COMMITS = 10` would have
discarded 37 of 191 events (19%). Small repositories are disproportionately
dead repositories, which is precisely why they cannot be filtered out of a
mortality study.

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
