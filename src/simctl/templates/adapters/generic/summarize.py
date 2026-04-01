from __future__ import annotations

from pathlib import Path
from typing import Any


def summarize(run_dir: Path, base_summary: dict[str, Any]) -> dict[str, Any]:
    """Extend the adapter summary for one run.

    Edit this file to parse simulator-specific outputs from ``work/`` and to
    save plots under ``analysis/figures/``.
    """

    summary = dict(base_summary)

    work_dir = run_dir / "work"
    summary["work_file_count"] = sum(1 for path in work_dir.rglob("*") if path.is_file())

    return summary
