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
    filing_prices_by_slug: dict = {}
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
        # The headline multiple is formed when the revenue became public, not at
        # the quarter-end, so prices are needed on the filing dates too.
        filing_dates = sorted({f.revenue_filed for f in fundamentals
                               if f.revenue_filed is not None})
        series = crsp_prices.get(firm.ticker.upper())
        if series:
            prices_by_slug[firm.slug] = quarter_end_prices_from_series(series, quarter_ends)
            filing_prices_by_slug[firm.slug] = quarter_end_prices_from_series(
                series, filing_dates)
        else:
            prices_by_slug[firm.slug] = quarter_end_prices(firm.ticker, quarter_ends, cache)
            filing_prices_by_slug[firm.slug] = quarter_end_prices(
                firm.ticker, filing_dates, cache)
        kept.append(firm)
    panel = build_panel(kept, metrics_by_slug, fundamentals_by_slug, prices_by_slug,
                        filing_prices_by_slug)
    panel.to_csv(output, index=False)
    n_firms = panel["firm"].nunique() if len(panel) else 0
    typer.echo(f"Panel written to {output}: {len(panel)} firm-quarters across {n_firms} firms")


@panel_app.command()
def power(
    panel_csv: Path = typer.Argument(..., exists=True, dir_okay=False),
    outcome: str = typer.Option("log_ev_rev", "--outcome",
                                help="Dependent variable to compute power for"),
    replicates: int = typer.Option(400, "--replicates"),
    draws: int = typer.Option(499, "--draws", help="Bootstrap draws per replicate"),
    output: Path = typer.Option(None, "--output", "-o",
                                help="Optional CSV to write the power curve to"),
) -> None:
    """Simulate the power of the pre-specified bootstrap test and report the
    minimum detectable effect.

    A null is uninterpretable without this: it matters enormously whether the
    design could have detected a coefficient of 0.05 or only one of 1.5."""
    _require_panel_extra()
    import pandas as pd

    from git_due_diligence.panel.power import power_curve
    from git_due_diligence.panel.regress import add_calendar_period, drop_singletons

    index_col = "repo_health_index_z"
    controls = ["growth_yoy", "op_margin_ltm", "log_rev"]
    panel = add_calendar_period(pd.read_csv(panel_csv))
    data = panel.dropna(subset=[outcome, index_col, *controls])
    data, _ = drop_singletons(data)
    formula = (f"{outcome} ~ {index_col} + " + " + ".join(controls)
               + " + C(firm) + C(period)")

    result = power_curve(data, formula, index_col,
                         replicates=replicates, draws=draws)
    typer.echo(f"{result.n_observations} firm-quarters, {result.n_clusters} clusters, "
               f"sd({outcome}) = {result.outcome_sd:.3f}")
    for point in result.curve:
        typer.echo(f"  beta={point.effect:5.2f}  power={point.power:6.1%}")
    if result.mde is None:
        typer.echo(f"\nMDE: no tested effect reaches {result.target_power:.0%} power.")
    else:
        typer.echo(f"\nMinimum detectable effect at {result.target_power:.0%} power, "
                   f"alpha={result.alpha}: beta = {result.mde}")
        typer.echo(f"  i.e. a 1 SD move in the index must shift {outcome} by "
                   f"{result.mde} to be detectable at all.")
    if output:
        result.as_frame().to_csv(output, index=False)
        typer.echo(f"Wrote power curve to {output}")


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
    diagnostics = results.pop("diagnostics", {})
    dropped = diagnostics.get("h1_singletons_dropped", 0)
    if dropped:
        typer.echo(
            f"Dropped {dropped} singleton observation(s) per Correia (2015); "
            f"H1 estimated on {diagnostics.get('h1_observations')} firm-quarters "
            f"across {diagnostics.get('h1_firms')} firms.")
    for name, res in results.items():
        coefficient = res.params.get("repo_health_index_z")
        typer.echo(f"{name}: repo_health_index_z = {coefficient:+.4f}")

    bootstrap = diagnostics.get("bootstrap")
    if bootstrap is not None and len(bootstrap):
        typer.echo("\nWild cluster bootstrap (headline inference):")
        for row in bootstrap.itertuples():
            typer.echo(
                f"  {row.model:<8} beta={row.coefficient:+.4f} "
                f"t={row.t_observed:+.3f} p={row.p_value:.4f} "
                f"({row.replications} refits, {row.weights} weights)")
        typer.echo(
            f"  NOTE: {int(bootstrap['n_clusters'].min())}-"
            f"{int(bootstrap['n_clusters'].max())} clusters; lowest attainable "
            f"p-value {bootstrap['min_attainable_p'].max():.4f}. Asymptotic "
            f"cluster-robust SEs in the tables are unreliable at this cluster "
            f"count and are reported only for comparison.")
    typer.echo(f"\nWrote {len(results)} summary tables to {output_dir}")
