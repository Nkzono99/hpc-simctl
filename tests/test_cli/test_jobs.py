"""Tests for `runops runs jobs` (including the new --watch loop)."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

import tomli_w
from typer.testing import CliRunner

from runops.cli.main import app

if TYPE_CHECKING:
    import pytest

runner = CliRunner()


def _make_project(tmp_path: Path) -> Path:
    (tmp_path / "runops.toml").write_text('[project]\nname = "test-project"\n')
    (tmp_path / "cases").mkdir()
    (tmp_path / "runs").mkdir()
    return tmp_path


def _create_run(
    parent: Path,
    run_id: str,
    *,
    status: str,
    job_id: str = "",
    submitted_at: str = "",
) -> Path:
    """Create a minimal run directory with manifest.toml under ``parent``."""
    run_dir = parent / run_id
    run_dir.mkdir(parents=True)
    manifest: dict[str, Any] = {
        "run": {
            "id": run_id,
            "display_name": f"d_{run_id}",
            "status": status,
        },
        "job": {
            "scheduler": "slurm",
            "job_id": job_id,
            "submitted_at": submitted_at,
        },
    }
    with open(run_dir / "manifest.toml", "wb") as f:
        tomli_w.dump(manifest, f)
    return run_dir


class TestJobs:
    """Tests for the basic (non-watch) jobs command."""

    def test_jobs_lists_active_runs(self, tmp_path: Path) -> None:
        project_dir = _make_project(tmp_path)
        _create_run(
            project_dir / "runs",
            "R20260327-0001",
            status="running",
            job_id="11111",
            submitted_at="2026-03-27T10:00:00+09:00",
        )
        _create_run(
            project_dir / "runs",
            "R20260327-0002",
            status="completed",
            job_id="22222",
        )

        result = runner.invoke(app, ["runs", "jobs", str(project_dir)])
        assert result.exit_code == 0
        assert "R20260327-0001" in result.output
        # Completed runs are not 'active', so should be hidden by default.
        assert "R20260327-0002" not in result.output
        assert "11111" in result.output

    def test_jobs_all_includes_completed(self, tmp_path: Path) -> None:
        project_dir = _make_project(tmp_path)
        _create_run(
            project_dir / "runs",
            "R20260327-0001",
            status="completed",
            job_id="22222",
        )

        result = runner.invoke(app, ["runs", "jobs", "--all", str(project_dir)])
        assert result.exit_code == 0
        assert "R20260327-0001" in result.output
        assert "completed" in result.output

    def test_jobs_no_runs(self, tmp_path: Path) -> None:
        _make_project(tmp_path)
        result = runner.invoke(app, ["runs", "jobs", str(tmp_path)])
        assert result.exit_code == 0
        assert "No runs found." in result.output


class TestWatchLoop:
    """Tests for the --watch refresh loop."""

    def test_watch_calls_print_repeatedly_then_stops(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The watch loop refreshes until KeyboardInterrupt, then exits cleanly."""
        from runops.cli import jobs as jobs_cli

        project_dir = _make_project(tmp_path)
        _create_run(
            project_dir / "runs",
            "R20260327-0001",
            status="running",
            job_id="11111",
        )

        call_count = {"n": 0}

        def fake_print_once(search_dir: Path, *, all_states: bool) -> None:
            call_count["n"] += 1
            jobs_cli.typer.echo(f"call {call_count['n']}")

        def fake_sleep(seconds: float) -> None:
            # Simulate the user pressing Ctrl-C after the second refresh.
            if call_count["n"] >= 2:
                raise KeyboardInterrupt
            # No actual sleep — keep the test fast.

        monkeypatch.setattr(jobs_cli, "_print_jobs_once", fake_print_once)
        monkeypatch.setattr(jobs_cli.time, "sleep", fake_sleep)

        result = runner.invoke(
            app, ["runs", "jobs", "--watch", "0.01", str(project_dir)]
        )
        assert result.exit_code == 0, result.output
        assert call_count["n"] >= 2
        assert "Stopped." in result.output

    def test_watch_short_alias_w(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``-w`` is an accepted short alias for --watch."""
        from runops.cli import jobs as jobs_cli

        project_dir = _make_project(tmp_path)
        _create_run(
            project_dir / "runs",
            "R20260327-0001",
            status="running",
            job_id="11111",
        )

        seen = {"called": False}

        def fake_print_once(search_dir: Path, *, all_states: bool) -> None:
            seen["called"] = True

        def fake_sleep(seconds: float) -> None:
            raise KeyboardInterrupt

        monkeypatch.setattr(jobs_cli, "_print_jobs_once", fake_print_once)
        monkeypatch.setattr(jobs_cli.time, "sleep", fake_sleep)

        result = runner.invoke(app, ["runs", "jobs", "-w", "0.01", str(project_dir)])
        assert result.exit_code == 0
        assert seen["called"]
