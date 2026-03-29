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
    def pip_packages(cls) -> list[str]:
        """Return pip packages to install for this simulator.

        Override in subclasses to list Python packages needed for
        analysis, post-processing, or utilities.

        Returns:
            List of pip package specifiers (e.g. ``["emout", "h5py"]``).
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
