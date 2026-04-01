# TOML Configuration Reference

simctl uses TOML files for all configuration. Each file has a JSON Schema for validation (`#:schema` comment at the top).

---

## simproject.toml

Project-level configuration. One per project root.

```toml
[project]
name = "emses-sheath"           # Required. Project name
description = "EMSES sheath simulations"  # Optional.
version = "1.0"                 # Optional.
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `project.name` | string | Yes | Project identifier |
| `project.description` | string | No | Human-readable description |
| `project.version` | string | No | Project version |

### `[knowledge]` section (optional)

External shared knowledge source integration. If absent, only local knowledge (insights, facts, links) is used.

```toml
[knowledge]
enabled = true                       # Enable knowledge integration
mount_dir = "refs/knowledge"         # Base mount directory
derived_dir = ".simctl/knowledge"    # Generated files directory
auto_sync_on_setup = true            # Sync sources during `simctl setup`
generate_claude_imports = true       # Generate CLAUDE.md @import stubs

[[knowledge.sources]]
name = "shared-lab-knowledge"        # Source identifier
type = "git"                         # "git" or "path"
url = "git@github.com:lab/kb.git"   # Git URL (for type = "git")
ref = "main"                         # Git ref to checkout
mount = "refs/knowledge/shared-lab-knowledge"  # Mount path
profiles = ["common-analysis", "emses-basic"]  # Enabled profiles

[[knowledge.sources]]
name = "personal-knowledge"
type = "path"
path = "../hpc-knowledge"            # Filesystem path (for type = "path")
mount = "refs/knowledge/personal-knowledge"
```

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `knowledge.enabled` | bool | No | `true` | Enable knowledge integration |
| `knowledge.mount_dir` | string | No | `"refs/knowledge"` | Base directory for source mounts |
| `knowledge.derived_dir` | string | No | `".simctl/knowledge"` | Directory for generated files |
| `knowledge.auto_sync_on_setup` | bool | No | `true` | Auto-sync on `simctl setup` |
| `knowledge.generate_claude_imports` | bool | No | `true` | Generate `imports.md` for CLAUDE.md |
| `knowledge.sources[].name` | string | Yes | — | Source identifier |
| `knowledge.sources[].type` | string | Yes | — | `"git"` or `"path"` |
| `knowledge.sources[].url` | string | Conditional | — | Git URL (required when type = "git") |
| `knowledge.sources[].path` | string | Conditional | — | Filesystem path (required when type = "path") |
| `knowledge.sources[].ref` | string | No | `"main"` | Git ref to checkout |
| `knowledge.sources[].mount` | string | No | `"<mount_dir>/<name>"` | Relative mount path |
| `knowledge.sources[].profiles` | string[] | No | `[]` | Enabled profile names |

---

## simulators.toml

Simulator adapter definitions. Declares which simulators are available in the project.

```toml
[simulators.emses]
adapter = "emses"
resolver_mode = "package"
executable = "mpiemses3D"
modules = ["intel/2023.2", "intelmpi/2023.2"]

