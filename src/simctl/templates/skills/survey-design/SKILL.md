---
name: survey-design
description: Design a parameter survey. Use when planning a parameter sweep, creating survey.toml, or exploring parameter space.
disable-model-invocation: true
---

# パラメータサーベイを設計する

## 手順

1. 指定されたケースの `case.toml` と入力ファイルを読む
2. `refs/` 以下のシミュレータドキュメントでパラメータの意味と妥当な範囲を確認する
3. `.simctl/facts.toml` で既知の制約を確認する
4. `survey.toml` を生成する
5. 生成される run 数を報告する

```bash
# 既存 case の確認
cat cases/$ARGUMENTS/case.toml
simctl knowledge facts

# survey ディレクトリ作成と編集
mkdir -p runs/<category>/<survey_name>
# survey.toml を作成 (フォーマットは tools/hpc-simctl/docs/toml-reference.md 参照)

# run 展開と確認
simctl sweep runs/<category>/<survey_name>
simctl list runs/<category>/<survey_name>
```

## survey.toml のフォーマット

詳細は `tools/hpc-simctl/docs/toml-reference.md` の survey.toml セクションを参照。
