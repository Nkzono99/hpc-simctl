"""Claude Code harness policy and settings generation."""

from __future__ import annotations

import json
from typing import Final

_ALLOW_BASH: Final[tuple[str, ...]] = (
    "Bash(simctl context*)",
    "Bash(simctl runs list*)",
    "Bash(simctl runs status*)",
    "Bash(simctl runs sync*)",
    "Bash(simctl runs jobs*)",
    "Bash(simctl runs history*)",
    "Bash(simctl runs log*)",
    "Bash(simctl doctor*)",
    "Bash(simctl config show*)",
    "Bash(simctl case new *)",
    "Bash(simctl runs create *)",
    "Bash(simctl runs sweep *)",
    "Bash(simctl runs clone *)",
    "Bash(simctl runs extend *)",
    "Bash(simctl analyze summarize*)",
    "Bash(simctl analyze collect*)",
    "Bash(simctl knowledge list*)",
    "Bash(simctl knowledge show*)",
    "Bash(simctl knowledge facts*)",
    "Bash(simctl knowledge save*)",
    "Bash(simctl knowledge add-fact*)",
    "Bash(simctl knowledge source list*)",
    "Bash(simctl knowledge source status*)",
    "Bash(uv run pytest*)",
    "Bash(uv run ruff*)",
    "Bash(uv run mypy*)",
    "Bash(source .venv/bin/activate*)",
    "Bash(cat runs/*/work/*.out*)",
    "Bash(cat runs/*/work/*.err*)",
    "Bash(git status*)",
    "Bash(git log*)",
    "Bash(git diff*)",
)
_ASK_BASH: Final[tuple[str, ...]] = (
    "Bash(simctl runs archive*)",
    "Bash(simctl runs purge-work*)",
    "Bash(simctl update-refs*)",
    "Bash(simctl knowledge source attach*)",
    "Bash(simctl knowledge source detach*)",
    "Bash(simctl knowledge source sync*)",
    "Bash(simctl knowledge source render*)",
    "Bash(simctl config add-simulator*)",
    "Bash(simctl config add-launcher*)",
    "Bash(git commit*)",
)
_DENY_BASH: Final[tuple[str, ...]] = (
    "Bash(rm -rf *)",
    "Bash(git push --force*)",
    "Bash(git reset --hard*)",
)
_ALLOW_EDIT_PATHS: Final[tuple[str, ...]] = (
    "/campaign.toml",
    "/cases/**",
    "/surveys/**",
    "/runs/**/survey.toml",
    "/docs/**",
    "/README.md",
)
_ASK_EDIT_PATHS: Final[tuple[str, ...]] = (
    "/simproject.toml",
    "/simulators.toml",
    "/launchers.toml",
    "/CLAUDE.md",
    "/AGENTS.md",
    "/**/CLAUDE.md",
    "/.claude/**",
    "/.vscode/**",
    "/.idea/**",
    "/tools/hpc-simctl/**",
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
_PROTECT_FILES_COMMAND: Final[str] = (
    'bash "$CLAUDE_PROJECT_DIR/.claude/hooks/protect-files.sh"'
)
_GUARD_BASH_COMMAND: Final[str] = (
    'bash "$CLAUDE_PROJECT_DIR/.claude/hooks/guard-bash.sh"'
)
_APPROVE_RUN_COMMAND: Final[str] = (
    'bash "$CLAUDE_PROJECT_DIR/.claude/hooks/approve-run.sh"'
)

CLAUDE_HOOK_TEMPLATES: Final[tuple[tuple[str, str], ...]] = (
    ("approve-run.sh", "scaffold/hooks/approve-run.sh"),
    ("protect-files.sh", "scaffold/hooks/protect-files.sh"),
    ("guard-bash.sh", "scaffold/hooks/guard-bash.sh"),
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
    """Build team-shared Claude Code settings for simctl projects."""
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
        "hooks": {
            "PreToolUse": [
                {
                    "matcher": "Edit|Write",
                    "hooks": [
                        {
                            "type": "command",
                            "command": _PROTECT_FILES_COMMAND,
                        }
                    ],
                },
                {
                    "matcher": "Bash",
                    "hooks": [
                        {
                            "type": "command",
                            "command": _GUARD_BASH_COMMAND,
                        }
                    ],
                },
                {
                    "matcher": "Bash",
                    "if": "Bash(simctl runs submit*)",
                    "hooks": [
                        {
                            "type": "command",
                            "command": _APPROVE_RUN_COMMAND,
                        }
                    ],
                },
            ]
        },
    }
    return json.dumps(settings, ensure_ascii=False, indent=2) + "\n"
