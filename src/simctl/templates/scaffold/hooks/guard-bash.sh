#!/bin/bash
# guard-bash.sh — Bash 経由の direct write を path policy で制御する

set -euo pipefail

INPUT=$(cat)
COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // ""')
NORMALIZED=$(printf '%s' "$COMMAND" | tr '\\' '/')

is_write_command() {
    local cmd="$1"
    [[ "$cmd" == *">"* ]] \
        || [[ "$cmd" =~ (^|[[:space:]])tee([[:space:]]|$) ]] \
        || [[ "$cmd" =~ (^|[[:space:]])(cp|mv|rm|touch|mkdir|install|truncate|dd|ln)([[:space:]]|$) ]] \
        || [[ "$cmd" =~ (^|[[:space:]])sed([[:space:]].*)-i ]] \
        || [[ "$cmd" =~ (^|[[:space:]])perl([[:space:]].*)-i ]]
}

match_path() {
    local cmd="$1"
    shift
    local pattern
    for pattern in "$@"; do
        if [[ "$cmd" == *"$pattern"* ]]; then
            printf '%s' "$pattern"
            return 0
        fi
    done
    return 1
}

match_protected_run_path() {
    local cmd="$1"
    if [[ "$cmd" =~ runs/.+/manifest\.toml ]]; then
        printf '%s' 'runs/**/manifest.toml'
        return 0
    fi
    if [[ "$cmd" =~ runs/.+/input/ ]]; then
        printf '%s' 'runs/**/input/**'
        return 0
    fi
    if [[ "$cmd" =~ runs/.+/submit/ ]]; then
        printf '%s' 'runs/**/submit/**'
        return 0
    fi
    if [[ "$cmd" =~ runs/.+/work/ ]]; then
        printf '%s' 'runs/**/work/**'
        return 0
    fi
    if [[ "$cmd" =~ runs/.+/status/ ]]; then
        printf '%s' 'runs/**/status/**'
        return 0
    fi
    if [[ "$cmd" =~ runs/.+/analysis/ ]]; then
        printf '%s' 'runs/**/analysis/**'
        return 0
    fi
    return 1
}

if ! is_write_command "$NORMALIZED"; then
    exit 0
fi

DENY_PATTERNS=(
    "SITE.md"
    ".simctl/environment.toml"
    ".simctl/knowledge/"
    ".simctl/insights/"
    ".simctl/facts.toml"
    "refs/"
    ".venv/"
    ".git/"
)
ASK_PATTERNS=(
    "runs/"
    "simproject.toml"
    "simulators.toml"
    "launchers.toml"
    "CLAUDE.md"
    "AGENTS.md"
    ".claude/"
    ".vscode/"
    ".idea/"
    "tools/hpc-simctl/"
)

if MATCH=$(match_protected_run_path "$NORMALIZED"); then
    jq -n --arg cmd "$COMMAND" --arg path "$MATCH" '{
      hookSpecificOutput: {
        hookEventName: "PreToolUse",
        permissionDecision: "deny",
        permissionDecisionReason: ("Bash から保護対象へ直接書き込もうとしています。\n一致パターン: " + $path + "\nコマンド: " + $cmd + "\nrun の生成物は simctl コマンド経由で更新してください。")
      }
    }'
    exit 0
fi

if MATCH=$(match_path "$NORMALIZED" "${DENY_PATTERNS[@]}"); then
    jq -n --arg cmd "$COMMAND" --arg path "$MATCH" '{
      hookSpecificOutput: {
        hookEventName: "PreToolUse",
        permissionDecision: "deny",
        permissionDecisionReason: ("Bash から保護対象へ直接書き込もうとしています。\n一致パターン: " + $path + "\nコマンド: " + $cmd + "\nrun の生成物・knowledge・refs は simctl コマンド経由で更新してください。")
      }
    }'
    exit 0
fi

if MATCH=$(match_path "$NORMALIZED" "${ASK_PATTERNS[@]}"); then
    jq -n --arg cmd "$COMMAND" --arg path "$MATCH" '{
      hookSpecificOutput: {
        hookEventName: "PreToolUse",
        permissionDecision: "ask",
        permissionDecisionReason: ("Bash で設定系ファイルを書き換えようとしています。\n一致パターン: " + $path + "\nコマンド: " + $cmd + "\n意図した設定変更であることを確認してから承認してください。")
      }
    }'
    exit 0
fi

exit 0
