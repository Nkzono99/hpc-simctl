"""CLI commands for project initialization and environment checks."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer


def init(
    path: Optional[Path] = typer.Argument(
        None, help="Directory to initialize as a simctl project."
    ),
) -> None:
    """Initialize a new simctl project (simproject.toml etc.)."""
    raise NotImplementedError("simctl init is not yet implemented.")


def doctor(
    path: Optional[Path] = typer.Argument(None, help="Project directory to check."),
) -> None:
    """Check the environment and project configuration for issues."""
    raise NotImplementedError("simctl doctor is not yet implemented.")
