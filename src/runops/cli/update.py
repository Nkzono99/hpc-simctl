"""CLI command for upgrading simulator packages."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Annotated, Optional

import typer

from runops.core.exceptions import SimctlError
from runops.core.project import find_project_root, load_project


def _venv_python_from_dir(venv_dir: Path) -> Path | None:
    """Return the venv's Python interpreter, handling Windows layout and symlinks."""
    python_rel = "Scripts/python.exe" if sys.platform == "win32" else "bin/python"
    python_path = venv_dir / python_rel
    if python_path.exists():
        return python_path
    try:
        resolved = venv_dir.resolve()
    except OSError:
        return None
    if resolved != venv_dir:
        python_path = resolved / python_rel
        if python_path.exists():
            return python_path
    return None


def _find_venv_python() -> Path | None:
    """Locate the project's venv Python interpreter.

    Resolution order:
      1. Project root's ``.venv/bin/python`` (walked up from cwd).
      2. ``$VIRTUAL_ENV/bin/python`` if an activated venv is set.

    Both paths are tried with symlink resolution so projects accessed via
    symlinked paths still work.
    """
    candidates: list[Path] = []

    cwd = Path.cwd().resolve()
    try:
        root = find_project_root(cwd)
    except SimctlError:
        root = cwd
    candidates.append(root / ".venv")

    virtual_env = os.environ.get("VIRTUAL_ENV")
    if virtual_env:
        candidates.append(Path(virtual_env))

    seen: set[Path] = set()
    for venv_dir in candidates:
        try:
            key = venv_dir.resolve()
        except OSError:
            key = venv_dir
        if key in seen:
            continue
        seen.add(key)
        python_path = _venv_python_from_dir(venv_dir)
        if python_path is not None:
            return python_path

    return None


def _find_uv() -> str | None:
    """Return the uv executable path, or None if not on PATH."""
    return shutil.which("uv")


def _build_install_cmd(
    venv_python: Path,
    packages: list[str],
    *,
    upgrade: bool = True,
) -> tuple[list[str], str]:
    """Build an install command for the given venv Python.

    Prefers ``uv pip install`` (works on pip-less uv venvs) and falls back to
    ``python -m pip install`` when uv is not available.

    Returns:
        (command list, short label describing the approach used).
    """
    uv = _find_uv()
    if uv is not None:
        cmd = [uv, "pip", "install", "--python", str(venv_python)]
        if upgrade:
            cmd.append("--upgrade")
        cmd.extend(packages)
        return cmd, "uv pip"

    cmd = [str(venv_python), "-m", "pip", "install"]
    if upgrade:
        cmd.append("--upgrade")
    cmd.extend(packages)
    return cmd, "python -m pip"


def _collect_packages(simulator_names: list[str]) -> list[str]:
    """Collect pip packages for the given simulators."""
    import runops.adapters  # noqa: F401
    from runops.adapters.registry import get_global_registry

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
      runops update emses        # upgrade EMSES and its dependencies
      runops update              # upgrade all simulators in project
      runops update --dry-run    # show what would be upgraded
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

    venv_python = _find_venv_python()
    if venv_python is None:
        typer.echo(
            "No .venv found. Run 'runops init' first, activate an existing "
            "venv, or create one with 'uv venv'.",
            err=True,
        )
        raise typer.Exit(code=1)

    cmd, approach = _build_install_cmd(venv_python, packages, upgrade=True)
    typer.echo(
        f"Upgrading packages for: {', '.join(simulators)} "
        f"(via {approach}, target {venv_python})"
    )
    result = subprocess.run(cmd, text=True, check=False)

    if result.returncode == 0:
        typer.echo(f"Upgraded {len(packages)} packages.")
    else:
        if approach == "python -m pip":
            typer.echo(
                "\nHint: uv is not on PATH. Either install uv "
                "(https://astral.sh/uv) or ensure pip is installed in the "
                "venv (e.g. 'uv pip install --python .venv pip').",
                err=True,
            )
        typer.echo("Upgrade failed.", err=True)
        raise typer.Exit(code=1)
