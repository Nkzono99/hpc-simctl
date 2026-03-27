"""State transition management for runs.

Defines the canonical set of run states, valid transitions between them,
and functions to update state in both manifest.toml and status/state.json.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from simctl.core.exceptions import InvalidStateTransitionError


class RunState(str, Enum):
    """Possible states for a simulation run.

    Values match SPEC section 13.
    """

    CREATED = "created"
    SUBMITTED = "submitted"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    ARCHIVED = "archived"
    PURGED = "purged"


#: Valid state transitions: maps current state to allowed next states.
#: Matches SPEC section 13.2 exactly.
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


def transition_state(current: RunState, target: RunState) -> RunState:
    """Perform a validated state transition.

    Args:
        current: The current run state.
        target: The desired next state.

    Returns:
        The new state (same as target).

    Raises:
        InvalidStateTransitionError: If the transition is not allowed.
    """
    if not validate_transition(current, target):
        raise InvalidStateTransitionError(current.value, target.value)
    return target


def update_state(
    run_dir: Path,
    new_state: RunState,
    *,
    timestamp: datetime | None = None,
) -> None:
    """Update the run state in both manifest.toml and status/state.json.

    This function reads the current manifest, validates the transition,
    updates ``run.status`` in manifest.toml, and writes a corresponding
    ``status/state.json``.

    Args:
        run_dir: Path to the run directory.
        new_state: The target state.
        timestamp: Optional timestamp for the state change. Defaults
            to the current UTC time.

    Raises:
        InvalidStateTransitionError: If the transition is not allowed.
        ManifestNotFoundError: If manifest.toml does not exist.
    """
    # Import here to avoid circular imports
    from simctl.core.manifest import read_manifest, update_manifest

    if timestamp is None:
        timestamp = datetime.now(tz=timezone.utc)

    manifest = read_manifest(run_dir)
    current_str = manifest.run.get("status", "")
    try:
        current = RunState(current_str)
    except ValueError:
        raise InvalidStateTransitionError(current_str, new_state.value) from None

    # Validate and perform transition
    transition_state(current, new_state)

    # Update manifest.toml
    update_manifest(
        run_dir,
        {
            "run": {"status": new_state.value},
        },
    )

    # Write status/state.json
    status_dir = run_dir / "status"
    status_dir.mkdir(parents=True, exist_ok=True)
    state_json: dict[str, Any] = {
        "state": new_state.value,
        "previous_state": current.value,
        "changed_at": timestamp.isoformat(),
    }
    state_file = status_dir / "state.json"
    with open(state_file, "w") as f:
        json.dump(state_json, f, indent=2)
        f.write("\n")
