---
name: new-case
description: Create a new simulation case and customize its input files. Use when setting up a new case from scratch with simctl new.
disable-model-invocation: true
---

# ケースを作成・編集する

## 手順

1. campaign.toml を確認して研究目的・対象シミュレータを把握する
2. `simctl new` でケースの雛形を生成する
3. case.toml のパラメータを研究目的に合わせて編集する
4. 入力テンプレートをカスタマイズする
5. (必要なら) survey.toml も同時に生成する

## ケースの作成

```bash
# simulator を指定するだけで cases/<sim>/ 以下に自動生成
simctl new my_case -s emses

# survey.toml も同時に生成
simctl new my_case -s emses --survey

# cases/<sim>/ 以下にいれば -s 不要 (自動検出)
cd cases/emses && simctl new my_case

# 明示的に生成先を指定
simctl new my_case -s emses -d /path/to/dest
```

生成されるファイル:
```
cases/<sim>/<case_name>/
  case.toml          # パラメータ定義
  <input_file>       # シミュレータ固有の入力テンプレート
  survey.toml        # (--survey 指定時) runs/<case_name>/ に生成
```

## case.toml の編集

```toml
[case]
name = "my_case"
simulator = "emses"
launcher = "default"
description = "実験の目的を簡潔に記述"

[params]
# dot 記法でシミュレータパラメータを上書き
"tmgrid.dt" = 1.0
"tmgrid.nx" = 128
"jobcon.nstep" = 50000

[job]
partition = "compute"
nodes = 4
ntasks = 32
walltime = "02:00:00"
```

### パラメータの確認方法

```bash
# CLAUDE.md の agent_guide セクションでパラメータ名を確認
cat CLAUDE.md

# cookbook で推奨パラメータ・値域を確認
cat refs/<repo>/cookbook/index.toml

# 既知の制約を確認
simctl knowledge facts
```

## 入力テンプレートの編集

- EMSES: `cases/emses/<case_name>/plasma.toml`
- BEACH: `cases/beach/<case_name>/beach.toml`

case.toml の `[params]` で dot 記法で指定したパラメータは、入力テンプレートの値を上書きする。
テンプレートには基本設定を書き、case.toml には実験ごとに変えるパラメータだけを書く。

## 注意

- ケースは必ず `simctl new` で作る (手書きしない)
- cookbook の `[edit_policy].immutable` パラメータは変更しない
- `[edit_policy].sensitive` パラメータを変更する場合は理由を記録する
- description には実験の意図を書く (後から振り返れるように)
- ケース作成後は `simctl create` で run を生成する
