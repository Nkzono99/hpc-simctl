"""CLI command for listing active jobs in the project."""

from __future__ import annotations

import contextlib
from pathlib import Path
from typing import Annotated, Optional

import typer

from simctl.core.discovery import discover_runs
from simctl.core.exceptions import SimctlError
from simctl.core.manifest import read_manifest
from simctl.core.project import find_project_root


def jobs(
    path: Annotated[
        Optional[Path],
        typer.Argument(help="Directory to search (defaults to cwd)."),
    ] = None,
    all_states: Annotated[
        bool,
        typer.Option("--all", "-a", help="Show all runs, not just active jobs."),
    ] = False,
) -> None:
    """List active (submitted/running) jobs in the project.

    Shows job_id, status, run_id, and path for runs with Slurm jobs.

    Examples:
      simctl runs jobs             # active jobs under cwd
      simctl runs jobs --all       # all runs with job info
    """
    search_dir = (path or Path.cwd()).resolve()

    # Try to find project root for broader search
    try:
        root = find_project_root(search_dir)
        runs_dir = root / "runs"
        if runs_dir.is_dir():
            search_dir = runs_dir
    except SimctlError:
        pass  # Use the given path

    try:
        run_dirs = discover_runs(search_dir)
    except SimctlError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1) from None

    if not run_dirs:
        typer.echo("No runs found.")
        return

    active_states = {"submitted", "running"}
    rows: list[tuple[str, str, str, str, str]] = []

    for run_dir in run_dirs:
        try:
            manifest = read_manifest(run_dir)
        except SimctlError:
            continue

        status = manifest.run.get("status", "unknown")
        if not all_states and status not in active_states:
            continue

        run_id = manifest.run.get("id", "???")
        job_id = manifest.job.get("job_id", "")
        submitted_at = manifest.job.get("submitted_at", "")
        # Shorten timestamp
        if submitted_at and "T" in submitted_at:
            submitted_at = submitted_at.split("T")[0]

        rel_path = str(run_dir)
        with contextlib.suppress(ValueError):
            rel_path = str(run_dir.relative_to(search_dir.parent))

        rows.append((job_id or "-", run_id, status, submitted_at, rel_path))

    rows.sort(key=lambda r: r[1])  # sort by run_id

    if not rows:
        typer.echo("No active jobs found.")
        return

    headers = ("JOB_ID", "RUN_ID", "STATUS", "SUBMITTED", "PATH")
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))

    fmt = "  ".join(f"{{:<{w}}}" for w in widths)
    typer.echo(fmt.format(*headers))
    typer.echo(fmt.format(*("-" * w for w in widths)))
    for row in rows:
        typer.echo(fmt.format(*row))

    # Summary
    active = sum(1 for r in rows if r[2] in active_states)
    typer.echo(f"\n{active} active, {len(rows)} total")
