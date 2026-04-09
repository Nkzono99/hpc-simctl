# CLAUDE.md — hpc-simctl

## プロジェクト概要

HPC 環境における Slurm ベースのシミュレーション実行管理 CLI ツール。
run ディレクトリを日常運用の主単位とし、パラメータサーベイ展開・job 投入・状態追跡・provenance 記録・解析補助を一貫して管理する。

仕様書: `SPEC.md`

## プロジェクトでの利用方法

simctl はプロジェクトごとにブートストラップインストールする。事前のグローバルインストールは不要。

```bash
# 新規プロジェクト作成
mkdir my-project && cd my-project
uvx --from hpc-simctl simctl init

# activate
source .venv/bin/activate
simctl doctor
```

`simctl init` が `.venv/` と `tools/hpc-simctl/` を自動構築し、editable install する。
Agent は `tools/hpc-simctl/docs/` や `tools/hpc-simctl/SPEC.md` を直接参照できる。

```bash
# 既存プロジェクトを clone + セットアップ
uvx --from hpc-simctl simctl setup https://github.com/user/my-project.git
source my-project/.venv/bin/activate
simctl doctor
```

## 技術スタック

- 言語: Python 3.10+
- パッケージ管理: uv (pyproject.toml)
- CLI フレームワーク: typer (click ベース)
- 設定ファイル形式: TOML (tomli / tomli-w)
- テスト: pytest
- Lint/Format: ruff
- 型チェック: mypy (strict)

## ディレクトリ構成

```
hpc-simctl/
  pyproject.toml
  src/
    simctl/
      __init__.py
      cli/              # CLI エントリポイント (typer)
        __init__.py
        main.py
        init.py         # simctl init / doctor
        setup.py        # simctl setup (clone + bootstrap)
        context.py      # simctl context
        new.py          # simctl case new
        create.py       # simctl runs create / sweep
        submit.py       # simctl runs submit
        status.py       # simctl runs status / sync
        log.py          # simctl runs log
        jobs.py         # simctl runs jobs (--watch 対応)
        history.py      # simctl runs history
        list.py         # simctl runs list (複数 PATH 対応)
        dashboard.py    # simctl runs dashboard (multi-run 進捗ビュー)
        clone.py        # simctl runs clone
        extend.py       # simctl runs extend
        analyze.py      # simctl analyze summarize / collect / plot
        manage.py       # simctl runs archive / purge-work / cancel / delete
        knowledge.py    # simctl knowledge / knowledge source
        config.py       # simctl config
        update.py       # simctl update
        update_harness.py # simctl update-harness
        update_refs.py  # simctl update-refs
        run_lookup.py   # run path / id lookup helper
      core/             # ドメインロジック
        __init__.py
        project.py      # Project 読込・検証
        case.py         # Case 読込・展開
        survey.py       # Survey 展開・parameter 直積
        run.py          # Run 生成・run_id 採番
        manifest.py     # manifest.toml 読書き
        state.py        # 状態遷移管理
        provenance.py   # コード provenance 取得
        discovery.py    # runs/ 再帰探索・run_id 一意性検証
        knowledge_source.py # 外部知識ソース管理
      adapters/         # Simulator Adapter
        __init__.py
        base.py         # SimulatorAdapter 抽象基底クラス
        registry.py     # Adapter 登録・lookup
      launchers/        # Launcher Profile
        __init__.py
        base.py         # Launcher 抽象基底クラス
        srun.py
        mpirun.py
        mpiexec.py
      jobgen/           # job.sh 生成
        __init__.py
        generator.py
      slurm/            # Slurm 連携 (sbatch / squeue / sacct)
        __init__.py
        submit.py
        query.py
      sites/            # bundled site preset (simctl init で読込)
        __init__.py
        camphor.toml
        camphor.md
      harness/          # Agent harness 定義 (Claude Code 等)
        __init__.py
        claude.py
      templates/        # project / case / survey 用 静的テンプレート
        __init__.py
        ...
  tests/
    conftest.py
    test_core/
    test_cli/
    test_adapters/
    test_launchers/
    test_slurm/
    fixtures/           # テスト用 TOML ファイル等
```

## 主要コマンド

