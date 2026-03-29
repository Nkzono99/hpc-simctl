"""Tests for simctl init and simctl doctor CLI commands."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from simctl.cli.main import app

runner = CliRunner()


class TestInit:
    """Tests for the 'simctl init' command."""

    def test_init_creates_all_files(self, tmp_path: Path) -> None:
        """Init in an empty directory creates all expected files and dirs."""
        result = runner.invoke(app, ["init", "-y", "--path", str(tmp_path)])
        assert result.exit_code == 0
        assert (tmp_path / "simproject.toml").exists()
        assert (tmp_path / "simulators.toml").exists()
        assert (tmp_path / "launchers.toml").exists()
        assert (tmp_path / "cases").is_dir()
        assert (tmp_path / "runs").is_dir()
        assert (tmp_path / ".gitignore").exists()
        assert (tmp_path / ".git").is_dir()
        assert (tmp_path / "CLAUDE.md").exists()
        assert (tmp_path / "AGENTS.md").exists()
        assert (tmp_path / "SKILLS.md").exists()
        assert (tmp_path / ".vscode" / "settings.json").exists()

    def test_init_simproject_content(self, tmp_path: Path) -> None:
        """simproject.toml has correct project name derived from dir name."""
        result = runner.invoke(app, ["init", "-y", "--path", str(tmp_path)])
        assert result.exit_code == 0
        content = (tmp_path / "simproject.toml").read_text()
        assert "[project]" in content
        assert f'name = "{tmp_path.name}"' in content

    def test_init_custom_name(self, tmp_path: Path) -> None:
        """--name option overrides directory name in simproject.toml."""
        result = runner.invoke(
            app, ["init", "-y", "--path", str(tmp_path), "--name", "my-project"]
        )
        assert result.exit_code == 0
        content = (tmp_path / "simproject.toml").read_text()
        assert 'name = "my-project"' in content
        assert "my-project" in result.output

    def test_init_simulators_content(self, tmp_path: Path) -> None:
        """simulators.toml has empty [simulators] section."""
        runner.invoke(app, ["init", "-y", "--path", str(tmp_path)])
        content = (tmp_path / "simulators.toml").read_text()
        assert "[simulators]" in content

    def test_init_launchers_content(self, tmp_path: Path) -> None:
        """launchers.toml has default srun launcher."""
        runner.invoke(app, ["init", "-y", "--path", str(tmp_path)])
        content = (tmp_path / "launchers.toml").read_text()
        assert "[launchers.srun]" in content
        assert 'type = "srun"' in content
        assert "use_slurm_ntasks = true" in content

    def test_init_gitignore_content(self, tmp_path: Path) -> None:
        """.gitignore contains run output exclusion patterns."""
        runner.invoke(app, ["init", "-y", "--path", str(tmp_path)])
        content = (tmp_path / ".gitignore").read_text()
        assert "runs/**/work/outputs/" in content
        assert "runs/**/work/restart/" in content
        assert "runs/**/work/tmp/" in content

    def test_init_skips_existing_files(self, tmp_path: Path) -> None:
        """Init does not overwrite existing files."""
        (tmp_path / "simproject.toml").write_text('[project]\nname = "original"\n')
        result = runner.invoke(app, ["init", "-y", "--path", str(tmp_path)])
        assert result.exit_code == 0
        content = (tmp_path / "simproject.toml").read_text()
        assert 'name = "original"' in content
        assert "Skipped" in result.output

    def test_init_reports_created_items(self, tmp_path: Path) -> None:
        """Init output lists created items."""
        result = runner.invoke(app, ["init", "-y", "--path", str(tmp_path)])
        assert result.exit_code == 0
        assert "Created:" in result.output
        assert "simproject.toml" in result.output

    def test_init_creates_target_directory(self, tmp_path: Path) -> None:
        """Init creates the target directory if it does not exist."""
        target = tmp_path / "new-project"
        result = runner.invoke(app, ["init", "-y", "--path", str(target)])
        assert result.exit_code == 0
        assert target.is_dir()
        assert (target / "simproject.toml").exists()

    def test_init_defaults_to_cwd(self, tmp_path: Path) -> None:
        """Init without path argument uses current working directory."""
        import os

        original_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            result = runner.invoke(app, ["init", "-y"])
            assert result.exit_code == 0
            assert (tmp_path / "simproject.toml").exists()
        finally:
            os.chdir(original_cwd)

    def test_init_skips_git_init_if_exists(self, tmp_path: Path) -> None:
        """Init skips git init when .git already exists."""
        (tmp_path / ".git").mkdir()
        result = runner.invoke(app, ["init", "-y", "--path", str(tmp_path)])
        assert result.exit_code == 0
        assert "git init" in result.output
        assert "Skipped" in result.output

    def test_init_claude_md_with_simulators(self, tmp_path: Path) -> None:
        """CLAUDE.md includes simulator-specific guides when simulators given."""
        runner.invoke(app, ["init", "emses", "beach", "-y", "--path", str(tmp_path)])
        content = (tmp_path / "CLAUDE.md").read_text()
        assert "EMSES" in content
        assert "plasma.toml" in content
        assert "BEACH" in content
        assert "beach.toml" in content

    def test_init_claude_md_without_simulators(self, tmp_path: Path) -> None:
        """CLAUDE.md is generated without simulator sections when none given."""
        runner.invoke(app, ["init", "-y", "--path", str(tmp_path)])
        content = (tmp_path / "CLAUDE.md").read_text()
        assert "simctl" in content
        assert "シミュレータ固有知識" not in content

    def test_init_agents_md(self, tmp_path: Path) -> None:
        """AGENTS.md is a symlink to CLAUDE.md."""
        runner.invoke(app, ["init", "emses", "-y", "--path", str(tmp_path)])
        agents_path = tmp_path / "AGENTS.md"
        assert agents_path.is_symlink()
        assert agents_path.resolve() == (tmp_path / "CLAUDE.md").resolve()
        content = agents_path.read_text()
        assert "simctl" in content

    def test_init_skills_md(self, tmp_path: Path) -> None:
        """SKILLS.md contains skill definitions."""
        runner.invoke(app, ["init", "-y", "--path", str(tmp_path)])
        content = (tmp_path / "SKILLS.md").read_text()
        assert "/setup-env" in content
        assert "uv venv" in content
        assert "/survey-design" in content
        assert "/check-status" in content

    def test_init_skills_md_with_packages(self, tmp_path: Path) -> None:
        """SKILLS.md includes pip packages when simulators specified."""
        runner.invoke(app, ["init", "emses", "-y", "--path", str(tmp_path)])
        content = (tmp_path / "SKILLS.md").read_text()
        assert "emout" in content
        assert "h5py" in content

    def test_init_with_simulators(self, tmp_path: Path) -> None:
        """Init with simulator names generates default simulators.toml."""
        result = runner.invoke(
            app, ["init", "emses", "beach", "-y", "--path", str(tmp_path)]
        )
        assert result.exit_code == 0
        content = (tmp_path / "simulators.toml").read_text()
        assert "[simulators.emses]" in content
        assert 'adapter = "emses"' in content
        assert 'executable = "mpiemses3D"' in content
        assert "[simulators.beach]" in content
        assert 'adapter = "beach"' in content

    def test_init_with_unknown_simulator(self, tmp_path: Path) -> None:
        """Init with unknown simulator name fails with helpful error."""
        result = runner.invoke(
            app, ["init", "nonexistent", "-y", "--path", str(tmp_path)]
        )
        assert result.exit_code != 0
        assert "Unknown simulator" in result.output

    def test_init_with_single_simulator(self, tmp_path: Path) -> None:
        """Init with a single simulator name works."""
        result = runner.invoke(
            app, ["init", "emses", "-y", "--path", str(tmp_path)]
        )
        assert result.exit_code == 0
        content = (tmp_path / "simulators.toml").read_text()
        assert "[simulators.emses]" in content
        assert "beach" not in content

    def test_init_schema_comments(self, tmp_path: Path) -> None:
        """Generated TOMLs include #:schema comments."""
        runner.invoke(app, ["init", "-y", "--path", str(tmp_path)])
        for filename in ("simproject.toml", "simulators.toml", "launchers.toml"):
            content = (tmp_path / filename).read_text()
            assert "#:schema" in content

    def test_init_generates_usage_guide(self, tmp_path: Path) -> None:
        """Init generates docs/simctl-guide.md."""
        runner.invoke(app, ["init", "-y", "--path", str(tmp_path)])
        guide = tmp_path / "docs" / "simctl-guide.md"
        assert guide.exists()
        content = guide.read_text()
        assert "simctl" in content
        assert "survey.toml" in content

    def test_init_default_is_interactive(self, tmp_path: Path) -> None:
        """Init without -y is interactive (prompts for project name)."""
        user_input = "\n" * 20
        result = runner.invoke(
            app, ["init", "--path", str(tmp_path)], input=user_input
        )
        assert result.exit_code == 0
        assert "Project name" in result.output


