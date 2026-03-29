"""CLI command for cloning and deriving runs."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Optional

import typer

from simctl.core.discovery import collect_existing_run_ids, resolve_run
from simctl.core.exceptions import SimctlError
from simctl.core.manifest import ManifestData, read_manifest, write_manifest
from simctl.core.run import next_run_id
from simctl.core.state import RunState


def clone(
    run: str = typer.Argument(None, help="Run directory or run_id (defaults to cwd)."),
    dest: Optional[Path] = typer.Option(
        None, "--dest", "-d", help="Destination directory (defaults to cwd)."
    ),
    set_params: Optional[list[str]] = typer.Option(
        None, "--set", help="Override parameters as key=value."
    ),
) -> None:
    """Clone a run, optionally modifying parameters."""
    if run is None:
        cwd = Path.cwd().resolve()
        if (cwd / "manifest.toml").exists():
            source_dir = cwd
        else:
            typer.echo("Error: No manifest.toml in cwd. Specify a run.", err=True)
            raise typer.Exit(code=1)
    else:
        search_dir = Path.cwd()
        try:
            source_dir = resolve_run(run, search_dir)
        except SimctlError as e:
            typer.echo(f"Error: {e}", err=True)
            raise typer.Exit(code=1) from None

    try:
        source_manifest = read_manifest(source_dir)
    except SimctlError as e:
        typer.echo(f"Error reading manifest: {e}", err=True)
        raise typer.Exit(code=1) from None

    # Determine destination parent directory
    dest_parent = dest or source_dir.parent

    # Generate new run_id, searching both cwd and dest for existing IDs
    try:
        existing_ids = collect_existing_run_ids(search_dir)
        if dest_parent != search_dir:
            existing_ids |= collect_existing_run_ids(dest_parent)
        new_run_id = next_run_id(existing_ids)
    except SimctlError as e:
        typer.echo(f"Error generating run_id: {e}", err=True)
        raise typer.Exit(code=1) from None

    new_run_dir = dest_parent / new_run_id

    try:
        # Create run directory structure
        new_run_dir.mkdir(parents=True)
        for subdir in ("input", "submit", "work", "analysis", "status"):
            (new_run_dir / subdir).mkdir(exist_ok=True)

        # Copy input files from source
        source_input = source_dir / "input"
        if source_input.is_dir():
            dest_input = new_run_dir / "input"
            # Remove the empty dir we just created, then copy tree
            dest_input.rmdir()
            shutil.copytree(source_input, dest_input)

        # Copy submit/ directory (including job.sh) from source
        source_submit = source_dir / "submit"
        if source_submit.is_dir():
            dest_submit = new_run_dir / "submit"
            dest_submit.rmdir()
            shutil.copytree(source_submit, dest_submit)

        # Build new manifest
        source_run_id = source_manifest.run.get("id", "")
        new_manifest = ManifestData.from_dict(source_manifest.to_dict())
        new_manifest.run["id"] = new_run_id
        new_manifest.run["status"] = RunState.CREATED.value
        new_manifest.run["display_name"] = f"clone of {source_run_id}"
        new_manifest.origin["parent_run"] = source_run_id

        # Apply parameter overrides
        if set_params:
            for param in set_params:
                if "=" not in param:
                    typer.echo(
                        f"Error: invalid --set format {param!r}, expected key=value",
                        err=True,
                    )
                    raise typer.Exit(code=1)
                key, value = param.split("=", 1)
                new_manifest.params_snapshot[key.strip()] = value.strip()

        write_manifest(new_run_dir, new_manifest)

    except SimctlError as e:
        typer.echo(f"Error creating clone: {e}", err=True)
        raise typer.Exit(code=1) from None
    except OSError as e:
        typer.echo(f"Error creating clone directory: {e}", err=True)
        raise typer.Exit(code=1) from None

    typer.echo(f"Cloned {source_run_id} -> {new_run_id}")
    typer.echo(f"  Path: {new_run_dir}")
