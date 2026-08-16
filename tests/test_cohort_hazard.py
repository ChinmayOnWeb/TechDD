import json
from datetime import date, timedelta

import pytest

from git_due_diligence.cohort.hazard import (
    ACTIVITY_CONTROL,
    PREDICTOR_LAG_QUARTERS,
    STRUCTURAL,
    load_observations,
)


def _metric(qe, volume, contributors):
    return {
        "quarter_end": qe.isoformat(), "active_contributors": contributors,
        "top_author_share": 0.5, "contributor_gini": 0.3, "bus_factor_50": 1,
        "churn_gini": 0.4, "release_cadence": None, "merge_share": 0.1,
        "commit_volume": volume, "secret_incidence": None,
    }


def _repo(slug, volumes, contributors=None):
    contributors = contributors or [2] * len(volumes)
    start = date(2016, 3, 31)
    metrics = [_metric(start + timedelta(days=91 * i), v, c)
               for i, (v, c) in enumerate(zip(volumes, contributors))]
    return {"slug": slug, "status": "ok", "commit_count": sum(volumes),
            "first_commit": "2016-01-01", "last_commit": "2024-01-01",
            "metrics": metrics, "error": ""}


def _write(tmp_path, records):
    path = tmp_path / "h.jsonl"
    path.write_text("\n".join(json.dumps(r) for r in records), encoding="utf-8")
    return {"test": path}


def test_predictors_are_lagged_clear_of_the_event_window(tmp_path):
    """The event is determined by commits over roughly the six quarters before
    it, so a contemporaneous covariate conditions on a component of the
    outcome. With no lag, commit_volume == 0 perfectly separates the event and
    the model is unestimable (singular Hessian), not merely biased."""
    assert PREDICTOR_LAG_QUARTERS >= 5

    volumes = [10] * 10 + [0] * 4
    panel = load_observations(_write(tmp_path, [_repo("a/b", volumes)]))
    row = panel[panel["event"] == 1].iloc[0]
    lag_index = row["quarter_index"] - PREDICTOR_LAG_QUARTERS
    source = panel[panel["quarter_index"] == lag_index].iloc[0]
    assert row["lag_log_commit_volume"] == pytest.approx(source["log_commit_volume"])
    assert source["commit_volume"] > 0        # predictor drawn from an active quarter


def test_lag_does_not_leak_across_repositories(tmp_path):
    a = _repo("a/one", [10] * 12)
    b = _repo("b/two", [99] * 12)
    panel = load_observations(_write(tmp_path, [a, b]))
    early = panel[(panel["slug"] == "b/two")
                  & (panel["quarter_index"] < PREDICTOR_LAG_QUARTERS)]
    assert early["lag_log_commit_volume"].isna().all()


def test_activity_control_is_present_and_named(tmp_path):
    assert ACTIVITY_CONTROL == "log_commit_volume"
    assert ACTIVITY_CONTROL not in STRUCTURAL      # a control, not a health metric


def test_counts_enter_in_logs(tmp_path):
    panel = load_observations(_write(tmp_path, [_repo("a/b", [10] * 12,
                                                     contributors=[4] * 12)]))
    import numpy as np
    assert panel["log_contributors"].iloc[0] == pytest.approx(np.log1p(4))


def test_risk_set_ends_at_the_event(tmp_path):
    volumes = [10] * 8 + [0] * 6
    panel = load_observations(_write(tmp_path, [_repo("a/b", volumes)]))
    events = panel[panel["event"] == 1]
    assert len(events) == 1
    assert panel["quarter_index"].max() == events.iloc[0]["quarter_index"]


def test_censored_repo_contributes_only_zero_event_rows(tmp_path):
    panel = load_observations(_write(tmp_path, [_repo("a/b", [10] * 12)]))
    assert panel["event"].sum() == 0
    assert len(panel) == 12


def test_solo_flag_tracks_contributor_count(tmp_path):
    panel = load_observations(_write(tmp_path, [
        _repo("a/solo", [5] * 10, contributors=[1] * 10),
        _repo("a/multi", [5] * 10, contributors=[3] * 10)]))
    assert panel[panel["slug"] == "a/solo"]["solo"].eq(1).all()
    assert panel[panel["slug"] == "a/multi"]["solo"].eq(0).all()


def test_ecosystem_label_is_retained_for_separate_estimation(tmp_path):
    paths = _write(tmp_path, [_repo("a/b", [5] * 10)])
    panel = load_observations(paths)
    assert set(panel["ecosystem"]) == {"test"}
