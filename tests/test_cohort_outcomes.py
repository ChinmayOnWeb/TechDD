from datetime import date

from git_due_diligence.cohort.outcomes import (
    first_contributor_collapse,
    first_dormancy,
    observation_rows,
)
from git_due_diligence.panel.history import QuarterMetrics


def _m(commit_volume=10, contributors=3, index=0):
    return QuarterMetrics(
        quarter_end=date(2020 + index // 4, [3, 6, 9, 12][index % 4], 28),
        active_contributors=contributors, top_author_share=0.4,
        contributor_gini=0.3, bus_factor_50=2, churn_gini=0.4,
        release_cadence=None, merge_share=0.1,
        commit_volume=commit_volume, secret_incidence=None,
    )


def _series(volumes, contributors=None):
    contributors = contributors or [3] * len(volumes)
    return [_m(v, c, i) for i, (v, c) in enumerate(zip(volumes, contributors))]


def test_dormancy_fires_at_end_of_silent_run():
    # quarters passed explicitly so the algorithm test is independent of the
    # pre-registered default threshold
    spell = first_dormancy("a/b", _series([5, 5, 0, 0, 0, 0, 0]), quarters=4)
    assert spell.event is True
    assert spell.quarter_index == 5          # end of the silent run, not its start


def test_dormancy_not_triggered_by_short_gap():
    spell = first_dormancy("a/b", _series([5, 0, 0, 0, 5, 5]), quarters=4)
    assert spell.event is False              # three quiet quarters, then revival


def test_dormancy_run_resets_on_activity():
    spell = first_dormancy("a/b", _series([0, 0, 0, 5, 0, 0, 0]), quarters=4)
    assert spell.event is False


def test_active_repo_is_right_censored_not_a_survivor():
    metrics = _series([5] * 10)
    spell = first_dormancy("a/b", metrics)
    assert spell.event is False
    assert spell.quarter_index == 9          # censored at last observation
    assert spell.quarter_end == metrics[-1].quarter_end


def test_contributor_collapse_detected_against_horizon():
    spell = first_contributor_collapse(
        "a/b", _series([5] * 8, contributors=[10, 10, 10, 10, 4, 4, 4, 4]))
    assert spell.event is True
    assert spell.quarter_index == 4          # 10 -> 4 across the 4-quarter horizon


def test_single_maintainer_dropout_is_not_collapse():
    # 1 -> 0 contributors is dormancy, not collapse; keeps the constructs distinct
    spell = first_contributor_collapse(
        "a/b", _series([5] * 8, contributors=[1, 1, 1, 1, 0, 0, 0, 0]))
    assert spell.event is False


def test_mild_decline_is_not_collapse():
    spell = first_contributor_collapse(
        "a/b", _series([5] * 8, contributors=[10, 10, 10, 10, 8, 8, 8, 8]))
    assert spell.event is False


def test_observation_rows_stop_at_event():
    metrics = _series([5, 5, 0, 0, 0, 0, 5, 5])
    spell = first_dormancy("a/b", metrics, quarters=4)
    rows = observation_rows("a/b", metrics, spell)
    assert len(rows) == spell.quarter_index + 1
    assert [r["event"] for r in rows] == [0] * (len(rows) - 1) + [1]


def test_censored_rows_carry_no_event():
    metrics = _series([5] * 6)
    spell = first_dormancy("a/b", metrics)
    rows = observation_rows("a/b", metrics, spell)
    assert len(rows) == 6
    assert all(r["event"] == 0 for r in rows)


def test_observation_rows_carry_point_in_time_predictors():
    metrics = _series([5, 5, 5])
    rows = observation_rows("a/b", metrics, first_dormancy("a/b", metrics))
    assert rows[0]["active_contributors"] == 3
    assert "bus_factor_50" in rows[0] and "churn_gini" in rows[0]
