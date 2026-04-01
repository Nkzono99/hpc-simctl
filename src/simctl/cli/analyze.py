"""CLI commands for analysis: summarize, collect, and plot."""

from __future__ import annotations

import json
from pathlib import Path

import typer

from simctl.core.analysis import (
    collect_survey_summaries,
    generate_run_summary,
    load_survey_plot_table,
    render_survey_plot,
)
from simctl.core.discovery import resolve_run
from simctl.core.exceptions import SimctlError
from simctl.core.manifest import read_manifest


def summarize(
    run: str = typer.Argument(None, help="Run directory or run_id (defaults to cwd)."),
) -> None:
    """Generate or update analysis/summary.json for a run."""
    if run is None:
        cwd = Path.cwd().resolve()
        if (cwd / "manifest.toml").exists():
            run_dir = cwd
        else:
            typer.echo("Error: No manifest.toml in cwd. Specify a run.", err=True)
            raise typer.Exit(code=1)
    else:
        search_dir = Path.cwd()
        try:
            run_dir = resolve_run(run, search_dir)
        except SimctlError as e:
            typer.echo(f"Error: {e}", err=True)
            raise typer.Exit(code=1) from None

    try:
        result = generate_run_summary(run_dir)
        manifest = read_manifest(run_dir)
    except KeyError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1) from None
    except (OSError, TypeError, json.JSONDecodeError, SimctlError) as e:
        typer.echo(f"Error generating summary: {e}", err=True)
        raise typer.Exit(code=1) from None

    if result.script_path is not None:
        typer.echo(f"  Applied script: {result.script_path.name}")
    for warning in result.warnings:
        typer.echo(f"Warning: {warning}", err=True)

    run_id = manifest.run.get("id", "???")
    typer.echo(f"Summary written: {result.summary_path}")
    typer.echo(f"  Run: {run_id}")
    typer.echo(f"  Keys: {', '.join(sorted(result.summary.keys()))}")


def collect(
    survey_dir: Path = typer.Argument(None, help="Survey directory (defaults to cwd)."),
) -> None:
    """Collect summaries from all runs in a survey into aggregate artifacts."""
    if survey_dir is None:
        survey_dir = Path.cwd()
    if not survey_dir.is_dir():
        typer.echo(f"Error: directory not found: {survey_dir}", err=True)
        raise typer.Exit(code=1)

    try:
        result = collect_survey_summaries(survey_dir)
    except (OSError, TypeError, json.JSONDecodeError, SimctlError) as e:
        typer.echo(f"Error collecting summaries: {e}", err=True)
        raise typer.Exit(code=1) from None

    typer.echo(f"Collected {result.summaries_collected} summaries")
    typer.echo(f"  CSV: {result.csv_path}")
    typer.echo(f"  JSON: {result.json_path}")
    typer.echo(f"  Figures: {result.figures_path}")
    typer.echo(f"  Report: {result.report_path}")
    if result.generated_summaries > 0:
        typer.echo(
            "  Auto-summarized:"
            f" {result.generated_summaries} completed runs during collect"
        )
    if result.missing_summaries > 0:
        typer.echo(f"  ({result.missing_summaries} runs missing summary.json)")
    for warning in result.warnings:
        typer.echo(f"Warning: {warning}", err=True)


def plot(
    survey_dir: Path = typer.Argument(None, help="Survey directory (defaults to cwd)."),
    x: str | None = typer.Option(None, "--x", help="Column for the x-axis."),
    y: str | None = typer.Option(None, "--y", help="Column for the y-axis."),
    kind: str = typer.Option(
        "auto",
        "--kind",
        help="Plot kind: auto, line, scatter, or bar.",
    ),
    group_by: str = typer.Option(
        "",
        "--group",
        help="Optional column used to split data into multiple series.",
    ),
    title: str = typer.Option("", "--title", help="Optional plot title."),
    output: Path | None = typer.Option(
        None,
        "--output",
        "-o",
        help="Output image path (default: summary/plots/<y>_vs_<x>.png).",
    ),
    list_columns: bool = typer.Option(
        False,
        "--list-columns",
        help="Print available plot columns and exit.",
    ),
) -> None:
    """Render a simple survey plot from collected summary data."""
    if survey_dir is None:
        survey_dir = Path.cwd()
    if not survey_dir.is_dir():
        typer.echo(f"Error: directory not found: {survey_dir}", err=True)
        raise typer.Exit(code=1)

    if list_columns:
        try:
            table = load_survey_plot_table(survey_dir)
        except (OSError, TypeError, json.JSONDecodeError, SimctlError) as e:
            typer.echo(f"Error loading plot columns: {e}", err=True)
            raise typer.Exit(code=1) from None

        typer.echo("Available columns:")
        for column in table.columns:
            typer.echo(f"  {column}")
        return

    if not x or not y:
        typer.echo(
            "Error: --x and --y are required unless --list-columns is used.",
            err=True,
        )
        raise typer.Exit(code=1)

    try:
        result = render_survey_plot(
            survey_dir,
            x=x,
            y=y,
            kind=kind,
            group_by=group_by,
            title=title,
            output_path=output,
        )
    except (OSError, TypeError, json.JSONDecodeError, SimctlError) as e:
        typer.echo(f"Error rendering plot: {e}", err=True)
        raise typer.Exit(code=1) from None

    typer.echo(f"Plot written: {result.output_path}")
    typer.echo(f"  Kind: {result.kind}")
    typer.echo(f"  Points: {result.points_plotted}")
    if result.generated_summaries > 0:
        typer.echo(
            "  Auto-summarized:"
            f" {result.generated_summaries} completed runs during plot"
        )
