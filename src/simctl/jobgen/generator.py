"""Job script (job.sh) generation.

Generates Slurm batch scripts from run configuration, launcher profile,
and simulator adapter output.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def generate_job_script(
    run_dir: Path,
    job_config: dict[str, Any],
    exec_line: str,
) -> Path:
    """Generate a job.sh script for Slurm submission.

    Args:
        run_dir: Target run directory.
        job_config: Job parameters (partition, nodes, ntasks, walltime).
        exec_line: The execution line produced by the launcher.

    Returns:
        Path to the generated job.sh file.
    """
    raise NotImplementedError
