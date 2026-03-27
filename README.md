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

## インストール

### uv を使う場合（推奨）

```bash
# リポジトリをクローン
git clone https://github.com/your-org/hpc-simctl.git
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
  .gitignore           # 大容量出力の除外設定
  cases/               # Case 定義の格納場所
  runs/                # run の格納場所
```

### 2. シミュレータと Launcher の設定

`simulators.toml` にシミュレータを定義:

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

### 3. Case の定義

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

### 4. 単一 run の作成

```bash
simctl create my_case --dest runs/cavity/test
```

### 5. パラメータサーベイの実行

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

### 6. Job の投入

```bash
# 単一 run を投入
simctl submit R20260327-0001

# survey 内の全 run を一括投入
simctl submit --all runs/cavity/scan
```

### 7. 状態の確認

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

| コマンド | 説明 |
|---------|------|
| `simctl init [PATH]` | プロジェクトの初期化 (simproject.toml 等を生成) |
| `simctl doctor [PATH]` | 環境検査 (設定ファイル、sbatch 可用性、run_id 一意性) |
| `simctl create CASE --dest DIR` | Case から単一 run を生成 |
| `simctl sweep DIR` | survey.toml からパラメータ直積で全 run を一括生成 |
| `simctl submit RUN` | sbatch で run を job 投入 |
| `simctl submit --all DIR` | ディレクトリ内の全 created run を一括投入 |
| `simctl status RUN` | run の状態確認 |
| `simctl sync RUN` | Slurm 状態を manifest.toml に反映 |
| `simctl list [PATH]` | run の一覧表示 (状態・タグでフィルタ可能) |
| `simctl clone RUN --dest DIR` | run の複製・派生 |
| `simctl summarize RUN` | Adapter による run 解析 summary 生成 |
| `simctl collect DIR` | survey 内の全 run から集計データ生成 |
| `simctl archive RUN` | run のアーカイブ |
| `simctl purge-work RUN` | work/ 内の不要ファイル削除 |

## プロジェクト構成

```
hpc-simctl/
  pyproject.toml
  SPEC.md                  # 詳細仕様書
  CLAUDE.md                # 開発ガイド
  src/
    simctl/
      cli/                 # CLI エントリポイント (typer)
        main.py            # コマンド登録
        init.py            # init / doctor
        create.py          # create / sweep
        submit.py          # submit
        status.py          # status / sync
        list.py            # list
        clone.py           # clone
        analyze.py         # summarize / collect
        manage.py          # archive / purge-work
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
- [SPEC.md](SPEC.md) -- 完全な仕様書

## ライセンス

MIT
