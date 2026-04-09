---
name: test-module
description: "Run tests for a specific module. Usage: /test-module <module_name>"
---

# モジュール単体テスト実行

引数からテストファイルパスを決定して実行する。

## パス変換ルール

- `core/project` → `tests/test_core/test_project.py`
- `cli/init` → `tests/test_cli/test_init.py`
- `adapters/emses` → `tests/test_adapters/test_emses.py`

```bash
uv run pytest tests/test_<package>/test_<module>.py -v
```

テストが失敗した場合、ソースとテストファイルを読んで原因を診断し、修正案を提示する。
