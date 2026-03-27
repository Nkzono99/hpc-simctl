"""Slurm job state queries via squeue and sacct.

Provides functions to query active and historical job states and map them to
simctl ``RunState`` values.  All subprocess calls go through an injectable
``CommandRunner`` callable so that tests never invoke real Slurm commands.
"""

from __future__ import annotations

from simctl.core.state import RunState
from simctl.slurm.submit import (
    CommandResult,
    CommandRunner,
    SlurmNotFoundError,
    _default_runner,
)

# ---------------------------------------------------------------------------
# Slurm state -> simctl RunState mapping
# ---------------------------------------------------------------------------

_SLURM_STATE_MAP: dict[str, RunState] = {
    # Active / queued
    "PENDING": RunState.SUBMITTED,
    "CONFIGURING": RunState.RUNNING,
    "RUNNING": RunState.RUNNING,
    "COMPLETING": RunState.RUNNING,
    "SUSPENDED": RunState.RUNNING,
    "REQUEUED": RunState.SUBMITTED,
    # Successful termination
    "COMPLETED": RunState.COMPLETED,
    # Failure modes
    "FAILED": RunState.FAILED,
    "NODE_FAIL": RunState.FAILED,
    "OUT_OF_MEMORY": RunState.FAILED,
    "TIMEOUT": RunState.FAILED,
    "PREEMPTED": RunState.FAILED,
    "BOOT_FAIL": RunState.FAILED,
    "DEADLINE": RunState.FAILED,
    # Cancellation
    "CANCELLED": RunState.CANCELLED,
}


class SlurmQueryError(RuntimeError):
    """Raised when a Slurm query command fails unexpectedly."""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def map_slurm_state(slurm_state: str) -> RunState:
    """Map a raw Slurm job state string to a simctl ``RunState``.

    Slurm may append qualifiers like ``CANCELLED by 1000`` -- only the first
    word is used for the lookup.

    Args:
        slurm_state: Raw state string from squeue or sacct (e.g.
            ``"RUNNING"``, ``"CANCELLED by 1000"``).

    Returns:
        The corresponding ``RunState``.

    Raises:
        SlurmQueryError: If the state is not recognised.
    """
    # Take first token to handle "CANCELLED by UID" variants
    key = slurm_state.strip().split()[0].rstrip("+")
    try:
        return _SLURM_STATE_MAP[key]
    except KeyError:
        raise SlurmQueryError(f"Unknown Slurm job state: {slurm_state!r}") from None


# ---------------------------------------------------------------------------
# squeue
# ---------------------------------------------------------------------------


def squeue_status(
    job_id: str,
    *,
    runner: CommandRunner | None = None,
) -> str | None:
    """Query ``squeue`` for an active job's state.

    Args:
        job_id: Slurm job ID.
        runner: Optional command runner for testing.

    Returns:
        The raw Slurm state string (e.g. ``"RUNNING"``) if the job is still
        in the queue, or ``None`` if it has left the queue.

    Raises:
        SlurmNotFoundError: If ``squeue`` is not on PATH.
        SlurmQueryError: If squeue returns a non-zero exit code.
    """
    run = runner or _default_runner
    cmd = [
        "squeue",
        "--job",
        job_id,
        "--noheader",
        "--format=%T",
    ]

    try:
        result: CommandResult = run(cmd)
    except SlurmNotFoundError:
        raise

    if result.returncode != 0:
        # squeue returns non-zero when the job is not found on some clusters
        if "Invalid job id" in result.stderr:
            return None
        raise SlurmQueryError(
            f"squeue failed (exit {result.returncode}):\n{result.stderr.strip()}"
        )

    state = result.stdout.strip()
    if not state:
        return None
    return state


# ---------------------------------------------------------------------------
# sacct
# ---------------------------------------------------------------------------


def sacct_status(
    job_id: str,
    *,
    runner: CommandRunner | None = None,
) -> dict[str, str] | None:
    """Query ``sacct`` for a historical job's state and exit code.

    Uses ``--parsable2 --noheader`` with explicit format fields for reliable
    parsing.

    Args:
        job_id: Slurm job ID.
        runner: Optional command runner for testing.

    Returns:
        A dictionary with keys ``"state"`` and ``"exit_code"`` if the job is
        found, or ``None`` if sacct has no record.

    Raises:
        SlurmNotFoundError: If ``sacct`` is not on PATH.
        SlurmQueryError: If sacct returns a non-zero exit code.
    """
    run = runner or _default_runner
    cmd = [
        "sacct",
        "--jobs",
        job_id,
        "--noheader",
        "--parsable2",
        "--format=JobID,State,ExitCode",
    ]

    try:
        result: CommandResult = run(cmd)
    except SlurmNotFoundError:
        raise

    if result.returncode != 0:
        raise SlurmQueryError(
            f"sacct failed (exit {result.returncode}):\n{result.stderr.strip()}"
        )

    # sacct may return multiple lines (one per step).  We want the "batch"
    # line or the main job line (the one whose JobID matches exactly).
    for line in result.stdout.strip().splitlines():
        parts = line.split("|")
        if len(parts) < 3:
            continue
        sacct_job_id, state, exit_code = parts[0], parts[1], parts[2]
        # Match the main job entry (not sub-steps like "12345.batch")
        if sacct_job_id.strip() == job_id:
            return {"state": state.strip(), "exit_code": exit_code.strip()}

    return None


# ---------------------------------------------------------------------------
# Combined query
# ---------------------------------------------------------------------------


def query_job_status(
    job_id: str,
    *,
    runner: CommandRunner | None = None,
) -> RunState:
    """Determine the current simctl state of a Slurm job.

    Strategy: try ``squeue`` first (cheap, covers active jobs).  If the job
    is no longer in the queue, fall back to ``sacct`` (covers completed /
    historical jobs).

    Args:
        job_id: Slurm job ID.
        runner: Optional command runner for testing.

    Returns:
        The simctl ``RunState`` corresponding to the job's Slurm state.

    Raises:
        SlurmNotFoundError: If Slurm commands are not on PATH.
        SlurmQueryError: If neither squeue nor sacct can find the job, or
            if the returned state is unrecognised.
    """
    # 1. Try squeue (active jobs)
    sq_state = squeue_status(job_id, runner=runner)
    if sq_state is not None:
        return map_slurm_state(sq_state)

    # 2. Fall back to sacct (historical jobs)
    sa_info = sacct_status(job_id, runner=runner)
    if sa_info is not None:
        return map_slurm_state(sa_info["state"])

    raise SlurmQueryError(
        f"Job {job_id} not found in squeue or sacct. "
        "It may have been purged from the Slurm database."
    )
