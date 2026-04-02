#!/bin/bash
# approve-run.sh — simctl runs submit の実行前承認フック
#
# 実ジョブ投入は必ず ask にし、dry-run / help だけは自動で通す。

set -euo pipefail

INPUT=$(cat)
COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // ""')
NORMALIZED=$(printf '%s' "$COMMAND" | tr '\\' '/')

if [[ "$NORMALIZED" == *"--dry-run"* ]] || [[ "$NORMALIZED" == *"--help"* ]]; then
    exit 0
fi

jq -n --arg cmd "$COMMAND" '{
  hookSpecificOutput: {
    hookEventName: "PreToolUse",
    permissionDecision: "ask",
    permissionDecisionReason: ("ジョブ投入の前に確認してください。\nコマンド: " + $cmd + "\n対象 run・queue・資源量が意図通りなら承認してください。")
  }
}'

