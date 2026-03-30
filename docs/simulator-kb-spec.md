# Simulator Repo `simctl/` Knowledge Bundle Spec

シミュレーションリポジトリ側で、`simctl` と AI Agent が参照できる
simulator-specific knowledge source を提供するための規約。

目的は、単なる README 参照ではなく、

- 典型的な入力例
- 用途別プリセット
- パラメータ生成のためのベースライン
- 部分設定の再利用
- 数値安定性や既知制約

を、ファイルシステム上の軽量な構造で提供することにある。

この knowledge bundle は source repo 側で管理し、
project 側の `campaign.toml` や `insights` とは分離する。

## 位置づけ

- **source repo 側**: simulator-specific knowledge source
- **simctl project 側**: campaign-specific working knowledge

`simctl update-refs` は `refs/` にクローンした source repo を更新し、
この bundle を `.simctl/knowledge/` のインデックス対象として扱う。

## ディレクトリ構成

推奨構成:

```text
repo/
  simctl/
    index.toml
    examples/
      electrostatic/
        sheath-basic/
          meta.toml
          input.toml
          notes.md
      electromagnetic/
        alfven-wave/
          meta.toml
          input.toml
    fragments/
      boundary/
        absorbing-open/
          meta.toml
          fragment.toml
      diagnostics/
        quick-look/
          meta.toml
          fragment.toml
    constraints/
      physics.toml
      numerics.toml
      notes.md
```

## 必須要件

- `simctl/index.toml` は必須
- 各 example / fragment ディレクトリは `meta.toml` を持つ
- 各 bundle は `schema_version` を持つ
- 各 entry は repo 内で安定な `id` を持つ
- `path` は `simctl/` からの相対ではなく、`index.toml` から見た相対パスで表す

## 設計原則

- 大きな DB ではなく、構造化ディレクトリ + 薄い目録に留める
- index は検索エンジンではなく、Agent が全体像を掴むための目録
- 完全な入力例を主役にし、fragment と constraint は補助にする
- 人間向け補足は Markdown、機械可読メタデータは TOML に分ける
- 破壊的変更を避けるため `schema_version` を明示する

## `index.toml`

`index.toml` は bundle 全体の目録。Agent はまずこれを読む想定。

最小例:

```toml
[bundle]
schema_version = "0.1"
simulator = "emses"
title = "MPIEMSES3D simctl knowledge bundle"
description = "Examples, fragments, and constraints for agent-assisted setup"

[[entries]]
id = "electrostatic-sheath-basic"
kind = "example"
path = "examples/electrostatic/sheath-basic"
title = "Basic electrostatic sheath"
summary = "Minimal stable sheath setup for quick testing"
tags = ["electrostatic", "sheath", "1d", "baseline"]
recommended_for = ["sanity-check", "parameter-sweep-base"]
difficulty = "low"

[[entries]]
id = "quick-look-diagnostics"
kind = "fragment"
path = "fragments/diagnostics/quick-look"
title = "Quick-look diagnostics"
summary = "Minimal diagnostics fragment for cheap smoke tests"
tags = ["diagnostics", "smoke-test"]
recommended_for = ["baseline", "debug"]
difficulty = "low"

[[entries]]
id = "numerics-constraints"
kind = "constraint_set"
path = "constraints/numerics.toml"
title = "Numerical constraints"
summary = "Known numerical stability and resolution guidance"
tags = ["numerics", "stability"]
recommended_for = ["parameter-generation", "validation"]
difficulty = "medium"
```

### `[bundle]`

必須項目:

- `schema_version`
- `simulator`

推奨項目:

- `title`
- `description`
- `repo_url`
- `maintainers`

### `[[entries]]`

必須項目:

- `id`: 安定な識別子
- `kind`: `example`, `fragment`, `constraint_set`, `note`
- `path`: entry の実体への相対パス
- `title`

推奨項目:

- `summary`
- `tags`
- `recommended_for`
- `difficulty`
- `priority`

### `kind`

- `example`: 完全な入力例。Agent の第一候補になる
- `fragment`: 部分設定。example に合成して使う
- `constraint_set`: 数値条件、推奨範囲、既知の危険条件
- `note`: 追加の説明資料

### 語彙の推奨

`recommended_for` はなるべく語彙を揃える:

- `sanity-check`
- `baseline`
- `parameter-sweep-base`
- `parameter-generation`
- `small-test`
- `debug`
- `production-template`

`difficulty` は以下に限定する:

- `low`
- `medium`
- `high`

## example / fragment の `meta.toml`

入力ファイル本体だけでは意図が分かりにくいので、
各 entry に `meta.toml` を置く。

