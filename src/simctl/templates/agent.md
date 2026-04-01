# {{ doc_name }} — {{ project_name }}

このプロジェクトは simctl で管理されています。
人が研究目的・ベース入力・計算資源上限を決め、Agent はその範囲で
campaign 設計、case / survey 編集、run 生成、投入、監視、解析、知見整理を進めます。

## まずやること

0. **venv を activate する** — `source .venv/bin/activate` (Linux/Mac) / `.venv\Scripts\activate` (Windows)
   simctl や関連パッケージは `.venv/` にインストール済み。activate しないと simctl コマンドが使えない。
1. `simctl context` で project の現在地を把握する
2. `campaign.toml` を読む
3. 関連する `cases/**/case.toml` と `runs/**/survey.toml` を読む
4. `.simctl/facts.toml` を読む
5. 必要なら最近の failed run の `simctl status` / `simctl log -e` を見る
6. **定型作業は `/skill-name` で呼び出す** (下記「スキル」参照)

## スキル

`.claude/skills/` に定型作業のスキルがある。
`/skill-name` で直接呼び出すか、Claude が関連時に自動読み込みする。

| スキル | 用途 |
|---|---|
| `/survey-design` | パラメータサーベイを設計する |
| `/run-all` | survey の全 run を生成して投入する |
| `/check-status` | run / survey の状態を確認・同期する |
| `/analyze` | 完了 run の結果を解析・集計する |
| `/debug-failed` | 失敗 run を診断する |
| `/cleanup` | run のアーカイブ・整理 |
| `/learn` | 知見を記録する |
| `/setup-env` | 環境セットアップ |

コマンドの詳細は `simctl-reference` スキル（自動読み込み）を参照。

## 役割分担

### 人が決めるもの
- 研究目的・ベース入力ファイル・計算資源の上限

### Agent が進めてよいもの
- campaign / case / survey の編集、run 生成・投入・監視・解析・知見整理

### 確認が必要なもの
- 初回の大規模 survey / `simctl run --all` / 資源増加を伴う retry
- `simctl archive` / `simctl purge-work`
- 実行バイナリ、モジュール、launcher の変更
- `tools/hpc-simctl/` の編集提案

## 知見の保存

「知見をまとめて」「結果を記録して」等の指示は **プロジェクトの knowledge システムに保存する**。
Agent 自身の memory に保存してはいけない。`/learn` スキルを使う。

## 情報源の優先順位

1. `.claude/skills/` → simulator docs / enabled knowledge → `tools/hpc-simctl/docs/`
2. `simctl --help` / `simctl <command> --help`
3. `tools/hpc-simctl/src/` は最後の手段
{% if doc_repos %}

## リファレンスリポジトリ

{% for url, dest in doc_repos -%}
- `refs/{{ dest }}/` — cookbook: `refs/{{ dest }}/cookbook/`, docs: `refs/{{ dest }}/docs/`
{% endfor %}
{% endif %}
{% if knowledge_imports_path %}

## 知識ソース (@import)

@{{ knowledge_imports_path }}
{% endif %}
