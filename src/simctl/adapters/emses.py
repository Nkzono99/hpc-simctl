"""EMSES (Electromagnetic Particle-in-Cell) simulator adapter.

Handles EMSES-specific input format (Fortran namelist plasma.inp/plasma.preinp),
HDF5/ASCII output detection, and MPI-based execution via srun.
"""

from __future__ import annotations

import hashlib
import logging
import shutil
import subprocess
from pathlib import Path
from typing import Any

from simctl.adapters.base import SimulatorAdapter
from simctl.adapters.namelist import apply_overrides, parse_namelist_params

logger = logging.getLogger(__name__)

INPUT_DIR = "input"
WORK_DIR = "work"

# Known EMSES ASCII diagnostic file names
_DIAGNOSTIC_FILES = frozenset({
    "energy",
    "energy1",
    "energy2",
    "ewave",
    "chgacm1",
    "chgacm2",
    "chgmov",
    "influx",
    "isflux",
    "noflux",
    "icur",
    "ocur",
    "currnt",
    "seyield",
    "volt",
    "pbody",
    "pbodyr",
    "pbodyd",
    "oltime",
    "nesc",
})

# Default module set for the HPC environment
_DEFAULT_MODULES = [
    "intel/2023.2",
    "intelmpi/2023.2",
    "hdf5/1.12.2_intel-2023.2-impi",
    "fftw/3.3.10_intel-2022.3-impi",
]


