"""EMSES (Electromagnetic Particle-in-Cell) simulator adapter.

Handles EMSES TOML configuration (plasma.toml), HDF5/ASCII output
detection, and MPI-based execution via srun.

EMSES now uses TOML configuration (format_version 2 with structured
``[[species]]``, ``[[ptcond.objects]]``, etc.).  Legacy Fortran
namelist (plasma.inp) is no longer required.
"""

from __future__ import annotations

import hashlib
import logging
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

try:
    import tomli_w
except ImportError:
    tomli_w = None  # type: ignore[assignment]

from simctl.adapters._utils import find_venv
from simctl.adapters._utils.toml_utils import apply_dotted_overrides
from simctl.adapters.base import SimulatorAdapter
from simctl.core.validation import ValidationIssue

logger = logging.getLogger(__name__)

INPUT_DIR = "input"
WORK_DIR = "work"

# Domain decomposition: [mpi] group, nodes = [nxdiv, nydiv, nzdiv]
DOMAIN_DECOMP_SECTION = "mpi"
DOMAIN_DECOMP_KEY = "nodes"




def compute_mpi_processes(config: dict[str, Any]) -> int | None:
    """Compute the required MPI process count from domain decomposition.

    In MPIEMSES3D, the ``[mpi]`` section's ``nodes`` parameter
    (a list ``[nxdiv, nydiv, nzdiv]``) defines the domain
    decomposition.  Total processes = product(nodes).

    Args:
        config: Parsed plasma.toml configuration dictionary.

    Returns:
        Total MPI process count, or ``None`` if nodes is not specified.
    """
    mpi_section = config.get(DOMAIN_DECOMP_SECTION, {})
    nodes = mpi_section.get(DOMAIN_DECOMP_KEY)
    if nodes is None:
        return None
    if isinstance(nodes, (list, tuple)):
        result = 1
        for n in nodes:
            result *= int(n)
        return result
    return int(nodes)


