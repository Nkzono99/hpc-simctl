"""Contract tests for the AI-facing action registry."""

from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import Any

import pytest

from simctl.core import actions
from simctl.core.actions import ActionStatus


def _signature_params(
    fn: Callable[..., Any],
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Return required and optional parameter names from a callable signature."""
    required: list[str] = []
    optional: list[str] = []

    for param in inspect.signature(fn).parameters.values():
        if param.kind not in (
            inspect.Parameter.POSITIONAL_ONLY,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
            inspect.Parameter.KEYWORD_ONLY,
        ):
            continue
        if param.default is inspect.Signature.empty:
            required.append(param.name)
        else:
            optional.append(param.name)

    return tuple(required), tuple(optional)


def test_action_specs_and_dispatch_cover_the_same_actions() -> None:
    """Every advertised action must be executable, and vice versa."""
    assert set(actions.ACTION_SPECS) == set(actions._DISPATCH)
    for name, spec in actions.ACTION_SPECS.items():
        assert spec.name == name


@pytest.mark.parametrize("name", sorted(actions.ACTION_SPECS))
def test_action_spec_matches_dispatch_signature(name: str) -> None:
    """required_params/optional_params must match the callable signature."""
    spec = actions.ACTION_SPECS[name]
    required_params, optional_params = _signature_params(actions._DISPATCH[name])

    assert spec.required_params == required_params
    assert spec.optional_params == optional_params


def test_list_actions_exposes_all_registered_specs() -> None:
    """The public registry listing should expose every registered action."""
    assert {spec.name for spec in actions.list_actions()} == set(actions.ACTION_SPECS)


def test_get_action_spec_returns_registered_spec() -> None:
    """Named lookups should round-trip to the stored ActionSpec objects."""
    for name, expected in actions.ACTION_SPECS.items():
        assert actions.get_action_spec(name) == expected

    assert actions.get_action_spec("missing_action") is None


def test_execute_action_rejects_unknown_actions() -> None:
    """Unknown actions should return a structured error instead of raising."""
    result = actions.execute_action("missing_action")

    assert result.status is ActionStatus.ERROR
    assert "Unknown action" in result.message
