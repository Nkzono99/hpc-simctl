"""Tests for agent-facing action helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import tomli_w

from simctl.core.actions import (
    ActionStatus,
    add_fact,
    collect_survey,
    retry_run,
    submit_run,
    summarize_run,
)
from simctl.core.actions import (
    create_run as create_run_action,
)
from simctl.core.knowledge import load_facts


def _write_manifest(run_dir: Path, data: dict[str, Any]) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    with open(run_dir / "manifest.toml", "wb") as f:
        tomli_w.dump(data, f)


def _create_project_with_case(project_root: Path) -> None:
    (project_root / "simproject.toml").write_text(
        '[project]\nname = "test-project"\n',
        encoding="utf-8",
    )
    (project_root / "simulators.toml").write_text(
        "[simulators.test_sim]\n"
        'adapter = "generic"\n'
        'executable = "echo"\n'
        'resolver_mode = "package"\n',
        encoding="utf-8",
    )
    (project_root / "launchers.toml").write_text(
        "[launchers.slurm_srun]\n"
        'kind = "srun"\n'
        'command = "srun"\n'
        "use_slurm_ntasks = true\n",
        encoding="utf-8",
    )
    case_dir = project_root / "cases" / "my_case"
    case_dir.mkdir(parents=True)
    (project_root / "runs").mkdir()
    (case_dir / "case.toml").write_text(
        "[case]\n"
        'name = "my_case"\n'
        'simulator = "test_sim"\n'
        'launcher = "slurm_srun"\n'
        "\n"
        "[job]\n"
        'partition = "debug"\n'
        "nodes = 1\n"
        "ntasks = 2\n"
        'walltime = "00:10:00"\n'
        "\n"
        "[params]\n"
        "nx = 64\n"
        "ny = 64\n",
        encoding="utf-8",
    )


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


def test_create_run_action_generates_full_run_artifacts(tmp_path: Path) -> None:
    _create_project_with_case(tmp_path)

    result = create_run_action(
        tmp_path,
        "my_case",
        params={"nx": 128},
        display_name="custom-display",
    )

    assert result.status is ActionStatus.SUCCESS
    run_dir = Path(result.data["run_dir"])
    assert (run_dir / "manifest.toml").exists()
    assert (run_dir / "submit" / "job.sh").exists()
    assert (run_dir / "input" / "params.json").exists()

    with open(run_dir / "input" / "params.json", encoding="utf-8") as f:
        params = json.load(f)
    assert params["nx"] == 128
    assert params["ny"] == 64


def test_collect_survey_writes_aggregate_artifacts(tmp_path: Path) -> None:
    run_dir = tmp_path / "R20260330-0001"
    _write_manifest(
        run_dir,
        {
            "run": {
                "id": "R20260330-0001",
                "status": "completed",
                "display_name": "baseline",
            }
        },
    )
    (run_dir / "analysis").mkdir(parents=True, exist_ok=True)
    with open(run_dir / "analysis" / "summary.json", "w", encoding="utf-8") as f:
        json.dump({"energy": 1.0}, f)

    result = collect_survey(tmp_path)

    assert result.status is ActionStatus.SUCCESS
    assert Path(result.data["csv_path"]).exists()
    assert Path(result.data["json_path"]).exists()
    assert Path(result.data["report_path"]).exists()


def test_collect_survey_auto_summarizes_completed_runs(tmp_path: Path) -> None:
    run_dir = tmp_path / "R20260330-0001"
    _write_manifest(
        run_dir,
        {
            "run": {
                "id": "R20260330-0001",
                "status": "completed",
            },
            "simulator": {
                "name": "test_sim",
                "adapter": "test_adapter",
            },
        },
    )

    mock_adapter = MagicMock()
    mock_adapter.summarize.return_value = {"energy": 2.5}
    mock_adapter_cls = MagicMock(return_value=mock_adapter)

    with patch("simctl.core.analysis.get_adapter", return_value=mock_adapter_cls):
        result = collect_survey(tmp_path)

    assert result.status is ActionStatus.SUCCESS
    assert result.data["generated_summaries"] == 1
    assert (run_dir / "analysis" / "summary.json").exists()


def test_summarize_run_writes_summary_json(tmp_path: Path) -> None:
    run_dir = tmp_path / "R20260330-0001"
    run_dir.mkdir(parents=True, exist_ok=True)
    _write_manifest(
        run_dir,
        {
            "run": {
                "id": "R20260330-0001",
                "status": "completed",
            },
            "simulator": {
                "name": "test_sim",
                "adapter": "test_adapter",
            },
        },
    )

    mock_adapter = MagicMock()
    mock_adapter.summarize.return_value = {"energy": 42.0}
    mock_adapter_cls = MagicMock(return_value=mock_adapter)

    with patch("simctl.core.analysis.get_adapter", return_value=mock_adapter_cls):
        result = summarize_run(run_dir)

    assert result.status is ActionStatus.SUCCESS
    assert (run_dir / "analysis" / "summary.json").exists()
    with open(run_dir / "analysis" / "summary.json", encoding="utf-8") as f:
        data = json.load(f)
    assert data["energy"] == 42.0


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


def test_submit_run_updates_manifest_and_state_file(tmp_path: Path) -> None:
    run_dir = tmp_path / "R20260330-0001"
    _write_manifest(
        run_dir,
        {
            "run": {
                "id": "R20260330-0001",
                "status": "created",
            },
            "job": {
                "partition": "debug",
            },
        },
    )
    (run_dir / "submit").mkdir(parents=True, exist_ok=True)
    (run_dir / "submit" / "job.sh").write_text(
        "#!/bin/bash\n#SBATCH --job-name=test\necho hello\n",
        encoding="utf-8",
    )
    (run_dir / "input").mkdir(parents=True, exist_ok=True)
    (run_dir / "input" / "params.json").write_text("{}", encoding="utf-8")

    with patch("simctl.slurm.submit.sbatch_submit", return_value="12345"):
        result = submit_run(run_dir)

    assert result.status is ActionStatus.SUCCESS
    assert result.data["job_id"] == "12345"
    assert (run_dir / "status" / "state.json").exists()


def test_submit_run_rejects_empty_input_dir(tmp_path: Path) -> None:
    run_dir = tmp_path / "R20260330-0001"
    _write_manifest(
        run_dir,
        {
            "run": {
                "id": "R20260330-0001",
                "status": "created",
            }
        },
    )
    (run_dir / "submit").mkdir(parents=True, exist_ok=True)
    (run_dir / "submit" / "job.sh").write_text(
        "#!/bin/bash\n#SBATCH --job-name=test\necho hello\n",
        encoding="utf-8",
    )
    (run_dir / "input").mkdir(parents=True, exist_ok=True)

    result = submit_run(run_dir)

    assert result.status is ActionStatus.PRECONDITION_FAILED
    assert "input/" in result.message
