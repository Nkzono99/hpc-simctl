"""Action registry: normalized execution interface for AI agents.

Provides a fixed set of named actions with explicit input schemas,
preconditions, and structured results.  Unlike the CLI (designed for humans),
the action registry is designed for programmatic consumption where inputs
and outputs are typed dictionaries.

Each action wraps existing core functions -- no new domain logic lives here.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from simctl.core.exceptions import SimctlError
from simctl.core.state import RunState

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


class ActionStatus(str, Enum):
    """Outcome of an action execution."""

    SUCCESS = "success"
    FAILED = "failed"
    PRECONDITION_FAILED = "precondition_failed"
    ERROR = "error"


@dataclass
class ActionResult:
    """Structured result returned by every action.

    Attributes:
        action: Name of the executed action.
        status: Outcome status.
        message: Human-readable summary.
        data: Arbitrary result payload (action-specific).
        state_before: Run state before execution (if applicable).
        state_after: Run state after execution (if applicable).
    """

    action: str
    status: ActionStatus
    message: str = ""
    data: dict[str, Any] = field(default_factory=dict)
    state_before: str = ""
    state_after: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-friendly dictionary."""
        d: dict[str, Any] = {
            "action": self.action,
            "status": self.status.value,
            "message": self.message,
        }
        if self.data:
            d["data"] = self.data
        if self.state_before:
            d["state_before"] = self.state_before
        if self.state_after:
            d["state_after"] = self.state_after
        return d


# ---------------------------------------------------------------------------
# Action specifications (metadata for agents)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ActionSpec:
    """Machine-readable specification for a single action.

    Attributes:
        name: Action identifier (e.g. ``"create_run"``).
        description: One-line summary.
        required_params: Required input parameter names.
        optional_params: Optional input parameter names.
        preconditions: Human-readable preconditions list.
        state_change: Expected state transition (e.g. ``"created -> submitted"``).
        destructive: Whether the action is hard to reverse.
    """

    name: str
    description: str
    required_params: tuple[str, ...] = ()
    optional_params: tuple[str, ...] = ()
    preconditions: tuple[str, ...] = ()
    state_change: str = ""
    destructive: bool = False


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

ACTION_SPECS: dict[str, ActionSpec] = {
    "create_run": ActionSpec(
        name="create_run",
        description="Create a new run directory from a case.",
        required_params=("project_root", "case_name"),
        optional_params=("dest_dir", "display_name", "params"),
        preconditions=("project loaded", "case exists"),
        state_change="-> created",
    ),
    "submit_run": ActionSpec(
        name="submit_run",
        description="Submit a run to Slurm via sbatch.",
        required_params=("run_dir",),
        optional_params=("queue_name",),
        preconditions=("run state == created", "job.sh exists"),
        state_change="created -> submitted",
    ),
    "sync_run": ActionSpec(
        name="sync_run",
        description="Synchronize run state with Slurm.",
        required_params=("run_dir",),
        preconditions=("run state in {submitted, running}", "job_id recorded"),
        state_change="submitted/running -> completed/failed/cancelled",
    ),
    "show_log": ActionSpec(
        name="show_log",
        description="Read latest job stdout and return tail lines.",
        required_params=("run_dir",),
        optional_params=("lines",),
        preconditions=("run has been submitted at least once",),
    ),
    "summarize_run": ActionSpec(
        name="summarize_run",
        description="Generate analysis summary for a completed run.",
        required_params=("run_dir",),
        preconditions=("run state == completed",),
    ),
    "collect_survey": ActionSpec(
        name="collect_survey",
        description="Aggregate results across all runs in a survey.",
        required_params=("survey_dir",),
        preconditions=("survey directory contains completed runs",),
    ),
    "retry_run": ActionSpec(
        name="retry_run",
        description="Resubmit a failed run, optionally adjusting parameters.",
        required_params=("run_dir",),
        optional_params=("adjustments",),
        preconditions=("run state == failed",),
        state_change="failed -> submitted (new attempt)",
    ),
    "archive_run": ActionSpec(
        name="archive_run",
        description="Archive a completed run (compress work directory).",
        required_params=("run_dir",),
        preconditions=("run state == completed",),
        state_change="completed -> archived",
        destructive=True,
    ),
    "add_fact": ActionSpec(
        name="add_fact",
        description="Record a structured knowledge fact.",
        required_params=("claim",),
        optional_params=(
            "fact_type",
            "simulator",
            "scope_case",
            "scope_text",
            "param_name",
            "confidence",
            "source_run",
            "evidence_kind",
            "evidence_ref",
            "tags",
        ),
        preconditions=("project loaded",),
    ),
}


def list_actions() -> list[ActionSpec]:
    """Return all registered action specifications."""
    return list(ACTION_SPECS.values())


