"""Tests for simctl setup CLI command."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

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
        (root / "tools" / "hpc-simctl").mkdir(parents=True, exist_ok=True)
        (root / "tools" / "hpc-simctl" / "entrypoints.toml").write_text(
            'imports = ["docs/agent-user-guide.md"]\n',
            encoding="utf-8",
        )
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


def test_setup_smoke_with_knowledge_attach_render_and_doctor(
    tmp_path: Path,
    monkeypatch,
) -> None:
    project_dir = tmp_path / "smoke-project"

    def _fake_bootstrap(
        root: Path,
        _sim_names: list[str],
        _simctl_repo: str,
        created: list[str],
        _skipped: list[str],
    ) -> None:
        (root / "tools" / "hpc-simctl").mkdir(parents=True, exist_ok=True)
        (root / "tools" / "hpc-simctl" / "entrypoints.toml").write_text(
            'imports = ["docs/agent-user-guide.md"]\n',
            encoding="utf-8",
        )
        docs_dir = root / "tools" / "hpc-simctl" / "docs"
        docs_dir.mkdir(parents=True, exist_ok=True)
        (docs_dir / "agent-user-guide.md").write_text("# Agent guide\n")
        created.append("tools/hpc-simctl")

    monkeypatch.setattr("simctl.cli.init._bootstrap_environment", _fake_bootstrap)

    init_result = runner.invoke(app, ["init", "-y", "--path", str(project_dir)])
    assert init_result.exit_code == 0

    kb_dir = tmp_path / "shared-kb"
    (kb_dir / "profiles").mkdir(parents=True)
    (kb_dir / "README.md").write_text("# Shared KB\n", encoding="utf-8")
    (kb_dir / "profiles" / "common.md").write_text("# Common\n", encoding="utf-8")
    (kb_dir / "entrypoints.toml").write_text(
        '[profiles.common]\nimports = ["profiles/common.md"]\n',
        encoding="utf-8",
    )

    with patch("simctl.cli.knowledge.Path.cwd", return_value=project_dir):
        attach_result = runner.invoke(
            app,
            [
                "knowledge",
                "source",
                "attach",
                "path",
                "shared-kb",
                str(kb_dir),
                "--profiles",
                "common",
            ],
        )
        render_result = runner.invoke(app, ["knowledge", "source", "render"])

    assert attach_result.exit_code == 0
    assert render_result.exit_code == 0

    setup_result = runner.invoke(app, ["setup", "--path", str(project_dir)])
    assert setup_result.exit_code == 0

    with patch("simctl.cli.init.shutil.which", return_value="/usr/bin/sbatch"):
        doctor_result = runner.invoke(app, ["doctor", str(project_dir)])

    assert doctor_result.exit_code == 0
    imports = (
        project_dir / ".simctl" / "knowledge" / "enabled" / "imports.md"
    ).read_text(encoding="utf-8")
    assert "@tools/hpc-simctl/docs/agent-user-guide.md" in imports
    assert "@refs/knowledge/shared-kb/profiles/common.md" in imports
