"""CLI command for upgrading simulator packages."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Annotated, Optional

import typer

from simctl.core.exceptions import SimctlError
from simctl.core.project import find_project_root, load_project


def _find_venv_pip() -> str | None:
    """Find pip in the project's .venv."""
    cwd = Path.cwd().resolve()
    try:
        root = find_project_root(cwd)
    except SimctlError:
        root = cwd

    venv_pip = root / ".venv" / "bin" / "pip"
    if venv_pip.exists():
        return str(venv_pip)

    # Fallback: current interpreter's pip
    return None


def _collect_packages(simulator_names: list[str]) -> list[str]:
    """Collect pip packages for the given simulators."""
    from simctl.adapters.registry import get_global_registry

    import simctl.adapters  # noqa: F401

    registry = get_global_registry()
    seen: set[str] = set()
    packages: list[str] = []
    for sim_name in simulator_names:
        try:
            adapter_cls = registry.get(sim_name)
            for pkg in adapter_cls.pip_packages():
                if pkg not in seen:
                    seen.add(pkg)
                    packages.append(pkg)
        except KeyError:
            pass
    return packages


def _get_project_simulators() -> list[str]:
    """Read simulator names from the project's simulators.toml."""
    cwd = Path.cwd().resolve()
    try:
        root = find_project_root(cwd)
        project = load_project(root)
        return list(project.simulators.keys())
    except SimctlError:
        return []


def update(
    simulators: Annotated[
        Optional[list[str]],
        typer.Argument(help="Simulator names to upgrade (defaults to all in project)."),
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Show what would be upgraded."),
    ] = False,
) -> None:
    """Upgrade simulator packages in the project .venv.

    Examples:
      simctl update emses        # upgrade EMSES and its dependencies
      simctl update              # upgrade all simulators in project
      simctl update --dry-run    # show what would be upgraded
    """
    # Determine which simulators to update
    if not simulators:
        simulators = _get_project_simulators()
        if not simulators:
            typer.echo("No simulators found in project. Specify simulator names.")
            raise typer.Exit(code=1)

    packages = _collect_packages(simulators)
    if not packages:
        typer.echo(f"No packages to upgrade for: {', '.join(simulators)}")
        return

    if dry_run:
        typer.echo(f"Would upgrade for simulators: {', '.join(simulators)}")
        for pkg in packages:
            typer.echo(f"  {pkg}")
        return

    pip_exe = _find_venv_pip()
    if pip_exe is None:
        typer.echo(
            "No .venv found. Run 'simctl init' first or create .venv manually."
        )
        raise typer.Exit(code=1)

    typer.echo(f"Upgrading packages for: {', '.join(simulators)}")
    result = subprocess.run(
        [pip_exe, "install", "--upgrade", *packages],
        text=True,
        check=False,
    )

    if result.returncode == 0:
        typer.echo(f"Upgraded {len(packages)} packages.")
    else:
        typer.echo("Upgrade failed.")
        raise typer.Exit(code=1)
