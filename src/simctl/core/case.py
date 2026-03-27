"""Case loading and expansion.

Reads case.toml files and prepares case data for run generation.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def load_case(case_dir: Path) -> dict[str, Any]:
    """Load and validate a case.toml file.

    Args:
        case_dir: Directory containing case.toml.

    Returns:
        Parsed case configuration dictionary.
    """
    raise NotImplementedError


def resolve_case(case_name: str, project_dir: Path) -> Path:
    """Resolve a case name to its directory path.

    Args:
        case_name: Logical name of the case.
        project_dir: Root of the simctl project.

    Returns:
        Path to the case directory.

    Raises:
        FileNotFoundError: If the case is not found.
    """
    raise NotImplementedError
