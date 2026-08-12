import os
import subprocess
from datetime import date
from pathlib import Path

from git_due_diligence.panel.history import QuarterMetrics
from git_due_diligence.panel.metrics_cache import load_or_compute_metrics

QUARTERS = [date(2025, 3, 31), date(2025, 6, 30)]


def _init_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    env = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull}
    subprocess.run(["git", "init", "-b", "main", str(repo)], check=True, capture_output=True)
    (repo / "a.txt").write_text("x\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@example.com",
         "commit", "-m", "init"], check=True, capture_output=True, env=env)
    return repo


def _fake_compute(calls: list, ret: list[QuarterMetrics]):
    def compute(repo_path, quarter_ends):
        calls.append((repo_path, tuple(quarter_ends)))
        return ret
    return compute


def _sample(qs):
    return [QuarterMetrics(q, 3, 0.5, 0.4, 2, 0.6, 1, 0.3, 30, 0.0) for q in qs]


def test_second_call_hits_cache(tmp_path):
    repo = _init_repo(tmp_path)
    cache = tmp_path / "cache"
    calls: list = []
    compute = _fake_compute(calls, _sample(QUARTERS))

    first = load_or_compute_metrics("acme", repo, QUARTERS, cache, compute=compute)
    second = load_or_compute_metrics("acme", repo, QUARTERS, cache, compute=compute)

    assert len(calls) == 1                      # computed once, second served from cache
    assert (cache / "metrics_acme.json").exists()
    assert [m.quarter_end for m in second] == QUARTERS
    assert second[0] == first[0]                # round-trips through JSON intact


def test_new_head_invalidates_cache(tmp_path):
    repo = _init_repo(tmp_path)
    cache = tmp_path / "cache"
    calls: list = []
    compute = _fake_compute(calls, _sample(QUARTERS))
    load_or_compute_metrics("acme", repo, QUARTERS, cache, compute=compute)

    # advance HEAD
    env = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull}
    (repo / "b.txt").write_text("y\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@example.com",
         "commit", "-m", "second"], check=True, capture_output=True, env=env)

    load_or_compute_metrics("acme", repo, QUARTERS, cache, compute=compute)
    assert len(calls) == 2                      # recomputed after HEAD moved


def test_changed_quarter_grid_invalidates_cache(tmp_path):
    repo = _init_repo(tmp_path)
    cache = tmp_path / "cache"
    calls: list = []
    compute = _fake_compute(calls, _sample(QUARTERS))
    load_or_compute_metrics("acme", repo, QUARTERS, cache, compute=compute)

    new_grid = QUARTERS + [date(2025, 9, 30)]
    compute2 = _fake_compute(calls, _sample(new_grid))
    load_or_compute_metrics("acme", repo, new_grid, cache, compute=compute2)
    assert len(calls) == 2
