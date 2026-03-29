"""CLI commands for job submission."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Optional

import typer

from simctl.core.discovery import discover_runs, resolve_run
from simctl.core.exceptions import (
    InvalidStateTransitionError,
    ManifestNotFoundError,
    RunNotFoundError,
    SimctlError,
)
from simctl.core.manifest import read_manifest, update_manifest
from simctl.core.state import RunState, update_state
from simctl.slurm.submit import SlurmNotFoundError, SlurmSubmitError, sbatch_submit

logger = logging.getLogger(__name__)


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
    """Resolve a run identifier (path or run_id) to a run directory.

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


def _submit_single_run(
    run_dir: Path,
    *,
    quiet: bool = False,
    sbatch_extra: list[str] | None = None,
) -> str | None:
    """Submit a single run and return the job_id, or None on skip/error.

    Args:
        run_dir: Path to the run directory.
        quiet: If True, suppress per-run output (used in --all mode).

    Returns:
        The Slurm job ID string on success, or None if skipped or failed.

    Raises:
        typer.Exit: On fatal errors (only in single-run mode, not --all).
    """
    # Read manifest
    try:
        manifest = read_manifest(run_dir)
    except ManifestNotFoundError as e:
        typer.echo(f"Error: {e}")
        return None

    # Check current state
    current_status = manifest.run.get("status", "")
    if current_status != RunState.CREATED.value:
        msg = (
            f"Run {run_dir.name} is in state '{current_status}', "
            f"expected '{RunState.CREATED.value}'. Skipping."
        )
        typer.echo(msg)
        return None

    # Verify job script exists
    job_script = run_dir / "submit" / "job.sh"
    if not job_script.exists():
        typer.echo(f"Error: Job script not found: {job_script}")
        return None

    # Pre-flight: check input/ directory is not empty
    input_dir = run_dir / "input"
    if not input_dir.is_dir() or not any(input_dir.iterdir()):
        typer.echo(f"Error: input/ directory is empty or missing in {run_dir}")
        return None

    # Pre-flight: check job.sh contains SBATCH directives
    job_content = job_script.read_text()
    if "#SBATCH" not in job_content:
        typer.echo("Error: job.sh does not contain expected #SBATCH directives")
        return None

    # Pre-flight: if production tag, warn if git is dirty
    tags = manifest.classification.get("tags", [])
    if "production" in tags:
        sim_source = manifest.simulator_source
        if sim_source.get("git_dirty", False):
            typer.echo(
                "Warning: production run submitted with dirty git working tree"
            )

    # Determine working directory
    work_dir = run_dir / "work"
    if not work_dir.is_dir():
        work_dir = run_dir

    # Submit via sbatch
    try:
        job_id = sbatch_submit(job_script, work_dir, extra_args=sbatch_extra or None)
    except SlurmNotFoundError as e:
        typer.echo(f"Error: {e}")
        return None
    except SlurmSubmitError as e:
        typer.echo(f"Error: sbatch failed for {run_dir.name}: {e}")
        return None

    # Record job_id and submitted_at in manifest
    try:
        submitted_at = datetime.now(tz=timezone.utc).isoformat()
        update_manifest(
            run_dir, {"job": {"job_id": job_id, "submitted_at": submitted_at}}
        )
    except SimctlError as e:
        typer.echo(f"Error: Failed to update manifest: {e}")
        return None

    # Transition state to submitted
    try:
        update_state(run_dir, RunState.SUBMITTED)
    except InvalidStateTransitionError as e:
        typer.echo(f"Error: State transition failed: {e}")
        return None

    if not quiet:
        run_id = manifest.run.get("id", run_dir.name)
        typer.echo(f"Submitted {run_id}: job_id={job_id}")

    return job_id


def run_cmd(
    run: Annotated[
        Optional[str],
        typer.Argument(help="Run directory or run_id (defaults to cwd)."),
    ] = None,
    all_runs: Annotated[
        bool,
        typer.Option("--all", help="Submit all created runs in current directory."),
    ] = False,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Show what would be submitted."),
    ] = False,
    queue_name: Annotated[
        Optional[str],
        typer.Option("-qn", "--queue-name", help="Override partition/queue name."),
    ] = None,
) -> None:
    """Submit a run or all runs via sbatch.

    Examples:
      cd runs/experiment/R0001 && simctl run
      cd runs/mag_scan && simctl run --all
      simctl run -qn gr10451a
    """
    sbatch_extra: list[str] = []
    if queue_name:
        sbatch_extra.append(f"--partition={queue_name}")

    if all_runs:
        target = Path(run) if run else None
        _submit_all_cwd(target, dry_run=dry_run, sbatch_extra=sbatch_extra)
    elif run is None:
        _submit_single_cwd(dry_run=dry_run, sbatch_extra=sbatch_extra)
    else:
        _submit_single(run, dry_run=dry_run, sbatch_extra=sbatch_extra)


