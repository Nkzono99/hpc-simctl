"""Tests for Slurm submission module."""

from __future__ import annotations

from pathlib import Path

import pytest

from simctl.slurm.submit import (
    CommandResult,
    SlurmNotFoundError,
    SlurmSubmitError,
    parse_job_id,
    sbatch_submit,
)

# ---------------------------------------------------------------------------
# parse_job_id
# ---------------------------------------------------------------------------


class TestParseJobId:
    """Tests for sbatch output parsing."""

    def test_standard_output(self) -> None:
        assert parse_job_id("Submitted batch job 12345\n") == "12345"

    def test_large_job_id(self) -> None:
        assert parse_job_id("Submitted batch job 9999999") == "9999999"

    def test_with_extra_whitespace(self) -> None:
        assert parse_job_id("  Submitted batch job 42  \n") == "42"

    def test_empty_output_raises(self) -> None:
        with pytest.raises(SlurmSubmitError, match="Could not parse job ID"):
            parse_job_id("")

    def test_garbage_output_raises(self) -> None:
        with pytest.raises(SlurmSubmitError, match="Could not parse job ID"):
            parse_job_id("sbatch: error: Batch job submission failed")

    def test_partial_match_raises(self) -> None:
        with pytest.raises(SlurmSubmitError, match="Could not parse job ID"):
            parse_job_id("Submitted batch job")


# ---------------------------------------------------------------------------
# sbatch_submit with mock runner
# ---------------------------------------------------------------------------


def _make_runner(
    returncode: int = 0,
    stdout: str = "",
    stderr: str = "",
) -> tuple[list[list[str]], callable]:
    """Create a mock runner that records calls and returns a fixed result."""
    calls: list[list[str]] = []

    def runner(cmd: list[str]) -> CommandResult:
        calls.append(cmd)
        return CommandResult(returncode=returncode, stdout=stdout, stderr=stderr)

    return calls, runner


class TestSbatchSubmit:
    """Tests for the sbatch_submit function."""

    def test_success(self, tmp_path: Path) -> None:
        job_sh = tmp_path / "submit" / "job.sh"
        job_sh.parent.mkdir()
        job_sh.write_text("#!/bin/bash\necho hello")
        work_dir = tmp_path / "work"
        work_dir.mkdir()

        calls, runner = _make_runner(
            stdout="Submitted batch job 67890\n",
        )
        job_id = sbatch_submit(job_sh, work_dir, runner=runner)

        assert job_id == "67890"
        assert len(calls) == 1
        assert calls[0][0] == "sbatch"
        assert f"--chdir={work_dir}" in calls[0][1]
        assert str(job_sh) in calls[0]

    def test_script_not_found(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError, match="Job script not found"):
            sbatch_submit(
                tmp_path / "nonexistent.sh",
                tmp_path,
                runner=_make_runner()[1],
            )

    def test_nonzero_exit(self, tmp_path: Path) -> None:
        job_sh = tmp_path / "job.sh"
        job_sh.write_text("#!/bin/bash")

        _, runner = _make_runner(
            returncode=1,
            stderr="sbatch: error: invalid partition\n",
        )
        with pytest.raises(SlurmSubmitError, match="invalid partition"):
            sbatch_submit(job_sh, tmp_path, runner=runner)

    def test_unparseable_stdout(self, tmp_path: Path) -> None:
        job_sh = tmp_path / "job.sh"
        job_sh.write_text("#!/bin/bash")

        _, runner = _make_runner(stdout="Unexpected output\n")
        with pytest.raises(SlurmSubmitError, match="Could not parse job ID"):
            sbatch_submit(job_sh, tmp_path, runner=runner)

    def test_afterok_dependency(self, tmp_path: Path) -> None:
        """afterok parameter adds --dependency=afterok:<id> to sbatch."""
        job_sh = tmp_path / "job.sh"
        job_sh.write_text("#!/bin/bash\necho hello")
        work_dir = tmp_path / "work"
        work_dir.mkdir()

        calls, runner = _make_runner(stdout="Submitted batch job 99999\n")
        job_id = sbatch_submit(job_sh, work_dir, afterok="12345", runner=runner)

        assert job_id == "99999"
        assert "--dependency=afterok:12345" in calls[0]

    def test_afterok_with_extra_args(self, tmp_path: Path) -> None:
        """afterok and extra_args both appear in the command."""
        job_sh = tmp_path / "job.sh"
        job_sh.write_text("#!/bin/bash")
        work_dir = tmp_path / "work"
        work_dir.mkdir()

        calls, runner = _make_runner(stdout="Submitted batch job 11111\n")
        sbatch_submit(
            job_sh, work_dir,
            afterok="54321",
            extra_args=["--partition=debug"],
            runner=runner,
        )
        cmd = calls[0]
        assert "--dependency=afterok:54321" in cmd
        assert "--partition=debug" in cmd

    def test_slurm_not_found_propagates(self, tmp_path: Path) -> None:
        job_sh = tmp_path / "job.sh"
        job_sh.write_text("#!/bin/bash")

        def runner(cmd: list[str]) -> CommandResult:
            raise SlurmNotFoundError("sbatch not found")

        with pytest.raises(SlurmNotFoundError):
            sbatch_submit(job_sh, tmp_path, runner=runner)
