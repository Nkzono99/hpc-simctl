# Simulator Cookbook Spec

シミュレーションリポジトリ側で、AI Agent や管理ツールが参照できる
ツール非依存の入力例・設定カタログを提供するための規約。

## 目的

- 典型的な入力例を構造化して提供する
- 用途別プリセットとして再利用可能にする
- パラメータ生成の出発点を Agent に与える
- 部分設定 (fragment) の合成を可能にする
- ツール固有の知識ではなく、simulator 固有の知識として管理する

## 原則

- **ツール非依存**: 特定の管理ツールに依存しない。どの AI Agent やワークフローツールからでも参照できる
- **自己記述的**: cookbook 自体が構造と使い方を説明する (`COOKBOOK.md`)
- **軽量**: 大きな DB ではなく、構造化ディレクトリ + 薄い目録
- **example が主役**: 完全な入力例を中心に、fragment は補助
- **人間可読 + 機械可読**: メタデータは TOML、補足は Markdown

## ディレクトリ構成

```text
repo/
  cookbook/
    COOKBOOK.md              # この cookbook の管理ガイド (Agent 向け)
    index.toml              # 全 entry の目録
    examples/
      electrostatic/
        sheath-basic/
          meta.toml         # entry メタデータ
          input.toml        # 完全な入力ファイル
          notes.md          # 人間向け補足
      electromagnetic/
        alfven-wave/
          meta.toml
          input.toml
    fragments/
      boundary/
        absorbing-open/
          meta.toml
          fragment.toml     # 部分設定
      diagnostics/
        quick-look/
          meta.toml
          fragment.toml
```

## 必須要件

- `cookbook/COOKBOOK.md` は必須
- `cookbook/index.toml` は必須
- 各 example / fragment ディレクトリは `meta.toml` を持つ
- `index.toml` と `meta.toml` は `schema_version` を持つ
- 各 entry は repo 内で安定な `id` を持つ

## `COOKBOOK.md`

cookbook ディレクトリのルートに置く。2 つの役割がある:

1. **この cookbook の概要**: どんな simulator の、どんな入力例が入っているか
2. **管理ガイド**: repo 側の Agent や開発者が entry を追加・更新する手順

後述の「COOKBOOK.md テンプレート」節を参照。

## `index.toml`

bundle 全体の目録。Agent はまずこれを読む。

```toml
[cookbook]
schema_version = "0.1"
software = "MPIEMSES3D"
title = "MPIEMSES3D Cookbook"
description = "Input examples and reusable fragments for MPIEMSES3D"

[[entries]]
id = "electrostatic-sheath-basic"
kind = "example"
path = "examples/electrostatic/sheath-basic"
title = "Basic electrostatic sheath"
summary = "Minimal stable sheath setup for quick testing"
tags = ["electrostatic", "sheath", "1d", "baseline"]
recommended_for = ["sanity-check", "parameter-sweep-base"]

[[entries]]
id = "quick-look-diagnostics"
kind = "fragment"
path = "fragments/diagnostics/quick-look"
title = "Quick-look diagnostics"
summary = "Minimal diagnostics fragment for cheap smoke tests"
tags = ["diagnostics", "smoke-test"]
recommended_for = ["baseline", "debug"]
```

### `[cookbook]`

| フィールド | 必須 | 説明 |
|---|---|---|
| `schema_version` | yes | この仕様のバージョン |
| `software` | yes | 対象ソフトウェア名 |
| `title` | no | cookbook のタイトル |
| `description` | no | 概要 |

### `[[entries]]`

| フィールド | 必須 | 説明 |
|---|---|---|
| `id` | yes | 安定な識別子 (rename しない) |
| `kind` | yes | `example` / `fragment` / `note` |
| `path` | yes | index.toml からの相対パス |
| `title` | yes | 表示名 |
| `summary` | no | 一文の説明 |
| `tags` | no | 検索用タグ |
| `recommended_for` | no | 推奨用途 |

### `kind`

| kind | 説明 |
|---|---|
| `example` | 完全な入力例。Agent の第一候補 |
| `fragment` | 部分設定。example に合成して使う |
| `note` | 追加の説明資料 |

### `recommended_for` 推奨語彙

語彙は自由だが、以下を揃えると横断検索しやすい:

- `sanity-check`
- `baseline`
- `parameter-sweep-base`
- `small-test`
- `debug`
- `production-template`

## `meta.toml`

各 entry ディレクトリに置く。entry の用途と使い方を記述する。

```toml
schema_version = "0.1"
id = "electrostatic-sheath-basic"
kind = "example"
title = "Basic electrostatic sheath"
summary = "Minimal 1D sheath. Stable for moderate density."

[files]
input = ["input.toml"]
notes = ["notes.md"]

[applicability]
model = "electrostatic"
geometry = "1d"
boundary = "absorbing"

[recommended]
use_for = ["baseline", "small-test", "parameter-sweep-base"]
vary_first = ["tmgrid.dt", "tmgrid.nx", "species.0.density"]
keep_fixed = ["boundary.type"]
avoid_if = ["strongly electromagnetic phenomena"]
```

### 必須項目

- `schema_version`
- `id`
- `kind`
- `title`

### `[files]`

| フィールド | 説明 |
|---|---|
| `input` | 完全入力例または fragment ファイル一覧 |
| `notes` | 人間向け補足 |
| `related` | 参照したい追加ファイル |

