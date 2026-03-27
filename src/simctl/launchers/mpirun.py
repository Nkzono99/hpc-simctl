"""Mpirun launcher profile for OpenMPI-style execution."""

from __future__ import annotations

from typing import Any

from simctl.launchers.base import Launcher


class MpirunLauncher(Launcher):
    """Launcher using mpirun command."""

    @property
    def kind(self) -> str:
        """Return the launcher kind."""
        return "mpirun"

    def build_launch_command(
        self,
        program_command: list[str],
        job_config: dict[str, Any],
        launcher_config: dict[str, Any],
    ) -> list[str]:
        """Build mpirun launch command."""
        raise NotImplementedError

    def build_exec_line(
        self,
        program_command: list[str],
        job_config: dict[str, Any],
        launcher_config: dict[str, Any],
    ) -> str:
        """Generate mpirun exec line for job.sh."""
        raise NotImplementedError
