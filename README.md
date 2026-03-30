# hpc-simctl

HPC 環境における Slurm ベースのシミュレーション実行管理 CLI ツール。

run ディレクトリを日常運用の主単位とし、パラメータサーベイ展開・job 投入・状態追跡・provenance 記録・解析補助を一貫して管理します。

## 特徴

- **run 中心の管理**: すべての操作は run ディレクトリ (`runs/.../Rxxxx/`) を基点に行う
- **パラメータサーベイ**: survey.toml による parameter sweep の自動展開（直積生成）
- **Slurm 連携**: sbatch による job 投入、squeue/sacct による状態同期
- **Simulator Adapter**: シミュレータ固有処理を Adapter パターンで抽象化。core はシミュレータに依存しない
- **Launcher Profile**: srun / mpirun / mpiexec の起動方式を Profile で切替可能
- **Provenance 記録**: git commit、executable hash、パラメータ snapshot を manifest.toml に自動記録
- **多重ネスト対応**: `runs/` 以下を自由に階層化して分類・整理できる
- **Agent/AI 対応**: TOML/JSON ベースの構造化データで AI エージェントとの連携が容易
- **知識層**: シミュレータ知識・実行環境・研究意図の 3 層で AI エージェントにコンテキストを提供
- **パラメータバリデーション**: 物理的制約 (CFL 条件, Debye 長等) を run 生成前にチェック
- **Research Campaign**: campaign.toml で研究仮説・変数・観測量を構造化し、実験設計を明示

## インストール

### uv を使う場合（推奨）

```bash
# リポジトリをクローン
git clone https://github.com/Nkzono99/hpc-simctl.git
cd hpc-simctl

# 開発環境セットアップ
uv sync --dev
```

### pip を使う場合

```bash
pip install -e .
```

## クイックスタート

### 1. プロジェクトの初期化

```bash
mkdir my-simulation-project
cd my-simulation-project
simctl init
```

以下のファイル・ディレクトリが生成されます:

```
my-simulation-project/
  simproject.toml      # プロジェクト設定
  simulators.toml      # シミュレータ定義
  launchers.toml       # Launcher Profile 定義
  campaign.toml        # 研究意図 (仮説・変数・観測量)
  .gitignore           # 大容量出力の除外設定
  CLAUDE.md            # Claude 向け AI エージェント指示
  AGENTS.md            # Codex / 汎用 Agent 向け AI エージェント指示
  cases/               # Case 定義の格納場所
  runs/                # run の格納場所
  refs/                # シミュレータリファレンスリポジトリ
  .simctl/             # 知識層 (ナレッジ・環境・知見)
    knowledge/         # シミュレータ知識インデックス (自動生成)
    insights/          # 実験知見 (人間向け Markdown)
    facts.toml         # 構造化された知識 (AI 向け machine-readable claims)
    environment.toml   # 実行環境記述 (自動検出)
    links.toml         # 他プロジェクトへの参照
```

### 2. 研究意図の定義 (campaign.toml)

プロジェクトルートに `campaign.toml` を作成し、何を調べたいかを記述:

```toml
[campaign]
name = "parameter-sensitivity"
description = "格子サイズと時間刻みの感度解析"
hypothesis = "nx=512 以上で解が収束する"
simulator = "my_solver"

[variables]
"nx" = { role = "independent", range = [128, 1024], unit = "cells" }
"dt" = { role = "independent", range = [1.0e-9, 1.0e-7], unit = "s" }

[observables]
max_field = { source = "work/output.h5", description = "最大電場強度" }
```

AI エージェントはこのファイルを読んで survey 設計や結果解釈に活用します。

### 3. シミュレータと Launcher の設定

`simulators.toml` にシミュレータを定義 (シミュレータ指定で init した場合は自動生成):

```toml
[simulators.my_solver]
adapter = "generic"
resolver_mode = "local_executable"
executable = "/path/to/solver"
```

`launchers.toml` に Launcher Profile を定義:

```toml
[launchers.slurm_srun]
kind = "srun"
command = "srun"
use_slurm_ntasks = true
```

### 4. Case の定義

`cases/my_case/case.toml` を作成:

