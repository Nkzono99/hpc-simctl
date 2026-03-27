"""CLI commands for run lifecycle management: archive and purge."""

from __future__ import annotations

import shutil
from pathlib import Path

import typer

from simctl.core.discovery import resolve_run
from simctl.core.exceptions import InvalidStateTransitionError, SimctlError
from simctl.core.manifest import read_manifest
from simctl.core.state import RunState, update_state


def _get_dir_size(dir_path: Path) -> int:
    """Calculate total size of files in a directory tree.

    Args:
        dir_path: Directory path.

    Returns:
        Total size in bytes.
    """
    if not dir_path.is_dir():
        return 0
    total = 0
    for f in dir_path.rglob("*"):
        if f.is_file():
            total += f.stat().st_size
    return total


def _format_size(size_bytes: int) -> str:
    """Format a byte count as a human-readable string.

    Args:
        size_bytes: Size in bytes.

    Returns:
        Formatted string like "1.5 MB".
    """
    value = float(size_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024:
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} PB"


def archive(
    run: str = typer.Argument(..., help="Run directory or run_id to archive."),
) -> None:
    """Archive a completed run."""
    search_dir = Path.cwd()

    try:
        run_dir = resolve_run(run, search_dir)
    except SimctlError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1) from None

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

    try:
        update_state(run_dir, RunState.ARCHIVED)
    except InvalidStateTransitionError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1) from None

    run_id = manifest.run.get("id", "???")
    typer.echo(f"Archived run {run_id}.")
    typer.echo(f"  Path: {run_dir}")


def purge_work(
    run: str = typer.Argument(
        ..., help="Run directory or run_id to purge work files from."
    ),
) -> None:
    """Remove unnecessary files from a run's work/ directory."""
    search_dir = Path.cwd()

    try:
        run_dir = resolve_run(run, search_dir)
    except SimctlError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1) from None

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
            shutil.rmtree(target_dir)

    try:
        update_state(run_dir, RunState.PURGED)
    except InvalidStateTransitionError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1) from None

    run_id = manifest.run.get("id", "???")
    typer.echo(f"Purged work files for run {run_id}.")
    typer.echo(f"  Freed: {_format_size(total_freed)}")
    typer.echo(f"  Path: {run_dir}")
