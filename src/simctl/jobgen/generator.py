"""Job script (job.sh) generation.

Generates Slurm batch scripts from run configuration, launcher profile,
and simulator adapter output.
"""

from __future__ import annotations

import stat
from pathlib import Path
from typing import Any


class JobScriptError(RuntimeError):
    """Raised when job script generation fails due to invalid parameters."""


def generate_job_script(
    run_dir: Path,
    job_config: dict[str, Any],
    exec_line: str,
    *,
    run_id: str = "",
    extra_sbatch: list[str] | None = None,
    extra_env: dict[str, str] | None = None,
    modules: list[str] | None = None,
) -> Path:
    """Generate a ``job.sh`` script for Slurm submission.

    The script is written to ``<run_dir>/submit/job.sh`` and made executable.

    Args:
        run_dir: Target run directory.
        job_config: Job parameters.  Required keys: ``partition``, ``nodes``,
            ``ntasks``, ``walltime``.  Optional: ``job_name``.
        exec_line: The execution line produced by the launcher (e.g.
            ``"srun ./solver input.toml"``).
        run_id: Run identifier used as the default job name if ``job_name``
            is not set in *job_config*.
        extra_sbatch: Additional ``#SBATCH`` lines (without the ``#SBATCH``
            prefix) to include verbatim.
        extra_env: Extra environment variables to export before execution.
        modules: Module names to load (via ``module load``).

    Returns:
        Path to the generated ``submit/job.sh`` file.

    Raises:
        JobScriptError: If required keys are missing from *job_config*.
    """
    _validate_job_config(job_config)

    content = _render_script(
        job_config=job_config,
        exec_line=exec_line,
        run_dir=run_dir,
        run_id=run_id,
        extra_sbatch=extra_sbatch or [],
        extra_env=extra_env or {},
        modules=modules or [],
    )

    return write_job_script(run_dir, content)


def write_job_script(run_dir: Path, content: str) -> Path:
    """Write job script content to ``<run_dir>/submit/job.sh``.

    Creates the ``submit/`` directory if it does not exist and sets the
    executable permission bit on the resulting file.

    Args:
        run_dir: Target run directory.
        content: Full shell script content.

    Returns:
        Path to the written job script.
    """
    submit_dir = run_dir / "submit"
    submit_dir.mkdir(parents=True, exist_ok=True)

    job_sh = submit_dir / "job.sh"
    job_sh.write_text(content)
    job_sh.chmod(job_sh.stat().st_mode | stat.S_IEXEC)
    return job_sh


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_REQUIRED_JOB_KEYS = ("partition", "nodes", "ntasks", "walltime")


def _validate_job_config(job_config: dict[str, Any]) -> None:
    """Ensure all required keys are present in *job_config*.

    Raises:
        JobScriptError: If any required key is missing.
    """
    missing = [k for k in _REQUIRED_JOB_KEYS if k not in job_config]
    if missing:
        raise JobScriptError(f"Missing required job config keys: {', '.join(missing)}")


def _render_script(
    *,
    job_config: dict[str, Any],
    exec_line: str,
    run_dir: Path,
    run_id: str,
    extra_sbatch: list[str],
    extra_env: dict[str, str],
    modules: list[str],
) -> str:
    """Render the complete job script as a string."""
    lines: list[str] = ["#!/bin/bash"]

    # --- SBATCH directives ---
    job_name = job_config.get("job_name", run_id or "simctl-job")
    lines.append(f"#SBATCH --job-name={job_name}")
    lines.append(f"#SBATCH --partition={job_config['partition']}")
    lines.append(f"#SBATCH --nodes={job_config['nodes']}")
    lines.append(f"#SBATCH --ntasks={job_config['ntasks']}")
    lines.append(f"#SBATCH --time={job_config['walltime']}")

    work_dir = run_dir / "work"
    lines.append(f"#SBATCH --output={work_dir / '%j.out'}")
    lines.append(f"#SBATCH --error={work_dir / '%j.err'}")

    for directive in extra_sbatch:
        lines.append(f"#SBATCH {directive}")

    lines.append("")

    # --- Preamble ---
    lines.append("set -euo pipefail")
    lines.append("")

    # Module loads
    if modules:
        for mod in modules:
            lines.append(f"module load {mod}")
        lines.append("")

    # Environment variables
    if extra_env:
        for key, value in sorted(extra_env.items()):
            lines.append(f"export {key}={value!r}")
        lines.append("")

    # --- Change to work directory and execute ---
    lines.append(f"cd {work_dir}")
    lines.append("")
    lines.append(f"exec {exec_line}")
    lines.append("")

    return "\n".join(lines)
