from __future__ import annotations

from datetime import date
from pathlib import Path

import typer

panel_app = typer.Typer(
    add_completion=False,
    help="Firm-quarter panel: build the dataset, run the H1/H2 regressions",
)

_EXTRA_HINT = "panel commands require the panel extra: pip install git-due-diligence[panel]"


def _require_panel_extra() -> None:
    try:
        import pandas  # noqa: F401
        import statsmodels  # noqa: F401
    except ImportError:
        typer.echo(_EXTRA_HINT, err=True)
        raise typer.Exit(code=1)


@panel_app.command()
def build(
    universe: Path = typer.Option(..., "--universe", exists=True, file_okay=False,
                                  help="Directory of per-firm TOML configs"),
    clones: Path = typer.Option(..., "--clones", exists=True, file_okay=False,
                                help="Directory with one local clone per firm, named by slug"),
    output: Path = typer.Option(Path("panel.csv"), "--output", "-o"),
    cache: Path = typer.Option(Path("panel_cache"), "--cache",
                               help="Cache directory for EDGAR/price payloads (reused offline)"),
) -> None:
    """Build the firm-quarter panel CSV from local clones + EDGAR + prices."""
    _require_panel_extra()
    from git_due_diligence.panel.assemble import build_panel
    from git_due_diligence.panel.edgar import fetch_fundamentals
    from git_due_diligence.panel.metrics_cache import load_or_compute_metrics
    from git_due_diligence.panel.prices import quarter_end_prices
    from git_due_diligence.panel.universe import fiscal_quarter_ends, load_universe

    firms = load_universe(universe)
    metrics_by_slug: dict = {}
    fundamentals_by_slug: dict = {}
    prices_by_slug: dict = {}
    kept = []
    for firm in firms:
        clone = clones / firm.slug
        if not clone.exists():
            typer.echo(f"warning: no clone at {clone}; skipping {firm.slug}", err=True)
            continue
        quarter_ends = fiscal_quarter_ends(
            firm.fiscal_year_end_month, firm.listed_from, firm.listed_to or date.today())
        typer.echo(f"{firm.slug}: {len(quarter_ends)} fiscal quarters")
        metrics_by_slug[firm.slug] = load_or_compute_metrics(
            firm.slug, clone, quarter_ends, cache)
        fundamentals_by_slug[firm.slug] = fetch_fundamentals(firm.cik, cache)
        prices_by_slug[firm.slug] = quarter_end_prices(firm.ticker, quarter_ends, cache)
        kept.append(firm)
    panel = build_panel(kept, metrics_by_slug, fundamentals_by_slug, prices_by_slug)
    panel.to_csv(output, index=False)
    n_firms = panel["firm"].nunique() if len(panel) else 0
    typer.echo(f"Panel written to {output}: {len(panel)} firm-quarters across {n_firms} firms")


@panel_app.command()
def regress(
    panel_csv: Path = typer.Argument(..., exists=True, dir_okay=False),
    output_dir: Path = typer.Option(Path("panel_results"), "--output", "-o"),
) -> None:
    """Run the H1 (pricing) and H2 (predictive) regressions on a built panel."""
    _require_panel_extra()
    import pandas as pd

    from git_due_diligence.panel.regress import run_regressions

    panel = pd.read_csv(panel_csv)
    try:
        results = run_regressions(panel, output_dir)
    except ValueError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1)
    for name, res in results.items():
        coefficient = res.params.get("repo_health_index_z")
        typer.echo(f"{name}: repo_health_index_z = {coefficient:+.4f}")
    typer.echo(f"Wrote {len(results)} summary tables to {output_dir}")
