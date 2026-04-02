"""CLI commands for run lifecycle management: archive and purge."""

from __future__ import annotations

from pathlib import Path

import typer

from simctl.cli.run_lookup import resolve_run_or_cwd
from simctl.core.actions import ActionStatus
from simctl.core.actions import archive_run as archive_run_action
from simctl.core.actions import purge_work as purge_work_action
from simctl.core.exceptions import SimctlError
from simctl.core.manifest import read_manifest
from simctl.core.state import RunState


def _get_dir_size(dir_path: Path) -> int:
    """Calculate total size of files in a directory tree."""
    if not dir_path.is_dir():
        return 0
    total = 0
    for f in dir_path.rglob("*"):
        if f.is_file():
            total += f.stat().st_size
    return total


def _format_size(size_bytes: int) -> str:
    """Format a byte count as a human-readable string."""
    value = float(size_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024:
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} PB"


def archive(
    run: str = typer.Argument(None, help="Run directory or run_id (defaults to cwd)."),
    yes: bool = typer.Option(False, "--yes", help="Skip confirmation prompt."),
) -> None:
    """Archive a completed run."""
    run_dir = resolve_run_or_cwd(run, search_dir=Path.cwd())

    try:
        manifest = read_manifest(run_dir)
    except SimctlError as e:
        typer.echo(f"Error reading manifest: {e}", err=True)
        raise typer.Exit(code=1) from None

    current_status = manifest.run.get("status", "")
    if current_status != RunState.COMPLETED.value:
        typer.echo(
            f"Error: can only archive 'completed' runs, but run is '{current_status}'.",
            err=True,
        )
        raise typer.Exit(code=1)

    run_id = manifest.run.get("id", "???")
    if not yes and not typer.confirm(
        f"Archive run {run_id}? This changes the lifecycle state.",
        default=False,
    ):
        typer.echo("Cancelled.")
        raise typer.Exit()

    result = archive_run_action(run_dir)
    if result.status is not ActionStatus.SUCCESS:
        typer.echo(f"Error: {result.message}", err=True)
        raise typer.Exit(code=1)

    typer.echo(f"Archived run {run_id}.")
    typer.echo(f"  Path: {run_dir}")


def purge_work(
    run: str = typer.Argument(None, help="Run directory or run_id (defaults to cwd)."),
    yes: bool = typer.Option(False, "--yes", help="Skip confirmation prompt."),
) -> None:
    """Remove unnecessary files from a run's work/ directory."""
    run_dir = resolve_run_or_cwd(run, search_dir=Path.cwd())

    try:
        manifest = read_manifest(run_dir)
    except SimctlError as e:
        typer.echo(f"Error reading manifest: {e}", err=True)
        raise typer.Exit(code=1) from None

    current_status = manifest.run.get("status", "")
    if current_status != RunState.ARCHIVED.value:
        typer.echo(
            f"Error: can only purge 'archived' runs, but run is '{current_status}'.",
            err=True,
        )
        raise typer.Exit(code=1)

    # Calculate size of directories to remove
    work_dir = run_dir / "work"
    targets = ["outputs", "restart", "tmp"]
    total_freed = 0

    for dirname in targets:
        target_dir = work_dir / dirname
        if target_dir.is_dir():
            total_freed += _get_dir_size(target_dir)

    run_id = manifest.run.get("id", "???")
    if not yes and not typer.confirm(
        "Purge work files for "
        f"{run_id}? This will remove outputs/restart/tmp "
        f"(about {_format_size(total_freed)}).",
        default=False,
    ):
        typer.echo("Cancelled.")
        raise typer.Exit()

    result = purge_work_action(run_dir)
    if result.status is not ActionStatus.SUCCESS:
        typer.echo(f"Error: {result.message}", err=True)
        raise typer.Exit(code=1)

    typer.echo(f"Purged work files for run {run_id}.")
    typer.echo(f"  Freed: {_format_size(total_freed)}")
    typer.echo(f"  Path: {run_dir}")