def get_action_spec(name: str) -> ActionSpec | None:
    """Look up an action spec by name."""
    return ACTION_SPECS.get(name)


# ---------------------------------------------------------------------------
# Precondition helpers
# ---------------------------------------------------------------------------


def _require_state(run_dir: Path, *allowed: RunState) -> tuple[str, str | None]:
    """Read manifest and check run state.

    Returns:
        (current_state_value, error_message_or_None)
    """
    from simctl.core.manifest import read_manifest

    manifest = read_manifest(run_dir)
    state_str = manifest.run.get("status", "")
    try:
        state = RunState(state_str)
    except ValueError:
        return state_str, f"Unknown run state: {state_str!r}"

    if state not in allowed:
        allowed_str = ", ".join(s.value for s in allowed)
        return state_str, f"Run state is {state_str!r}, requires one of: {allowed_str}"

    return state_str, None


def _precondition_fail(action: str, message: str) -> ActionResult:
    return ActionResult(
        action=action,
        status=ActionStatus.PRECONDITION_FAILED,
        message=message,
    )


def _error(action: str, message: str) -> ActionResult:
    return ActionResult(
        action=action,
        status=ActionStatus.ERROR,
        message=message,
    )


# ---------------------------------------------------------------------------
# Action implementations
# ---------------------------------------------------------------------------


def create_run(
    project_root: Path,
    case_name: str,
    *,
    dest_dir: Path | None = None,
    display_name: str = "",
    params: dict[str, Any] | None = None,
) -> ActionResult:
    """Create a new run directory from a case definition."""
    from simctl.core.discovery import collect_existing_run_ids
    from simctl.core.manifest import ManifestData, write_manifest
    from simctl.core.run import create_run as _create_run

    try:
        runs_dir = dest_dir or (project_root / "runs" / case_name)
        runs_dir.mkdir(parents=True, exist_ok=True)

        existing_ids = collect_existing_run_ids(project_root / "runs")
        info = _create_run(
            parent_dir=runs_dir,
            existing_ids=existing_ids,
            display_name=display_name,
            params=params,
        )

        # Write initial manifest
        manifest = ManifestData(
            run={
                "id": info.run_id,
                "status": RunState.CREATED.value,
                "created_at": info.created_at,
                "display_name": info.display_name,
            },
            origin={"case": case_name},
        )
        write_manifest(info.run_dir, manifest)

        return ActionResult(
            action="create_run",
            status=ActionStatus.SUCCESS,
            message=f"Created run {info.run_id}",
            data={
                "run_id": info.run_id,
                "run_dir": str(info.run_dir),
                "display_name": info.display_name,
            },
            state_after=RunState.CREATED.value,
        )
    except SimctlError as e:
        return _error("create_run", str(e))


def submit_run(
    run_dir: Path,
    *,
    queue_name: str = "",
) -> ActionResult:
    """Submit a run to Slurm via sbatch."""
    from simctl.core.manifest import read_manifest, update_manifest
    from simctl.slurm.submit import SlurmSubmitError, sbatch_submit

    state_str, err = _require_state(run_dir, RunState.CREATED)
    if err:
        return _precondition_fail("submit_run", err)

    job_script = run_dir / "submit" / "job.sh"
    if not job_script.exists():
        return _precondition_fail("submit_run", f"Job script not found: {job_script}")

    work_dir = run_dir / "work"
    work_dir.mkdir(exist_ok=True)

    extra_args: list[str] = []
    if queue_name:
        extra_args.append(f"--partition={queue_name}")

    try:
        job_id = sbatch_submit(job_script, work_dir, extra_args=extra_args)
    except (SlurmSubmitError, FileNotFoundError, RuntimeError) as e:
        return _error("submit_run", f"sbatch failed: {e}")

    # Update manifest
    now = datetime.now(tz=timezone.utc).isoformat(timespec="seconds")
    manifest = read_manifest(run_dir)
    attempt = manifest.job.get("attempt", 0) + 1
    update_manifest(
        run_dir,
        {
            "run": {"status": RunState.SUBMITTED.value},
            "job": {
                "job_id": job_id,
                "submitted_at": now,
                "attempt": attempt,
                "queue": queue_name or manifest.job.get("queue", ""),
            },
        },
    )

    return ActionResult(
        action="submit_run",
        status=ActionStatus.SUCCESS,
        message=f"Submitted job {job_id} (attempt {attempt})",
        data={"job_id": job_id, "attempt": attempt},
        state_before=state_str,
        state_after=RunState.SUBMITTED.value,
    )


