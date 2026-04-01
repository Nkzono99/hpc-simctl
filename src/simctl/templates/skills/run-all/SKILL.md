---
name: run-all
description: Generate and submit all runs from a survey. Use when ready to launch a parameter sweep.
---

# サーベイの全 Run を生成して投入する

## 手順

1. `simctl sweep` で run 生成
2. `simctl list` で確認
3. run 数と queue を報告して承認を取る
4. `simctl run --all` で投入

```bash
simctl sweep $ARGUMENTS
simctl list $ARGUMENTS
# → run 数と queue を確認してから投入
cd $ARGUMENTS
simctl run --all -qn <queue>
```

## 注意

- `run --all` は高コスト操作。事前に plan を出す
- 初回の大規模 survey は承認を取る
- dry-run で確認: `simctl run --all --dry-run`
