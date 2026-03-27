"""Survey expansion and parameter cartesian product.

Reads survey.toml and expands parameter axes into individual run configs.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def load_survey(survey_dir: Path) -> dict[str, Any]:
    """Load and validate a survey.toml file.

    Args:
        survey_dir: Directory containing survey.toml.

    Returns:
        Parsed survey configuration dictionary.
    """
    raise NotImplementedError


def expand_axes(axes: dict[str, list[Any]]) -> list[dict[str, Any]]:
    """Compute the cartesian product of parameter axes.

    Args:
        axes: Mapping of parameter names to lists of values.

    Returns:
        List of parameter dictionaries, one per combination.
    """
    raise NotImplementedError
