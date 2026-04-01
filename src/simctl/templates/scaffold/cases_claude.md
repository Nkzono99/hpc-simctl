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

- case は `simctl case new <name> -s <simulator>` で生成する (cases/<sim>/ に自動生成)
- 生成された case.toml や入力テンプレートの編集は自由
- survey 付きは `simctl case new <name> --survey`
- case.toml の編集は自由だが、フォーマットは `simctl-reference` スキルを参照
- テンプレートの Jinja2 変数は case.toml の `[parameters]` から展開される