例:

```toml
id = "cavity-flow-2d"
kind = "example"
title = "2D cavity under flowing plasma"
summary = "Baseline example for cavity charging under plasma flow"

[files]
input = ["input.toml"]
notes = ["notes.md"]

[applicability]
model = "electrostatic"
geometry = "2d-cavity"
flow = true
photoelectron = false

[recommended]
use_for = ["baseline", "small-test", "parameter-generation"]
vary_first = ["flow_velocity", "cavity_width", "nx", "dt"]
avoid_if = ["strongly electromagnetic phenomena"]

[stability]
confidence = "medium"
known_good = true
notes = "Stable for moderate flow speed and current default grid"
```

### 必須項目

- `id`
- `kind`
- `title`

### 推奨項目

- `summary`
- `[files]`
- `[applicability]`
- `[recommended]`
- `[stability]`

### `[files]`

推奨フィールド:

- `input`: 完全入力例または fragment ファイル一覧
- `notes`: 人間向け補足
- `related`: 参照したい追加ファイル

ファイル名は自由だが、最初の運用では以下を推奨:

- example: `input.toml`
- fragment: `fragment.toml`
- notes: `notes.md`

シミュレータ固有のファイル名を併記してもよい。
たとえば EMSES なら `plasma.toml` を直接置いてもよい。

### `[applicability]`

想定するモデル・用途を表す。
語彙は simulator ごとに増えてよいが、同一 repo 内では揃える。

例:

- `model`
- `geometry`
- `boundary`
- `flow`
- `collisions`
- `photoelectron`
- `magnetized`

### `[recommended]`

Agent が parameter generation する際の補助情報。

推奨フィールド:

- `use_for`
- `vary_first`
- `keep_fixed`
- `avoid_if`
- `clone_from`

### `[stability]`

「この例がどの程度そのまま使えるか」を示す。

推奨フィールド:

- `confidence`: `low`, `medium`, `high`
- `known_good`: `true` / `false`
- `notes`
- `validated_with`

## `constraints/`

`constraints/` には「典型的なよくある失敗」と
「推奨範囲」を集約する。

最小例:

```toml
schema_version = "0.1"

[[constraints]]
id = "cfl-dt-upper-bound"
title = "CFL upper bound for dt"
kind = "numerical"
severity = "error"
summary = "dt must stay below the CFL-like stability threshold"
related_params = ["tmgrid.dt", "tmgrid.nx", "plasma.cv"]
guidance = "Reduce dt first before increasing other parameters"

[[constraints]]
id = "debye-length-resolution"
title = "Debye length resolution guidance"
kind = "physics"
severity = "warning"
summary = "Grid spacing should resolve Debye length"
related_params = ["tmgrid.nx", "plasma.wp", "plasma.te"]
guidance = "Increase resolution or limit plasma density"
```

推奨フィールド:

- `id`
- `title`
- `kind`
- `severity`
- `summary`
- `related_params`
- `guidance`
- `formula`
- `notes`

## Agent の想定読取順序

Agent は次の順序で読むのを推奨する。

1. `simctl/index.toml` で全体像と候補を把握
2. 選んだ entry の `meta.toml` で用途と適用条件を確認
3. `input.toml` / `fragment.toml` などの実ファイルを読む
4. `constraints/*.toml` と `notes.md` を見て危険設定を避ける

## ID と互換性

- `id` は rename しない
- 内容を更新しても `id` は維持する
- 破壊的な意味変更をするときは新しい `id` を作る
- `schema_version` が変わるときは、下位互換性の有無を `index.toml` の説明に書く

## simctl 側の期待

simulator repo 側でこの bundle を提供する場合、
adapter の `knowledge_sources()` は少なくとも次を拾うことを推奨:

- `simctl/index.toml`
- `simctl/**/*.toml`
- `simctl/**/*.md`
- 必要なら `simctl/**/input.*`

これにより `simctl update-refs` 後の `.simctl/knowledge/{simulator}.md`
から Agent が bundle の所在を追いやすくなる。

## 最小導入セット

最初の導入では次で十分:

1. `simctl/index.toml`
2. 2〜5 個の representative examples
3. 各 example の `meta.toml`
4. 1 つ以上の `constraints/*.toml`

fragment は後から足してよい。

## 非目標

この規約は、初期段階では以下を目的にしない。

- 中央集約型データベース
- 厳密な検索言語
- 全 simulator 共通の完全語彙統制
- simctl 本体による自動マージや自動生成の完全実装

まずは「Agent が source repo の知識を自然に使えること」を優先する。
