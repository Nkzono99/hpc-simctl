"""CLI commands for analysis: summarize, collect, and plot."""

from __future__ import annotations

import json
from pathlib import Path

import typer

from runops.cli.run_lookup import resolve_run_or_cwd
from runops.core.actions import ActionStatus, execute_action
from runops.core.analysis import (
    list_survey_plot_recipes,
    load_survey_plot_table,
    render_survey_plot,
    resolve_survey_plot_recipe,
)
from runops.core.exceptions import SimctlError


def summarize(
    run: str = typer.Argument(None, help="Run directory or run_id (defaults to cwd)."),
) -> None:
    """Generate or update analysis/summary.json for a run."""
    run_dir = resolve_run_or_cwd(run, search_dir=Path.cwd())

    try:
        result = execute_action("summarize_run", run_dir=run_dir)
    except (OSError, TypeError, json.JSONDecodeError, SimctlError) as e:
        typer.echo(f"Error generating summary: {e}", err=True)
        raise typer.Exit(code=1) from None

    if result.status is not ActionStatus.SUCCESS:
        typer.echo(f"Error generating summary: {result.message}", err=True)
        raise typer.Exit(code=1)

    script_path = str(result.data.get("script_path", ""))
    if script_path:
        typer.echo(f"  Applied script: {Path(script_path).name}")
    for warning in result.data.get("warnings", []):
        typer.echo(f"Warning: {warning}", err=True)

    summary = result.data.get("summary", {})
    run_id = result.data.get("run_id", "???")
    typer.echo(f"Summary written: {result.data.get('summary_path', '')}")
    typer.echo(f"  Run: {run_id}")
    typer.echo(f"  Keys: {', '.join(sorted(summary.keys()))}")


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
        result = execute_action("collect_survey", survey_dir=survey_dir)
    except (OSError, TypeError, json.JSONDecodeError, SimctlError) as e:
        typer.echo(f"Error collecting summaries: {e}", err=True)
        raise typer.Exit(code=1) from None

    if result.status is not ActionStatus.SUCCESS:
        typer.echo(f"Error collecting summaries: {result.message}", err=True)
        raise typer.Exit(code=1)

    typer.echo(f"Collected {result.message.removeprefix('Collected ').strip()}")
    typer.echo(f"  CSV: {result.data.get('csv_path', '')}")
    typer.echo(f"  JSON: {result.data.get('json_path', '')}")
    typer.echo(f"  Figures: {result.data.get('figures_path', '')}")
    typer.echo(f"  Report: {result.data.get('report_path', '')}")
    generated_summaries = int(result.data.get("generated_summaries", 0))
    if generated_summaries > 0:
        typer.echo(
            f"  Auto-summarized: {generated_summaries} completed runs during collect"
        )
    missing_summaries = int(result.data.get("missing_summaries", 0))
    if missing_summaries > 0:
        typer.echo(f"  ({missing_summaries} runs missing summary.json)")
    for warning in result.data.get("warnings", []):
        typer.echo(f"Warning: {warning}", err=True)


def plot(
    survey_dir: Path = typer.Argument(None, help="Survey directory (defaults to cwd)."),
    x: str | None = typer.Option(None, "--x", help="Column for the x-axis."),
    y: str | None = typer.Option(None, "--y", help="Column for the y-axis."),
    recipe: str = typer.Option(
        "",
        "--recipe",
        help="Adapter-aware plot recipe name.",
    ),
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
    list_recipes: bool = typer.Option(
        False,
        "--list-recipes",
        help="Print available adapter plot recipes and exit.",
    ),
) -> None:
    """Render a survey plot from explicit columns or an adapter recipe."""
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

    if list_recipes:
        try:
            recipes = list_survey_plot_recipes(survey_dir)
        except (OSError, TypeError, json.JSONDecodeError, SimctlError) as e:
            typer.echo(f"Error loading plot recipes: {e}", err=True)
            raise typer.Exit(code=1) from None

        if not recipes:
            typer.echo("No adapter plot recipes available for this survey.")
            return

        typer.echo("Available plot recipes:")
        for item in recipes:
            x_candidates = ", ".join(item.x_candidates)
            y_candidates = ", ".join(item.y_candidates)
            group_candidates = (
                ", ".join(item.group_by_candidates)
                if item.group_by_candidates
                else "(none)"
            )
            typer.echo(f"  {item.name} [{item.adapter}]")
            if item.description:
                typer.echo(f"    {item.description}")
            typer.echo(f"    x: {x_candidates}")
            typer.echo(f"    y: {y_candidates}")
            typer.echo(f"    kind: {item.kind}")
            typer.echo(f"    group_by: {group_candidates}")
        return

    resolved_recipe = None
    if recipe:
        try:
            resolved_recipe = resolve_survey_plot_recipe(survey_dir, recipe)
        except (OSError, TypeError, json.JSONDecodeError, SimctlError) as e:
            typer.echo(f"Error resolving plot recipe: {e}", err=True)
            raise typer.Exit(code=1) from None

    if not x and resolved_recipe is not None:
        x = resolved_recipe.x
    if not y and resolved_recipe is not None:
        y = resolved_recipe.y
    if not group_by and resolved_recipe is not None:
        group_by = resolved_recipe.group_by
    if kind == "auto" and resolved_recipe is not None:
        kind = resolved_recipe.recipe.kind
    if not title and resolved_recipe is not None:
        title = resolved_recipe.recipe.title

    if not x or not y:
        typer.echo(
            "Error: --x and --y are required unless --recipe, --list-columns, "
            "or --list-recipes is used.",
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
    if resolved_recipe is not None:
        typer.echo(f"  Recipe: {resolved_recipe.recipe.name}")
    typer.echo(f"  Kind: {result.kind}")
    typer.echo(f"  Points: {result.points_plotted}")
    if result.generated_summaries > 0:
        typer.echo(
            "  Auto-summarized:"
            f" {result.generated_summaries} completed runs during plot"
        )
