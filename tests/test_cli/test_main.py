"""Tests for CLI entry point."""

from __future__ import annotations

from typer.testing import CliRunner

from simctl.cli.main import app

runner = CliRunner()


def test_help_shows_all_commands() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for cmd in [
        "init",
        "doctor",
        "create",
        "sweep",
        "submit",
        "status",
        "sync",
        "list",
        "clone",
        "summarize",
        "collect",
        "archive",
        "purge-work",
    ]:
        assert cmd in result.output
