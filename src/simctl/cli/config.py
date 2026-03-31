"""CLI commands for project configuration management."""

from __future__ import annotations

import io
import logging
import sys
from pathlib import Path
from typing import Annotated, Any, Optional

import typer

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

try:
    import tomli_w
except ImportError:
    tomli_w = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

config_app = typer.Typer(
    name="config",
    help="View and modify project configuration.",
    no_args_is_help=True,
)


def _find_project_dir(path: Path | None) -> Path:
    """Resolve and validate the project directory."""
    project_dir = (path or Path.cwd()).resolve()
    if not (project_dir / "simproject.toml").exists():
        typer.echo(f"Error: simproject.toml not found in {project_dir}")
        raise typer.Exit(code=1)
    return project_dir


def _load_toml(path: Path) -> dict[str, Any]:
    """Load a TOML file."""
    with open(path, "rb") as f:
        return tomllib.load(f)


def _write_toml(path: Path, data: dict[str, Any]) -> None:
    """Write a TOML file."""
    if tomli_w is None:
        msg = "tomli_w is required to write TOML files"
        raise RuntimeError(msg)
    with open(path, "wb") as f:
        tomli_w.dump(data, f)


def _toml_to_str(data: dict[str, Any]) -> str:
    """Serialize dict to TOML string."""
    if tomli_w is None:
        msg = "tomli_w is required to serialize TOML"
        raise RuntimeError(msg)
    buf = io.BytesIO()
    tomli_w.dump(data, buf)
    return buf.getvalue().decode("utf-8")


@config_app.command("show")
def show(
    path: Annotated[
        Optional[Path],
        typer.Option("--path", "-p", help="Project directory."),
    ] = None,
) -> None:
    """Display current project configuration."""
    project_dir = _find_project_dir(path)

    # simproject.toml
    typer.echo("=== simproject.toml ===")
    simproject = project_dir / "simproject.toml"
    typer.echo(simproject.read_text(encoding="utf-8"))

    # simulators.toml
    typer.echo("=== simulators.toml ===")
    simulators = project_dir / "simulators.toml"
    if simulators.exists():
        typer.echo(simulators.read_text(encoding="utf-8"))
    else:
        typer.echo("(not found)\n")

    # launchers.toml
    typer.echo("=== launchers.toml ===")
    launchers = project_dir / "launchers.toml"
    if launchers.exists():
        typer.echo(launchers.read_text(encoding="utf-8"))
    else:
        typer.echo("(not found)\n")


@config_app.command("add-simulator")
def add_simulator(
    simulator: Annotated[
        Optional[str],
        typer.Argument(help="Simulator name (e.g. emses, beach)."),
    ] = None,
    path: Annotated[
        Optional[Path],
        typer.Option("--path", "-p", help="Project directory."),
    ] = None,
) -> None:
    """Add a simulator to simulators.toml (interactive)."""
    import simctl.adapters  # noqa: F401
    from simctl.adapters.registry import get_global_registry

    project_dir = _find_project_dir(path)
    registry = get_global_registry()
    available = registry.list_adapters()

    # Select simulator
    if not simulator:
        typer.echo("\nAvailable simulators:")
        for i, name in enumerate(available, 1):
            typer.echo(f"  {i}. {name}")

        selection = typer.prompt("\nSelect simulator (number or name)")
        if selection.isdigit():
            idx = int(selection) - 1
            if 0 <= idx < len(available):
                simulator = available[idx]
            else:
                typer.echo("Invalid selection.")
                raise typer.Exit(code=1)
        else:
            simulator = selection

    if simulator not in available:
        typer.echo(
            f"Unknown simulator: '{simulator}'. Available: {', '.join(available)}"
        )
        raise typer.Exit(code=1)

    # Load existing config
    sim_path = project_dir / "simulators.toml"
    existing = _load_toml(sim_path) if sim_path.exists() else {"simulators": {}}

    if "simulators" not in existing:
        existing["simulators"] = {}

    if simulator in existing["simulators"] and not typer.confirm(
        f"'{simulator}' already exists. Overwrite?", default=False
    ):
        typer.echo("Cancelled.")
        raise typer.Exit()

    # Interactive config
    adapter_cls = registry.get(simulator)
    config = adapter_cls.interactive_config()

    existing["simulators"][simulator] = config
    _write_toml(sim_path, existing)

    typer.echo(f"\nAdded simulator '{simulator}' to simulators.toml:")
    typer.echo(_toml_to_str({"simulators": {simulator: config}}))


@config_app.command("add-launcher")
def add_launcher(
    path: Annotated[
        Optional[Path],
        typer.Option("--path", "-p", help="Project directory."),
    ] = None,
) -> None:
    """Add a launcher profile to launchers.toml (interactive)."""
    project_dir = _find_project_dir(path)

    typer.echo("\nAvailable launcher types:")
    typer.echo("  1. srun (Slurm)")
    typer.echo("  2. mpirun (OpenMPI)")
    typer.echo("  3. mpiexec (MPICH)")

    selection = typer.prompt("\nSelect launcher type (number or name)")
    launcher_map = {"1": "srun", "2": "mpirun", "3": "mpiexec"}
    launcher_type = launcher_map.get(selection.strip(), selection.strip())

    if launcher_type not in ("srun", "mpirun", "mpiexec"):
        typer.echo(f"Unknown launcher type: '{launcher_type}'")
        raise typer.Exit(code=1)

    launcher_name = typer.prompt("Launcher profile name", default="default")

    config: dict[str, Any] = {"type": launcher_type}

    extra_args = typer.prompt(
        f"Extra {launcher_type} arguments (Enter to skip)", default=""
    )
    if extra_args:
        config["args"] = extra_args

    # Load existing
    launcher_path = project_dir / "launchers.toml"
    if launcher_path.exists():
        existing = _load_toml(launcher_path)
    else:
        existing = {"launchers": {}}

    if "launchers" not in existing:
        existing["launchers"] = {}

    if launcher_name in existing["launchers"] and not typer.confirm(
        f"'{launcher_name}' already exists. Overwrite?", default=False
    ):
        typer.echo("Cancelled.")
        raise typer.Exit()

    existing["launchers"][launcher_name] = config
    _write_toml(launcher_path, existing)

    typer.echo(f"\nAdded launcher '{launcher_name}' to launchers.toml:")
    typer.echo(_toml_to_str({"launchers": {launcher_name: config}}))
