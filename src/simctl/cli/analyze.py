"""CLI commands for analysis: summarize and collect."""

from __future__ import annotations

import csv
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import typer

from simctl.adapters.registry import get as get_adapter
from simctl.core.discovery import discover_runs, resolve_run
from simctl.core.exceptions import SimctlError
from simctl.core.manifest import ManifestData, read_manifest
from simctl.core.project import find_project_root


def _find_summarize_script(
    manifest: ManifestData,
    run_dir: Path,
) -> Path | None:
    """Discover a project-level summarize.py script.

    Search order:
      1. cases/<case>/summarize.py  (case-specific)
      2. scripts/summarize.py       (project-wide)

    Returns:
        Path to the script, or None if not found.
    """
    try:
        project_root = find_project_root(run_dir)
    except SimctlError:
        return None

    # 1. Case-specific script
    case_name = (
        manifest.origin.get("case")
        or manifest.run.get("case")
        or manifest.origin.get("base_case")
    )
    if case_name:
        case_script = project_root / "cases" / str(case_name) / "summarize.py"
        if case_script.is_file():
            return case_script

    # 2. Project-wide script
    project_script = project_root / "scripts" / "summarize.py"
    if project_script.is_file():
        return project_script

    return None


def _run_summarize_script(
    script_path: Path,
    run_dir: Path,
    base_summary: dict[str, Any],
) -> dict[str, Any]:
    """Load and execute a summarize.py script.

    The script must define a ``summarize(run_dir, base_summary)`` function
    that returns the updated summary dict.

    Args:
        script_path: Path to the summarize.py file.
        run_dir: The run directory.
        base_summary: Summary dict from the adapter.

    Returns:
        Updated summary dict.

    Raises:
        RuntimeError: If the script has no ``summarize`` function or it fails.
    """
    spec = importlib.util.spec_from_file_location("_project_summarize", script_path)
    if spec is None or spec.loader is None:
        msg = f"Could not load script: {script_path}"
        raise RuntimeError(msg)

    module = importlib.util.module_from_spec(spec)
    # Add the script's parent to sys.path so it can do relative imports
    script_parent = str(script_path.parent)
    path_added = script_parent not in sys.path
    if path_added:
        sys.path.insert(0, script_parent)
    try:
        spec.loader.exec_module(module)
    finally:
        if path_added and script_parent in sys.path:
            sys.path.remove(script_parent)

    fn = getattr(module, "summarize", None)
    if fn is None:
        msg = f"Script {script_path} has no 'summarize' function"
        raise RuntimeError(msg)

    return fn(run_dir, base_summary)  # type: ignore[no-any-return]


def summarize(
    run: str = typer.Argument(None, help="Run directory or run_id (defaults to cwd)."),
) -> None:
    """Generate or update analysis/summary.json for a run."""
    if run is None:
        cwd = Path.cwd().resolve()
        if (cwd / "manifest.toml").exists():
            run_dir = cwd
        else:
            typer.echo("Error: No manifest.toml in cwd. Specify a run.", err=True)
            raise typer.Exit(code=1)
    else:
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

    # Run project-level summarize script if found
    script_path = _find_summarize_script(manifest, run_dir)
    if script_path is not None:
        try:
            summary = _run_summarize_script(script_path, run_dir, summary)
            typer.echo(f"  Applied script: {script_path.name}")
        except Exception as e:
            typer.echo(f"Warning: summarize script failed: {e}", err=True)

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
    survey_dir: Path = typer.Argument(None, help="Survey directory (defaults to cwd)."),
) -> None:
    """Collect summaries from all runs in a survey into a CSV."""
    if survey_dir is None:
        survey_dir = Path.cwd()
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
