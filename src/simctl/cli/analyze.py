"""CLI commands for analysis: summarize and collect."""

from __future__ import annotations

from pathlib import Path

import typer


def summarize(
    run: str = typer.Argument(..., help="Run directory or run_id to summarize."),
) -> None:
    """Generate or update analysis/summary.json for a run."""
    raise NotImplementedError("simctl summarize is not yet implemented.")


def collect(
    survey_dir: Path = typer.Argument(
        ..., help="Survey directory to collect summaries from."
    ),
) -> None:
    """Collect summaries from all runs in a survey into a CSV."""
    raise NotImplementedError("simctl collect is not yet implemented.")
