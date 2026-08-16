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
    crsp: Path = typer.Option(None, "--crsp", exists=True, dir_okay=False,
                              help="CRSP daily-stock CSV export; used in preference to Stooq "
                                   "for any ticker it covers (required for delisted firms)"),
) -> None:
    """Build the firm-quarter panel CSV from local clones + EDGAR + prices."""
    _require_panel_extra()
    from git_due_diligence.panel.assemble import build_panel
    from git_due_diligence.panel.crsp import load_crsp_prices
    from git_due_diligence.panel.edgar import fetch_fundamentals
    from git_due_diligence.panel.metrics_cache import load_or_compute_metrics
    from git_due_diligence.panel.prices import quarter_end_prices, quarter_end_prices_from_series
    from git_due_diligence.panel.universe import fiscal_quarter_ends, load_universe

    crsp_prices = load_crsp_prices(crsp) if crsp else {}
    if crsp_prices:
        typer.echo(f"CRSP: {len(crsp_prices)} tickers loaded from {crsp}")

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
        try:
            fundamentals = fetch_fundamentals(firm.cik, cache)
        except Exception as exc:
            # A firm whose fundamentals are unavailable is skipped like one
            # without a clone, rather than ending the run. EDGAR is unreachable
            # from some environments, so the cache is the normal source and a
            # missing entry must not cost every other firm its build.
            typer.echo(f"warning: no fundamentals for {firm.slug} "
                       f"(CIK {firm.cik}): {type(exc).__name__}; skipping", err=True)
            continue
        metrics_by_slug[firm.slug] = load_or_compute_metrics(
            firm.slug, clone, quarter_ends, cache)
        fundamentals_by_slug[firm.slug] = fundamentals
        series = crsp_prices.get(firm.ticker.upper())
        if series:
            prices_by_slug[firm.slug] = quarter_end_prices_from_series(series, quarter_ends)
        else:
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
