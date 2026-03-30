# {{ doc_name }} — {{ project_name }}

このプロジェクトは simctl (HPC シミュレーション管理 CLI) で管理されています。
人がベース入力ファイルと計算資源方針を与え、AI エージェントが
campaign 設計、case / survey 編集、run 生成、投入、監視、解析、
知見整理を半自動で進めることを想定しています。

## 運用モード

- 人が主に決めるもの: ベース入力ファイル、計算資源の上限、研究目的、公開してよい知見
- Agent が進めてよいもの:
  `campaign.toml` / `case.toml` / `survey.toml` の編集、run 生成、
  個別 run の投入、状態同期、ログ確認、要約・集計、知見整理
- 確認が必要なもの:
  初回の大規模 survey、`simctl run --all`、資源増加を伴う retry、
  `archive` / `purge-work`、実行バイナリやモジュール設定の変更
- destructive / 高コスト操作には、実行前に理由と想定影響を短く残す

## 最初にやること

1. `simctl context --json` で project / campaign / runs / recent_failures を把握する
2. **simctl の使い方がわからなければ `tools/hpc-simctl/docs/toml-reference.md` を読む**
   - TOML のフォーマットはここに全て書いてある。src/ は読まない
3. `campaign.toml`、関連する `cases/*/case.toml`、
   `runs/**/survey.toml`、`.simctl/facts.toml`、
   必要なら最近の log を読む
4. action の前に plan を JSON で明示する

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

plan にない高コスト操作をいきなり実行しないこと。

## 編集優先順位

1. `campaign.toml` で研究意図、変数、観測量を整理する
2. `cases/*/case.toml` で共通パラメータ、job 設定、分類を管理する
3. `runs/**/survey.toml` で掃引軸を定義する
4. `runs/**/input/*` の直接編集は、adapter で表現できない差分か、
   log を見たうえでの緊急修正に限る

- `runs/**/input/*` を直接直したら、同じ修正を上流の `case.toml` やテンプレートへ戻す
- `manifest.toml` は正本だが手動編集しない
- `work/` と `.simctl/knowledge/` の自動生成物は手で整形しない

## Case / Survey / Run の作り方 (Agent 向けチートシート)

**TOML フォーマットの詳細は `tools/hpc-simctl/docs/toml-reference.md` を参照すること。**
ここでは手順だけを示す。フィールドの意味・省略可否はドキュメントを見ること。

### 新しい Case を作る

1. `cases/<case_name>/` ディレクトリと `cases/<case_name>/input/` を作る
2. `cases/<case_name>/case.toml` を書く (フォーマットは `tools/hpc-simctl/docs/toml-reference.md` の case.toml セクション参照)
3. シミュレータの入力ファイル (例: `plasma.toml`) を `input/` に置く
   - `input/` 以下が run の `input/` にそのままコピーされる

```
cases/my_new_case/
  case.toml            # メタデータ・パラメータ定義
  input/               # テンプレート入力ファイル
    plasma.toml
```

### 新しい Survey を作る

1. `runs/` 以下に survey ディレクトリを作る (分類階層は自由)
2. `survey.toml` を書く (フォーマットは `tools/hpc-simctl/docs/toml-reference.md` の survey.toml セクション参照)
3. `simctl sweep <survey_dir>` で run を一括生成する

```bash
# 例
mkdir -p runs/sheath/angle_scan
# → runs/sheath/angle_scan/survey.toml を編集
simctl sweep runs/sheath/angle_scan
# → runs/sheath/angle_scan/R20260330-0001/ 等が自動生成される
```

### 単一 Run を作る

```bash
simctl create <case_name> --dest <path>
# 例: simctl create my_case --dest runs/sheath/test
```

### やってはいけないこと

- `Rxxxx/` ディレクトリを mkdir で作る
- `manifest.toml` を Write で書く
- `Rxxxx/input/` にファイルを直接置く
- `Rxxxx/submit/job.sh` を手書きする
- これらは全て `simctl create` / `simctl sweep` が自動で行う

## 推奨ワークフロー

- Design: `campaign.toml`, `case.toml`, `survey.toml`
  Commands: `simctl context --json`, `simctl config show`,
  `simctl knowledge list`, `simctl knowledge facts`
- Create: `cases/`, `runs/**/survey.toml`
  Commands: `simctl new`, `simctl create`, `simctl sweep`
- Submit: `runs/**/R*/`
  Commands: `simctl run`, `simctl run --all`
- Monitor: `manifest.toml`, `work/*.out`, `work/*.err`
  Commands: `simctl status`, `simctl sync`, `simctl log`,
  `simctl jobs`, `simctl history`, `simctl list`
- Analyze: `analysis/`, survey directory
  Commands: `simctl summarize`, `simctl collect`
- Learn: `.simctl/insights/`, `.simctl/facts.toml`
  Commands: `simctl knowledge save`, `simctl knowledge add-fact`,
  `simctl knowledge sync`

## 失敗時の扱い

- `submitted` / `running` が長く止まって見えるときは、
  まず `simctl sync` で状態を合わせる
- `timeout` / `oom` / `preempted` は retry 候補だが、job 条件の変更理由を plan に書く
- `exit_error` は必ず `simctl log -e` や `work/*.err` を確認してから再試行する
- 同じ run の試行回数が 3 回前後に達したら、自動 retry を止めて原因を要約する
- action registry を使う agent では `retry_run` は再投入そのものではなく、
  `failed -> created` の再準備とみなす

