"""Abstract base class for simulator adapters.

Each simulator (e.g. lunar_pic) must implement this interface to handle
its specific input format, execution command, output detection, and
provenance collection.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any


class SimulatorAdapter(ABC):
    """Abstract base class for simulator-specific adapters.

    Adapters handle everything that varies between simulators:
    input file rendering, runtime resolution, command construction,
    output detection, status inference, summarization, and provenance.
    """

    @classmethod
    def default_config(cls) -> dict[str, Any]:
        """Return the default simulators.toml entry for this adapter.

        Override in subclasses to provide simulator-specific defaults.

        Returns:
            Dictionary suitable for writing as a ``[simulators.<name>]``
            section in ``simulators.toml``.
        """
        return {
            "adapter": getattr(cls, "adapter_name", ""),
            "resolver_mode": "local_executable",
            "executable": "",
        }

    @classmethod
    def interactive_config(cls) -> dict[str, Any]:
        """Interactively prompt the user to build a simulator config.

        Uses typer.prompt() for each configurable field.
        Override in subclasses for simulator-specific prompts.

        Returns:
            Configuration dictionary for simulators.toml.
        """
        import typer

        defaults = cls.default_config()
        adapter_name = defaults.get("adapter", "")

        typer.echo(f"\n  Configuring '{adapter_name}' simulator:")

        resolver_mode = typer.prompt(
            "    Resolver mode (local_executable / local_source / package)",
            default=defaults.get("resolver_mode", "local_executable"),
        )
        executable = typer.prompt(
            "    Executable path or name",
            default=defaults.get("executable", ""),
        )

        config = {
            "adapter": adapter_name,
            "resolver_mode": resolver_mode,
            "executable": executable,
        }

        if resolver_mode == "local_source":
            source_repo = typer.prompt("    Source repository path", default="")
            build_command = typer.prompt("    Build command", default="make -j")
            config["source_repo"] = source_repo
            config["build_command"] = build_command

        # Carry over non-prompted defaults (e.g. modules)
        for key, value in defaults.items():
            if key not in config:
                config[key] = value

        return config

    @classmethod
    def case_template(cls) -> dict[str, str]:
        """Return template files for a new case.

        Override in subclasses to provide simulator-specific templates.

        Returns:
            Dict mapping filename to content string.
            Must include ``"case.toml"``.
        """
        name = getattr(cls, "adapter_name", "generic")
        return {
            "case.toml": (
                f'[case]\nname = ""\nsimulator = "{name}"\n'
                f'launcher = "default"\ndescription = ""\n\n'
                f"[params]\n\n[job]\n"
                f'partition = ""\nnodes = 1\nntasks = 1\n'
                f'walltime = "01:00:00"\n'
            ),
        }

    @classmethod
    def pip_packages(cls) -> list[str]:
        """Return pip packages to install for this simulator.

        Override in subclasses to list Python packages needed for
        analysis, post-processing, or utilities.

        Returns:
            List of pip package specifiers (e.g. ``["emout", "h5py"]``).
        """
        return []

    @classmethod
    def doc_repos(cls) -> list[tuple[str, str]]:
        """Return documentation/reference repositories to clone.

        Override in subclasses to list Git repositories that contain
        parameter references, usage examples, or documentation that
        AI agents and users can consult.

        Returns:
            List of ``(clone_url, dest_dir_name)`` tuples.
            ``dest_dir_name`` is the directory name under the project's
            ``refs/`` directory.
        """
        return []

    @classmethod
    def agent_guide(cls) -> str:
        """Return AI agent guide for this simulator as markdown.

        Override in subclasses to provide simulator-specific knowledge
        including input/output formats, key parameters, typical
        workflows, and documentation references.

        Returns:
            Markdown string for inclusion in CLAUDE.md / AGENTS.md.
        """
        name = getattr(cls, "adapter_name", cls.__name__)
        return f"### {name}\n\nNo detailed guide available.\n"

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the canonical name of this adapter."""
        ...

    @abstractmethod
    def render_inputs(self, case_data: dict[str, Any], run_dir: Path) -> list[str]:
        """Generate simulator input files in the run directory.

        Args:
            case_data: Merged case/survey parameters.
            run_dir: Target run directory.

        Returns:
            List of relative paths to generated input files.
        """
        ...

    @abstractmethod
    def resolve_runtime(
        self, simulator_config: dict[str, Any], resolver_mode: str
    ) -> dict[str, Any]:
        """Resolve the simulator runtime (executable, build, etc.).

        Args:
            simulator_config: Simulator section from simulators.toml.
            resolver_mode: One of "package", "local_source", "local_executable".

        Returns:
            Runtime information dictionary including executable path.
        """
        ...

    @abstractmethod
    def build_program_command(
        self, runtime_info: dict[str, Any], run_dir: Path
    ) -> list[str]:
        """Build the simulator execution command (without MPI launcher prefix).

        Args:
            runtime_info: Output from resolve_runtime.
            run_dir: The run directory.

        Returns:
            Command as a list of strings.
        """
        ...

    @abstractmethod
    def detect_outputs(self, run_dir: Path) -> dict[str, Any]:
        """Detect output files produced by the simulation.

        Args:
            run_dir: The run directory.

        Returns:
            Dictionary describing detected outputs.
        """
        ...

    @abstractmethod
    def detect_status(self, run_dir: Path) -> str:
        """Infer simulation completion status from output files.

        Args:
            run_dir: The run directory.

        Returns:
            A status string (e.g. "completed", "failed").
        """
        ...

    @abstractmethod
    def summarize(self, run_dir: Path) -> dict[str, Any]:
        """Extract key metrics from simulation outputs.

        Args:
            run_dir: The run directory.

        Returns:
            Summary dictionary for analysis/summary.json.
        """
        ...

    @abstractmethod
    def collect_provenance(self, runtime_info: dict[str, Any]) -> dict[str, Any]:
        """Collect code provenance for manifest recording.

        Args:
            runtime_info: Output from resolve_runtime.

        Returns:
            Provenance dictionary (git commit, exe hash, etc.).
        """
        ...
