"""Tests for the ``runops update`` CLI command."""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from typer.testing import CliRunner

from runops.cli.main import app
from runops.cli.update import (
    _build_install_cmd,
    _collect_packages,
    _find_venv_python,
    _get_project_simulators,
)
from runops.core.exceptions import SimctlError

runner = CliRunner()


def test_find_venv_python_prefers_project_virtualenv(tmp_path: Path) -> None:
    python_path = tmp_path / ".venv" / "bin" / "python"
    python_path.parent.mkdir(parents=True)
    python_path.write_text("", encoding="utf-8")

    with (
        patch("runops.cli.update.Path.cwd", return_value=tmp_path),
        patch("runops.cli.update.find_project_root", return_value=tmp_path),
    ):
        assert _find_venv_python() == python_path


def test_find_venv_python_returns_none_when_project_lookup_fails(
    tmp_path: Path,
) -> None:
    with (
        patch("runops.cli.update.Path.cwd", return_value=tmp_path),
        patch(
            "runops.cli.update.find_project_root", side_effect=SimctlError("no project")
        ),
        patch.dict(os.environ, {}, clear=False),
    ):
        os.environ.pop("VIRTUAL_ENV", None)
        assert _find_venv_python() is None


def test_find_venv_python_falls_back_to_virtual_env(tmp_path: Path) -> None:
    """When project .venv is missing, VIRTUAL_ENV should be honored."""
    real_venv = tmp_path / "shared_venv"
    python_path = real_venv / "bin" / "python"
    python_path.parent.mkdir(parents=True)
    python_path.write_text("", encoding="utf-8")

    project_dir = tmp_path / "project"
    project_dir.mkdir()

    with (
        patch("runops.cli.update.Path.cwd", return_value=project_dir),
        patch("runops.cli.update.find_project_root", return_value=project_dir),
        patch.dict(os.environ, {"VIRTUAL_ENV": str(real_venv)}, clear=False),
    ):
        assert _find_venv_python() == python_path


def test_find_venv_python_resolves_symlinked_venv(tmp_path: Path) -> None:
    """Symlinked project paths should still locate the real .venv."""
    real_project = tmp_path / "real" / "project"
    python_path = real_project / ".venv" / "bin" / "python"
    python_path.parent.mkdir(parents=True)
    python_path.write_text("", encoding="utf-8")

    link_dir = tmp_path / "link"
    link_dir.symlink_to(real_project)

    with (
        patch("runops.cli.update.Path.cwd", return_value=link_dir),
        patch("runops.cli.update.find_project_root", return_value=link_dir),
    ):
        result = _find_venv_python()
        assert result is not None
        assert result.resolve() == python_path.resolve()


def test_find_venv_python_works_without_pip(tmp_path: Path) -> None:
    """A uv-created venv without pip should still be discoverable."""
    venv = tmp_path / ".venv"
    (venv / "bin").mkdir(parents=True)
    (venv / "bin" / "python").write_text("")
    # Crucially: NO pip binary in .venv/bin

    with (
        patch("runops.cli.update.Path.cwd", return_value=tmp_path),
        patch("runops.cli.update.find_project_root", return_value=tmp_path),
    ):
        assert _find_venv_python() == venv / "bin" / "python"


def test_build_install_cmd_prefers_uv_when_available(tmp_path: Path) -> None:
    venv_py = tmp_path / ".venv" / "bin" / "python"
    with patch("runops.cli.update._find_uv", return_value="/usr/local/bin/uv"):
        cmd, approach = _build_install_cmd(venv_py, ["emout", "numpy"])
    assert approach == "uv pip"
    assert cmd[:5] == [
        "/usr/local/bin/uv",
        "pip",
        "install",
        "--python",
        str(venv_py),
    ]
    assert "--upgrade" in cmd
    assert cmd[-2:] == ["emout", "numpy"]


def test_build_install_cmd_falls_back_to_python_m_pip(tmp_path: Path) -> None:
    venv_py = tmp_path / ".venv" / "bin" / "python"
    with patch("runops.cli.update._find_uv", return_value=None):
        cmd, approach = _build_install_cmd(venv_py, ["emout"])
    assert approach == "python -m pip"
    assert cmd[:4] == [str(venv_py), "-m", "pip", "install"]
    assert cmd[-1] == "emout"


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
        patch("runops.cli.update._find_venv_python", return_value=None),
    ):
        result = runner.invoke(app, ["update"])

    assert result.exit_code == 1
    assert "No .venv found" in result.output


def test_update_runs_uv_pip_install_for_selected_simulators(tmp_path: Path) -> None:
    completed = SimpleNamespace(returncode=0)
    venv_py = tmp_path / ".venv" / "bin" / "python"

    with (
        patch("runops.cli.update._collect_packages", return_value=["emout", "numpy"]),
        patch("runops.cli.update._find_venv_python", return_value=venv_py),
        patch("runops.cli.update._find_uv", return_value="/usr/local/bin/uv"),
        patch("runops.cli.update.subprocess.run", return_value=completed) as mock_run,
    ):
        result = runner.invoke(app, ["update", "emses", "beach"])

    assert result.exit_code == 0, result.output
    assert "Upgrading packages for: emses, beach" in result.output
    assert "uv pip" in result.output
    assert "Upgraded 2 packages." in result.output
    assert mock_run.call_args.args[0] == [
        "/usr/local/bin/uv",
        "pip",
        "install",
        "--python",
        str(venv_py),
        "--upgrade",
        "emout",
        "numpy",
    ]


def test_update_falls_back_to_python_m_pip_when_uv_missing(tmp_path: Path) -> None:
    """Without uv, fall back to python -m pip."""
    completed = SimpleNamespace(returncode=0)
    venv_py = tmp_path / ".venv" / "bin" / "python"

    with (
        patch("runops.cli.update._collect_packages", return_value=["emout"]),
        patch("runops.cli.update._find_venv_python", return_value=venv_py),
        patch("runops.cli.update._find_uv", return_value=None),
        patch("runops.cli.update.subprocess.run", return_value=completed) as mock_run,
    ):
        result = runner.invoke(app, ["update", "emses"])

    assert result.exit_code == 0, result.output
    assert "python -m pip" in result.output
    assert mock_run.call_args.args[0] == [
        str(venv_py),
        "-m",
        "pip",
        "install",
        "--upgrade",
        "emout",
    ]


def test_update_surfaces_upgrade_failures(tmp_path: Path) -> None:
    failed = SimpleNamespace(returncode=1)
    venv_py = tmp_path / ".venv" / "bin" / "python"

    with (
        patch("runops.cli.update._collect_packages", return_value=["emout"]),
        patch("runops.cli.update._find_venv_python", return_value=venv_py),
        patch("runops.cli.update._find_uv", return_value="/usr/local/bin/uv"),
        patch("runops.cli.update.subprocess.run", return_value=failed),
    ):
        result = runner.invoke(app, ["update", "emses"])

    assert result.exit_code == 1
    assert "Upgrade failed." in result.output
