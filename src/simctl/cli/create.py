"""CLI commands for run and survey creation."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Optional

import typer

from simctl.core.exceptions import SimctlError
from simctl.core.run_creation import (
    CreatedRunResult,
    create_case_run,
    create_survey_runs,
    load_project_from_path,
)


def _echo_warnings(result: CreatedRunResult, *, context: str = "") -> None:
    """Print non-fatal validation warnings emitted during run creation."""
    prefix = f"{context}: " if context else ""
    for warning in result.warnings:
        typer.echo(f"  Warning: {prefix}{warning}", err=True)


def create(
    case_name: Annotated[
        str,
        typer.Argument(
            help=(
                "Case name to create a run from, or 'survey' to expand "
                "survey.toml in the current directory."
            ),
        ),
    ],
    dest: Annotated[
        Optional[Path],
        typer.Option("--dest", "-d", help="Destination directory (defaults to cwd)."),
    ] = None,
) -> None:
    """Create run(s) in the current directory.

    Examples:
      cd runs/experiment && simctl runs create flat_surface
      cd runs/mag_scan   && simctl runs create survey
    """
    target_dir = (dest or Path.cwd()).resolve()

    if case_name == "survey":
        _create_survey(target_dir)
    else:
        _create_single(case_name, target_dir)


def _create_single(case_name: str, target_dir: Path) -> None:
    """Create a single run from a case template."""
    try:
        project = load_project_from_path(target_dir)
        result = create_case_run(
            project,
            case_name,
            dest_dir=target_dir,
        )
    except SimctlError as exc:
        typer.echo(f"Error creating run: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    _echo_warnings(result)
    typer.echo(f"Created run: {result.run_info.run_id}")
    typer.echo(f"  Path: {result.run_info.run_dir}")


def _create_survey(survey_dir: Path) -> None:
    """Expand survey.toml into multiple runs."""
    try:
        project = load_project_from_path(survey_dir)
        created_runs = create_survey_runs(project, survey_dir)
    except SimctlError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    if not created_runs:
        typer.echo("No parameter combinations to expand.")
        raise typer.Exit(code=0)

    for result in created_runs:
        _echo_warnings(result, context=result.run_info.display_name)

    typer.echo(f"Created {len(created_runs)} runs in {survey_dir}")
    for result in created_runs:
        run_info = result.run_info
        name_part = f" ({run_info.display_name})" if run_info.display_name else ""
        typer.echo(f"  {run_info.run_id}{name_part}")


def sweep(
    survey_dir: Annotated[
        Optional[Path],
        typer.Argument(help="Directory containing survey.toml (defaults to cwd)."),
    ] = None,
) -> None:
    """Generate all runs from a survey.toml parameter sweep."""
    target = (survey_dir or Path.cwd()).resolve()
    _create_survey(target)
