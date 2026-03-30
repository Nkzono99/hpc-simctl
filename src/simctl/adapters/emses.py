"""Simulator adapter for MPIEMSES3D (3D electromagnetic PIC plasma simulator).

MPIEMSES3D is a Fortran-based MPI-parallel particle-in-cell simulator.
Input files use Fortran namelist format (``plasma.inp``, optional
``plasma.preinp``).  Outputs are HDF5 files (``*_NNNN.h5``).

GitHub: https://github.com/CS12-Laboratory/MPIEMSES3D
"""

from __future__ import annotations

import hashlib
import logging
import re
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
INPUT_FILE = "plasma.inp"
PREINP_FILE = "plasma.preinp"
EXECUTABLE_NAME = "mpiemses3D"

STDOUT_FILE = "stdout.log"
STDERR_FILE = "stderr.log"
EXIT_CODE_FILE = "exit_code"

DEFAULT_NAMELIST_GROUP = "emses"

_RESOLVER_MODES = frozenset({"package", "local_source", "local_executable"})

# Patterns for log parsing
_TIMESTEP_PATTERN = re.compile(r"istep\s*=\s*(\d+)", re.IGNORECASE)
_WALLTIME_PATTERN = re.compile(
    r"(?:wall\s*time|elapsed)\s*[:=]\s*([\d.]+)", re.IGNORECASE
)
_ERROR_PATTERNS = (
    re.compile(r"error", re.IGNORECASE),
    re.compile(r"abort", re.IGNORECASE),
    re.compile(r"SIGTERM|SIGSEGV|SIGKILL", re.IGNORECASE),
)


# ---------------------------------------------------------------------------
# Namelist helpers
# ---------------------------------------------------------------------------


def parse_namelist(text: str) -> dict[str, dict[str, Any]]:
    """Parse Fortran namelist text into nested dicts.

    Each namelist group ``&name ... /`` becomes a top-level key whose
    value is a dict of parameter name-value pairs.

    Args:
        text: Raw namelist file contents.

    Returns:
        Mapping of group name to parameter dict.
    """
    groups: dict[str, dict[str, Any]] = {}
    # Match &group_name ... / blocks (Fortran namelist syntax)
    group_pattern = re.compile(r"&(\w+)\s*(.*?)\s*/", re.DOTALL | re.IGNORECASE)
    for match in group_pattern.finditer(text):
        group_name = match.group(1).lower()
        body = match.group(2)
        params = _parse_namelist_body(body)
        groups[group_name] = params
    return groups


def _parse_namelist_body(body: str) -> dict[str, Any]:
    """Parse the body of a single namelist group into key-value pairs.

    Args:
        body: Text between ``&group`` and ``/``.

    Returns:
        Parameter dict with Python-typed values.
    """
    params: dict[str, Any] = {}
    # Remove line continuations and normalise whitespace
    clean = body.replace("\n", " ").replace("\r", " ")
    # Split on commas that are not inside quotes
    tokens = re.split(r",(?=\s*\w+\s*=)", clean)
    for token in tokens:
        token = token.strip()
        if not token or "=" not in token:
            continue
        key, _, value = token.partition("=")
        key = key.strip().lower()
        value = value.strip().rstrip(",").strip()
        params[key] = _cast_namelist_value(value)
    return params


def _cast_namelist_value(raw: str) -> Any:
    """Convert a namelist value string to a Python type.

    Args:
        raw: Raw string value from namelist.

    Returns:
        Converted Python value (int, float, bool, or str).
    """
    # Strip surrounding quotes
    if (raw.startswith("'") and raw.endswith("'")) or (
        raw.startswith('"') and raw.endswith('"')
    ):
        return raw[1:-1]
    # Fortran booleans
    low = raw.lower().strip(".")
    if low in ("true", "t"):
        return True
    if low in ("false", "f"):
        return False
    # Integer
    try:
        return int(raw)
    except ValueError:
        pass
    # Float (handle Fortran 'd' exponent)
    try:
        return float(raw.replace("d", "e").replace("D", "E"))
    except ValueError:
        pass
    return raw


def write_namelist(params: dict[str, Any], group_name: str) -> str:
    """Generate a Fortran namelist string from a parameter dict.

    Args:
        params: Parameter name-value mapping.
        group_name: Namelist group name (without ``&``).

    Returns:
        Formatted namelist string.
    """
    lines: list[str] = [f"&{group_name}"]
    for key, value in params.items():
        formatted = _format_namelist_value(value)
        lines.append(f"  {key} = {formatted},")
    lines.append("/")
    return "\n".join(lines) + "\n"


def _format_namelist_value(value: Any) -> str:
    """Format a Python value for Fortran namelist output.

    Args:
        value: Python value to format.

    Returns:
        Formatted string suitable for namelist files.
    """
    if isinstance(value, bool):
        return ".true." if value else ".false."
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return f"{value}"
    if isinstance(value, str):
        return f"'{value}'"
    return str(value)


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------


