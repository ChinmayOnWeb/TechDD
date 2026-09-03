import json
import subprocess

from typer.testing import CliRunner

from git_due_diligence.cli import app

runner = CliRunner()

_QUARTER_PERIODS = [
    ("2023-01-01", "2023-03-31"), ("2023-04-01", "2023-06-30"),
    ("2023-07-01", "2023-09-30"), ("2023-10-01", "2023-12-31"),
    ("2024-01-01", "2024-03-31"), ("2024-04-01", "2024-06-30"),
    ("2024-07-01", "2024-09-30"), ("2024-10-01", "2024-12-31"),
]

ACME_TOML = """\
name = "Acme"
slug = "acme"
ticker = "ACME"
cik = "0000000001"
repos = ["https://example.com/acme.git"]
fiscal_year_end_month = 12
listed_from = 2023-01-01
listed_to = 2024-12-31
"""

STOOQ_CSV = "Date,Open,High,Low,Close,Volume\n" + "\n".join(
    f"{d},20,21,19,20.0,1000" for d in
    ["2023-03-31", "2023-06-30", "2023-09-29", "2023-12-29",
     "2024-03-28", "2024-06-28", "2024-09-30", "2024-12-31"]) + "\n"


def _canned_edgar() -> dict:
    revenue = [{"start": s, "end": e, "val": 100.0 + 5 * i, "form": "10-Q"}
               for i, (s, e) in enumerate(_QUARTER_PERIODS)]
    ends = [e for _, e in _QUARTER_PERIODS]
    return {"cik": 1, "facts": {
        "dei": {"EntityCommonStockSharesOutstanding": {"units": {"shares": [
            {"end": e, "val": 1_000_000.0, "form": "10-Q"} for e in ends]}}},
        "us-gaap": {
            "Revenues": {"units": {"USD": revenue}},
            "OperatingIncomeLoss": {"units": {"USD": [
                {**entry, "val": 10.0} for entry in revenue]}},
            "CashAndCashEquivalentsAtCarryingValue": {"units": {"USD": [
                {"end": e, "val": 50.0} for e in ends]}},
            "LongTermDebt": {"units": {"USD": [
                {"end": e, "val": 0.0} for e in ends]}},
        },
    }}


def test_panel_help_lists_commands():
    result = runner.invoke(app, ["panel", "--help"])
    assert result.exit_code == 0
    assert "build" in result.output
    assert "regress" in result.output


def test_panel_build_runs_offline_from_cache_outside_repository(tmp_path, monkeypatch):
    universe = tmp_path / "universe"
    universe.mkdir()
    (universe / "acme.toml").write_text(ACME_TOML, encoding="utf-8")

    clones = tmp_path / "clones"
    repo = clones / "acme"
    repo.mkdir(parents=True)
    subprocess.run(["git", "init", "-b", "main", str(repo)], check=True, capture_output=True)
    (repo / "a.py").write_text("A = 1\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "a.py"], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@example.com",
         "commit", "-m", "init", "--date", "2023-02-01T10:00:00"],
        check=True, capture_output=True,
    )

    cache = tmp_path / "cache"
    cache.mkdir()
    (cache / "edgar_CIK0000000001.json").write_text(json.dumps(_canned_edgar()), encoding="utf-8")
    (cache / "stooq_acme.us.csv").write_text(STOOQ_CSV, encoding="utf-8")
    ledger = tmp_path / "debt_evidence.toml"
    ledger.write_text("schema_version = 1\n", encoding="utf-8")

    output = tmp_path / "panel.csv"
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, [
        "panel", "build", "--universe", str(universe), "--clones", str(clones),
        "--cache", str(cache), "--debt-evidence", str(ledger), "-o", str(output),
    ])
    assert result.exit_code == 0, result.output
    import pandas as pd
    panel = pd.read_csv(output)
    assert len(panel) == 5
    assert "repo_health_index_z" in panel.columns
    assert set(panel["firm"]) == {"acme"}


def test_panel_build_skips_firm_without_clone(tmp_path):
    universe = tmp_path / "universe"
    universe.mkdir()
    (universe / "acme.toml").write_text(ACME_TOML, encoding="utf-8")
    clones = tmp_path / "clones"
    clones.mkdir()
    output = tmp_path / "panel.csv"
    result = runner.invoke(app, [
        "panel", "build", "--universe", str(universe), "--clones", str(clones),
        "--cache", str(tmp_path / "cache"), "-o", str(output),
    ])
    assert result.exit_code == 0
    assert "skipping acme" in result.output


def test_panel_regress_writes_result_tables(tmp_path):
    import numpy as np
    import pandas as pd
    rng = np.random.default_rng(0)
    rows = []
    for i in range(10):
        for t in range(20):
            idx = rng.normal()
            rows.append({
                "firm": f"f{i}", "quarter_end": f"q{t:02d}",
                "repo_health_index_z": idx,
                "growth_yoy": rng.normal(0, 0.01),
                "op_margin_ltm": rng.normal(0, 0.1),
                "log_rev": rng.normal(5, 0.5),
                "log_ev_rev": 1.0 + 0.5 * idx + rng.normal(0, 0.01),
            })
    csv_path = tmp_path / "panel.csv"
    pd.DataFrame(rows).to_csv(csv_path, index=False)
    out_dir = tmp_path / "results"
    result = runner.invoke(app, ["panel", "regress", str(csv_path), "-o", str(out_dir)])
    assert result.exit_code == 0, result.output
    assert (out_dir / "h1_pricing.txt").exists()
    assert "h1" in result.output


