"""CLI commands for project initialization and environment checks."""

from __future__ import annotations

import logging
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Annotated, Any, Optional

import typer

from simctl.core.discovery import validate_uniqueness
from simctl.core.exceptions import DuplicateRunIdError, ProjectConfigError
from simctl.core.project import load_project

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

try:
    import tomli_w
except ImportError:
    tomli_w = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

_SIMPROJECT_FILE = "simproject.toml"
_SIMULATORS_FILE = "simulators.toml"
_LAUNCHERS_FILE = "launchers.toml"

_GITIGNORE_CONTENT = """\
# heavy run outputs
runs/**/work/outputs/
runs/**/work/restart/
runs/**/work/tmp/

# logs
runs/**/work/*.out
runs/**/work/*.err
runs/**/work/*.log

# analysis cache
runs/**/analysis/cache/
runs/**/analysis/.ipynb_checkpoints/
"""


def _write_if_missing(path: Path, content: str) -> bool:
    """Write content to path if the file does not already exist.

    Args:
        path: File path to create.
        content: File content to write.

    Returns:
        True if the file was created, False if it already existed.
    """
    if path.exists():
        return False
    path.write_text(content, encoding="utf-8")
    return True


def _mkdir_if_missing(path: Path) -> bool:
    """Create a directory if it does not already exist.

    Args:
        path: Directory path to create.

    Returns:
        True if the directory was created, False if it already existed.
    """
    if path.exists():
        return False
    path.mkdir(parents=True)
    return True


def _build_simulators_toml(simulator_names: list[str]) -> str:
    """Build simulators.toml content from adapter default configs.

    Args:
        simulator_names: List of simulator adapter names (e.g. ["emses", "beach"]).

    Returns:
        TOML string for simulators.toml.

    Raises:
        typer.BadParameter: If a simulator name is not recognized.
    """
    from simctl.adapters.registry import get_global_registry

    # Ensure built-in adapters are registered
    import simctl.adapters  # noqa: F401

    registry = get_global_registry()
    available = registry.list_adapters()

    config: dict[str, Any] = {"simulators": {}}
    for sim_name in simulator_names:
        if sim_name not in available:
            msg = (
                f"Unknown simulator: '{sim_name}'. "
                f"Available: {', '.join(available)}"
            )
            raise typer.BadParameter(msg)
        adapter_cls = registry.get(sim_name)
        config["simulators"][sim_name] = adapter_cls.default_config()

    if tomli_w is None:
        # Fallback to manual TOML generation
        lines = ["[simulators]", ""]
        for sim_name, sim_cfg in config["simulators"].items():
            lines.append(f"[simulators.{sim_name}]")
            for key, value in sim_cfg.items():
                if isinstance(value, list):
                    items = ", ".join(f'"{v}"' for v in value)
                    lines.append(f"{key} = [{items}]")
                elif isinstance(value, str):
                    lines.append(f'{key} = "{value}"')
                else:
                    lines.append(f"{key} = {value}")
            lines.append("")
        return "\n".join(lines) + "\n"

    import io

    buf = io.BytesIO()
    tomli_w.dump(config, buf)
    return buf.getvalue().decode("utf-8")


