---
name: improve-harness
description: "Trigger when the user asks to improve, audit, or update the AI agent harness configuration — CLAUDE.md, .claude/ rules/skills/agents/settings, or the scaffolded project-side harness templates in src/simctl/templates/."
---

# Harness 改善スキル

simctl には **2 つのハーネス** がある。どちらを改善するか確認すること:

| ハーネス | 場所 | 対象者 |
|---|---|---|
| **開発ハーネス** | `.claude/` (このリポジトリ直下) | simctl 開発者 |
| **プロジェクトハーネス** | `src/simctl/templates/` → `simctl init` が生成 | simctl を使うプロジェクトのエージェント |

## 改善の進め方

### 1. 現状の監査

```bash
# 開発ハーネスの構成確認
ls -R .claude/

# プロジェクトハーネスのテンプレート
ls src/simctl/templates/scaffold/rules/
ls src/simctl/templates/skills/
cat src/simctl/templates/agent.md
```

### 2. 改善パターン

**ルール (`.claude/rules/`)** — 開発中にエージェントが守るべき制約
- 品質ゲート (lint, test, type check)
- アーキテクチャ境界
- よくあるミス (Gotchas)
- ワークフロー規約

**スキル (`.claude/skills/<name>/SKILL.md`)** — 繰り返す定型作業
- description はトリガー条件を書く (「いつ発火すべきか」)
- ゴールと制約を書き、手順は詳細にしすぎない
- scripts/ や examples/ のサブディレクトリで progressive disclosure

**エージェント (`.claude/agents/<name>.md`)** — 独立コンテキストで動く専門家
- 実装系 (implement-core, implement-cli, etc.)
- シミュレータ系 (emses, beach)
- レビュー系 (spec-reviewer, test-writer)

**settings.json** — 許可 / 拒否ルール
- `permissions.allow` — 頻繁に使う安全なコマンド
- `permissions.deny` — 破壊的操作

### 3. プロジェクトハーネスの変更

プロジェクト側テンプレートを変更した場合:
- `src/simctl/templates/` のファイルを編集
- `harness/builder.py` の `build_harness_bundle()` に新ファイルを追加
- `tests/test_cli/test_init.py` にテストを追加
- `tests/test_cli/test_update_harness.py` にテストを追加
- 既存プロジェクトには `simctl update-harness` で反映される

### 4. 検証

```bash
# Lint/type/test
uv run ruff check src/ tests/
uv run mypy src/
uv run pytest tests/test_cli/test_init.py tests/test_cli/test_update_harness.py -x -q

# init が正しく生成するか確認
cd /tmp && mkdir test-harness && cd test-harness
uv run --directory <repo> simctl init -y
ls -la .claude/rules/ .claude/skills/
```

## Gotchas

- ルールファイルを追加しただけでは `build_harness_bundle` に含まれない。
  builder.py にエントリを足す必要がある (プロジェクトハーネスの場合)
- 開発ハーネス (`.claude/` 直下) は builder を経由しない。直接ファイルを置く
- settings.json の `allow` / `deny` は **先頭一致** でマッチする。
  パターンが広すぎると意図しないコマンドまで通る
- CLAUDE.md は 200 行以下を目標にする。詳細は `.claude/rules/` に分離
