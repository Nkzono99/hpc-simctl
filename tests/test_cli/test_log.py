"""Tests for the ``simctl runs log`` CLI command."""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import tomli_w
from typer.testing import CliRunner

from simctl.cli.log import _find_latest_log, _get_progress, _tail_file
from simctl.cli.main import app
from simctl.core.exceptions import SimctlError

runner = CliRunner()


def _write_manifest(run_dir: Path, *, job_id: str = "12345") -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    with open(run_dir / "manifest.toml", "wb") as f:
        tomli_w.dump(
            {
                "run": {"id": run_dir.name, "status": "running"},
                "job": {"job_id": job_id},
                "simulator": {"adapter": "emses"},
            },
            f,
        )


def test_find_latest_log_prefers_newest_match(tmp_path: Path) -> None:
    older = tmp_path / "stdout.12345.log"
    newer = tmp_path / "stdout.12346.log"
    older.write_text("old\n", encoding="utf-8")
    newer.write_text("new\n", encoding="utf-8")

    os.utime(older, (1, 1))
    os.utime(newer, (2, 2))

    assert _find_latest_log(tmp_path, "stdout.*.log") == newer


def test_find_latest_log_returns_none_for_missing_directory(tmp_path: Path) -> None:
    assert _find_latest_log(tmp_path / "missing", "*.log") is None


def test_tail_file_returns_last_requested_lines(tmp_path: Path) -> None:
    log_file = tmp_path / "stdout.log"
    log_file.write_text("a\nb\nc\nd\ne\n", encoding="utf-8")

    assert _tail_file(log_file, 2) == ["d", "e"]


def test_tail_file_returns_empty_on_oserror(tmp_path: Path) -> None:
    with patch("builtins.open", side_effect=OSError("boom")):
        assert _tail_file(tmp_path / "missing.log", 10) == []


def test_get_progress_formats_summary_from_adapter(tmp_path: Path) -> None:
    fake_adapter = SimpleNamespace(
        summarize=lambda run_dir: {
            "last_step": 25,
            "nstep": 100,
            "status": "running",
        }
    )

    def fake_adapter_cls() -> SimpleNamespace:
        return fake_adapter

    with patch("simctl.adapters.registry.get", return_value=fake_adapter_cls):
        progress = _get_progress(tmp_path, {"simulator": {"adapter": "emses"}})

    assert progress == "Progress: 25/100 (25.0%) [running]"


def test_get_progress_returns_status_only_when_steps_are_missing(
    tmp_path: Path,
) -> None:
    fake_adapter = SimpleNamespace(summarize=lambda run_dir: {"status": "warming up"})

    def fake_adapter_cls() -> SimpleNamespace:
        return fake_adapter

    with patch("simctl.adapters.registry.get", return_value=fake_adapter_cls):
        progress = _get_progress(tmp_path, {"simulator": {"adapter": "emses"}})

    assert progress == "Status: warming up"


def test_get_progress_returns_none_without_adapter_metadata(tmp_path: Path) -> None:
    assert _get_progress(tmp_path, {"simulator": {}}) is None


def test_get_progress_returns_none_when_adapter_lookup_fails(tmp_path: Path) -> None:
    with patch("simctl.adapters.registry.get", side_effect=RuntimeError("missing")):
        assert _get_progress(tmp_path, {"simulator": {"adapter": "emses"}}) is None


def test_runs_log_shows_tail_and_progress(tmp_path: Path) -> None:
    run_dir = tmp_path / "R20260409-0001"
    _write_manifest(run_dir)
    work_dir = run_dir / "work"
    work_dir.mkdir()
    (work_dir / "stdout.12345.log").write_text(
        "line1\nline2\nline3\nline4\n",
        encoding="utf-8",
    )

    with patch(
        "simctl.cli.log._get_progress",
        return_value="Progress: 2/4 (50.0%) [running]",
    ):
        result = runner.invoke(app, ["runs", "log", "-n", "2", str(run_dir)])

    assert result.exit_code == 0, result.output
    assert "Run: R20260409-0001" in result.output
    assert "Progress: 2/4 (50.0%) [running]" in result.output
    assert "line3" in result.output
    assert "line4" in result.output
    assert "line1" not in result.output


def test_runs_log_errors_when_no_matching_log_exists(tmp_path: Path) -> None:
    run_dir = tmp_path / "R20260409-0001"
    _write_manifest(run_dir)
    (run_dir / "work").mkdir()

    result = runner.invoke(app, ["runs", "log", str(run_dir)])

    assert result.exit_code == 1
    assert "No stdout log found for R20260409-0001" in result.output
    assert "(job_id: 12345)" in result.output


def test_runs_log_reads_stderr_with_fallback_pattern(tmp_path: Path) -> None:
    run_dir = tmp_path / "R20260409-0001"
    _write_manifest(run_dir)
    work_dir = run_dir / "work"
    work_dir.mkdir()
    (work_dir / "stderr-latest.log").write_text("stderr line\n", encoding="utf-8")

    with patch("simctl.cli.log._get_progress", return_value=None):
        result = runner.invoke(app, ["runs", "log", "--stderr", str(run_dir)])

    assert result.exit_code == 0, result.output
    assert "stderr-latest.log" in result.output
    assert "stderr line" in result.output


def test_runs_log_surfaces_manifest_read_errors(tmp_path: Path) -> None:
    with (
        patch("simctl.cli.log.resolve_run_or_cwd", return_value=tmp_path),
        patch("simctl.cli.log.read_manifest", side_effect=SimctlError("bad manifest")),
    ):
        result = runner.invoke(app, ["runs", "log"])

    assert result.exit_code == 1
    assert "Error: bad manifest" in result.output


def test_runs_log_follow_mode_invokes_tail(tmp_path: Path) -> None:
    run_dir = tmp_path / "R20260409-0001"
    _write_manifest(run_dir)
    work_dir = run_dir / "work"
    work_dir.mkdir()
    log_file = work_dir / "stdout.12345.log"
    log_file.write_text("line1\nline2\n", encoding="utf-8")

    with patch("subprocess.run") as mock_tail:
        result = runner.invoke(app, ["runs", "log", "--follow", str(run_dir)])

    assert result.exit_code == 0, result.output
    assert mock_tail.call_args.args[0] == ["tail", "-n20", "-f", str(log_file)]


def test_runs_log_follow_mode_exits_cleanly_on_keyboard_interrupt(
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / "R20260409-0001"
    _write_manifest(run_dir)
    work_dir = run_dir / "work"
    work_dir.mkdir()
    (work_dir / "stdout.12345.log").write_text("line1\n", encoding="utf-8")

    with patch("subprocess.run", side_effect=KeyboardInterrupt):
        result = runner.invoke(app, ["runs", "log", "--follow", str(run_dir)])

    assert result.exit_code == 0