## 知見の記録

- 人向けの考察や途中メモは `simctl knowledge save` で `.simctl/insights/` に保存する
- 機械可読な安定知見は `simctl knowledge add-fact` で `.simctl/facts.toml` に追加する
- `high` confidence は、複数 run の再現か deterministic な確認がある場合だけ使う
- 既存 fact を修正するときは上書きせず、
  新しい fact を追加して `--supersedes fNNN` を使う

## 重要なファイル

- **`manifest.toml`** — run の正本。状態・パラメータ・provenance をすべて記録
- **`campaign.toml`** — 研究意図、仮説、変数、観測量
- **`simproject.toml`** — プロジェクト名・説明
- **`simulators.toml`** — シミュレータの adapter / executable / modules 定義
- **`launchers.toml`** — MPI ランチャーの設定
- **`case.toml`** — ケーステンプレートの定義
- **`survey.toml`** — パラメータサーベイの定義 (直積展開)
- **`tools/hpc-simctl/`** — simctl 本体のソースコード・ドキュメント (Git 管理外)
  - `docs/` — アーキテクチャ、TOML リファレンス等
  - `SPEC.md` — 仕様書
{% if simulator_guides %}

## シミュレータ固有知識

{{ simulator_guides }}
{% endif %}
{% if doc_repos %}

## リファレンスリポジトリ

`refs/` 以下にシミュレータのソースコード・ドキュメントを配置している (Git 管理外)。
パラメータの意味や入力ファイル形式を調べる際に参照すること。

{% for url, dest in doc_repos -%}
- **`refs/{{ dest }}/`** — {{ url }}
{% endfor %}
{% endif %}

## 環境構築

`simctl init` がプロジェクトルートに `.venv` と `tools/hpc-simctl/` を自動構築する。
手動セットアップが必要な場合は `SKILLS.md` の `/setup-env` を参照。

```bash
# ブートストラップ (simctl 未インストールでも実行可能)
uvx --from git+https://github.com/Nkzono99/hpc-simctl.git simctl init

# activate して利用開始
source .venv/bin/activate
simctl doctor
```

## 運用ルール

- run ディレクトリ (`Rxxxx/`) が全操作の基点
- `manifest.toml` が正本。手動編集は避け、simctl コマンド経由で更新する
- `work/` の大容量ファイルは Git 管理外 (.gitignore 済み)
- `.venv/` はプロジェクトルートに配置。Git 管理外
- `tools/hpc-simctl/` はプロジェクトルートに配置。Git 管理外
- パラメータ変更は case.toml / survey.toml で管理し、新しい run を生成する
- `refs/` 以下はシミュレータの参考資料。パラメータの意味を調べる際に参照する
- simctl のドキュメント・仕様書は `tools/hpc-simctl/` を参照する
- `.simctl/knowledge/` にナレッジインデックスがある。ドキュメントの所在はここで把握する
- シミュレータ更新時は `simctl update-refs` でリファレンスとナレッジを最新化する

## 絶対禁止事項

### run ディレクトリを手で作らない

run ディレクトリ (`Rxxxx/`) 内のファイル群 (`manifest.toml`, `input/`, `submit/job.sh`) を
**手動で作成・Write してはいけない**。必ず simctl CLI で生成する。

- 単一 run: `simctl create <case_name>` (cwd に run を生成)
- survey 展開: `simctl sweep <survey_dir>` (survey.toml から全 run を一括生成)

Agent が編集してよいのは以下のみ:
- `campaign.toml` / `case.toml` / `survey.toml` — 設計ファイル
- `runs/**/survey.toml` — 掃引軸の定義
- `cases/**/` 内のテンプレート入力ファイル (例: `plasma.toml`)

Agent が自分で書いてはいけないもの:
- `Rxxxx/manifest.toml` — simctl が自動生成・管理する
- `Rxxxx/input/*` — simctl create / sweep が case テンプレートからコピーする
- `Rxxxx/submit/job.sh` — simctl が launcher 設定から自動生成する

**正しい手順**: case.toml / survey.toml を編集 → `simctl sweep` or `simctl create` → run が自動生成される

## simctl の使い方を調べるとき

**ドキュメントを先に読むこと。ソースコードを読みに行かないこと。**

simctl の TOML フォーマット、コマンド体系、設計思想を知りたいときは、
以下の順序で情報源を参照する:

1. **`tools/hpc-simctl/docs/toml-reference.md`** — 全 TOML ファイルのフィールド定義・例
2. **`tools/hpc-simctl/docs/getting-started.md`** — ワークフロー・コマンド例
3. **`tools/hpc-simctl/SPEC.md`** — 仕様の詳細 (設計判断の根拠)
4. **`tools/hpc-simctl/docs/architecture.md`** — 内部設計 (adapter / launcher の仕組み)
5. **`schemas/*.json`** — JSON Schema (TOML の機械可読な定義)
6. **`simctl --help` / `simctl <command> --help`** — コマンドのオプション確認

`tools/hpc-simctl/src/` のソースコードを直接読むのは **最終手段**。
ドキュメントと `--help` で解決しない場合にのみ参照すること。

理由: src/ を読んでも実装の詳細に引きずられて正しい使い方がわからなくなる。
ドキュメントには「何をすべきか」が、ソースコードには「どう実装されているか」しか書かれていない。
