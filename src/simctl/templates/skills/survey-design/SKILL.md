---
name: survey-design
description: Design a parameter survey. Use when planning a parameter sweep, creating survey.toml, or exploring parameter space.
---

# パラメータサーベイを設計する

## 手順

1. 指定されたケースの `case.toml` と入力ファイルを読む
2. `refs/` の cookbook で既存の入力例を探す
   - `cookbook/index.toml` で `tags` と `recommended_for` から候補を絞る
   - 候補の `meta.toml` で `[recommended].vary_first` と `[edit_policy]` を確認
   - `[cost]` から計算コストを見積もる
3. `.simctl/facts.toml` で既知の制約を確認する
4. `survey.toml` を生成する
5. 生成される run 数とコスト見積もりを報告する

## cookbook の活用

```bash
# cookbook の entry 一覧を確認
cat refs/<repo>/cookbook/index.toml

# 候補 entry の詳細を確認
cat refs/<repo>/cookbook/examples/<category>/<name>/meta.toml

# 入力例を参照
cat refs/<repo>/cookbook/examples/<category>/<name>/input.toml

# 既知の制約を確認
simctl knowledge facts
```

## survey の作成

```bash
mkdir -p runs/<category>/<survey_name>
# survey.toml を作成 (フォーマットは tools/hpc-simctl/docs/toml-reference.md 参照)
simctl runs sweep runs/<category>/<survey_name>
simctl runs list runs/<category>/<survey_name>
```

## 注意

- cookbook の `[edit_policy].immutable` パラメータは survey 軸にしない
- `[edit_policy].sensitive` パラメータを振る場合は理由を plan に書く
- `status = "stable"` の entry をベースにする
- fragment を使う場合は `[merge]` と `[compatibility]` を確認する

## TOML フォーマット

詳細は `tools/hpc-simctl/docs/toml-reference.md` の survey.toml セクションを参照。

