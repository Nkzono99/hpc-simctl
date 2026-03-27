"""Slurm job state queries via squeue and sacct."""

from __future__ import annotations

from typing import Any


def squeue_status(job_id: str) -> dict[str, Any] | None:
    """Query squeue for a running job's status.

    Args:
        job_id: Slurm job ID.

    Returns:
        Job info dictionary, or None if the job is no longer in squeue.
    """
    raise NotImplementedError


def sacct_status(job_id: str) -> dict[str, Any] | None:
    """Query sacct for a completed/failed job's status.

    Args:
        job_id: Slurm job ID.

    Returns:
        Job accounting dictionary, or None if not found.
    """
    raise NotImplementedError
