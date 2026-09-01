import json
import os
import subprocess
from datetime import date, datetime, timezone
from pathlib import Path

from git_due_diligence.panel.history import QuarterMetrics
from git_due_diligence.panel.recovery import (
    load_manifest,
    provenance_path,
    recover_repository_metrics,
    validate_runtime_artifacts,
    validation_succeeds,
    write_provenance,
)


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


def _record(path: Path, kind: str, identity: str, *, tickers=None, head=None):
    return write_provenance(
        path,
        artifact_type=kind,
        identity=identity,
        source="test fixture",
        retrieved_or_built_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
        techdd_commit="a" * 40 if kind == "metrics" else None,
        source_repository_head=head,
        data_schema_version="v1",
        extra={"tickers": tickers} if tickers else None,
    )


def _complete_artifacts(tmp_path: Path):
    cache = tmp_path / "cache"
    cache.mkdir()
    fundamentals = cache / "edgar.json"
    fundamentals.write_text('{"cik": 1, "facts": {}}', encoding="utf-8")
    _record(fundamentals, "fundamentals", "acme")
    metrics = cache / "metrics_acme.json"
    metrics.write_text('{"head": "abc", "metrics": []}', encoding="utf-8")
    _record(metrics, "metrics", "acme", head="abc")
    prices = cache / "prices.csv"
    prices.write_text("date,TICKER,PRC\n2024-01-01,ACME,10\n", encoding="utf-8")
    _record(prices, "prices", "part-a-core", tickers=["ACME"])
    return fundamentals


def test_manifest_parses_declared_firm():
    manifest = load_manifest(Path("panel/data_manifest.toml"))
    assert [firm.slug for firm in manifest.firms] == ["elastic", "gitlab", "mongodb"]
    assert manifest.firms[1].repository_url == "https://gitlab.com/gitlab-org/gitlab.git"


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