[simulators.beach]
adapter = "beach"
resolver_mode = "package"
executable = "beach"
```

### `[simulators.<name>]`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `adapter` | string | Yes | Adapter name (`emses`, `beach`, `generic`) |
| `resolver_mode` | string | No | How to find the executable: `package` (pip installed), `local_executable` (PATH), `local_source` (build from source) |
| `executable` | string | No | Executable name or path |
| `source_repo` | string | No | Source repository path (`local_source` mode only) |
| `build_command` | string | No | Build command (`local_source` mode only) |
| `modules` | string[] | No | Simulator-specific HPC modules (e.g. hdf5, fftw). Site-common modules (intel, intelmpi) are defined in `launchers.toml`. Both are merged in job.sh. |

### resolver_mode

- **`package`** (recommended): Executable is pip-installed into `.venv`. `simctl init` installs it automatically.
- **`local_executable`**: Executable is on PATH or specified as an absolute path.
- **`local_source`**: Build from source. `source_repo` and `build_command` must be set.

---

## launchers.toml

MPI launcher profiles. Defines how simulators are launched (srun, mpirun, mpiexec) and site-specific job configuration.

### Basic srun (standard Slurm)

```toml
[launchers.srun]
type = "srun"
use_slurm_ntasks = true
```

### camphor site profile

```toml
[launchers.camphor]
type = "srun"
use_slurm_ntasks = true
resource_style = "rsc"
modules = [
    "intel/2023.2",
    "intelmpi/2023.2",
    "hdf5/1.12.2_intel-2023.2-impi",
    "fftw/3.3.10_intel-2022.3-impi",
]
stdout = "stdout.%J.log"
stderr = "stderr.%J.log"
```

### mpirun

```toml
[launchers.openmpi]
type = "mpirun"
command = "mpirun"
args = "--bind-to core"
modules = ["openmpi/4.1"]
```

### `[launchers.<name>]`

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `type` | string | Yes | — | Launcher type: `srun`, `mpirun`, `mpiexec` |
| `command` | string | No | same as `type` | Launcher executable command |
| `use_slurm_ntasks` | bool | No | `false` | Rely on `SLURM_NTASKS` env var instead of explicit `--ntasks` flag |
| `args` | string | No | `""` | Extra launcher arguments (space-separated string) |
| `extra_options` | string[] | No | `[]` | Extra launcher options (list form, alternative to `args`) |
| `resource_style` | string | No | `"standard"` | SBATCH resource style: `standard` or `rsc` |
| `modules` | string[] | No | `[]` | HPC modules to load in job.sh |
| `stdout` | string | No | `%j.out` | Custom stdout file format |
| `stderr` | string | No | `%j.err` | Custom stderr file format |
| `extra_sbatch` | string[] | No | `[]` | Additional raw `#SBATCH` directives |
| `env` | table | No | `{}` | Site-specific environment variables |

### resource_style

- **`standard`**: Emits `#SBATCH --ntasks=N`, `#SBATCH --nodes=N`, etc.
- **`rsc`**: Emits `#SBATCH --rsc p=N:t=T:c=C` (camphor/FUJITSU-style). `p` = processes, `t` = threads per process, `c` = cores per process.

---

## site.toml

HPC サイト固有の環境設定。`simctl init` でサイトプロファイル選択時に自動生成される。
Launcher (MPI 起動方式) とは独立に、ジョブスクリプト生成に影響する環境設定を管理する。

```toml
[site]
name = "camphor"
resource_style = "rsc"
modules = ["intel/2023.2", "intelmpi/2023.2"]
stdout = "stdout.%J.log"
stderr = "stderr.%J.log"

[site.env]
OMP_PROC_BIND = "spread"

[site.simulators.emses]
modules = ["hdf5/1.12.2_intel-2023.2-impi", "fftw/3.3.10_intel-2022.3-impi"]
```

### `[site]`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | No | サイト名 |
| `resource_style` | string | No | `"standard"` or `"rsc"` |
| `modules` | string[] | No | サイト共通モジュール |
| `stdout` | string | No | カスタム stdout ファイル名 |
| `stderr` | string | No | カスタム stderr ファイル名 |
| `extra_sbatch` | string[] | No | 追加 `#SBATCH` ディレクティブ |
| `setup_commands` | string[] | No | 実行前セットアップコマンド |

### `[site.env]`

ジョブスクリプト内で `export` する環境変数。

### `[site.simulators.<name>]`

| Field | Type | Description |
|-------|------|-------------|
| `modules` | string[] | シミュレータ固有の追加モジュール (サイト共通モジュールとマージされる) |

---

## case.toml

Case template definition. Located in `cases/<case_name>/case.toml`.

シミュレータの入力ファイルは `cases/<case_name>/input/` に置く。`simctl runs create` / `simctl runs sweep` 実行時、`input/` 以下がディレクトリ構造ごと run の `input/` に自動コピーされる。その後 adapter がパラメータ適用済みファイルで上書きする。

```
cases/
  flat_surface/
    case.toml          # メタデータ・パラメータ定義
    summarize.py       # run 後の解析・可視化フック
    input/             # テンプレート入力ファイル
      plasma.toml
```

