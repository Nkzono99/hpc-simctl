"""Simulator adapter for BEACH (BEM + Accumulated CHarge).

BEACH is a boundary element method simulator for surface charging.
It uses TOML-based configuration and produces CSV output files.

GitHub: https://github.com/Nkzono99/BEACH
Package: ``pip install beach-bem``
"""

from __future__ import annotations

import hashlib
import logging
import shutil
import subprocess
from pathlib import Path
from typing import Any

from simctl.adapters.base import SimulatorAdapter

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

INPUT_DIR = "input"
WORK_DIR = "work"
EXIT_CODE_FILE = "exit_code"

# BEACH file names
BEACH_CONFIG = "beach.toml"
SUMMARY_FILE = "summary.txt"
CHARGES_FILE = "charges.csv"
MESH_TRIANGLES_FILE = "mesh_triangles.csv"
CHARGE_HISTORY_FILE = "charge_history.csv"
POTENTIAL_HISTORY_FILE = "potential_history.csv"

EXPECTED_OUTPUTS: dict[str, str] = {
    "summary": SUMMARY_FILE,
    "charges": CHARGES_FILE,
    "mesh_triangles": MESH_TRIANGLES_FILE,
    "charge_history": CHARGE_HISTORY_FILE,
    "potential_history": POTENTIAL_HISTORY_FILE,
}

_RESOLVER_MODES = frozenset({"package", "local_source", "local_executable"})


