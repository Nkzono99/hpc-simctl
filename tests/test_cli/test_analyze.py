"""Tests for simctl summarize and collect commands."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import tomli_w
from typer.testing import CliRunner

from simctl.cli.main import app

runner = CliRunner()


def _create_run(
    parent: Path,
    run_id: str,
    *,
    status: str = "completed",
    simulator_name: str = "test_sim",
    adapter_name: str = "test_adapter",
) -> Path:
    """Create a minimal run directory with manifest.toml."""
    run_dir = parent / run_id
    run_dir.mkdir(parents=True)
    for sub in ("input", "submit", "work", "analysis", "status"):
        (run_dir / sub).mkdir()

    manifest: dict[str, Any] = {
        "run": {
            "id": run_id,
            "display_name": "test run",
            "status": status,
        },
        "simulator": {
            "name": simulator_name,
            "adapter": adapter_name,
        },
    }
    with open(run_dir / "manifest.toml", "wb") as f:
        tomli_w.dump(manifest, f)
    return run_dir


class TestSummarize:
    def test_summarize_success(self, tmp_path: Path) -> None:
        run_dir = _create_run(tmp_path, "R20260327-0001")

        mock_adapter = MagicMock()
        mock_adapter.summarize.return_value = {"energy": 42.0, "steps": 1000}

        mock_adapter_cls = MagicMock(return_value=mock_adapter)

        with patch("simctl.cli.analyze.get_adapter", return_value=mock_adapter_cls):
            result = runner.invoke(app, ["summarize", str(run_dir)])

        assert result.exit_code == 0
        assert "Summary written" in result.output

        summary_path = run_dir / "analysis" / "summary.json"
        assert summary_path.exists()
        with open(summary_path) as f:
            data = json.load(f)
        assert data["energy"] == 42.0
        assert data["steps"] == 1000

    def test_summarize_no_adapter(self, tmp_path: Path) -> None:
        run_dir = _create_run(tmp_path, "R20260327-0001")

        with patch("simctl.cli.analyze.get_adapter", side_effect=KeyError("not found")):
            result = runner.invoke(app, ["summarize", str(run_dir)])

        assert result.exit_code == 1

    def test_summarize_nonexistent_run(self) -> None:
        result = runner.invoke(app, ["summarize", "/nonexistent/run"])
        assert result.exit_code == 1
        assert "Error" in result.output

    def test_summarize_no_simulator_in_manifest(self, tmp_path: Path) -> None:
        run_dir = tmp_path / "R20260327-0001"
        run_dir.mkdir(parents=True)
        for sub in ("input", "submit", "work", "analysis", "status"):
            (run_dir / sub).mkdir()

        manifest: dict[str, Any] = {
            "run": {"id": "R20260327-0001", "status": "completed"},
        }
        with open(run_dir / "manifest.toml", "wb") as f:
            tomli_w.dump(manifest, f)

        result = runner.invoke(app, ["summarize", str(run_dir)])
        assert result.exit_code == 1
        out = result.output.lower()
        assert "simulator" in out or "adapter" in out


class TestCollect:
    def test_collect_success(self, tmp_path: Path) -> None:
        # Create two runs with summaries
        for i, run_id in enumerate(["R20260327-0001", "R20260327-0002"], start=1):
            run_dir = _create_run(tmp_path, run_id)
            summary = {"energy": float(i * 10), "steps": i * 100}
            with open(run_dir / "analysis" / "summary.json", "w") as f:
                json.dump(summary, f)

        result = runner.invoke(app, ["collect", str(tmp_path)])
        assert result.exit_code == 0
        assert "Collected 2 summaries" in result.output

        csv_path = tmp_path / "summary" / "survey_summary.csv"
        assert csv_path.exists()
        content = csv_path.read_text()
        assert "run_id" in content
        assert "energy" in content
        assert "R20260327-0001" in content
        assert "R20260327-0002" in content

    def test_collect_no_runs(self, tmp_path: Path) -> None:
        result = runner.invoke(app, ["collect", str(tmp_path)])
        assert result.exit_code == 1
        assert "No runs found" in result.output

    def test_collect_no_summaries(self, tmp_path: Path) -> None:
        _create_run(tmp_path, "R20260327-0001")

        result = runner.invoke(app, ["collect", str(tmp_path)])
        assert result.exit_code == 1
        assert "No summaries found" in result.output

    def test_collect_partial_summaries(self, tmp_path: Path) -> None:
        run1 = _create_run(tmp_path, "R20260327-0001")
        _create_run(tmp_path, "R20260327-0002")  # no summary

        with open(run1 / "analysis" / "summary.json", "w") as f:
            json.dump({"energy": 10.0}, f)

        result = runner.invoke(app, ["collect", str(tmp_path)])
        assert result.exit_code == 0
        assert "Collected 1 summaries" in result.output
        assert "1 runs missing" in result.output

    def test_collect_nonexistent_dir(self) -> None:
        result = runner.invoke(app, ["collect", "/nonexistent/path"])
        assert result.exit_code == 1
        assert "Error" in result.output
