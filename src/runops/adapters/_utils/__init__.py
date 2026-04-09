"""Shared utilities for simulator adapters."""

from __future__ import annotations

from pathlib import Path

from runops.adapters._utils.toml_utils import apply_dotted_overrides


def find_venv(start: Path) -> Path | None:
    """Find the nearest ``.venv`` directory by searching upward.

    Starts from *start* and walks parent directories until a ``.venv``
    directory containing ``bin/activate`` (or ``Scripts/activate``) is found.

    Args:
        start: Starting directory for the search.

    Returns:
        Path to the venv directory, or ``None`` if not found.
    """
    current = start.resolve()
    for directory in [current, *current.parents]:
        venv = directory / ".venv"
        if venv.is_dir() and (
            (venv / "bin" / "activate").exists()
            or (venv / "Scripts" / "activate").exists()
        ):
            return venv
    return None


__all__ = [
    "apply_dotted_overrides",
    "find_venv",
]
