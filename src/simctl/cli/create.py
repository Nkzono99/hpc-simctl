"""CLI commands for run and survey creation."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Optional

import typer

from simctl.core.actions import ActionStatus, execute_action
from simctl.core.exceptions import SimctlError
from simctl.core.project import find_project_root


def _echo_warnings(warnings: list[str], *, context: str = "") -> None:
    """Print non-fatal validation warnings emitted during run creation."""
    prefix = f"{context}: " if context else ""
    for warning in warnings:
        typer.echo(f"  Warning: {prefix}{warning}", err=True)


def create(
    case_name: Annotated[
        str,
        typer.Argument(
            help="Case name to create a run from.",
        ),
    ],
    dest: Annotated[
        Optional[Path],
        typer.Option("--dest", "-d", help="Destination directory (defaults to cwd)."),
    ] = None,
) -> None:
    """Create a run in the current directory.

    Examples:
      cd runs/experiment && simctl runs create flat_surface
    """
    target_dir = (dest or Path.cwd()).resolve()

    if case_name == "survey" and (target_dir / "survey.toml").is_file():
        typer.echo(
            "Error: 'simctl runs create survey' has been removed. "
            "Use 'simctl runs sweep [DIR]' instead.",
            err=True,
        )
        raise typer.Exit(code=1)

    _create_single(case_name, target_dir)


def _create_single(case_name: str, target_dir: Path) -> None:
    """Create a single run from a case template."""
    try:
        project_root = find_project_root(target_dir)
        result = execute_action(
            "create_run",
            project_root=project_root,
            case_name=case_name,
            dest_dir=target_dir,
        )
    except SimctlError as exc:
        typer.echo(f"Error creating run: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    if result.status is not ActionStatus.SUCCESS:
        typer.echo(f"Error creating run: {result.message}", err=True)
        raise typer.Exit(code=1)

    _echo_warnings(list(result.data.get("warnings", [])))
    typer.echo(f"Created run: {result.data.get('run_id', '???')}")
    typer.echo(f"  Path: {result.data.get('run_dir', target_dir)}")


def _create_survey(survey_dir: Path) -> None:
    """Expand survey.toml into multiple runs."""
    try:
        project_root = find_project_root(survey_dir)
        result = execute_action(
            "create_survey",
            project_root=project_root,
            survey_dir=survey_dir,
        )
    except SimctlError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    if result.status is not ActionStatus.SUCCESS:
        typer.echo(f"Error: {result.message}", err=True)
        raise typer.Exit(code=1)

    created_runs = list(result.data.get("runs", []))
    if not created_runs:
        typer.echo("No parameter combinations to expand.")
        raise typer.Exit(code=0)

    for created_run in created_runs:
        _echo_warnings(
            list(created_run.get("warnings", [])),
            context=str(created_run.get("display_name", "")),
        )

    typer.echo(f"Created {len(created_runs)} runs in {survey_dir}")
    for created_run in created_runs:
        display_name = str(created_run.get("display_name", ""))
        name_part = f" ({display_name})" if display_name else ""
        typer.echo(f"  {created_run.get('run_id', '???')}{name_part}")


def sweep(
    survey_dir: Annotated[
        Optional[Path],
        typer.Argument(help="Directory containing survey.toml (defaults to cwd)."),
    ] = None,
) -> None:
    """Generate all runs from a survey.toml parameter sweep."""
    target = (survey_dir or Path.cwd()).resolve()
    _create_survey(target)