```toml
[case]
name = "flat_surface"
simulator = "emses"
launcher = "srun"
description = "Flat surface sheath simulation"

[classification]
model = "sheath"
submodel = "flat_surface"
tags = ["2d", "electrostatic"]

[job]
partition = "gr20001a"
nodes = 1
ntasks = 800
walltime = "120:00:00"

[params]
"tmgrid.nx" = 4000
"tmgrid.ny" = 1
"tmgrid.nz" = 800
"tmgrid.dt" = 0.002
"jobcon.nstep" = 400000
"plasma.wc" = 0.0
"plasma.phiz" = 0.0
```

### `[case]`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | Yes | Case name (used in run_id generation) |
| `simulator` | string | Yes | Simulator name (must match `simulators.toml`) |
| `launcher` | string | No | Launcher profile name (must match `launchers.toml`) |
| `description` | string | No | Human-readable description |

### `[classification]`

Optional metadata for organizing runs.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `model` | string | No | Physical model category (e.g. `sheath`, `wave`) |
| `submodel` | string | No | Subcategory (e.g. `flat_surface`, `periodic`) |
| `tags` | string[] | No | Free-form tags for filtering |

### `[job]`

Slurm job parameters. These become `#SBATCH` directives in `job.sh`.

#### Standard mode (`resource_style = "standard"`)

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `partition` | string | No | Partition/queue name. Can be overridden at submit time with `simctl runs submit -qn <name>` |
| `nodes` | integer | No | Number of nodes |
| `ntasks` | integer | No | Number of MPI tasks |
| `walltime` | string | Yes | Wall time limit (HH:MM:SS) |

#### RSC mode (`resource_style = "rsc"`, camphor 等)

`site.toml` で `resource_style = "rsc"` の場合、`simctl case new` は以下のフィールドを生成する:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `partition` | string | No | Partition/queue name |
| `processes` | integer | No | MPI プロセス数 (`--rsc p=N`) |
| `threads` | integer | No | プロセスあたりスレッド数 (`--rsc t=T`) |
| `cores` | integer | No | プロセスあたりコア数 (`--rsc c=C`, ≥ threads) |
| `memory` | string | No | プロセスあたりメモリ (`--rsc m=MEM`, e.g. `"8G"`) |
| `gpus` | integer | No | GPU 数 (`--rsc g=N`) |
| `walltime` | string | Yes | Wall time limit (HH:MM:SS) |

#### 共通フィールド

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `modules` | string[] | No | 追加モジュール (site modules にマージされる) |
| `pre_commands` | string[] | No | 実行前シェルコマンド |
| `post_commands` | string[] | No | 実行後シェルコマンド |

### `[params]`

Parameter overrides using dot-notation keys. These modify the simulator's input file.

```toml
[params]
"tmgrid.nx" = 4000       # config["tmgrid"]["nx"] = 4000
"species.0.wp" = 1.0     # config["species"][0]["wp"] = 1.0
```

- Keys are dot-separated paths into the simulator's TOML input
- Numeric segments are treated as array indices
- Values can be integers, floats, strings, booleans, or arrays

---

## survey.toml

Parameter survey definition. Generates runs from the Cartesian product of parameter axes and co-varying (linked) parameter groups.

```toml
[survey]
id = "S20260328-mag-angle"
name = "Magnetic field angle scan"
base_case = "flat_surface"
simulator = "emses"
launcher = "srun"

[classification]
model = "sheath"
submodel = "with_mag"
tags = ["magnetic", "angle_scan"]

[axes]
"plasma.wc" = [0.0, 0.147, 0.294]
"plasma.phiz" = [0.0, 45.0, 90.0]

[naming]
display_name = "wc{wc}_phi{phiz}"

[job]
partition = "gr20001a"
nodes = 1
ntasks = 800
walltime = "120:00:00"
```

### `[survey]`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | string | No | Survey identifier |
| `name` | string | No | Human-readable name |
| `base_case` | string | Yes | Case name to use as template |
| `simulator` | string | Yes | Simulator name |
| `launcher` | string | No | Launcher profile name |

### `[axes]`

Parameter axes for Cartesian product expansion. Each key is a dot-notation parameter, value is an array of values to sweep.

```toml
[axes]
"plasma.wc" = [0.0, 0.147, 0.294]    # 3 values
"plasma.phiz" = [0.0, 45.0, 90.0]     # 3 values
# Total runs: 3 x 3 = 9
```

### `[[linked]]`

