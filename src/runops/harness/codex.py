"""Codex CLI harness config generation.

This module owns the Python-side wiring for Codex harness files.  The actual
generated text lives under ``runops/templates/harness/codex/`` so policy text
can evolve like the other scaffold templates instead of being embedded in
Python string literals.
"""

from __future__ import annotations

from typing import Final

from runops.templates import load_static, render

CODEX_CONFIG: Final = ".codex/config.toml"
CODEX_README: Final = ".codex/README.md"
CODEX_RULES: Final = ".codex/rules/runops.rules"
AGENTS_SKILLS_PREFIX: Final = ".agents/skills/"

_CODEX_CONFIG_TEMPLATE: Final = "harness/codex/config.toml.j2"
_CODEX_README_TEMPLATE: Final = "harness/codex/README.md.j2"
_CODEX_RULES_TEMPLATE: Final = "harness/codex/rules/runops.rules"


def build_codex_config(project_name: str) -> str:
    """Return ``.codex/config.toml`` content for ``project_name``."""
    return render(_CODEX_CONFIG_TEMPLATE, project_name=project_name)


def build_codex_rules() -> str:
    """Return project-scoped Codex command escalation rules."""
    return load_static(_CODEX_RULES_TEMPLATE)


def build_codex_readme(project_name: str) -> str:
    """Return ``.codex/README.md`` content documenting the Codex harness."""
    return render(_CODEX_README_TEMPLATE, project_name=project_name)


__all__ = [
    "AGENTS_SKILLS_PREFIX",
    "CODEX_CONFIG",
    "CODEX_README",
    "CODEX_RULES",
    "build_codex_config",
    "build_codex_readme",
    "build_codex_rules",
]
