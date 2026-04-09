Run all quality checks (ruff format, ruff check, mypy, pytest) on the changed files. Report pass/fail for each step. If anything fails, show the error and suggest a fix.

```bash
uv run ruff format --check src/ tests/
uv run ruff check src/ tests/
uv run mypy src/
uv run pytest tests/ -x -q
```
