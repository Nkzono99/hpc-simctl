"""Tests for simctl runs archive and runs purge-work commands."""

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
    }
    with open(run_dir / "manifest.toml", "wb") as f:
        tomli_w.dump(manifest, f)
    return run_dir


class TestArchive:
    def test_archive_completed_run(self, tmp_path: Path) -> None:
        run_dir = _create_run(tmp_path, "R20260327-0001", status="completed")

        result = runner.invoke(app, ["runs", "archive", "--yes", str(run_dir)])
        assert result.exit_code == 0
        assert "Archived run R20260327-0001" in result.output

    def test_archive_verifies_manifest_state(self, tmp_path: Path) -> None:
        """After archive, manifest should show 'archived' status."""
        import sys

        if sys.version_info >= (3, 11):
            import tomllib
        else:
            import tomli as tomllib

        run_dir = _create_run(tmp_path, "R20260327-0001", status="completed")

        result = runner.invoke(app, ["runs", "archive", "--yes", str(run_dir)])
        assert result.exit_code == 0

        with open(run_dir / "manifest.toml", "rb") as f:
            data = tomllib.load(f)
        assert data["run"]["status"] == "archived"

    def test_archive_cancelled_without_confirmation(self, tmp_path: Path) -> None:
        run_dir = _create_run(tmp_path, "R20260327-0001", status="completed")

        result = runner.invoke(app, ["runs", "archive", str(run_dir)], input="n\n")
        assert result.exit_code == 0
        assert "Cancelled." in result.output

        from simctl.core.manifest import read_manifest

        manifest = read_manifest(run_dir)
        assert manifest.run["status"] == "completed"

    def test_archive_rejects_non_completed(self, tmp_path: Path) -> None:
        run_dir = _create_run(tmp_path, "R20260327-0001", status="created")

        result = runner.invoke(app, ["runs", "archive", str(run_dir)])
        assert result.exit_code == 1
        assert "completed" in result.output.lower()

    def test_archive_rejects_failed(self, tmp_path: Path) -> None:
        run_dir = _create_run(tmp_path, "R20260327-0001", status="failed")

        result = runner.invoke(app, ["runs", "archive", str(run_dir)])
        assert result.exit_code == 1

    def test_archive_nonexistent_run(self) -> None:
        result = runner.invoke(app, ["runs", "archive", "/nonexistent/run"])
        assert result.exit_code == 1
        assert "Error" in result.output


class TestPurgeWork:
    def test_purge_archived_run(self, tmp_path: Path) -> None:
        run_dir = _create_run(tmp_path, "R20260327-0001", status="archived")

        # Create work subdirectories with files
        for dirname in ("outputs", "restart", "tmp"):
            d = run_dir / "work" / dirname
            d.mkdir()
            (d / "data.bin").write_bytes(b"x" * 1024)

        result = runner.invoke(app, ["runs", "purge-work", "--yes", str(run_dir)])
        assert result.exit_code == 0
        assert "Purged work files" in result.output
        assert "Freed" in result.output

        # Verify directories are removed
        assert not (run_dir / "work" / "outputs").exists()
        assert not (run_dir / "work" / "restart").exists()
        assert not (run_dir / "work" / "tmp").exists()
        # work/ itself should still exist
        assert (run_dir / "work").exists()

    def test_purge_updates_state(self, tmp_path: Path) -> None:
        import sys

        if sys.version_info >= (3, 11):
            import tomllib
        else:
            import tomli as tomllib

        run_dir = _create_run(tmp_path, "R20260327-0001", status="archived")

        result = runner.invoke(app, ["runs", "purge-work", "--yes", str(run_dir)])
        assert result.exit_code == 0

        with open(run_dir / "manifest.toml", "rb") as f:
            data = tomllib.load(f)
        assert data["run"]["status"] == "purged"

    def test_purge_cancelled_without_confirmation(self, tmp_path: Path) -> None:
        run_dir = _create_run(tmp_path, "R20260327-0001", status="archived")

        work_outputs = run_dir / "work" / "outputs"
        work_outputs.mkdir()
        (work_outputs / "data.bin").write_bytes(b"x" * 1024)

        result = runner.invoke(
            app,
            ["runs", "purge-work", str(run_dir)],
            input="n\n",
        )
        assert result.exit_code == 0
        assert "Cancelled." in result.output
        assert work_outputs.exists()

        from simctl.core.manifest import read_manifest

        manifest = read_manifest(run_dir)
        assert manifest.run["status"] == "archived"

    def test_purge_rejects_non_archived(self, tmp_path: Path) -> None:
        run_dir = _create_run(tmp_path, "R20260327-0001", status="completed")

        result = runner.invoke(app, ["runs", "purge-work", str(run_dir)])
        assert result.exit_code == 1
        assert "archived" in result.output.lower()

    def test_purge_nonexistent_run(self) -> None:
        result = runner.invoke(app, ["runs", "purge-work", "/nonexistent/run"])
        assert result.exit_code == 1
        assert "Error" in result.output

    def test_purge_no_work_dirs(self, tmp_path: Path) -> None:
        """Purge succeeds even if work subdirectories don't exist."""
        run_dir = _create_run(tmp_path, "R20260327-0001", status="archived")

        result = runner.invoke(app, ["runs", "purge-work", "--yes", str(run_dir)])
        assert result.exit_code == 0
        assert "Freed: 0.0 B" in result.output
