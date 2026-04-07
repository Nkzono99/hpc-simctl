"""CLI commands for status checking and Slurm state synchronization."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Optional

import typer

from simctl.cli.run_lookup import resolve_run_targets
from simctl.core.actions import ActionStatus
from simctl.core.actions import sync_run as sync_run_action
from simctl.core.exceptions import (
    ManifestNotFoundError,
)
from simctl.core.manifest import read_manifest
from simctl.slurm.query import SlurmQueryError, query_job_status
from simctl.slurm.submit import SlurmNotFoundError


def status(
    runs: Annotated[
        Optional[list[str]],
        typer.Argument(
            help=(
                "Run identifiers or directories.  Each item may be a run_id, "
                "a run directory, or a directory containing runs (recursive). "
                "Defaults to cwd."
            )
        ),
    ] = None,
) -> None:
    """Show the current status of one or more runs.

    Displays the run state from manifest.toml. If a Slurm job_id is
    recorded, also queries Slurm for the live job state. Does NOT
    update the manifest (use ``simctl runs sync`` for that).

    Multi-target form: pass a survey directory (e.g. ``runs/series_A``)
    or several run_ids; status is printed for each.
    """
    targets = resolve_run_targets(runs, search_dir=Path.cwd())

    multi = len(targets) > 1
    for index, run_dir in enumerate(targets):
        if multi and index > 0:
            typer.echo("")
        _print_status_one(run_dir)


def _print_status_one(run_dir: Path) -> None:
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
    runs: Annotated[
        Optional[list[str]],
        typer.Argument(
            help=(
                "Run identifiers or directories.  Each item may be a run_id, "
                "a run directory, or a directory containing runs (recursive). "
                "Defaults to cwd."
            )
        ),
    ] = None,
) -> None:
    """Synchronize Slurm job state into one or more run manifests.

    Queries Slurm for the current job state of each target and updates
    both manifest.toml and status/state.json if the state has changed.

    When passed a survey directory (e.g. ``simctl runs sync runs/series_A``)
    every run found underneath is sync'd.  Runs whose manifest does not
    record a job_id (typical for ``created`` runs that haven't been
    submitted yet) are silently skipped so the bulk command remains useful
    on mixed-state surveys.
    """
    targets = resolve_run_targets(runs, search_dir=Path.cwd())
    multi = len(targets) > 1

    failures = 0
    for run_dir in targets:
        try:
            manifest = read_manifest(run_dir)
        except ManifestNotFoundError as e:
            typer.echo(f"Error: {e}", err=True)
            failures += 1
            continue

        # In multi-target / bulk mode, runs without a job_id are skipped
        # silently — they typically belong to ``created`` runs that haven't
        # been submitted yet, and we want bulk sync over a mixed-state
        # survey to remain useful.  In single-target mode the user is
        # explicitly asking about a specific run, so report the error.
        if not manifest.job.get("job_id", ""):
            if multi:
                continue
            run_id_str = manifest.run.get("id", run_dir.name)
            typer.echo(
                f"Error: {run_id_str}: no job_id recorded in manifest "
                "(was the run submitted?)",
                err=True,
            )
            raise typer.Exit(code=1)

        result = sync_run_action(run_dir)
        run_id = str(result.data.get("run_id", run_dir.name))
        if result.status is not ActionStatus.SUCCESS:
            typer.echo(f"{run_id}: error — {result.message}", err=True)
            failures += 1
            continue

        if result.state_before == result.state_after:
            typer.echo(f"{run_id}: state unchanged ({result.state_after})")
        else:
            msg = f"{run_id}: {result.state_before} -> {result.state_after}"
            failure_reason = str(result.data.get("failure_reason", ""))
            if failure_reason:
                msg += f" (reason: {failure_reason})"
            typer.echo(msg)

    if failures:
        raise typer.Exit(code=1)
