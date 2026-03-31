# はじめに (Getting Started)

このドキュメントでは、hpc-simctl を使ったシミュレーション管理の基本的なワークフローをステップごとに説明します。

## 前提条件

- Python 3.10 以上
- Slurm 環境 (`sbatch`, `squeue`, `sacct` が利用可能)
- uv ([astral.sh/uv](https://astral.sh/uv))

## インストール

simctl はプロジェクトごとにブートストラップインストールされます。
事前のグローバルインストールは不要です。

```bash
# プロジェクトディレクトリを作成して初期化 (uv だけあれば OK)
mkdir my-hpc-project
cd my-hpc-project
uvx --from git+https://github.com/Nkzono99/hpc-simctl.git simctl init

# activate して利用開始
source .venv/bin/activate
```

`simctl init` が以下を自動的に行います:

1. 設定ファイル群を生成 (`simproject.toml`, `simulators.toml`, `launchers.toml`, `campaign.toml`)
2. `.simctl/` 骨格を作成 (`insights/`, `facts.toml`, `links.toml`)
3. `.venv/` を作成 (uv venv)
4. `tools/hpc-simctl/` に simctl リポジトリを clone
5. simctl を `.venv` に editable install (`uv pip install -e`)
6. シミュレータ固有パッケージをインストール
7. `git init` + Initial commit で clean な状態にする

### 既存プロジェクトの clone + セットアップ

GitHub 等にある既存の simctl プロジェクトをセットアップする場合は `simctl setup` を使います:

```bash
uvx --from git+https://github.com/Nkzono99/hpc-simctl.git simctl setup https://github.com/user/my-project.git
cd my-project
source .venv/bin/activate
simctl doctor
```

`simctl setup` は既存の TOML ファイルを上書きせず、環境 (`.venv`, `tools/`, `refs/`, `.simctl/`) のみセットアップします。

インストール確認:

```bash
simctl --help
```

出力例:

```
Usage: simctl [OPTIONS] COMMAND [ARGS]...

  HPC simulation run management CLI tool.

Commands:
  init        Initialize a new simctl project.
  doctor      Check the environment and project configuration.
  create      Create a single run from a case definition.
  sweep       Generate all runs from a survey.toml parameter sweep.
  submit      Submit a run or all runs in a survey via sbatch.
  status      Check run status.
  sync        Synchronize Slurm state to manifest.
  list        List runs.
  clone       Clone a run.
  summarize   Generate run analysis summary.
  collect     Collect survey-level summary.
  archive     Archive a run.
  purge-work  Purge work directory files.
```

---

## ステップ 1: プロジェクトの初期化

まず、シミュレーション管理用のプロジェクトディレクトリを作成します。

```bash
cd my-hpc-project
source .venv/bin/activate
simctl doctor
```

出力例:

```
Initialized project 'my-hpc-project' in /home/user/my-hpc-project
  Created:
    simproject.toml
    simulators.toml
    launchers.toml
    campaign.toml
    .simctl/
    .simctl/insights/
    .simctl/facts.toml
    .simctl/links.toml
    cases/
    runs/
    .gitignore
    CLAUDE.md
    AGENTS.md
    git init
    .venv
    tools/hpc-simctl
    uv pip install -e tools/hpc-simctl
    git commit (Initial commit)
```

### 生成されるファイル

#### simproject.toml

プロジェクトの基本情報を定義します。

```toml
[project]
name = "my-hpc-project"
description = ""
```

#### simulators.toml

シミュレータの定義を記述します。初期状態は空です。

```toml
[simulators]
```

#### launchers.toml

MPI の起動方式を定義します。初期状態は空です。

```toml
[launchers]
```

#### .gitignore

大容量の実行出力を Git 管理対象外にします。

```gitignore
# Python venv
.venv/

# simctl tool (cloned by simctl init)
tools/

# Reference repos
refs/

# Auto-generated (insights/, facts.toml, links.toml are tracked)
.simctl/knowledge/
.simctl/environment.toml
.simctl/shared/

# heavy run outputs
runs/**/work/outputs/
runs/**/work/restart/
runs/**/work/tmp/

# logs
runs/**/work/*.out
runs/**/work/*.err
runs/**/work/*.log

# analysis cache
runs/**/analysis/cache/
runs/**/analysis/.ipynb_checkpoints/
```

### 環境チェック

`simctl doctor` で環境が正しく設定されているか確認できます。

```bash
simctl doctor
```

出力例:

```
[PASS] simproject.toml is valid
[PASS] simulators.toml found
[PASS] launchers.toml found
[PASS] sbatch is available
[PASS] No runs/ directory (nothing to check)

All checks passed.
```

---

## ステップ 1.5: campaign.toml のセットアップ (AI エージェント活用)

`simctl init` が生成する `campaign.toml` はスケルトン状態です。
研究テーマ・仮説・変数・観測量を記入することで、AI エージェントがサーベイ設計や結果解析の文脈を理解できるようになります。

### AI エージェントに記入させる (推奨)

Claude Code などの AI エージェント環境では、テーマを自然言語で伝えるだけで campaign.toml を構造化できます。

```bash
# Claude Code の場合
claude "campaign.tomlを整えて。テーマは月面平面に太陽風プラズマが吹きつけ、
光電効果もある場合の表面電位変動を調べること。照射角を独立変数にする。"
```

エージェントは `.claude/skills/setup-campaign/SKILL.md` を参照し、以下を自動的に行います:

1. `[campaign]` の description と hypothesis を記入
2. `[variables]` にパラメータの role (independent / dependent / fixed) を設定
3. `[observables]` に測定する物理量を定義

### 手動で記入する場合

```toml
[campaign]
name = "flat_surface"
description = "月面平面における太陽風プラズマ-表面相互作用の研究"
hypothesis = "太陽天頂角が大きくなると光電子放出量が減少し、表面電位が負方向に変化する"
simulator = "emses"

[variables]
ray_zenith_angle_deg = { role = "independent", values = [0, 20, 40, 60, 80], unit = "deg", reason = "太陽照射角の影響を系統的に調べる" }
surface_potential = { role = "dependent", unit = "V", reason = "表面電位が主要な観測量" }

[observables]
surface_potential = { source = "work/phisp*.h5", description = "表面電位分布", unit = "V" }
```

---

## ステップ 2: シミュレータと Launcher の設定

### simulators.toml

使用するシミュレータを定義します。以下は 3 つの resolver mode の例です。

```toml
[simulators.my_solver]
# generic adapter を使用（汎用的なシミュレータに対応）
adapter = "generic"

# resolver_mode: シミュレータ実行ファイルの解決方法
#   "package"          - PATH 上のインストール済みコマンドを使用
#   "local_source"     - ローカルソースからビルドして使用
#   "local_executable" - ビルド済み実行ファイルを直接指定

# 例: ローカルビルド済み実行ファイル
resolver_mode = "local_executable"
executable = "/home/user/work/my-solver/build/solver"

# 例: ローカルソースからビルド
# resolver_mode = "local_source"
# source_repo = "/home/user/work/my-solver"
# executable = "/home/user/work/my-solver/build/solver"
# build_command = "make -j"

# 例: インストール済みパッケージ
# resolver_mode = "package"
# executable = "my-solver"
```

### launchers.toml

MPI 起動方式を定義します。

```toml
# srun (Slurm ネイティブ)
[launchers.slurm_srun]
kind = "srun"
command = "srun"
use_slurm_ntasks = true

# mpirun (OpenMPI)
[launchers.openmpi]
kind = "mpirun"
command = "mpirun"
np_flag = "-np"
use_slurm_ntasks = true

# mpiexec
[launchers.mpiexec]
kind = "mpiexec"
command = "mpiexec"
n_flag = "-n"
use_slurm_ntasks = true
```

`use_slurm_ntasks = true` の場合、タスク数は Slurm の `#SBATCH --ntasks` から自動的に取得されます（`SLURM_NTASKS` 環境変数）。

---

## ステップ 3: Case の定義

Case は run を生成するための再利用可能な雛形です。`cases/` ディレクトリ以下に配置します。

### simctl new でテンプレート生成

`simctl new` コマンドでケーステンプレートを自動生成できます。

```bash
# cases/<simulator>/ ディレクトリ内で実行
cd cases/emses
simctl new solar_wind_flat

# survey.toml のスタブも同時に生成する場合
simctl new solar_wind_flat --survey
```

`--survey` オプションを付けると、`runs/<case_name>/survey.toml` にスタブファイルも同時に生成されます。

### ディレクトリ構成

```
cases/
  emses/
    solar_wind_flat/
      case.toml          # メタデータ・パラメータ定義
      plasma.toml        # シミュレータ入力ファイル (Adapter が生成)
      input/             # テンプレート入力ファイル (run の input/ にコピーされる)
```

### case.toml の例

```toml
[case]
name = "cavity_base"
simulator = "my_solver"
launcher = "slurm_srun"
description = "Cavity モデルの基本ケース"

[classification]
model = "cavity"
submodel = "rectangular"
tags = ["baseline"]

[job]
partition = "gr20001a"
nodes = 1
ntasks = 32
walltime = "12:00:00"

[params]
nx = 256
ny = 256
nz = 512
dt = 1.0e-8
u = 4.0e5
aspect = 4.0
seed = 1
```

各セクションの意味:

| セクション | 説明 |
|-----------|------|
| `[case]` | Case の基本情報 (名前・使用シミュレータ・Launcher) |
| `[classification]` | 分類メタデータ (モデル種別・タグ) |
| `[job]` | Slurm ジョブ設定 (パーティション・ノード数・タスク数・制限時間) |
| `[params]` | シミュレーション固有のパラメータ (意味は Adapter が解釈) |

---

## ステップ 4: 単一 run の作成

Case から単一の run を作成します。

```bash
simctl create cavity_base --dest runs/cavity/test
```

出力例:

```
Created run: R20260327-0001
  Path: /home/user/my-hpc-project/runs/cavity/test/R20260327-0001
```

### 生成される run ディレクトリの構造

```
R20260327-0001/
  manifest.toml      # run の台帳（正本情報）
  input/             # 入力ファイル
    params.json      # パラメータスナップショット
  submit/            # job script
    job.sh           # Slurm 投入スクリプト
  work/              # 実行作業空間
  analysis/          # 解析成果
  status/            # 状態追跡情報
```

### manifest.toml の内容

manifest.toml は run の全メタデータを保持する正本ファイルです。

```toml
[run]
id = "R20260327-0001"
display_name = "cavity_base"
status = "created"
created_at = "2026-03-27T04:00:00+00:00"

[path]
run_dir = "/home/user/my-hpc-project/runs/cavity/test/R20260327-0001"

[origin]
case = "cavity_base"
survey = ""
parent_run = ""

[classification]
model = "cavity"
submodel = "rectangular"
tags = ["baseline"]

[simulator]
name = "my_solver"
adapter = "generic"
resolver_mode = "local_executable"

[launcher]
name = "slurm_srun"

[simulator_source]
executable = "/home/user/work/my-solver/build/solver"
exe_hash = "sha256:abc123..."
resolver_mode = "local_executable"
# ...

[job]
scheduler = "slurm"
job_id = ""
partition = "gr20001a"
nodes = 1
ntasks = 32
walltime = "12:00:00"
submitted_at = ""

[params_snapshot]
nx = 256
ny = 256
nz = 512
dt = 1e-08
u = 400000.0
aspect = 4.0
seed = 1

[files]
input_dir = "input"
submit_dir = "submit"
work_dir = "work"
analysis_dir = "analysis"
status_dir = "status"
```

---

## ステップ 5: パラメータサーベイ

複数のパラメータ組み合わせで一括して run を生成するには、survey.toml を使います。

### survey.toml の作成

`simctl new --survey` でケースと同時にスタブを生成するか、手動で作成します。

```bash
# 方法 1: simctl new --survey で自動生成済みの場合
# → runs/<case_name>/survey.toml が既に存在する

# 方法 2: 手動作成
mkdir -p runs/cavity/rectangular/u_aspect_scan
```

`runs/cavity/rectangular/u_aspect_scan/survey.toml`:

```toml
[survey]
id = "S20260327-cavity-u-a"
name = "u-aspect scan"
base_case = "cavity_base"
simulator = "my_solver"
launcher = "slurm_srun"

[classification]
model = "cavity"
submodel = "rectangular"
tags = ["scan", "paper1"]

[axes]
u = [2.0e5, 4.0e5, 8.0e5]
aspect = [2.0, 4.0, 8.0]
seed = [1, 2, 3]

[naming]
display_name = "u{u}_a{aspect}_s{seed}"

[job]
partition = "gr20001a"
nodes = 1
ntasks = 32
walltime = "12:00:00"
```

`[axes]` セクションの各パラメータリストの直積が展開されます。上の例では 3 x 3 x 3 = 27 個の run が生成されます。

### sweep の実行

```bash
simctl sweep runs/cavity/rectangular/u_aspect_scan
```

出力例:

```
Created 27 runs in /home/user/my-hpc-project/runs/cavity/rectangular/u_aspect_scan
  R20260327-0001 (u200000_a2_s1)
  R20260327-0002 (u200000_a2_s2)
  R20260327-0003 (u200000_a2_s3)
  R20260327-0004 (u200000_a4_s1)
  ...
  R20260327-0027 (u800000_a8_s3)
```

各 run の `display_name` は `[naming]` テンプレートに基づいて自動生成されます。

---

## ステップ 6: Job の投入

### 単一 run の投入

```bash
simctl submit R20260327-0001
```

出力例:

```
Submitted R20260327-0001: job_id=12345678
```

パスで指定することもできます:

```bash
simctl submit runs/cavity/rectangular/u_aspect_scan/R20260327-0001
```

### survey 内の全 run を一括投入

```bash
simctl submit --all runs/cavity/rectangular/u_aspect_scan
```

出力例:

```
  Submitted R20260327-0001: job_id=12345678
  Submitted R20260327-0002: job_id=12345679
  ...

Summary: 27 submitted, 0 skipped, 0 failed (total: 27 runs)
```

### Dry-run モード

実際に投入せず、何が起きるか確認:

```bash
simctl submit --all runs/cavity/rectangular/u_aspect_scan --dry-run
```

---

## ステップ 7: 状態の確認と同期

### 状態確認

```bash
simctl status R20260327-0001
```

### Slurm 状態の同期

Slurm (squeue/sacct) から最新の状態を取得し、manifest.toml に反映:

```bash
simctl sync R20260327-0001
```

### run の一覧表示

```bash
# 全 run の一覧
simctl list

# 特定ディレクトリ以下の run
simctl list runs/cavity/rectangular/u_aspect_scan

# 状態でフィルタ
simctl list --status failed

# タグでフィルタ
simctl list --tag production
```

---

## ステップ 8: 解析

### 単一 run の summary 生成

```bash
simctl summarize R20260327-0001
```

Adapter が出力ファイルを解析し、`analysis/summary.json` を生成します。

### survey 集計

```bash
simctl collect runs/cavity/rectangular/u_aspect_scan
```

survey 内の全 run の summary を収集し、集計データを生成します。

---

## ステップ 9: 整理

### run のアーカイブ

```bash
simctl archive --yes R20260327-0001
```

### work/ の不要ファイル削除

```bash
simctl purge-work --yes R20260327-0001
```

---

## run の状態遷移

run は以下の状態を持ちます:

| 状態 | 意味 |
|-----|------|
| `created` | run ディレクトリ・manifest・入力・job script が生成済み |
| `submitted` | sbatch 済みで job_id を取得済み |
| `running` | 実行中 |
| `completed` | 正常終了 |
| `failed` | 異常終了または失敗判定 |
| `cancelled` | 途中停止 |
| `archived` | 出力整理済み |
| `purged` | 不要 work を削除済み |

遷移ルール:

```
created -> submitted -> running -> completed -> archived -> purged
created/submitted/running -> failed
submitted/running -> cancelled
```

---

## run_id について

run_id は `RYYYYMMDD-NNNN` の形式です（例: `R20260327-0001`）。

- プロジェクト内で一意
- パスの変更に影響されない（run を別ディレクトリに移動しても run_id は不変）
- 日付部分は run 生成日、連番部分はその日の中での通し番号

run_id またはパスのどちらでも run を指定できます:

```bash
# run_id で指定
simctl status R20260327-0001

# パスで指定
simctl status runs/cavity/rectangular/u_aspect_scan/R20260327-0001
```

---

## 運用モード

### development モード

- `local_source` / `local_executable` の使用可
- dirty な git working tree を許容
- provenance は常に記録
- タグに `dev` を推奨

### production モード

- clean な git working tree を推奨
- git commit を固定
- executable hash の記録必須
- タグに `production` を推奨

---

## 次のステップ

- [アーキテクチャ](architecture.md) -- システム全体の設計を理解する
- [拡張ガイド](extending.md) -- 新しい Adapter や Launcher を追加する
- [SPEC.md](../SPEC.md) -- 完全な仕様書
