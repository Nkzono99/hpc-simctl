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

## 手順

1. `simctl summarize` で各 run の要約を生成
2. survey の場合は `simctl collect <dir>` で集計 CSV を生成
3. 結果の概要と注目すべき傾向を報告
4. 知見があれば `/learn` で保存
