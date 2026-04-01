### BEACH (BEM + Accumulated CHarge Simulator)

#### 概要
BEACH は境界要素法 (BEM) ベースの表面帯電シミュレーション。
MPI + OpenMP ハイブリッド並列で実行し、宇宙機表面の帯電現象を計算する。

#### 入力ファイル
- **`input/beach.toml`** — メイン設定ファイル (TOML 形式)
  - `[sim]`: `dt`, `max_step`, `batch_count`, `field_solver`
  - `[mesh]`: `obj_path` (OBJ メッシュファイルパス)
  - `[environment]`: プラズマ環境パラメータ (密度, 温度, etc.)
  - `[output]`: `dir` (出力ディレクトリ)

#### 出力ファイル (`work/outputs/` 以下)
- `summary.txt` — 計算結果サマリー (完了時に生成)
- `charges.csv` — 表面電荷分布
- `charge_history.csv` — 電荷時間履歴
- `potential_history.csv` — 電位時間履歴
- `mesh_triangles.csv`, `mesh_sources.csv` — メッシュ情報
- `performance_profile.csv` — 性能プロファイル

#### 完了判定
- `work/outputs/summary.txt` が存在 → completed
- stderr に "error", "fatal", "killed" → failed
- `charges.csv` のみ存在 → running (途中)

#### パラメータサーベイでよく変えるパラメータ
- `sim.dt`, `sim.max_step`, `sim.batch_count`
- `environment.electron_density`, `environment.electron_temperature`
- `environment.ion_density`, `environment.ion_temperature`
- `mesh.obj_path` (異なるジオメトリの比較)

#### ドキュメント・参考
- BEACH ソースリポジトリの README / docs/
- OBJ メッシュファイルは Blender 等で作成
- パラメータの dot 記法例: `sim.dt=1.0e-6`, `environment.electron_density=1.0e12`

#### 実行コマンド
```
srun beach input/beach.toml
```

#### 環境変数 (OpenMP)
```
OMP_NUM_THREADS=${SLURM_CPUS_PER_TASK:-1}
OMP_PROC_BIND=spread
OMP_PLACES=cores
```