def sync_run(run_dir: Path) -> ActionResult:
    """Synchronize run state with Slurm."""
    from simctl.core.manifest import read_manifest
    from simctl.core.state import update_state
    from simctl.slurm.query import SlurmQueryError, query_job_status

    state_str, err = _require_state(run_dir, RunState.SUBMITTED, RunState.RUNNING)
    if err:
        return _precondition_fail("sync_run", err)

    manifest = read_manifest(run_dir)
    job_id = manifest.job.get("job_id", "")
    if not job_id:
        return _precondition_fail("sync_run", "No job_id recorded in manifest")

    try:
        job_status = query_job_status(job_id)
    except (SlurmQueryError, RuntimeError) as e:
        return _error("sync_run", f"Slurm query failed: {e}")

    new_state = job_status.run_state
    if new_state.value == state_str:
        return ActionResult(
            action="sync_run",
            status=ActionStatus.SUCCESS,
            message=f"State unchanged: {state_str}",
            data={"slurm_state": job_status.slurm_state},
            state_before=state_str,
            state_after=state_str,
        )

    try:
        update_state(
            run_dir,
            new_state,
            reconcile=True,
            reason=job_status.failure_reason,
            slurm_state=job_status.slurm_state,
        )
    except SimctlError as e:
        return _error("sync_run", f"State update failed: {e}")

    return ActionResult(
        action="sync_run",
        status=ActionStatus.SUCCESS,
        message=f"State: {state_str} -> {new_state.value}",
        data={
            "slurm_state": job_status.slurm_state,
            "failure_reason": job_status.failure_reason,
            "exit_code": job_status.exit_code,
        },
        state_before=state_str,
        state_after=new_state.value,
    )


def show_log(run_dir: Path, *, lines: int = 50) -> ActionResult:
    """Read the latest job stdout log."""
    # Look for common log file patterns
    work_dir = run_dir / "work"
    log_candidates = [
        *sorted(work_dir.glob("slurm-*.out"), reverse=True),
        *sorted(work_dir.glob("*.log"), reverse=True),
        *sorted(work_dir.glob("*.out"), reverse=True),
    ]

    if not log_candidates:
        return _precondition_fail("show_log", "No log files found in work/")

    log_file = log_candidates[0]
    try:
        all_lines = log_file.read_text().splitlines()
        tail = all_lines[-lines:] if len(all_lines) > lines else all_lines
    except OSError as e:
        return _error("show_log", f"Failed to read log: {e}")

    return ActionResult(
        action="show_log",
        status=ActionStatus.SUCCESS,
        message=f"Last {len(tail)} lines from {log_file.name}",
        data={
            "log_file": str(log_file),
            "total_lines": len(all_lines),
            "lines": tail,
        },
    )


def summarize_run(run_dir: Path) -> ActionResult:
    """Generate an analysis summary for a completed run."""
    _state_str, err = _require_state(run_dir, RunState.COMPLETED)
    if err:
        return _precondition_fail("summarize_run", err)

    from simctl.core.manifest import read_manifest

    manifest = read_manifest(run_dir)
    sim_name = manifest.simulator.get("name", "unknown")

    # Delegate to adapter if available
    try:
        from simctl.adapters.registry import get as get_adapter_cls

        adapter_cls = get_adapter_cls(sim_name)
        if adapter_cls is not None:
            adapter = adapter_cls()
            summary = adapter.summarize(run_dir)
            return ActionResult(
                action="summarize_run",
                status=ActionStatus.SUCCESS,
                message=f"Summary generated via {sim_name} adapter",
                data={"summary": summary, "simulator": sim_name},
            )
    except (ImportError, SimctlError):
        pass

    # Fallback: list output files
    analysis_dir = run_dir / "analysis"
    work_dir = run_dir / "work"
    outputs = (
        [str(p.name) for p in work_dir.iterdir() if p.is_file()]
        if work_dir.is_dir()
        else []
    )

    return ActionResult(
        action="summarize_run",
        status=ActionStatus.SUCCESS,
        message="Basic summary (no adapter)",
        data={
            "simulator": sim_name,
            "work_files": outputs[:50],
            "has_analysis": analysis_dir.is_dir() and any(analysis_dir.iterdir()),
        },
    )


def collect_survey(survey_dir: Path) -> ActionResult:
    """Aggregate results across all runs in a survey directory."""
    from simctl.core.discovery import discover_runs
    from simctl.core.manifest import read_manifest

    run_dirs = discover_runs(survey_dir)
    if not run_dirs:
        return _precondition_fail("collect_survey", f"No runs found under {survey_dir}")

    summary: dict[str, int] = {s.value: 0 for s in RunState}
    run_data: list[dict[str, Any]] = []
    for rd in run_dirs:
        try:
            m = read_manifest(rd)
            state = m.run.get("status", "unknown")
            summary[state] = summary.get(state, 0) + 1
            run_data.append(
                {
                    "run_id": m.run.get("id", ""),
                    "status": state,
                    "display_name": m.run.get("display_name", ""),
                }
            )
        except SimctlError:
            continue

    return ActionResult(
        action="collect_survey",
        status=ActionStatus.SUCCESS,
        message=f"Collected {len(run_data)} runs",
        data={
            "total_runs": len(run_data),
            "state_counts": {k: v for k, v in summary.items() if v > 0},
            "runs": run_data,
        },
    )


