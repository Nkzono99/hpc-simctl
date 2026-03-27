"""CLI command for listing runs."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer


def list_runs(
    path: Optional[Path] = typer.Argument(None, help="Directory to search for runs."),
    status_filter: Optional[str] = typer.Option(
        None, "--status", help="Filter by run status."
    ),
    tag: Optional[str] = typer.Option(None, "--tag", help="Filter by tag."),
) -> None:
    """List runs under the given path."""
    raise NotImplementedError("simctl list is not yet implemented.")
