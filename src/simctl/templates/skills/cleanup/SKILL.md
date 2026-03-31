---
name: cleanup
description: Archive completed runs and purge unnecessary work files. Use for housekeeping after experiments.
disable-model-invocation: true
---

# 完了・不要な Run を整理する

```bash
# 状態を確認
simctl list $ARGUMENTS

# completed run をアーカイブ
cd <run_dir>
simctl archive

# work/ の不要ファイルを削除
simctl purge-work
```

## 注意

- `archive` / `purge-work` は確認が必要な操作
- 実行前に対象と理由を報告する
