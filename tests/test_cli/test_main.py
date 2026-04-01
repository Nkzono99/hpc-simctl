"""Tests for CLI entry point."""

from __future__ import annotations

from typer.testing import CliRunner

from simctl.cli.main import app

runner = CliRunner()


def test_help_shows_primary_commands() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for cmd in [
        "init",
        "setup",
        "doctor",
        "context",
        "config",
        "knowledge",
        "case",
        "runs",
        "analyze",
        "update",
        "update-refs",
    ]:
        assert cmd in result.output


def test_case_help_shows_grouped_case_commands() -> None:
    result = runner.invoke(app, ["case", "--help"])
    assert result.exit_code == 0
    assert "new" in result.output


def test_runs_help_shows_grouped_run_commands() -> None:
    result = runner.invoke(app, ["runs", "--help"])
    assert result.exit_code == 0
    for cmd in [
        "create",
        "submit",
        "status",
        "sync",
        "log",
        "list",
        "jobs",
        "history",
        "clone",
        "extend",
        "archive",
        "purge-work",
    ]:
        assert cmd in result.output


def test_analyze_help_shows_grouped_analysis_commands() -> None:
    result = runner.invoke(app, ["analyze", "--help"])
    assert result.exit_code == 0
    for cmd in ["summarize", "collect", "plot"]:
        assert cmd in result.output


def test_runs_submit_help_is_available() -> None:
    result = runner.invoke(app, ["runs", "submit", "--help"])
    assert result.exit_code == 0
    assert "--afterok" in result.output


def test_removed_top_level_create_command_is_unavailable() -> None:
    result = runner.invoke(app, ["create", "--help"])
    assert result.exit_code != 0
    assert "No such command" in result.output


def test_removed_top_level_run_command_is_unavailable() -> None:
    result = runner.invoke(app, ["run", "--help"])
    assert result.exit_code != 0
    assert "No such command" in result.output


def test_removed_top_level_submit_command_is_unavailable() -> None:
    result = runner.invoke(app, ["submit", "--help"])
    assert result.exit_code != 0
    assert "No such command" in result.output
