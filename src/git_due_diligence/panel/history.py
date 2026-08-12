from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

from git_due_diligence.ingest import RepoIngest
from git_due_diligence.modules.bus_factor import _bus_factor, _gini, _is_bot_author
from git_due_diligence.modules.security import (
    _SECRET_PATTERNS,
    _is_private_key_prose_mention,
    _is_template_binding_mention,
    _looks_like_test_path,
)

TRAILING_DAYS = 365


@dataclass
class QuarterMetrics:
    quarter_end: date
    active_contributors: int
    top_author_share: float
    contributor_gini: float
    bus_factor_50: int
    churn_gini: float
    # release_cadence and secret_incidence are None when not measured (lite mode),
    # which is distinct from a measured zero. Collapsing the two would read
    # "no releases / no secrets" for repos we simply never scanned.
    release_cadence: int | None
    merge_share: float
    commit_volume: int
    secret_incidence: float | None


def _zero_row(quarter_end: date, lite: bool = False) -> QuarterMetrics:
    return QuarterMetrics(
        quarter_end, 0, 0.0, 0.0, 0, 0.0,
        None if lite else 0, 0.0, 0, None if lite else 0.0,
    )


def _high_confidence_secret_shas(ingest: RepoIngest) -> Counter:
    counts: Counter = Counter()
    seen: set[str] = set()
    for record in ingest.iter_patch_records():
        if not record.startswith("COMMIT "):
            continue
        header, _, body = record.partition("\n")
        sha = header.removeprefix("COMMIT ").strip()
        current_path: str | None = None
        for line in body.splitlines():
            if line.startswith("+++ b/"):
                current_path = line[6:]
                continue
            if not line.startswith("+") or line.startswith("+++"):
                continue
            for label, pattern in _SECRET_PATTERNS:
                for match in pattern.finditer(line):
                    secret = match.group(0)
                    if secret in seen:
                        continue
                    seen.add(secret)
                    low_confidence = (
                        (label == "Private key block"
                         and _is_private_key_prose_mention(line, match))
                        or (label == "Hardcoded credential assignment"
                            and _is_template_binding_mention(line, match))
                        or _looks_like_test_path(current_path)
                    )
                    if not low_confidence:
                        counts[sha] += 1
    return counts


def quarterly_metrics(repo_path: Path, quarter_ends: list[date],
                      lite: bool = False) -> list[QuarterMetrics]:
    """Trailing-window metrics at each requested quarter-end.

    `lite=True` skips the two passes that dominate runtime -- the full-history
    patch scan behind `secret_incidence` (~15k commits/min, 37 minutes on a
    550k-commit repo) and the per-tag date lookup behind `release_cadence`
    (one subprocess per tag). Both fields come back None to mark them
    unmeasured. Lite mode is what makes a thousands-of-repos sweep tractable;
    the firm panel always runs full."""
    ingest = RepoIngest(repo_path)
    commits = [c for c in ingest.commits() if not _is_bot_author(c.author_email)]
    tag_dates = [] if lite else [dt.date() for _, dt in ingest.tags()]
    secrets_by_sha = Counter() if lite else _high_confidence_secret_shas(ingest)

    rows: list[QuarterMetrics] = []
    for q_end in quarter_ends:
        start = q_end - timedelta(days=TRAILING_DAYS)
        window = [c for c in commits if start < c.authored_at.date() <= q_end]
        if not window:
            rows.append(_zero_row(q_end, lite=lite))
            continue
        n = len(window)
        author_counts = Counter(c.author_email for c in window)
        churn: Counter = Counter()
        for c in window:
            for change in c.changes:
                churn[change.path] += change.added + change.deleted
        merges = sum(1 for c in window if len(c.parents) > 1)
        releases = sum(1 for d in tag_dates if start < d <= q_end)
        secrets = sum(secrets_by_sha.get(c.sha, 0) for c in window)
        rows.append(QuarterMetrics(
            quarter_end=q_end,
            active_contributors=len(author_counts),
            top_author_share=round(author_counts.most_common(1)[0][1] / n, 4),
            contributor_gini=round(_gini(list(author_counts.values())), 4),
            bus_factor_50=_bus_factor(author_counts),
            churn_gini=round(_gini(list(churn.values())), 4),
            release_cadence=None if lite else releases,
            merge_share=round(merges / n, 4),
            commit_volume=n,
            secret_incidence=None if lite else round(1000.0 * secrets / n, 4),
        ))
    return rows
