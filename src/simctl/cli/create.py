"""CLI commands for run and survey creation."""

from __future__ import annotations

from pathlib import Path

import typer


def create(
    case_name: str = typer.Argument(..., help="Name of the case to create a run from."),
    dest: Path = typer.Option(..., "--dest", help="Destination survey directory."),
) -> None:
    """Create a single run from a case definition."""
    raise NotImplementedError("simctl create is not yet implemented.")


def sweep(
    survey_dir: Path = typer.Argument(..., help="Directory containing survey.toml."),
) -> None:
    """Generate all runs from a survey.toml parameter sweep."""
    raise NotImplementedError("simctl sweep is not yet implemented.")