```toml
[case]
name = "my_case"
simulator = "my_solver"
launcher = "slurm_srun"
description = "基本ケース"

[classification]
model = "cavity"
submodel = "rectangular"
tags = ["baseline"]

[job]
partition = "compute"
nodes = 1
ntasks = 32
walltime = "12:00:00"

[params]
nx = 256
ny = 256
dt = 1.0e-8
```

### 5. 単一 run の作成

```bash
simctl create my_case --dest runs/cavity/test
```

### 6. パラメータサーベイの実行

`runs/cavity/scan/survey.toml` を作成:

```toml
[survey]
id = "S20260327-scan"
name = "parameter scan"
base_case = "my_case"
simulator = "my_solver"
launcher = "slurm_srun"

[axes]
nx = [128, 256, 512]
dt = [1.0e-8, 1.0e-9]

[naming]
display_name = "nx{nx}_dt{dt}"

[job]
partition = "compute"
nodes = 1
ntasks = 32
walltime = "12:00:00"
```

```bash
simctl sweep runs/cavity/scan
```

### 7. Job の投入

```bash
# cwd の run を投入
cd runs/cavity/test/R20260327-0001
simctl run

# survey 内の全 run を一括投入
cd runs/cavity/scan
simctl run --all
```

### 8. 状態の確認

```bash
# 単一 run の状態確認
simctl status R20260327-0001

# Slurm 状態を manifest に同期
simctl sync R20260327-0001

# run の一覧表示
simctl list
simctl list runs/cavity/scan
```

## コマンドリファレンス

### プロジェクト管理

| コマンド | 説明 |
|---------|------|
| `simctl init [SIMS...] [-y]` | プロジェクトの初期化 (対話型がデフォルト) |
| `simctl doctor [PATH]` | 環境検査 (設定・sbatch・run_id 一意性・環境検出) |
| `simctl config show` | 設定表示 |
| `simctl config add-simulator` | シミュレータ追加 (対話型) |
| `simctl config add-launcher` | ランチャー追加 (対話型) |

### Run 作成・投入

| コマンド | 説明 |
|---------|------|
| `simctl new CASE` | 新規ケースのスキャフォールド生成 |
| `simctl create CASE` | cwd にケースから run 生成 |
| `simctl sweep [DIR]` | survey.toml からパラメータ直積で全 run 一括生成 |
| `simctl run [-qn QUEUE]` | cwd の run を sbatch で投入 |
| `simctl run --all [-qn QUEUE]` | cwd 内の全 created run を一括投入 |
| `simctl clone` | run 複製・派生 |
| `simctl extend` | スナップショットから継続 run 生成 |

### 状態管理・モニタリング

| コマンド | 説明 |
|---------|------|
| `simctl status` | run の状態確認 |
| `simctl sync` | Slurm 状態を manifest.toml に反映 |
| `simctl log` | 最新 job の stdout 表示 + 進捗% |
| `simctl jobs` | プロジェクト内の実行中ジョブ一覧 |
| `simctl history` | 投入履歴表示 |
| `simctl list [PATH]` | run の一覧表示 (状態・タグでフィルタ可能) |

### 解析・整理

| コマンド | 説明 |
|---------|------|
| `simctl summarize` | Adapter による run 解析 summary 生成 |
| `simctl collect [DIR]` | survey 内の全 run から集計データ生成 |
| `simctl archive` | run のアーカイブ |
| `simctl purge-work` | work/ 内の不要ファイル削除 |

### 知識管理

| コマンド | 説明 |
|---------|------|
| `simctl update` | シミュレータパッケージのアップグレード |
| `simctl update-refs [SIMS...]` | refs/ リポジトリ更新 + ナレッジインデックス再生成 |
| `simctl knowledge save NAME` | 知見を .simctl/insights/ に保存 |
| `simctl knowledge list` | 知見一覧表示 |
| `simctl knowledge show NAME` | 知見の詳細表示 |
| `simctl knowledge sync` | リンク先プロジェクトから知見をインポート |
| `simctl knowledge links` | プロジェクトリンク一覧 |
| `simctl knowledge add-fact CLAIM` | 構造化された知識を facts.toml に追加 |
| `simctl knowledge facts` | 構造化知識の一覧表示 |

