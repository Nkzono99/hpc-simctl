"""Tests for simctl runs clone command."""

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
    status: str = "completed",
    params: dict[str, Any] | None = None,
) -> Path:
    """Create a minimal run directory with manifest.toml and input files."""
    run_dir = parent / run_id
    run_dir.mkdir(parents=True)
    for sub in ("input", "submit", "work", "analysis", "status"):
        (run_dir / sub).mkdir()

    # Write a sample input file
    (run_dir / "input" / "config.txt").write_text("nx=64\nny=64\n")

    # Write a sample job script
    (run_dir / "submit" / "job.sh").write_text(
        "#!/bin/bash\n#SBATCH --job-name=test\necho hello\n"
    )

    manifest: dict[str, Any] = {
        "run": {
            "id": run_id,
            "display_name": "test run",
            "status": status,
        },
        "origin": {
            "case": "test_case",
            "survey": "",
            "parent_run": "",
        },
        "simulator": {
            "name": "test_sim",
            "adapter": "test_adapter",
        },
    }
    if params:
        manifest["params_snapshot"] = params

    with open(run_dir / "manifest.toml", "wb") as f:
        tomli_w.dump(manifest, f)
    return run_dir


def test_clone_basic(tmp_path: Path) -> None:
    source = _create_run(tmp_path, "R20260327-0001")

    result = runner.invoke(
        app,
        ["runs", "clone", str(source), "--dest", str(tmp_path)],
    )
    assert result.exit_code == 0
    assert "Cloned R20260327-0001" in result.output

    # Find the new run directory
    new_dirs = [d for d in tmp_path.iterdir() if d.is_dir() and d != source]
    assert len(new_dirs) == 1

    new_dir = new_dirs[0]
    assert (new_dir / "manifest.toml").exists()
    assert (new_dir / "input" / "config.txt").exists()
    assert (new_dir / "input" / "config.txt").read_text() == "nx=64\nny=64\n"
    assert (new_dir / "submit" / "job.sh").exists()
    assert "#SBATCH" in (new_dir / "submit" / "job.sh").read_text()


def test_clone_sets_parent_run(tmp_path: Path) -> None:
    import sys

    if sys.version_info >= (3, 11):
        import tomllib
    else:
        import tomli as tomllib

    source = _create_run(tmp_path, "R20260327-0001")

    result = runner.invoke(
        app,
        ["runs", "clone", str(source), "--dest", str(tmp_path)],
    )
    assert result.exit_code == 0

    new_dirs = [d for d in tmp_path.iterdir() if d.is_dir() and d != source]
    new_dir = new_dirs[0]

    with open(new_dir / "manifest.toml", "rb") as f:
        data = tomllib.load(f)

    assert data["origin"]["parent_run"] == "R20260327-0001"
    assert data["run"]["status"] == "created"


def test_clone_with_set_params(tmp_path: Path) -> None:
    import sys

    if sys.version_info >= (3, 11):
        import tomllib
    else:
        import tomli as tomllib

    source = _create_run(tmp_path, "R20260327-0001", params={"nx": 64})

    result = runner.invoke(
        app,
        ["runs", "clone", str(source), "--dest", str(tmp_path), "--set", "nx=128"],
    )
    assert result.exit_code == 0

    new_dirs = [d for d in tmp_path.iterdir() if d.is_dir() and d != source]
    new_dir = new_dirs[0]

    with open(new_dir / "manifest.toml", "rb") as f:
        data = tomllib.load(f)

    assert data["params_snapshot"]["nx"] == "128"


def test_clone_invalid_set_format(tmp_path: Path) -> None:
    source = _create_run(tmp_path, "R20260327-0001")

    result = runner.invoke(
        app,
        [
            "runs",
            "clone",
            str(source),
            "--dest",
            str(tmp_path),
            "--set",
            "badparam",
        ],
    )
    assert result.exit_code == 1
    assert "invalid --set format" in result.output


def test_clone_nonexistent_run() -> None:
    result = runner.invoke(app, ["runs", "clone", "/nonexistent/run"])
    assert result.exit_code == 1
    assert "Error" in result.output
