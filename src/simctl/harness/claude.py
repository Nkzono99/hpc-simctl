"""Claude Code harness policy and settings generation."""

from __future__ import annotations

import json
from typing import Final

# Bash commands the agent can run without confirmation.
#
# We deliberately keep ASK_BASH small (see _ASK_BASH below): the only Bash
# commands that should prompt are ones that spend HPC resources or destroy
# files irreversibly.  Everything else, including knowledge sync, ref
# updates, and local git commits, lives here.
_ALLOW_BASH: Final[tuple[str, ...]] = (
    # Read-only inspection
    "Bash(simctl context*)",
    "Bash(simctl runs list*)",
    "Bash(simctl runs status*)",
    "Bash(simctl runs sync*)",
    "Bash(simctl runs jobs*)",
    "Bash(simctl runs history*)",
    "Bash(simctl runs log*)",
    "Bash(simctl doctor*)",
    "Bash(simctl config show*)",
    # Generation (cheap, reversible by deleting the new files)
    "Bash(simctl case new *)",
    "Bash(simctl runs create *)",
    "Bash(simctl runs sweep *)",
    "Bash(simctl runs clone *)",
    "Bash(simctl runs extend *)",
    # Analysis (read + write into analysis/)
    "Bash(simctl analyze summarize*)",
    "Bash(simctl analyze collect*)",
    "Bash(simctl analyze plot*)",
    # Knowledge management (mutates .simctl/knowledge/ via simctl, reversible)
    "Bash(simctl knowledge list*)",
    "Bash(simctl knowledge show*)",
    "Bash(simctl knowledge facts*)",
    "Bash(simctl knowledge save*)",
    "Bash(simctl knowledge add-fact*)",
    "Bash(simctl knowledge source list*)",
    "Bash(simctl knowledge source status*)",
    "Bash(simctl knowledge source attach*)",
    "Bash(simctl knowledge source detach*)",
    "Bash(simctl knowledge source sync*)",
    "Bash(simctl knowledge source render*)",
    # Refs / config additions (mutates the corresponding TOML, which is
    # itself ask-listed below — the resulting prompt happens once, not twice)
    "Bash(simctl update-harness*)",
    "Bash(simctl update-refs*)",
    "Bash(simctl config add-simulator*)",
    "Bash(simctl config add-launcher*)",
    # Lifecycle move that does not delete data
    "Bash(simctl runs archive*)",
    "Bash(simctl runs cancel*)",
    # Dev tooling
    "Bash(uv run pytest*)",
    "Bash(uv run ruff*)",
    "Bash(uv run mypy*)",
    "Bash(source .venv/bin/activate*)",
    "Bash(cat runs/*/work/*.out*)",
    "Bash(cat runs/*/work/*.err*)",
    # Git: read-only and local commits.  Pushes are not auto-allowed; the
    # agent system prompt already says to only commit when explicitly asked.
    "Bash(git status*)",
    "Bash(git log*)",
    "Bash(git diff*)",
    "Bash(git commit*)",
)
# Bash commands that must always prompt the user.  Keep this list as short
# as possible — every entry here trains the user to dismiss prompts.
_ASK_BASH: Final[tuple[str, ...]] = (
    "Bash(simctl runs submit*)",  # spends HPC resources
    "Bash(simctl runs purge-work*)",  # deletes work/ files irreversibly
    "Bash(simctl runs delete*)",  # removes run directory irreversibly
)
_DENY_BASH: Final[tuple[str, ...]] = (
    "Bash(rm -rf *)",
    "Bash(git push --force*)",
    "Bash(git reset --hard*)",
)
# Paths the agent may freely Edit/Write without confirmation.
# tools/hpc-simctl/** is included so projects that dev-install the simctl
# repo from tools/hpc-simctl/ can iterate on it without per-edit prompts.
# .claude/{rules,skills,commands}/** are allowed because they are
# documentation-style files.  Only the actual policy files
# (.claude/settings.json, .claude/hooks/**) require confirmation.
_ALLOW_EDIT_PATHS: Final[tuple[str, ...]] = (
    "/campaign.toml",
    "/cases/**",
    "/surveys/**",
    "/runs/**/survey.toml",
    "/docs/**",
    "/README.md",
    "/tools/hpc-simctl/**",
    "/.claude/rules/**",
    "/.claude/skills/**",
    "/.claude/commands/**",
    "/.vscode/**",
    "/.idea/**",
)
# Edit/Write paths that always prompt.  Limited to project-defining and
# agent-behaviour-defining files.
_ASK_EDIT_PATHS: Final[tuple[str, ...]] = (
    "/simproject.toml",
    "/simulators.toml",
    "/launchers.toml",
    "/CLAUDE.md",
    "/AGENTS.md",
    "/**/CLAUDE.md",
    "/.claude/settings.json",
    "/.claude/settings.local.json",
    "/.claude/hooks/**",
)
_DENY_EDIT_PATHS: Final[tuple[str, ...]] = (
    "/SITE.md",
    "/runs/**/manifest.toml",
    "/runs/**/input/**",
    "/runs/**/submit/**",
    "/runs/**/work/**",
    "/runs/**/status/**",
    "/runs/**/analysis/**",
    "/.simctl/environment.toml",
    "/.simctl/knowledge/**",
    "/.simctl/insights/**",
    "/.simctl/facts.toml",
    "/refs/**",
    "/.venv/**",
    "/.git/**",
)
_DENY_READ_PATHS: Final[tuple[str, ...]] = (
    "/.env",
    "/.env.*",
    "/secrets/**",
    "~/.ssh/**",
    "~/.aws/credentials",
    "~/.config/gcloud/**",
    "~/.kube/config",
)


def _build_permission_rules(
    tools: tuple[str, ...],
    patterns: tuple[str, ...],
) -> list[str]:
    """Expand tool/path combinations into Claude permission rule strings."""
    rules: list[str] = []
    for tool in tools:
        rules.extend(f"{tool}({pattern})" for pattern in patterns)
    return rules


def build_claude_settings() -> str:
    """Build team-shared Claude Code settings for simctl projects.

    The returned settings declare allow / ask / deny rules only.  Behavioural
    expectations that earlier versions enforced via PreToolUse hooks (submit
    approval, run-directory protection, Bash write guards) are now documented
    in ``.claude/rules/simctl-workflow.md`` so they remain visible to the
    agent without forcing per-action shell hooks on the user.
    """
    allow_rules = list(_ALLOW_BASH)
    allow_rules.extend(_build_permission_rules(("Edit", "Write"), _ALLOW_EDIT_PATHS))

    ask_rules = list(_ASK_BASH)
    ask_rules.extend(_build_permission_rules(("Edit", "Write"), _ASK_EDIT_PATHS))

    deny_rules = list(_DENY_BASH)
    deny_rules.extend(_build_permission_rules(("Edit", "Write"), _DENY_EDIT_PATHS))
    deny_rules.extend(_build_permission_rules(("Read",), _DENY_READ_PATHS))

    settings = {
        "permissions": {
            "allow": allow_rules,
            "ask": ask_rules,
            "deny": deny_rules,
            "disableBypassPermissionsMode": "disable",
        },
    }
    return json.dumps(settings, ensure_ascii=False, indent=2) + "\n"
