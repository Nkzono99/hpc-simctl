"""Run discovery via recursive search under runs/.

Finds all run directories by locating manifest.toml files
and verifies run_id uniqueness within a project.
"""

from __future__ import annotations

from pathlib import Path


def discover_runs(runs_dir: Path) -> list[Path]:
    """Recursively find all run directories under runs/.

    A directory is considered a run if it contains a manifest.toml file.

    Args:
        runs_dir: Root runs/ directory to search.

    Returns:
        Sorted list of paths to run directories.
    """
    raise NotImplementedError


def check_run_id_uniqueness(runs_dir: Path) -> list[str]:
    """Check for duplicate run_ids under runs/.

    Args:
        runs_dir: Root runs/ directory to search.

    Returns:
        List of duplicate run_id strings (empty if all unique).
    """
    raise NotImplementedError
