# simctl Agent ユーザーガイド

simctl プロジェクトにおける Agent の作業ガイド。
現時点の標準ハーネスは Claude Code で、プロジェクトの `CLAUDE.md` から `@docs/agent-user-guide.md` で参照される。

## simctl の基本原則

- **run ディレクトリが主単位**: すべての操作は run_id または run ディレクトリを基点
- **manifest.toml が正本**: run の状態・由来・provenance はすべて manifest.toml に記録
- **cwd ベース**: 全コマンドはカレントディレクトリをデフォルトターゲット
- **case は `simctl case new` で生成**: case.toml を手書きしない
- **run は `simctl runs create` / `simctl runs sweep` で生成**: run ディレクトリを手で作らない

## コマンドクイックリファレンス

| 操作 | コマンド |
|------|---------|
| プロジェクト状況把握 | `simctl context --json` |
| case テンプレート生成 | `simctl case new <name>` |
| 最小 case テンプレート生成 | `simctl case new <name> --minimal` |
| survey 付き case 生成 | `simctl case new <name> --survey` |
| run 生成 | `simctl runs create <case>` |
| survey 全 run 生成 | `simctl runs sweep <survey>` |
| sweep 内容を確認だけ | `simctl runs sweep <survey> --dry-run` |
| job 投入 | `simctl runs submit` |
| 全 run 一括投入 | `simctl runs submit --all` |
| キュー上書き / 依存ジョブ | `simctl runs submit -qn <queue>` / `--afterok <job_id>` |
| 状態確認 (単一/複数/survey 一括) | `simctl runs status [RUNS...]` |
| Slurm 同期 (単一/複数/survey 一括) | `simctl runs sync [RUNS...]` (bulk: created + terminal state は silent skip) |
| ログ確認 | `simctl runs log` |
| エラーログ | `simctl runs log -e` |
| 実行中ジョブ一覧 / 自動更新 | `simctl runs jobs` / `simctl runs jobs -w 30` |
| 複数 run の進捗ダッシュボード | `simctl runs dashboard runs/<survey>` (`-w 30`, `--all` 対応) |
| run 一覧 (複数 PATH 可) | `simctl runs list [PATHS...]` |
| run 停止 (scancel + sync) | `simctl runs cancel` |
| run のハード削除 (created/failed/cancelled) | `simctl runs delete` |
| 解析 | `simctl analyze summarize` |
| 集計 | `simctl analyze collect` |
| lab notebook に追記 | `simctl notes append "<title>" "<body>"` |
| lab notebook 日付一覧 | `simctl notes list` |
| lab notebook 内容表示 | `simctl notes show [DATE\|today\|latest]` |
| 知見保存 (curated) | `simctl knowledge save` |
| 知見一覧 | `simctl knowledge list` |
| 知見表示 | `simctl knowledge show <name>` |
| 構造化 fact 一覧 | `simctl knowledge facts` |
| fact 追加 | `simctl knowledge add-fact` |
| 外部知識ソース一覧 | `simctl knowledge source list` |
| 外部知識ソース同期 | `simctl knowledge source sync` |

## TOML ファイル体系

- `simproject.toml` — プロジェクト定義
- `simulators.toml` — シミュレータ設定
- `launchers.toml` — ランチャー設定
- `campaign.toml` — 研究意図・計画
- `cases/**/case.toml` — ケース定義
- `runs/**/survey.toml` — パラメータサーベイ定義
- `runs/**/Rxxxx/manifest.toml` — run メタデータ (自動生成、手動編集禁止)

## Lab notebook と curated knowledge の二層

実験で残す情報は **2 層** で管理する。Agent 自身の memory には保存しない。

| 種類 | 性質 | 書き先 | コマンド |
|---|---|---|---|
| 整理済の名前付き知見 | curated, durable, 上書き可 | `.simctl/insights/<name>.md` | `simctl knowledge save` |
| 機械可読 atomic claim | curated, atomic | `.simctl/facts.toml` | `simctl knowledge add-fact` |
| 時系列の lab notebook (準備の意思決定, 観察, 仮説, TODO) | append-only, chronological | `notes/YYYY-MM-DD.md` | `simctl notes append` |
| 長文 refined レポート | refined, 改稿可 | `notes/reports/<topic>.md` | (直接編集) |

