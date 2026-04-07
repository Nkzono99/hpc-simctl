"""Tests for simctl runs status and runs sync CLI commands."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

import tomli_w
from typer.testing import CliRunner

from simctl.cli.main import app
from simctl.core.state import RunState
from simctl.slurm.query import JobStatus

runner = CliRunner()


def _write_manifest(run_dir: Path, data: dict[str, Any]) -> None:
    """Write a manifest.toml into the given run directory."""
    run_dir.mkdir(parents=True, exist_ok=True)
    with open(run_dir / "manifest.toml", "wb") as f:
        tomli_w.dump(data, f)


def _create_run(
    run_dir: Path,
    *,
    run_id: str = "R20260327-0001",
    status: str = "submitted",
    job_id: str = "12345",
) -> None:
    """Create a minimal run directory with manifest."""
    manifest_data: dict[str, Any] = {
        "run": {
            "id": run_id,
            "display_name": "test_run",
            "status": status,
            "created_at": "2026-03-27T13:00:00+09:00",
        },
        "job": {
            "scheduler": "slurm",
            "job_id": job_id,
            "partition": "debug",
        },
    }
    _write_manifest(run_dir, manifest_data)


# ---------------------------------------------------------------------------
# status command tests
# ---------------------------------------------------------------------------


def test_status_shows_run_info(tmp_path: Path) -> None:
    """status should display run_id, state, and job_id."""
    (tmp_path / "simproject.toml").write_text('[project]\nname = "test"\n')
    run_dir = tmp_path / "runs" / "R20260327-0001"
    _create_run(run_dir)

    with (
        patch("simctl.cli.status.Path.cwd", return_value=tmp_path),
        patch(
            "simctl.cli.status.query_job_status",
            return_value=JobStatus(run_state=RunState.RUNNING, slurm_state="RUNNING"),
        ),
    ):
        result = runner.invoke(app, ["runs", "status", str(run_dir)])

    assert result.exit_code == 0
    assert "R20260327-0001" in result.output
    assert "submitted" in result.output
    assert "12345" in result.output
    assert "RUNNING" in result.output


def test_status_no_job_id(tmp_path: Path) -> None:
    """status with no job_id should show 'not submitted'."""
    (tmp_path / "simproject.toml").write_text('[project]\nname = "test"\n')
    run_dir = tmp_path / "runs" / "R20260327-0001"
    _create_run(run_dir, status="created", job_id="")

    with patch("simctl.cli.status.Path.cwd", return_value=tmp_path):
        result = runner.invoke(app, ["runs", "status", str(run_dir)])

    assert result.exit_code == 0
    assert "not submitted" in result.output


def test_status_slurm_unavailable(tmp_path: Path) -> None:
    """status should gracefully handle missing Slurm commands."""
    (tmp_path / "simproject.toml").write_text('[project]\nname = "test"\n')
    run_dir = tmp_path / "runs" / "R20260327-0001"
    _create_run(run_dir)

    from simctl.slurm.submit import SlurmNotFoundError

    with (
        patch("simctl.cli.status.Path.cwd", return_value=tmp_path),
        patch(
            "simctl.cli.status.query_job_status",
            side_effect=SlurmNotFoundError("squeue not found"),
        ),
    ):
        result = runner.invoke(app, ["runs", "status", str(run_dir)])

    assert result.exit_code == 0
    assert "not available" in result.output


def test_status_run_not_found(tmp_path: Path) -> None:
    """status for a non-existent run should error."""
    (tmp_path / "simproject.toml").write_text('[project]\nname = "test"\n')
    (tmp_path / "runs").mkdir()

    with patch("simctl.cli.status.Path.cwd", return_value=tmp_path):
        result = runner.invoke(app, ["runs", "status", "nonexistent"])
    assert result.exit_code != 0


# ---------------------------------------------------------------------------
# sync command tests
# ---------------------------------------------------------------------------


def test_sync_updates_state(tmp_path: Path) -> None:
    """sync should transition state and show old -> new."""
    (tmp_path / "simproject.toml").write_text('[project]\nname = "test"\n')
    run_dir = tmp_path / "runs" / "R20260327-0001"
    _create_run(run_dir, status="submitted", job_id="12345")

    with (
        patch("simctl.cli.status.Path.cwd", return_value=tmp_path),
        patch(
            "simctl.slurm.query.query_job_status",
            return_value=JobStatus(run_state=RunState.RUNNING, slurm_state="RUNNING"),
        ),
    ):
        result = runner.invoke(app, ["runs", "sync", str(run_dir)])

    assert result.exit_code == 0
    assert "submitted" in result.output
    assert "running" in result.output
    assert "->" in result.output

    # Verify manifest was actually updated
    from simctl.core.manifest import read_manifest

    updated = read_manifest(run_dir)
    assert updated.run["status"] == "running"

    # Verify state.json was written
    state_json = run_dir / "status" / "state.json"
    assert state_json.exists()


def test_sync_no_change(tmp_path: Path) -> None:
    """sync should report no change when states match."""
    (tmp_path / "simproject.toml").write_text('[project]\nname = "test"\n')
    run_dir = tmp_path / "runs" / "R20260327-0001"
    _create_run(run_dir, status="running", job_id="12345")

    with (
        patch("simctl.cli.status.Path.cwd", return_value=tmp_path),
        patch(
            "simctl.slurm.query.query_job_status",
            return_value=JobStatus(run_state=RunState.RUNNING, slurm_state="RUNNING"),
        ),
    ):
        result = runner.invoke(app, ["runs", "sync", str(run_dir)])

    assert result.exit_code == 0
    assert "unchanged" in result.output


def test_sync_no_job_id(tmp_path: Path) -> None:
    """sync without a job_id should error."""
    (tmp_path / "simproject.toml").write_text('[project]\nname = "test"\n')
    run_dir = tmp_path / "runs" / "R20260327-0001"
    _create_run(run_dir, status="created", job_id="")

    with patch("simctl.cli.status.Path.cwd", return_value=tmp_path):
        result = runner.invoke(app, ["runs", "sync", str(run_dir)])

    assert result.exit_code != 0
    assert "no job_id" in result.output.lower()


def test_sync_slurm_query_failure(tmp_path: Path) -> None:
    """sync should handle Slurm query failures gracefully."""
    (tmp_path / "simproject.toml").write_text('[project]\nname = "test"\n')
    run_dir = tmp_path / "runs" / "R20260327-0001"
    _create_run(run_dir, status="submitted", job_id="12345")

    from simctl.slurm.query import SlurmQueryError

    with (
        patch("simctl.cli.status.Path.cwd", return_value=tmp_path),
        patch(
            "simctl.slurm.query.query_job_status",
            side_effect=SlurmQueryError("Job not found"),
        ),
    ):
        result = runner.invoke(app, ["runs", "sync", str(run_dir)])

    assert result.exit_code != 0
    assert "query failed" in result.output or "Job not found" in result.output


def test_sync_completed(tmp_path: Path) -> None:
    """sync should transition running -> completed."""
    (tmp_path / "simproject.toml").write_text('[project]\nname = "test"\n')
    run_dir = tmp_path / "runs" / "R20260327-0001"
    _create_run(run_dir, status="running", job_id="12345")

    with (
        patch("simctl.cli.status.Path.cwd", return_value=tmp_path),
        patch(
            "simctl.slurm.query.query_job_status",
            return_value=JobStatus(
                run_state=RunState.COMPLETED, slurm_state="COMPLETED"
            ),
        ),
    ):
        result = runner.invoke(app, ["runs", "sync", str(run_dir)])

    assert result.exit_code == 0
    assert "running" in result.output
    assert "completed" in result.output

    from simctl.core.manifest import read_manifest

    updated = read_manifest(run_dir)
    assert updated.run["status"] == "completed"


# ---------------------------------------------------------------------------
# Bulk sync / status tests (multi-target argument list, survey directory)
# ---------------------------------------------------------------------------


def test_sync_survey_dir_processes_all_runs(tmp_path: Path) -> None:
    """Passing a survey directory syncs every run inside it."""
    (tmp_path / "simproject.toml").write_text('[project]\nname = "test"\n')
    survey = tmp_path / "runs" / "series_x"
    _create_run(
        survey / "R20260327-0001",
        run_id="R20260327-0001",
        status="running",
        job_id="11111",
    )
    _create_run(
        survey / "R20260327-0002",
        run_id="R20260327-0002",
        status="running",
        job_id="22222",
    )

    seen: list[str] = []

    def fake_query(job_id: str, runner=None):  # type: ignore[no-untyped-def]
        seen.append(job_id)
        return JobStatus(run_state=RunState.COMPLETED, slurm_state="COMPLETED")

    with (
        patch("simctl.cli.status.Path.cwd", return_value=tmp_path),
        patch("simctl.slurm.query.query_job_status", side_effect=fake_query),
    ):
        result = runner.invoke(app, ["runs", "sync", str(survey)])

    assert result.exit_code == 0, result.output
    assert "R20260327-0001" in result.output
    assert "R20260327-0002" in result.output
    assert sorted(seen) == ["11111", "22222"]


def test_sync_bulk_skips_runs_without_job_id(tmp_path: Path) -> None:
    """In multi-target mode, runs without job_id are silently skipped."""
    (tmp_path / "simproject.toml").write_text('[project]\nname = "test"\n')
    survey = tmp_path / "runs" / "series_x"
    _create_run(
        survey / "R20260327-0001",
        run_id="R20260327-0001",
        status="created",
        job_id="",
    )
    _create_run(
        survey / "R20260327-0002",
        run_id="R20260327-0002",
        status="running",
        job_id="22222",
    )

    with (
        patch("simctl.cli.status.Path.cwd", return_value=tmp_path),
        patch(
            "simctl.slurm.query.query_job_status",
            return_value=JobStatus(
                run_state=RunState.COMPLETED, slurm_state="COMPLETED"
            ),
        ),
    ):
        result = runner.invoke(app, ["runs", "sync", str(survey)])

    assert result.exit_code == 0, result.output
    # The second run gets sync'd, the first is skipped silently.
    assert "R20260327-0002" in result.output
    # First run's id should not show up — its sync was skipped.
    # (It may still appear elsewhere in path strings, so check the
    #  state-change output specifically.)
    assert "R20260327-0001:" not in result.output


def test_sync_multi_run_arguments(tmp_path: Path) -> None:
    """Passing multiple run paths processes each one."""
    (tmp_path / "simproject.toml").write_text('[project]\nname = "test"\n')
    run1 = tmp_path / "runs" / "R20260327-0001"
    run2 = tmp_path / "runs" / "R20260327-0002"
    _create_run(run1, run_id="R20260327-0001", status="running", job_id="11111")
    _create_run(run2, run_id="R20260327-0002", status="running", job_id="22222")

    with (
        patch("simctl.cli.status.Path.cwd", return_value=tmp_path),
        patch(
            "simctl.slurm.query.query_job_status",
            return_value=JobStatus(
                run_state=RunState.COMPLETED, slurm_state="COMPLETED"
            ),
        ),
    ):
        result = runner.invoke(app, ["runs", "sync", str(run1), str(run2)])

    assert result.exit_code == 0
    assert "R20260327-0001" in result.output
    assert "R20260327-0002" in result.output


def test_status_multi_run_arguments(tmp_path: Path) -> None:
    """Status accepts multiple targets and prints each."""
    (tmp_path / "simproject.toml").write_text('[project]\nname = "test"\n')
    run1 = tmp_path / "runs" / "R20260327-0001"
    run2 = tmp_path / "runs" / "R20260327-0002"
    _create_run(run1, run_id="R20260327-0001", status="running", job_id="11111")
    _create_run(run2, run_id="R20260327-0002", status="running", job_id="22222")

    with (
        patch("simctl.cli.status.Path.cwd", return_value=tmp_path),
        patch(
            "simctl.cli.status.query_job_status",
            return_value=JobStatus(run_state=RunState.RUNNING, slurm_state="RUNNING"),
        ),
    ):
        result = runner.invoke(app, ["runs", "status", str(run1), str(run2)])

    assert result.exit_code == 0
    assert "R20260327-0001" in result.output
    assert "R20260327-0002" in result.output
