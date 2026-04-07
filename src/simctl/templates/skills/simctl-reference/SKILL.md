---
name: simctl-reference
description: simctl CLI command reference and usage patterns. Use when working with simctl commands, creating runs, submitting jobs, or checking status.
user-invocable: false
---

# simctl コマンドリファレンス

詳細なフィールド定義は `tools/hpc-simctl/docs/toml-reference.md` を参照。

## 現在地を把握する

```bash
simctl context --json      # project / campaign / runs / failures の概要
simctl runs list           # run 一覧
simctl runs list runs/a runs/b  # 複数 PATH 指定
simctl runs jobs           # submitted/running のジョブ一覧
simctl runs jobs --all     # 全 run のジョブ情報
simctl runs jobs -w 30     # 30 秒ごとに自動更新
simctl runs dashboard runs/<survey>     # 複数 run の進捗 (state, step/N, %, slurm)
simctl runs dashboard runs/<survey> -w 30
simctl runs dashboard runs/<survey> --all  # completed/failed も表示
simctl runs history        # 投入履歴 (最新20件)
simctl runs history -n 0   # 全件
```

## Case を作る

```bash
# simulator 指定で cases/<sim>/ 以下に自動生成
simctl case new my_case -s emses
# cases/<sim>/ 以下なら simulator を自動検出
cd cases/emses && simctl case new my_case
# 小さな bundled テンプレートで生成 (refs/ の rich テンプレートを使わない)
simctl case new my_case -s emses --minimal
# survey.toml stub も同時生成
simctl case new my_case -s emses --survey
# 生成先を明示指定
simctl case new my_case -s emses -d /path/to/dest
```

EMSES の場合、`simctl case new` は best-effort で `emu generate -u` を呼んで
生成された `plasma.toml` の `[meta.physical]` を埋める (`emu` が PATH に
入っていなければ silent skip)。

## Run を作る

```bash
# case から単一 run を生成 (cwd に生成)
cd runs/test/basic && simctl runs create my_case
# 生成先を指定
simctl runs create my_case --dest runs/test/basic
```

## Survey を展開する

```bash
# survey.toml から全 run を生成
simctl runs sweep runs/sheath/angle_scan
# cwd が survey ディレクトリなら引数省略可
cd runs/sheath/angle_scan && simctl runs sweep
# 生成せずに件数・パラメータ組合せ・概算 core-hour だけ確認
simctl runs sweep runs/sheath/angle_scan --dry-run
```

## Run を投入する

```bash
# 個別 run
cd runs/test/basic/R20260330-0001
simctl runs submit
simctl runs submit -qn compute       # queue 指定
simctl runs submit --dry-run          # 確認のみ

# survey 全体
cd runs/sheath/angle_scan
simctl runs submit --all
simctl runs submit --all -qn compute
```

## 状態確認と同期

```bash
simctl runs status                    # cwd の run の状態 (manifest 更新なし)
simctl runs status R20260330-0001 R20260330-0002  # 複数を一気に
simctl runs status runs/sheath/angle_scan         # survey 配下を一括で
simctl runs sync                      # Slurm 状態を manifest に反映
simctl runs sync runs/sheath/angle_scan           # survey 一括 sync
                                                  # (created な run は silent skip)
```

## ログ

```bash
simctl runs log            # stdout (デフォルト20行)
simctl runs log -e         # stderr
simctl runs log -n 100     # 行数指定
simctl runs log -f         # follow (tail -f 相当)
```

## Clone / Extend

```bash
# clone
simctl runs clone --dest runs/test/variant
simctl runs clone --set dt=0.5e-8 --set nx=128

# 完了 run から continuation
simctl runs extend
simctl runs extend --nstep 200000
simctl runs extend --run         # 生成して即投入
```

## 解析

```bash
simctl analyze summarize                          # run の要約
simctl analyze collect runs/sheath/angle_scan     # survey 集計 artifacts (CSV/JSON/report)
simctl analyze plot runs/sheath/angle_scan --list-columns
simctl analyze plot runs/sheath/angle_scan --list-recipes
simctl analyze plot runs/sheath/angle_scan --recipe completion-vs-dt
simctl analyze plot runs/sheath/angle_scan --x param.angle --y ion_flux
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
simctl knowledge facts --local-only
simctl knowledge facts --scope emses --tag stability -c medium
simctl knowledge promote-fact shared:f004

# 外部 knowledge source
simctl knowledge source attach path other-project ../other-project --kind project
simctl knowledge source attach git shared-kb https://github.com/u/repo.git
simctl knowledge source attach path analysis-notes ../shared-notes --kind insights
simctl knowledge source detach other-project
simctl knowledge source list
simctl knowledge source sync                        # 接続先から知見をインポート
simctl knowledge source sync -s emses
```

## 停止・整理・削除

```bash
# 実行中の run を安全に停止 (scancel + sync を一回で)
simctl runs cancel             # submitted/running の run を停止
simctl runs cancel --yes       # 確認スキップ

# completed → archived → purged の通常フロー
simctl runs archive            # completed run をアーカイブ
simctl runs archive --yes      # 確認スキップ
simctl runs purge-work         # work/ の不要ファイル削除 (archived のみ)
simctl runs purge-work --yes

# created/cancelled/failed の run ディレクトリをハード削除
# (completed/archived には使えない — archive → purge-work を使うこと)
simctl runs delete             # 確認あり
simctl runs delete --yes       # 確認スキップ
```

## Cookbook を参照する

`refs/` 以下のシミュレータリポジトリに `cookbook/` がある場合:

```bash
# entry 一覧 (index.toml)
cat refs/<repo>/cookbook/index.toml

# entry の詳細 (meta.toml)
cat refs/<repo>/cookbook/examples/<category>/<name>/meta.toml

# 入力例
cat refs/<repo>/cookbook/examples/<category>/<name>/input.toml

# fragment
cat refs/<repo>/cookbook/fragments/<category>/<name>/meta.toml
cat refs/<repo>/cookbook/fragments/<category>/<name>/fragment.toml
```

index.toml で `status = "stable"` の entry を選ぶ。
meta.toml の `[recommended].vary_first` がサーベイ軸の候補になる。
`[edit_policy].immutable` は変更しない。
fragment は `[merge]` と `[compatibility]` を確認してから使う。

## 環境

```bash
simctl doctor             # 環境検査
simctl update-refs        # refs/ 更新 + cookbook/ナレッジ再生成
simctl config show        # 設定表示
```
