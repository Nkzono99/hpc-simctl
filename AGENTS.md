# AGENTS.md — hpc-simctl Agent Operating Rules

AI エージェントが `simctl init` 済みプロジェクトで作業する際の運用ルール。

## 目的と前提

- 本プロジェクトの運用モードは **完全自動ではなく半自動** である
- 人間は少なくとも以下を与える
  - 利用する simulator / launcher の設定
  - ベースとなる入力テンプレート (`plasma.toml`, `beach.toml` など)
- エージェントは以下を支援してよい
  - `campaign.toml` の作成・更新
  - `case.toml` / `survey.toml` の作成・更新
  - run 生成、投入、同期、ログ確認、解析、知識記録
- コストの高い実行、破壊的操作、研究上の意味が変わる編集は **人間の確認を挟む**

## 最重要ルール

1. **最初に context を読む**
   - 作業開始時に `simctl context --json` を実行して現在状態を把握する
2. **実行前に plan を明示する**
   - action 実行や重要ファイル編集の前に、何をするかを plan として示す
3. **plan にない action は実行しない**
   - 途中で方針変更が必要になったら plan を更新してから進む
4. **高コスト / 破壊的 / 意味変更の大きい操作は確認を挟む**
   - 特に bulk submit、resource 増加、archive、purge は確認対象
5. **run より上流を優先して直す**
   - 再利用される変更は `campaign.toml` / `case.toml` / `survey.toml` に反映し、生成済み run の入力を場当たり的に直し続けない

## 作業フェーズ

### Phase 0: Context

- `simctl context --json` で project 状態を読む
- 必要に応じて以下も確認する
  - `campaign.toml`
  - `cases/*/case.toml`
  - `runs/**/survey.toml`
  - `.simctl/facts.toml`
  - 最近失敗した run の `manifest.toml` と log

### Phase 1: Planning

- まず不足を分類する
  - **design**: campaign / case / survey が未整備
  - **execution**: create / submit / sync / retry / log
  - **analysis**: summarize / collect / fact / insight
- 実行予定を JSON で示す

```json
{
  "assumptions": [
    "base input template already exists in cases/flat_surface/plasma.toml"
  ],
  "plan": [
    {
      "kind": "edit",
      "target": "campaign.toml",
      "reason": "研究仮説と観測量を明文化する"
    },
    {
      "kind": "edit",
      "target": "runs/angle_scan/survey.toml",
      "reason": "campaign の independent variables を survey 軸に反映する"
    },
    {
      "kind": "action",
      "action": "create_run",
      "target": "runs/angle_scan",
      "reason": "survey から run を展開する"
    },
    {
      "kind": "action",
      "action": "submit_run",
      "target": "runs/angle_scan/R20260330-0001",
      "reason": "レビュー済み run を投入する",
      "requires_confirmation": true
    }
  ]
}
```

### Phase 2: Execution

- plan の項目を順に実行する
- action 実行時は `simctl.core.actions.execute_action()` または対応 CLI を使う
- 各 action の結果で以下を確認する
  - `status == success`
  - `precondition_failed`
  - `error`
- `precondition_failed` / `error` が出たら、そのまま次へ進まず plan を更新する

## どのファイルをどう編集するか

### 優先順位

1. `campaign.toml`
   - 研究意図、仮説、変数、観測量を定義する
2. `cases/*/case.toml`
   - ベース条件、job 設定、共通 params を定義する
3. `runs/**/survey.toml`
   - 探索軸、命名、survey 単位の job override を定義する
4. `runs/**/input/*`
   - その run だけの診断的修正に限定する

### 編集ルール

- 再利用したい変更は run ではなく case / survey に戻す
- 生成済み run の `input/*` を直接編集するのは以下に限定する
  - 単発の失敗診断
  - continuation / retry 前の一時調整
  - survey に戻すと過去 run の provenance が不明瞭になる場合
- run の `input/*` を直接編集したら plan に理由を書く

## Action Registry の使い方

利用可能な action は `simctl.core.actions.ACTION_SPECS` に従う。

| Action | 用途 | 主な前提条件 |
|--------|------|-------------|
| `create_run` | case から run 生成 | project loaded, case exists |
| `create_survey` | survey.toml から複数 run を展開 | project loaded, survey.toml exists, base case exists |
| `submit_run` | created run を Slurm に投入 | state == created, job.sh exists |
| `sync_run` | submitted / running run の状態同期 | state in {submitted, running}, job_id recorded |
| `show_log` | 最新 log の確認 | run has been submitted at least once |
| `summarize_run` | completed run の解析 summary 生成 | state == completed |
| `collect_survey` | survey 集計 | at least one completed run exists |
| `retry_run` | failed run を retry 用に `created` に戻す | state == failed |
| `archive_run` | completed run を archived にする | state == completed |
| `purge_work` | archived run の purgeable な work を削除する | state == archived |
| `save_insight` | Markdown insight を `.simctl/insights/` に保存する | project loaded |
| `add_fact` | structured fact を追加する | project loaded |