def init(
    simulators: Annotated[
        Optional[list[str]],
        typer.Argument(help="Simulator names to configure (e.g. emses beach)."),
    ] = None,
    path: Annotated[
        Optional[Path],
        typer.Option("--path", "-p", help="Directory to initialize (defaults to cwd)."),
    ] = None,
    name: Annotated[
        Optional[str],
        typer.Option("--name", "-n", help="Project name (defaults to directory name)."),
    ] = None,
) -> None:
    """Initialize a new simctl project (simproject.toml etc.).

    Optionally specify simulator names to generate default simulators.toml
    entries. Example: simctl init emses beach
    """
    project_dir = (path or Path.cwd()).resolve()

    if not project_dir.exists():
        project_dir.mkdir(parents=True)

    project_name = name or project_dir.name

    created: list[str] = []
    skipped: list[str] = []

    # simproject.toml
    simproject_content = f'[project]\nname = "{project_name}"\ndescription = ""\n'
    if _write_if_missing(project_dir / _SIMPROJECT_FILE, simproject_content):
        created.append(_SIMPROJECT_FILE)
    else:
        skipped.append(_SIMPROJECT_FILE)

    # simulators.toml
    if simulators:
        sim_content = _build_simulators_toml(simulators)
    else:
        sim_content = "[simulators]\n"
    if _write_if_missing(project_dir / _SIMULATORS_FILE, sim_content):
        created.append(_SIMULATORS_FILE)
    else:
        skipped.append(_SIMULATORS_FILE)

    # launchers.toml
    if _write_if_missing(project_dir / _LAUNCHERS_FILE, "[launchers]\n"):
        created.append(_LAUNCHERS_FILE)
    else:
        skipped.append(_LAUNCHERS_FILE)

    # cases/ directory
    if _mkdir_if_missing(project_dir / "cases"):
        created.append("cases/")
    else:
        skipped.append("cases/")

    # runs/ directory
    if _mkdir_if_missing(project_dir / "runs"):
        created.append("runs/")
    else:
        skipped.append("runs/")

    # .gitignore
    if _write_if_missing(project_dir / ".gitignore", _GITIGNORE_CONTENT):
        created.append(".gitignore")
    else:
        skipped.append(".gitignore")

    # git init
    if (project_dir / ".git").exists():
        skipped.append("git init")
    else:
        result = subprocess.run(
            ["git", "init"],
            cwd=project_dir,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            created.append("git init")
        else:
            typer.echo(f"  Warning: git init failed: {result.stderr.strip()}")

    # Print results
    typer.echo(f"Initialized project '{project_name}' in {project_dir}")
    if created:
        typer.echo("  Created:")
        for item in created:
            typer.echo(f"    {item}")
    if skipped:
        typer.echo("  Skipped (already exist):")
        for item in skipped:
            typer.echo(f"    {item}")


def doctor(
    path: Annotated[
        Optional[Path],
        typer.Argument(help="Project directory to check."),
    ] = None,
) -> None:
    """Check the environment and project configuration for issues."""
    project_dir = (path or Path.cwd()).resolve()
    failures: list[str] = []

    # Check simproject.toml exists and is valid
    simproject_path = project_dir / _SIMPROJECT_FILE
    if not simproject_path.exists():
        typer.echo("[FAIL] simproject.toml not found")
        failures.append(_SIMPROJECT_FILE)
    else:
        try:
            load_project(project_dir)
            typer.echo("[PASS] simproject.toml is valid")
        except ProjectConfigError as e:
            typer.echo(f"[FAIL] simproject.toml: {e}")
            failures.append(_SIMPROJECT_FILE)

    # Check simulators.toml exists
    if (project_dir / _SIMULATORS_FILE).exists():
        typer.echo("[PASS] simulators.toml found")
    else:
        typer.echo("[FAIL] simulators.toml not found")
        failures.append(_SIMULATORS_FILE)

    # Check launchers.toml exists
    if (project_dir / _LAUNCHERS_FILE).exists():
        typer.echo("[PASS] launchers.toml found")
    else:
        typer.echo("[FAIL] launchers.toml not found")
        failures.append(_LAUNCHERS_FILE)

    # Check sbatch availability
    if shutil.which("sbatch") is not None:
        typer.echo("[PASS] sbatch is available")
    else:
        typer.echo("[FAIL] sbatch not found in PATH")
        failures.append("sbatch")

    # Check simulator adapters from simulators.toml
    simulators_path = project_dir / _SIMULATORS_FILE
    if simulators_path.exists():
        try:
            with open(simulators_path, "rb") as f:
                sim_data = tomllib.load(f)
            simulators: dict[str, Any] = sim_data.get("simulators", {})
            if simulators:
                from simctl.adapters.registry import AdapterRegistry

                registry = AdapterRegistry()
                for sim_name, sim_cfg in simulators.items():
                    if not isinstance(sim_cfg, dict):
                        continue
                    adapter_name = sim_cfg.get("adapter", "")
                    if not adapter_name:
                        continue
                    try:
                        registry.load_from_config(
                            {"simulators": {sim_name: sim_cfg}}
                        )
                        typer.echo(
                            f"[PASS] Simulator adapter '{adapter_name}' "
                            f"for '{sim_name}' is importable"
                        )
                    except Exception as e:
                        typer.echo(
                            f"[FAIL] Simulator adapter '{adapter_name}' "
                            f"for '{sim_name}': {e}"
                        )
                        failures.append(f"adapter:{adapter_name}")
        except tomllib.TOMLDecodeError as e:
            typer.echo(f"[FAIL] simulators.toml parse error: {e}")
            failures.append(_SIMULATORS_FILE)

    # Check launcher configs from launchers.toml
    launchers_path = project_dir / _LAUNCHERS_FILE
    if launchers_path.exists():
        try:
            with open(launchers_path, "rb") as f:
                launcher_data = tomllib.load(f)
            launchers: dict[str, Any] = launcher_data.get("launchers", {})
            if launchers:
                from simctl.launchers.base import Launcher, LauncherConfigError

                for lname, lcfg in launchers.items():
                    if not isinstance(lcfg, dict):
                        continue
                    try:
                        Launcher.from_config(lname, lcfg)
                        typer.echo(
                            f"[PASS] Launcher profile '{lname}' is valid"
                        )
                    except LauncherConfigError as e:
                        typer.echo(f"[FAIL] Launcher profile '{lname}': {e}")
                        failures.append(f"launcher:{lname}")
        except tomllib.TOMLDecodeError as e:
            typer.echo(f"[FAIL] launchers.toml parse error: {e}")
            failures.append(_LAUNCHERS_FILE)

    # Check run_id uniqueness
    runs_dir = project_dir / "runs"
    if runs_dir.is_dir():
        try:
            validate_uniqueness(runs_dir)
            typer.echo("[PASS] No duplicate run_ids")
        except DuplicateRunIdError as e:
            typer.echo(f"[FAIL] Duplicate run_id: {e}")
            failures.append("run_id uniqueness")
    else:
        typer.echo("[PASS] No runs/ directory (nothing to check)")

    # Final verdict
    if failures:
        typer.echo(f"\n{len(failures)} check(s) failed.")
        raise typer.Exit(code=1)
    else:
        typer.echo("\nAll checks passed.")
