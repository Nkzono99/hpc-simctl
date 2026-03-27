"""CLI commands for status checking and Slurm state synchronization."""

from __future__ import annotations

import typer


def status(
    run: str = typer.Argument(..., help="Run directory or run_id to check."),
) -> None:
    """Show the current status of a run."""
    raise NotImplementedError("simctl status is not yet implemented.")


def sync(
    run: str = typer.Argument(..., help="Run directory or run_id to sync Slurm state."),
) -> None:
    """Synchronize Slurm job state into the run manifest."""
    raise NotImplementedError("simctl sync is not yet implemented.")
