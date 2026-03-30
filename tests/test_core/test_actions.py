"""Tests for agent-facing action helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import tomli_w

from simctl.core.actions import ActionStatus, add_fact, collect_survey, retry_run
from simctl.core.knowledge import load_facts


def _write_manifest(run_dir: Path, data: dict[str, Any]) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    with open(run_dir / "manifest.toml", "wb") as f:
        tomli_w.dump(data, f)


def test_collect_survey_requires_at_least_one_completed_run(tmp_path: Path) -> None:
    run_dir = tmp_path / "R20260330-0001"
    _write_manifest(
        run_dir,
        {
            "run": {
                "id": "R20260330-0001",
                "status": "failed",
            }
        },
    )

    result = collect_survey(tmp_path)

    assert result.status is ActionStatus.PRECONDITION_FAILED
    assert "No completed runs" in result.message


def test_retry_run_blocks_exit_error_without_log_review(tmp_path: Path) -> None:
    run_dir = tmp_path / "R20260330-0001"
    _write_manifest(
        run_dir,
        {
            "run": {
                "id": "R20260330-0001",
                "status": "failed",
                "failure_reason": "exit_error",
            },
            "job": {
                "attempt": 1,
            },
        },
    )

    result = retry_run(run_dir)

    assert result.status is ActionStatus.PRECONDITION_FAILED
    assert "requires log review" in result.message


def test_retry_run_respects_max_attempts(tmp_path: Path) -> None:
    run_dir = tmp_path / "R20260330-0001"
    _write_manifest(
        run_dir,
        {
            "run": {
                "id": "R20260330-0001",
                "status": "failed",
                "failure_reason": "timeout",
            },
            "job": {
                "attempts": [
                    {"attempt": "1"},
                    {"attempt": "2"},
                    {"attempt": "3"},
                ],
            },
        },
    )

    result = retry_run(run_dir, adjustments={"walltime_factor": 1.5})

    assert result.status is ActionStatus.PRECONDITION_FAILED
    assert "Max attempts" in result.message


def test_add_fact_supports_superseding_fact(tmp_path: Path) -> None:
    first = add_fact(tmp_path, claim="initial fact")
    second = add_fact(tmp_path, claim="revised fact", supersedes="f001")

    assert first.status is ActionStatus.SUCCESS
    assert second.status is ActionStatus.SUCCESS

    facts = load_facts(tmp_path)
    assert [fact.id for fact in facts] == ["f001", "f002"]
    assert facts[1].supersedes == "f001"

