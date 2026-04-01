"""Tests for simctl runs list command."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import tomli_w
from typer.testing import CliRunner

from simctl.cli.main import app

runner = CliRunner()


def _create_run(
    parent: Path,
    run_id: str,
    *,
    status: str = "created",
    display_name: str = "",
    tags: list[str] | None = None,
) -> Path:
    """Create a minimal run directory with manifest.toml."""
    run_dir = parent / run_id
    run_dir.mkdir(parents=True)
    for sub in ("input", "submit", "work", "analysis", "status"):
        (run_dir / sub).mkdir()

    manifest: dict[str, Any] = {
        "run": {
            "id": run_id,
            "display_name": display_name,
            "status": status,
        },
    }
    if tags:
        manifest["classification"] = {"tags": tags}

    with open(run_dir / "manifest.toml", "wb") as f:
        tomli_w.dump(manifest, f)
    return run_dir


def test_list_no_runs(tmp_path: Path) -> None:
    result = runner.invoke(app, ["runs", "list", str(tmp_path)])
    assert result.exit_code == 0
    assert "No runs found" in result.output


def test_list_discovers_runs(tmp_path: Path) -> None:
    _create_run(tmp_path, "R20260327-0001", status="created", display_name="run_a")
    _create_run(tmp_path, "R20260327-0002", status="completed", display_name="run_b")

    result = runner.invoke(app, ["runs", "list", str(tmp_path)])
    assert result.exit_code == 0
    assert "R20260327-0001" in result.output
    assert "R20260327-0002" in result.output
    assert "run_a" in result.output
    assert "run_b" in result.output


def test_list_filter_by_status(tmp_path: Path) -> None:
    _create_run(tmp_path, "R20260327-0001", status="created")
    _create_run(tmp_path, "R20260327-0002", status="failed")

    result = runner.invoke(app, ["runs", "list", str(tmp_path), "--status", "failed"])
    assert result.exit_code == 0
    assert "R20260327-0002" in result.output
    assert "R20260327-0001" not in result.output


def test_list_filter_by_tag(tmp_path: Path) -> None:
    _create_run(tmp_path, "R20260327-0001", tags=["production"])
    _create_run(tmp_path, "R20260327-0002", tags=["test"])

    result = runner.invoke(
        app,
        ["runs", "list", str(tmp_path), "--tag", "production"],
    )
    assert result.exit_code == 0
    assert "R20260327-0001" in result.output
    assert "R20260327-0002" not in result.output


def test_list_no_match(tmp_path: Path) -> None:
    _create_run(tmp_path, "R20260327-0001", status="created")

    result = runner.invoke(app, ["runs", "list", str(tmp_path), "--status", "failed"])
    assert result.exit_code == 0
    assert "No runs match" in result.output


def test_list_sorted_by_run_id(tmp_path: Path) -> None:
    _create_run(tmp_path, "R20260327-0003")
    _create_run(tmp_path, "R20260327-0001")
    _create_run(tmp_path, "R20260327-0002")

    result = runner.invoke(app, ["runs", "list", str(tmp_path)])
    assert result.exit_code == 0
    lines = result.output.strip().split("\n")
    # Skip header rows (header + separator)
    data_lines = lines[2:]
    assert "R20260327-0001" in data_lines[0]
    assert "R20260327-0002" in data_lines[1]
    assert "R20260327-0003" in data_lines[2]


def test_list_nonexistent_dir() -> None:
    result = runner.invoke(app, ["runs", "list", "/nonexistent/path"])
    assert result.exit_code == 1
    assert "Error" in result.output