Co-varying parameter groups. Parameters within each `[[linked]]` group are **zipped** (must have equal-length arrays). Multiple `[[linked]]` groups are combined via Cartesian product with each other and with `[axes]`.

```toml
[axes]
seed = [1, 2, 3]

# nx and ny co-vary (zip): (32,32), (64,64), (128,128)
[[linked]]
nx = [32, 64, 128]
ny = [32, 64, 128]
# Total runs: 3 seeds × 3 linked pairs = 9
```

| Constraint | Description |
|-----------|-------------|
| Equal length | All arrays in one `[[linked]]` group must have the same length |
| No overlap | Parameter names must not appear in both `[axes]` and `[[linked]]` |
| Multiple groups | Each `[[linked]]` group is independent; groups are Cartesian-multiplied |

**Multiple groups example:**

```toml
[[linked]]
nx = [32, 64]
ny = [32, 64]

[[linked]]
dt = [0.1, 0.01]
steps = [100, 1000]
# Total runs: 2 grid pairs × 2 time pairs = 4
```

### `[naming]`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `display_name` | string | No | Template for run display names. Use `{key}` placeholders (leaf key after last dot) |

### `[job]`

Same as `case.toml [job]`. Shared across all generated runs.

---

## manifest.toml

Run manifest. The source of truth for a run's state, provenance, and history. Located at `<run_dir>/manifest.toml`. **Managed by simctl** — do not edit manually.

```toml
[run]
id = "R20260329-0001"
status = "completed"
created_at = "2026-03-29T10:30:00+09:00"
simulator = "emses"
case = "flat_surface"

[params]
"tmgrid.nx" = 4000
"tmgrid.nz" = 800
"plasma.wc" = 0.147
"plasma.phiz" = 45.0

[job]
job_id = "12345"
submitted_at = "2026-03-29T10:31:00+09:00"

[classification]
model = "sheath"
submodel = "with_mag"
tags = ["magnetic"]

[provenance]
resolver_mode = "package"
executable = "mpiemses3D"
git_commit = "abc1234"
git_dirty = false
```

### `[run]`

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Unique run ID (`R<YYYYMMDD>-<NNNN>`) |
| `status` | string | Current state (see state machine below) |
| `created_at` | datetime | ISO 8601 creation timestamp |
| `simulator` | string | Simulator name |
| `case` | string | Source case name |
| `parent_run_id` | string | Parent run ID (for cloned/extended runs) |

### State Machine

```
created -> submitted -> running -> completed
created/submitted/running -> failed
submitted/running -> cancelled
completed -> archived -> purged
```

### `[params]`

Frozen parameter snapshot at run creation time.

### `[job]`

| Field | Type | Description |
|-------|------|-------------|
| `job_id` | string | Slurm job ID |
| `submitted_at` | datetime | Submission timestamp |

### `[provenance]`

| Field | Type | Description |
|-------|------|-------------|
| `resolver_mode` | string | How the executable was resolved |
| `executable` | string | Executable path or name |
| `exe_hash` | string | SHA256 hash of executable |
| `git_commit` | string | Git commit hash |
| `git_dirty` | boolean | Whether working tree had uncommitted changes |
| `source_repo` | string | Source repository path |

---

## Run Directory Structure

```
R20260329-0001/
  manifest.toml        # Run state and metadata (source of truth)
  input/               # Simulator input files (frozen at creation)
    plasma.toml
  submit/
    job.sh             # Generated Slurm batch script
  work/                # Execution directory (cd here before srun)
    stdout.12345.log   # Job stdout
    stderr.12345.log   # Job stderr
    outputs/           # Simulator output files
    restart/           # Restart/checkpoint files
  analysis/            # Post-processing results
    summary.json       # Key metrics (generated by simctl analyze summarize)
    figures/            # Plots and visualizations
```

---

## analysis/summary.json

`simctl analyze summarize` が生成する run の要約ファイル。Adapter が基本メトリクスを出力し、プロジェクトスクリプトで拡張できる。
`simctl analyze collect` 実行時も、completed run に `analysis/summary.json` が無い場合はこの生成処理が自動で走る。

### 基本構造

