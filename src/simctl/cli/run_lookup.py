"""Shared helpers for resolving run directories from CLI arguments."""

from __future__ import annotations

from pathlib import Path

import typer

from simctl.core.discovery import resolve_run
from simctl.core.exceptions import ProjectNotFoundError, RunNotFoundError, SimctlError
from simctl.core.project import find_project_root


def find_project_runs_dir(start: Path | None = None) -> Path:
    """Walk upward from ``start`` to find the project's ``runs/`` directory."""
    try:
        project_root = find_project_root((start or Path.cwd()).resolve())
    except ProjectNotFoundError as exc:
        typer.echo(f"Error: {exc}")
        raise typer.Exit(code=1) from None
    return project_root / "runs"


def resolve_project_run_dir(identifier: str, *, start: Path | None = None) -> Path:
    """Resolve a run identifier relative to the nearest enclosing project."""
    try:
        runs_dir = find_project_runs_dir(start)
        return resolve_run(identifier, runs_dir)
    except RunNotFoundError as e:
        typer.echo(f"Error: {e}")
        raise typer.Exit(code=1) from None


def resolve_run_or_cwd(run: str | None, *, search_dir: Path | None = None) -> Path:
    """Resolve a run argument or fall back to the current run directory."""
    cwd = (search_dir or Path.cwd()).resolve()
    if run is None:
        if (cwd / "manifest.toml").exists():
            return cwd
        typer.echo("Error: No manifest.toml in cwd. Specify a run.", err=True)
        raise typer.Exit(code=1)
    try:
        return resolve_run(run, cwd)
    except SimctlError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1) from None
