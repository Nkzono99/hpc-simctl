"""Tests for Claude harness settings generation."""

from __future__ import annotations

import json

from simctl.harness import CLAUDE_HOOK_TEMPLATES, build_claude_settings


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


def test_claude_hook_templates_list_all_scaffolded_hooks() -> None:
    """Claude hook templates enumerate the files init should scaffold."""
    assert CLAUDE_HOOK_TEMPLATES == (
        ("approve-run.sh", "scaffold/hooks/approve-run.sh"),
        ("protect-files.sh", "scaffold/hooks/protect-files.sh"),
        ("guard-bash.sh", "scaffold/hooks/guard-bash.sh"),
    )
