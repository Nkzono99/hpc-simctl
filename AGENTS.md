# AGENTS.md — hpc-simctl Agent Operating Rules

AI エージェントが hpc-simctl プロジェクトで作業する際の運用ルール。

## 基本原則

1. **まず context を読む** — 作業開始時に `simctl context` を実行し、プロジェクトの現在状態を把握する
2. **plan を立ててから実行する** — action を実行する前に、何をすべきかを plan として明示する
3. **plan にない action は実行しない** — 予定外の操作は禁止
4. **destructive action には理由を付ける** — archive, purge 等は実行理由を明記する

## Planner / Executor 分離

Agent の動作は2フェーズに分ける。

### Phase 1: Planning

- `simctl context` でプロジェクト状態を取得
- 失敗 run、未投入 run、completed run の優先順位を決定
- 実行すべき action のリストを JSON で作成

```json
{
  "plan": [
    {"action": "sync_run", "run_dir": "runs/scan/R20260330-0001", "reason": "submitted状態のまま"},
    {"action": "retry_run", "run_dir": "runs/scan/R20260330-0004", "reason": "timeout, walltime延長"}
  ]
}
```

### Phase 2: Execution

- plan の各 action を順に `execute_action()` で実行
- 各結果の `ActionResult.status` を確認
- `precondition_failed` / `error` の場合は plan を修正

## Action Registry

利用可能な action は `simctl.core.actions.ACTION_SPECS` で定義されている。

| Action | 説明 | 主な前提条件 |
|--------|------|-------------|
| `create_run` | ケースから run 生成 | project loaded, case exists |
| `submit_run` | Slurm に投入 | state == created, job.sh exists |
| `sync_run` | Slurm 状態を同期 | state in {submitted, running} |
| `show_log` | ログ表示 | submitted 以降 |
| `summarize_run` | 解析サマリ生成 | state == completed |
| `collect_survey` | survey 集計 | completed runs exist |
| `retry_run` | 失敗 run の再投入準備 | state == failed |
| `archive_run` | run アーカイブ | state == completed |
| `add_fact` | 知識 fact 記録 | project loaded |

## Retry Policy

失敗 run の対処は `simctl.core.retry.suggest_retry()` の提案に従う。

| failure_reason | 推奨 action | confidence |
|---------------|------------|------------|
| `timeout` | retry_run (walltime 延長) | high |
| `oom` | retry_run (memory 増加) | high |
| `preempted` | retry_run (同一設定) | high |
| `node_fail` | retry_run (同一設定) | high |
| `exit_error` | show_log → 原因特定 → retry_run | high → low |

- 最大試行回数: 3 (超えたら手動検査)
- `exit_error` は必ずログを確認してから判断する

## Facts の扱い

### Confidence の基準

| Level | 基準 |
|-------|------|
| `high` | 2件以上の独立 run で再現、または deterministic check で検証済み |
| `medium` | 1件の明確な run 観測 |
| `low` | 解釈を含む暫定知見 |

### Fact を作る条件

- run の結果から得られた定量的知見
- パラメータの制約条件
- 安定性条件 (CFL, 解像度要件)
- 実験間の依存関係

### Fact を作らない条件

- 一時的なエラー (node_fail, preempted)
- 環境依存の問題 (特定ノードの不具合)
- まだ1回しか観測していない現象 → `hypothesis` として記録

### supersedes ルール

- 既存 fact の修正は直接編集しない
- 新しい fact を作成し `supersedes = "f001"` を設定
- query_facts はデフォルトで superseded fact を除外する

## 優先順位の判断基準

1. **失敗 run の同期** — submitted/running のまま放置されている run を sync
2. **失敗 run の診断** — failed run のログ確認と原因特定
3. **retry 可能な run の再投入** — timeout/oom/preempted は自動 retry 候補
4. **未投入 run の投入** — created 状態の run を submit
5. **completed run の集計** — survey 内の全 run が完了したら collect
6. **知見の記録** — 実験結果から得られた fact の記録

## 禁止事項

- `archive_run` / `purge_work` を confirmation なしで実行しない
- `exit_error` の run を log 確認なしで retry しない
- `hypothesis` を `high confidence` の `constraint` として記録しない
- plan なしで複数の action を連続実行しない
