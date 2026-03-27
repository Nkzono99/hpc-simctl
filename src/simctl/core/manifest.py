"""Manifest (manifest.toml) read/write operations.

The manifest is the single source of truth for a run's metadata,
state, provenance, and job information.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def read_manifest(run_dir: Path) -> dict[str, Any]:
    """Read and parse a run's manifest.toml.

    Args:
        run_dir: Path to the run directory.

    Returns:
        Parsed manifest dictionary.
    """
    raise NotImplementedError


def write_manifest(run_dir: Path, data: dict[str, Any]) -> None:
    """Write manifest data to manifest.toml.

    Args:
        run_dir: Path to the run directory.
        data: Manifest data to write.
    """
    raise NotImplementedError


def update_manifest(run_dir: Path, updates: dict[str, Any]) -> None:
    """Merge updates into an existing manifest.toml.

    Args:
        run_dir: Path to the run directory.
        updates: Key-value pairs to merge into the manifest.
    """
    raise NotImplementedError
