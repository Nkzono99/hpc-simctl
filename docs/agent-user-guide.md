# simctl Agent ユーザーガイド

simctl プロジェクトにおける Agent (Claude Code 等) の作業ガイド。
プロジェクトの CLAUDE.md から `@docs/agent-user-guide.md` で参照される。

## simctl の基本原則

- **run ディレクトリが主単位**: すべての操作は run_id または run ディレクトリを基点
- **manifest.toml が正本**: run の状態・由来・provenance はすべて manifest.toml に記録
- **cwd ベース**: 全コマンドはカレントディレクトリをデフォルトターゲット
- **case は `simctl new` で生成**: case.toml を手書きしない
- **run は `simctl create` / `simctl sweep` で生成**: run ディレクトリを手で作らない

## コマンドクイックリファレンス

| 操作 | コマンド |
|------|---------|
| プロジェクト状況把握 | `simctl context` |
| case テンプレート生成 | `simctl new <name>` |
| survey 付き case 生成 | `simctl new <name> --survey` |
| run 生成 | `simctl create <case>` |
| survey 全 run 生成 | `simctl sweep <survey>` |
| job 投入 | `simctl run` |
| 全 run 一括投入 | `simctl run --all` |
| 状態確認 | `simctl status` |
| Slurm 同期 | `simctl sync` |
| ログ確認 | `simctl log` |
| エラーログ | `simctl log -e` |
| 解析 | `simctl summarize` |
| 集計 | `simctl collect` |
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
