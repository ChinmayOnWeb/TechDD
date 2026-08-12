import json

from git_due_diligence.cohort.frame import (
    FrameEntry,
    extract_github_repo,
    fetch_project_names,
    read_frame,
    resolve_projects,
    sample_projects,
    write_frame,
)

SIMPLE_INDEX = json.dumps({"projects": [{"name": f"pkg{i:03d}"} for i in range(500)]})


def _meta(project_urls=None, home_page=None, releases=None):
    return {
        "info": {"project_urls": project_urls, "home_page": home_page},
        "releases": releases or {},
    }


def test_simple_index_cached_once(tmp_path):
    calls: list[str] = []

    def fetch(url):
        calls.append(url)
        return SIMPLE_INDEX

    assert len(fetch_project_names(tmp_path, fetch)) == 500
    fetch_project_names(tmp_path, fetch)
    assert len(calls) == 1                       # frozen snapshot, not re-drawn


def test_sample_is_deterministic_for_a_seed(tmp_path):
    names = [f"pkg{i:03d}" for i in range(500)]
    first = sample_projects(names, 20, seed=7)
    second = sample_projects(names, 20, seed=7)
    assert first == second
    assert len(set(first)) == 20
    assert sample_projects(names, 20, seed=8) != first


def test_sample_independent_of_input_ordering():
    names = [f"pkg{i:03d}" for i in range(200)]
    assert sample_projects(names, 15, seed=3) == sample_projects(reversed(names), 15, seed=3)


def test_sample_larger_than_pool_returns_whole_pool():
    assert len(sample_projects(["a", "b", "c"], 10, seed=1)) == 3


def test_extracts_repo_from_source_label():
    found = extract_github_repo(_meta({"Source": "https://github.com/psf/requests"}))
    assert found == ("psf", "requests")


def test_prefers_source_label_over_unrelated_github_link():
    found = extract_github_repo(_meta({
        "Funding": "https://github.com/sponsors/someone",
        "Repository": "https://github.com/real/project",
    }))
    assert found == ("real", "project")


def test_falls_back_to_home_page():
    found = extract_github_repo(_meta(project_urls=None,
                                      home_page="https://github.com/owner/thing"))
    assert found == ("owner", "thing")


def test_strips_git_suffix_and_ignores_sponsors():
    assert extract_github_repo(_meta({"Source": "https://github.com/o/r.git"})) == ("o", "r")
    assert extract_github_repo(_meta({"Funding": "https://github.com/sponsors/o"})) is None


def test_non_github_project_is_out_of_frame():
    assert extract_github_repo(_meta({"Source": "https://gitlab.com/o/r"})) is None


def test_resolve_dedupes_monorepo_packages(tmp_path):
    payloads = {
        "pkg-a": _meta({"Source": "https://github.com/acme/mono"},
                       releases={"1.0": [{"upload_time_iso_8601": "2020-01-05T00:00:00Z"}]}),
        "pkg-b": _meta({"Source": "https://github.com/ACME/Mono"}),   # same repo, other case
        "pkg-c": _meta({"Source": "https://github.com/other/solo"}),
    }

    def fetch(url):
        name = url.rsplit("/json", 1)[0].rsplit("/", 1)[-1]
        return json.dumps(payloads[name])

    entries = resolve_projects(["pkg-a", "pkg-b", "pkg-c"], tmp_path,
                               fetch=fetch, delay_seconds=0)
    assert sorted(e.slug for e in entries) == ["acme/mono", "other/solo"]


def test_resolve_skips_missing_projects_without_failing(tmp_path):
    def fetch(url):
        if "gone" in url:
            raise RuntimeError("404 yanked")
        return json.dumps(_meta({"Source": "https://github.com/o/live"}))

    entries = resolve_projects(["gone", "live"], tmp_path, fetch=fetch, delay_seconds=0)
    assert [e.slug for e in entries] == ["o/live"]


def test_release_stats_captured_for_post_stratification(tmp_path):
    payload = _meta({"Source": "https://github.com/o/r"}, releases={
        "1.0": [{"upload_time_iso_8601": "2019-03-04T10:00:00Z"}],
        "2.0": [{"upload_time_iso_8601": "2021-07-09T10:00:00Z"}],
    })
    entries = resolve_projects(["p"], tmp_path,
                               fetch=lambda url: json.dumps(payload), delay_seconds=0)
    entry = entries[0]
    assert entry.release_count == 2
    assert entry.first_release == "2019-03-04"
    assert entry.last_release == "2021-07-09"


def test_frame_round_trips(tmp_path):
    entries = [FrameEntry("p", "o", "r", "https://github.com/o/r.git", 3, "2020-01-01", "2021-01-01")]
    path = tmp_path / "frame.json"
    write_frame(entries, path, meta={"seed": 42, "sample_size": 1})
    assert read_frame(path) == entries
    assert json.loads(path.read_text())["meta"]["seed"] == 42
