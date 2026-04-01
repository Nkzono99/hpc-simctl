#!/bin/bash
# approve-run.sh — simctl run の実行前承認フック
#
# 動作:
#   1. 承認トークンがあれば → allow (トークン削除して実行許可)
#   2. なければ → deny (Claude にユーザー確認を促す)
#
# Claude は deny を受けたらユーザーに確認し、承認されたら
# トークンファイルを作成して再実行する。

set -euo pipefail

INPUT=$(cat)
COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command')
TOKEN_DIR="${CLAUDE_PROJECT_DIR:-.}/.claude/hooks"
TOKEN_FILE="$TOKEN_DIR/.approve-run-token"

# 承認トークンがあれば実行を許可
if [ -f "$TOKEN_FILE" ]; then
    rm -f "$TOKEN_FILE"
    exit 0
fi

# トークンがなければ deny — Claude にユーザー確認を促す
echo "⚠ ジョブ投入の承認が必要です: $COMMAND" >&2

jq -n --arg cmd "$COMMAND" '{
  hookSpecificOutput: {
    hookEventName: "PreToolUse",
    permissionDecision: "deny",
    permissionDecisionReason: ("ジョブ投入にはユーザー承認が必要です。\nコマンド: " + $cmd + "\n承認されたら .claude/hooks/.approve-run-token を作成して再実行してください。")
  }
}'
