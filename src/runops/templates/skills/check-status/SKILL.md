---
name: check-status
description: Check and sync run or survey status. Use when monitoring job progress or after submission.
---

# Run / Survey の状態を確認・同期する

```bash
# プロジェクト全体の active jobs
runops runs jobs

# 特定ディレクトリの run 一覧
runops runs list $ARGUMENTS

# 個別 run の同期と確認
cd <run_dir>
runops runs sync
runops runs status
```

## survey 全体のステータスを確認する場合

```bash
runops runs list $ARGUMENTS
runops runs jobs
```

状態をサマリーとして報告する: completed / running / failed / submitted の数。

