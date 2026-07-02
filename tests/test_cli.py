from pathlib import Path

from typer.testing import CliRunner

from acquirescope import cli

runner = CliRunner()


def test_analyze_writes_report(fixture_repo, tmp_path):
    out = tmp_path / "report.md"
    result = runner.invoke(cli.app, [str(fixture_repo), "--output", str(out)])
    assert result.exit_code == 0
    assert out.exists()
    md = out.read_text(encoding="utf-8")
    assert "# Technical Due Diligence Report:" in md


def test_module_crash_degrades_gracefully(fixture_repo, tmp_path, monkeypatch):
    def explode(ingest):
        raise RuntimeError("boom")

    monkeypatch.setattr(cli, "MODULES", [("hotspots", explode)] + [m for m in cli.MODULES if m[0] != "hotspots"])
    out = tmp_path / "report.md"
    result = runner.invoke(cli.app, [str(fixture_repo), "--output", str(out)])
    assert result.exit_code == 0
    md = out.read_text(encoding="utf-8")
    assert "Not assessed" in md
    assert "boom" in md
    # other modules still ran
    assert "Module: bus_factor" in md