```jsonc
{
  // Adapter が出す基本情報
  "status": "completed",
  "nstep": 400000,

  // プロジェクトスクリプトが追加するメトリクス
  "ion_flux_max": 1.23,

  // プロット参照 (analysis/ からの相対パス)
  "figures": [
    {
      "path": "figures/potential_profile.png",
      "caption": "Potential profile along z-axis"
    }
  ]
}
```

スキーマは固定しない。Adapter とプロジェクトスクリプトが任意のキーを追加できる。`figures` キーのみ以下の規約に従う:

| Field | Type | Description |
|-------|------|-------------|
| `figures[].path` | string | `analysis/` からの相対パス |
| `figures[].caption` | string | 図の説明 |

### プロジェクトスクリプトによる拡張

`simctl analyze summarize` は Adapter の `summarize()` 実行後、以下の順でプロジェクトスクリプトを探索し、見つかれば実行する:

1. `cases/<case>/summarize.py` — ケース固有の解析
2. `cases/<simulator>/<case>/summarize.py` — multi-simulator layout のケース解析
3. `scripts/summarize.py` — プロジェクト共通の解析

スクリプトは `summarize(run_dir, base_summary)` 関数を定義する:

```python
# cases/flat_surface/summarize.py
from pathlib import Path

def summarize(run_dir: Path, base_summary: dict) -> dict:
    """Adapter の summary を受け取り、拡張して返す。"""
    # work/ の出力を読んで独自メトリクスを追加
    base_summary["ion_flux_max"] = compute_ion_flux(run_dir)

    # プロット生成 → analysis/figures/ に保存
    fig_dir = run_dir / "analysis" / "figures"
    fig_dir.mkdir(parents=True, exist_ok=True)
    plot_path = fig_dir / "potential_profile.png"
    make_plot(run_dir, plot_path)

    base_summary.setdefault("figures", [])
    base_summary["figures"].append({
        "path": "figures/potential_profile.png",
        "caption": "Potential profile along z-axis",
    })
    return base_summary
```

スクリプトが例外を投げた場合は Warning を出力し、Adapter の summary のみで続行する。

---

## survey summary outputs

`simctl analyze collect <survey_dir>` は survey 配下の run を走査し、`<survey_dir>/summary/` に集計成果物を生成する。
`simctl analyze plot <survey_dir> --x <column> --y <column>` はこの集計結果を使って図を生成する。

### 生成されるファイル

| File | Description |
|------|-------------|
| `summary/survey_summary.csv` | ネストをフラット化した run 一覧。list/dict は JSON 文字列として保持。`origin.*`, `classification.*`, `variation.*`, `param.*` など manifest 由来の列も含む |
| `summary/survey_summary.json` | run ごとの summary 原本、状態数、数値統計、warning を含む集計 JSON |
| `summary/figures_index.json` | `analysis/figures/` と `summary.figures[]` を run ごとに引いた索引 |
| `summary/survey_summary.md` | すぐ読める Markdown レポート |
| `summary/plots/*.png` | `simctl analyze plot` が生成する survey 可視化 |

### 収集ルール

- `analysis/summary.json` がある run はそれを利用する
- completed run で `analysis/summary.json` が無い場合は自動 summarize してから集計する
- completed 以外の run は state count には含めるが、summary が無ければ集計対象外

### survey_summary.json の概要

```jsonc
{
  "generated_at": "2026-04-01T10:57:41+00:00",
  "survey_dir": "runs/beach_smoke",
  "total_runs": 2,
  "summaries_collected": 2,
  "generated_summaries": 1,
  "missing_summaries": 0,
  "state_counts": {
    "completed": 2
  },
  "numeric_stats": {
    "potential_final_v": {
      "count": 2,
      "min": -1.35,
      "max": 1.15,
      "mean": -0.1
    }
  },
  "warnings": [],
  "runs": [
    {
      "run_id": "R20260401-0001",
      "status": "completed",
      "summary": {
        "potential_final_v": 1.15
      }
    }
  ]
}
```

### plot command

`simctl analyze plot` は `survey_summary.json` の各 run から `flat_metadata` と `flat_summary` を統合した表を読み、指定列で可視化する。

