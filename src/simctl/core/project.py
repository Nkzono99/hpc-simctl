"""Project loading and validation.

Handles reading simproject.toml and validating the project structure.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def load_project(project_dir: Path) -> dict[str, Any]:
    """Load and validate a simproject.toml file.

    Args:
        project_dir: Root directory of the simctl project.

    Returns:
        Parsed project configuration dictionary.
    """
    raise NotImplementedError


def find_project_root(start: Path) -> Path:
    """Walk up from *start* to locate the nearest simproject.toml.

    Args:
        start: Directory to begin searching from.

    Returns:
        Path to the project root directory.

    Raises:
        FileNotFoundError: If no simproject.toml is found.
    """
    raise NotImplementedError
