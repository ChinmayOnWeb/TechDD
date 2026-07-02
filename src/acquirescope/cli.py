from __future__ import annotations

from pathlib import Path
from typing import Callable

import typer

from acquirescope.bridge.adjustments import price_adjustments
from acquirescope.bridge.assumptions import load_assumptions
from acquirescope.bridge.valuation import (
    blended_pre_dd_ev_mid,
    comps_valuation,
    dcf_scenarios,
    dcf_valuation,
    sensitivity_grid,
)
from acquirescope.excel import write_model
from acquirescope.ingest import RepoIngest
from acquirescope.models import ModuleResult
from acquirescope.modules import bus_factor, hotspots, licenses
from acquirescope.report import render_markdown

app = typer.Typer(add_completion=False)

MODULES: list[tuple[str, Callable[[RepoIngest], ModuleResult]]] = [
    ("bus_factor", bus_factor.analyze),
    ("licenses", licenses.analyze),
    ("hotspots", hotspots.analyze),
]


def run_modules(ingest: RepoIngest) -> list[ModuleResult]:
    results: list[ModuleResult] = []
    for name, analyze_fn in MODULES:
        try:
            results.append(analyze_fn(ingest))
        except Exception as exc:  # graceful degradation is a spec requirement
            results.append(ModuleResult(module=name, status="failed", error=str(exc)))
    return results


@app.command()
def analyze(
    repo_path: Path = typer.Argument(..., exists=True, file_okay=False, help="Path to a local git repository"),
    output: Path = typer.Option(Path("dd-report.md"), "--output", "-o", help="Report output path"),
) -> None:
    """Run all due-diligence modules against REPO_PATH and write a markdown report."""
    results = run_modules(RepoIngest(repo_path))
    output.write_text(render_markdown(repo_path.name, results), encoding="utf-8")
    typer.echo(f"Report written to {output}")


@app.command()
def model(
    repo_path: Path = typer.Argument(..., exists=True, file_okay=False, help="Path to a local git repository"),
    assumptions_file: Path = typer.Option(..., "--assumptions", "-a", exists=True, dir_okay=False, help="Analyst assumptions TOML"),
    output: Path = typer.Option(Path("dd-model.xlsx"), "--output", "-o", help="Excel model output path"),
) -> None:
    """Run the engine, price the findings, and write the Excel valuation model."""
    try:
        assumptions = load_assumptions(assumptions_file)
    except ValueError as exc:
        typer.echo(f"Invalid assumptions: {exc}", err=True)
        raise typer.Exit(code=1)

    results = run_modules(RepoIngest(repo_path))
    comps = comps_valuation(assumptions)
    dcf = dcf_valuation(assumptions)
    pre_dd_ev_mid = blended_pre_dd_ev_mid(comps, dcf)
    adjustments = price_adjustments(results, assumptions, pre_dd_ev_mid)
    total_adjustment_mid = sum(adj.mid for adj in adjustments)
    grid = sensitivity_grid(assumptions, total_adjustment_mid)
    write_model(output, assumptions, adjustments, comps, dcf,
                dcf_scenarios(assumptions), grid)
    typer.echo(f"Model written to {output}")


if __name__ == "__main__":
    app()
