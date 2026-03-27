"""CLI command for cloning and deriving runs."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer


def clone(
    run: str = typer.Argument(..., help="Run directory or run_id to clone."),
    dest: Optional[Path] = typer.Option(
        None, "--dest", help="Destination directory for the cloned run."
    ),
    set_params: Optional[list[str]] = typer.Option(
        None, "--set", help="Override parameters as key=value."
    ),
) -> None:
    """Clone a run, optionally modifying parameters."""
    raise NotImplementedError("simctl clone is not yet implemented.")
