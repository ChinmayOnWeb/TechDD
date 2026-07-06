from __future__ import annotations

import os
from pathlib import Path
from typing import Callable

import typer

from git_due_diligence.bridge.adjustments import price_adjustments
from git_due_diligence.bridge.assumptions import load_assumptions
from git_due_diligence.bridge.valuation import (
    blended_pre_dd_ev_mid,
    comps_valuation,
    dcf_scenarios,
    dcf_valuation,
    sensitivity_grid,
)
from git_due_diligence.dispositions import (
    Disposition,
    apply_dispositions,
    load_dispositions,
    merge_dispositions,
    save_dispositions,
)
from git_due_diligence.excel import write_model
from git_due_diligence.ingest import RepoIngest
from git_due_diligence.interview_questions import generate_questions
from git_due_diligence.models import Finding, ModuleResult
from git_due_diligence.modules import bus_factor, delivery, hotspots, licenses, security
from git_due_diligence.narrative import generate_narrative
from git_due_diligence.report import render_markdown

app = typer.Typer(add_completion=False)

MODULES: list[tuple[str, Callable[[RepoIngest], ModuleResult]]] = [
    ("bus_factor", bus_factor.analyze),
    ("licenses", licenses.analyze),
    ("hotspots", hotspots.analyze),
    ("security", security.analyze),
    ("delivery", delivery.analyze),
]


def run_modules(ingest: RepoIngest) -> list[ModuleResult]:
    results: list[ModuleResult] = []
    for name, analyze_fn in MODULES:
        try:
            results.append(analyze_fn(ingest))
        except Exception as exc:  # graceful degradation is a spec requirement
            results.append(ModuleResult(module=name, status="failed", error=str(exc)))
    return results


def _llm_unavailable_reason() -> str | None:
    try:
        import anthropic  # noqa: F401
    except ImportError:
        return "this feature requires the anthropic package: pip install git-due-diligence[llm]"
    if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
        return "this feature requires ANTHROPIC_API_KEY (or ANTHROPIC_AUTH_TOKEN) in the environment"
    return None


def _resolve_dispositions(
    path: Path | None, target_name: str, results: list[ModuleResult]
) -> tuple[list[ModuleResult], list[tuple[Finding, Disposition]]]:
    if path is None:
        return results, []
    existing = load_dispositions(path) if path.exists() else {}
    merged = merge_dispositions(results, existing)
    save_dispositions(path, target_name, merged)
    return apply_dispositions(results, merged)


def _anthropic_complete(prompt: str) -> str:
    import anthropic

    client = anthropic.Anthropic()
    response = client.messages.create(
        model="claude-opus-4-8",
        max_tokens=2048,
        messages=[{"role": "user", "content": prompt}],
    )
    return "".join(block.text for block in response.content if block.type == "text")


@app.command()
def analyze(
    repo_path: Path = typer.Argument(..., exists=True, file_okay=False, help="Path to a local git repository"),
    output: Path = typer.Option(Path("dd-report.md"), "--output", "-o", help="Report output path"),
    narrative: bool = typer.Option(False, "--narrative", help="Prepend an LLM-generated, citation-verified executive narrative (requires git-due-diligence[llm] and an Anthropic API key)"),
    questions: bool = typer.Option(False, "--questions", help="Generate an LLM-written 'question for management' per finding (requires git-due-diligence[llm] and an Anthropic API key)"),
    dispositions: Path = typer.Option(None, "--dispositions", help="Analyst disposition file (JSON) -- confirm/downgrade/dismiss findings; bootstrapped on first use"),
) -> None:
    """Run all due-diligence modules against REPO_PATH and write a markdown report."""
    if narrative or questions:
        reason = _llm_unavailable_reason()
        if reason:
            typer.echo(reason, err=True)
            raise typer.Exit(code=1)
    results = run_modules(RepoIngest(repo_path))
    try:
        results, dismissed = _resolve_dispositions(dispositions, repo_path.name, results)
    except ValueError as exc:
        typer.echo(f"Invalid dispositions file: {exc}", err=True)
        raise typer.Exit(code=1)
    narrative_text: str | None = None
    if narrative:
        try:
            narrative_text = generate_narrative(repo_path.name, results, _anthropic_complete)
        except Exception as exc:  # report must never be lost to a narrative failure
            typer.echo(f"Warning: narrative generation failed ({exc}); writing report without it.", err=True)
    questions_map: dict[str, str] = {}
    if questions:
        try:
            questions_map = generate_questions(repo_path.name, results, _anthropic_complete)
        except Exception as exc:  # report must never be lost to a question-generation failure
            typer.echo(f"Warning: question generation failed ({exc}); writing report without them.", err=True)
    output.write_text(
        render_markdown(repo_path.name, results, narrative_text, dismissed, questions_map),
        encoding="utf-8",
    )
    typer.echo(f"Report written to {output}")


@app.command()
def model(
    repo_path: Path = typer.Argument(..., exists=True, file_okay=False, help="Path to a local git repository"),
    assumptions_file: Path = typer.Option(..., "--assumptions", "-a", exists=True, dir_okay=False, help="Analyst assumptions TOML"),
    output: Path = typer.Option(Path("dd-model.xlsx"), "--output", "-o", help="Excel model output path"),
    dispositions: Path = typer.Option(None, "--dispositions", help="Analyst disposition file (JSON) -- confirm/downgrade/dismiss findings before pricing"),
) -> None:
    """Run the engine, price the findings, and write the Excel valuation model."""
    try:
        assumptions = load_assumptions(assumptions_file)
    except ValueError as exc:
        typer.echo(f"Invalid assumptions: {exc}", err=True)
        raise typer.Exit(code=1)

    results = run_modules(RepoIngest(repo_path))
    try:
        results, _dismissed = _resolve_dispositions(dispositions, repo_path.name, results)
    except ValueError as exc:
        typer.echo(f"Invalid dispositions file: {exc}", err=True)
        raise typer.Exit(code=1)
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
