"""Code provenance collection.

Records simulator source repository, git commit, executable hash,
and other provenance information for reproducibility.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def collect_git_provenance(repo_path: Path) -> dict[str, Any]:
    """Collect git provenance from a source repository.

    Args:
        repo_path: Path to the git repository.

    Returns:
        Dictionary with commit hash, dirty state, etc.
    """
    raise NotImplementedError


def compute_executable_hash(executable: Path) -> str:
    """Compute a SHA-256 hash of an executable file.

    Args:
        executable: Path to the executable.

    Returns:
        Hex-encoded SHA-256 hash string prefixed with "sha256:".
    """
    raise NotImplementedError