class TestDoctor:
    """Tests for the 'simctl doctor' command."""

    def test_doctor_all_pass(self, tmp_path: Path) -> None:
        """Doctor passes on a properly initialized project with sbatch."""
        # Set up a valid project
        (tmp_path / "simproject.toml").write_text(
            '[project]\nname = "test-project"\n'
        )
        (tmp_path / "simulators.toml").write_text("[simulators]\n")
        (tmp_path / "launchers.toml").write_text("[launchers]\n")
        (tmp_path / "runs").mkdir()

        with patch("simctl.cli.init.shutil.which", return_value="/usr/bin/sbatch"):
            result = runner.invoke(app, ["doctor", str(tmp_path)])

        assert result.exit_code == 0
        assert "All checks passed" in result.output

    def test_doctor_missing_simproject(self, tmp_path: Path) -> None:
        """Doctor fails if simproject.toml is missing."""
        result = runner.invoke(app, ["doctor", str(tmp_path)])
        assert result.exit_code == 1
        assert "[FAIL] simproject.toml not found" in result.output

    def test_doctor_invalid_simproject(self, tmp_path: Path) -> None:
        """Doctor fails if simproject.toml is invalid."""
        (tmp_path / "simproject.toml").write_text("invalid content\n")
        (tmp_path / "simulators.toml").write_text("[simulators]\n")
        (tmp_path / "launchers.toml").write_text("[launchers]\n")

        with patch("simctl.cli.init.shutil.which", return_value="/usr/bin/sbatch"):
            result = runner.invoke(app, ["doctor", str(tmp_path)])

        assert result.exit_code == 1
        assert "[FAIL] simproject.toml" in result.output

    def test_doctor_missing_simulators(self, tmp_path: Path) -> None:
        """Doctor fails if simulators.toml is missing."""
        (tmp_path / "simproject.toml").write_text(
            '[project]\nname = "test-project"\n'
        )
        (tmp_path / "launchers.toml").write_text("[launchers]\n")

        with patch("simctl.cli.init.shutil.which", return_value="/usr/bin/sbatch"):
            result = runner.invoke(app, ["doctor", str(tmp_path)])

        assert result.exit_code == 1
        assert "[FAIL] simulators.toml not found" in result.output

    def test_doctor_missing_launchers(self, tmp_path: Path) -> None:
        """Doctor fails if launchers.toml is missing."""
        (tmp_path / "simproject.toml").write_text(
            '[project]\nname = "test-project"\n'
        )
        (tmp_path / "simulators.toml").write_text("[simulators]\n")

        with patch("simctl.cli.init.shutil.which", return_value="/usr/bin/sbatch"):
            result = runner.invoke(app, ["doctor", str(tmp_path)])

        assert result.exit_code == 1
        assert "[FAIL] launchers.toml not found" in result.output

    def test_doctor_missing_sbatch(self, tmp_path: Path) -> None:
        """Doctor fails if sbatch is not in PATH."""
        (tmp_path / "simproject.toml").write_text(
            '[project]\nname = "test-project"\n'
        )
        (tmp_path / "simulators.toml").write_text("[simulators]\n")
        (tmp_path / "launchers.toml").write_text("[launchers]\n")

        with patch("simctl.cli.init.shutil.which", return_value=None):
            result = runner.invoke(app, ["doctor", str(tmp_path)])

        assert result.exit_code == 1
        assert "[FAIL] sbatch not found in PATH" in result.output

    def test_doctor_duplicate_run_ids(self, tmp_path: Path) -> None:
        """Doctor fails if duplicate run_ids exist."""
        (tmp_path / "simproject.toml").write_text(
            '[project]\nname = "test-project"\n'
        )
        (tmp_path / "simulators.toml").write_text("[simulators]\n")
        (tmp_path / "launchers.toml").write_text("[launchers]\n")
        runs_dir = tmp_path / "runs"
        runs_dir.mkdir()

        # Create two runs with the same run_id
        for sub in ("run_a", "run_b"):
            run_dir = runs_dir / sub
            run_dir.mkdir()
            (run_dir / "manifest.toml").write_text(
                '[run]\nid = "R20260327-0001"\nstatus = "created"\n'
            )

        with patch("simctl.cli.init.shutil.which", return_value="/usr/bin/sbatch"):
            result = runner.invoke(app, ["doctor", str(tmp_path)])

        assert result.exit_code == 1
        assert "[FAIL] Duplicate run_id" in result.output

    def test_doctor_no_runs_dir(self, tmp_path: Path) -> None:
        """Doctor passes run_id check when runs/ does not exist."""
        (tmp_path / "simproject.toml").write_text(
            '[project]\nname = "test-project"\n'
        )
        (tmp_path / "simulators.toml").write_text("[simulators]\n")
        (tmp_path / "launchers.toml").write_text("[launchers]\n")

        with patch("simctl.cli.init.shutil.which", return_value="/usr/bin/sbatch"):
            result = runner.invoke(app, ["doctor", str(tmp_path)])

        assert result.exit_code == 0
        assert "[PASS] No runs/ directory" in result.output

    def test_doctor_reports_failure_count(self, tmp_path: Path) -> None:
        """Doctor output includes the number of failed checks."""
        # Empty dir: simproject, simulators, launchers all missing + no sbatch
        with patch("simctl.cli.init.shutil.which", return_value=None):
            result = runner.invoke(app, ["doctor", str(tmp_path)])

        assert result.exit_code == 1
        assert "check(s) failed" in result.output