def _write_explain_fixture(
    tmp_path, *, debt=100.0, ledger_record=False, include_audit_csv=True,
):
    root = tmp_path / "root"
    (root / "panel_cache").mkdir(parents=True)
    (root / "panel").mkdir()
    if include_audit_csv:
        (root / "panel/candidate_universe.csv").write_text(
            "slug,cik\nacme,0000000001\n", encoding="utf-8")
    facts = _canned_edgar()
    facts["facts"]["us-gaap"]["LongTermDebt"]["units"]["USD"] = (
        [] if debt is None else [{"end": "2024-03-31", "val": debt,
                                  "accn": "0000000001-24-000002"}])
    (root / "panel_cache/edgar_CIK0000000001.json").write_text(
        json.dumps(facts), encoding="utf-8")
    manifest = tmp_path / "manifest.toml"
    manifest.write_text('''schema_version = 1
+provenance_schema_version = 1
+metric_schema_version = "quarter-metrics-v1"
+[[firms]]
+slug="acme"
+name="Acme"
+ticker="ACME"
+cik="0000000001"
+repository_url="https://example.test/acme"
+repository_host="example.test"
+repository_attribution="test"
+repository_head="unavailable"
+tier="core"
+fiscal_year_end_month=12
+listing_start=2023-01-01
+listing_end="open"
+sample_end=2024-12-31
+permanent_security_id="unavailable"
+financial_source="SEC"
+fundamentals_artifact="panel_cache/edgar_CIK0000000001.json"
+price_source="CRSP"
+price_artifact="prices.csv"
+price_coverage_start=2023-01-01
+price_coverage_end=2024-12-31
+metrics_artifact="metrics.json"
+coverage_caveat="none"
+'''.replace("+", ""), encoding="utf-8")
    ledger = tmp_path / "debt.toml"
    record = '''
+[[records]]
+firm="acme"
+cik="0000000001"
+quarter_end=2024-03-31
+classification="ZERO_SUPPORTED_BY_FILINGS"
+accession="0000000001-24-000001"
+filing_date=2024-05-01
+filing_form="10-Q"
+evidence_location="balance sheet"
+evidence_note="facility had no balance"
+source_url="https://www.sec.gov/Archives/edgar/data/1/000000000124000001/"
+immutable_evidence_id="sec-accession:0000000001-24-000001"
+reviewer="reviewer"
+reviewed_at=2024-05-02T00:00:00Z
+'''.replace("+", "") if ledger_record else ""
    ledger.write_text("schema_version = 1\n" + record, encoding="utf-8")
    return root, manifest, ledger


def test_explain_debt_identifies_reported_fact(tmp_path):
    root, manifest, ledger = _write_explain_fixture(tmp_path)
    result = runner.invoke(app, ["panel", "explain-debt", "--firm", "acme",
        "--quarter", "2024-03-31", "--manifest", str(manifest),
        "--ledger", str(ledger), "--root", str(root)])
    assert result.exit_code == 0, result.output
    assert "REPORTED_NONZERO" in result.output
    assert "concept=LongTermDebt" in result.output


def test_explain_debt_identifies_filing_backed_zero(tmp_path):
    root, manifest, ledger = _write_explain_fixture(tmp_path, debt=None, ledger_record=True)
    result = runner.invoke(app, ["panel", "explain-debt", "--firm", "acme",
        "--quarter", "2024-03-31", "--manifest", str(manifest),
        "--ledger", str(ledger), "--root", str(root)])
    assert result.exit_code == 0, result.output
    assert "ZERO_SUPPORTED_BY_FILINGS" in result.output
    assert "0000000001-24-000001" in result.output


def test_explain_debt_identifies_unresolved(tmp_path):
    root, manifest, ledger = _write_explain_fixture(tmp_path, debt=None)
    result = runner.invoke(app, ["panel", "explain-debt", "--firm", "acme",
        "--quarter", "2024-03-31", "--manifest", str(manifest),
        "--ledger", str(ledger), "--root", str(root)])
    assert result.exit_code == 0, result.output
    assert "UNRESOLVED" in result.output


def test_explain_debt_works_without_candidate_audit_csv(tmp_path, monkeypatch):
    root, manifest, ledger = _write_explain_fixture(
        tmp_path, debt=None, ledger_record=True, include_audit_csv=False)
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["panel", "explain-debt", "--firm", "acme",
        "--quarter", "2024-03-31", "--manifest", str(manifest),
        "--ledger", str(ledger), "--root", str(root)])
    assert result.exit_code == 0, result.output
    assert "ZERO_SUPPORTED_BY_FILINGS" in result.output
