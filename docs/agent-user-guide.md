# simctl Agent ユーザーガイド

simctl プロジェクトにおける Agent (Claude Code 等) の作業ガイド。
プロジェクトの CLAUDE.md から `@docs/agent-user-guide.md` で参照される。

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

## Simulator Adapter のガイド

各シミュレータは `refs/<repo>/docs/agent-*.md` に固有のガイドを置く。
CLAUDE.md から `@import` で参照されるため、シミュレータ固有のパラメータ設定・
トラブルシューティング・ベストプラクティスはそちらを参照すること。

