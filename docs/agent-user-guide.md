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
| survey 付き case 生成 | `simctl case new <name> --survey` |
| run 生成 | `simctl runs create <case>` |
| survey 全 run 生成 | `simctl runs sweep <survey>` |
| job 投入 | `simctl runs submit` |
| 全 run 一括投入 | `simctl runs submit --all` |
| 状態確認 | `simctl runs status` |
| Slurm 同期 | `simctl runs sync` |
| ログ確認 | `simctl runs log` |
| エラーログ | `simctl runs log -e` |
| 解析 | `simctl analyze summarize` |
| 集計 | `simctl analyze collect` |
| 知見保存 | `simctl knowledge save` |
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

## 状態遷移

```
created → submitted → running → completed
created/submitted/running → failed
submitted/running → cancelled
completed → archived → purged
```

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
