#!/bin/bash
# protect-files.sh — Edit / Write で触ってはいけない generated file を遮断する

set -euo pipefail

INPUT=$(cat)
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // ""')
PROJECT_DIR=$(printf '%s' "${CLAUDE_PROJECT_DIR:-}" | tr '\\' '/')
NORMALIZED=$(printf '%s' "$FILE_PATH" | tr '\\' '/')
RELATIVE="$NORMALIZED"

if [[ -n "$PROJECT_DIR" && "$NORMALIZED" == "$PROJECT_DIR/"* ]]; then
    RELATIVE=${NORMALIZED#"$PROJECT_DIR"/}
fi

PROTECTED_PATTERNS=(
    "SITE.md"
    "runs/*/manifest.toml"
    "runs/*/input/*"
    "runs/*/submit/*"
    "runs/*/work/*"
    "runs/*/status/*"
    "runs/*/analysis/*"
    ".simctl/environment.toml"
    ".simctl/knowledge/*"
    ".simctl/insights/*"
    ".simctl/facts.toml"
    "refs/*"
    ".venv/*"
    ".git/*"
)

for pattern in "${PROTECTED_PATTERNS[@]}"; do
    if [[ "$RELATIVE" == $pattern ]]; then
        jq -n --arg path "$FILE_PATH" --arg pattern "$pattern" '{
          hookSpecificOutput: {
            hookEventName: "PreToolUse",
            permissionDecision: "deny",
            permissionDecisionReason: ("直接編集できない保護対象です: " + $path + "\n一致ルール: " + $pattern + "\nsimctl コマンド経由で更新するか、上流の case / survey / knowledge コマンドを使ってください。")
          }
        }'
        exit 0
    fi
done

exit 0