### 注意

- `ACTION_SPECS` には `risk_level` / `cost_class` / `requires_confirmation` /
  `confirmation_reason` / `confirmation_conditions` が含まれる
  - Agent は prose だけでなく metadata も見て確認境界を判断する
- `retry_run` は **再投入そのものではない**
  - `failed -> created` に戻すだけで、必要なら次に `submit_run` を行う
- `collect_survey` は completed run が 1 件もない状態では実行しない
- `archive_run` / `purge_work` は action registry でも confirmation metadata を持つ
  - CLI では `simctl runs archive` / `simctl runs purge-work` が対話確認を行う

## Retry Policy

失敗 run の対処は `simctl.core.retry.suggest_retry()` の提案に従う。

| failure_reason | 第一候補 | confidence |
|---------------|----------|------------|
| `timeout` | `retry_run` + walltime 延長 | high |
| `oom` | `retry_run` + memory 増加 | high |
| `preempted` | `retry_run` + 同一設定 | high |
| `node_fail` | `retry_run` + 同一設定 | high |
| `boot_fail` | `retry_run` + 同一設定 | high |
| `exit_error` | `show_log` | high |

### retry の必須ルール

- 最大試行回数は 3
  - それ以上は手動検査に切り替える
- `exit_error` は必ず log を確認してから判断する
- `retry_run` 実行前に以下を plan に書く
  - failure_reason
  - 現在の attempt 数
  - 変更する resource / parameter
  - 変更しない理由

## Human-in-the-loop の確認ポイント

以下は原則として人間の確認を挟む。

### 必須確認

- 新しい survey の初回 bulk submit
- `simctl runs submit --all` 相当の一括投入
- walltime / memory / node 数を増やす retry
- `simctl runs archive`
- `simctl runs purge-work`
- 研究仮説の意味が変わる `campaign.toml` 編集

### 推奨確認

- 新しい case の初回作成
- baseline template (`plasma.toml`, `beach.toml` など) の大幅変更
- completed run の集計結果から high confidence fact を作る前

## Facts と Insights の扱い

### 使い分け

- `insight`
  - 人間向け Markdown の考察、結果要約、分析メモ
- `fact`
  - AI / ツール向け structured claim

### Confidence の基準

| Level | 基準 |
|-------|------|
| `high` | 2件以上の独立 run で再現、または deterministic check で検証済み |
| `medium` | 1件の明確な run 観測 |
| `low` | 解釈を含む暫定知見 |

### fact を作る条件

- run の結果から得られた定量的知見
- パラメータ制約条件
- 安定性条件 (CFL, 解像度要件)
- 実験間の依存関係
- 運用ポリシーとして再利用したい知見

### fact を作らない条件

- 一時的なエラー (`node_fail`, `preempted`)
- 環境依存の問題 (特定ノードのみの不具合)
- 1回しか観測していない現象を high confidence の `constraint` として残すこと

### fact 作成時の推奨フィールド

- `fact_type`
- `simulator`
- `scope_case`
- `scope_text`
- `param_name`
- `confidence`
- `source_run`
- `evidence_kind`
- `evidence_ref`
- `supersedes`

### supersedes ルール

- 既存 fact は直接編集しない
- 修正時は新しい fact を追加し `supersedes = "f001"` を設定する
- `query_facts()` はデフォルトで superseded fact を除外する

## 優先順位の判断基準

1. **Context 不足の解消**
   - campaign / case / survey が未整備なら先に整える
2. **active run の同期**
   - submitted / running のまま止まっている run を `sync_run`
3. **failed run の診断**
   - `show_log` と failure_reason を確認する
4. **retry 候補の準備**
   - timeout / oom / preempted / node_fail を優先
5. **created run の投入**
   - review 済み run のみ `submit_run`
6. **completed run の解析**
   - `summarize_run`、必要なら `collect_survey`
7. **知識の記録**
   - facts / insights を追加する

## 禁止事項

- context を読まずに作業を始めること
- plan なしで複数 action を連続実行すること
- `exit_error` の run を log 確認なしで retry すること
- `archive` / `purge-work` を確認なしで実行すること
- `hypothesis` をそのまま high confidence fact にすること
- 本来 case / survey に戻すべき変更を、run の `input/*` にだけ積み続けること
