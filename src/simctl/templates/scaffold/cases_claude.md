# cases/ ディレクトリ

ここには simulation case の定義を置く。

## 構造

```
cases/<simulator>/<case-name>/
  case.toml          # パラメータ定義
  survey.toml        # (optional) パラメータ掃引定義
  templates/         # 入力テンプレート
```

## ルール

- case は `simctl new <name>` で生成する (手書きしない)
- survey 付きは `simctl new <name> --survey`
- case.toml の編集は自由だが、フォーマットは `simctl-reference` スキルを参照
- テンプレートの Jinja2 変数は case.toml の `[parameters]` から展開される
