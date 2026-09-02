import json
import os
import subprocess
from dataclasses import replace
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from git_due_diligence.panel.history import QuarterMetrics
from git_due_diligence.panel.recovery import (
    load_manifest,
    provenance_path,
    recover_repository_metrics,
    select_manifest_firms,
    sha256_file,
    validate_runtime_artifacts,
    validation_succeeds,
    write_provenance,
)
from git_due_diligence.panel.universe import fiscal_quarter_ends


FROZEN_SAMPLE_END = date(2026, 6, 30)
FROZEN_REPOSITORY_HEADS = {
    "elastic": "b5935733cebf339c1a42d62862a189e2b4aee5b7",
    "gitlab": "94b75fd34b533575dacfea444813f95f9e681155",
    "mongodb": "d4089ca8721646c1dc944b2e81ca72cdbab5e5a2",
}


def _manifest(tmp_path: Path, *, sample_end="2024-12-31") -> Path:
    path = tmp_path / "manifest.toml"
    path.write_text(f'''\
schema_version = 1
provenance_schema_version = 1
metric_schema_version = "quarter-metrics-v1"
[[firms]]
slug = "acme"
name = "Acme"
ticker = "ACME"
cik = "0000000001"
repository_url = "https://example.com/acme.git"
repository_host = "example.com"
repository_attribution = "verified_firm_owned"
repository_head = "unavailable_until_recovery"
tier = "core"
fiscal_year_end_month = 12
listing_start = 2023-01-01
listing_end = "open"
sample_end = {sample_end}
permanent_security_id = "unavailable"
financial_source = "SEC EDGAR CompanyFacts"
fundamentals_artifact = "cache/edgar.json"
price_source = "CRSP"
price_artifact = "cache/prices.csv"
price_coverage_start = 2023-01-01
price_coverage_end = 2024-12-31
metrics_artifact = "cache/metrics_acme.json"
coverage_caveat = "none"
''', encoding="utf-8")
    return path


def _record(path: Path, kind: str, identity: str, *, tickers=None, head=None,
            quarter_ends=None):
    return write_provenance(
        path,
        artifact_type=kind,
        identity=identity,
        source="test fixture",
        retrieved_or_built_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
        techdd_commit="a" * 40 if kind == "metrics" else None,
        source_repository_head=head,
        data_schema_version="v1",
        extra=({"tickers": tickers} if tickers else
               {"quarter_ends": quarter_ends} if quarter_ends is not None else None),
    )


def _complete_artifacts(tmp_path: Path):
    cache = tmp_path / "cache"
    cache.mkdir()
    fundamentals = cache / "edgar.json"
    fundamentals.write_text('{"cik": 1, "facts": {}}', encoding="utf-8")
    _record(fundamentals, "fundamentals", "acme")
    metrics = cache / "metrics_acme.json"
    quarter_ends = [
        "2023-03-31", "2023-06-30", "2023-09-30", "2023-12-31",
        "2024-03-31", "2024-06-30", "2024-09-30", "2024-12-31",
    ]
    metrics.write_text(json.dumps({"head": "abc", "quarter_ends": quarter_ends,
                                   "metrics": []}), encoding="utf-8")
    _record(metrics, "metrics", "acme", head="abc", quarter_ends=quarter_ends)
    prices = cache / "prices.csv"
    prices.write_text(
        "date,TICKER,PRC\n2023-01-01,ACME,10\n2024-12-31,ACME,11\n",
        encoding="utf-8",
    )
    _record(prices, "prices", "part-a-core", tickers=["ACME"])
    return fundamentals


def test_manifest_parses_declared_firm():
    manifest = load_manifest(Path("panel/data_manifest.toml"))
    assert [firm.slug for firm in manifest.firms] == ["elastic", "gitlab", "mongodb"]
    assert manifest.firms[1].repository_url == "https://gitlab.com/gitlab-org/gitlab.git"


def test_manifest_firm_selection_is_optional_and_exact():
    manifest = load_manifest(Path("panel/data_manifest.toml"))
    assert select_manifest_firms(manifest) == manifest.firms
    assert [firm.slug for firm in select_manifest_firms(manifest, "elastic")] == ["elastic"]
    with pytest.raises(ValueError, match="not declared"):
        select_manifest_firms(manifest, "not-a-firm")


