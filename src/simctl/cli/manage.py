"""CLI commands for run lifecycle management: archive and purge."""

from __future__ import annotations

import typer


def archive(
    run: str = typer.Argument(..., help="Run directory or run_id to archive."),
) -> None:
    """Archive a completed run."""
    raise NotImplementedError("simctl archive is not yet implemented.")


def purge_work(
    run: str = typer.Argument(
        ..., help="Run directory or run_id to purge work files from."
    ),
) -> None:
    """Remove unnecessary files from a run's work/ directory."""
    raise NotImplementedError("simctl purge-work is not yet implemented.")
