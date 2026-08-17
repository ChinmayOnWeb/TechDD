from __future__ import annotations

import hashlib
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


SOURCE_MARKER = "SOURCE_PANEL.txt"


def source_claim(panel_csv: Path) -> str:
    digest = hashlib.sha256(panel_csv.read_bytes()).hexdigest()
    return f"{panel_csv.name} sha256:{digest}\n"


def claim_output_dir(output_dir: Path, panel_csv: Path, force: bool = False) -> None:
    """Bind a results directory to the panel that produced it.

    The health index is standardized ACROSS the panel, so panel.csv and
    panel_7firm.csv are two different studies rather than two filters of one.
    Their result tables nonetheless have identical filenames, and both
    `regress` and `deals` default to the same `panel_results` directory. That
    makes it a one-omitted-flag mistake to overwrite the primary arm's numbers
    with the robustness arm's -- silently, with nothing in the output to say
    which arm you are now looking at. Recording the source panel turns that
    into an error, and leaves provenance behind in the directory either way.
    """
    claim = source_claim(panel_csv)
    marker = output_dir / SOURCE_MARKER
    if marker.exists():
        held = marker.read_text(encoding="utf-8")
        if held != claim and not force:
            typer.echo(
                f"error: {output_dir}/ holds results built from {held.split()[0]}, "
                f"not {panel_csv.name}.\n"
                f"       These arms are separate studies -- the index is standardized "
                f"across whichever firms are in the panel.\n"
                f"       Write elsewhere with -o, or pass --force to overwrite.",
                err=True)
            raise typer.Exit(code=1)
    output_dir.mkdir(parents=True, exist_ok=True)
    marker.write_text(claim, encoding="utf-8")


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
    exclude: list[str] = typer.Option(None, "--exclude",
                                      help="Firm slug to drop from this build; repeatable. "
                                           "Needed because the health index is standardized "
                                           "ACROSS the panel, so a firm cannot be added or "
                                           "removed after the fact -- every other firm's "
                                           "z-score moves with it. Each arm of a robustness "
                                           "comparison therefore needs its own build."),
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
    dropped = {s.strip().lower() for s in (exclude or [])}
    unknown = dropped - {f.slug for f in firms}
    if unknown:
        typer.echo(f"error: --exclude names no firm in the universe: "
                   f"{', '.join(sorted(unknown))}", err=True)
        raise typer.Exit(code=1)
    if dropped:
        firms = [f for f in firms if f.slug not in dropped]
        typer.echo(f"Excluding {len(dropped)} firm(s): {', '.join(sorted(dropped))}")
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
def deals(
    panel_csv: Path = typer.Argument(..., exists=True, dir_okay=False),
    register: Path = typer.Option(Path("panel/deals.toml"), "--deals", exists=True,
                                 dir_okay=False, help="Deal register TOML"),
    crsp: Path = typer.Option(Path("panel_cache/prices_delisted.csv"), "--crsp",
                              exists=True, dir_okay=False),
    output_dir: Path = typer.Option(Path("panel_results"), "--output", "-o"),
    force: bool = typer.Option(False, "--force",
                               help="Overwrite results built from a different panel"),
) -> None:
    """Part B: does repo health predict which firms are acquired, and on what terms?

    Reports exact, distribution-free tests and their smallest attainable
    p-value. At five deals the floor is what limits the study, not the data, so
    it is printed before the result rather than after it."""
    _require_panel_extra()
    import pandas as pd

    from git_due_diligence.panel.crsp import load_crsp_prices
    from git_due_diligence.panel.deals import (build_risk_set, deal_terms, hazard_logit,
                                               hazard_permutation_p,
                                               last_observation_by_firm, load_deals,
                                               pre_announcement_health, separation_scan,
                                               spearman_exact)

    claim_output_dir(output_dir, panel_csv, force)
    panel = pd.read_csv(panel_csv)
    register_deals = load_deals(register)
    prices = {t: dict(series) for t, series in load_crsp_prices(crsp).items()}

    typer.echo(f"B2 -- deal terms ({len(register_deals)} deals)\n")
    rows = []
    for deal in register_deals:
        terms = deal_terms(deal, prices)
        health = pre_announcement_health(panel, deal)
        rows.append({
            "slug": deal.slug, "ticker": deal.ticker,
            "announced": deal.announced.isoformat(), "acquirer": deal.acquirer,
            "consideration": deal.consideration, "offer_value": terms.offer_value,
            "unaffected_close": terms.unaffected_close, "premium": terms.premium,
            "premium_30d": terms.premium_long,
            "premium_preleak": terms.premium_preleak,
            "announcement_return": terms.announcement_return,
            "repo_health_pre": health,
        })
        prem = "     n/a" if terms.premium is None else f"{terms.premium:+7.1%}"
        ann = "    n/a" if terms.announcement_return is None else f"{terms.announcement_return:+6.1%}"
        hstr = "  n/a " if health is None else f"{health:+5.2f}"
        typer.echo(f"  {deal.ticker:<5} {deal.announced.isoformat()} {deal.consideration:<5} "
                   f"premium={prem}  announce={ann}  health={hstr}")
    frame = pd.DataFrame(rows)
    output_dir.mkdir(parents=True, exist_ok=True)
    frame.to_csv(output_dir / "part_b_deals.csv", index=False)

    paired = frame.dropna(subset=["premium", "repo_health_pre"])
    if len(paired) >= 3:
        test = spearman_exact(list(paired["repo_health_pre"]), list(paired["premium"]))
        typer.echo(f"\n  Spearman(repo health, premium) = {test.statistic:+.3f}, "
                   f"exact p = {test.p_value:.3f} over {test.arrangements} permutations "
                   f"of n={test.n_events}")
        typer.echo(f"  Smallest attainable p at this n: {test.min_attainable_p:.3f}"
                   + ("" if test.can_reject_at_5pct
                      else "  -- ABOVE 0.05, so this test CANNOT reject at 5%."))

    typer.echo("\nB1 -- selection")
    risk = build_risk_set(panel, register_deals)
    exact = hazard_permutation_p(risk)
    typer.echo(f"  Risk set: {len(risk)} firm-quarters, {risk['firm'].nunique()} firms, "
               f"{exact.n_events} acquired, {exact.n_censored} still independent")
    typer.echo(f"  Mean pre-event repo health: acquired {exact.group_means[0]:+.3f} vs "
               f"never-acquired {exact.group_means[1]:+.3f}")
    typer.echo(f"  Exact rank-sum p = {exact.p_value:.3f} (statistic {exact.statistic:.1f}) "
               f"over {exact.arrangements} label assignments across firms")
    typer.echo(f"  Smallest attainable p: {exact.min_attainable_p:.3f}"
               + ("" if exact.can_reject_at_5pct
                  else "  -- ABOVE 0.05, so this test CANNOT reject at 5%."))
    scan = separation_scan(last_observation_by_firm(panel, register_deals),
                           set(risk.loc[risk["acquired"] == 1, "firm"]))
    if scan:
        typer.echo("\n  Does anything ELSE separate them? Same exact test, same firms:")
        for name, test, perfect in scan:
            flag = "  <- separates perfectly" if perfect else ""
            typer.echo(f"    {name:<22} exact p={test.p_value:.3f}{flag}")
        pd.DataFrame([
            {"variable": name, "rank_sum": test.statistic, "exact_p": test.p_value,
             "min_attainable_p": test.min_attainable_p, "separates_perfectly": int(perfect),
             "mean_acquired": test.group_means[0], "mean_independent": test.group_means[1]}
            for name, test, perfect in scan
        ]).to_csv(output_dir / "part_b_separation.csv", index=False)
        tied = [n for n, t, p in scan if p and n != "repo_health_index_z"]
        if tied and any(n == "repo_health_index_z" for n, _, p in scan if p):
            typer.echo(f"  WARNING: {len(tied)} other variable(s) separate the groups just as "
                       f"cleanly ({', '.join(tied)}).\n  At this many firms the test cannot "
                       "attribute the separation to repo health specifically.")

    try:
        fit, used = hazard_logit(risk)
        typer.echo(f"\n  Hazard logit (comparison only, {len(used)} firm-quarters, "
                   f"{int(used['announced_next'].sum())} events): "
                   f"beta={fit.params['repo_health_index_z']:+.3f} "
                   f"asymptotic p={fit.pvalues['repo_health_index_z']:.3f}")
        typer.echo("  NOTE: that p-value is not inference. It assumes independent "
                   "observations and many events; there are "
                   f"{int(used['announced_next'].sum())}. The exact test above is the result.")
        risk.to_csv(output_dir / "part_b_risk_set.csv", index=False)
    except Exception as exc:      # separation, singular Hessian: expected at this n
        typer.echo(f"\n  Hazard logit did not estimate: {type(exc).__name__}: {exc}")
        typer.echo("  That is the honest outcome of a logit with this many events.")
    typer.echo(f"\nWrote Part B tables to {output_dir}")


@panel_app.command()
def regress(
    panel_csv: Path = typer.Argument(..., exists=True, dir_okay=False),
    output_dir: Path = typer.Option(Path("panel_results"), "--output", "-o"),
    force: bool = typer.Option(False, "--force",
                               help="Overwrite results built from a different panel"),
) -> None:
    """Run the H1 (pricing) and H2 (predictive) regressions on a built panel."""
    _require_panel_extra()
    import pandas as pd

    from git_due_diligence.panel.regress import run_regressions

    claim_output_dir(output_dir, panel_csv, force)
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
