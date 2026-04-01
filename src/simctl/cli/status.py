"""CLI commands for status checking and Slurm state synchronization."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Optional

import typer

from simctl.cli.run_lookup import resolve_project_run_dir, resolve_run_or_cwd
from simctl.core.actions import ActionStatus
from simctl.core.actions import sync_run as sync_run_action
from simctl.core.exceptions import (
    ManifestNotFoundError,
)
from simctl.core.manifest import read_manifest
from simctl.slurm.query import SlurmQueryError, query_job_status
from simctl.slurm.submit import SlurmNotFoundError


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
    cwd = Path.cwd()
    run_dir = (
        resolve_run_or_cwd(None, search_dir=cwd)
        if run is None
        else resolve_project_run_dir(run, start=cwd)
    )

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

    # Show failure reason if recorded
    failure_reason = manifest.run.get("failure_reason", "")
    if failure_reason:
        typer.echo(f"Reason: {failure_reason}")

    if job_id:
        typer.echo(f"Job ID: {job_id}")

        # Query Slurm for live status (best-effort)
        try:
            job_status = query_job_status(job_id)
            typer.echo(f"Slurm:  {job_status.slurm_state}")
            if job_status.failure_reason:
                typer.echo(f"Slurm reason: {job_status.failure_reason}")
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
    cwd = Path.cwd()
    run_dir = (
        resolve_run_or_cwd(None, search_dir=cwd)
        if run is None
        else resolve_project_run_dir(run, start=cwd)
    )

    result = sync_run_action(run_dir)
    if result.status is not ActionStatus.SUCCESS:
        typer.echo(f"Error: {result.message}")
        raise typer.Exit(code=1)

    run_id = str(result.data.get("run_id", run_dir.name))
    if result.state_before == result.state_after:
        typer.echo(f"{run_id}: state unchanged ({result.state_after})")
        return

    msg = f"{run_id}: {result.state_before} -> {result.state_after}"
    failure_reason = str(result.data.get("failure_reason", ""))
    if failure_reason:
        msg += f" (reason: {failure_reason})"
    typer.echo(msg)
