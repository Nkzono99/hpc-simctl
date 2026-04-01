---
name: analyze
description: Analyze completed runs and collect survey results. Use after runs complete to summarize findings.
---

# 完了した Run の結果を解析・集計する

## 個別 run の要約

```bash
cd <run_dir>
simctl summarize
```

## survey の集計

```bash
simctl collect $ARGUMENTS
```

## survey の plot

```bash
simctl plot $ARGUMENTS --list-columns
simctl plot $ARGUMENTS --x param.some_axis --y some_metric
```

## 手順

1. `simctl summarize` で各 run の要約を生成する
2. survey の場合は `simctl collect <dir>` を実行する
3. `collect` が生成した `summary/survey_summary.csv`, `summary/survey_summary.json`, `summary/figures_index.json`, `summary/survey_summary.md` を確認する
4. 必要なら `simctl plot <dir> --list-columns` で列を確認し、`--x/--y` を指定して図を生成する
5. completed run に `analysis/summary.json` が無い場合、`collect` が自動 summarize することを前提に進めてよい
6. 結果の概要と注目すべき傾向を報告する
7. 知見があれば `/learn` で保存する
