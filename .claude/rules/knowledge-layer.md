# 知識層 (Knowledge Layer)

AI エージェントがシミュレーションを自律的に行うための知識管理。
詳細は `docs/knowledge-layer.md` を参照。

## 知識の種類

| 種類 | 保存先 | 更新方法 |
|------|--------|----------|
| シミュレータ知識 | `refs/` + `.simctl/knowledge/` | `simctl update-refs` |
| 外部共有知識 | `simproject.toml` の `[knowledge]` | `knowledge source attach/sync` |
| 実行環境 | `.simctl/environment.toml` | `simctl doctor` |
| 研究意図 | `campaign.toml` | ユーザーが記述 |
| 実験知見 (curated) | `.simctl/insights/` | `knowledge save` / `knowledge source sync` |
| 構造化知識 (curated) | `.simctl/facts.toml` | `knowledge add-fact` / `knowledge facts` |
| lab notebook | `notes/YYYY-MM-DD.md` | `simctl notes append` |
| 長文レポート | `notes/reports/<topic>.md` | 直接編集 (改稿可) |

## 二層構造

- `.simctl/insights/` / `.simctl/facts.toml` は整理済の永続知見 (上書き可・名前付き・atomic)
- `notes/YYYY-MM-DD.md` は append-only な時系列ログ
- 価値が出てきたら `notes/reports/` → `.simctl/insights/` / `facts.toml` に昇格

## 外部知識ソース

複数プロジェクト間で共有する知識を外部リポジトリとして管理し、project に接続できる。

```bash
simctl knowledge source attach git shared-kb git@github.com:lab/hpc-shared-knowledge.git
simctl knowledge source attach path local-kb ../hpc-knowledge
simctl knowledge source sync
simctl knowledge source render
```

- `simctl init` 時に GitHub の `*shared_knowledge*` リポジトリを自動検索し接続
- `simctl setup` 時は `simproject.toml` に設定された知識ソースを自動同期
