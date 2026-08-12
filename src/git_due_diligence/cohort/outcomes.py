"""Outcome events for the Part C cohort study.

Each outcome is derived purely from the harvested metric series, so it inherits
the same point-in-time property as the predictors: the value at quarter t uses
only history available at t, and the outcome is observed strictly afterwards.
That separation is what makes the hazard models interpretable as prediction
rather than contemporaneous correlation.

Right-censoring is explicit. A repository that is still active at the end of the
observation window has not "survived forever" -- it is censored, and the hazard
model must be told so. Treating censored repositories as non-events would bias
survival upward exactly for the healthiest projects.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from git_due_diligence.panel.history import QuarterMetrics

# Consecutive zero-commit quarters before a project is called dormant.
#
# NOTE the interaction with the predictor window: commit_volume is itself a
# TRAILING 365-DAY count, so a single zero quarter already means "no commits in
# the preceding twelve months". Requiring N consecutive zero quarters therefore
# means roughly 12 + 3N months of silence, not 3N. Two quarters is ~18 months
# without a commit -- long enough not to flag projects that merely pause, short
# enough to observe events inside the window. This threshold is a
# pre-registration decision and should be frozen before estimation.
DORMANCY_QUARTERS = 2
# Fractional fall in active contributors over the comparison horizon.
COLLAPSE_RATIO = 0.5
COLLAPSE_HORIZON_QUARTERS = 4


@dataclass(frozen=True)
class OutcomeSpell:
    """One repository's outcome under a single definition.

    `event` is True when the outcome occurred, False when the repository was
    still event-free at the end of observation (right-censored). `quarter_index`
    is the position in the metric series at which the event was first observed,
    or the final observed index when censored -- the duration a hazard model
    consumes."""
    slug: str
    outcome: str
    event: bool
    quarter_index: int
    quarter_end: date | None


def first_dormancy(slug: str, metrics: list[QuarterMetrics],
                   quarters: int = DORMANCY_QUARTERS) -> OutcomeSpell:
    """First quarter completing `quarters` consecutive zero-commit quarters.

    The event is dated at the END of the silent run, not its start: at the start
    we cannot yet distinguish a dormant project from a quiet one, and dating it
    there would leak future information into the event time."""
    run = 0
    for index, row in enumerate(metrics):
        if row.commit_volume == 0:
            run += 1
            if run >= quarters:
                return OutcomeSpell(slug, "dormancy", True, index, row.quarter_end)
        else:
            run = 0
    last = len(metrics) - 1
    return OutcomeSpell(slug, "dormancy", False, max(last, 0),
                        metrics[last].quarter_end if metrics else None)


def first_contributor_collapse(slug: str, metrics: list[QuarterMetrics],
                               ratio: float = COLLAPSE_RATIO,
                               horizon: int = COLLAPSE_HORIZON_QUARTERS) -> OutcomeSpell:
    """First quarter where active contributors have fallen by at least `ratio`
    relative to `horizon` quarters earlier.

    Only evaluated from a base of at least two contributors: a one-person
    project dropping to zero is dormancy, and counting it here would make the
    two outcomes near-duplicates rather than distinct constructs."""
    for index in range(horizon, len(metrics)):
        base = metrics[index - horizon].active_contributors
        current = metrics[index].active_contributors
        if base >= 2 and current <= base * (1 - ratio):
            return OutcomeSpell(slug, "contributor_collapse", True, index,
                                metrics[index].quarter_end)
    last = len(metrics) - 1
    return OutcomeSpell(slug, "contributor_collapse", False, max(last, 0),
                        metrics[last].quarter_end if metrics else None)


def observation_rows(slug: str, metrics: list[QuarterMetrics],
                     spell: OutcomeSpell) -> list[dict]:
    """Repository-quarter rows up to and including the event (or censoring),
    each carrying the predictors measured at that quarter and a 0/1 event flag.

    Quarters after the event are dropped: once a project is dormant it is no
    longer at risk, and leaving those rows in would let post-event quarters
    contribute to the hazard."""
    rows: list[dict] = []
    for index, row in enumerate(metrics[: spell.quarter_index + 1]):
        is_last = index == spell.quarter_index
        rows.append({
            "slug": slug,
            "outcome": spell.outcome,
            "quarter_end": row.quarter_end.isoformat(),
            "quarter_index": index,
            "event": int(spell.event and is_last),
            "active_contributors": row.active_contributors,
            "top_author_share": row.top_author_share,
            "contributor_gini": row.contributor_gini,
            "bus_factor_50": row.bus_factor_50,
            "churn_gini": row.churn_gini,
            "merge_share": row.merge_share,
            "commit_volume": row.commit_volume,
        })
    return rows
