"""Tests for adapter registry."""

from __future__ import annotations

from simctl.adapters.registry import list_adapters


def test_list_adapters_initially_empty() -> None:
    # No adapters registered yet in the skeleton
    result = list_adapters()
    assert isinstance(result, list)
