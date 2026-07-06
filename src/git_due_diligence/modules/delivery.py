from __future__ import annotations

from git_due_diligence.ingest import RepoIngest
from git_due_diligence.models import Evidence, Finding, ModuleResult, Severity

MODULE = "delivery"
STALE_RELEASE_DAYS = 180
TREND_WINDOW_DAYS = 90
TREND_MIN_PRIOR_COMMITS = 10
MERGE_SHARE_MIN = 0.10
MIN_COMMITS_FOR_REVIEW_PROXY = 20
CI_FILES = (".gitlab-ci.yml", "Jenkinsfile", ".circleci/config.yml")


def analyze(ingest: RepoIngest) -> ModuleResult:
    commits = ingest.commits()
    files = ingest.list_files()
    findings: list[Finding] = []
    latest = max(c.authored_at for c in commits)

    # 1. Release cadence from tags.
    tags = ingest.tags()
    days_since_last_release = -1
    if not tags:
        findings.append(Finding(
            module=MODULE, title="No tagged releases", severity=Severity.MEDIUM,
            summary="The repository has no git tags; release cadence cannot be established from history.",
            evidence=[Evidence(description="git tag list is empty")],
        ))
    else:
        last_name, last_date = tags[-1]
        days_since_last_release = (latest - last_date).days
        if days_since_last_release > STALE_RELEASE_DAYS:
            findings.append(Finding(
                module=MODULE, title="Stale release cadence", severity=Severity.MEDIUM,
                summary=(
                    f"The newest tag {last_name} predates the latest commit by "
                    f"{days_since_last_release} days; releases appear to have stalled."
                ),
                evidence=[Evidence(description=f"tag {last_name} dated {last_date.date()}", detail=last_name)],
            ))

    # 2. Contribution activity trend (windows anchored at the latest commit).
    recent = [c for c in commits if 0 <= (latest - c.authored_at).days < TREND_WINDOW_DAYS]
    prior = [c for c in commits
             if TREND_WINDOW_DAYS <= (latest - c.authored_at).days < 2 * TREND_WINDOW_DAYS]
    if len(prior) >= TREND_MIN_PRIOR_COMMITS and len(recent) < 0.5 * len(prior):
        findings.append(Finding(
            module=MODULE, title="Contribution activity declining", severity=Severity.MEDIUM,
            summary=(
                f"{len(recent)} commits in the last {TREND_WINDOW_DAYS} days vs {len(prior)} in "
                f"the prior window — activity has more than halved."
            ),
            evidence=[Evidence(description=f"{len(recent)} recent vs {len(prior)} prior commits")],
        ))

    # 3. Review-flow proxy: merge-commit share. Honest label — squash flows hide review.
    merges = [c for c in commits if len(c.parents) >= 2]
    merge_share = len(merges) / len(commits)
    if len(commits) >= MIN_COMMITS_FOR_REVIEW_PROXY and merge_share < MERGE_SHARE_MIN:
        findings.append(Finding(
            module=MODULE,
            title="Little evidence of PR-based review flow",
            severity=Severity.LOW,
            summary=(
                f"Only {merge_share:.0%} of commits are merge commits (proxy metric; "
                f"squash/rebase merge strategies can hide a real review process)."
            ),
            evidence=[Evidence(description=f"{len(merges)}/{len(commits)} merge commits")],
        ))

    # 4. CI maturity: presence of any known CI configuration.
    fileset = set(files)
    ci_configured = (
        any(f.startswith(".github/workflows/") for f in files)
        or any(ci in fileset for ci in CI_FILES)
    )
    if not ci_configured:
        findings.append(Finding(
            module=MODULE, title="No CI configuration detected", severity=Severity.MEDIUM,
            summary="No GitHub Actions, GitLab CI, Jenkins, or CircleCI configuration is tracked in the repository.",
            evidence=[Evidence(description="no known CI config paths present")],
        ))

    return ModuleResult(
        module=MODULE, status="ok", findings=findings,
        metrics={
            "release_count": len(tags),
            "days_since_last_release": days_since_last_release,
            "merge_commit_share": round(merge_share, 3),
            "commits_last_90d": len(recent),
            "ci_configured": ci_configured,
        },
    )
