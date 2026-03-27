"""Tests for Slurm job state query module."""

from __future__ import annotations

import pytest

from simctl.core.state import RunState
from simctl.slurm.query import (
    SlurmQueryError,
    map_slurm_state,
    query_job_status,
    sacct_status,
    squeue_status,
)
from simctl.slurm.submit import CommandResult, SlurmNotFoundError

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _runner(
    returncode: int = 0,
    stdout: str = "",
    stderr: str = "",
) -> callable:
    """Return a mock runner that always returns the given result."""

    def run(cmd: list[str]) -> CommandResult:
        return CommandResult(returncode=returncode, stdout=stdout, stderr=stderr)

    return run


# ---------------------------------------------------------------------------
# map_slurm_state
# ---------------------------------------------------------------------------


class TestMapSlurmState:
    """Tests for the Slurm-to-simctl state mapping."""

    @pytest.mark.parametrize(
        ("slurm_state", "expected"),
        [
            ("PENDING", RunState.SUBMITTED),
            ("RUNNING", RunState.RUNNING),
            ("CONFIGURING", RunState.RUNNING),
            ("COMPLETING", RunState.RUNNING),
            ("COMPLETED", RunState.COMPLETED),
            ("FAILED", RunState.FAILED),
            ("NODE_FAIL", RunState.FAILED),
            ("OUT_OF_MEMORY", RunState.FAILED),
            ("TIMEOUT", RunState.FAILED),
            ("CANCELLED", RunState.CANCELLED),
            ("PREEMPTED", RunState.FAILED),
            ("REQUEUED", RunState.SUBMITTED),
        ],
    )
    def test_known_states(self, slurm_state: str, expected: RunState) -> None:
        assert map_slurm_state(slurm_state) == expected

    def test_cancelled_by_user(self) -> None:
        """CANCELLED by UID variant should still map to CANCELLED."""
        assert map_slurm_state("CANCELLED by 1000") == RunState.CANCELLED

    def test_state_with_plus_suffix(self) -> None:
        """States like COMPLETING+ should be handled."""
        assert map_slurm_state("COMPLETING+") == RunState.RUNNING

    def test_unknown_state_raises(self) -> None:
        with pytest.raises(SlurmQueryError, match="Unknown Slurm job state"):
            map_slurm_state("TOTALLY_UNKNOWN")


# ---------------------------------------------------------------------------
# squeue_status
# ---------------------------------------------------------------------------


class TestSqueueStatus:
    """Tests for squeue_status."""

    def test_running_job(self) -> None:
        result = squeue_status("12345", runner=_runner(stdout="RUNNING\n"))
        assert result == "RUNNING"

    def test_pending_job(self) -> None:
        result = squeue_status("12345", runner=_runner(stdout="PENDING\n"))
        assert result == "PENDING"

    def test_job_not_in_queue(self) -> None:
        """Empty output means the job left the queue."""
        result = squeue_status("12345", runner=_runner(stdout=""))
        assert result is None

    def test_invalid_job_id_stderr(self) -> None:
        """Some clusters return non-zero with 'Invalid job id'."""
        result = squeue_status(
            "99999",
            runner=_runner(
                returncode=1,
                stderr="slurm_load_jobs error: Invalid job id",
            ),
        )
        assert result is None

    def test_other_error_raises(self) -> None:
        with pytest.raises(SlurmQueryError, match="squeue failed"):
            squeue_status(
                "12345",
                runner=_runner(returncode=1, stderr="Connection refused"),
            )


# ---------------------------------------------------------------------------
# sacct_status
# ---------------------------------------------------------------------------