ファイル名は自由。推奨:
- example: `input.toml` (またはシミュレータ固有名 `plasma.toml` 等)
- fragment: `fragment.toml`
- notes: `notes.md`

### `[applicability]`

想定するモデル・用途。語彙は simulator ごとに自由だが repo 内では揃える。

よく使うフィールド:

- `model`
- `geometry`
- `boundary`
- `flow`
- `collisions`
- `magnetized`

### `[recommended]`

Agent がパラメータ生成に使う補助情報。

| フィールド | 説明 |
|---|---|
| `use_for` | 推奨用途 |
| `vary_first` | 最初に振るべきパラメータ (dot 記法) |
| `keep_fixed` | 固定すべきパラメータ |
| `avoid_if` | この例を使うべきでない状況 |
| `clone_from` | ベースにした他 entry の id |

## Agent の想定読取順序

1. `cookbook/COOKBOOK.md` で cookbook の概要を把握
2. `cookbook/index.toml` で全 entry を一覧し、候補を選ぶ
3. 選んだ entry の `meta.toml` で用途と適用条件を確認
4. `input.toml` / `fragment.toml` の実ファイルを読む
5. `notes.md` で注意事項を確認

## ID と互換性

- `id` は rename しない
- 内容を更新しても `id` は維持する
- 破壊的な意味変更をするときは新しい `id` を作る
- `schema_version` が変わるときは下位互換性の有無を `COOKBOOK.md` に書く

## 最小導入セット

最初の導入では次で十分:

1. `cookbook/COOKBOOK.md`
2. `cookbook/index.toml`
3. 2〜5 個の representative examples
4. 各 example の `meta.toml`

fragment は後から足してよい。

## 非目標

- 中央集約型データベース
- 厳密な検索言語
- 全 simulator 共通の完全語彙統制
- 制約チェック (利用側ツールの責務)
- バリデーションルールの定義

制約・バリデーションは cookbook の外で管理する。
cookbook は「何をどう使うか」だけに集中する。

---

## COOKBOOK.md テンプレート

以下は simulator repo の `cookbook/COOKBOOK.md` に置くテンプレート。
`{...}` はリポジトリに合わせて書き換える。

````markdown
# {Software Name} Cookbook

{Software Name} の入力例・設定フラグメント集。
AI Agent や開発者が入力ファイルを生成する際の出発点として使う。

## 構成

```
cookbook/
  COOKBOOK.md        # このファイル
  index.toml        # 全 entry の目録
  examples/         # 完全な入力例
  fragments/        # 再利用可能な部分設定
```

## 使い方

1. `index.toml` を読んで、目的に合う entry を探す
2. entry の `meta.toml` で用途と適用条件を確認する
3. `input.toml` (または `fragment.toml`) を読む
4. `notes.md` があれば注意事項を確認する
5. 必要に応じて example をコピーし、パラメータを変更して使う

## entry の追加手順

### 1. ディレクトリを作る

example の場合:
```bash
mkdir -p cookbook/examples/{category}/{entry-name}
```

fragment の場合:
```bash
mkdir -p cookbook/fragments/{category}/{entry-name}
```

### 2. meta.toml を書く

```toml
schema_version = "0.1"
id = "{category}-{entry-name}"
kind = "example"  # or "fragment"
title = "{人間向けタイトル}"
summary = "{一文の説明}"

[files]
input = ["{入力ファイル名}"]
notes = ["notes.md"]

[applicability]
# この entry が想定する条件を書く
# model = "..."
# geometry = "..."

[recommended]
use_for = ["baseline"]
vary_first = ["{最初に振るべきパラメータ}"]
```

### 3. 入力ファイルを置く

- example: そのまま実行できる完全な入力ファイルを `input.toml` として置く
  - simulator 固有の名前 ({simulator の入力ファイル名}) でもよい
- fragment: 他の入力に合成して使う部分設定を `fragment.toml` として置く

### 4. notes.md を書く (任意)

- この entry の意図、背景、注意事項を書く
- パラメータの選定理由があれば書く
- 既知の制限があれば書く

### 5. index.toml に登録する

```toml
[[entries]]
id = "{meta.toml の id と一致させる}"
kind = "example"
path = "examples/{category}/{entry-name}"
title = "{meta.toml の title と一致させる}"
summary = "{一文の説明}"
tags = ["{関連するタグ}"]
recommended_for = ["{推奨用途}"]
```

## entry の更新

- `id` は変えない
- 内容を改善するときは `meta.toml` と入力ファイルを直接更新する
- 破壊的な変更 (互換性のないパラメータ変更等) は新しい `id` で別 entry を作る

## 品質基準

- example は **そのまま実行できる** こと
- `meta.toml` の `[recommended].vary_first` には、実際に振って意味のあるパラメータだけを書く
- `tags` は既存 entry と語彙を揃える (`index.toml` の既存タグを確認)
- fragment は **単体では実行できない** ことを `notes.md` に明記する

## タグ一覧

{このリポジトリで使われているタグを列挙する。新しいタグを追加したらここも更新する。}

## 仕様

この cookbook は [Simulator Cookbook Spec](https://github.com/Nkzono99/hpc-simctl/blob/main/docs/simulator-kb-spec.md) に準拠する。
````
