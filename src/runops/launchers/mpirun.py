"""Mpirun launcher profile for OpenMPI / MPICH-style execution.

When use_slurm_ntasks is True, the task count is expressed as
``${SLURM_NTASKS}`` in the exec line for shell expansion, so that
Slurm determines the actual number of ranks at runtime.
"""

from __future__ import annotations

import shlex
from typing import Any

from runops.launchers.base import Launcher, LauncherConfigError


class MpirunLauncher(Launcher):
    """Launcher using ``mpirun`` command.

    Attributes:
        np_flag: The flag used to specify the number of processes
            (default ``"-np"``).
    """

    def __init__(
        self,
        name: str,
        command: str,
        *,
        use_slurm_ntasks: bool = False,
        extra_options: list[str] | None = None,
        np_flag: str = "-np",
        site_config: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            name,
            command,
            use_slurm_ntasks=use_slurm_ntasks,
            extra_options=extra_options,
            site_config=site_config,
        )
        self._np_flag = np_flag

    @property
    def kind(self) -> str:
        """Return the launcher kind."""
        return "mpirun"

    @property
    def np_flag(self) -> str:
        """Return the flag used for number of processes."""
        return self._np_flag

    def build_launch_command(
        self,
        program_command: list[str],
        ntasks: int,
        extra_options: dict[str, Any] | None = None,
    ) -> list[str]:
        """Build mpirun launch command.

        Args:
            program_command: The simulator command to launch.
            ntasks: Number of MPI tasks.
            extra_options: Additional mpirun CLI options (key-value pairs).

        Returns:
            Full launch command as a list of strings.

        Raises:
            LauncherConfigError: If program_command is empty.
        """
        if not program_command:
            raise LauncherConfigError("program_command must not be empty.")

        parts: list[str] = [self.command, self._np_flag, str(ntasks)]

        # Instance-level extra options.
        parts.extend(self._extra_options)

        # Per-call extra options.
        if extra_options:
            for key, value in extra_options.items():
                if value is True:
                    parts.append(f"--{key}")
                elif value is not False and value is not None:
                    parts.extend([f"--{key}", str(value)])

        parts.extend(program_command)
        return parts

    def build_exec_line(
        self,
        program_command: list[str],
        ntasks: int,
        extra_options: dict[str, Any] | None = None,
    ) -> str:
        """Generate mpirun exec line for job.sh.

        When use_slurm_ntasks is True, the task count is rendered as
        ``${SLURM_NTASKS}`` for shell expansion.

        Args:
            program_command: The simulator command to launch.
            ntasks: Number of MPI tasks (used when use_slurm_ntasks is False).
            extra_options: Additional mpirun CLI options.

        Returns:
            Shell command string for the job script.

        Raises:
            LauncherConfigError: If program_command is empty.
        """
        if not program_command:
            raise LauncherConfigError("program_command must not be empty.")

        parts: list[str] = [self.command]

        np_str = "${SLURM_NTASKS}" if self.use_slurm_ntasks else str(ntasks)

        parts.extend(self._extra_options)

        if extra_options:
            for key, value in extra_options.items():
                if value is True:
                    parts.append(f"--{key}")
                elif value is not False and value is not None:
                    parts.extend([f"--{key}", str(value)])

        # Build shell string: quote everything except ${SLURM_NTASKS}.
        option_str = " ".join(shlex.quote(p) for p in parts)
        prog_str = " ".join(shlex.quote(p) for p in program_command)
        return f"{option_str} {self._np_flag} {np_str} {prog_str}"
