"""Retry policy: suggest next action for failed runs.

Maps failure reasons to candidate recovery actions.  The actual decision
to retry is left to the agent or user -- this module only provides
suggestions with rationale and confidence.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from runops.core.state import RunState


@dataclass(frozen=True)
class RetrySuggestion:
    """A suggested recovery action for a failed run.

    Attributes:
        action: Recommended action name (from the action registry).
        rationale: Why this action is suggested.
        confidence: ``"high"``, ``"medium"``, or ``"low"``.
        adjustments: Suggested parameter adjustments (if any).
    """

    action: str
    rationale: str
    confidence: str = "medium"
    adjustments: dict[str, Any] | None = None


#: Maps failure_reason to a list of suggestions (first = most preferred).
_SUGGESTION_TABLE: dict[str, list[RetrySuggestion]] = {
    "timeout": [
        RetrySuggestion(
            action="retry_run",
            rationale=(
                "Job exceeded walltime limit. Extend walltime or reduce problem size."
            ),
            confidence="high",
            adjustments={"walltime_factor": 1.5},
        ),
    ],
    "oom": [
        RetrySuggestion(
            action="retry_run",
            rationale=(
                "Job ran out of memory. Increase allocation or reduce problem size."
            ),
            confidence="high",
            adjustments={"memory_factor": 1.5},
        ),
    ],
    "preempted": [
        RetrySuggestion(
            action="retry_run",
            rationale=("Job was preempted. Resubmit with same configuration."),
            confidence="high",
        ),
    ],
    "node_fail": [
        RetrySuggestion(
            action="retry_run",
            rationale="Node failed. Resubmit same config.",
            confidence="high",
        ),
    ],
    "boot_fail": [
        RetrySuggestion(
            action="retry_run",
            rationale="Node boot failure. Resubmit same config.",
            confidence="high",
        ),
    ],
    "deadline": [
        RetrySuggestion(
            action="retry_run",
            rationale="Job reached deadline. Review constraints.",
            confidence="medium",
        ),
    ],
    "exit_error": [
        RetrySuggestion(
            action="show_log",
            rationale=("Non-zero exit code. Inspect log before retrying."),
            confidence="high",
        ),
        RetrySuggestion(
            action="retry_run",
            rationale="Resubmit after fixing the issue.",
            confidence="low",
        ),
    ],
}


def suggest_retry(
    failure_reason: str,
    *,
    attempt: int = 1,
    max_attempts: int = 3,
) -> list[RetrySuggestion]:
    """Suggest recovery actions for a given failure reason.

    Args:
        failure_reason: The failure reason string from manifest
            (e.g. ``"timeout"``, ``"oom"``, ``"exit_error"``).
        attempt: Current attempt number.
        max_attempts: Maximum retry attempts before giving up.

    Returns:
        List of suggestions ordered by preference (most preferred first).
        Empty list if no suggestions or max attempts exceeded.
    """
    if attempt >= max_attempts:
        return [
            RetrySuggestion(
                action="show_log",
                rationale=(
                    f"Max attempts ({max_attempts}) reached."
                    " Manual inspection required."
                ),
                confidence="high",
            ),
        ]

    suggestions = _SUGGESTION_TABLE.get(failure_reason, [])
    if not suggestions:
        return [
            RetrySuggestion(
                action="show_log",
                rationale=(
                    f"Unknown failure reason: {failure_reason!r}. Inspect log first."
                ),
                confidence="medium",
            ),
        ]

    return list(suggestions)


def get_attempt_count(job_data: dict[str, Any]) -> int:
    """Return the observed retry count from manifest ``job`` data.

    Newer manifests track a detailed ``attempts`` list while older ones may
    only store a scalar ``attempt`` field.  This helper normalizes both.
    """
    attempts = job_data.get("attempts", [])
    if isinstance(attempts, list) and attempts:
        return len(attempts)

    raw_attempt = job_data.get("attempt")
    if isinstance(raw_attempt, int) and raw_attempt > 0:
        return raw_attempt
    if isinstance(raw_attempt, str):
        try:
            parsed = int(raw_attempt)
            if parsed > 0:
                return parsed
        except ValueError:
            pass

    if job_data.get("job_id") or job_data.get("submitted_at"):
        return 1
    return 0


def suggest_retry_for_run(run_dir: Path) -> list[RetrySuggestion]:
    """Read manifest and suggest retry actions for a failed run.

    Convenience wrapper that reads failure_reason and attempt count
    from the manifest.

    Args:
        run_dir: Path to the run directory.

    Returns:
        List of RetrySuggestion instances.
    """
    from runops.core.manifest import read_manifest

    manifest = read_manifest(Path(run_dir))
    state_str = manifest.run.get("status", "")

    if state_str != RunState.FAILED.value:
        return []

    reason = manifest.run.get("failure_reason", "")
    attempt = get_attempt_count(manifest.job)

    return suggest_retry(reason, attempt=attempt)
