# SKILLS.md — {{ project_name }}

Agent と人がそのまま参照できる **実行例集** です。
定型作業はまずこのファイルの Bash 例に沿って進めます。

詳細なフィールド定義は `tools/hpc-simctl/docs/toml-reference.md` を参照してください。

---

## 0. project の現在地を把握する

```bash
simctl context
simctl list
simctl jobs
```

使う場面:
- 新しいセッションを始めたとき
- 何が走っているか把握したいとき

---

## 1. 新しい Case を作る

```bash
# 雛形を作る (cases/<sim>/ 以下なら simulator を自動検出)
cd cases/emses && simctl new my_case
# または simulator を明示
simctl new my_case -s emses -d cases/emses

# case 定義を編集
$EDITOR cases/emses/my_case/case.toml

# テンプレート入力を置く
$EDITOR cases/emses/my_case/input/plasma.toml
```

---

## 2. Case から単一 Run を作る

```bash
cd runs/test/basic
simctl create my_case
simctl list
```

`--dest` で生成先を変更できる:

```bash
simctl create my_case --dest runs/test/basic
```

---

## 3. Survey を組んで展開する

```bash
mkdir -p runs/sheath/angle_scan
$EDITOR runs/sheath/angle_scan/survey.toml

# survey.toml から全 run を生成
simctl sweep runs/sheath/angle_scan
simctl list runs/sheath/angle_scan
```

`simctl create survey` でも同じ:

```bash
cd runs/sheath/angle_scan
simctl create survey
```

---

## 4. 個別 Run を投入する

```bash
cd runs/test/basic/R20260330-0001
simctl run
simctl status
simctl history
```

queue を明示したいとき:

```bash
simctl run -qn compute
```

dry-run で確認:

```bash
simctl run --dry-run
```

---

## 5. Survey 全体を投入する

```bash
cd runs/sheath/angle_scan
simctl list
simctl run --all
```

queue を明示したいとき:

```bash
simctl run --all -qn compute
```

注意:
- `run --all` は高コスト操作。事前に plan を出す
- 初回の大規模 survey は承認を取る

---

## 6. 状態確認と同期

### 個別 run

```bash
cd runs/test/basic/R20260330-0001
simctl status     # manifest の状態を表示 (更新しない)
simctl sync       # Slurm 状態を manifest に反映
```

### プロジェクト全体

```bash
simctl list runs/sheath/angle_scan
simctl jobs           # submitted/running のジョブ一覧
simctl jobs --all     # 全 run のジョブ情報
simctl history        # 投入履歴 (最新20件)
simctl history -n 0   # 全件
```

---

## 7. ログを見る

```bash
cd runs/test/basic/R20260330-0001

# stdout (デフォルト20行)
simctl log

# stderr
simctl log -e

# 行数を指定
simctl log -n 100

# follow (tail -f 相当)
simctl log -f

# 必要なら work 以下も見る
ls work/
tail -n 100 work/*.err
tail -n 100 work/*.out
```

---

## 8. Failed Run を調べる

```bash
cd runs/test/basic/R20260330-0001
simctl sync
simctl status
simctl log -e
simctl log
```

判断の目安:
- `timeout` → walltime 延長候補
- `oom` → メモリ増加または問題サイズ縮小候補
- `preempted` → 同条件再投入候補
- `exit_error` → まず log / err を確認

---

## 9. Retry のために再準備する

```bash
# case を修正して新しい run を作る
$EDITOR cases/emses/sheath_basic/case.toml
simctl create sheath_basic --dest runs/sheath/retry

# または survey を修正して再展開
$EDITOR runs/sheath/angle_scan/survey.toml
simctl sweep runs/sheath/angle_scan
```

その後、必要な run を投入する:

```bash
simctl run
# または
simctl run --all
```

---

## 10. Run を Clone する

```bash
# cwd の run を clone
simctl clone --dest runs/test/variant

# パラメータを変更して clone
simctl clone --set dt=0.5e-8 --set nx=128
```

---

## 11. 完了した Run を継続する

```bash
# cwd の completed run から continuation run を生成
simctl extend

# ステップ数を指定して継続
simctl extend --nstep 200000

# 継続 run を生成して即投入
simctl extend --run
```

---

## 12. Run を要約する

```bash
cd runs/test/basic/R20260330-0001
simctl summarize
```

---

## 13. Survey 結果を集計する

```bash
simctl collect runs/sheath/angle_scan
```

---

## 14. 人向け知見を保存する

```bash
simctl knowledge save sheath_scan_summary \
  -t result \
  -s emses \
  -m "Angle scan shows strongest response near 45 degrees."
```

タグ付きの例:

```bash
simctl knowledge save dt_instability_note \
  -t constraint \
  -s emses \
  --tags "stability,cfl,dt" \
  -m "dt above 1.0e-8 destabilizes the nx=64 setup."
```

知見タイプ: `constraint`, `result`, `analysis`, `dependency`

---

## 15. 機械可読な Fact を追加する

```bash
simctl knowledge add-fact \
  "dt > 1.0e-8 destabilizes EMSES electrostatic runs at nx=64" \
  -t constraint \
  -s emses \
  --param-name tmgrid.dt \
  --scope-text "baseline electrostatic scan" \
  --evidence-kind run_observation \
  --evidence-ref run:R20260330-0004 \
  -c high \
  --tags "stability,cfl,dt"
```

fact を確認する:

```bash
simctl knowledge facts
simctl knowledge facts --scope emses
simctl knowledge facts --tag stability -c medium
```

fact タイプ: `observation`, `constraint`, `dependency`, `policy`, `hypothesis`

---

## 16. 他 Project から知見を取り込む

```bash
simctl knowledge links
simctl knowledge sync
simctl knowledge sync -s emses
```

---

## 17. Refs と Simulator Knowledge を確認する

```bash
# refs の更新
simctl update-refs

# ナレッジインデックスの確認
find .simctl/knowledge -maxdepth 2 -type f | sort

# refs の中身を確認
find refs -maxdepth 2 -type d | sort
find refs -maxdepth 4 -type f | head -200
```

---

## 18. 整理・アーカイブ

```bash
# completed run をアーカイブ
simctl archive
simctl archive --yes   # 確認をスキップ

# work/ の不要ファイルを削除
simctl purge-work
simctl purge-work --yes
```

注意: `archive` / `purge-work` は確認が必要な操作。

---

## 19. 環境セットアップ

```bash
# 方法 1: ブートストラップ (新規プロジェクト)
uvx --from git+https://github.com/Nkzono99/hpc-simctl.git simctl init
source .venv/bin/activate

# 方法 2: 手動セットアップ (既存プロジェクト)
uv venv .venv
mkdir -p tools && git clone https://github.com/Nkzono99/hpc-simctl.git tools/hpc-simctl
uv pip install -e ./tools/hpc-simctl
{{ pip_install_line }}
source .venv/bin/activate
simctl doctor
```

---

## 20. コマンドのオプションを調べる

```bash
simctl --help
simctl create --help
simctl sweep --help
simctl run --help
simctl status --help
simctl knowledge --help
simctl knowledge add-fact --help
```

---

## 短い注意

- run は simctl で生成する
- `manifest.toml` は手で書かない
- `Rxxxx/input/*` や `submit/job.sh` を直接作らない
- まず実行例に沿って進める
- 迷ったら `AGENTS.md` に戻る
