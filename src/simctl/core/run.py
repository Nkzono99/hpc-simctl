"""Run generation and run_id assignment.

Creates run directories and assigns unique run identifiers.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def generate_run_id(date_str: str, sequence: int) -> str:
    """Generate a run_id in the format RYYYYMMDD-NNNN.

    Args:
        date_str: Date string in YYYYMMDD format.
        sequence: Sequence number for the day.

    Returns:
        Formatted run_id string.
    """
    raise NotImplementedError


def create_run_directory(
    parent_dir: Path,
    run_id: str,
    case_data: dict[str, Any],
) -> Path:
    """Create a run directory with standard subdirectories.

    Args:
        parent_dir: Parent directory (survey directory).
        run_id: Unique run identifier.
        case_data: Case configuration for this run.

    Returns:
        Path to the created run directory.
    """
    raise NotImplementedError
