"""Tests for project context bundles exposed to AI agents."""

from __future__ import annotations

from pathlib import Path

import tomli_w

from simctl.core.context import build_project_context


def _write_toml(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        tomli_w.dump(data, f)


def test_context_includes_knowledge_integration_details(tmp_path: Path) -> None:
    _write_toml(
        tmp_path / "simproject.toml",
        {
            "project": {"name": "test-project"},
            "knowledge": {
                "enabled": True,
                "mount_dir": "refs/knowledge",
                "derived_dir": ".simctl/knowledge",
                "sources": [
                    {
                        "name": "shared-kb",
                        "type": "path",
                        "kind": "profiles",
                        "path": "../shared-kb",
                        "mount": "refs/knowledge/shared-kb",
                        "profiles": ["common"],
                    },
                    {
                        "name": "other-project",
                        "type": "path",
                        "kind": "project",
                        "path": "../other-project",
                    }
                ],
            },
        },
    )

    mounted_kb = tmp_path / "refs" / "knowledge" / "shared-kb"
    (mounted_kb / "profiles").mkdir(parents=True)
    (mounted_kb / "profiles" / "common.md").write_text("# Common\n", encoding="utf-8")

    imports_path = tmp_path / ".simctl" / "knowledge" / "enabled" / "imports.md"
    imports_path.parent.mkdir(parents=True, exist_ok=True)
    imports_path.write_text("@refs/knowledge/shared-kb/profiles/common.md\n")

    insight_path = tmp_path / ".simctl" / "insights" / "result_note.md"
    insight_path.parent.mkdir(parents=True, exist_ok=True)
    insight_path.write_text(
        "---\n"
        "type: result\n"
        "simulator: emses\n"
        "created: 2026-04-01\n"
        "---\n\n"
        "Survey summary.\n",
        encoding="utf-8",
    )

    other_project = tmp_path.parent / "other-project"
    other_project.mkdir(parents=True, exist_ok=True)

    _write_toml(
        tmp_path / ".simctl" / "facts.toml",
        {
            "facts": [
                {
                    "id": "f001",
                    "claim": "initial fact",
                    "fact_type": "observation",
                    "confidence": "low",
                },
                {
                    "id": "f002",
                    "claim": "refined fact",
                    "fact_type": "constraint",
                    "confidence": "high",
                    "supersedes": "f001",
                    "source_run": "R20260401-0001",
                    "evidence_ref": "run:R20260401-0001",
                },
            ]
        },
    )

    ctx = build_project_context(tmp_path)

    assert ctx["project"]["name"] == "test-project"
    assert [fact["id"] for fact in ctx["facts"]] == ["f002"]
    assert ctx["facts"][0]["source_run"] == "R20260401-0001"

    knowledge = ctx["knowledge"]
    assert knowledge["imports_ready"] is True
    assert knowledge["knowledge_enabled"] is True
    assert knowledge["insights_count"] == 1
    assert knowledge["recent_insights"][0]["name"] == "result_note"
    assert len(knowledge["external_knowledge"]) == 2
    assert knowledge["external_knowledge"][0]["kind"] == "project"
    shared = next(
        source
        for source in knowledge["knowledge_sources"]
        if source["name"] == "shared-kb"
    )
    assert shared["kind"] == "profiles"
    assert shared["available"] is True
    assert shared["profiles_available"] == ["common"]
    other = next(
        source
        for source in knowledge["knowledge_sources"]
        if source["name"] == "other-project"
    )
    assert other["kind"] == "project"

    actions = {action["name"]: action for action in ctx["available_actions"]}
    assert actions["submit_run"]["required_params"] == ["run_dir"]
    assert actions["submit_run"]["preconditions"] == [
        "run state == created",
        "job.sh exists",
    ]
    assert actions["archive_run"]["destructive"] is True
    assert actions["purge_work"]["state_change"] == "archived -> purged"
    assert actions["archive_run"]["requires_confirmation"] is True
    assert actions["submit_run"]["risk_level"] == "high"
    assert "confirmation_conditions" in actions["retry_run"]
    assert actions["save_insight"]["required_params"] == [
        "project_root",
        "name",
        "content",
    ]


def test_context_reports_diagnostics_for_broken_sections(tmp_path: Path) -> None:
    _write_toml(
        tmp_path / "simproject.toml",
        {
            "project": {"name": "broken-project"},
        },
    )
    facts_path = tmp_path / ".simctl" / "facts.toml"
    facts_path.parent.mkdir(parents=True, exist_ok=True)
    facts_path.write_text("not valid toml", encoding="utf-8")

    ctx = build_project_context(tmp_path)

    assert ctx["status"] == "degraded"
    assert ctx["facts"] == []
    assert ctx["section_status"]["facts"] == "error"
    assert any(
        diagnostic["section"] == "facts" for diagnostic in ctx["diagnostics"]
    )
