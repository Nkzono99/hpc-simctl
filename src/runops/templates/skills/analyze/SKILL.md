---
name: analyze
description: Analyze completed runs and collect survey results. Use after runs complete to summarize findings.
---

# 完了した Run の結果を解析・集計する

## 個別 run の要約

```bash
cd <run_dir>
runops analyze summarize
```

## survey の集計

```bash
runops analyze collect $ARGUMENTS
```

## survey の plot

```bash
runops analyze plot $ARGUMENTS --list-columns
runops analyze plot $ARGUMENTS --list-recipes
runops analyze plot $ARGUMENTS --recipe completion-vs-dt
runops analyze plot $ARGUMENTS --x param.some_axis --y some_metric
```

## 手順

1. `runops analyze summarize` で各 run の要約を生成する
2. survey の場合は `runops analyze collect <dir>` を実行する
3. `collect` が生成した `summary/survey_summary.csv`, `summary/survey_summary.json`, `summary/figures_index.json`, `summary/survey_summary.md` を確認する
4. まず `runops analyze plot <dir> --list-recipes` を試し、使える recipe があれば `--recipe` を優先する
5. recipe が無い場合は `runops analyze plot <dir> --list-columns` で列を確認し、`--x/--y` を指定して図を生成する
6. 試行中の図やメモは `runs/**/analysis/scratch/` に置き、curated な出力だけを `analysis/` に残す
7. completed run に `analysis/summary.json` が無い場合、`collect` が自動 summarize することを前提に進めてよい
8. 結果の概要と注目すべき傾向を報告する
9. 知見があれば `/learn` で保存する