知識管理は二層構造:
- **insights** (Markdown) — 人間が読む実験知見・考察
- **facts** (TOML) — AI が使う構造化された claims (scope, evidence, confidence 付き)

全コマンドは引数省略時にカレントディレクトリをデフォルトとする。

## プロジェクト構成

```
hpc-simctl/
  pyproject.toml
  SPEC.md                  # 詳細仕様書
  CLAUDE.md                # 開発ガイド
  AGENTS.md                # Agent 運用ガイド
  src/
    simctl/
      cli/                 # CLI エントリポイント (typer)
        main.py            # コマンド登録
        init.py            # init / doctor
        new.py             # new (ケーススキャフォールド)
        create.py          # create / sweep
        submit.py          # run (sbatch 投入)
        status.py          # status / sync
        log.py             # log (stdout 表示)
        jobs.py            # jobs (実行中ジョブ一覧)
        history.py         # history (投入履歴)
        list.py            # list
        clone.py           # clone
        extend.py          # extend (継続 run)
        analyze.py         # summarize / collect
        manage.py          # archive / purge-work
        update.py          # update (パッケージ更新)
        update_refs.py     # update-refs (refs/ 更新 + ナレッジ)
        knowledge.py       # knowledge (知見管理)
        config.py          # config (設定管理)
      core/                # ドメインロジック
        project.py         # Project 読込・検証
        case.py            # Case 読込・展開
        survey.py          # Survey 展開・parameter 直積
        run.py             # Run 生成・run_id 採番
        manifest.py        # manifest.toml 読書き
        state.py           # 状態遷移管理
        provenance.py      # コード provenance 取得
        discovery.py       # runs/ 再帰探索・run_id 一意性検証
        exceptions.py      # ドメイン例外
        validation.py      # パラメータバリデーション
        campaign.py        # campaign.toml 読込
        environment.py     # 実行環境検出・記述
        knowledge.py       # 知識層 (insights, links)
      adapters/            # Simulator Adapter
        base.py            # SimulatorAdapter 抽象基底クラス
        registry.py        # Adapter 登録・lookup
        generic.py         # 汎用 Adapter 実装
      launchers/           # Launcher Profile
        base.py            # Launcher 抽象基底クラス
        srun.py            # srun Launcher
        mpirun.py          # mpirun Launcher
        mpiexec.py         # mpiexec Launcher
      jobgen/              # job.sh 生成
        generator.py       # Slurm batch script 生成
      slurm/               # Slurm 連携
        submit.py          # sbatch 投入
        query.py           # squeue / sacct 問合せ
  tests/
  docs/
```

## 状態遷移

run は以下の状態遷移に従います:

```
created --> submitted --> running --> completed
                |           |
                v           v
             failed      failed
                |
                v
            cancelled

completed --> archived --> purged
```

> **Note**: `simctl sync` は Slurm の観測結果を manifest に反映するため、
> ポーリング間隔によっては `submitted → completed` のように途中状態を飛び越す遷移が発生します。
> 詳細は [SPEC.md](SPEC.md) を参照してください。

## 技術スタック

- Python 3.10+
- CLI: [typer](https://typer.tiangolo.com/) (click ベース)
- 設定ファイル: TOML (tomli / tomli-w)
- パッケージ管理: [uv](https://docs.astral.sh/uv/)
- テスト: pytest
- Lint/Format: ruff
- 型チェック: mypy (strict)

## 開発

```bash
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

## ドキュメント

- [はじめに (Getting Started)](docs/getting-started.md) -- チュートリアル形式のウォークスルー
- [アーキテクチャ](docs/architecture.md) -- システム設計とモジュール構成
- [拡張ガイド](docs/extending.md) -- Adapter / Launcher の追加方法
- [知識層](docs/knowledge-layer.md) -- AI エージェント向け知識管理アーキテクチャ
- [TOML リファレンス](docs/toml-reference.md) -- 全設定ファイルのフィールド定義
- [SPEC.md](SPEC.md) -- 完全な仕様書

## ライセンス

MIT