class BeachAdapter(SimulatorAdapter):
    """Adapter for BEACH boundary element method simulator.

    BEACH uses a single TOML configuration file (``beach.toml``) and
    produces CSV output files for charges, mesh data, and time histories.

    Class Attributes:
        adapter_name: Registry key for this adapter.
    """

    adapter_name: str = "beach"

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
        """Generate ``input/beach.toml`` from case parameters.

        The ``case_data["params"]`` dictionary is serialized as a TOML
        file.  It may contain nested dictionaries that map directly to
        TOML sections (e.g. ``[sim]``, ``[mesh]``, ``[output]``,
        ``[[particles.species]]``).

        Args:
            case_data: Merged case/survey parameters.
            run_dir: Target run directory.

        Returns:
            List of relative paths to generated input files.

        Raises:
            ValueError: If required case metadata is missing.
        """
        case_section = case_data.get("case", {})
        if not case_section:
            msg = "case_data must contain a 'case' section"
            raise ValueError(msg)

        params = case_data.get("params")
        if not params:
            msg = "case_data must contain a 'params' section for BEACH config"
            raise ValueError(msg)

        input_dir = run_dir / INPUT_DIR
        input_dir.mkdir(parents=True, exist_ok=True)

        config_path = input_dir / BEACH_CONFIG
        config_path.write_text(_render_toml(params))

        return [str(config_path.relative_to(run_dir))]

    def resolve_runtime(
        self,
        simulator_config: dict[str, Any],
        resolver_mode: str,
    ) -> dict[str, Any]:
        """Resolve the BEACH runtime (executable and tools).

        BEACH is a Python package installed via ``pip install beach-bem``.
        The main executable is ``beach`` and the post-processing CLI is
        ``beachx``.

        Supports ``venv_path`` in *simulator_config* to locate binaries
        inside a virtual environment.

        Args:
            simulator_config: Simulator section from ``simulators.toml``.
            resolver_mode: One of ``"package"``, ``"local_source"``,
                ``"local_executable"``.

        Returns:
            Runtime information dictionary.

        Raises:
            ValueError: If *resolver_mode* is unsupported or required
                keys are missing.
        """
        if resolver_mode not in _RESOLVER_MODES:
            msg = (
                f"Unsupported resolver_mode '{resolver_mode}'. "
                f"Expected one of {sorted(_RESOLVER_MODES)}"
            )
            raise ValueError(msg)

        runtime: dict[str, Any] = {"resolver_mode": resolver_mode}
        venv_path = simulator_config.get("venv_path", "")
        if venv_path:
            runtime["venv_path"] = venv_path

        if resolver_mode == "package":
            exe_name = simulator_config.get("executable", "beach")
            resolved = shutil.which(exe_name)
            runtime["executable"] = resolved if resolved else exe_name
            runtime["source"] = "package"
            # Also resolve beachx
            beachx = shutil.which("beachx")
            runtime["beachx"] = beachx if beachx else "beachx"
            # Try to get package version
            runtime["package_version"] = _get_package_version()

        elif resolver_mode == "local_source":
            source_repo = simulator_config.get("source_repo", "")
            executable = simulator_config.get("executable", "")
            if not source_repo or not executable:
                msg = (
                    "simulator_config must specify 'source_repo' and "
                    "'executable' for local_source mode"
                )
                raise ValueError(msg)
            runtime["source_repo"] = source_repo
            runtime["executable"] = executable
            runtime["build_command"] = simulator_config.get(
                "build_command", "pip install ."
            )

        elif resolver_mode == "local_executable":
            executable = simulator_config.get("executable", "")
            if not executable:
                msg = (
                    "simulator_config must specify 'executable' "
                    "for local_executable mode"
                )
                raise ValueError(msg)
            runtime["executable"] = executable

        return runtime

    def build_program_command(
        self,
        runtime_info: dict[str, Any],
        run_dir: Path,
    ) -> list[str]:
        """Build ``["beach", "beach.toml"]`` execution command.

        Virtual environment activation is expected to be handled by
        ``pre_commands`` in ``job.sh``, not by this method.

        Args:
            runtime_info: Output from :meth:`resolve_runtime`.
            run_dir: The run directory.

        Returns:
            Command as a list of strings (no MPI launcher prefix).

        Raises:
            ValueError: If *runtime_info* lacks ``executable``.
        """
        executable: str = runtime_info.get("executable", "")
        if not executable:
            msg = "runtime_info must contain 'executable'"
            raise ValueError(msg)

        input_file = run_dir / INPUT_DIR / BEACH_CONFIG
        config_arg = str(input_file) if input_file.exists() else BEACH_CONFIG
        return [executable, config_arg]

    def detect_outputs(self, run_dir: Path) -> dict[str, Any]:
        """Detect BEACH output files in the run directory.

        Looks for known output files (``summary.txt``, ``charges.csv``,
        etc.) in the ``work/`` directory.

        Args:
            run_dir: The run directory.

        Returns:
            Mapping of output type to relative path strings.
        """
        work_dir = run_dir / WORK_DIR
        if not work_dir.is_dir():
            logger.warning("work/ directory not found in %s", run_dir)
            return {}

        outputs: dict[str, Any] = {}

        for label, filename in EXPECTED_OUTPUTS.items():
            path = work_dir / filename
            if path.exists():
                outputs[label] = str(path.relative_to(run_dir))

        # Also detect stdout/stderr logs
        for log_name in ("stdout.log", "stderr.log"):
            log_path = work_dir / log_name
            if log_path.exists():
                outputs[log_path.stem] = str(log_path.relative_to(run_dir))

        return outputs

    def detect_status(self, run_dir: Path) -> str:
        """Infer BEACH simulation status from output files.

        Detection logic:

        1. If ``work/exit_code`` is ``0`` and ``summary.txt`` exists,
           return ``"completed"``.
        2. If ``work/exit_code`` is ``0`` but no ``summary.txt``,
           return ``"completed"`` (exit code takes precedence).
        3. If ``work/exit_code`` is non-zero, return ``"failed"``.
        4. If ``summary.txt`` exists without exit code, return
           ``"completed"`` (BEACH finished normally).
        5. If ``work/`` has content but no markers, return ``"running"``.
        6. Otherwise return ``"unknown"``.

        Args:
            run_dir: The run directory.

        Returns:
            A status string.
        """
        work_dir = run_dir / WORK_DIR
        exit_code_path = work_dir / EXIT_CODE_FILE

        # Check exit code first
        if exit_code_path.exists():
            try:
                code = int(exit_code_path.read_text().strip())
            except (ValueError, OSError):
                return "unknown"
            return "completed" if code == 0 else "failed"

        # No exit code -- check for summary.txt as success indicator
        summary_path = work_dir / SUMMARY_FILE
        if summary_path.exists():
            return "completed"

        # Check for charges.csv as partial progress
        charges_path = work_dir / CHARGES_FILE
        if charges_path.exists():
            return "running"

        # Check whether work/ has any content
        if work_dir.is_dir() and any(work_dir.iterdir()):
            return "running"

        return "unknown"

    def summarize(self, run_dir: Path) -> dict[str, Any]:
        """Extract key results from BEACH output files.

        Parses ``summary.txt`` if available and counts output CSV files.

        Args:
            run_dir: The run directory.

        Returns:
            Summary dictionary.
        """
        summary: dict[str, Any] = {}
        errors: list[str] = []

        try:
            summary["status"] = self.detect_status(run_dir)
        except Exception as exc:
            errors.append(f"detect_status: {exc}")
            summary["status"] = "unknown"

        try:
            summary["outputs"] = self.detect_outputs(run_dir)
        except Exception as exc:
            errors.append(f"detect_outputs: {exc}")
            summary["outputs"] = {}

        # Parse exit code
        exit_code_path = run_dir / WORK_DIR / EXIT_CODE_FILE
        if exit_code_path.exists():
            try:
                summary["exit_code"] = int(exit_code_path.read_text().strip())
            except (ValueError, OSError) as exc:
                errors.append(f"exit_code: {exc}")

        # Parse summary.txt
        summary_path = run_dir / WORK_DIR / SUMMARY_FILE
        if summary_path.exists():
            try:
                summary["summary_text"] = _parse_summary_file(summary_path)
            except Exception as exc:
                errors.append(f"summary.txt: {exc}")

        # Count CSV output rows
        charges_path = run_dir / WORK_DIR / CHARGES_FILE
        if charges_path.exists():
            try:
                lines = charges_path.read_text().strip().splitlines()
                # Subtract header row
                summary["charge_count"] = max(0, len(lines) - 1)
            except OSError as exc:
                errors.append(f"charges.csv: {exc}")

        if errors:
            summary["errors"] = errors

        return summary

    def collect_provenance(
        self,
        runtime_info: dict[str, Any],
    ) -> dict[str, Any]:
        """Collect BEACH provenance information.

        Gathers package version, executable path and hash, and
        optional git information for local_source mode.

        Args:
            runtime_info: Output from :meth:`resolve_runtime`.

        Returns:
            Provenance dictionary with SPEC-compliant field names.
        """
        provenance: dict[str, Any] = {
            "resolver_mode": runtime_info.get("resolver_mode", ""),
            "executable": runtime_info.get("executable", ""),
            "exe_hash": "",
            "git_commit": "",
            "git_dirty": False,
            "source_repo": runtime_info.get("source_repo", ""),
            "build_command": runtime_info.get("build_command", ""),
            "package_version": runtime_info.get("package_version", ""),
            "venv_path": runtime_info.get("venv_path", ""),
        }

        # Executable hash
        exe_path = Path(runtime_info.get("executable", ""))
        if exe_path.is_file():
            provenance["exe_hash"] = _compute_file_hash(exe_path)

        # Git provenance for local_source
        if runtime_info.get("resolver_mode") == "local_source":
            repo = runtime_info.get("source_repo", "")
            if repo:
                git_info = _collect_git_info(Path(repo))
                provenance["git_commit"] = git_info.get("commit", "")
                provenance["git_dirty"] = git_info.get("dirty", False)

        return provenance


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _render_toml(data: dict[str, Any], prefix: str = "") -> str:
    """Render a dictionary as TOML text.

    Handles nested dicts as TOML sections and lists of dicts as
    array-of-tables.  This is a minimal renderer sufficient for
    BEACH config files without requiring a ``tomli_w`` dependency.

    Args:
        data: Dictionary to render.
        prefix: Current section prefix for nested rendering.

    Returns:
        TOML-formatted string.
    """
    lines: list[str] = []
    simple_keys: dict[str, Any] = {}
    nested_keys: dict[str, Any] = {}

    for key, value in data.items():
        if isinstance(value, dict) or (
            isinstance(value, list) and value and isinstance(value[0], dict)
        ):
            nested_keys[key] = value
        else:
            simple_keys[key] = value

    # Emit simple key-value pairs
    for key, value in simple_keys.items():
        lines.append(f"{key} = {_toml_value(value)}")

    # Emit nested sections
    for key, value in nested_keys.items():
        section = f"{prefix}.{key}" if prefix else key
        if isinstance(value, list):
            # Array of tables: [[section]]
            for item in value:
                lines.append("")
                lines.append(f"[[{section}]]")
                lines.append(_render_toml(item, section))
        else:
            lines.append("")
            lines.append(f"[{section}]")
            lines.append(_render_toml(value, section))

    return "\n".join(lines)


