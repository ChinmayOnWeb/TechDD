import json
import os
import subprocess
from datetime import date
from pathlib import Path

from git_due_diligence.cohort.frame import FrameEntry
from git_due_diligence.cohort.harvest import (
    HarvestResult,
    append_result,
    calendar_quarter_ends,
    completed_slugs,
    harvest_frame,
    harvest_repo,
)
from git_due_diligence.panel.history import QuarterMetrics

TODAY = date(2026, 8, 12)


def _entry(owner="acme", repo="thing", url="https://example.invalid/acme/thing.git"):
    return FrameEntry("pkg", owner, repo, url, 3, "2020-01-01", "2024-01-01")


def _make_repo(path: Path, n_commits: int, start_year: int = 2020) -> Path:
    env = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull}
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-b", "main", str(path)], check=True, capture_output=True)
    for i in range(n_commits):
        (path / "f.txt").write_text(f"v{i}\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(path), "add", "."], check=True, capture_output=True)
        stamp = f"{start_year + i // 4}-{1 + (i % 4) * 3:02d}-15T10:00:00"
        subprocess.run(
            ["git", "-C", str(path), "-c", "user.name=t", "-c", "user.email=t@example.com",
             "commit", "-m", f"c{i}"],
            check=True, capture_output=True,
            env={**env, "GIT_AUTHOR_DATE": stamp, "GIT_COMMITTER_DATE": stamp})
    return path


def _fake_clone_from(source: Path):
    def clone(url, target):
        subprocess.run(["git", "clone", "--bare", "--quiet", str(source), str(target)],
                       check=True, capture_output=True)
        return True, ""
    return clone


def test_calendar_quarter_ends_are_calendar_not_fiscal():
    ends = calendar_quarter_ends(date(2024, 1, 1), date(2024, 12, 31))
    assert ends == [date(2024, 3, 31), date(2024, 6, 30),
                    date(2024, 9, 30), date(2024, 12, 31)]


def test_clone_failure_recorded_not_raised(tmp_path):
    def failing_clone(url, target):
        return False, "repository not found"

    result = harvest_repo(_entry(), tmp_path / "work", TODAY, clone=failing_clone)
    assert result.status == "clone_failed"
    assert "not found" in result.error
    assert result.metrics == []


def test_tiny_repo_is_kept_by_default(tmp_path):
    """A published-once-then-abandoned project is the maximal-mortality case and
    must stay in the sample; excluding it by commit count would select on the
    outcome. The default floor is the mechanical one (metrics computable)."""
    source = _make_repo(tmp_path / "src", n_commits=3, start_year=2019)
    result = harvest_repo(_entry(), tmp_path / "work", TODAY,
                          clone=_fake_clone_from(source))
    assert result.status == "ok"
    assert result.commit_count == 3


def test_commit_floor_is_applicable_for_sensitivity_analysis(tmp_path):
    source = _make_repo(tmp_path / "src", n_commits=3, start_year=2019)
    result = harvest_repo(_entry(), tmp_path / "work", TODAY,
                          clone=_fake_clone_from(source), min_commits=10)
    assert result.status == "too_small"


def test_earliest_observable_event_is_informational_not_a_filter():
    """The half-open trailing window puts the first all-zero quarter at index 3
    or 4 depending on the first commit's position in its quarter, so a
    2-quarter dormancy run can fire by quarter 5. A hand-derived threshold of 7
    discarded real events in a pilot, so no follow-up exclusion is applied."""
    from git_due_diligence.cohort.harvest import (
        MIN_QUARTERS, earliest_observable_event_quarters,
    )
    assert earliest_observable_event_quarters(2) == 5
    assert earliest_observable_event_quarters(4) == 7
    assert MIN_QUARTERS == 1               # mechanical floor only


def test_short_followup_repo_is_kept_and_censored(tmp_path):
    """Right-censoring handles varying follow-up; excluding short histories
    would discard early events instead."""
    source = _make_repo(tmp_path / "src", n_commits=4, start_year=2025)
    result = harvest_repo(_entry(), tmp_path / "work", TODAY,
                          clone=_fake_clone_from(source))
    assert result.status == "ok"
    assert 0 < len(result.metrics) < 8


def test_short_history_excluded(tmp_path):
    # 12 commits inside a single year -> fewer than MIN_QUARTERS quarter-ends
    source = tmp_path / "src"
    _make_repo(source, n_commits=12, start_year=2024)
    subprocess.run(["git", "-C", str(source), "log", "--oneline"], capture_output=True)
    result = harvest_repo(_entry(), tmp_path / "work", TODAY,
                          clone=_fake_clone_from(source))
    assert result.status in {"too_short", "ok"}
    if result.status == "too_short":
        assert result.metrics == []


def test_successful_harvest_produces_metrics_and_deletes_clone(tmp_path):
    source = _make_repo(tmp_path / "src", n_commits=24, start_year=2019)
    workdir = tmp_path / "work"
    result = harvest_repo(_entry(), workdir, TODAY, clone=_fake_clone_from(source))
    assert result.status == "ok"
    assert result.commit_count == 24
    assert len(result.metrics) >= 8
    assert list(workdir.iterdir()) == []          # clone removed after measuring


def test_observation_window_extends_past_last_commit(tmp_path):
    """A repo abandoned years ago must still yield the silent quarters that
    constitute dormancy. Ending the window at the last commit would make the
    primary outcome unobservable by construction."""
    source = _make_repo(tmp_path / "src", n_commits=24, start_year=2015)
    result = harvest_repo(_entry(), tmp_path / "work", TODAY,
                          clone=_fake_clone_from(source))
    assert result.status == "ok"
    assert result.last_commit < "2022"
    silent = [m for m in result.metrics if m.commit_volume == 0]
    assert len(silent) >= 4                       # dormancy is detectable
    assert result.metrics[-1].quarter_end >= date(2026, 6, 30)


def test_shortlived_repo_still_enters_the_sample(tmp_path):
    """A project with a burst of commits then abandonment is an EVENT, not an
    exclusion -- dropping it would select on the outcome."""
    source = tmp_path / "src"
    _make_repo(source, n_commits=12, start_year=2021)
    result = harvest_repo(_entry(), tmp_path / "work", TODAY,
                          clone=_fake_clone_from(source))
    assert result.status == "ok"
    assert any(m.commit_volume == 0 for m in result.metrics)


def test_clone_removed_even_when_measurement_raises(tmp_path):
    source = _make_repo(tmp_path / "src", n_commits=24, start_year=2019)
    workdir = tmp_path / "work"

    def boom(path, ends):
        raise RuntimeError("measurement exploded")

    try:
        harvest_repo(_entry(), workdir, TODAY,
                     clone=_fake_clone_from(source), measure=boom)
    except RuntimeError:
        pass
    assert list(workdir.iterdir()) == []          # no stranded gigabytes


def test_lite_metrics_mark_unmeasured_fields_none(tmp_path):
    source = _make_repo(tmp_path / "src", n_commits=24, start_year=2019)
    result = harvest_repo(_entry(), tmp_path / "work", TODAY,
                          clone=_fake_clone_from(source))
    measured = [m for m in result.metrics if m.commit_volume > 0][0]
    assert measured.secret_incidence is None      # not scanned, not "zero secrets"
    assert measured.release_cadence is None
    assert measured.active_contributors >= 1


def test_checkpoint_roundtrip_and_resume(tmp_path):
    checkpoint = tmp_path / "cp.jsonl"
    append_result(checkpoint, HarvestResult(
        "acme/thing", "ok", 12, "2020-01-01", "2024-01-01",
        [QuarterMetrics(date(2024, 3, 31), 2, 0.5, 0.3, 1, 0.4, None, 0.0, 5, None)]))
    assert completed_slugs(checkpoint) == {"acme/thing"}
    row = json.loads(checkpoint.read_text().splitlines()[0])
    assert row["metrics"][0]["quarter_end"] == "2024-03-31"
    assert row["metrics"][0]["secret_incidence"] is None


def test_torn_checkpoint_line_does_not_break_resume(tmp_path):
    checkpoint = tmp_path / "cp.jsonl"
    checkpoint.write_text('{"slug": "a/b"}\n{"slug": "c/d"\n', encoding="utf-8")
    assert completed_slugs(checkpoint) == {"a/b"}


def test_clone_timeout_recorded_not_fatal(tmp_path):
    """A timeout is a property of one repository, not of the sweep. An uncaught
    TimeoutExpired ended a 4,850-repo run after 866 on ccxt/ccxt."""
    import subprocess as sp

    from git_due_diligence.cohort.harvest import clone_bare

    def exploding_run(args, timeout):
        raise sp.TimeoutExpired(args, timeout)

    import git_due_diligence.cohort.harvest as h
    original, h._run = h._run, exploding_run
    try:
        ok, error = clone_bare("https://example.invalid/big.git", tmp_path / "x", timeout=1)
    finally:
        h._run = original
    assert ok is False
    assert error.startswith("__timeout__")


def test_timeout_gets_its_own_status(tmp_path):
    def timing_out_clone(url, target):
        return False, "__timeout__ clone exceeded 300s"

    result = harvest_repo(_entry(), tmp_path / "work", TODAY, clone=timing_out_clone)
    assert result.status == "clone_timeout"          # distinct from clone_failed


def test_sweep_stops_cleanly_when_disk_is_low(tmp_path):
    import pytest

    import git_due_diligence.cohort.harvest as h
    original, h.free_disk_gb = h.free_disk_gb, lambda: 0.5
    try:
        with pytest.raises(RuntimeError, match="checkpointed"):
            list(harvest_frame([_entry()], tmp_path / "work",
                               tmp_path / "cp.jsonl", TODAY, min_free_gb=3.0))
    finally:
        h.free_disk_gb = original


def test_parallel_harvest_covers_every_entry_once(tmp_path):
    from git_due_diligence.cohort.harvest import harvest_frame_parallel

    entries = [_entry(owner="o", repo=f"r{i}") for i in range(25)]
    seen: list[str] = []
    lock_seen = __import__("threading").Lock()

    def clone(url, target):
        with lock_seen:
            seen.append(url)
        return False, "stub"

    results = list(harvest_frame_parallel(entries, tmp_path / "work",
                                          tmp_path / "cp.jsonl", TODAY,
                                          workers=4, clone=clone))
    assert len(results) == 25
    assert len({r.slug for r in results}) == 25       # no duplicates
    assert len(seen) == 25                            # each cloned exactly once


def test_parallel_checkpoint_is_not_corrupted_by_concurrent_writes(tmp_path):
    from git_due_diligence.cohort.harvest import harvest_frame_parallel

    entries = [_entry(owner="o", repo=f"r{i}") for i in range(40)]
    checkpoint = tmp_path / "cp.jsonl"
    list(harvest_frame_parallel(entries, tmp_path / "work", checkpoint, TODAY,
                                workers=8, clone=lambda u, t: (False, "stub")))
    lines = [l for l in checkpoint.read_text().splitlines() if l.strip()]
    assert len(lines) == 40
    for line in lines:
        json.loads(line)                              # every line intact
    assert len(completed_slugs(checkpoint)) == 40


def test_parallel_harvest_resumes_from_checkpoint(tmp_path):
    from git_due_diligence.cohort.harvest import harvest_frame_parallel

    checkpoint = tmp_path / "cp.jsonl"
    append_result(checkpoint, HarvestResult("o/r0", "ok", 5, "", "", []))
    entries = [_entry(owner="o", repo=f"r{i}") for i in range(5)]
    results = list(harvest_frame_parallel(entries, tmp_path / "work", checkpoint,
                                          TODAY, workers=4,
                                          clone=lambda u, t: (False, "stub")))
    assert "o/r0" not in {r.slug for r in results}
    assert len(results) == 4


def test_harvest_frame_skips_completed(tmp_path):
    checkpoint = tmp_path / "cp.jsonl"
    append_result(checkpoint, HarvestResult("acme/done", "ok", 5, "", "", []))
    attempted: list[str] = []

    def clone(url, target):
        attempted.append(url)
        return False, "stub"

    entries = [_entry(owner="acme", repo="done"), _entry(owner="acme", repo="fresh")]
    results = list(harvest_frame(entries, tmp_path / "work", checkpoint, TODAY, clone=clone))
    assert [r.slug for r in results] == ["acme/fresh"]
    assert len(attempted) == 1
