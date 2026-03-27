"""Tests for core state module."""

from __future__ import annotations

from simctl.core.state import RunState, validate_transition


def test_valid_transition_created_to_submitted() -> None:
    assert validate_transition(RunState.CREATED, RunState.SUBMITTED) is True


def test_invalid_transition_created_to_completed() -> None:
    assert validate_transition(RunState.CREATED, RunState.COMPLETED) is False


def test_all_states_defined() -> None:
    expected = {
        "created",
        "submitted",
        "running",
        "completed",
        "failed",
        "cancelled",
        "archived",
        "purged",
    }
    assert {s.value for s in RunState} == expected
