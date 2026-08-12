import io
import json
import tarfile

from git_due_diligence.cohort.npm import (
    extract_github_repo,
    fetch_package_names,
    resolve_packages,
)


def _packument(repository=None, homepage=None, versions=None, times=None, latest="1.0.0"):
    return {
        "dist-tags": {"latest": latest},
        "versions": versions or {latest: {}},
        "repository": repository,
        "homepage": homepage,
        "time": times or {},
    }


def _names_tarball(names) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        payload = json.dumps(names).encode()
        info = tarfile.TarInfo("package/names.json")
        info.size = len(payload)
        archive.addfile(info, io.BytesIO(payload))
    return buffer.getvalue()


def test_name_list_fetched_from_mirror_and_cached(tmp_path):
    calls: list[str] = []

    def fetch(url):
        calls.append(url)
        return json.dumps({
            "dist-tags": {"latest": "2.0.1"},
            "versions": {"2.0.1": {"dist": {"tarball": "https://registry.npmjs.org/t.tgz"}}},
        })

    def fetch_bytes(url):
        calls.append(url)
        return _names_tarball(["a", "b", "c"])

    names, version = fetch_package_names(tmp_path, fetch=fetch, fetch_bytes=fetch_bytes)
    assert names == ["a", "b", "c"]
    assert version == "2.0.1"

    again, again_version = fetch_package_names(tmp_path, fetch=fetch, fetch_bytes=fetch_bytes)
    assert again == names and again_version == "2.0.1"
    assert len(calls) == 2                      # cached; mirror not re-fetched


def test_resolves_git_plus_https_url():
    meta = _packument(repository={"type": "git", "url": "git+https://github.com/o/r.git"})
    assert extract_github_repo(meta) == ("o", "r")


def test_resolves_bare_string_repository():
    assert extract_github_repo(_packument(repository="https://github.com/o/r")) == ("o", "r")


def test_resolves_github_shorthand():
    assert extract_github_repo(_packument(repository="github:owner/thing")) == ("owner", "thing")


def test_resolves_git_protocol_and_ssh_forms():
    """git:// dominated npm around 2011-2015, so these packages skew old and
    therefore skew abandoned. Dropping them would bias the frame to survivors."""
    assert extract_github_repo(_packument(repository="git://github.com/o/r.git")) == ("o", "r")
    assert extract_github_repo(
        _packument(repository={"url": "ssh://git@github.com/o/r.git"})) == ("o", "r")
    assert extract_github_repo(
        _packument(repository="git@github.com:o/r.git")) == ("o", "r")   # scp syntax


def test_version_level_repository_preferred_over_stale_top_level():
    meta = _packument(
        repository="https://github.com/old/location",
        versions={"1.0.0": {"repository": {"url": "git+https://github.com/new/location.git"}}},
    )
    assert extract_github_repo(meta) == ("new", "location")


def test_falls_back_to_homepage():
    assert extract_github_repo(
        _packument(repository=None, homepage="https://github.com/o/hp")) == ("o", "hp")


def test_non_github_and_missing_are_out_of_frame():
    assert extract_github_repo(_packument(repository="https://gitlab.com/o/r")) is None
    assert extract_github_repo(_packument()) is None


def test_resolve_dedupes_and_captures_release_dates(tmp_path):
    payloads = {
        "pkg-a": _packument(repository="github:acme/mono",
                            times={"1.0.0": "2019-05-06T00:00:00Z",
                                   "1.1.0": "2021-08-09T00:00:00Z"}),
        "pkg-b": _packument(repository="https://github.com/ACME/Mono"),   # same repo
        "pkg-c": _packument(repository="github:other/solo"),
    }

    def fetch(url):
        return json.dumps(payloads[url.rsplit("/", 1)[-1]])

    entries = resolve_packages(["pkg-a", "pkg-b", "pkg-c"], tmp_path,
                               fetch=fetch, delay_seconds=0)
    assert sorted(e.slug for e in entries) == ["acme/mono", "other/solo"]
    mono = next(e for e in entries if e.slug == "acme/mono")
    assert mono.first_release == "2019-05-06"
    assert mono.last_release == "2021-08-09"


def test_scoped_package_name_is_cache_safe(tmp_path):
    def fetch(url):
        return json.dumps(_packument(repository="github:o/scoped"))

    entries = resolve_packages(["@scope/pkg"], tmp_path, fetch=fetch, delay_seconds=0)
    assert [e.slug for e in entries] == ["o/scoped"]
    assert (tmp_path / "npm__at_scope__pkg.json").exists()   # no path traversal


def test_missing_package_skipped(tmp_path):
    def fetch(url):
        if "gone" in url:
            raise RuntimeError("404")
        return json.dumps(_packument(repository="github:o/live"))

    entries = resolve_packages(["gone", "live"], tmp_path, fetch=fetch, delay_seconds=0)
    assert [e.slug for e in entries] == ["o/live"]