| コマンド | 説明 |
|---------|------|
| `simctl init [SIMS...] -y` | Project 初期化 (対話型がデフォルト) |
| `simctl setup [URL]` | 既存プロジェクトを clone + 環境セットアップ |
| `simctl doctor` | 環境検査 |
| `simctl context --json` | Agent 向け project context を JSON で取得 |
| `simctl case new CASE [--minimal] [--survey]` | case のスキャフォールド生成 (`--minimal` で小さな bundled テンプレート、EMSES では `emu generate -u` を自動実行) |
| `simctl runs create CASE` | case から単一 run を生成 |
| `simctl runs sweep [DIR] [--dry-run]` | survey.toml からパラメータ直積で全 run 生成 (`--dry-run` で件数・パラメータ・概算 core-hour を表示するだけ) |
| `simctl runs submit [RUN]` | run を sbatch で投入 (`-qn`, `--afterok` 対応) |
| `simctl runs submit --all [DIR]` | created な run を一括投入 |
| `simctl runs log [RUN]` | 最新 job の stdout/stderr 表示 + 進捗% |
| `simctl runs status [RUNS...]` | run 状態確認 (run_id・run dir・survey dir を複数渡してまとめて表示可) |
| `simctl runs sync [RUNS...]` | Slurm 状態を manifest に反映 (bulk 対応: survey 配下の created run + terminal state な run は silent skip) |
| `simctl runs jobs [PATH] [--watch SECS]` | プロジェクト内の実行中ジョブ一覧 (`--watch` で N 秒ごとに自動更新) |
| `simctl runs dashboard [TARGETS...] [--watch SECS] [--all]` | 複数 run の進捗 (state, step/N, %, last Slurm state) を 1 つの表で表示 |
| `simctl runs history [PATH]` | 投入履歴表示 |
| `simctl runs list [PATHS...]` | run 一覧表示 (複数 PATH 指定可) |
| `simctl runs clone` | run 複製・派生 |
| `simctl runs extend` | スナップショットから継続 run 生成 |
| `simctl analyze summarize [RUN]` | run 解析 summary 生成 |
| `simctl analyze collect [DIR]` | survey 集計 |
| `simctl notes append TITLE [BODY]` | 今日の lab notebook (`notes/YYYY-MM-DD.md`) に追記 (`-` または省略で stdin) |
| `simctl notes list` | 最近の lab notebook 日付一覧 |
| `simctl notes show [DATE\|today\|latest]` | 指定日 (省略時 today) の lab notebook を表示 |
| `simctl runs archive [RUN]` | run アーカイブ (completed のみ) |
| `simctl runs purge-work [RUN]` | work/ 内の不要ファイル削除 (archived のみ) |
| `simctl runs cancel [RUN]` | scancel + sync を同時実行し、submitted/running な run を停止 |
| `simctl runs delete [RUN]` | created/cancelled/failed な run ディレクトリをハード削除 (completed/archived は archive→purge-work を使う) |
| `simctl config show` | 設定表示 |
| `simctl config add-simulator` | シミュレータ追加 (対話型) |
| `simctl config add-launcher` | ランチャー追加 (対話型) |
| `simctl update-harness` | ハーネスファイル再生成 (CLAUDE.md, rules, skills 等) |
| `simctl update-refs` | refs/ リポジトリ更新 + ナレッジインデックス再生成 |
| `simctl knowledge save` | 知見を .simctl/insights/ に保存 |
| `simctl knowledge add-fact` | 構造化 fact を .simctl/facts.toml に追加 |
| `simctl knowledge list` | 知見一覧表示 |
| `simctl knowledge facts` | 構造化 fact 一覧表示 |
| `simctl knowledge show` | 知見の詳細表示 |
| `simctl knowledge source list` | 外部知識ソース一覧表示 |
| `simctl knowledge source attach` | 外部知識ソースを接続 (git / path) |
| `simctl knowledge source detach` | 外部知識ソースを切断 |
| `simctl knowledge source sync` | 知識ソース同期 + 外部知見取り込み |
| `simctl knowledge source render` | 有効な profile から imports.md を生成 |
| `simctl knowledge source status` | 知識統合の状態表示 |

全コマンドは引数省略時にカレントディレクトリをデフォルトとする。

## 開発ルール

### コーディング規約

- ruff format / ruff check を CI で強制
- mypy strict モード
- テストカバレッジ 80% 以上を目標
- docstring は Google style

### 設計原則

- **run ディレクトリが主単位**: すべての操作は run_id または run ディレクトリを基点とする
- **不変と可変の分離**: run_id は不変、パスは可変（分類・整理用）
- **Simulator Adapter パターン**: simulator 固有処理は Adapter に閉じ込める。core は simulator に依存しない
- **Launcher Profile パターン**: MPI 起動方式は Launcher に閉じ込める
- **MPI に介入しない**: Python ツールは rank ごとのラッパにならない。job.sh で srun/mpirun を直接実行
- **manifest.toml が正本**: run の状態・由来・provenance はすべて manifest.toml に記録
- **cwd ベース**: 全コマンドはカレントディレクトリをデフォルトターゲットとする

