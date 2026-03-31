# {{ doc_name }} — {{ project_name }}

このプロジェクトは simctl で管理されています。
人が研究目的・ベース入力・計算資源上限を決め、Agent はその範囲で
campaign 設計、case / survey 編集、run 生成、投入、監視、解析、知見整理を進めます。

## まずやること

1. `simctl context` で project の現在地を把握する
2. `campaign.toml` を読む
3. 関連する `cases/**/case.toml` と `runs/**/survey.toml` を読む
4. `.simctl/facts.toml` を読む
5. 必要なら最近の failed run の `simctl status` / `simctl log -e` を見る
6. **定型作業はまず `SKILLS.md` の該当節を見る**

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
- `case.toml` で共通条件を定義する
- 掃引したいときは `survey.toml` を作る
- run は `simctl create` / `simctl sweep` で生成する
- **具体例は `SKILLS.md` を参照**

### failed run を調べる

- まず `simctl sync`
- 次に `simctl status`
- その後 `simctl log -e` や `work/*.err` を見る
- retry は `failure_reason` を見て判断する
- **具体例は `SKILLS.md` を参照**

### 知見を残す

- 人向けの考察は `simctl knowledge save`
- 機械可読な知見は `simctl knowledge add-fact`
- `high` confidence は複数 run の再現か deterministic 確認がある場合だけ使う

## 重要なルール

- run ディレクトリ (`Rxxxx/`) は手で作らない
- `manifest.toml` は手動編集しない
- `Rxxxx/input/*` は直接作らない
- `Rxxxx/submit/job.sh` は手書きしない
- run は必ず `simctl create` または `simctl sweep` で生成する
- `work/` と `.simctl/knowledge/` の自動生成物は手で整形しない
- `runs/**/input/*` を緊急修正した場合は、同じ修正を上流へ戻す
- `tools/hpc-simctl/` は参照用。通常は編集しない

## 情報源の優先順位

1. `SKILLS.md`
2. `tools/hpc-simctl/docs/toml-reference.md`
3. `tools/hpc-simctl/docs/getting-started.md`
4. `tools/hpc-simctl/SPEC.md`
5. `tools/hpc-simctl/docs/architecture.md`
6. `simctl --help` / `simctl <command> --help`
7. `tools/hpc-simctl/src/` は最後の手段

原則として、**まず実行例を見る**。
詳細が必要なときだけ docs / SPEC に降りる。

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
- `refs/{{ dest }}/` — {{ url }}
{% endfor %}
{% endif %}
{% if simulator_guides %}

## シミュレータ固有知識

{{ simulator_guides }}
{% endif %}
