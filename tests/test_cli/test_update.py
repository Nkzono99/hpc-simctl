"""Tests for the ``runops update`` CLI command."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from typer.testing import CliRunner

from runops.cli.main import app
from runops.cli.update import _collect_packages, _find_venv_pip, _get_project_simulators
from runops.core.exceptions import SimctlError

runner = CliRunner()


def test_find_venv_pip_prefers_project_virtualenv(tmp_path: Path) -> None:
    pip_path = tmp_path / ".venv" / "bin" / "pip"
    pip_path.parent.mkdir(parents=True)
    pip_path.write_text("", encoding="utf-8")

    with (
        patch("runops.cli.update.Path.cwd", return_value=tmp_path),
        patch("runops.cli.update.find_project_root", return_value=tmp_path),
    ):
        assert _find_venv_pip() == str(pip_path)


def test_find_venv_pip_returns_none_when_project_lookup_fails(tmp_path: Path) -> None:
    with (
        patch("runops.cli.update.Path.cwd", return_value=tmp_path),
        patch(
            "runops.cli.update.find_project_root", side_effect=SimctlError("no project")
        ),
    ):
        assert _find_venv_pip() is None


def test_collect_packages_deduplicates_and_skips_unknown_adapters() -> None:
    fake_registry = SimpleNamespace(
        get=lambda name: {
            "emses": SimpleNamespace(pip_packages=lambda: ["emout", "numpy", "numpy"]),
            "beach": SimpleNamespace(pip_packages=lambda: ["beach-tools", "numpy"]),
        }[name]
    )

    with patch(
        "runops.adapters.registry.get_global_registry",
        return_value=fake_registry,
    ):
        packages = _collect_packages(["emses", "missing", "beach"])

    assert packages == ["emout", "numpy", "beach-tools"]


def test_get_project_simulators_reads_loaded_project(tmp_path: Path) -> None:
    project = SimpleNamespace(simulators={"emses": {}, "beach": {}})

    with (
        patch("runops.cli.update.Path.cwd", return_value=tmp_path),
        patch("runops.cli.update.find_project_root", return_value=tmp_path),
        patch("runops.cli.update.load_project", return_value=project),
    ):
        simulators = _get_project_simulators()

    assert simulators == ["emses", "beach"]


def test_get_project_simulators_returns_empty_on_error(tmp_path: Path) -> None:
    with (
        patch("runops.cli.update.Path.cwd", return_value=tmp_path),
        patch("runops.cli.update.find_project_root", side_effect=SimctlError("boom")),
    ):
        assert _get_project_simulators() == []


def test_update_requires_simulators_when_project_has_none() -> None:
    with patch("runops.cli.update._get_project_simulators", return_value=[]):
        result = runner.invoke(app, ["update"])

    assert result.exit_code == 1
    assert "No simulators found in project" in result.output


def test_update_reports_when_no_packages_are_needed() -> None:
    with (
        patch("runops.cli.update._get_project_simulators", return_value=["emses"]),
        patch("runops.cli.update._collect_packages", return_value=[]),
    ):
        result = runner.invoke(app, ["update"])

    assert result.exit_code == 0
    assert "No packages to upgrade for: emses" in result.output


def test_update_dry_run_lists_packages(tmp_path: Path) -> None:
    with (
        patch("runops.cli.update._get_project_simulators", return_value=["emses"]),
        patch("runops.cli.update._collect_packages", return_value=["emout", "numpy"]),
    ):
        result = runner.invoke(app, ["update", "--dry-run"])

    assert result.exit_code == 0
    assert "Would upgrade for simulators: emses" in result.output
    assert "emout" in result.output
    assert "numpy" in result.output


def test_update_requires_virtualenv_for_real_upgrade() -> None:
    with (
        patch("runops.cli.update._get_project_simulators", return_value=["emses"]),
        patch("runops.cli.update._collect_packages", return_value=["emout"]),
        patch("runops.cli.update._find_venv_pip", return_value=None),
    ):
        result = runner.invoke(app, ["update"])

    assert result.exit_code == 1
    assert "No .venv found" in result.output


def test_update_runs_pip_install_for_selected_simulators() -> None:
    completed = SimpleNamespace(returncode=0)
    pip_path = "/tmp/demo/.venv/bin/pip"

    with (
        patch("runops.cli.update._collect_packages", return_value=["emout", "numpy"]),
        patch("runops.cli.update._find_venv_pip", return_value=pip_path),
        patch("runops.cli.update.subprocess.run", return_value=completed) as mock_run,
    ):
        result = runner.invoke(app, ["update", "emses", "beach"])

    assert result.exit_code == 0, result.output
    assert "Upgrading packages for: emses, beach" in result.output
    assert "Upgraded 2 packages." in result.output
    assert mock_run.call_args.args[0] == [
        pip_path,
        "install",
        "--upgrade",
        "emout",
        "numpy",
    ]


def test_update_surfaces_upgrade_failures() -> None:
    failed = SimpleNamespace(returncode=1)
    pip_path = "/tmp/demo/.venv/bin/pip"

    with (
        patch("runops.cli.update._collect_packages", return_value=["emout"]),
        patch("runops.cli.update._find_venv_pip", return_value=pip_path),
        patch("runops.cli.update.subprocess.run", return_value=failed),
    ):
        result = runner.invoke(app, ["update", "emses"])

    assert result.exit_code == 1
    assert "Upgrade failed." in result.output
