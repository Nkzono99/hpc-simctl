# {{ doc_name }} — {{ project_name }}

このプロジェクトは simctl で管理されています。
人が研究目的・ベース入力・計算資源上限を決め、Agent はその範囲で
campaign 設計、case / survey 編集、run 生成、投入、監視、解析、知見整理を進めます。
現在の標準ハーネスは Claude Code / `CLAUDE.md` です。`AGENTS.md` は同じ運用ルールを共有する補助ファイルとして置いています。

## コミュニケーション

- **日本語で応答する**。コード・コマンド・変数名・エラーメッセージは英語のまま
- commit message は英語 (`fix:`, `feat:`, `refactor:`, `test:`, `docs:`)

## まずやること

0. **venv を activate する** — `source .venv/bin/activate` (Linux/Mac) / `.venv\Scripts\activate` (Windows)
   simctl や関連パッケージは `.venv/` にインストール済み。activate しないと simctl コマンドが使えない。
1. `simctl context --json` で project の現在地を把握する
2. `campaign.toml` を読む
3. 関連する `cases/**/case.toml` と `runs/**/survey.toml` を読む
4. `.simctl/facts.toml` を読み、必要なら `.simctl/knowledge/candidates/facts/` も確認する
5. 必要なら最近の failed run の `simctl runs status` / `simctl runs log -e` を見る
6. **定型作業は `/skill-name` で呼び出す** (下記「スキル」参照)

## スキル

`.claude/skills/` に定型作業のスキルがある。
`/skill-name` で直接呼び出すか、Claude が関連時に自動読み込みする。

| スキル | 用途 |
|---|---|
| `/new-case` | ケースを作成・編集する |
| `/create-run` | Run / Survey を生成する |
| `/survey-design` | パラメータサーベイを設計する |
| `/run-all` | survey の全 run を生成して投入する |
| `/check-status` | run / survey の状態を確認・同期する |
| `/analyze` | 完了 run の結果を解析・集計する |
| `/debug-failed` | 失敗 run を診断する |
| `/cleanup` | run のアーカイブ・整理 |
| `/learn` | 知見を記録する (curated, 名前付き) |
| `/note` | lab notebook に時系列エントリを追記する |
| `/setup-env` | 環境セットアップ |
| `/setup-campaign` | campaign.toml を研究テーマから設計する |

コマンドの詳細は `simctl-reference` スキル（自動読み込み）を参照。

## 役割分担

### 人が決めるもの
- 研究目的・ベース入力ファイル・計算資源の上限

### Agent が進めてよいもの
- campaign / case / survey の編集、run 生成・投入・監視・解析・知見整理
- `tools/hpc-simctl/` のソース修正 (editable install されているので即試せる)

### 確認が必要なもの
- 初回の大規模 survey / `simctl runs submit --all` / 資源増加を伴う retry
- `simctl runs purge-work` / `simctl runs delete` (実ファイル削除)
- 実行バイナリ、モジュール、launcher の変更

### 報告してから進めるもの
- `simctl runs cancel` (実行中の job を停止するが、追加確認プロンプトは不要)

## 進捗のコミット (義務)

意味のある作業単位ごとに **必ず Git コミットして履歴を残す**こと。
コミットを溜めると、後から状態を巻き戻したり差分を読んだりするのが困難になる。

### コミットするタイミング (最低限)

- campaign.toml / case / survey を新規作成・大幅変更したとき
- `simctl runs sweep` で新しい run を生成したとき (run 設定が確定したとき)
- 解析結果・知見を `.simctl/insights/` や `.simctl/facts.toml` に保存したとき
- `tools/hpc-simctl/` を修正してテストが通ったとき
- `simctl runs submit` の前 (投入前のスナップショットとして)
- 1 つの作業フェーズが完了したとき (例: 新しい survey の設計が固まった、全 run の解析が終わった)

### コミット粒度

- 1 コミット = 1 つの論理的変更にする (機能追加と無関係な編集を混ぜない)
- メッセージは「何を」「なぜ」変更したかを 1-2 行で記述
- 作業の途中でも、テストが通る・少なくとも壊れていない単位でコミットする

### しないこと

- 大量の変更を 1 つのコミットに詰め込まない
- コミットを溜めたまま新しい作業を始めない
- `git push --force` / `git reset --hard` で履歴を破壊しない (deny されている)

## 知見の保存と実験ノート

実験で得た情報には **2 種類** あり、書き先を分ける:

| 種類 | 性質 | 書き先 | スキル |
|---|---|---|---|
| 整理済の名前付き知見 | curated, durable | `.simctl/insights/<name>.md`, `.simctl/facts.toml` | `/learn` |
| 時系列の実験ノート (準備の意思決定, 試したこと, 観察, 仮説, TODO) | append-only, chronological | `notes/YYYY-MM-DD.md` | `/note` |

- 「結果をまとめて」「知見を記録して」等の整理済情報は **`/learn` で knowledge レイヤに**
- 「今やってる作業のメモ」「途中経過」「議論の流れ」は **`/note` で lab notebook に**
- どちらも Agent 自身の memory に保存してはいけない (会話を跨いで失われる)
- 共有 source 由来の candidate fact を採用するときは
  `simctl knowledge promote-fact` で local fact に昇格する

### `/note` は準備フェーズから使う

`/note` は解析時だけでなく **準備フェーズ (campaign 設計, case / survey 設計,
パラメータ選定, 投入計画) の意思決定もここに残す**。
意思決定の理由・トレードオフ・却下した代替案・不安要素を後から読み返せる
形にしておくと、再現性と方針修正の根拠が手に入る。具体例:

- 「vti を 1-19 eV にしたのは 4σ CFL で 19 eV が上限だから」
- 「no_plate ケースは EMSES v4.9.0 で動かないので保留」
- 「smoke test に R20260330-0001 / -0010 / -0019 を選んだ。両端と中央」
- 「Series A を先に投入する。Series B はこの結果を見てから」

設計フェーズの skill (`/setup-campaign`, `/new-case`, `/create-run`,
`/survey-design`, `/run-all`) は **完了時に `/note` で経緯を残してから次に進む**。

### `/learn` は `/note` を素材として使う

`/note` は raw な原料、`/learn` (curated knowledge) は整理済みの最終産物。
つまり **`/learn` を呼ぶときは、まず `notes/` を読んで素材を集める**:

1. `simctl notes list` で最近の lab notebook の日付を確認
2. 当該テーマに関連する `notes/YYYY-MM-DD.md` を `simctl notes show` で読む
3. 散らばっている観察・仮説・反例を一つの insight にまとめる
4. `simctl knowledge save` / `add-fact` で永続化する
5. 出処になった日付を insight 本文に書き残しておくと、後から検証可能

lab notebook の entry が積み上がってストーリーになったら、
`notes/reports/<topic>.md` に refined version を書き起こし、必要なら
`/learn` で `.simctl/insights/` / `facts.toml` に昇格する。

## サイト固有情報

@SITE.md

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
