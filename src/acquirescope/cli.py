from __future__ import annotations

from pathlib import Path
from typing import Callable

import typer

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


@app.command()
def analyze(
    repo_path: Path = typer.Argument(..., exists=True, file_okay=False, help="Path to a local git repository"),
    output: Path = typer.Option(Path("dd-report.md"), "--output", "-o", help="Report output path"),
) -> None:
    """Run all due-diligence modules against REPO_PATH and write a markdown report."""
    ingest = RepoIngest(repo_path)
    results: list[ModuleResult] = []
    for name, analyze_fn in MODULES:
        try:
            results.append(analyze_fn(ingest))
        except Exception as exc:  # graceful degradation is a spec requirement
            results.append(ModuleResult(module=name, status="failed", error=str(exc)))
    output.write_text(render_markdown(repo_path.name, results), encoding="utf-8")
    typer.echo(f"Report written to {output}")


if __name__ == "__main__":
    app()