def test_core_manifest_has_one_fixed_study_cutoff_and_resolved_heads():
    manifest = load_manifest(Path("panel/data_manifest.toml"))
    assert {firm.sample_end for firm in manifest.firms} == {FROZEN_SAMPLE_END}
    assert {firm.price_coverage_end for firm in manifest.firms} == {FROZEN_SAMPLE_END}
    assert {firm.slug: firm.repository_head for firm in manifest.firms} == \
        FROZEN_REPOSITORY_HEADS
    assert all(len(firm.repository_head) == 40 for firm in manifest.firms)
    assert all(int(firm.repository_head, 16) >= 0 for firm in manifest.firms)


def test_frozen_cutoff_controls_each_fiscal_quarter_grid():
    manifest = load_manifest(Path("panel/data_manifest.toml"))
    for firm in manifest.firms:
        ends = fiscal_quarter_ends(
            firm.fiscal_year_end_month, firm.listing_start, firm.sample_end)
        assert ends[-1] == date(2026, 4, 30)
        assert all(quarter_end <= FROZEN_SAMPLE_END for quarter_end in ends)


def test_recovery_rejects_dynamic_or_different_build_end(tmp_path):
    firm = load_manifest(_manifest(tmp_path)).firms[0]
    with pytest.raises(ValueError, match="does not match frozen manifest sample_end"):
        recover_repository_metrics(
            (firm,), work_dir=tmp_path / "work", artifact_root=tmp_path,
            techdd_commit="b" * 40, build_end=date(2026, 9, 1),
            clone=lambda *_args: pytest.fail("clone must not run for a wrong cutoff"))


def test_provenance_generation_and_sha_verification(tmp_path):
    manifest = load_manifest(_manifest(tmp_path))
    _complete_artifacts(tmp_path)
    findings = validate_runtime_artifacts(manifest, tmp_path)
    assert validation_succeeds(findings)
    metadata = json.loads(provenance_path(tmp_path / "cache/edgar.json").read_text())
    assert metadata["retrieved_or_built_at"] == "2026-01-02T00:00:00+00:00"
    assert len(metadata["sha256"]) == 64


def test_missing_required_artifact_fails_closed(tmp_path):
    findings = validate_runtime_artifacts(load_manifest(_manifest(tmp_path)), tmp_path)
    assert not validation_succeeds(findings)
    assert any(f.status == "MISSING" for f in findings)


def test_hash_mismatch_fails_closed(tmp_path):
    manifest = load_manifest(_manifest(tmp_path))
    fundamentals = _complete_artifacts(tmp_path)
    fundamentals.write_text('{"cik": 2}', encoding="utf-8")
    findings = validate_runtime_artifacts(manifest, tmp_path)
    assert not validation_succeeds(findings)
    assert any(f.status == "HASH MISMATCH" for f in findings)


def test_metrics_repository_head_must_match_frozen_manifest_sha(tmp_path):
    manifest = load_manifest(_manifest(tmp_path))
    _complete_artifacts(tmp_path)
    firm = replace(manifest.firms[0], repository_head="a" * 40)
    findings = validate_runtime_artifacts(replace(manifest, firms=(firm,)), tmp_path)
    assert any(f.status == "IDENTITY WARNING" and "does not match frozen" in f.detail
               for f in findings)
    assert not validation_succeeds(findings)


@pytest.mark.parametrize("record", ["artifact", "provenance"])
def test_metrics_quarter_grid_must_match_frozen_manifest_grid(tmp_path, record):
    manifest = load_manifest(_manifest(tmp_path))
    _complete_artifacts(tmp_path)
    metrics = tmp_path / "cache/metrics_acme.json"
    metadata = json.loads(provenance_path(metrics).read_text(encoding="utf-8"))
    if record == "artifact":
        payload = json.loads(metrics.read_text(encoding="utf-8"))
        payload["quarter_ends"] = payload["quarter_ends"][:-1]
        metrics.write_text(json.dumps(payload), encoding="utf-8")
        metadata["sha256"] = sha256_file(metrics)
    else:
        metadata["extra"]["quarter_ends"] = metadata["extra"]["quarter_ends"][:-1]
    provenance_path(metrics).write_text(json.dumps(metadata), encoding="utf-8")

    findings = validate_runtime_artifacts(manifest, tmp_path)
    assert any(f.status == "COVERAGE WARNING" and
               f"metrics {record} quarter grid" in f.detail for f in findings)
    assert not validation_succeeds(findings)