def retry_run(
    run_dir: Path,
    *,
    adjustments: dict[str, Any] | None = None,
) -> ActionResult:
    """Resubmit a failed run as a new attempt."""
    from simctl.core.manifest import read_manifest, update_manifest

    state_str, err = _require_state(run_dir, RunState.FAILED)
    if err:
        return _precondition_fail("retry_run", err)

    manifest = read_manifest(run_dir)
    attempt = manifest.job.get("attempt", 0)

    # Reset state to created for resubmission
    update_manifest(
        run_dir,
        {
            "run": {
                "status": RunState.CREATED.value,
                "failure_reason": "",
            },
            "job": {
                "attempt": attempt,
                "retry_adjustments": adjustments or {},
            },
        },
    )

    return ActionResult(
        action="retry_run",
        status=ActionStatus.SUCCESS,
        message=f"Reset to created for retry (attempt {attempt + 1})",
        data={
            "previous_attempt": attempt,
            "next_attempt": attempt + 1,
            "adjustments": adjustments or {},
        },
        state_before=state_str,
        state_after=RunState.CREATED.value,
    )


def archive_run(run_dir: Path) -> ActionResult:
    """Archive a completed run."""
    from simctl.core.state import update_state

    state_str, err = _require_state(run_dir, RunState.COMPLETED)
    if err:
        return _precondition_fail("archive_run", err)

    try:
        update_state(run_dir, RunState.ARCHIVED)
    except SimctlError as e:
        return _error("archive_run", str(e))

    return ActionResult(
        action="archive_run",
        status=ActionStatus.SUCCESS,
        message="Run archived",
        state_before=state_str,
        state_after=RunState.ARCHIVED.value,
    )


def add_fact(
    project_root: Path,
    *,
    claim: str,
    fact_type: str = "observation",
    simulator: str = "",
    scope_case: str = "",
    scope_text: str = "",
    param_name: str = "",
    confidence: str = "medium",
    source_run: str = "",
    evidence_kind: str = "",
    evidence_ref: str = "",
    tags: list[str] | None = None,
) -> ActionResult:
    """Record a structured knowledge fact.

    This delegates to the knowledge module's save_fact function.
    """
    from simctl.core.knowledge import Fact, load_facts, save_fact

    # Auto-generate ID
    existing = load_facts(project_root)
    next_num = len(existing) + 1
    fact_id = f"f{next_num:03d}"

    fact = Fact(
        id=fact_id,
        claim=claim,
        fact_type=fact_type,
        simulator=simulator,
        scope_case=scope_case,
        scope_text=scope_text,
        param_name=param_name,
        confidence=confidence,
        source_run=source_run,
        evidence_kind=evidence_kind,
        evidence_ref=evidence_ref,
        tags=tags or [],
    )
    try:
        save_fact(project_root, fact)
    except (RuntimeError, OSError) as e:
        return _error("add_fact", str(e))

    return ActionResult(
        action="add_fact",
        status=ActionStatus.SUCCESS,
        message=f"Saved fact {fact_id}: {claim}",
        data={"fact_id": fact_id},
    )


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

#: Map action name -> callable.
_DISPATCH: dict[str, Any] = {
    "create_run": create_run,
    "submit_run": submit_run,
    "sync_run": sync_run,
    "show_log": show_log,
    "summarize_run": summarize_run,
    "collect_survey": collect_survey,
    "retry_run": retry_run,
    "archive_run": archive_run,
    "add_fact": add_fact,
}


def execute_action(name: str, **kwargs: Any) -> ActionResult:
    """Execute a named action with keyword arguments.

    This is the primary entry point for agents.

    Args:
        name: Action name (must be in ACTION_SPECS).
        **kwargs: Arguments matching the action's parameter spec.

    Returns:
        ActionResult with status, message, and data.
    """
    if name not in _DISPATCH:
        return ActionResult(
            action=name,
            status=ActionStatus.ERROR,
            message=f"Unknown action: {name!r}. Available: {sorted(_DISPATCH)}",
        )

    fn = _DISPATCH[name]
    try:
        result: ActionResult = fn(**kwargs)
        return result
    except TypeError as e:
        return ActionResult(
            action=name,
            status=ActionStatus.ERROR,
            message=f"Invalid arguments for {name}: {e}",
        )
    except Exception as e:
        logger.exception("Unexpected error in action %s", name)
        return ActionResult(
            action=name,
            status=ActionStatus.ERROR,
            message=f"Unexpected error: {e}",
        )