class EmseAdapter(SimulatorAdapter):
    """Adapter for the EMSES electromagnetic PIC simulator.

    EMSES uses TOML configuration files (``plasma.toml``) and produces
    HDF5 field data and ASCII time-series diagnostics.

    Class Attributes:
        adapter_name: Registry key for this adapter.
    """

    adapter_name: str = "emses"

    # ------------------------------------------------------------------
    # SimulatorAdapter interface
    # ------------------------------------------------------------------

    @classmethod
    def default_config(cls) -> dict[str, Any]:
        """Return default simulators.toml entry for EMSES."""
        return {
            "adapter": "emses",
            "resolver_mode": "package",
            "executable": "mpiemses3D",
        }

    @classmethod
    def interactive_config(cls) -> dict[str, Any]:
        """Interactively prompt for EMSES configuration."""
        import typer

        typer.echo("\n  Configuring 'emses' simulator (EMSES PIC):")

        resolver_mode = typer.prompt(
            "    Resolver mode (package / local_executable / local_source)",
            default="package",
        )
        executable = typer.prompt(
            "    Executable path or name",
            default="mpiemses3D",
        )

        config: dict[str, Any] = {
            "adapter": "emses",
            "resolver_mode": resolver_mode,
            "executable": executable,
        }

        if resolver_mode == "local_source":
            config["source_repo"] = typer.prompt(
                "    EMSES source repository path", default=""
            )
            config["build_command"] = typer.prompt(
                "    Build command", default="make -j"
            )

        return config

    @classmethod
    def case_template(cls) -> dict[str, str]:
        """Return template files for a new EMSES case."""
        return {
            "case.toml": (
                '[case]\nname = ""\nsimulator = "emses"\n'
                'launcher = "default"\ndescription = ""\n\n'
                "[params]\n"
                '# "tmgrid.nx" = 64\n'
                '# "tmgrid.ny" = 64\n'
                '# "tmgrid.nz" = 64\n'
                '# "tmgrid.dt" = 1.0\n'
                '# "jobcon.nstep" = 10000\n\n'
                "[job]\n"
                'partition = ""\nnodes = 1\nntasks = 1\n'
                'walltime = "01:00:00"\n'
            ),
            "plasma.toml": (
                "# EMSES plasma configuration\n"
                "# See EMSES documentation for full parameter reference\n\n"
                "[jobcon]\n"
                "nstep = 10000\n\n"
                "[tmgrid]\n"
                "nx = 64\nny = 64\nnz = 64\n"
                "dt = 1.0\n\n"
                "[[species]]\n"
                'name = "electron"\n'
                "# charge, mass, temperature, density, etc.\n\n"
                "[emfield]\n"
                "# External field configuration\n"
            ),
        }

    @classmethod
    def pip_packages(cls) -> list[str]:
        """Return pip packages for EMSES (simulator + analysis tools)."""
        return [
            "MPIEMSES3D @ git+https://github.com/CS12-Laboratory/MPIEMSES3D.git",
            "emout",
            "h5py",
            "matplotlib",
            "numpy",
        ]

    @classmethod
    def doc_repos(cls) -> list[tuple[str, str]]:
        """Return documentation repos for EMSES."""
        return [
            (
                "https://github.com/CS12-Laboratory/MPIEMSES3D.git",
                "MPIEMSES3D",
            ),
        ]

    @classmethod
    def knowledge_sources(cls) -> dict[str, list[str]]:
        """Return knowledge-relevant file patterns for EMSES repos."""
        return {
            "MPIEMSES3D": [
                "README.md",
                "docs/**/*.md",
                "schemas/*.json",
                "examples/**/*.toml",
                "simctl/index.toml",
                "simctl/**/*.toml",
                "simctl/**/*.md",
            ],
        }

    @classmethod
    def parameter_schema(cls) -> dict[str, dict[str, Any]]:
        """Return EMSES parameter schema."""
        return {
            "jobcon.nstep": {
                "type": "int",
                "unit": "",
                "description": "Total simulation time steps",
                "range": [1, None],
                "default": 10000,
                "constraints": [],
                "interdependencies": [],
            },
            "tmgrid.dt": {
                "type": "float",
                "unit": "1/omega_pe",
                "description": "Time step in normalized units",
                "range": [0.0, None],
                "default": 1.0,
                "constraints": ["cfl_condition"],
                "derived_from": "Must satisfy dt < dx / cv",
                "interdependencies": [
                    "tmgrid.nx",
                    "plasma.cv",
                ],
            },
            "tmgrid.nx": {
                "type": "int",
                "unit": "cells",
                "description": "Grid cells in X direction",
                "range": [1, None],
                "default": 64,
                "constraints": ["debye_resolution", "grid_divisibility"],
                "interdependencies": ["mpi.nodes"],
            },
            "tmgrid.ny": {
                "type": "int",
                "unit": "cells",
                "description": "Grid cells in Y direction",
                "range": [1, None],
                "default": 64,
                "constraints": ["debye_resolution", "grid_divisibility"],
                "interdependencies": ["mpi.nodes"],
            },
            "tmgrid.nz": {
                "type": "int",
                "unit": "cells",
                "description": "Grid cells in Z direction",
                "range": [1, None],
                "default": 64,
                "constraints": ["debye_resolution", "grid_divisibility"],
                "interdependencies": ["mpi.nodes"],
            },
            "plasma.cv": {
                "type": "float",
                "unit": "dx/dt_norm",
                "description": "Speed of light in normalized units",
                "range": [0.0, None],
                "default": 1.0,
                "constraints": ["cfl_condition"],
                "interdependencies": ["tmgrid.dt"],
            },
            "mpi.nodes": {
                "type": "list[int]",
                "unit": "",
                "description": (
                    "Domain decomposition [nxdiv, nydiv, nzdiv]. "
                    "Product must equal ntasks."
                ),
                "range": [1, None],
                "constraints": [
                    "domain_decomp_consistency",
                    "grid_divisibility",
                ],
                "interdependencies": [
                    "tmgrid.nx",
                    "tmgrid.ny",
                    "tmgrid.nz",
                ],
            },
            "species.N.wp": {
                "type": "float",
                "unit": "omega_pe",
                "description": "Plasma frequency of species N",
                "range": [0.0, None],
                "derived_from": "sqrt(n * q^2 / (m * eps0))",
                "constraints": ["debye_resolution"],
                "interdependencies": ["species.N.qm", "tmgrid.nx"],
            },
            "species.N.qm": {
                "type": "float",
                "unit": "e/m_e",
                "description": "Charge-to-mass ratio of species N",
                "interdependencies": ["species.N.wp"],
            },
            "species.N.npin": {
                "type": "int",
                "unit": "",
                "description": "Number of macro-particles for species N",
                "range": [0, None],
            },
            "emfield.ex0": {
                "type": "float",
                "unit": "normalized",
                "description": "External electric field (X)",
                "default": 0.0,
            },
            "emfield.bx0": {
                "type": "float",
                "unit": "normalized",
                "description": "External magnetic field (X)",
                "default": 0.0,
            },
        }

    def validate_params(
        self,
        case_data: dict[str, Any],
    ) -> list[ValidationIssue]:
        """Validate EMSES parameters against physics constraints.

        Checks: CFL condition, Debye length resolution, domain
        decomposition consistency, and grid divisibility.
        """
        issues: list[ValidationIssue] = []
        config = self._resolve_config(case_data)
        if not config:
            return issues

        tmgrid = config.get("tmgrid", {})
        plasma = config.get("plasma", {})
        mpi_sec = config.get(DOMAIN_DECOMP_SECTION, {})
        species_list = config.get("species", [])

        dt = tmgrid.get("dt")
        nx = tmgrid.get("nx")
        ny = tmgrid.get("ny")
        nz = tmgrid.get("nz")
        cv = plasma.get("cv", 1.0)

        # CFL condition: dt * cv < dx (dx = 1.0 in normalized units)
        if dt is not None and cv is not None:
            cfl_ratio = float(dt) * float(cv)
            if cfl_ratio >= 1.0:
                issues.append(ValidationIssue(
                    severity="error",
                    message=(
                        f"CFL condition violated: dt*cv = {cfl_ratio:.3f} >= 1.0. "
                        f"Reduce dt below {1.0 / float(cv):.3f}."
                    ),
                    parameter="tmgrid.dt",
                    constraint_name="cfl_condition",
                    details={
                        "dt": dt,
                        "cv": cv,
                        "cfl_ratio": cfl_ratio,
                        "max_dt": 1.0 / float(cv),
                    },
                ))
            elif cfl_ratio > 0.8:
                issues.append(ValidationIssue(
                    severity="warning",
                    message=(
                        f"CFL ratio dt*cv = {cfl_ratio:.3f} is close to "
                        f"stability limit (1.0). Consider reducing dt."
                    ),
                    parameter="tmgrid.dt",
                    constraint_name="cfl_condition",
                    details={"cfl_ratio": cfl_ratio},
                ))

        # Debye length resolution check
        for i, sp in enumerate(species_list):
            wp = sp.get("wp")
            vdthz = sp.get("vdthz") or sp.get("vdth", {}).get("z")
            if wp and vdthz and float(wp) > 0:
                debye = float(vdthz) / float(wp)
                # dx = 1.0 in normalized units; want debye >= ~0.5 dx
                if debye < 0.5:
                    issues.append(ValidationIssue(
                        severity="warning",
                        message=(
                            f"Species {i}: Debye length ({debye:.3f} dx) "
                            f"is under-resolved by grid (dx=1). "
                            f"Increase grid resolution or reduce density."
                        ),
                        parameter=f"species.{i}.wp",
                        constraint_name="debye_resolution",
                        details={
                            "species_index": i,
                            "debye_length": debye,
                            "wp": float(wp),
                            "vdthz": float(vdthz),
                        },
                    ))

        # Domain decomposition consistency
        nodes = mpi_sec.get(DOMAIN_DECOMP_KEY)
        if nodes and isinstance(nodes, (list, tuple)):
            total_procs = 1
            for n in nodes:
                total_procs *= int(n)

            # Grid divisibility
            dims = [("nx", nx), ("ny", ny), ("nz", nz)]
            for idx, (dim_name, dim_val) in enumerate(dims):
                if dim_val is not None and idx < len(nodes):
                    ndiv = int(nodes[idx])
                    if int(dim_val) % ndiv != 0:
                        issues.append(ValidationIssue(
                            severity="error",
                            message=(
                                f"Grid {dim_name}={dim_val} is not "
                                f"divisible by MPI decomposition "
                                f"nodes[{idx}]={ndiv}."
                            ),
                            parameter=f"tmgrid.{dim_name}",
                            constraint_name="grid_divisibility",
                            details={
                                "dimension": dim_name,
                                "grid_size": int(dim_val),
                                "mpi_division": ndiv,
                            },
                        ))

        return issues

    @staticmethod
    def _resolve_config(case_data: dict[str, Any]) -> dict[str, Any]:
        """Load template config and apply param overrides."""
        case_section = case_data.get("case", {})
        params = case_data.get("params", {})
        config: dict[str, Any] = {}

        case_dir_str = case_section.get("case_dir", "")
        if case_dir_str:
            candidate = Path(case_dir_str) / "plasma.toml"
            if candidate.is_file():
                with open(candidate, "rb") as f:
                    config = tomllib.load(f)

        if params and config:
            config = apply_dotted_overrides(config, params)

        return config

    @classmethod
    def agent_guide(cls) -> str:
        """Return AI agent guide for EMSES."""
        return """\
### EMSES (Electromagnetic Particle-in-Cell Simulator)

#### 概要
EMSES は 3D 電磁粒子シミュレーション (PIC) コード。
MPI 並列で実行し、電磁場と荷電粒子の自己無撞着な時間発展を計算する。

#### 入力ファイル
- **`input/plasma.toml`** — メイン設定ファイル (TOML 形式)
  - `[jobcon]`: `nstep` (総ステップ数) が最重要パラメータ
  - `[tmgrid]`: `nx`, `ny`, `nz` (グリッド数), `dt` (時間刻み)
  - `[[species]]`: 粒子種の定義 (質量比, 温度, 密度 etc.)
  - `[emfield]`: 外部磁場・電場の設定
  - `[[ptcond.objects]]`: 境界条件・導体オブジェクト

#### 出力ファイル (`work/` 以下)
- `*.h5` — HDF5 形式の電磁場データ (ex, ey, ez, bx, by, bz, etc.)
- `energy` — エネルギー時系列 (ASCII)。最終行のステップ番号で完了判定
- `SNAPSHOT1/esdat*.h5` — リスタート用スナップショット
- 各種診断ファイル: `ewave`, `chgacm1`, `influx`, `icur` 等

#### 完了判定
- `work/energy` の最終行のステップ番号 ≥ `nstep` → completed
- stderr に "error", "segmentation fault", "killed" → failed

#### パラメータサーベイでよく変えるパラメータ
- `tmgrid.dt`, `tmgrid.nx/ny/nz`
- `species[0].temperature`, `species[0].density`
- `emfield.ex0`, `emfield.bx0` (外部場)
- `jobcon.nstep`

#### ドキュメント・参考
- EMSES ソースリポジトリの README / docs/
- `plasma.toml` のスキーマは `format_version = 2` (structured TOML)
- パラメータの dot 記法例: `tmgrid.nx=128`, `species.0.temperature=1.0e6`

#### 実行コマンド
```
srun mpiemses3D plasma.toml
```
"""

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

        Reads ``plasma.toml`` from the case directory, applies parameter
        overrides via dot-notation, and writes to ``<run_dir>/input/plasma.toml``.

        Args:
            case_data: Merged case/survey parameters.  Expects a
                ``case`` section with ``case_dir`` pointing to the
                template directory, and an optional ``params`` section.
            run_dir: Target run directory.

        Returns:
            List of relative paths to generated input files.

        Raises:
            ValueError: If the case section is missing.
            RuntimeError: If ``tomli_w`` is not installed.
        """
        case_section = case_data.get("case", {})
        if not case_section:
            msg = "case_data must contain a 'case' section"
            raise ValueError(msg)

        params = case_data.get("params", {})
        input_dir = run_dir / INPUT_DIR
        input_dir.mkdir(parents=True, exist_ok=True)

        created: list[str] = []

        # Locate template plasma.toml from case directory
        case_dir_str = case_section.get("case_dir", "")
        template_config: dict[str, Any] = {}

        if case_dir_str:
            case_dir = Path(case_dir_str)
            # Look in input/ subdirectory first, then case root for compat
            for candidate in (case_dir / "input" / "plasma.toml", case_dir / "plasma.toml"):
                if candidate.is_file():
                    with open(candidate, "rb") as f:
                        template_config = tomllib.load(f)
                    break

        # Also check explicit input_files list
        input_files: list[str] = case_section.get("input_files", [])
        for src_str in input_files:
            src = Path(src_str)
            if src.suffix == ".toml" and src.is_file():
                if not template_config:
                    with open(src, "rb") as f:
                        template_config = tomllib.load(f)
                elif src.name != "plasma.toml":
                    dest = input_dir / src.name
                    shutil.copy2(src, dest)
                    created.append(str(dest.relative_to(run_dir)))

        # Apply parameter overrides
        if params and template_config:
            template_config = apply_dotted_overrides(template_config, params)

        # Write plasma.toml
        if template_config:
            if tomli_w is None:
                msg = "tomli_w is required to write TOML files"
                raise RuntimeError(msg)
            plasma_toml = input_dir / "plasma.toml"
            with open(plasma_toml, "wb") as f:
                tomli_w.dump(template_config, f)
            created.append(str(plasma_toml.relative_to(run_dir)))

        # Copy additional input files (e.g., mesh files)
        for src_str in input_files:
            src = Path(src_str)
            if not src.is_file():
                logger.warning("Input file not found, skipping: %s", src)
                continue
            if src.suffix == ".toml":
                continue  # Already handled
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

        venv_path = simulator_config.get("venv_path", "")
        if not venv_path:
            found = find_venv(Path.cwd())
            if found:
                venv_path = str(found)
        if venv_path:
            runtime["venv_path"] = venv_path

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

        Returns a command that runs ``mpiemses3D`` with ``plasma.toml``.

        Args:
            runtime_info: Output from :meth:`resolve_runtime`.
            run_dir: The run directory.

        Returns:
            Command as a list of strings.
        """
        executable = runtime_info.get("executable", "mpiemses3D")
        # Path relative to work/ (sbatch --chdir=work)
        plasma_toml = f"../{INPUT_DIR}/plasma.toml"
        return [executable, plasma_toml]

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
            outputs["hdf5_fields"] = [str(f.relative_to(run_dir)) for f in h5_files]

        # ASCII diagnostics (non-HDF5, non-log files directly in work/)
        log_patterns = {"*.out", "*.err", "*.log"}
        diag_files: list[str] = []
        for f in sorted(work_dir.iterdir()):
            if not f.is_file() or f.suffix == ".h5":
                continue
            if any(f.match(p) for p in log_patterns):
                continue
            diag_files.append(str(f.relative_to(run_dir)))
        if diag_files:
            outputs["diagnostics"] = diag_files

        # SNAPSHOT data
        snapshot_dir = work_dir / "SNAPSHOT1"
        if snapshot_dir.is_dir():
            snap_files = sorted(snapshot_dir.glob("esdat*.h5"))
            if snap_files:
                outputs["snapshots"] = [str(f.relative_to(run_dir)) for f in snap_files]

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
            k: len(v) if isinstance(v, list) else 1 for k, v in outputs.items()
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

        # Simulation parameters from plasma.toml
        config = self._load_input_config(run_dir)
        if config:
            tmgrid = config.get("tmgrid", {})
            for key in ("nx", "ny", "nz", "dt"):
                if key in tmgrid:
                    summary[key] = tmgrid[key]
            jobcon = config.get("jobcon", {})
            if "nstep" in jobcon:
                summary["nstep"] = jobcon["nstep"]

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
        """Return setup commands for the EMSES job script."""
        input_dir = run_dir / INPUT_DIR
        return [
            f"cp {input_dir}/plasma.toml . 2>/dev/null || true",
            "rm -f *_0000.h5",
            "date",
        ]

    def get_post_commands(self) -> list[str]:
        """Return post-execution commands."""
        return ["date"]

    def get_modules(self) -> list[str]:
        """Return default module names for EMSES.

        Returns empty list — modules are now managed via sites/*.toml
        and simulators.toml, not hardcoded in the adapter.
        """
        return []

    def get_extra_env(self) -> dict[str, str]:
        """Return default environment variables for EMSES."""
        return {"EMSES_DEBUG": "no"}

    def setup_continuation(
        self,
        source_dir: Path,
        new_dir: Path,
        nstep_override: int | None = None,
    ) -> dict[str, Any]:
        """Set up EMSES continuation from snapshot.

        Links SNAPSHOT1 from source as SNAPSHOT0 in new run,
        and updates jobcon.jobnum for restart.

        Args:
            source_dir: Completed run directory.
            new_dir: New run directory.
            nstep_override: Override nstep if given.

        Returns:
            Info dict with continuation details.
        """
        info: dict[str, Any] = {}
        work_dir = new_dir / WORK_DIR
        work_dir.mkdir(parents=True, exist_ok=True)

        # Link SNAPSHOT1 -> SNAPSHOT0
        source_snapshot = source_dir / WORK_DIR / "SNAPSHOT1"
        if source_snapshot.is_dir():
            target_link = work_dir / "SNAPSHOT0"
            if not target_link.exists():
                target_link.symlink_to(source_snapshot.resolve())
                info["snapshot_link"] = f"SNAPSHOT0 -> {source_snapshot}"

        # Update plasma.toml for restart
        plasma_toml = new_dir / INPUT_DIR / "plasma.toml"
        if plasma_toml.is_file() and tomli_w is not None:
            with open(plasma_toml, "rb") as f:
                config = tomllib.load(f)

            # Set jobnum = [1, 1] for restart
            if "jobcon" not in config:
                config["jobcon"] = {}
            config["jobcon"]["jobnum"] = [1, 1]
            info["jobnum"] = [1, 1]

            if nstep_override is not None:
                config["jobcon"]["nstep"] = nstep_override
                info["nstep"] = nstep_override

            with open(plasma_toml, "wb") as f:
                tomli_w.dump(config, f)

        return info

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @staticmethod
    def _load_input_config(run_dir: Path) -> dict[str, Any]:
        """Load the plasma.toml from the run's input directory."""
        plasma_toml = run_dir / INPUT_DIR / "plasma.toml"
        if plasma_toml.is_file():
            try:
                with open(plasma_toml, "rb") as f:
                    return tomllib.load(f)
            except (tomllib.TOMLDecodeError, OSError):
                pass
        return {}

    @staticmethod
    def _get_expected_nstep(run_dir: Path) -> int | None:
        """Read ``nstep`` from the run's plasma.toml."""
        plasma_toml = run_dir / INPUT_DIR / "plasma.toml"
        if plasma_toml.is_file():
            try:
                with open(plasma_toml, "rb") as f:
                    config = tomllib.load(f)
                return int(config.get("jobcon", {}).get("nstep", 0)) or None
            except (tomllib.TOMLDecodeError, ValueError, OSError):
                pass
        return None
