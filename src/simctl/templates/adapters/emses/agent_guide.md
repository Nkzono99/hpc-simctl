### EMSES (Electromagnetic Particle-in-Cell Simulator)

#### 概要
EMSES は 3D 電磁粒子シミュレーション (PIC) コード。
MPI 並列で実行し、電磁場と荷電粒子の自己無撞着な時間発展を計算する。

#### 入力ファイル
- **`input/plasma.toml`** — メイン設定ファイル (TOML 形式)
  - `[jobcon]`: `nstep` (総ステップ数) が最重要パラメータ
  - `[tmgrid]`: `nx`, `ny`, `nz` (グリッド数), `dt` (時間刻み)
  - `[[species]]`: 粒子種の定義 (質量比, 温度, 密度 etc.)
  - `[emfield]`: 外部磁場・電場の設定
  - `[[ptcond.objects]]`: 境界条件・導体オブジェクト

#### 出力ファイル (`work/` 以下)
- `*.h5` — HDF5 形式の電磁場データ (ex, ey, ez, bx, by, bz, etc.)
- `energy` — エネルギー時系列 (ASCII)。最終行のステップ番号で完了判定
- `SNAPSHOT1/esdat*.h5` — リスタート用スナップショット
- 各種診断ファイル: `ewave`, `chgacm1`, `influx`, `icur` 等

#### 完了判定
- `work/energy` の最終行のステップ番号 ≥ `nstep` → completed
- stderr に "error", "segmentation fault", "killed" → failed

#### パラメータサーベイでよく変えるパラメータ
- `tmgrid.dt`, `tmgrid.nx/ny/nz`
- `species[0].temperature`, `species[0].density`
- `emfield.ex0`, `emfield.bx0` (外部場)
- `jobcon.nstep`

#### ドキュメント・参考
- EMSES ソースリポジトリの README / docs/
- `plasma.toml` のスキーマは `format_version = 2` (structured TOML)
- パラメータの dot 記法例: `tmgrid.nx=128`, `species.0.temperature=1.0e6`

#### 実行コマンド
```
srun mpiemses3D plasma.toml
```
