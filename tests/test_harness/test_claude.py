"""Tests for Claude harness settings generation."""

from __future__ import annotations

import json

from simctl.harness import build_claude_settings


def test_build_claude_settings_exposes_expected_policy() -> None:
    """Claude settings include the expected allow/ask/deny policy."""
    data = json.loads(build_claude_settings())

    assert "permissions" in data
    assert "allow" in data["permissions"]
    assert "ask" in data["permissions"]
    assert "deny" in data["permissions"]
    assert "Bash(simctl analyze plot*)" in data["permissions"]["allow"]
    assert "Edit(/campaign.toml)" in data["permissions"]["allow"]
    assert "Write(/simproject.toml)" in data["permissions"]["ask"]
    assert "Write(/SITE.md)" in data["permissions"]["deny"]
    assert "Edit(/runs/**/manifest.toml)" in data["permissions"]["deny"]
    assert data["permissions"]["disableBypassPermissionsMode"] == "disable"


def test_settings_allow_tools_hpc_simctl_writes() -> None:
    """tools/hpc-simctl/** must be allow-listed for in-place dev install."""
    data = json.loads(build_claude_settings())
    assert "Edit(/tools/hpc-simctl/**)" in data["permissions"]["allow"]
    assert "Write(/tools/hpc-simctl/**)" in data["permissions"]["allow"]
    # And must NOT appear in ask (no per-edit confirmation).
    assert "Edit(/tools/hpc-simctl/**)" not in data["permissions"]["ask"]
    assert "Write(/tools/hpc-simctl/**)" not in data["permissions"]["ask"]


def test_runs_submit_is_ask_listed() -> None:
    """simctl runs submit must be ask-listed (the old hook is now a rule)."""
    data = json.loads(build_claude_settings())
    assert "Bash(simctl runs submit*)" in data["permissions"]["ask"]


def test_settings_does_not_install_pretooluse_hooks() -> None:
    """Settings.json must not declare PreToolUse hooks (moved to rules)."""
    data = json.loads(build_claude_settings())
    assert "hooks" not in data
