"""Tests for simctl knowledge CLI commands."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from simctl.cli.main import app
from simctl.core.knowledge import load_facts, query_facts

runner = CliRunner()


def _create_project(tmp_path: Path) -> Path:
    (tmp_path / "simproject.toml").write_text('[project]\nname = "test-project"\n')
    return tmp_path


def test_add_fact_supports_legacy_scope_and_evidence_options(tmp_path: Path) -> None:
    project_root = _create_project(tmp_path)

    with patch("simctl.cli.knowledge.Path.cwd", return_value=project_root):
        result = runner.invoke(
            app,
            [
                "knowledge",
                "add-fact",
                "dt must stay below the CFL limit",
                "--scope",
                "emses",
                "--evidence",
                "run_observation",
                "--confidence",
                "high",
                "--run",
                "R20260330-0001",
            ],
        )

    assert result.exit_code == 0
    assert "Saved fact [f001]" in result.output

    facts = load_facts(project_root)
    assert len(facts) == 1
    assert facts[0].scope_text == "emses"
    assert facts[0].evidence_kind == "run_observation"
    assert facts[0].source_run == "R20260330-0001"


def test_add_fact_supports_structured_fields_and_supersedes(tmp_path: Path) -> None:
    project_root = _create_project(tmp_path)

    with patch("simctl.cli.knowledge.Path.cwd", return_value=project_root):
        first = runner.invoke(
            app,
            ["knowledge", "add-fact", "initial observation"],
        )
        second = runner.invoke(
            app,
            [
                "knowledge",
                "add-fact",
                "refined constraint",
                "--type",
                "constraint",
                "--simulator",
                "emses",
                "--scope-case",
                "baseline",
                "--scope-text",
                "stable grid setup",
                "--param-name",
                "tmgrid.dt",
                "--evidence-kind",
                "run_observation",
                "--evidence-ref",
                "run:R20260330-0002",
                "--supersedes",
                "f001",
            ],
        )

    assert first.exit_code == 0
    assert second.exit_code == 0
    assert "Saved fact [f002]" in second.output

    facts = load_facts(project_root)
    assert len(facts) == 2
    assert facts[1].fact_type == "constraint"
    assert facts[1].simulator == "emses"
    assert facts[1].scope_case == "baseline"
    assert facts[1].scope_text == "stable grid setup"
    assert facts[1].param_name == "tmgrid.dt"
    assert facts[1].evidence_ref == "run:R20260330-0002"
    assert facts[1].supersedes == "f001"

    visible = query_facts(project_root)
    assert [fact.id for fact in visible] == ["f002"]
