"""Tests for retry suggestion helpers."""

from __future__ import annotations

from pathlib import Path

import tomli_w

from simctl.core.retry import get_attempt_count, suggest_retry_for_run


def _create_failed_run(
    run_dir: Path,
    *,
    failure_reason: str = "timeout",
    attempts: list[dict[str, str]] | None = None,
    attempt: int | None = None,
) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, object] = {
        "run": {
            "id": run_dir.name,
            "status": "failed",
            "failure_reason": failure_reason,
        },
        "job": {},
    }
    job = manifest["job"]
    assert isinstance(job, dict)
    if attempts is not None:
        job["attempts"] = attempts
    if attempt is not None:
        job["attempt"] = attempt

    with open(run_dir / "manifest.toml", "wb") as f:
        tomli_w.dump(manifest, f)


def test_get_attempt_count_prefers_attempts_history() -> None:
    count = get_attempt_count(
        {
            "attempt": 1,
            "attempts": [
                {"attempt": "1"},
                {"attempt": "2"},
            ],
        }
    )
    assert count == 2


def test_suggest_retry_for_run_respects_max_attempts_from_attempts_list(
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / "R20260330-0001"
    _create_failed_run(
        run_dir,
        attempts=[
            {"attempt": "1"},
            {"attempt": "2"},
            {"attempt": "3"},
        ],
    )

    suggestions = suggest_retry_for_run(run_dir)

    assert len(suggestions) == 1
    assert suggestions[0].action == "show_log"
    assert "Max attempts" in suggestions[0].rationale