class TestSacctStatus:
    """Tests for sacct_status."""

    def test_completed_job(self) -> None:
        stdout = "12345|COMPLETED|0:0\n12345.batch|COMPLETED|0:0\n"
        result = sacct_status("12345", runner=_runner(stdout=stdout))
        assert result is not None
        assert result["state"] == "COMPLETED"
        assert result["exit_code"] == "0:0"

    def test_failed_job(self) -> None:
        stdout = "12345|FAILED|1:0\n12345.batch|FAILED|1:0\n"
        result = sacct_status("12345", runner=_runner(stdout=stdout))
        assert result is not None
        assert result["state"] == "FAILED"
        assert result["exit_code"] == "1:0"

    def test_cancelled_job(self) -> None:
        stdout = "12345|CANCELLED by 1000|0:0\n"
        result = sacct_status("12345", runner=_runner(stdout=stdout))
        assert result is not None
        assert result["state"] == "CANCELLED by 1000"

    def test_job_not_found(self) -> None:
        result = sacct_status("12345", runner=_runner(stdout=""))
        assert result is None

    def test_sacct_error_raises(self) -> None:
        with pytest.raises(SlurmQueryError, match="sacct failed"):
            sacct_status(
                "12345",
                runner=_runner(returncode=1, stderr="Slurm accounting error"),
            )

    def test_ignores_substep_lines(self) -> None:
        """Only the main job line (exact ID match) should be returned."""
        stdout = "12345.batch|COMPLETED|0:0\n12345.extern|COMPLETED|0:0\n"
        result = sacct_status("12345", runner=_runner(stdout=stdout))
        assert result is None

    def test_main_line_present_among_steps(self) -> None:
        stdout = (
            "12345|COMPLETED|0:0\n"
            "12345.batch|COMPLETED|0:0\n"
            "12345.extern|COMPLETED|0:0\n"
        )
        result = sacct_status("12345", runner=_runner(stdout=stdout))
        assert result is not None
        assert result["state"] == "COMPLETED"


# ---------------------------------------------------------------------------
# query_job_status (combined)
# ---------------------------------------------------------------------------


class TestQueryJobStatus:
    """Tests for the combined query_job_status function."""

    def test_active_job_uses_squeue(self) -> None:
        """If squeue returns a state, sacct is not needed."""
        call_log: list[str] = []

        def runner(cmd: list[str]) -> CommandResult:
            call_log.append(cmd[0])
            if cmd[0] == "squeue":
                return CommandResult(0, "RUNNING\n", "")
            return CommandResult(0, "", "")

        state = query_job_status("12345", runner=runner)
        assert state is RunState.RUNNING
        assert "sacct" not in call_log

    def test_completed_job_falls_to_sacct(self) -> None:
        """If squeue returns empty, sacct should be consulted."""

        def runner(cmd: list[str]) -> CommandResult:
            if cmd[0] == "squeue":
                return CommandResult(0, "", "")
            # sacct
            return CommandResult(0, "12345|COMPLETED|0:0\n", "")

        state = query_job_status("12345", runner=runner)
        assert state is RunState.COMPLETED

    def test_failed_job_from_sacct(self) -> None:
        def runner(cmd: list[str]) -> CommandResult:
            if cmd[0] == "squeue":
                return CommandResult(0, "", "")
            return CommandResult(0, "12345|FAILED|1:0\n", "")

        state = query_job_status("12345", runner=runner)
        assert state is RunState.FAILED

    def test_cancelled_from_sacct(self) -> None:
        def runner(cmd: list[str]) -> CommandResult:
            if cmd[0] == "squeue":
                return CommandResult(0, "", "")
            return CommandResult(0, "12345|CANCELLED by 1000|0:0\n", "")

        state = query_job_status("12345", runner=runner)
        assert state is RunState.CANCELLED

    def test_job_purged_raises(self) -> None:
        """If neither squeue nor sacct finds the job, raise."""

        def runner(cmd: list[str]) -> CommandResult:
            return CommandResult(0, "", "")

        with pytest.raises(SlurmQueryError, match="not found in squeue or sacct"):
            query_job_status("12345", runner=runner)

    def test_slurm_not_found_propagates(self) -> None:
        def runner(cmd: list[str]) -> CommandResult:
            raise SlurmNotFoundError("squeue not found")

        with pytest.raises(SlurmNotFoundError):
            query_job_status("12345", runner=runner)
