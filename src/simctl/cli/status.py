"""CLI commands for status checking and Slurm state synchronization."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Optional

import typer

from simctl.core.discovery import resolve_run
from simctl.core.exceptions import (
    InvalidStateTransitionError,
    ManifestNotFoundError,
    RunNotFoundError,
    SimctlError,
)
from simctl.core.manifest import read_manifest
from simctl.core.state import update_state
from simctl.slurm.query import SlurmQueryError, query_job_status
from simctl.slurm.submit import SlurmNotFoundError


def _find_project_runs_dir() -> Path:
    """Walk up from cwd to find a directory containing simproject.toml.

    Returns:
        The ``runs/`` directory under the project root.

    Raises:
        typer.Exit: If no project root is found.
    """
    cwd = Path.cwd()
    for parent in [cwd, *cwd.parents]:
        if (parent / "simproject.toml").exists():
            return parent / "runs"
    typer.echo("Error: Could not find simproject.toml in any parent directory.")
    raise typer.Exit(code=1)


def _resolve_run_dir(identifier: str) -> Path:
    """Resolve a run identifier to a directory path.

    Args:
        identifier: A run directory path or run_id string.

    Returns:
        Absolute path to the run directory.

    Raises:
        typer.Exit: If the run cannot be found.
    """
    try:
        runs_dir = _find_project_runs_dir()
        return resolve_run(identifier, runs_dir)
    except RunNotFoundError as e:
        typer.echo(f"Error: {e}")
        raise typer.Exit(code=1) from None


def status(
    run: Annotated[
        Optional[str],
        typer.Argument(help="Run directory or run_id (defaults to cwd)."),
    ] = None,
) -> None:
    """Show the current status of a run.

    Displays the run state from manifest.toml. If a Slurm job_id is
    recorded, also queries Slurm for the live job state. Does NOT
    update the manifest (use ``simctl sync`` for that).
    """
    if run is None:
        cwd = Path.cwd().resolve()
        if (cwd / "manifest.toml").exists():
            run_dir = cwd
        else:
            typer.echo("Error: No manifest.toml in cwd. Specify a run.")
            raise typer.Exit(code=1)
    else:
        run_dir = _resolve_run_dir(run)

    try:
        manifest = read_manifest(run_dir)
    except ManifestNotFoundError as e:
        typer.echo(f"Error: {e}")
        raise typer.Exit(code=1) from None

    run_id = manifest.run.get("id", run_dir.name)
    current_status = manifest.run.get("status", "unknown")
    job_id = manifest.job.get("job_id", "")

    typer.echo(f"Run:    {run_id}")
    typer.echo(f"Path:   {run_dir}")
    typer.echo(f"State:  {current_status}")

    if job_id:
        typer.echo(f"Job ID: {job_id}")

        # Query Slurm for live status (best-effort)
        try:
            slurm_state = query_job_status(job_id)
            typer.echo(f"Slurm:  {slurm_state.value}")
        except SlurmNotFoundError:
            typer.echo("Slurm:  (Slurm commands not available)")
        except SlurmQueryError as e:
            typer.echo(f"Slurm:  (query failed: {e})")
    else:
        typer.echo("Job ID: (not submitted)")


def sync(
    run: Annotated[
        Optional[str],
        typer.Argument(help="Run directory or run_id (defaults to cwd)."),
    ] = None,
) -> None:
    """Synchronize Slurm job state into the run manifest.

    Queries Slurm for the current job state and updates both
    manifest.toml and status/state.json if the state has changed.
    """
    if run is None:
        cwd = Path.cwd().resolve()
        if (cwd / "manifest.toml").exists():
            run_dir = cwd
        else:
            typer.echo("Error: No manifest.toml in cwd. Specify a run.")
            raise typer.Exit(code=1)
    else:
        run_dir = _resolve_run_dir(run)

    try:
        manifest = read_manifest(run_dir)
    except ManifestNotFoundError as e:
        typer.echo(f"Error: {e}")
        raise typer.Exit(code=1) from None

    run_id = manifest.run.get("id", run_dir.name)
    current_status = manifest.run.get("status", "unknown")
    job_id = manifest.job.get("job_id", "")

    if not job_id:
        typer.echo(f"Error: Run {run_id} has no job_id. Submit the run first.")
        raise typer.Exit(code=1)

    # Query Slurm
    try:
        slurm_state = query_job_status(job_id)
    except SlurmNotFoundError as e:
        typer.echo(f"Error: {e}")
        raise typer.Exit(code=1) from None
    except SlurmQueryError as e:
        typer.echo(f"Error: Slurm query failed for job {job_id}: {e}")
        raise typer.Exit(code=1) from None

    # Check if state actually changed
    if slurm_state.value == current_status:
        typer.echo(f"{run_id}: state unchanged ({current_status})")
        return

    # Attempt state transition
    try:
        update_state(run_dir, slurm_state)
    except InvalidStateTransitionError as e:
        typer.echo(
            f"Error: Cannot transition {run_id} from "
            f"'{current_status}' to '{slurm_state.value}': {e}"
        )
        raise typer.Exit(code=1) from None
    except SimctlError as e:
        typer.echo(f"Error: Failed to update state: {e}")
        raise typer.Exit(code=1) from None

    typer.echo(f"{run_id}: {current_status} -> {slurm_state.value}")
