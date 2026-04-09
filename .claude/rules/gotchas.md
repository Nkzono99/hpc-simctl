# Gotchas (よくあるミス)

## Circular imports

`harness/builder.py` が `cli/init.py` を import するとループする。
harness は templates と adapters.registry にだけ依存する。
cli/init.py が harness/builder を import する方向は OK。

## `_write_if_missing` のセマンティクス

`_write_if_missing` は **ファイルが存在しなければ書く**。
既存ファイルは一切上書きしない。テストでファイル上書きを期待すると失敗する。

## load_static vs get_jinja_env

- `load_static("path")` — そのまま返す (変数展開なし)
- `get_jinja_env().get_template("path")` — Jinja2 レンダリングが必要な場合

テンプレートに `{{` が含まれないなら `load_static` で十分。

## tomllib vs tomli

Python 3.11+ は `tomllib` が標準。3.10 では `tomli` を使う。
ファイル先頭の `sys.version_info` 分岐を踏襲すること。

## settings.json と settings.local.json

- `.claude/settings.json` — Git 管理。チーム共有の permissions / model
- `.claude/settings.local.json` — .gitignore 済。個人の許可パターン

local が team を **マージ上書き** する。同じキーを両方に書くと local が勝つ。

## Adapter の pip_packages / doc_repos

Adapter が返すリストは **累積** (重複排除) される。
同じ package を複数 adapter が返しても 1 回だけ install される。

## ハーネス lock

`harness.lock` は **テンプレートの hash** を記録する。
ファイルの hash ではない。比較は「disk hash == lock hash」→ unedited。
lock がない旧プロジェクトでは全ファイルが "edited" 扱いになる。