def _init_source(destination: Path) -> None:
    destination.mkdir()
    env = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull}
    subprocess.run(["git", "init", "-b", "main", str(destination)], check=True,
                   capture_output=True)
    (destination / "file.txt").write_text("content\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(destination), "add", "."], check=True,
                   capture_output=True)
    subprocess.run(
        ["git", "-C", str(destination), "-c", "user.name=t",
         "-c", "user.email=t@example.com", "commit", "-m", "initial"],
        check=True, capture_output=True, env=env)


def test_recovery_streams_one_clone_at_a_time(tmp_path):
    manifest = load_manifest(_manifest(tmp_path))
    first = manifest.firms[0]
    firms = (first, type(first)(**{**first.__dict__, "slug": "second",
                                  "metrics_artifact": Path("panel_cache/metrics_second.json")}))
    work = tmp_path / "work"
    observed: list[list[str]] = []

    def clone(_url, destination):
        observed.append(sorted(path.name for path in work.iterdir()))
        _init_source(destination)

    def compute(slug, _repo, quarter_ends, cache):
        cache.mkdir(parents=True, exist_ok=True)
        rows = [QuarterMetrics(q, 1, 1.0, 0.0, 1, 0.0, 0, 0.0, 1, 0.0)
                for q in quarter_ends]
        payload = {"head": "test", "quarter_ends": [q.isoformat() for q in quarter_ends],
                   "metrics": [{**row.__dict__, "quarter_end": row.quarter_end.isoformat()}
                               for row in rows]}
        (cache / f"metrics_{slug}.json").write_text(json.dumps(payload), encoding="utf-8")
        return rows

    results = recover_repository_metrics(
        firms, work_dir=work, artifact_root=tmp_path, techdd_commit="b" * 40,
        build_end=date(2024, 12, 31), clone=clone, compute=compute)

    assert [result["slug"] for result in results] == ["acme", "second"]
    assert observed == [[], []]
    assert list(work.iterdir()) == []
    assert (tmp_path / "cache/metrics_acme.json").is_file()
    assert (tmp_path / "panel_cache/metrics_second.json").is_file()


def _commit(destination: Path, content: str, message: str) -> str:
    (destination / "file.txt").write_text(content, encoding="utf-8")
    subprocess.run(["git", "-C", str(destination), "add", "."], check=True,
                   capture_output=True)
    subprocess.run(
        ["git", "-C", str(destination), "-c", "user.name=t",
         "-c", "user.email=t@example.com", "commit", "-m", message],
        check=True, capture_output=True)
    return subprocess.run(
        ["git", "-C", str(destination), "rev-parse", "HEAD"], check=True,
        capture_output=True, text=True).stdout.strip()


def _recovery_compute(slug, repo, _quarter_ends, cache):
    cache.mkdir(parents=True, exist_ok=True)
    head = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"], check=True,
        capture_output=True, text=True).stdout.strip()
    (cache / f"metrics_{slug}.json").write_text(
        json.dumps({"head": head, "metrics": []}), encoding="utf-8")
    return []


def test_unresolved_repository_head_records_current_head(tmp_path):
    firm = load_manifest(_manifest(tmp_path)).firms[0]
    observed = {}

    def clone(_url, destination):
        _init_source(destination)
        observed["head"] = _commit(destination, "new\n", "new")

    result = recover_repository_metrics(
        (firm,), work_dir=tmp_path / "work", artifact_root=tmp_path,
        techdd_commit="b" * 40, build_end=date(2024, 12, 31), clone=clone,
        compute=_recovery_compute)

    assert result[0]["head"] == observed["head"]


def test_resolved_repository_head_checks_out_historical_commit(tmp_path):
    firm = load_manifest(_manifest(tmp_path)).firms[0]
    source = tmp_path / "source"
    _init_source(source)
    requested = subprocess.run(
        ["git", "-C", str(source), "rev-parse", "HEAD"], check=True,
        capture_output=True, text=True).stdout.strip()
    current = _commit(source, "new\n", "new")

    def clone(_url, destination):
        subprocess.run(["git", "clone", str(source), str(destination)], check=True,
                       capture_output=True)

    frozen = replace(firm, repository_head=requested)
    result = recover_repository_metrics(
        (frozen,), work_dir=tmp_path / "work", artifact_root=tmp_path,
        techdd_commit="b" * 40, build_end=date(2024, 12, 31), clone=clone,
        compute=_recovery_compute)

    assert result[0]["head"] == requested
    assert result[0]["head"] != current


