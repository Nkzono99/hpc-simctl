"""Tests for the ``simctl runs history`` CLI command."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

import tomli_w
from typer.testing import CliRunner

from simctl.cli.main import app
from simctl.core.exceptions import SimctlError

runner = CliRunner()


def _write_manifest(run_dir: Path, data: dict[str, Any]) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    with open(run_dir / "manifest.toml", "wb") as f:
        tomli_w.dump(data, f)


def test_history_reports_no_runs_when_project_is_empty(tmp_path: Path) -> None:
    (tmp_path / "simproject.toml").write_text('[project]\nname = "demo"\n')
    (tmp_path / "runs").mkdir()

    result = runner.invoke(app, ["runs", "history", str(tmp_path)])

    assert result.exit_code == 0
    assert "No runs found." in result.output


def test_history_reports_no_submitted_runs(tmp_path: Path) -> None:
    (tmp_path / "simproject.toml").write_text('[project]\nname = "demo"\n')
    _write_manifest(
        tmp_path / "runs" / "R20260409-0001",
        {
            "run": {"id": "R20260409-0001", "status": "created"},
            "job": {"job_id": ""},
        },
    )

    result = runner.invoke(app, ["runs", "history", str(tmp_path)])

    assert result.exit_code == 0
    assert "No submitted runs found." in result.output


def test_history_sorts_entries_and_honors_count(tmp_path: Path) -> None:
    (tmp_path / "simproject.toml").write_text('[project]\nname = "demo"\n')
    _write_manifest(
        tmp_path / "runs" / "survey_a" / "R20260409-0001",
        {
            "run": {"id": "R20260409-0001", "status": "completed"},
            "job": {
                "job_id": "11111",
                "submitted_at": "2026-04-09T10:00:00+00:00",
            },
        },
    )
    _write_manifest(
        tmp_path / "runs" / "survey_a" / "R20260409-0002",
        {
            "run": {"id": "R20260409-0002", "status": "running"},
            "job": {
                "job_id": "22222",
                "submitted_at": "2026-04-09T12:30:00+00:00",
            },
        },
    )
    _write_manifest(
        tmp_path / "runs" / "survey_b" / "R20260409-0003",
        {
            "run": {"id": "R20260409-0003", "status": "submitted"},
            "job": {
                "job_id": "33333",
                "submitted_at": "2026-04-09T11:00:00+00:00",
            },
        },
    )

    result = runner.invoke(app, ["runs", "history", "-n", "2", str(tmp_path)])

    assert result.exit_code == 0, result.output
    assert "SUBMITTED" in result.output
    assert "2026-04-09 12:30:00" in result.output
    assert "R20260409-0002" in result.output
    assert "R20260409-0003" in result.output
    assert "R20260409-0001" not in result.output
    assert "runs/survey_a/R20260409-0002" in result.output
    assert "2 entries" in result.output


def test_history_reports_discovery_errors(tmp_path: Path) -> None:
    with patch(
        "simctl.cli.history.discover_runs",
        side_effect=SimctlError("broken runs directory"),
    ):
        result = runner.invoke(app, ["runs", "history", str(tmp_path)])

    assert result.exit_code == 1
    assert "broken runs directory" in result.output
