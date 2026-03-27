"""Project loading and validation.

Handles reading simproject.toml, simulators.toml, and launchers.toml,
and locating the project root by walking up directories.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

from simctl.core.exceptions import ProjectConfigError, ProjectNotFoundError

_PROJECT_FILE = "simproject.toml"
_SIMULATORS_FILE = "simulators.toml"
_LAUNCHERS_FILE = "launchers.toml"


@dataclass(frozen=True)
class ProjectConfig:
    """Immutable representation of a simctl project configuration.

    Attributes:
        name: Project name from simproject.toml.
        description: Optional project description.
        root_dir: Absolute path to the project root directory.
        simulators: Simulator configurations from simulators.toml.
        launchers: Launcher configurations from launchers.toml.
        raw: The raw parsed simproject.toml dictionary.
    """

    name: str
    description: str
    root_dir: Path
    simulators: dict[str, dict[str, Any]] = field(default_factory=dict)
    launchers: dict[str, dict[str, Any]] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)


def _read_toml(path: Path) -> dict[str, Any]:
    """Read and parse a TOML file.

    Args:
        path: Path to the TOML file.

    Returns:
        Parsed TOML dictionary.

    Raises:
        ProjectConfigError: If the file cannot be read or parsed.
    """
    try:
        with open(path, "rb") as f:
            return tomllib.load(f)
    except FileNotFoundError:
        raise ProjectConfigError(f"File not found: {path}") from None
    except tomllib.TOMLDecodeError as e:
        raise ProjectConfigError(f"Invalid TOML in {path}: {e}") from e


def load_project(project_dir: Path) -> ProjectConfig:
    """Load and validate a simctl project from its root directory.

    Reads simproject.toml (required), simulators.toml (optional),
    and launchers.toml (optional).

    Args:
        project_dir: Root directory of the simctl project.

    Returns:
        Validated ProjectConfig instance.

    Raises:
        ProjectConfigError: If simproject.toml is missing or invalid.
    """
    project_dir = project_dir.resolve()
    project_file = project_dir / _PROJECT_FILE

    if not project_file.exists():
        raise ProjectConfigError(f"{_PROJECT_FILE} not found in {project_dir}")

    raw = _read_toml(project_file)

    project_section = raw.get("project")
    if not isinstance(project_section, dict):
        raise ProjectConfigError(
            f"Missing or invalid [project] section in {project_file}"
        )

    name = project_section.get("name")
    if not isinstance(name, str) or not name:
        raise ProjectConfigError(f"Missing or empty 'project.name' in {project_file}")

    description = project_section.get("description", "")
    if not isinstance(description, str):
        description = str(description)

    # Load optional simulators.toml
    simulators: dict[str, dict[str, Any]] = {}
    simulators_file = project_dir / _SIMULATORS_FILE
    if simulators_file.exists():
        sim_raw = _read_toml(simulators_file)
        sim_section = sim_raw.get("simulators", {})
        if isinstance(sim_section, dict):
            simulators = sim_section

    # Load optional launchers.toml
    launchers: dict[str, dict[str, Any]] = {}
    launchers_file = project_dir / _LAUNCHERS_FILE
    if launchers_file.exists():
        launcher_raw = _read_toml(launchers_file)
        launcher_section = launcher_raw.get("launchers", {})
        if isinstance(launcher_section, dict):
            launchers = launcher_section

    return ProjectConfig(
        name=name,
        description=description,
        root_dir=project_dir,
        simulators=simulators,
        launchers=launchers,
        raw=raw,
    )


def find_project_root(start: Path) -> Path:
    """Walk up from *start* to locate the nearest simproject.toml.

    Args:
        start: Directory to begin searching from.

    Returns:
        Path to the project root directory (containing simproject.toml).

    Raises:
        ProjectNotFoundError: If no simproject.toml is found up to
            the filesystem root.
    """
    current = start.resolve()

    # If start is a file, begin from its parent
    if current.is_file():
        current = current.parent

    while True:
        if (current / _PROJECT_FILE).exists():
            return current
        parent = current.parent
        if parent == current:
            # Reached filesystem root
            break
        current = parent

    raise ProjectNotFoundError(
        f"No {_PROJECT_FILE} found in {start} or any parent directory"
    )
