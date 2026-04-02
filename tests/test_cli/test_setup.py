"""Tests for simctl setup CLI command."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from simctl.cli.main import app

runner = CliRunner()


def _make_existing_project(project_dir: Path) -> None:
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "simproject.toml").write_text(
        '[project]\nname = "setup-project"\n',
        encoding="utf-8",
    )
    (project_dir / "simulators.toml").write_text("[simulators]\n", encoding="utf-8")
    (project_dir / "launchers.toml").write_text("[launchers]\n", encoding="utf-8")


def test_setup_renders_imports_for_bootstrapped_tool_docs(
    tmp_path: Path,
    monkeypatch,
) -> None:
    project_dir = tmp_path / "setup-project"
    _make_existing_project(project_dir)

    def _fake_bootstrap(
        root: Path,
        _sim_names: list[str],
        _simctl_repo: str,
        created: list[str],
        _skipped: list[str],
    ) -> None:
        docs_dir = root / "tools" / "hpc-simctl" / "docs"
        docs_dir.mkdir(parents=True, exist_ok=True)
        (docs_dir / "agent-user-guide.md").write_text("# Agent guide\n")
        created.append("tools/hpc-simctl")

    monkeypatch.setattr("simctl.cli.init._bootstrap_environment", _fake_bootstrap)

    result = runner.invoke(app, ["setup", "--path", str(project_dir)])

    assert result.exit_code == 0
    imports_path = project_dir / ".simctl" / "knowledge" / "enabled" / "imports.md"
    assert imports_path.is_file()
    imports = imports_path.read_text(encoding="utf-8")
    assert "@tools/hpc-simctl/docs/agent-user-guide.md" in imports
