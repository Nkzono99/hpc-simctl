"""Tests for simctl update-harness CLI command."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from simctl.cli.main import app
from simctl.harness.builder import (
    HARNESS_LOCK_PATH,
    hash_text,
    load_harness_lock,
    save_harness_lock,
)

runner = CliRunner()


@pytest.fixture(autouse=True)
def _mock_bootstrap(monkeypatch: pytest.MonkeyPatch) -> None:
    """Skip the bootstrap step (uv/git clone) in all tests."""
    monkeypatch.setattr(
        "simctl.cli.init._bootstrap_environment",
        lambda *_args, **_kwargs: None,
    )


def _init_project(tmp_path: Path) -> None:
    """Create a minimal project via simctl init."""
    result = runner.invoke(app, ["init", "-y", "--path", str(tmp_path)])
    assert result.exit_code == 0


class TestUpdateHarnessBasic:
    """Basic update-harness scenarios."""

    def test_all_files_up_to_date(self, tmp_path: Path) -> None:
        """Freshly-inited project reports all files up to date."""
        _init_project(tmp_path)
        result = runner.invoke(app, ["update-harness", str(tmp_path), "--skip-pull"])
        assert result.exit_code == 0
        assert "up to date" in result.output

    def test_creates_harness_lock(self, tmp_path: Path) -> None:
        """init creates .simctl/harness.lock with template hashes."""
        _init_project(tmp_path)
        lock = load_harness_lock(tmp_path)
        assert "CLAUDE.md" in lock
        assert "AGENTS.md" in lock
        assert ".claude/settings.json" in lock
        assert ".claude/rules/simctl-workflow.md" in lock
        assert ".claude/rules/upstream-feedback.md" in lock

    def test_overwrites_unedited_files(self, tmp_path: Path) -> None:
        """Files matching their lock hash are silently overwritten."""
        _init_project(tmp_path)
        claude_md = tmp_path / "CLAUDE.md"
        original = claude_md.read_text(encoding="utf-8")

        # Simulate template change by tampering with lock hash
        lock = load_harness_lock(tmp_path)
        lock["CLAUDE.md"] = hash_text(original)  # match current disk
        save_harness_lock(tmp_path, lock)

        result = runner.invoke(app, ["update-harness", str(tmp_path), "--skip-pull"])
        assert result.exit_code == 0
        # File content is identical to template, so it's "up to date"
        assert "up to date" in result.output

    def test_writes_new_for_user_edited(self, tmp_path: Path) -> None:
        """User-edited files are preserved; .new variant is written."""
        _init_project(tmp_path)
        claude_md = tmp_path / "CLAUDE.md"

        # User edits the file
        claude_md.write_text("# My custom CLAUDE.md\n", encoding="utf-8")

        result = runner.invoke(app, ["update-harness", str(tmp_path), "--skip-pull"])
        assert result.exit_code == 0
        assert ".new" in result.output
        # Original is preserved
        assert claude_md.read_text(encoding="utf-8") == "# My custom CLAUDE.md\n"
        # .new file exists
        new_file = tmp_path / "CLAUDE.md.new"
        assert new_file.exists()

    def test_force_overwrites_edited(self, tmp_path: Path) -> None:
        """--force overwrites even user-edited files."""
        _init_project(tmp_path)
        claude_md = tmp_path / "CLAUDE.md"
        claude_md.write_text("# Edited\n", encoding="utf-8")

        result = runner.invoke(
            app, ["update-harness", str(tmp_path), "--skip-pull", "--force"]
        )
        assert result.exit_code == 0
        assert "Updated" in result.output
        # File should no longer be the user edit
        assert claude_md.read_text(encoding="utf-8") != "# Edited\n"

    def test_dry_run_no_writes(self, tmp_path: Path) -> None:
        """--dry-run reports but does not actually write files."""
        _init_project(tmp_path)
        claude_md = tmp_path / "CLAUDE.md"
        claude_md.write_text("# Edited\n", encoding="utf-8")

        old_lock = load_harness_lock(tmp_path)

        result = runner.invoke(
            app, ["update-harness", str(tmp_path), "--skip-pull", "--dry-run"]
        )
        assert result.exit_code == 0
        assert "[dry-run]" in result.output
        # File untouched
        assert claude_md.read_text(encoding="utf-8") == "# Edited\n"
        # No .new file
        assert not (tmp_path / "CLAUDE.md.new").exists()
        # Lock unchanged
        assert load_harness_lock(tmp_path) == old_lock

    def test_adopt_locks_current_state(self, tmp_path: Path) -> None:
        """--adopt records current file hashes without overwriting."""
        _init_project(tmp_path)
        claude_md = tmp_path / "CLAUDE.md"
        claude_md.write_text("# Custom\n", encoding="utf-8")

        result = runner.invoke(
            app, ["update-harness", str(tmp_path), "--skip-pull", "--adopt"]
        )
        assert result.exit_code == 0
        assert "Adopted" in result.output

        # Lock now matches the on-disk custom content
        lock = load_harness_lock(tmp_path)
        assert lock["CLAUDE.md"] == hash_text("# Custom\n")

    def test_only_filters_paths(self, tmp_path: Path) -> None:
        """--only limits which files are processed."""
        _init_project(tmp_path)
        # Edit both CLAUDE.md and AGENTS.md
        (tmp_path / "CLAUDE.md").write_text("# A\n", encoding="utf-8")
        (tmp_path / "AGENTS.md").write_text("# B\n", encoding="utf-8")

        result = runner.invoke(
            app,
            [
                "update-harness",
                str(tmp_path),
                "--skip-pull",
                "--force",
                "--only",
                "CLAUDE.md",
            ],
        )
        assert result.exit_code == 0
        # CLAUDE.md was updated
        assert (tmp_path / "CLAUDE.md").read_text(encoding="utf-8") != "# A\n"
        # AGENTS.md was NOT touched
        assert (tmp_path / "AGENTS.md").read_text(encoding="utf-8") == "# B\n"


class TestInitUpstreamFeedback:
    """Tests for --no-upstream-feedback in simctl init."""

    def test_default_includes_feedback_rule(self, tmp_path: Path) -> None:
        """By default, upstream-feedback.md rule is created."""
        _init_project(tmp_path)
        rule = tmp_path / ".claude" / "rules" / "upstream-feedback.md"
        assert rule.exists()
        content = rule.read_text(encoding="utf-8")
        assert "Nkzono99/hpc-simctl" in content
        assert "gh issue create" in content

    def test_no_upstream_feedback_flag(self, tmp_path: Path) -> None:
        """--no-upstream-feedback omits the rule file."""
        result = runner.invoke(
            app, ["init", "-y", "--no-upstream-feedback", "--path", str(tmp_path)]
        )
        assert result.exit_code == 0
        rule = tmp_path / ".claude" / "rules" / "upstream-feedback.md"
        assert not rule.exists()

    def test_simproject_records_upstream_feedback(self, tmp_path: Path) -> None:
        """simproject.toml includes [harness] upstream_feedback = true."""
        _init_project(tmp_path)
        content = (tmp_path / "simproject.toml").read_text(encoding="utf-8")
        assert "[harness]" in content
        assert "upstream_feedback = true" in content

    def test_simproject_records_no_upstream_feedback(self, tmp_path: Path) -> None:
        """--no-upstream-feedback sets upstream_feedback = false."""
        runner.invoke(
            app, ["init", "-y", "--no-upstream-feedback", "--path", str(tmp_path)]
        )
        content = (tmp_path / "simproject.toml").read_text(encoding="utf-8")
        assert "upstream_feedback = false" in content

    def test_update_harness_respects_setting(self, tmp_path: Path) -> None:
        """update-harness reads upstream_feedback from simproject.toml."""
        # Init without feedback
        runner.invoke(
            app, ["init", "-y", "--no-upstream-feedback", "--path", str(tmp_path)]
        )
        rule = tmp_path / ".claude" / "rules" / "upstream-feedback.md"
        assert not rule.exists()

        # update-harness should NOT create it
        result = runner.invoke(app, ["update-harness", str(tmp_path), "--skip-pull"])
        assert result.exit_code == 0
        assert not rule.exists()


class TestHarnessLock:
    """Tests for .simctl/harness.lock persistence."""

    def test_lock_is_valid_json(self, tmp_path: Path) -> None:
        """harness.lock is valid JSON with version and hashes."""
        _init_project(tmp_path)
        lock_path = tmp_path / HARNESS_LOCK_PATH
        assert lock_path.exists()
        data = json.loads(lock_path.read_text(encoding="utf-8"))
        assert data["version"] == 1
        assert isinstance(data["hashes"], dict)
        assert len(data["hashes"]) > 0

    def test_lock_hashes_are_sha256(self, tmp_path: Path) -> None:
        """All hashes in the lock are 64-char hex sha256 strings."""
        _init_project(tmp_path)
        lock = load_harness_lock(tmp_path)
        for _path, h in lock.items():
            assert len(h) == 64
            int(h, 16)  # raises if not hex

    def test_no_lock_treated_as_all_edited(self, tmp_path: Path) -> None:
        """When harness.lock is missing, all files are treated as user-edited."""
        _init_project(tmp_path)
        # Remove lock
        (tmp_path / HARNESS_LOCK_PATH).unlink()

        # Edit one file to differ from template
        (tmp_path / "CLAUDE.md").write_text("# Custom\n", encoding="utf-8")

        result = runner.invoke(app, ["update-harness", str(tmp_path), "--skip-pull"])
        assert result.exit_code == 0
        # CLAUDE.md should get a .new since it's edited and lock is missing
        assert (tmp_path / "CLAUDE.md.new").exists()
