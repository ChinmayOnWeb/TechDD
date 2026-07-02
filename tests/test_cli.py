from pathlib import Path

from typer.testing import CliRunner

from acquirescope import cli

runner = CliRunner()


def test_analyze_writes_report(fixture_repo, tmp_path):
    out = tmp_path / "report.md"
    result = runner.invoke(cli.app, ["analyze", str(fixture_repo), "--output", str(out)])
    assert result.exit_code == 0
    assert out.exists()
    md = out.read_text(encoding="utf-8")
    assert "# Technical Due Diligence Report:" in md


def test_module_crash_degrades_gracefully(fixture_repo, tmp_path, monkeypatch):
    def explode(ingest):
        raise RuntimeError("boom")

    monkeypatch.setattr(cli, "MODULES", [("hotspots", explode)] + [m for m in cli.MODULES if m[0] != "hotspots"])
    out = tmp_path / "report.md"
    result = runner.invoke(cli.app, ["analyze", str(fixture_repo), "--output", str(out)])
    assert result.exit_code == 0
    md = out.read_text(encoding="utf-8")
    assert "Not assessed" in md
    assert "boom" in md
    # other modules still ran
    assert "Module: bus_factor" in md


def test_all_planted_issues_detected_end_to_end(fixture_repo, tmp_path):
    """Spec regression gate: every planted issue in the synthetic repo is found."""
    out = tmp_path / "e2e-report.md"
    result = runner.invoke(cli.app, ["analyze", str(fixture_repo), "--output", str(out)])
    assert result.exit_code == 0
    md = out.read_text(encoding="utf-8")

    # Planted issue 1: payments/ single-owner module
    assert "Single point of failure: payments/" in md
    # Planted issue 2: GPL dependency in requirements.txt
    assert "Copyleft dependency: mysqlclient" in md
    # Planted issue 3: churn+complexity hotspot
    assert "Tech-debt hotspot: core/engine.py" in md
    # Planted issue 4: departed key contributor
    assert "Departed key contributor: dave@example.com" in md
    # Confidence band present in metrics line
    assert "remediation_months_low" in md


def test_model_writes_workbook(fixture_repo, tmp_path):
    from openpyxl import load_workbook

    example = Path(__file__).parent.parent / "examples" / "assumptions.example.toml"
    out = tmp_path / "model.xlsx"
    result = runner.invoke(cli.app, [
        "model", str(fixture_repo), "--assumptions", str(example), "--output", str(out),
    ])
    assert result.exit_code == 0
    wb = load_workbook(out)
    assert "Valuation Summary" in wb.sheetnames


def test_model_invalid_assumptions_exits_1(fixture_repo, tmp_path):
    bad = tmp_path / "bad.toml"
    bad.write_text("[target]\nname = 'x'\n", encoding="utf-8")
    out = tmp_path / "model.xlsx"
    result = runner.invoke(cli.app, [
        "model", str(fixture_repo), "--assumptions", str(bad), "--output", str(out),
    ])
    assert result.exit_code == 1
    assert not out.exists()


def test_planted_issues_priced_in_model_end_to_end(fixture_repo, tmp_path):
    """Phase 2 regression gate: planted DD issues become priced line items."""
    from openpyxl import load_workbook

    example = Path(__file__).parent.parent / "examples" / "assumptions.example.toml"
    out = tmp_path / "e2e-model.xlsx"
    result = runner.invoke(cli.app, [
        "model", str(fixture_repo), "--assumptions", str(example), "--output", str(out),
    ])
    assert result.exit_code == 0
    wb = load_workbook(out)

    adj = wb["DD Adjustments"]
    # Row order fixed: 2 remediation, 3 retention, 4 license, 5 integration, 6 security
    assert adj["B2"].value > 0                        # remediation capex priced from hotspot
    assert adj["C3"].value == 600_000                 # exactly 2 key-person findings x 300k
    assert adj["C4"].value > 0                        # license discount priced
    assert "mysqlclient" in adj["G4"].value           # evidence reaches the workbook
    assert adj["E6"].value == "NOT ASSESSED"          # security honest about scope

    summary = wb["Valuation Summary"]
    # Formulas are not evaluated by openpyxl; recompute from stored values.
    pre_mid = (summary["C4"].value + summary["C5"].value) / 2
    total_mid = sum(adj.cell(row=r, column=3).value for r in range(2, 7))
    assert total_mid > 0
    assert pre_mid - total_mid < pre_mid              # post-DD EV strictly below pre-DD