- 「結果をまとめて」「知見を記録して」等の整理済情報 → `simctl knowledge save` / `add-fact` で curated 層に
- 「今やってる作業のメモ」「途中経過」「議論の流れ」「準備フェーズの意思決定」 → `simctl notes append` で lab notebook に
- 価値が出てきたら `notes/` → `notes/reports/` → `.simctl/insights/` / `facts.toml` の順に昇格

`/note` skill は **準備フェーズから使う**。campaign 設計, case 設計,
survey 設計, run 生成, 投入の各タイミングで意思決定の理由・トレードオフ・
却下した代替案を `notes/YYYY-MM-DD.md` に残しておくと、後の `/learn`
(curated 化) の素材として再利用できる。

```bash
# 準備フェーズで意思決定を残す
simctl notes append "Series A 設計" - <<'EOF'
独立軸: vti = 1..19 eV (10 点). 4σ CFL で 19 eV が上限.
固定: vflow=400 km/s. 没案: vflow も振る → 資源不足.
EOF

# 後で日付一覧 → 内容を確認
simctl notes list
simctl notes show 2026-04-08
simctl notes show today    # 今日
simctl notes show latest   # 一番新しい日

# /learn 時に notes を素材として読み込む
simctl notes show latest | head -100
```

## ハーネスのガード

`simctl init` は `.claude/settings.json` と `.claude/hooks/` も生成し、
Claude Code 向けに project 内の保護ルールを設定する。

- 直接編集してよいのは主に `campaign.toml`、`cases/**`、`runs/**/survey.toml`、通常の docs
- 直接編集してはいけないのは `runs/**/manifest.toml`、`input/**`、`submit/**`、`work/**`、`SITE.md`
- `.simctl/insights/` と `.simctl/facts.toml` は `simctl knowledge save` / `add-fact` を使う
- `notes/YYYY-MM-DD.md` は `simctl notes append` 経由で append-only に追記する (既存 entry を書き換えない)
- `simctl runs submit` は `--dry-run` を除いて実行前に確認を挟む
- `simctl runs cancel` は harness 上 allow 扱いだが、実行前に対象 run と理由は報告する

## 状態遷移

```
created → submitted → running → completed
created/submitted/running → failed
submitted/running → cancelled
completed → archived → purged
```

`simctl runs cancel` は `submitted` / `running` の run に対して `scancel` と
`simctl runs sync` をまとめて実行し、`cancelled` 状態に遷移させる安全な経路。
`simctl runs delete` はライフサイクル外の操作で、`created` / `cancelled` / `failed`
の run ディレクトリを直接削除する (`completed` / `archived` の run には使えないので
`archive` → `purge-work` を使うこと)。

## 知識の活用

作業開始時に知識層を読んで、既知の制約や過去の知見を把握する。

| 情報 | 場所 | 読むタイミング |
|------|------|---------------|
| 研究意図・仮説 | `campaign.toml` | 作業開始時 |
| 構造化 fact (制約・依存性) | `.simctl/facts.toml` | パラメータ設計・検証時 |
| 実験知見 (Markdown) | `.simctl/insights/` | 作業開始時・解析後 |
| シミュレータドキュメント | `.simctl/knowledge/`, `refs/` | パラメータ設計時 |
| 実行環境 | `.simctl/environment.toml` | job 設定・launcher 選択時 |
| 外部共有知識 | `refs/knowledge/` | 必要に応じて |

### 読む

```bash
simctl knowledge list                     # 知見の一覧
simctl knowledge list -s emses -t constraint  # フィルタ付き
simctl knowledge show <name>              # 知見の全文表示
simctl knowledge facts                    # 構造化 fact の一覧
simctl knowledge facts --scope emses -c high  # フィルタ付き
```

### 書く

知見の保存は `/learn` スキル経由で行う。Agent 自身の memory には保存しない。

```bash
simctl knowledge save <name> -t <type> -s <simulator> -m "<内容>"
simctl knowledge add-fact "<claim>" -t <type> -s <simulator> -c <confidence>
```

詳細な仕様は [knowledge-layer.md](knowledge-layer.md) を参照。

## Simulator Adapter のガイド

各シミュレータは `refs/<repo>/docs/agent-*.md` に固有のガイドを置く。
CLAUDE.md から `@import` で参照されるため、シミュレータ固有のパラメータ設定・
トラブルシューティング・ベストプラクティスはそちらを参照すること。