def test_unavailable_resolved_head_fails_before_metric_computation(tmp_path):
    firm = replace(load_manifest(_manifest(tmp_path)).firms[0], repository_head="f" * 40)
    computed = False

    def compute(*_args):
        nonlocal computed
        computed = True

    with pytest.raises(subprocess.CalledProcessError):
        recover_repository_metrics(
            (firm,), work_dir=tmp_path / "work", artifact_root=tmp_path,
            techdd_commit="b" * 40, build_end=date(2024, 12, 31),
            clone=lambda _url, destination: _init_source(destination), compute=compute)
    assert not computed


def _replace_prices(tmp_path: Path, body: str, *, tickers=("ACME",)) -> None:
    prices = tmp_path / "cache/prices.csv"
    prices.write_text(body, encoding="utf-8")
    _record(prices, "prices", "part-a-core", tickers=list(tickers))


def _coverage_warnings(manifest, tmp_path):
    return [f for f in validate_runtime_artifacts(manifest, tmp_path)
            if f.status == "COVERAGE WARNING"]


def test_price_artifact_full_actual_coverage_is_valid(tmp_path):
    manifest = load_manifest(_manifest(tmp_path))
    _complete_artifacts(tmp_path)
    assert not _coverage_warnings(manifest, tmp_path)
    assert validation_succeeds(validate_runtime_artifacts(manifest, tmp_path))


def test_price_ticker_declared_in_provenance_but_absent_from_csv(tmp_path):
    manifest = load_manifest(_manifest(tmp_path))
    _complete_artifacts(tmp_path)
    _replace_prices(tmp_path, "date,TICKER,PRC\n2023-01-01,OTHER,10\n")
    warnings = _coverage_warnings(manifest, tmp_path)
    assert any("zero usable rows" in f.detail for f in warnings)
    assert not validation_succeeds(validate_runtime_artifacts(manifest, tmp_path))


@pytest.mark.parametrize("body,missing", [
    ("date,TICKER,PRC\n2023-01-01,ACME,10\n", "required end"),
    ("date,TICKER,PRC\n2023-02-01,ACME,10\n2024-12-31,ACME,11\n", "required start"),
    ("date,TICKER,PRC\n2023-01-01,ACME,10\n2024-01-01,ACME,11\n", "required end"),
])
def test_insufficient_actual_price_coverage_fails_closed(tmp_path, body, missing):
    manifest = load_manifest(_manifest(tmp_path))
    _complete_artifacts(tmp_path)
    _replace_prices(tmp_path, body)
    warnings = _coverage_warnings(manifest, tmp_path)
    assert any(missing in f.detail for f in warnings)
    assert not validation_succeeds(validate_runtime_artifacts(manifest, tmp_path))


def test_shared_price_file_validates_each_ticker_independently(tmp_path):
    base = load_manifest(_manifest(tmp_path)).firms[0]
    manifest = load_manifest(_manifest(tmp_path))
    manifest = replace(manifest, firms=(base, replace(base, slug="other", ticker="OTHER")))
    _complete_artifacts(tmp_path)
    _replace_prices(
        tmp_path,
        "date,TSYMBOL,PRICE\n2023-01-01,ACME,10\n2024-12-31,ACME,11\n"
        "2023-02-01,OTHER,20\n2024-12-31,OTHER,21\n",
        tickers=("ACME", "OTHER"))
    warnings = _coverage_warnings(manifest, tmp_path)
    assert any("OTHER" in f.detail and "required start" in f.detail for f in warnings)
    assert not any("ACME" in f.detail for f in warnings)


def test_price_coverage_uses_existing_zero_and_negative_semantics(tmp_path):
    manifest = load_manifest(_manifest(tmp_path))
    _complete_artifacts(tmp_path)
    _replace_prices(
        tmp_path,
        "DATADATE,SYMBOL,CLOSE\n2023-01-01,ACME,0\n"
        "2023-01-02,ACME,-10\n2024-12-31,ACME,-11\n")
    warnings = _coverage_warnings(manifest, tmp_path)
    assert any("required start" in f.detail and "2023-01-02" in f.detail for f in warnings)
