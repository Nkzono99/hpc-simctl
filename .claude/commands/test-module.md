Run tests for a specific module. Usage: `/test-module <module_name>`

Determine the test file path from the module name:
- `core/project` → `tests/test_core/test_project.py`
- `cli/init` → `tests/test_cli/test_init.py`
- `adapters/emses` → `tests/test_adapters/test_emses.py`

Run with verbose output:
```bash
uv run pytest tests/test_<package>/test_<module>.py -v
```

If tests fail, read the source and test files, diagnose the issue, and suggest a fix.
