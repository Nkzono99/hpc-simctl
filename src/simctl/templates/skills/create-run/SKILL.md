---
name: create-run
description: Create runs or expand a survey from cases. Use when generating simulation runs with simctl create or simctl sweep.
disable-model-invocation: true
---

# Run / Survey を生成する

## 手順

1. 使用するケースの case.toml を確認する
2. 単一 run か survey (パラメータスイープ) かを判断する
3. run を生成する
4. 生成結果を確認する

## 単一 Run の生成

```bash
# 生成先ディレクトリへ移動して実行
cd runs/test/basic
simctl create <case_name>

# または --dest で生成先を指定
simctl create <case_name> --dest runs/test/basic
```

生成される run:
```
runs/test/basic/Rxxxxxxxx-xxxx/
  manifest.toml      # 状態・由来・provenance (正本)
  input/             # 入力ファイル (case から自動生成)
  submit/            # job.sh (自動生成)
  work/              # 実行時出力用 (空)
  analysis/          # 解析結果用 (空)
```

## Survey の展開

survey.toml がある場合、パラメータの直積で複数 run を一括生成する。

```bash
# survey.toml のあるディレクトリを指定
simctl sweep runs/sheath/angle_scan

# または cwd で
cd runs/sheath/angle_scan
simctl create survey
```

### survey.toml の準備

survey.toml が未作成の場合は、先にケースと survey を作成する:

```bash
# ケース作成時に --survey で同時生成
simctl new my_case -s emses --survey

# または既存ケースに survey を追加
mkdir -p runs/<survey_name>
# survey.toml を作成 (フォーマットは /survey-design スキル参照)
```

### survey.toml の例

```toml
[survey]
name = "angle sweep"
base_case = "emses/my_case"
simulator = "emses"
launcher = "default"

[axes]
"species[2].ray_zenith_angle_deg" = [0, 20, 40, 60, 80]
"tmgrid.dt" = [0.5, 1.0]

[naming]
display_name = "angle{%raw%}{{ray_zenith_angle_deg}}{%endraw%}_dt{%raw%}{{tmgrid_dt}}{%endraw%}"

[job]
partition = "compute"
nodes = 4
ntasks = 32
walltime = "02:00:00"
```

この例では 5 x 2 = 10 個の run が生成される。

## 生成結果の確認

```bash
# run 一覧を表示
simctl list
simctl list runs/sheath/angle_scan

# 生成数と設定を確認
simctl status
```

## 生成後の次ステップ

```bash
# 単一 run を投入
cd runs/test/basic/Rxxxxxxxx-xxxx
simctl run -qn <partition>

# survey 全体を投入 (/run-all スキル推奨)
cd runs/sheath/angle_scan
simctl run --all -qn <partition>
```

## 注意

- run ディレクトリを手で作らない (必ず `simctl create` / `simctl sweep` を使う)
- manifest.toml を手動編集しない
- input/ や submit/job.sh を直接作らない
- survey の run 数が多い場合は投入前に plan を出して承認を取る
- `simctl run --all --dry-run` で投入前に確認できる
