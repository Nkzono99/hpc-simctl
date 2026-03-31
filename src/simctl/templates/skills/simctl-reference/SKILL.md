---
name: simctl-reference
description: simctl CLI command reference and usage patterns. Use when working with simctl commands, creating runs, submitting jobs, or checking status.
user-invocable: false
---

# simctl コマンドリファレンス

詳細なフィールド定義は `tools/hpc-simctl/docs/toml-reference.md` を参照。

## 現在地を把握する

```bash
simctl context        # project / campaign / runs / failures の概要
simctl list           # run 一覧
simctl jobs           # submitted/running のジョブ一覧
simctl jobs --all     # 全 run のジョブ情報
simctl history        # 投入履歴 (最新20件)
simctl history -n 0   # 全件
```

## Case を作る

```bash
# cases/<sim>/ 以下なら simulator を自動検出
cd cases/emses && simctl new my_case
# simulator を明示
simctl new my_case -s emses -d cases/emses
```

## Run を作る

```bash
# case から単一 run を生成 (cwd に生成)
cd runs/test/basic && simctl create my_case
# 生成先を指定
simctl create my_case --dest runs/test/basic
```

## Survey を展開する

```bash
# survey.toml から全 run を生成
simctl sweep runs/sheath/angle_scan
# または cwd で
cd runs/sheath/angle_scan && simctl create survey
```

## Run を投入する

```bash
# 個別 run
cd runs/test/basic/R20260330-0001
simctl run
simctl run -qn compute       # queue 指定
simctl run --dry-run          # 確認のみ

# survey 全体
cd runs/sheath/angle_scan
simctl run --all
simctl run --all -qn compute
```

## 状態確認と同期

```bash
simctl status         # manifest の状態を表示 (更新しない)
simctl sync           # Slurm 状態を manifest に反映
```

## ログ

```bash
simctl log            # stdout (デフォルト20行)
simctl log -e         # stderr
simctl log -n 100     # 行数指定
simctl log -f         # follow (tail -f 相当)
```

## Clone / Extend

```bash
# clone
simctl clone --dest runs/test/variant
simctl clone --set dt=0.5e-8 --set nx=128

# 完了 run から continuation
simctl extend
simctl extend --nstep 200000
simctl extend --run         # 生成して即投入
```

## 解析

```bash
simctl summarize                          # run の要約
simctl collect runs/sheath/angle_scan     # survey 集計 CSV
```

## 知見管理

```bash
# 人向け知見
simctl knowledge save name -t result -s emses -m "..."
simctl knowledge save name -t constraint -s emses --tags "stability,cfl" -m "..."
simctl knowledge list
simctl knowledge list -s emses -t constraint

# 機械可読 fact
simctl knowledge add-fact "claim" -t constraint -s emses \
  --param-name tmgrid.dt --scope-text "baseline scan" \
  --evidence-kind run_observation --evidence-ref run:R20260330-0001 \
  -c high --tags "stability,cfl"
simctl knowledge facts
simctl knowledge facts --scope emses --tag stability -c medium

# プロジェクト間
simctl knowledge links
simctl knowledge sync
simctl knowledge sync -s emses
```

## 整理

```bash
simctl archive            # completed run をアーカイブ
simctl archive --yes      # 確認スキップ
simctl purge-work         # work/ の不要ファイル削除
simctl purge-work --yes
```

## 環境

```bash
simctl doctor             # 環境検査
simctl update-refs        # refs/ 更新 + ナレッジ再生成
simctl config show        # 設定表示
```
