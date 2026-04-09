"""Srun launcher profile for Slurm-native MPI execution.

When use_slurm_ntasks is True, srun relies on the SLURM_NTASKS
environment variable set by Slurm and does not emit an explicit
``--ntasks`` flag.  This is the typical Slurm-native pattern where
``#SBATCH --ntasks`` in job.sh already determines the task count.
"""

from __future__ import annotations

import shlex
from typing import Any

from runops.launchers.base import Launcher, LauncherConfigError


class SrunLauncher(Launcher):
    """Launcher using Slurm's ``srun`` command."""

    def __init__(
        self,
        name: str,
        command: str,
        *,
        use_slurm_ntasks: bool = False,
        extra_options: list[str] | None = None,
        site_config: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            name,
            command,
            use_slurm_ntasks=use_slurm_ntasks,
            extra_options=extra_options,
            site_config=site_config,
        )

    @property
    def kind(self) -> str:
        """Return the launcher kind."""
        return "srun"

    def build_launch_command(
        self,
        program_command: list[str],
        ntasks: int,
        extra_options: dict[str, Any] | None = None,
    ) -> list[str]:
        """Build srun launch command.

        Args:
            program_command: The simulator command to launch.
            ntasks: Number of MPI tasks.
            extra_options: Additional srun CLI options (key-value pairs).

        Returns:
            Full launch command as a list of strings.

        Raises:
            LauncherConfigError: If program_command is empty.
        """
        if not program_command:
            raise LauncherConfigError("program_command must not be empty.")

        parts: list[str] = [self.command]

        # When not relying on SLURM_NTASKS, pass --ntasks explicitly.
        if not self.use_slurm_ntasks:
            parts.append(f"--ntasks={ntasks}")

        # Instance-level extra options.
        parts.extend(self._extra_options)

        # Per-call extra options.
        if extra_options:
            for key, value in extra_options.items():
                if value is True:
                    parts.append(f"--{key}")
                elif value is not False and value is not None:
                    parts.append(f"--{key}={value}")

        parts.extend(program_command)
        return parts

    def build_exec_line(
        self,
        program_command: list[str],
        ntasks: int,
        extra_options: dict[str, Any] | None = None,
    ) -> str:
        """Generate srun exec line for job.sh.

        When use_slurm_ntasks is True, the line omits ``--ntasks`` entirely
        since Slurm injects SLURM_NTASKS from ``#SBATCH --ntasks``.

        Args:
            program_command: The simulator command to launch.
            ntasks: Number of MPI tasks (ignored when use_slurm_ntasks is True).
            extra_options: Additional srun CLI options.

        Returns:
            Shell command string for the job script.

        Raises:
            LauncherConfigError: If program_command is empty.
        """
        if not program_command:
            raise LauncherConfigError("program_command must not be empty.")

        parts: list[str] = [self.command]

        if not self.use_slurm_ntasks:
            parts.append(f"--ntasks={ntasks}")

        parts.extend(self._extra_options)

        if extra_options:
            for key, value in extra_options.items():
                if value is True:
                    parts.append(f"--{key}")
                elif value is not False and value is not None:
                    parts.append(f"--{key}={value}")

        # Quote program command for shell safety.
        prog_str = " ".join(shlex.quote(p) for p in program_command)
        option_str = " ".join(shlex.quote(p) for p in parts)
        return f"{option_str} {prog_str}"
