"""Srun launcher profile for Slurm-native MPI execution."""

from __future__ import annotations

from typing import Any

from simctl.launchers.base import Launcher


class SrunLauncher(Launcher):
    """Launcher using Slurm's srun command."""

    @property
    def kind(self) -> str:
        """Return the launcher kind."""
        return "srun"

    def build_launch_command(
        self,
        program_command: list[str],
        job_config: dict[str, Any],
        launcher_config: dict[str, Any],
    ) -> list[str]:
        """Build srun launch command."""
        raise NotImplementedError

    def build_exec_line(
        self,
        program_command: list[str],
        job_config: dict[str, Any],
        launcher_config: dict[str, Any],
    ) -> str:
        """Generate srun exec line for job.sh."""
        raise NotImplementedError
