"""CLI commands for job submission."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer


def submit(
    run: Optional[str] = typer.Argument(
        None, help="Run directory or run_id to submit."
    ),
    all_runs: bool = typer.Option(
        False, "--all", help="Submit all runs in a survey directory."
    ),
    survey_dir: Optional[Path] = typer.Option(
        None, "--survey-dir", help="Survey directory (used with --all)."
    ),
) -> None:
    """Submit a run or all runs in a survey via sbatch."""
    raise NotImplementedError("simctl submit is not yet implemented.")
