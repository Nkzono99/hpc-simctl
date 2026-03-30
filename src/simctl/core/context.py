"""Project context bundle: single-read summary for AI agents.

Collects project configuration, campaign intent, simulator/launcher info,
run state counts, recent failures, and latest facts into one dictionary
that agents read as their entry point.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from simctl.core.exceptions import SimctlError

logger = logging.getLogger(__name__)


def build_project_context(project_root: Path) -> dict[str, Any]:
    """Build a lightweight context bundle for the current project.

    This is the canonical entry point for AI agents.  Instead of reading
    many files individually, agents call this once to get a structured
    overview of the project state.

    Args:
        project_root: Absolute path to the project root directory.

    Returns:
        JSON-serializable dictionary with project overview.
    """
    ctx: dict[str, Any] = {}

    # -- Project basics --
    ctx["project"] = _load_project_info(project_root)

    # -- Campaign --
    ctx["campaign"] = _load_campaign_info(project_root)

    # -- Simulators & Launchers --
    ctx["simulators"] = _load_simulator_names(project_root)
    ctx["launchers"] = _load_launcher_names(project_root)

    # -- Run statistics --
    ctx["runs"] = _collect_run_stats(project_root)

    # -- Recent failures --
    ctx["recent_failures"] = _collect_recent_failures(project_root)

    # -- Facts --
    ctx["facts"] = _collect_facts_summary(project_root)

    # -- Knowledge index --
    ctx["knowledge"] = _collect_knowledge_paths(project_root)

    # -- Available actions --
    from simctl.core.actions import list_actions

    ctx["available_actions"] = [
        {"name": a.name, "description": a.description} for a in list_actions()
    ]

    return ctx


# ---------------------------------------------------------------------------
# Section builders
# ---------------------------------------------------------------------------


def _load_project_info(root: Path) -> dict[str, Any]:
    try:
        from simctl.core.project import load_project

        proj = load_project(root)
        return {
            "name": proj.name,
            "description": proj.description,
            "root": str(root),
        }
    except SimctlError:
        return {"name": "", "root": str(root)}


def _load_campaign_info(root: Path) -> dict[str, Any]:
    try:
        from simctl.core.campaign import load_campaign

        camp = load_campaign(root)
        if camp is None:
            return {}
        result: dict[str, Any] = {
            "name": camp.name,
            "hypothesis": camp.hypothesis,
            "simulator": camp.simulator,
        }
        if camp.variables:
            result["variables"] = [
                {"name": v.name, "role": v.role, "unit": v.unit} for v in camp.variables
            ]
        if camp.observables:
            result["observables"] = [
                {"name": o.name, "description": o.description} for o in camp.observables
            ]
        return result
    except SimctlError:
        return {}


def _load_simulator_names(root: Path) -> list[str]:
    try:
        from simctl.core.project import load_project

        proj = load_project(root)
        return sorted(proj.simulators.keys())
    except SimctlError:
        return []


def _load_launcher_names(root: Path) -> list[str]:
    try:
        from simctl.core.project import load_project

        proj = load_project(root)
        return sorted(proj.launchers.keys())
    except SimctlError:
        return []


def _collect_run_stats(root: Path) -> dict[str, Any]:
    from simctl.core.state import RunState

    runs_dir = root / "runs"
    if not runs_dir.is_dir():
        return {"total": 0}

    try:
        from simctl.core.discovery import discover_runs
        from simctl.core.manifest import read_manifest

        run_dirs = discover_runs(runs_dir)
        counts: dict[str, int] = {s.value: 0 for s in RunState}
        for rd in run_dirs:
            try:
                m = read_manifest(rd)
                state = m.run.get("status", "unknown")
                counts[state] = counts.get(state, 0) + 1
            except SimctlError:
                counts["unknown"] = counts.get("unknown", 0) + 1

        non_zero = {k: v for k, v in counts.items() if v > 0}
        non_zero["total"] = len(run_dirs)
        return non_zero
    except Exception:
        return {"total": 0}


def _collect_recent_failures(root: Path, *, limit: int = 10) -> list[dict[str, str]]:
    runs_dir = root / "runs"
    if not runs_dir.is_dir():
        return []

    try:
        from simctl.core.discovery import discover_runs
        from simctl.core.manifest import read_manifest

        failures: list[dict[str, str]] = []
        for rd in discover_runs(runs_dir):
            try:
                m = read_manifest(rd)
                if m.run.get("status") == "failed":
                    failures.append(
                        {
                            "run_id": m.run.get("id", ""),
                            "reason": m.run.get("failure_reason", ""),
                            "display_name": m.run.get("display_name", ""),
                        }
                    )
            except SimctlError:
                continue
        return failures[:limit]
    except Exception:
        return []


def _collect_facts_summary(root: Path, *, limit: int = 20) -> list[dict[str, Any]]:
    try:
        from simctl.core.knowledge import load_facts

        facts = load_facts(root)
        return [
            {
                "id": f.id,
                "claim": f.claim,
                "confidence": f.confidence,
                "fact_type": getattr(f, "fact_type", ""),
                "simulator": getattr(f, "simulator", ""),
            }
            for f in facts[:limit]
        ]
    except Exception:
        return []


def _collect_knowledge_paths(root: Path) -> dict[str, Any]:
    result: dict[str, Any] = {}

    refs_dir = root / "refs"
    if refs_dir.is_dir():
        result["refs_dir"] = str(refs_dir)
        result["refs_repos"] = [p.name for p in refs_dir.iterdir() if p.is_dir()]

    knowledge_dir = root / ".simctl" / "knowledge"
    if knowledge_dir.is_dir():
        result["knowledge_dir"] = str(knowledge_dir)

    insights_dir = root / ".simctl" / "insights"
    if insights_dir.is_dir():
        insight_files = list(insights_dir.glob("*.md"))
        result["insights_count"] = len(insight_files)

    facts_file = root / ".simctl" / "facts.toml"
    if facts_file.is_file():
        result["facts_file"] = str(facts_file)

    return result
