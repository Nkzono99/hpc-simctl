---
name: release
description: "Prepare and publish a new runops release. Bump version, sync __init__.py, generate changelog, create commit and tag, and push to trigger PyPI publish."
---

# runops リリース

`/release` は新しいバージョンの runops をリリースするスキル。

## 使い方

```
/release patch      # 0.2.1 -> 0.2.2
/release minor      # 0.2.1 -> 0.3.0
/release major      # 0.2.1 -> 1.0.0
/release 0.3.0      # 明示的にバージョン指定
```

引数なしで呼んだ場合は、前回リリースからの変更を一覧し、
patch / minor / major のどれが適切か提案する。

## 手順

### 1. リリース可否を確認する

```bash
# 未コミットの変更がないか
git status --porcelain

# テストが全て通るか
uv run pytest tests/ -x -q

# lint / type check
uv run ruff check src/ tests/
uv run mypy src/
```

品質ゲートが通らなければリリースを中止する。

### 2. 変更内容を把握する

```bash
# 前回リリースタグからの変更
git log $(git describe --tags --abbrev=0 2>/dev/null || echo HEAD~20)..HEAD --oneline
```

commit message から以下を分類する:

- **Breaking changes** (`feat!:`, `BREAKING CHANGE`) → major bump 候補
- **New features** (`feat:`) → minor bump 候補
- **Bug fixes** (`fix:`) → patch bump 候補
- **Other** (`refactor:`, `test:`, `docs:`, `chore:`)

### 3. バージョンを決定する

引数で指定されていればそれを使う。なければ変更内容から提案し、
ユーザーに確認する。

### 4. バージョンを更新する

2 箇所を同時に更新する (**ずれ防止**):

1. `pyproject.toml` の `version = "X.Y.Z"` — pip / PyPI が参照する正本
2. `src/runops/__init__.py` の `__version__ = "X.Y.Z"` — ランタイム参照

### 5. コミットとタグ

```bash
git add pyproject.toml src/runops/__init__.py
git commit -m "chore: bump version to X.Y.Z"
git tag vX.Y.Z
```

### 6. push してリリース

ユーザーの確認を得てから push する:

```bash
git push origin main
git push origin vX.Y.Z
```

`v*` タグの push により `.github/workflows/publish.yml` が起動し、
CI が自動で PyPI にパブリッシュする。

### 7. 確認

```bash
gh run list --workflow=publish.yml --limit 1
```

## 引数なしの場合

前回タグからの変更一覧を表示し、推奨 bump レベルを提案する:

```
## リリース候補

現在: v0.2.1
前回リリースからの変更:

### New features (3)
- feat: add --qos option to runs submit
- feat: show overall summary after runs sync
- feat: add /feedback skill

### Bug fixes (2)
- fix: add explicit encoding="utf-8" to all read_text() calls
- fix: show actionable warning for leftover .new files

### Other (1)
- docs: add QOS section to camphor site documentation

→ 推奨: minor bump (0.2.1 → 0.3.0)
→ `/release minor` で実行できます
```
