---
name: cleanup
description: Archive completed runs and purge unnecessary work files. Use for housekeeping after experiments.
---

# 完了・不要な Run を整理する

```bash
# 状態を確認
simctl runs list $ARGUMENTS

# completed run をアーカイブ
cd <run_dir>
simctl runs archive

# work/ の不要ファイルを削除
simctl runs purge-work
```

## 注意

- `archive` / `purge-work` は確認が必要な操作
- 実行前に対象と理由を報告する

