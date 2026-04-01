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
- 研究目的
- ベース入力ファイル
- 計算資源の上限
- 公開してよい知見
- 初回の大規模 survey 実施可否

### Agent が進めてよいもの
- `campaign.toml` の整理
- `cases/**/case.toml` の編集
- `runs/**/survey.toml` の編集
- `simctl create` / `simctl sweep` による run 生成
- 個別 run の投入 (`simctl run`)
- `simctl sync`, `simctl status`, `simctl log` による監視
- `simctl summarize`, `simctl collect` による解析
- `simctl knowledge save`, `simctl knowledge add-fact` による知見整理

### 確認が必要なもの
- 初回の大規模 survey
- `simctl run --all`
- 資源増加を伴う retry
- `simctl archive` / `simctl purge-work`
- 実行バイナリ、モジュール、launcher の変更
- `tools/hpc-simctl/` の編集提案

## 実行前のルール

複数ファイル編集または高コスト操作の前には、短い plan を出す。

```json
{
  "goal": "map stability boundary for dt and nx",
  "edits": [
    "campaign.toml",
    "cases/plasma/case.toml",
    "runs/plasma/stability/survey.toml"
  ],
  "commands": [
    "simctl sweep runs/plasma/stability",
    "simctl run --all runs/plasma/stability"
  ],
  "checkpoints": [
    "Confirm survey size and queue before bulk submit",
    "Review failed logs before retry"
  ]
}
```

- 高コスト操作では run 数・queue・retry 理由を書く
- plan にない高コスト操作をいきなり実行しない
- approval が必要な操作は、plan を出したところで止まる

## 正しい進め方

### 新しい実験を始める

- `campaign.toml` で研究意図を整理する
- `refs/` の cookbook (`cookbook/index.toml`) で既存の入力例を探す
- **`simctl new <name>` で case テンプレートを生成する** (`cases/<sim>/` 下で実行。case.toml に launcher, simulator, job 設定の雛形が自動生成される)
- 生成された `case.toml` を編集してパラメータと job 設定を定義する
- 掃引したいときは `simctl new <name> --survey` で case + survey.toml を同時生成し、`/survey-design` で survey を組む
- run は `simctl create` / `simctl sweep` で生成する

### failed run を調べる

- `/debug-failed` を使う
- retry は `failure_reason` を見て判断する

### 知見を残す

「知見をまとめて」「結果を記録して」「知識を保存して」などの指示は、
**すべてプロジェクトの knowledge システムに保存する**。
Agent 自身の memory に保存してはいけない。

- `/learn` スキルを使う (`simctl knowledge save` / `simctl knowledge add-fact`)
- 保存先は `.simctl/insights/` と `.simctl/facts.toml` (プロジェクト内・Git 管理)
- `high` confidence は複数 run の再現か deterministic 確認がある場合だけ使う

## Simulator Cookbook

`refs/` 以下のシミュレータリポジトリに `cookbook/` がある場合、
入力例やフラグメントをパラメータ生成の出発点として使う。

### 読取順序

1. `refs/<repo>/cookbook/index.toml` で `tags` / `status` から候補を絞る
2. 候補 entry の `meta.toml` で `[applicability]` と `[recommended]` を確認
3. `input.toml` の実ファイルを読む
4. fragment を使うときは `[merge]` と `[compatibility]` を確認してから合成

### 注意

- `status = "stable"` の entry を優先する
- fragment の `[compatibility].requires_tags` を entry の tags と照合する
- `[edit_policy]` の `immutable` パラメータは変更しない
- `[cost]` を参考に計算資源を見積もる

## 重要なルール

- **simctl コマンド実行前に `.venv/` を activate する**
- **case は `simctl new` で生成する** (case.toml を手書きしない)
- run ディレクトリ (`Rxxxx/`) は手で作らない
- `manifest.toml` は手動編集しない
- `Rxxxx/input/*` は直接作らない
- `Rxxxx/submit/job.sh` は手書きしない
- run は必ず `simctl create` または `simctl sweep` で生成する
- `work/` と `.simctl/knowledge/` の自動生成物は手で整形しない
- **実験の知見・結果は Agent の memory ではなく `/learn` で保存する** (保存先: `.simctl/insights/`, `.simctl/facts.toml`)
- `runs/**/input/*` を緊急修正した場合は、同じ修正を上流へ戻す
- `tools/hpc-simctl/` は参照用。通常は編集しない

## 情報源の優先順位

1. `.claude/skills/` (スキルとコマンドリファレンス)
2. `refs/**/cookbook/index.toml` → `meta.toml` (入力例・パラメータ知識)
3. `tools/hpc-simctl/docs/toml-reference.md`
4. `tools/hpc-simctl/docs/getting-started.md`
5. `tools/hpc-simctl/SPEC.md`
6. `simctl --help` / `simctl <command> --help`
7. `tools/hpc-simctl/src/` は最後の手段

## 重要なファイル

- `campaign.toml`
- `simproject.toml`
- `simulators.toml`
- `launchers.toml`
- `cases/**/case.toml`
- `runs/**/survey.toml`
- `manifest.toml`
- `.simctl/facts.toml`
- `.simctl/insights/`
- `tools/hpc-simctl/`
{% if doc_repos %}

## リファレンスリポジトリ

{% for url, dest in doc_repos -%}
- `refs/{{ dest }}/` — cookbook: `refs/{{ dest }}/cookbook/`, docs: `refs/{{ dest }}/docs/`
{% endfor %}
{% endif %}
{% if agent_doc_imports %}

## Agent ガイド (@import)

{% for path in agent_doc_imports -%}
@{{ path }}
{% endfor %}
{% endif %}
{% if simulator_guides %}

## シミュレータ固有知識

{{ simulator_guides }}
{% endif %}