```bash
simctl analyze plot runs/sheath/angle_scan --list-columns
simctl analyze plot runs/sheath/angle_scan --x param.tmgrid_dt --y floating_potential_final
simctl analyze plot runs/sheath/angle_scan --x origin.case --y energy_total_ratio --kind bar
simctl analyze plot runs/sheath/angle_scan --x param.angle --y ion_flux --group param.seed
```

| Option | Description |
|--------|-------------|
| `--x` | x 軸列名 |
| `--y` | y 軸列名 (数値列) |
| `--kind` | `auto`, `line`, `scatter`, `bar` |
| `--group` | シリーズ分割に使う列名 |
| `--output` | 保存先パス |
| `--list-columns` | 利用可能な列を表示して終了 |

`--kind auto` では、x 列が数値なら line、非数値なら bar を選ぶ。

---

## JSON Schema

All TOML files support schema validation via `#:schema` comments:

```toml
#:schema https://raw.githubusercontent.com/Nkzono99/hpc-simctl/main/schemas/case.json
[case]
...
```

Schema files: `schemas/simproject.json`, `schemas/simulators.json`, `schemas/launchers.json`, `schemas/case.json`, `schemas/survey.json`, `schemas/manifest.json`, `schemas/campaign.json`

---

## campaign.toml

プロジェクトルートに配置する研究意図の記述ファイル。AI エージェントに「何を調べたいか」を伝える。

### [campaign]

| フィールド | 型 | 必須 | 説明 |
|-----------|-----|------|------|
| `name` | string | Yes | キャンペーン名 |
| `description` | string | No | 研究の動機・背景 |
| `hypothesis` | string | No | 検証する仮説 |
| `simulator` | string | No | 使用するシミュレータ名 |

### [variables]

パラメータ名 (dot 記法) をキーとし、変数定義を値とする。

| フィールド | 型 | 必須 | 説明 |
|-----------|-----|------|------|
| `role` | string | Yes | `independent` / `dependent` / `fixed` / `controlled` |
| `range` | [number, number] | No | 独立変数の [min, max] |
| `values` | array | No | 明示的な値のリスト |
| `unit` | string | No | 物理単位 |
| `reason` | string | No | この値に設定した理由 |

### [observables]

観測量名をキーとし、出力定義を値とする。

| フィールド | 型 | 必須 | 説明 |
|-----------|-----|------|------|
| `source` | string | No | 出力ファイルのパスまたは glob |
| `column` | int/string | No | 出力ファイル内のカラム |
| `description` | string | No | 観測量の説明 |
| `unit` | string | No | 物理単位 |

### 例

```toml
[campaign]
name = "magnetic-angle-dependence"
hypothesis = "磁力線入射角 45 度付近でイオンフラックスが最大になる"
simulator = "emses"

[variables]
"plasma.wc" = { role = "independent", range = [0.0, 0.5], unit = "omega_pe" }
"tmgrid.dt" = { role = "fixed", values = [1.0], reason = "CFL 条件" }

[observables]
ion_flux = { source = "work/influx", column = 1, description = "イオンフラックス" }
```

---

## .simctl/environment.toml

`simctl doctor` で自動生成される実行環境記述ファイル。

### [cluster]

| フィールド | 型 | 説明 |
|-----------|-----|------|
| `name` | string | クラスタ名 |
| `scheduler` | string | ジョブスケジューラ (`slurm`) |
| `scratch_path` | string | スクラッチパステンプレート |

### [cluster.partitions.{name}]

| フィールド | 型 | 説明 |
|-----------|-----|------|
| `max_nodes` | int | 最大ノード数 |
| `max_walltime` | string | 最大実行時間 |
| `gpu` | bool | GPU 利用可否 |
| `default` | bool | デフォルトパーティションか |

### [cluster.constraints]

任意のキー・値ペアでクラスタ制約を記述 (例: `max_jobs_per_user = 100`)。

### [modules]

名前付きモジュールセット。値はモジュール名のリスト。

---

## .simctl/links.toml

他プロジェクトや共有知識ストアへの参照を定義。

### [projects]

キーがリンク名、値が相対/絶対パス。

### [shared]

キーがリソース名、値がパス (`~` 展開対応)。

```toml
[projects]
surface-charging = "../surface-charging"

[shared]
knowledge = "~/.simctl/knowledge"
```

