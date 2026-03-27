"""Abstract base class for launcher profiles.

A launcher wraps a simulator command with the appropriate MPI
launch command (srun, mpirun, mpiexec, etc.).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class Launcher(ABC):
    """Abstract base class for MPI launcher profiles."""

    @property
    @abstractmethod
    def kind(self) -> str:
        """Return the launcher kind identifier (e.g. 'srun', 'mpirun')."""
        ...

    @abstractmethod
    def build_launch_command(
        self,
        program_command: list[str],
        job_config: dict[str, Any],
        launcher_config: dict[str, Any],
    ) -> list[str]:
        """Wrap a program command with the MPI launcher invocation.

        Args:
            program_command: The simulator command to launch.
            job_config: Job configuration (nodes, ntasks, etc.).
            launcher_config: Launcher-specific settings from launchers.toml.

        Returns:
            Full launch command as a list of strings.
        """
        ...

    @abstractmethod
    def build_exec_line(
        self,
        program_command: list[str],
        job_config: dict[str, Any],
        launcher_config: dict[str, Any],
    ) -> str:
        """Generate the execution line for inclusion in job.sh.

        Args:
            program_command: The simulator command to launch.
            job_config: Job configuration (nodes, ntasks, etc.).
            launcher_config: Launcher-specific settings from launchers.toml.

        Returns:
            Shell command string for the job script.
        """
        ...
