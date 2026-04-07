"""CLI command for the multi-run dashboard view."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Annotated, Optional

import typer

from simctl.cli.run_lookup import resolve_run_targets
from simctl.core.exceptions import SimctlError
from simctl.core.manifest import read_manifest


def dashboard(
    targets: Annotated[
        Optional[list[str]],
        typer.Argument(
            help=(
                "Run identifiers, run directories, or directories containing "
                "runs (recursive).  Defaults to cwd / project runs/."
            ),
        ),
    ] = None,
    watch: Annotated[
        Optional[float],
        typer.Option(
            "--watch",
            "-w",
            help=(
                "Refresh the dashboard every N seconds (clears screen between "
                "refreshes).  Press Ctrl-C to stop."
            ),
        ),
    ] = None,
    all_states: Annotated[
        bool,
        typer.Option(
            "--all",
            "-a",
            help="Show all runs, not just the ones in submitted/running state.",
        ),
    ] = False,
) -> None:
    """Multi-run progress dashboard.

    Aggregates per-run progress (state, step, %, last diagnostic) into a
    single table.  Useful while a survey of dozens of runs is in flight:
    instead of opening ``simctl runs log`` for each run individually,
    one ``simctl runs dashboard`` call shows the whole survey.

    Examples:
      simctl runs dashboard runs/series_A          # one survey
      simctl runs dashboard -w 30 runs/series_A    # auto-refresh every 30 s
      simctl runs dashboard --all runs/            # whole project, including
                                                    # completed/failed runs
    """
    cwd = Path.cwd().resolve()
    run_dirs = resolve_run_targets(targets, search_dir=cwd)

    if watch is not None and watch > 0:
        _watch_loop(run_dirs, all_states=all_states, interval=watch)
    else:
        _print_dashboard(run_dirs, all_states=all_states)


def _print_dashboard(run_dirs: list[Path], *, all_states: bool) -> None:
    """Render the dashboard table once."""
    if not run_dirs:
        typer.echo("No runs found.")
        return

    active_states = {"submitted", "running"}
    rows: list[tuple[str, str, str, str, str, str]] = []

    for run_dir in run_dirs:
        try:
            manifest = read_manifest(run_dir)
        except SimctlError:
            continue

        status = str(manifest.run.get("status", "unknown"))
        if not all_states and status not in active_states:
            continue

        run_id = str(manifest.run.get("id", run_dir.name))
        display_name = str(manifest.run.get("display_name", ""))

        step_str, pct_str = _progress_for_run(run_dir, manifest.simulator)

        # Show the latest known Slurm state if recorded.
        last_slurm = str(manifest.run.get("last_slurm_state", "")) or "-"

        rows.append((run_id, display_name, status, step_str, pct_str, last_slurm))

    if not rows:
        typer.echo("No active runs found.")
        return

    # Sort by run_id for stable output.
    rows.sort(key=lambda r: r[0])

    headers = ("RUN_ID", "NAME", "STATE", "STEP", "%", "SLURM")
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))

    fmt = "  ".join(f"{{:<{w}}}" for w in widths)
    typer.echo(fmt.format(*headers))
    typer.echo(fmt.format(*("-" * w for w in widths)))
    for row in rows:
        typer.echo(fmt.format(*row))

    n_active = sum(1 for r in rows if r[2] in active_states)
    typer.echo(f"\n{n_active} active, {len(rows)} total")


def _progress_for_run(
    run_dir: Path,
    simulator: dict[str, str],
) -> tuple[str, str]:
    """Best-effort progress lookup for a single run.

    Returns ``(step_str, pct_str)`` where each part is a short string
    suitable for table cells.  Returns ``("-", "-")`` when the adapter
    has no progress to report.
    """
    adapter_name = simulator.get("adapter", "") or simulator.get("name", "")
    if not adapter_name:
        return "-", "-"

    try:
        import simctl.adapters  # noqa: F401  (registers adapters)
        from simctl.adapters.registry import get as get_adapter

        adapter_cls = get_adapter(adapter_name)
        adapter = adapter_cls()
        summary = adapter.summarize(run_dir)
    except Exception:
        return "-", "-"

    last_step = summary.get("last_step")
    nstep = summary.get("nstep")
    if last_step is None or not nstep:
        return "-", "-"

    pct = float(last_step) / float(nstep) * 100
    return f"{int(last_step):d}/{int(nstep):d}", f"{pct:5.1f}%"


def _watch_loop(
    run_dirs: list[Path],
    *,
    all_states: bool,
    interval: float,
) -> None:
    """Refresh the dashboard every ``interval`` seconds.

    Stops cleanly on Ctrl-C.  Each refresh re-reads the manifests and
    re-runs the per-run progress lookup, so newly-submitted or newly-
    completed runs are picked up automatically.
    """
    from datetime import datetime

    try:
        while True:
            typer.echo("\x1b[2J\x1b[H", nl=False)
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            typer.echo(
                f"simctl runs dashboard (watch every {interval:g}s) — {timestamp}"
            )
            typer.echo("")
            _print_dashboard(run_dirs, all_states=all_states)
            time.sleep(interval)
    except KeyboardInterrupt:
        typer.echo("\nStopped.")
        raise typer.Exit(code=0) from None