def _toml_value(value: Any) -> str:
    """Convert a Python value to its TOML string representation.

    Args:
        value: The value to convert.

    Returns:
        TOML-formatted value string.
    """
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return str(value)
    if isinstance(value, str):
        return f'"{value}"'
    if isinstance(value, list):
        items = ", ".join(_toml_value(v) for v in value)
        return f"[{items}]"
    return f'"{value}"'


def _parse_summary_file(path: Path) -> dict[str, str]:
    """Parse BEACH summary.txt into key-value pairs.

    Expects lines of the form ``key: value`` or ``key = value``.

    Args:
        path: Path to summary.txt.

    Returns:
        Dictionary of parsed key-value pairs.
    """
    result: dict[str, str] = {}
    text = path.read_text()
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        for sep in (":", "="):
            if sep in line:
                key, _, val = line.partition(sep)
                result[key.strip()] = val.strip()
                break
    return result


def _get_package_version() -> str:
    """Query the installed BEACH package version.

    Returns:
        Version string, or empty string on failure.
    """
    try:
        result = subprocess.run(
            ["beach", "--version"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except FileNotFoundError:
        pass

    # Fallback: try pip show
    try:
        result = subprocess.run(
            ["pip", "show", "beach-bem"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                if line.startswith("Version:"):
                    return line.split(":", 1)[1].strip()
    except FileNotFoundError:
        pass

    return ""


def _compute_file_hash(path: Path) -> str:
    """Return ``sha256:<hex>`` hash of a file.

    Args:
        path: Path to the file.

    Returns:
        Hash string prefixed with ``sha256:``.
    """
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return f"sha256:{h.hexdigest()}"


def _collect_git_info(repo_path: Path) -> dict[str, Any]:
    """Collect basic git info from a repository path.

    Args:
        repo_path: Path to the git repository root.

    Returns:
        Dictionary with ``commit``, ``dirty``, and ``branch`` keys.
    """
    info: dict[str, Any] = {"commit": "", "dirty": False, "branch": ""}
    if not repo_path.is_dir():
        return info
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            cwd=repo_path,
            check=False,
        )
        if result.returncode == 0:
            info["commit"] = result.stdout.strip()

        result = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True,
            text=True,
            cwd=repo_path,
            check=False,
        )
        if result.returncode == 0:
            info["dirty"] = bool(result.stdout.strip())

        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            cwd=repo_path,
            check=False,
        )
        if result.returncode == 0:
            info["branch"] = result.stdout.strip()
    except FileNotFoundError:
        logger.debug("git not found on PATH; skipping git provenance")

    return info
