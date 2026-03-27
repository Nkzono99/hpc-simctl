"""Job script (job.sh) generation.

Generates Slurm batch scripts from run configuration, launcher profile,
and simulator adapter output.

Supports two resource specification modes:

- **Standard mode**: ``#SBATCH --nodes`` / ``#SBATCH --ntasks``
- **RSC mode**: ``#SBATCH --rsc p=N:t=T:c=C`` (custom Slurm environments)
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
    setup_commands: list[str] | None = None,
    post_commands: list[str] | None = None,
    resource_style: str = "standard",
    stdout_format: str | None = None,
    stderr_format: str | None = None,
) -> Path:
    """Generate a ``job.sh`` script for Slurm submission.

    The script is written to ``<run_dir>/submit/job.sh`` and made executable.

    Args:
        run_dir: Target run directory.
        job_config: Job parameters.  Required keys: ``partition``,
            ``walltime``.  Optional: ``nodes``, ``ntasks``, ``job_name``.
        exec_line: The execution line produced by the launcher (e.g.
            ``"srun ./solver input.toml"``).
        run_id: Run identifier used as the default job name if ``job_name``
            is not set in *job_config*.
        extra_sbatch: Additional ``#SBATCH`` lines (without the ``#SBATCH``
            prefix) to include verbatim.
        extra_env: Extra environment variables to export before execution.
        modules: Module names to load (via ``module load``).
        setup_commands: Shell commands to run before the main execution
            (e.g. copying files to work/, running preprocessors).
        post_commands: Shell commands to run after the main execution
            (e.g. post-processing, visualization).

    Returns:
        Path to the generated ``submit/job.sh`` file.

    Raises:
        JobScriptError: If required keys are missing from *job_config*.
    """
    _validate_job_config(job_config)

    # Merge modules from job_config and explicit parameter
    all_modules = list(modules or [])
    config_modules = job_config.get("modules", [])
    if isinstance(config_modules, list):
        for m in config_modules:
            if m not in all_modules:
                all_modules.append(m)

    # Merge setup/post commands from job_config and explicit parameter
    all_setup = list(setup_commands or [])
    config_pre = job_config.get("pre_commands", job_config.get("setup_commands", []))
    if isinstance(config_pre, list):
        all_setup.extend(config_pre)

    all_post = list(job_config.get("post_commands", []))
    if post_commands:
        all_post.extend(post_commands)

    content = _render_script(
        job_config=job_config,
        exec_line=exec_line,
        run_dir=run_dir,
        run_id=run_id,
        extra_sbatch=extra_sbatch or [],
        extra_env=extra_env or {},
        modules=all_modules,
        setup_commands=all_setup,
        post_commands=all_post,
        resource_style=resource_style,
        stdout_format=stdout_format,
        stderr_format=stderr_format,
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

_REQUIRED_JOB_KEYS = ("walltime",)


def _validate_job_config(job_config: dict[str, Any]) -> None:
    """Ensure all required keys are present in *job_config*.

    Raises:
        JobScriptError: If any required key is missing.
    """
    missing = [k for k in _REQUIRED_JOB_KEYS if k not in job_config]
    if missing:
        raise JobScriptError(
            f"Missing required job config keys: {', '.join(missing)}"
        )


def _render_script(
    *,
    job_config: dict[str, Any],
    exec_line: str,
    run_dir: Path,
    run_id: str,
    extra_sbatch: list[str],
    extra_env: dict[str, str],
    modules: list[str],
    setup_commands: list[str],
    post_commands: list[str],
    resource_style: str = "standard",
    stdout_format: str | None = None,
    stderr_format: str | None = None,
) -> str:
    """Render the complete job script as a string."""
    lines: list[str] = ["#!/bin/bash"]

    # --- SBATCH directives ---
    partition = job_config.get("partition", "")
    if partition:
        lines.append(f"#SBATCH -p {partition}")

    if resource_style == "rsc":
        # cmaphor-style: --rsc p=N:t=T:c=C
        ntasks = job_config.get("ntasks", 1)
        threads = job_config.get("threads_per_process", 1)
        cores = job_config.get("cores_per_thread", 1)
        lines.append(f"#SBATCH --rsc p={ntasks}:t={threads}:c={cores}")
    else:
        # Standard Slurm directives
        if "nodes" in job_config:
            lines.append(f"#SBATCH --nodes={job_config['nodes']}")
        if "ntasks" in job_config:
            lines.append(f"#SBATCH --ntasks={job_config['ntasks']}")
        if "cpus_per_task" in job_config:
            lines.append(f"#SBATCH --cpus-per-task={job_config['cpus_per_task']}")

    lines.append(f"#SBATCH -t {job_config['walltime']}")

    # stdout / stderr
    work_dir = run_dir / "work"
    if stdout_format:
        lines.append(f"#SBATCH -o {stdout_format}")
    else:
        lines.append(f"#SBATCH --output={work_dir / '%j.out'}")
    if stderr_format:
        lines.append(f"#SBATCH -e {stderr_format}")
    else:
        lines.append(f"#SBATCH --error={work_dir / '%j.err'}")

    job_name = job_config.get("job_name", run_id or "simctl-job")
    if job_name:
        lines.append(f"#SBATCH -J {job_name}")

    for directive in extra_sbatch:
        lines.append(f"#SBATCH {directive}")

    lines.append("")

    # --- Module loads ---
    if modules:
        for mod in modules:
            lines.append(f"module load {mod}")
        lines.append("module list")
        lines.append("")

    # --- Environment variables ---
    if extra_env:
        for key, value in sorted(extra_env.items()):
            lines.append(f"export {key}={value}")
        lines.append("")

    # --- Change to work directory ---
    lines.append(f"cd {work_dir}")
    lines.append("")

    # --- Setup commands (before main execution) ---
    if setup_commands:
        for cmd in setup_commands:
            lines.append(cmd)
        lines.append("")

    # --- Main execution ---
    if post_commands:
        # Cannot use exec if there are post-commands to run
        lines.append(exec_line)
    else:
        lines.append(f"exec {exec_line}")
    lines.append("")

    # --- Post commands (after main execution) ---
    if post_commands:
        for cmd in post_commands:
            lines.append(cmd)
        lines.append("")

    return "\n".join(lines)
