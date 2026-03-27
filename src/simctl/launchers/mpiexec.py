"""Mpiexec launcher profile."""

from __future__ import annotations

from typing import Any

from simctl.launchers.base import Launcher


class MpiexecLauncher(Launcher):
    """Launcher using mpiexec command."""

    @property
    def kind(self) -> str:
        """Return the launcher kind."""
        return "mpiexec"

    def build_launch_command(
        self,
        program_command: list[str],
        job_config: dict[str, Any],
        launcher_config: dict[str, Any],
    ) -> list[str]:
        """Build mpiexec launch command."""
        raise NotImplementedError

    def build_exec_line(
        self,
        program_command: list[str],
        job_config: dict[str, Any],
        launcher_config: dict[str, Any],
    ) -> str:
        """Generate mpiexec exec line for job.sh."""
        raise NotImplementedError