def _submit_single_cwd(
    *,
    dry_run: bool = False,
    sbatch_extra: list[str] | None = None,
) -> None:
    """Submit the run in the current directory."""
    cwd = Path.cwd().resolve()
    # Check if cwd itself is a run (has manifest.toml)
    if (cwd / "manifest.toml").exists():
        run_dir = cwd
    else:
        # Try to find a single run in cwd
        run_dirs = discover_runs(cwd)
        if len(run_dirs) == 1:
            run_dir = run_dirs[0]
        elif len(run_dirs) > 1:
            typer.echo(
                f"Multiple runs found in {cwd}. "
                "Use 'simctl run --all' or specify a run."
            )
            raise typer.Exit(code=1)
        else:
            typer.echo(f"No run found in {cwd}")
            raise typer.Exit(code=1)

    if dry_run:
        job_script = run_dir / "submit" / "job.sh"
        typer.echo(f"Would submit: {run_dir}")
        typer.echo(f"  Job script: {job_script}")
        typer.echo(f"  Exists: {job_script.exists()}")
        return

    result = _submit_single_run(run_dir, sbatch_extra=sbatch_extra)
    if result is None:
        raise typer.Exit(code=1)


def _submit_all_cwd(
    target: Path | None,
    *,
    dry_run: bool = False,
    sbatch_extra: list[str] | None = None,
) -> None:
    """Submit all runs in the given directory or cwd."""
    target_dir = (target or Path.cwd()).resolve()
    _submit_all(None, target_dir, dry_run=dry_run, sbatch_extra=sbatch_extra)


def _submit_single(
    run_arg: str | None,
    *,
    dry_run: bool = False,
    sbatch_extra: list[str] | None = None,
) -> None:
    """Handle single-run submission."""
    if run_arg is None:
        typer.echo("Error: RUN argument is required (unless using --all).")
        raise typer.Exit(code=1)

    run_dir = _resolve_run_dir(run_arg)

    if dry_run:
        job_script = run_dir / "submit" / "job.sh"
        typer.echo(f"Would submit: {run_dir}")
        typer.echo(f"  Job script: {job_script}")
        typer.echo(f"  Exists: {job_script.exists()}")
        return

    result = _submit_single_run(run_dir, sbatch_extra=sbatch_extra)
    if result is None:
        raise typer.Exit(code=1)


def _submit_all(
    run_arg: str | None,
    survey_dir_opt: Path | None,
    *,
    dry_run: bool = False,
    sbatch_extra: list[str] | None = None,
) -> None:
    """Handle batch submission of all runs in a directory.

    Args:
        run_arg: Positional argument that may serve as the survey directory.
        survey_dir_opt: Explicit --survey-dir option.
        dry_run: If True, only show what would happen.
    """
    # Determine the target directory from arguments (fallback to cwd)
    target_dir: Path | None = None
    if survey_dir_opt is not None:
        target_dir = survey_dir_opt
    elif run_arg is not None:
        target_dir = Path(run_arg)
    else:
        target_dir = Path.cwd()

    if not target_dir.is_dir():
        typer.echo(f"Error: Directory not found: {target_dir}")
        raise typer.Exit(code=1)

    run_dirs = discover_runs(target_dir)
    if not run_dirs:
        typer.echo(f"No runs found under {target_dir}")
        return

    if dry_run:
        typer.echo(f"Found {len(run_dirs)} run(s) under {target_dir}")
        for rd in run_dirs:
            try:
                manifest = read_manifest(rd)
                status = manifest.run.get("status", "unknown")
                run_id = manifest.run.get("id", rd.name)
            except SimctlError:
                status = "error"
                run_id = rd.name
            would_submit = status == RunState.CREATED.value
            marker = " [would submit]" if would_submit else " [skip]"
            typer.echo(f"  {run_id} ({status}){marker}")
        return

    submitted = 0
    skipped = 0
    failed = 0

    for rd in run_dirs:
        try:
            manifest = read_manifest(rd)
        except ManifestNotFoundError:
            skipped += 1
            continue

        current_status = manifest.run.get("status", "")
        if current_status != RunState.CREATED.value:
            skipped += 1
            continue

        job_id = _submit_single_run(rd, quiet=True, sbatch_extra=sbatch_extra)
        if job_id is not None:
            run_id = manifest.run.get("id", rd.name)
            typer.echo(f"  Submitted {run_id}: job_id={job_id}")
            submitted += 1
        else:
            failed += 1

    typer.echo(
        f"\nSummary: {submitted} submitted, {skipped} skipped, {failed} failed "
        f"(total: {len(run_dirs)} runs)"
    )
    if failed > 0:
        raise typer.Exit(code=1)