class EmseAdapter(SimulatorAdapter):
    """Adapter for the EMSES electromagnetic PIC simulator.

    EMSES uses Fortran namelist files (plasma.inp / plasma.preinp) for
    configuration and produces HDF5 field data and ASCII time-series
    diagnostics.

    Class Attributes:
        adapter_name: Registry key for this adapter.
    """

    adapter_name: str = "emses"

    # ------------------------------------------------------------------
    # SimulatorAdapter interface
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        """Return the canonical name of this adapter."""
        return self.adapter_name

    def render_inputs(
        self,
        case_data: dict[str, Any],
        run_dir: Path,
    ) -> list[str]:
        """Generate EMSES input files in the run directory.

        Copies ``plasma.preinp`` (or ``plasma.inp``) from the case
        directory, applies parameter overrides from *case_data*, and
        writes the result to ``<run_dir>/input/``.

        Args:
            case_data: Merged case/survey parameters.  Expects a
                ``case`` section with ``case_dir`` pointing to the
                template directory, and an optional ``params`` section.
            run_dir: Target run directory.

        Returns:
            List of relative paths to generated input files.
        """
        case_section = case_data.get("case", {})
        if not case_section:
            msg = "case_data must contain a 'case' section"
            raise ValueError(msg)

        params = case_data.get("params", {})
        input_dir = run_dir / INPUT_DIR
        input_dir.mkdir(parents=True, exist_ok=True)

        created: list[str] = []

        # Locate template files from case directory
        case_dir_str = case_section.get("case_dir", "")
        case_dir = Path(case_dir_str) if case_dir_str else None

        template_file: Path | None = None
        if case_dir:
            for candidate_name in ("plasma.preinp", "plasma.inp"):
                candidate = case_dir / candidate_name
                if candidate.is_file():
                    template_file = candidate
                    break

        # Also check explicit input_files list
        input_files: list[str] = case_section.get("input_files", [])
        for src_str in input_files:
            src = Path(src_str)
            if src.name in ("plasma.preinp", "plasma.inp") and src.is_file():
                template_file = src
                break

        # Process the main input template
        if template_file is not None:
            template_text = template_file.read_text()
            if params:
                template_text = apply_overrides(template_text, params)

            dest = input_dir / template_file.name
            dest.write_text(template_text)
            created.append(str(dest.relative_to(run_dir)))

            # If we wrote plasma.preinp, also process the companion plasma.inp
            if template_file.name == "plasma.preinp" and template_file.parent:
                companion = template_file.parent / "plasma.inp"
                if companion.is_file():
                    companion_text = companion.read_text()
                    if params:
                        companion_text = apply_overrides(companion_text, params)
                    dest_inp = input_dir / "plasma.inp"
                    dest_inp.write_text(companion_text)
                    created.append(str(dest_inp.relative_to(run_dir)))

        # Copy any additional input files
        for src_str in input_files:
            src = Path(src_str)
            if not src.is_file():
                logger.warning("Input file not found, skipping: %s", src)
                continue
            if src.name in ("plasma.preinp", "plasma.inp"):
                continue  # Already handled above
            dest = input_dir / src.name
            shutil.copy2(src, dest)
            created.append(str(dest.relative_to(run_dir)))

        return created

    def resolve_runtime(
        self,
        simulator_config: dict[str, Any],
        resolver_mode: str,
    ) -> dict[str, Any]:
        """Resolve the EMSES runtime (mpiemses3D executable).

        Args:
            simulator_config: Simulator section from ``simulators.toml``.
            resolver_mode: One of ``"package"``, ``"local_source"``,
                ``"local_executable"``.

        Returns:
            Runtime info dict with at least ``executable`` and
            ``resolver_mode`` keys.

        Raises:
            ValueError: If required keys are missing or mode is invalid.
        """
        runtime: dict[str, Any] = {"resolver_mode": resolver_mode}
        executable = simulator_config.get("executable", "mpiemses3D")

        if resolver_mode == "package":
            resolved = shutil.which(executable)
            runtime["executable"] = resolved if resolved else executable
            runtime["source"] = "package"

        elif resolver_mode == "local_source":
            source_repo = simulator_config.get("source_repo", "")
            if not source_repo:
                msg = "source_repo required for local_source mode"
                raise ValueError(msg)
            runtime["source_repo"] = source_repo
            runtime["executable"] = executable
            runtime["build_command"] = simulator_config.get("build_command", "")

        elif resolver_mode == "local_executable":
            exe_path = simulator_config.get("executable", "")
            if not exe_path:
                msg = "executable path required for local_executable mode"
                raise ValueError(msg)
            runtime["executable"] = exe_path

        else:
            msg = f"Unsupported resolver_mode: {resolver_mode}"
            raise ValueError(msg)

        return runtime

    def build_program_command(
        self,
        runtime_info: dict[str, Any],
        run_dir: Path,
    ) -> list[str]:
        """Build the EMSES execution command.

        Returns a command that runs ``mpiemses3D`` with ``plasma.inp``
        as its argument.  The command is designed to run from the
        ``work/`` directory.

        Args:
            runtime_info: Output from :meth:`resolve_runtime`.
            run_dir: The run directory.

        Returns:
            Command as a list of strings.
        """
        executable = runtime_info.get("executable", "mpiemses3D")
        return [executable, "plasma.inp"]

    def detect_outputs(self, run_dir: Path) -> dict[str, Any]:
        """Detect EMSES output files in ``work/``.

        Scans for HDF5 field data, ASCII diagnostics, and snapshot files.

        Args:
            run_dir: The run directory.

        Returns:
            Dictionary of output categories to file lists.
        """
        work_dir = run_dir / WORK_DIR
        if not work_dir.is_dir():
            return {}

        outputs: dict[str, Any] = {}

        # HDF5 field files
        h5_files = sorted(work_dir.glob("*.h5"))
        if h5_files:
            outputs["hdf5_fields"] = [
                str(f.relative_to(run_dir)) for f in h5_files
            ]

        # ASCII diagnostics
        diag_files: list[str] = []
        for diag_name in sorted(_DIAGNOSTIC_FILES):
            f = work_dir / diag_name
            if f.is_file():
                diag_files.append(str(f.relative_to(run_dir)))
        if diag_files:
            outputs["diagnostics"] = diag_files

        # SNAPSHOT data
        snapshot_dir = work_dir / "SNAPSHOT1"
        if snapshot_dir.is_dir():
            snap_files = sorted(snapshot_dir.glob("esdat*.h5"))
            if snap_files:
                outputs["snapshots"] = [
                    str(f.relative_to(run_dir)) for f in snap_files
                ]

        # Log files
        logs: list[str] = []
        for pattern in ("stdout.*.log", "stderr.*.log", "*.out", "*.err"):
            for f in sorted(work_dir.glob(pattern)):
                logs.append(str(f.relative_to(run_dir)))
        if logs:
            outputs["logs"] = logs

        return outputs

    def detect_status(self, run_dir: Path) -> str:
        """Infer EMSES simulation status from output files.

        Detection logic:

        1. If stderr contains error keywords -> ``"failed"``.
        2. If energy file shows completion to *nstep* -> ``"completed"``.
        3. If output files exist -> ``"running"``.
        4. Otherwise -> ``"unknown"``.

        Args:
            run_dir: The run directory.

        Returns:
            A status string.
        """
        work_dir = run_dir / WORK_DIR
        if not work_dir.is_dir():
            return "unknown"

        # Check for errors in log files
        for pattern in ("stderr.*.log", "*.err"):
            for log in work_dir.glob(pattern):
                try:
                    content = log.read_text(errors="replace")
                    if any(
                        kw in content.lower()
                        for kw in ("error", "segmentation fault", "killed", "oom")
                    ):
                        return "failed"
                except OSError:
                    pass

        # Check energy file for simulation progress
        energy_file = work_dir / "energy"
        if energy_file.is_file():
            try:
                nstep = self._get_expected_nstep(run_dir)
                lines = [
                    l for l in energy_file.read_text().strip().split("\n") if l.strip()
                ]
                if lines and nstep:
                    last_parts = lines[-1].strip().split()
                    if last_parts:
                        last_step = int(float(last_parts[0]))
                        if last_step >= nstep:
                            return "completed"
                        return "running"
            except (ValueError, IndexError, OSError):
                pass

        # Fallback: check for any output files
        if list(work_dir.glob("*.h5")):
            return "running"

        return "unknown"

    def summarize(self, run_dir: Path) -> dict[str, Any]:
        """Extract key metrics from EMSES outputs.

        Args:
            run_dir: The run directory.

        Returns:
            Summary dictionary with status, output counts, energy data,
            and simulation parameters.
        """
        summary: dict[str, Any] = {}
        work_dir = run_dir / WORK_DIR

        summary["status"] = self.detect_status(run_dir)

        # Count outputs by category
        outputs = self.detect_outputs(run_dir)
        summary["output_counts"] = {
            k: len(v) if isinstance(v, list) else 1
            for k, v in outputs.items()
        }

        # Energy diagnostics
        energy_file = work_dir / "energy"
        if energy_file.is_file():
            try:
                lines = [
                    l for l in energy_file.read_text().strip().split("\n") if l.strip()
                ]
                if lines:
                    summary["total_energy_lines"] = len(lines)
                    last_parts = lines[-1].strip().split()
                    if last_parts:
                        summary["last_step"] = int(float(last_parts[0]))
            except (ValueError, OSError):
                pass

        # Simulation parameters from input files
        input_dir = run_dir / INPUT_DIR
        for inp_name in ("plasma.inp", "plasma.preinp"):
            inp_file = input_dir / inp_name
            if inp_file.is_file():
                try:
                    params = parse_namelist_params(inp_file.read_text())
                    if "tmgrid" in params:
                        for key in ("nx", "ny", "nz", "dt"):
                            if key in params["tmgrid"]:
                                summary[key] = params["tmgrid"][key]
                    if "jobcon" in params:
                        if "nstep" in params["jobcon"]:
                            summary["nstep"] = params["jobcon"]["nstep"]
                except OSError:
                    pass
                break

        return summary

    def collect_provenance(
        self,
        runtime_info: dict[str, Any],
    ) -> dict[str, Any]:
        """Collect EMSES provenance information.

        Args:
            runtime_info: Output from :meth:`resolve_runtime`.

        Returns:
            Provenance dictionary with executable hash and git info.
        """
        provenance: dict[str, Any] = {
            "resolver_mode": runtime_info.get("resolver_mode", ""),
            "executable": runtime_info.get("executable", ""),
            "exe_hash": "",
            "git_commit": "",
            "git_dirty": False,
            "source_repo": runtime_info.get("source_repo", ""),
            "build_command": runtime_info.get("build_command", ""),
            "package_version": "",
        }

        # Executable hash
        exe_path = Path(runtime_info.get("executable", ""))
        if exe_path.is_file():
            h = hashlib.sha256()
            with exe_path.open("rb") as f:
                for chunk in iter(lambda: f.read(8192), b""):
                    h.update(chunk)
            provenance["exe_hash"] = f"sha256:{h.hexdigest()}"

        # Git provenance for local_source
        if runtime_info.get("resolver_mode") == "local_source":
            repo = runtime_info.get("source_repo", "")
            if repo and Path(repo).is_dir():
                try:
                    result = subprocess.run(
                        ["git", "rev-parse", "HEAD"],
                        capture_output=True,
                        text=True,
                        cwd=repo,
                        check=False,
                    )
                    if result.returncode == 0:
                        provenance["git_commit"] = result.stdout.strip()
                    result = subprocess.run(
                        ["git", "status", "--porcelain"],
                        capture_output=True,
                        text=True,
                        cwd=repo,
                        check=False,
                    )
                    if result.returncode == 0:
                        provenance["git_dirty"] = bool(result.stdout.strip())
                except FileNotFoundError:
                    logger.debug("git not found; skipping git provenance")

        return provenance

    # ------------------------------------------------------------------
    # EMSES-specific helpers (used by CLI / jobgen integration)
    # ------------------------------------------------------------------

    def get_setup_commands(self, run_dir: Path) -> list[str]:
        """Return setup commands for the EMSES job script.

        These copy input files to ``work/`` and run ``preinp``.
        """
        input_dir = run_dir / INPUT_DIR
        return [
            f"cp {input_dir}/plasma.* . 2>/dev/null || true",
            "if [ -f ./plasma.preinp ]; then preinp; fi",
            "rm -f *_0000.h5",
            "date",
        ]

    def get_post_commands(self) -> list[str]:
        """Return post-execution commands."""
        return ["date"]

    def get_modules(self) -> list[str]:
        """Return default module names for EMSES."""
        return list(_DEFAULT_MODULES)

    def get_extra_env(self) -> dict[str, str]:
        """Return default environment variables for EMSES."""
        return {"EMSES_DEBUG": "no"}

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @staticmethod
    def _get_expected_nstep(run_dir: Path) -> int | None:
        """Read ``nstep`` from the run's input files."""
        input_dir = run_dir / INPUT_DIR
        for inp_name in ("plasma.inp", "plasma.preinp"):
            inp_file = input_dir / inp_name
            if inp_file.is_file():
                try:
                    params = parse_namelist_params(inp_file.read_text())
                    if "jobcon" in params and "nstep" in params["jobcon"]:
                        return int(params["jobcon"]["nstep"])
                except (ValueError, OSError):
                    pass
        return None
