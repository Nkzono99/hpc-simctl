"""Tests for adapter registry."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from simctl.adapters.base import SimulatorAdapter
from simctl.adapters.registry import AdapterRegistry

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _StubAdapter(SimulatorAdapter):
    """Minimal concrete adapter for registry tests."""

    adapter_name = "stub"

    @property
    def name(self) -> str:
        return self.adapter_name

    def render_inputs(self, case_data: dict[str, Any], run_dir: Path) -> list[str]:
        return []

    def resolve_runtime(
        self, simulator_config: dict[str, Any], resolver_mode: str
    ) -> dict[str, Any]:
        return {}

    def build_program_command(
        self, runtime_info: dict[str, Any], run_dir: Path
    ) -> list[str]:
        return []

    def detect_outputs(self, run_dir: Path) -> dict[str, Any]:
        return {}

    def detect_status(self, run_dir: Path) -> str:
        return "unknown"

    def summarize(self, run_dir: Path) -> dict[str, Any]:
        return {}

    def collect_provenance(self, runtime_info: dict[str, Any]) -> dict[str, Any]:
        return {}


class _NoNameAdapter(_StubAdapter):
    """Adapter without adapter_name for error-path testing."""

    adapter_name = ""


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.fixture()
def registry() -> AdapterRegistry:
    """Fresh registry for each test."""
    return AdapterRegistry()


def test_register_and_get(registry: AdapterRegistry) -> None:
    """Register an adapter and retrieve it by name."""
    registry.register(_StubAdapter)
    assert registry.get("stub") is _StubAdapter


def test_register_with_explicit_name(registry: AdapterRegistry) -> None:
    """Explicit name overrides adapter_name."""
    registry.register(_StubAdapter, name="custom")
    assert registry.get("custom") is _StubAdapter


def test_duplicate_registration_raises(registry: AdapterRegistry) -> None:
    """Registering the same name twice should raise ValueError."""
    registry.register(_StubAdapter)
    with pytest.raises(ValueError, match="already registered"):
        registry.register(_StubAdapter)


def test_get_unknown_raises(registry: AdapterRegistry) -> None:
    """Looking up an unregistered name should raise KeyError."""
    with pytest.raises(KeyError, match="Unknown adapter"):
        registry.get("nonexistent")


def test_no_name_raises(registry: AdapterRegistry) -> None:
    """Adapter without adapter_name and no explicit name should raise."""
    with pytest.raises(AttributeError, match="must define"):
        registry.register(_NoNameAdapter)


def test_list_adapters(registry: AdapterRegistry) -> None:
    """list_adapters returns sorted names."""
    registry.register(_StubAdapter, name="b_adapter")
    registry.register(_StubAdapter, name="a_adapter")
    assert registry.list_adapters() == ["a_adapter", "b_adapter"]


def test_list_adapters_empty(registry: AdapterRegistry) -> None:
    """Empty registry returns empty list."""
    assert registry.list_adapters() == []


def test_load_from_config_unknown_module(registry: AdapterRegistry) -> None:
    """load_from_config logs a warning for missing adapter modules."""
    config = {
        "simulators": {
            "nonexistent_sim": {
                "adapter": "totally_fake_adapter",
                "resolver_mode": "package",
            }
        }
    }
    # Should not raise, just warn
    registry.load_from_config(config)
    assert "totally_fake_adapter" not in registry.list_adapters()


def test_load_from_config_skips_already_registered(
    registry: AdapterRegistry,
) -> None:
    """Already-registered adapters are not re-imported."""
    registry.register(_StubAdapter, name="my_adapter")
    config = {
        "simulators": {
            "some_sim": {"adapter": "my_adapter"},
        }
    }
    # Should not raise even though the module doesn't exist
    registry.load_from_config(config)


# ---------------------------------------------------------------------------
# Global convenience API
# ---------------------------------------------------------------------------


def test_global_registry_has_generic() -> None:
    """Importing the adapters package registers GenericAdapter globally."""
    from simctl.adapters import list_adapters

    assert "generic" in list_adapters()


def test_global_get_generic() -> None:
    """Global get() returns GenericAdapter for 'generic'."""
    from simctl.adapters import get
    from simctl.adapters.generic import GenericAdapter

    assert get("generic") is GenericAdapter
