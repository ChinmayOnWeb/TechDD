from __future__ import annotations

from datetime import date
from datetime import datetime, timezone
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


@panel_app.command("validate-data")
def validate_data(
    manifest: Path = typer.Option(Path("panel/data_manifest.toml"), exists=True,
                                  dir_okay=False),
    root: Path = typer.Option(Path("."), exists=True, file_okay=False),
) -> None:
    """Validate required Part A artifacts and their provenance; fail closed."""
    from git_due_diligence.panel.recovery import (
        load_manifest,
        validate_runtime_artifacts,
        validation_succeeds,
    )

    try:
        findings = validate_runtime_artifacts(load_manifest(manifest), root)
    except (OSError, ValueError) as exc:
        typer.echo(f"manifest invalid: {exc}", err=True)
        raise typer.Exit(code=1)
    for finding in findings:
        typer.echo(f"{finding.status}\t{finding.artifact}\t{finding.detail}")
    if not validation_succeeds(findings):
        raise typer.Exit(code=1)


@panel_app.command("record-artifact")
def record_artifact(
    artifact: Path = typer.Argument(..., exists=True, dir_okay=False),
    artifact_type: str = typer.Option(...),
    identity: str = typer.Option(...),
    source: str = typer.Option(...),
    techdd_commit: str = typer.Option(None),
    source_repository_head: str = typer.Option(None),
    data_schema_version: str = typer.Option(None),
    ticker: list[str] = typer.Option(None, "--ticker"),
) -> None:
    """Create a SHA-256 provenance sidecar for a supplied raw artifact."""
    from git_due_diligence.panel.recovery import write_provenance

    sidecar = write_provenance(
        artifact,
        artifact_type=artifact_type,
        identity=identity,
        source=source,
        retrieved_or_built_at=datetime.now(timezone.utc),
        techdd_commit=techdd_commit,
        source_repository_head=source_repository_head,
        data_schema_version=data_schema_version,
        extra={"tickers": ticker} if ticker else None,
    )
    typer.echo(f"Provenance written to {sidecar}")


@panel_app.command("recover-metrics")
def recover_metrics(
    manifest: Path = typer.Option(Path("panel/data_manifest.toml"), exists=True,
                                  dir_okay=False),
    root: Path = typer.Option(Path("."), exists=True, file_okay=False),
    work_dir: Path = typer.Option(Path("panel_recovery_work")),
    build_end: datetime = typer.Option(..., formats=["%Y-%m-%d"]),
    firm: str = typer.Option(None, "--firm", help="Recover only this manifest firm slug"),
) -> None:
    """Regenerate full metrics by cloning and removing one canonical repo at a time."""
    import subprocess

    from git_due_diligence.panel.recovery import (
        load_manifest,
        recover_repository_metrics,
        select_manifest_firms,
    )

    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], check=True, capture_output=True, text=True,
    ).stdout.strip()
    try:
        firms = select_manifest_firms(load_manifest(manifest), firm)
        results = recover_repository_metrics(
            firms,
            work_dir=work_dir,
            artifact_root=root,
            techdd_commit=commit,
            build_end=build_end.date(),
        )
    except ValueError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1)
    for result in results:
        typer.echo(f"AVAILABLE\t{result['slug']}\tHEAD {result['head']}")


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
    debt_evidence_path: Path = typer.Option(
        Path("panel/debt_evidence.toml"), "--debt-evidence", exists=True,
        dir_okay=False, help="Reviewed filing-backed debt evidence ledger"),
) -> None:
    """Build the firm-quarter panel CSV from local clones + EDGAR + prices."""
    _require_panel_extra()
    from git_due_diligence.panel.assemble import build_panel
    from git_due_diligence.panel.crsp import load_crsp_prices
    from git_due_diligence.panel.edgar import fetch_fundamentals
    from git_due_diligence.panel.debt_evidence import (
        load_debt_evidence,
        load_firm_identities,
        merge_firm_identities,
    )
    from git_due_diligence.panel.metrics_cache import load_or_compute_metrics
    from git_due_diligence.panel.prices import quarter_end_prices, quarter_end_prices_from_series
    from git_due_diligence.panel.universe import fiscal_quarter_ends, load_universe

    crsp_prices = load_crsp_prices(crsp) if crsp else {}
    if crsp_prices:
        typer.echo(f"CRSP: {len(crsp_prices)} tickers loaded from {crsp}")

    firms = load_universe(universe)
    identities = {firm.slug: firm.cik for firm in firms}
    identity_path = debt_evidence_path.with_name("candidate_universe.csv")
    if identity_path.is_file():
        identities = merge_firm_identities(
            identities, load_firm_identities(identity_path))
    debt_evidence = load_debt_evidence(debt_evidence_path, identities)
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
        fundamentals_by_slug[firm.slug] = fetch_fundamentals(
            firm.cik, cache, firm_slug=firm.slug, debt_evidence=debt_evidence)
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


@panel_app.command("explain-debt")
def explain_debt(
    firm: str = typer.Option(..., "--firm"),
    quarter: datetime = typer.Option(..., "--quarter", formats=["%Y-%m-%d"]),
    manifest: Path = typer.Option(Path("panel/data_manifest.toml"), exists=True,
                                  dir_okay=False),
    ledger: Path = typer.Option(Path("panel/debt_evidence.toml"), exists=True,
                                dir_okay=False),
    root: Path = typer.Option(Path("."), exists=True, file_okay=False),
) -> None:
    """Explain the reported, filing-backed-zero, or unresolved debt source."""
    from git_due_diligence.panel.debt_evidence import (
        load_debt_evidence,
        load_firm_identities,
        merge_firm_identities,
    )
    from git_due_diligence.panel.edgar import fetch_fundamentals
    from git_due_diligence.panel.recovery import load_manifest, select_manifest_firms

    try:
        selected = select_manifest_firms(load_manifest(manifest), firm)[0]
        identities = {selected.slug: selected.cik}
        identity_path = root / "panel/candidate_universe.csv"
        if identity_path.is_file():
            identities = merge_firm_identities(
                identities, load_firm_identities(identity_path))
        evidence = load_debt_evidence(ledger, identities)
        rows = fetch_fundamentals(
            selected.cik,
            (root / selected.fundamentals_artifact).parent,
            firm_slug=selected.slug,
            debt_evidence=evidence,
        )
        target = quarter.date()
        row = next((item for item in rows if item.quarter_end == target), None)
    except (OSError, ValueError) as exc:
        typer.echo(f"debt evidence invalid: {exc}", err=True)
        raise typer.Exit(code=1)
    if row is None or row.debt is None:
        typer.echo(f"UNRESOLVED\t{firm}\t{target.isoformat()}\tno supported numeric debt fact or accepted zero assertion")
    elif row.debt_status == "ZERO_SUPPORTED_BY_FILINGS":
        typer.echo(
            f"ZERO_SUPPORTED_BY_FILINGS\t{firm}\t{target.isoformat()}\t"
            f"debt=0.0\taccession={row.debt_accession}")
    else:
        typer.echo(
            f"{row.debt_status}\t{firm}\t{target.isoformat()}\tdebt={row.debt}\t"
            f"concept={row.debt_concept}\taccession={row.debt_accession}")


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
