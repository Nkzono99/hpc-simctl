"""Slurm sbatch submission."""

from __future__ import annotations

from pathlib import Path


def sbatch(job_script: Path) -> str:
    """Submit a job script via sbatch.

    Args:
        job_script: Path to the job.sh file.

    Returns:
        The Slurm job_id as a string.
    """
    raise NotImplementedError
