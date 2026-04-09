# 主要コマンド一覧

全コマンドは引数省略時にカレントディレクトリをデフォルトとする。

## プロジェクト管理

| コマンド | 説明 |
|---------|------|
| `simctl init [SIMS...] -y` | Project 初期化 (対話型がデフォルト) |
| `simctl setup [URL]` | 既存プロジェクトを clone + 環境セットアップ |
| `simctl doctor` | 環境検査 |
| `simctl context --json` | Agent 向け project context を JSON で取得 |
| `simctl config show` | 設定表示 |
| `simctl config add-simulator` | シミュレータ追加 (対話型) |
| `simctl config add-launcher` | ランチャー追加 (対話型) |
| `simctl update-harness` | ハーネスファイル再生成 |
| `simctl update-refs` | refs/ リポジトリ更新 + ナレッジインデックス再生成 |

## Case / Run 操作

| コマンド | 説明 |
|---------|------|
| `simctl case new CASE [--minimal] [--survey]` | case のスキャフォールド生成 |
| `simctl runs create CASE` | case から単一 run を生成 |
| `simctl runs sweep [DIR] [--dry-run]` | survey.toml からパラメータ直積で全 run 生成 |
| `simctl runs submit [RUN]` | run を sbatch で投入 (`-qn`, `--afterok` 対応) |
| `simctl runs submit --all [DIR]` | created な run を一括投入 |
| `simctl runs clone` | run 複製・派生 |
| `simctl runs extend` | スナップショットから継続 run 生成 |

## モニタリング

| コマンド | 説明 |
|---------|------|
| `simctl runs status [RUNS...]` | run 状態確認 (複数指定可) |
| `simctl runs sync [RUNS...]` | Slurm 状態を manifest に反映 |
| `simctl runs log [RUN]` | 最新 job の stdout/stderr 表示 + 進捗% |
| `simctl runs jobs [PATH] [--watch SECS]` | 実行中ジョブ一覧 |
| `simctl runs dashboard [TARGETS...] [--watch SECS]` | 複数 run の進捗表 |
| `simctl runs history [PATH]` | 投入履歴表示 |
| `simctl runs list [PATHS...]` | run 一覧表示 |

## 解析・知見

| コマンド | 説明 |
|---------|------|
| `simctl analyze summarize [RUN]` | run 解析 summary 生成 |
| `simctl analyze collect [DIR]` | survey 集計 |
| `simctl notes append TITLE [BODY]` | lab notebook に追記 |
| `simctl notes list` | lab notebook 日付一覧 |
| `simctl notes show [DATE]` | 指定日の lab notebook を表示 |
| `simctl knowledge save` | 知見を .simctl/insights/ に保存 |
| `simctl knowledge add-fact` | 構造化 fact を追加 |
| `simctl knowledge list` / `show` / `facts` | 知見の表示 |
| `simctl knowledge source attach/detach/sync/render/status` | 外部知識ソース管理 |

## ライフサイクル管理

| コマンド | 説明 |
|---------|------|
| `simctl runs archive [RUN]` | run アーカイブ (completed のみ) |
| `simctl runs purge-work [RUN]` | work/ 内の不要ファイル削除 (archived のみ) |
| `simctl runs cancel [RUN]` | scancel + sync (submitted/running を停止) |
| `simctl runs delete [RUN]` | run ディレクトリ削除 (created/cancelled/failed のみ) |
