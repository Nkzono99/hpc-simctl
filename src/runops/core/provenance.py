"""Code provenance collection.

Records simulator source repository, git commit, executable hash,
and other provenance information for reproducibility.
"""

from __future__ import annotations

import hashlib
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from runops.core.exceptions import ProvenanceError


@dataclass(frozen=True)
class ProvenanceInfo:
    """Immutable provenance information for a run.

    Matches SPEC section 17 requirements.

    Attributes:
        source_repo: Path to the source repository.
        git_commit: Git commit hash (short or full).
        git_dirty: Whether the working tree has uncommitted changes.
        build_command: Command used to build the executable.
        executable: Path to the executable.
        exe_hash: SHA-256 hash of the executable (prefixed with "sha256:").
        package_version: Package version string (if installed via pip).
        resolver_mode: How the simulator was resolved ("package",
            "local_source", "local_executable").
    """

    source_repo: str = ""
    git_commit: str = ""
    git_dirty: bool = False
    build_command: str = ""
    executable: str = ""
    exe_hash: str = ""
    package_version: str = ""
    resolver_mode: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to a dictionary suitable for manifest.toml.

        Returns:
            Dictionary matching the [simulator_source] section format.
        """
        return {
            "source_repo": self.source_repo,
            "git_commit": self.git_commit,
            "git_dirty": self.git_dirty,
            "build_command": self.build_command,
            "executable": self.executable,
            "exe_hash": self.exe_hash,
            "package_version": self.package_version,
        }


def collect_git_provenance(repo_path: Path) -> ProvenanceInfo:
    """Collect git provenance from a source repository.

    Retrieves the current HEAD commit hash and dirty state from the
    given git repository.

    Args:
        repo_path: Path to the git repository.

    Returns:
        ProvenanceInfo with git_commit and git_dirty populated.

    Raises:
        ProvenanceError: If git commands fail or the path is not a
            git repository.
    """
    repo_path = repo_path.resolve()

    if not repo_path.is_dir():
        raise ProvenanceError(
            f"Repository path does not exist or is not a directory: {repo_path}"
        )

    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            cwd=repo_path,
            check=True,
        ).stdout.strip()
    except subprocess.CalledProcessError as e:
        raise ProvenanceError(
            f"Failed to get git commit from {repo_path}: {e.stderr.strip()}"
        ) from e
    except FileNotFoundError:
        raise ProvenanceError("git command not found") from None

    try:
        diff_result = subprocess.run(
            ["git", "diff", "--quiet", "HEAD"],
            capture_output=True,
            cwd=repo_path,
        )
        # Also check for untracked changes in the index
        index_result = subprocess.run(
            ["git", "diff", "--quiet", "--cached"],
            capture_output=True,
            cwd=repo_path,
        )
        dirty = diff_result.returncode != 0 or index_result.returncode != 0
    except FileNotFoundError:
        raise ProvenanceError("git command not found") from None

    return ProvenanceInfo(
        source_repo=str(repo_path),
        git_commit=commit,
        git_dirty=dirty,
    )


def compute_executable_hash(executable: Path) -> str:
    """Compute a SHA-256 hash of an executable file.

    Args:
        executable: Path to the executable.

    Returns:
        Hex-encoded SHA-256 hash string prefixed with "sha256:".

    Raises:
        ProvenanceError: If the file does not exist or cannot be read.
    """
    executable = executable.resolve()

    if not executable.is_file():
        raise ProvenanceError(f"Executable not found: {executable}")

    try:
        sha256 = hashlib.sha256()
        with open(executable, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
        return f"sha256:{sha256.hexdigest()}"
    except OSError as e:
        raise ProvenanceError(f"Failed to hash executable {executable}: {e}") from e
