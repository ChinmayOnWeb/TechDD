from __future__ import annotations

from collections import Counter, defaultdict

from acquirescope.ingest import RepoIngest
from acquirescope.models import Evidence, Finding, ModuleResult, Severity

MIN_DIR_COMMITS = 5       # directories with fewer commits are too small to judge
DEPARTED_SHARE = 0.20     # author owns >= 20% of all commits
DEPARTED_DAYS = 180       # and has been inactive this long vs latest commit
MODULE = "bus_factor"


def _bus_factor(author_counts: Counter) -> int:
    """Smallest number of authors covering >= 50% of a directory's commits."""
    total = sum(author_counts.values())
    covered, k = 0, 0
    for _, count in author_counts.most_common():
        covered += count
        k += 1
        if covered * 2 >= total:
            return k
    return k


def _gini(values: list[int]) -> float:
    if not values or sum(values) == 0:
        return 0.0
    sorted_vals = sorted(values)
    n = len(sorted_vals)
    cum = sum((i + 1) * v for i, v in enumerate(sorted_vals))
    return (2 * cum) / (n * sum(sorted_vals)) - (n + 1) / n


def analyze(ingest: RepoIngest) -> ModuleResult:
    commits = ingest.commits()
    findings: list[Finding] = []

    # Per top-level directory: which authors touch it, how often.
    dir_authors: dict[str, Counter] = defaultdict(Counter)
    for commit in commits:
        touched_dirs = {
            change.path.split("/", 1)[0] if "/" in change.path else "<root>"
            for change in commit.changes
        }
        for d in touched_dirs:
            dir_authors[d][commit.author_email] += 1

    for directory, counts in sorted(dir_authors.items()):
        total = sum(counts.values())
        if total < MIN_DIR_COMMITS:
            continue
        if _bus_factor(counts) == 1:
            owner, owner_count = counts.most_common(1)[0]
            findings.append(Finding(
                module=MODULE,
                title=f"Single point of failure: {directory}/",
                severity=Severity.HIGH,
                summary=(
                    f"One contributor accounts for the majority of all {total} commits "
                    f"touching {directory}/ ({owner_count} commits). Loss of this person "
                    f"strands the component."
                ),
                evidence=[Evidence(
                    description=f"{owner_count}/{total} commits in {directory}/",
                    path=directory, detail=owner,
                )],
            ))

    # High-share contributors who have gone quiet. The engine can only see
    # commit activity, not why it stopped -- it cannot distinguish a genuine
    # departure from a founder moving into a non-coding leadership role, a
    # maintainer handoff, or an extended leave. Report the observed fact
    # (inactivity) rather than asserting the unverifiable one (departure).
    author_totals = Counter(c.author_email for c in commits)
    total_commits = len(commits)
    latest = max(c.authored_at for c in commits)
    last_seen = {}
    for c in commits:
        prev = last_seen.get(c.author_email)
        if prev is None or c.authored_at > prev:
            last_seen[c.author_email] = c.authored_at
    for author, count in author_totals.items():
        share = count / total_commits
        inactive_days = (latest - last_seen[author]).days
        if share >= DEPARTED_SHARE and inactive_days > DEPARTED_DAYS:
            findings.append(Finding(
                module=MODULE,
                title=f"Key contributor inactive: {author}",
                severity=Severity.HIGH,
                summary=(
                    f"{author} authored {share:.0%} of all commits but has not committed "
                    f"in {inactive_days} days. This is consistent with departure, but also "
                    f"with a shift to a non-coding role (e.g. a founder moving into an "
                    f"executive position) or an extended leave -- verify this person's "
                    f"current relationship with the project before treating it as a "
                    f"departure or knowledge-loss risk."
                ),
                evidence=[Evidence(
                    description=f"{count}/{total_commits} commits; last active {last_seen[author].date()}",
                    detail=author,
                )],
            ))

    top_share = author_totals.most_common(1)[0][1] / total_commits
    return ModuleResult(
        module=MODULE, status="ok", findings=findings,
        metrics={
            "contributor_gini": round(_gini(list(author_totals.values())), 3),
            "top_author_share": round(top_share, 3),
        },
    )