class Emses3DAdapter(SimulatorAdapter):
    """Adapter for the MPIEMSES3D 3D electromagnetic PIC simulator.

    Class Attributes:
        adapter_name: Registry key for this adapter.
    """

    adapter_name: str = "emses"

    @property
    def name(self) -> str:
        """Return the canonical name of this adapter."""
        return self.adapter_name

    def render_inputs(
        self,
        case_data: dict[str, Any],
        run_dir: Path,
    ) -> list[str]:
        """Generate EMSES input files (``plasma.inp``, optional ``plasma.preinp``).

        Supports two modes:

        * **Template mode**: If ``case_data["case"]["input_template"]`` points
          to an existing ``plasma.inp``, it is copied and parameters from
          ``case_data["params"]`` are overlaid.
        * **Generate mode**: A new ``plasma.inp`` is written from scratch using
          ``case_data["params"]``.

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

        input_dir = run_dir / INPUT_DIR
        input_dir.mkdir(parents=True, exist_ok=True)

        params: dict[str, Any] = case_data.get("params", {})
        created: list[str] = []

        # --- plasma.inp ---
        group_name = case_data.get("namelist_group", DEFAULT_NAMELIST_GROUP)
        template_path_str: str = case_section.get("input_template", "")

        if template_path_str and Path(template_path_str).is_file():
            created.extend(
                self._render_from_template(
                    Path(template_path_str), params, group_name, input_dir, run_dir
                )
            )
        elif params:
            inp_path = input_dir / INPUT_FILE
            inp_path.write_text(write_namelist(params, group_name))
            created.append(str(inp_path.relative_to(run_dir)))
        else:
            msg = "No input_template and no params provided; cannot generate plasma.inp"
            raise ValueError(msg)

        # --- plasma.preinp ---
        preinp_content: str = case_data.get("preinp_content", "")
        preinp_template: str = case_section.get("preinp_template", "")

        if preinp_content:
            preinp_path = input_dir / PREINP_FILE
            preinp_path.write_text(preinp_content)
            created.append(str(preinp_path.relative_to(run_dir)))
        elif preinp_template and Path(preinp_template).is_file():
            preinp_path = input_dir / PREINP_FILE
            shutil.copy2(preinp_template, preinp_path)
            created.append(str(preinp_path.relative_to(run_dir)))

        return created

    def resolve_runtime(
        self,
        simulator_config: dict[str, Any],
        resolver_mode: str,
    ) -> dict[str, Any]:
        """Resolve the EMSES runtime (executable, source repo, etc.).

        Supports ``local_source``, ``local_executable``, and ``package``
        resolver modes.

        Args:
            simulator_config: Simulator section from ``simulators.toml``.
            resolver_mode: One of ``"package"``, ``"local_source"``,
                ``"local_executable"``.

        Returns:
            Runtime information dictionary.

        Raises:
            ValueError: If *resolver_mode* is unsupported or required keys
                are missing.
        """
        if resolver_mode not in _RESOLVER_MODES:
            msg = (
                f"Unsupported resolver_mode '{resolver_mode}'. "
                f"Expected one of {sorted(_RESOLVER_MODES)}"
            )
            raise ValueError(msg)

        runtime: dict[str, Any] = {"resolver_mode": resolver_mode}

        if resolver_mode == "package":
            exe_name = simulator_config.get("executable", EXECUTABLE_NAME)
            resolved = shutil.which(exe_name)
            runtime["executable"] = resolved if resolved else exe_name
            runtime["source"] = "package"

        elif resolver_mode == "local_source":
            source_repo = simulator_config.get("source_repo", "")
            if not source_repo:
                msg = (
                    "simulator_config must specify 'source_repo' for local_source mode"
                )
                raise ValueError(msg)
            executable = simulator_config.get("executable", "")
            if not executable:
                # Default: look for mpiemses3D in source repo root
                executable = str(Path(source_repo) / EXECUTABLE_NAME)
            runtime["source_repo"] = source_repo
            runtime["executable"] = executable
            runtime["build_command"] = simulator_config.get("build_command", "make")

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
        """Build the EMSES execution command.

        Returns ``[executable, "plasma.inp"]``.  The launcher (srun, mpirun)
        is prepended by the jobgen layer, not here.

        Args:
            runtime_info: Output from :meth:`resolve_runtime`.
            run_dir: The run directory.

        Returns:
            Command as a list of strings.

        Raises:
            ValueError: If *runtime_info* lacks an ``executable`` key.
        """
        executable: str = runtime_info.get("executable", "")
        if not executable:
            msg = "runtime_info must contain 'executable'"
            raise ValueError(msg)

        return [executable, INPUT_FILE]

    def detect_outputs(self, run_dir: Path) -> dict[str, Any]:
        """Detect EMSES output files in ``work/``.

        Looks for HDF5 files (``*.h5``), stdout/stderr logs, and any
        other files produced during the run.

        Args:
            run_dir: The run directory.

        Returns:
            Mapping of descriptive labels to relative path strings.
        """
        work_dir = run_dir / WORK_DIR
        if not work_dir.is_dir():
            logger.warning("work/ directory not found in %s", run_dir)
            return {}

        outputs: dict[str, Any] = {}

        # Logs
        for log_name in (STDOUT_FILE, STDERR_FILE):
            log_path = work_dir / log_name
            if log_path.exists():
                outputs[log_path.stem] = str(log_path.relative_to(run_dir))

        # HDF5 output files
        h5_files = sorted(work_dir.glob("*.h5"))
        if h5_files:
            outputs["hdf5_files"] = [str(f.relative_to(run_dir)) for f in h5_files]
            outputs["hdf5_count"] = len(h5_files)

        # Other files (excluding logs, exit_code, and h5)
        skip_names = {STDOUT_FILE, STDERR_FILE, EXIT_CODE_FILE}
        for path in sorted(work_dir.iterdir()):
            if path.name in skip_names or path.suffix == ".h5":
                continue
            if path.is_file() or path.is_dir():
                outputs[path.name] = str(path.relative_to(run_dir))

        return outputs

    def detect_status(self, run_dir: Path) -> str:
        """Determine EMSES run status from output files and logs.

        Detection logic:

        1. If ``work/exit_code`` exists and is ``0``, return ``"completed"``.
        2. If ``work/exit_code`` exists and is non-zero, return ``"failed"``.
        3. If stdout contains error/abort markers, return ``"failed"``.
        4. If HDF5 files exist but no exit code, return ``"running"``.
        5. Otherwise return ``"unknown"``.

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

        # Check for error markers in stdout
        stdout_path = work_dir / STDOUT_FILE
        if stdout_path.exists():
            try:
                content = stdout_path.read_text(errors="replace")
                for pattern in _ERROR_PATTERNS:
                    if pattern.search(content):
                        return "failed"
            except OSError:
                pass

        # Check for HDF5 output as sign of running
        if work_dir.is_dir() and any(work_dir.glob("*.h5")):
            return "running"

        # Check for any content in work/
        if work_dir.is_dir() and any(work_dir.iterdir()):
            return "running"

        return "unknown"

    def summarize(self, run_dir: Path) -> dict[str, Any]:
        """Extract key metrics from EMSES run outputs.

        Gathers status, HDF5 file counts, timestep progress, and wall
        time from log files.

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

        # Exit code
        exit_code_path = run_dir / WORK_DIR / EXIT_CODE_FILE
        if exit_code_path.exists():
            try:
                summary["exit_code"] = int(exit_code_path.read_text().strip())
            except (ValueError, OSError) as exc:
                errors.append(f"exit_code: {exc}")

        # Parse stdout for timestep and wall time
        stdout_path = run_dir / WORK_DIR / STDOUT_FILE
        if stdout_path.exists():
            try:
                self._parse_stdout_metrics(stdout_path, summary)
            except OSError as exc:
                errors.append(f"stdout_parse: {exc}")

        if errors:
            summary["errors"] = errors

        return summary

    def collect_provenance(
        self,
        runtime_info: dict[str, Any],
    ) -> dict[str, Any]:
        """Collect EMSES provenance information.

        Gathers executable hash, git commit info from source repo, and
        build metadata following the SPEC field naming convention.

        Args:
            runtime_info: Output from :meth:`resolve_runtime`.

        Returns:
            Provenance dictionary.
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

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _render_from_template(
        self,
        template_path: Path,
        params: dict[str, Any],
        group_name: str,
        input_dir: Path,
        run_dir: Path,
    ) -> list[str]:
        """Copy a template ``plasma.inp`` and overlay parameters.

        Args:
            template_path: Path to the template namelist file.
            params: Override parameters.
            group_name: Namelist group name to modify.
            input_dir: Destination input directory.
            run_dir: Run directory (for computing relative paths).

        Returns:
            List of relative paths to created files.
        """
        template_text = template_path.read_text()
        if params:
            groups = parse_namelist(template_text)
            target = groups.get(group_name, {})
            target.update(params)
            groups[group_name] = target
            # Rebuild the namelist file from parsed groups
            parts: list[str] = []
            for gname, gparams in groups.items():
                parts.append(write_namelist(gparams, gname))
            inp_path = input_dir / INPUT_FILE
            inp_path.write_text("\n".join(parts))
        else:
            inp_path = input_dir / INPUT_FILE
            shutil.copy2(template_path, inp_path)

        return [str(inp_path.relative_to(run_dir))]

    @staticmethod
    def _parse_stdout_metrics(
        stdout_path: Path,
        summary: dict[str, Any],
    ) -> None:
        """Extract timestep and wall-time metrics from stdout log.

        Args:
            stdout_path: Path to the stdout log file.
            summary: Summary dict to populate in place.
        """
        content = stdout_path.read_text(errors="replace")

        # Find last timestep
        matches = _TIMESTEP_PATTERN.findall(content)
        if matches:
            summary["last_timestep"] = int(matches[-1])

        # Find wall time
        wt_match = _WALLTIME_PATTERN.search(content)
        if wt_match:
            summary["wall_time_seconds"] = float(wt_match.group(1))


# ---------------------------------------------------------------------------
# Internal helpers (module-private)
# ---------------------------------------------------------------------------


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