### 後方互換性

- **現在は private リポジトリ**のため、後方互換性は気にしなくてよい
- コマンド名・引数・ファイル形式は自由に変更可能
- エイリアスや互換レイヤーは不要。古いインタフェースは削除する
- 将来 public 化する際に API を固める

### テスト方針

- Slurm 依存部分はモック化 (実 HPC なしでテスト可能にする)
- TOML 読書きは fixtures ディレクトリのサンプルファイルを使用
- CLI テストは typer の CliRunner を使用
- Adapter / Launcher は抽象基底クラスの contract test を用意

### Git 管理

- run の大容量出力 (work/outputs/, work/restart/, work/tmp/) は .gitignore で除外
- テスト fixtures の TOML ファイルは Git 管理対象
- `gh release create` などで release を切るときは、先に `pyproject.toml` の `[project].version` を更新し、Git tag / release 名と同じバージョンに揃えること

## ビルド・実行

```bash
# 開発環境セットアップ
uv sync --dev

# テスト
uv run pytest

# Lint
uv run ruff check src/ tests/
uv run ruff format --check src/ tests/

# 型チェック
uv run mypy src/

# CLI 実行 (開発中)
uv run simctl --help
```

## 状態遷移

```
created → submitted → running → completed
created/submitted/running → failed
submitted/running → cancelled
completed → archived → purged
```

## Adapter 実装時の注意

新しい Simulator Adapter を追加する場合:
1. `src/simctl/adapters/base.py` の `SimulatorAdapter` を継承
2. 全抽象メソッドを実装: render_inputs, resolve_runtime, build_program_command, detect_outputs, detect_status, summarize, collect_provenance
3. オプションメソッドの実装: parameter_schema, validate_params, knowledge_sources, agent_guide, case_template, doc_repos, pip_packages
4. `adapters/registry.py` に登録
5. `simulators.toml` に設定エントリを追加
6. テストを `tests/test_adapters/` に追加

## 知識層 (Knowledge Layer)

AI エージェントがシミュレーションを自律的に行うための知識管理。
詳細は `docs/knowledge-layer.md` を参照。

- **シミュレータ知識**: `refs/` + `.simctl/knowledge/` (update-refs で更新)
- **外部共有知識**: `simproject.toml` の `[knowledge]` に基づき外部ソースを接続し、必要に応じて `refs/knowledge/` 配下へ同期 (`knowledge source attach/sync` で管理)
- **実行環境**: `.simctl/environment.toml` (doctor で自動検出)
- **研究意図**: `campaign.toml` (ユーザーが記述)
- **実験知見 (curated)**: `.simctl/insights/` (knowledge save / knowledge source sync で管理)
- **構造化知識 (curated)**: `.simctl/facts.toml` (knowledge add-fact / knowledge facts で管理)
- **lab notebook (chronological)**: `notes/YYYY-MM-DD.md` (`simctl notes append` で時系列追記)
- **長文レポート**: `notes/reports/<topic>.md` (改稿可)

curated knowledge と lab notebook は **二層構造**:

- `.simctl/insights/` / `.simctl/facts.toml` は整理済の永続知見 (上書き可・名前付き・atomic)
- `notes/YYYY-MM-DD.md` は append-only な時系列ログ。準備フェーズの意思決定・観察・仮説・TODO をその場で残す
- 価値が出てきたら `notes/reports/` で refined version を書き、さらに `.simctl/insights/` / `facts.toml` に昇格

### 外部知識ソース

複数プロジェクト間で共有する知識を外部リポジトリとして管理し、project に接続できる。
`simproject.toml` の `[knowledge]` セクションで設定する。

```bash
# 外部知識ソースの接続
simctl knowledge source attach git shared-kb git@github.com:lab/hpc-shared-knowledge.git
simctl knowledge source attach path local-kb ../hpc-knowledge

# 同期・レンダリング
simctl knowledge source sync
simctl knowledge source render

# 状態確認
simctl knowledge source status
simctl knowledge source list
```

`simctl init` 時に GitHub の `*shared_knowledge*` リポジトリを自動検索し、対話的に接続できる。
`simctl setup` 時は `simproject.toml` に設定された知識ソースを自動同期する。

主要コマンド:
- `simctl update-refs` — refs/ リポジトリ更新 + ナレッジインデックス再生成
- `simctl knowledge source attach/detach/sync/render/status` — 外部知識ソース管理
- `simctl knowledge save/list/show` — Markdown 知見の管理
- `simctl knowledge add-fact/facts` — 構造化知識の管理
- `simctl doctor` — 環境検出・保存
