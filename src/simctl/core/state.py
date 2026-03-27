"""State transition management for runs.

Defines the canonical set of run states and valid transitions between them.
"""

from __future__ import annotations

from enum import Enum


class RunState(str, Enum):
    """Possible states for a simulation run."""

    CREATED = "created"
    SUBMITTED = "submitted"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    ARCHIVED = "archived"
    PURGED = "purged"


#: Valid state transitions: maps current state to allowed next states.
VALID_TRANSITIONS: dict[RunState, frozenset[RunState]] = {
    RunState.CREATED: frozenset({RunState.SUBMITTED, RunState.FAILED}),
    RunState.SUBMITTED: frozenset(
        {RunState.RUNNING, RunState.FAILED, RunState.CANCELLED}
    ),
    RunState.RUNNING: frozenset(
        {RunState.COMPLETED, RunState.FAILED, RunState.CANCELLED}
    ),
    RunState.COMPLETED: frozenset({RunState.ARCHIVED}),
    RunState.FAILED: frozenset(),
    RunState.CANCELLED: frozenset(),
    RunState.ARCHIVED: frozenset({RunState.PURGED}),
    RunState.PURGED: frozenset(),
}


def validate_transition(current: RunState, target: RunState) -> bool:
    """Check whether a state transition is valid.

    Args:
        current: The current run state.
        target: The desired next state.

    Returns:
        True if the transition is allowed, False otherwise.
    """
    return target in VALID_TRANSITIONS.get(current, frozenset())
