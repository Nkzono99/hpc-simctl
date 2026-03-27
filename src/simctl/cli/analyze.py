"""CLI commands for analysis: summarize and collect."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import typer

from simctl.adapters.registry import get as get_adapter
from simctl.core.discovery import discover_runs, resolve_run
from simctl.core.exceptions import SimctlError
from simctl.core.manifest import read_manifest


def summarize(
    run: str = typer.Argument(..., help="Run directory or run_id to summarize."),
) -> None:
    """Generate or update analysis/summary.json for a run."""
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

    simulator_name = manifest.simulator.get("adapter", "")
    if not simulator_name:
        simulator_name = manifest.simulator.get("name", "")
    if not simulator_name:
        typer.echo("Error: no simulator/adapter specified in manifest.", err=True)
        raise typer.Exit(code=1)

    try:
        adapter_cls = get_adapter(simulator_name)
    except KeyError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1) from None

    adapter = adapter_cls()

    try:
        summary = adapter.summarize(run_dir)
    except Exception as e:
        typer.echo(f"Error generating summary: {e}", err=True)
        raise typer.Exit(code=1) from None

    # Write to analysis/summary.json
    analysis_dir = run_dir / "analysis"
    analysis_dir.mkdir(parents=True, exist_ok=True)
    summary_path = analysis_dir / "summary.json"

    try:
        with open(summary_path, "w") as f:
            json.dump(summary, f, indent=2)
            f.write("\n")
    except OSError as e:
        typer.echo(f"Error writing summary: {e}", err=True)
        raise typer.Exit(code=1) from None

    run_id = manifest.run.get("id", "???")
    typer.echo(f"Summary written: {summary_path}")
    typer.echo(f"  Run: {run_id}")
    typer.echo(f"  Keys: {', '.join(sorted(summary.keys()))}")


def collect(
    survey_dir: Path = typer.Argument(
        ..., help="Survey directory to collect summaries from."
    ),
) -> None:
    """Collect summaries from all runs in a survey into a CSV."""
    if not survey_dir.is_dir():
        typer.echo(f"Error: directory not found: {survey_dir}", err=True)
        raise typer.Exit(code=1)

    try:
        run_dirs = discover_runs(survey_dir)
    except SimctlError as e:
        typer.echo(f"Error discovering runs: {e}", err=True)
        raise typer.Exit(code=1) from None

    if not run_dirs:
        typer.echo("No runs found in survey directory.")
        raise typer.Exit(code=1)

    # Load summaries
    all_summaries: list[dict[str, object]] = []
    missing_count = 0
    for run_dir in run_dirs:
        summary_path = run_dir / "analysis" / "summary.json"
        if not summary_path.exists():
            missing_count += 1
            continue

        try:
            manifest = read_manifest(run_dir)
            run_id = manifest.run.get("id", "???")
        except SimctlError:
            run_id = run_dir.name

        try:
            with open(summary_path) as f:
                summary: dict[str, object] = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            typer.echo(f"Warning: could not read {summary_path}: {e}", err=True)
            continue

        summary["run_id"] = run_id
        all_summaries.append(summary)

    if not all_summaries:
        typer.echo("No summaries found. Run 'simctl summarize' first.")
        raise typer.Exit(code=1)

    # Determine all columns (run_id first, then sorted)
    all_keys: set[str] = set()
    for s in all_summaries:
        all_keys.update(s.keys())
    all_keys.discard("run_id")
    columns = ["run_id", *sorted(all_keys)]

    # Write CSV
    summary_dir = survey_dir / "summary"
    summary_dir.mkdir(parents=True, exist_ok=True)
    csv_path = summary_dir / "survey_summary.csv"

    try:
        with open(csv_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
            writer.writeheader()
            for s in all_summaries:
                writer.writerow(s)
    except OSError as e:
        typer.echo(f"Error writing CSV: {e}", err=True)
        raise typer.Exit(code=1) from None

    typer.echo(f"Collected {len(all_summaries)} summaries -> {csv_path}")
    if missing_count > 0:
        typer.echo(f"  ({missing_count} runs missing summary.json)")
