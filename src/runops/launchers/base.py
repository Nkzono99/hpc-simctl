"""Abstract base class for launcher profiles.

A launcher wraps a simulator command with the appropriate MPI
launch command (srun, mpirun, mpiexec, etc.).
"""

from __future__ import annotations

import shlex
from abc import ABC, abstractmethod
from typing import Any


class LauncherConfigError(Exception):
    """Raised when launcher configuration is invalid."""


class Launcher(ABC):
    """Abstract base class for MPI launcher profiles.

    Attributes:
        name: Profile name as defined in launchers.toml (e.g. "slurm_srun").
        command: The launcher executable (e.g. "srun", "mpirun").
        use_slurm_ntasks: If True, rely on SLURM_NTASKS env var for task count.
        extra_options: Additional launcher-specific CLI options.
    """

    def __init__(
        self,
        name: str,
        command: str,
        *,
        use_slurm_ntasks: bool = False,
        extra_options: list[str] | None = None,
        site_config: dict[str, Any] | None = None,
    ) -> None:
        self._name = name
        self._command = command
        self._use_slurm_ntasks = use_slurm_ntasks
        self._extra_options = extra_options or []
        self._site_config = site_config or {}

    @property
    def name(self) -> str:
        """Return the profile name (e.g. 'slurm_srun')."""
        return self._name

    @property
    def command(self) -> str:
        """Return the launcher executable command."""
        return self._command

    @property
    def use_slurm_ntasks(self) -> bool:
        """Whether this launcher relies on SLURM_NTASKS for task count."""
        return self._use_slurm_ntasks

    # ------------------------------------------------------------------
    # Deprecated site_config properties — use SiteProfile instead.
    # Kept temporarily for backward compatibility.
    # ------------------------------------------------------------------

    @property
    def modules(self) -> list[str]:
        """Module names to load in job script.

        .. deprecated:: Use :class:`~runops.core.site.SiteProfile` instead.
        """
        return list(self._site_config.get("modules", []))

    @property
    def resource_style(self) -> str:
        """Resource specification style: "standard" or "rsc".

        .. deprecated:: Use :class:`~runops.core.site.SiteProfile` instead.
        """
        return str(self._site_config.get("resource_style", "standard"))

    @property
    def stdout_format(self) -> str | None:
        """Custom stdout file format (e.g. "stdout.%J.log").

        .. deprecated:: Use :class:`~runops.core.site.SiteProfile` instead.
        """
        return self._site_config.get("stdout")

    @property
    def stderr_format(self) -> str | None:
        """Custom stderr file format (e.g. "stderr.%J.log").

        .. deprecated:: Use :class:`~runops.core.site.SiteProfile` instead.
        """
        return self._site_config.get("stderr")

    @property
    def extra_sbatch(self) -> list[str]:
        """Additional raw #SBATCH directives.

        .. deprecated:: Use :class:`~runops.core.site.SiteProfile` instead.
        """
        return list(self._site_config.get("extra_sbatch", []))

    @property
    def site_env(self) -> dict[str, str]:
        """Site-specific environment variables.

        .. deprecated:: Use :class:`~runops.core.site.SiteProfile` instead.
        """
        raw = self._site_config.get("env", {})
        return {str(k): str(v) for k, v in raw.items()} if raw else {}

    @property
    def setup_commands(self) -> list[str]:
        """Shell commands to run before the main execution in job.sh.

        .. deprecated:: Use :class:`~runops.core.site.SiteProfile` instead.
        """
        return list(self._site_config.get("setup_commands", []))

    @property
    @abstractmethod
    def kind(self) -> str:
        """Return the launcher kind identifier (e.g. 'srun', 'mpirun')."""
        ...

    @abstractmethod
    def build_launch_command(
        self,
        program_command: list[str],
        ntasks: int,
        extra_options: dict[str, Any] | None = None,
    ) -> list[str]:
        """Wrap a program command with the MPI launcher invocation.

        Args:
            program_command: The simulator command to launch.
            ntasks: Number of MPI tasks.
            extra_options: Additional launcher-specific options.

        Returns:
            Full launch command as a list of strings.

        Raises:
            LauncherConfigError: If the configuration is invalid.
        """
        ...

    @abstractmethod
    def build_exec_line(
        self,
        program_command: list[str],
        ntasks: int,
        extra_options: dict[str, Any] | None = None,
    ) -> str:
        """Generate the execution line for inclusion in job.sh.

        This produces a shell-ready string. When use_slurm_ntasks is True,
        the task count is expressed as ${SLURM_NTASKS} for shell expansion.

        Args:
            program_command: The simulator command to launch.
            ntasks: Number of MPI tasks (used only when use_slurm_ntasks is False).
            extra_options: Additional launcher-specific options.

        Returns:
            Shell command string for the job script.
        """
        ...

    def build_env_vars(self, config: dict[str, Any] | None = None) -> dict[str, str]:
        """Return environment variables the launcher needs.

        Override in subclasses to provide launcher-specific env vars
        (e.g. OMP_NUM_THREADS).

        Args:
            config: Optional job/launcher config for deriving env vars.

        Returns:
            Dictionary of environment variable name to value.
        """
        env: dict[str, str] = {}
        if config and "cpus_per_task" in config:
            env["OMP_NUM_THREADS"] = str(config["cpus_per_task"])
        return env

    @classmethod
    def from_config(cls, name: str, config: dict[str, Any]) -> Launcher:
        """Create a Launcher instance from a launchers.toml profile entry.

        Args:
            name: Profile name (key under [launchers]).
            config: The profile dict (kind, command, options, ...).

        Returns:
            A concrete Launcher instance.

        Raises:
            LauncherConfigError: If kind is unknown or required fields missing.
        """
        # Accept "type" (config convention) or "kind" (legacy).
        kind = config.get("type") or config.get("kind")
        if not kind:
            raise LauncherConfigError(
                f"Launcher profile '{name}' is missing required field 'type'."
            )
        # Default command to the launcher type name (srun, mpirun, mpiexec).
        command = config.get("command", kind)

        # Import concrete launchers here to avoid circular imports.
        from runops.launchers.mpiexec import MpiexecLauncher
        from runops.launchers.mpirun import MpirunLauncher
        from runops.launchers.srun import SrunLauncher

        use_slurm = bool(config.get("use_slurm_ntasks", False))
        # Accept "extra_options" (list) or "args" (string, split by shell rules).
        extra_opts_raw = config.get("extra_options", [])
        extra_opts: list[str] = (
            list(extra_opts_raw) if isinstance(extra_opts_raw, list) else []
        )
        args_str = config.get("args", "")
        if args_str:
            extra_opts.extend(shlex.split(str(args_str)))

        # Site-specific config passed through for jobgen.
        site_config = {
            k: v
            for k, v in config.items()
            if k
            in (
                "modules",
                "resource_style",
                "stdout",
                "stderr",
                "extra_sbatch",
                "env",
            )
        }

        if kind == "srun":
            return SrunLauncher(
                name=name,
                command=str(command),
                use_slurm_ntasks=use_slurm,
                extra_options=extra_opts,
                site_config=site_config,
            )
        elif kind == "mpirun":
            np_flag = str(config.get("np_flag", "-np"))
            return MpirunLauncher(
                name=name,
                command=str(command),
                use_slurm_ntasks=use_slurm,
                extra_options=extra_opts,
                np_flag=np_flag,
                site_config=site_config,
            )
        elif kind == "mpiexec":
            n_flag = str(config.get("n_flag", "-n"))
            return MpiexecLauncher(
                name=name,
                command=str(command),
                use_slurm_ntasks=use_slurm,
                extra_options=extra_opts,
                n_flag=n_flag,
                site_config=site_config,
            )
        else:
            raise LauncherConfigError(
                f"Unknown launcher kind '{kind}' in profile '{name}'. "
                f"Supported kinds: srun, mpirun, mpiexec."
            )

    def _quote_command(self, parts: list[str]) -> str:
        """Join command parts into a shell-safe string.

        Args:
            parts: Command parts to join.

        Returns:
            A shell-escaped command string.
        """
        return " ".join(shlex.quote(p) for p in parts)


def load_launchers(launchers_data: dict[str, Any]) -> dict[str, Launcher]:
    """Load all launcher profiles from parsed launchers.toml data.

    Expects the top-level ``[launchers]`` table, e.g.::

        {
            "slurm_srun": {"kind": "srun", "command": "srun", ...},
            "openmpi": {"kind": "mpirun", "command": "mpirun", ...},
        }

    Args:
        launchers_data: The ``launchers`` table from launchers.toml.

    Returns:
        Dictionary mapping profile name to Launcher instance.

    Raises:
        LauncherConfigError: If any profile is invalid.
    """
    result: dict[str, Launcher] = {}
    for name, profile in launchers_data.items():
        if not isinstance(profile, dict):
            raise LauncherConfigError(
                f"Launcher profile '{name}' must be a table, "
                f"got {type(profile).__name__}."
            )
        result[name] = Launcher.from_config(name, profile)
    return result
