"""Adapter registry for looking up simulator adapters by name."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from simctl.adapters.base import SimulatorAdapter

_registry: dict[str, type[SimulatorAdapter]] = {}


def register(
    adapter_cls: type[SimulatorAdapter],
    *,
    name: str | None = None,
) -> type[SimulatorAdapter]:
    """Register a simulator adapter class.

    Can be used as a decorator::

        @register
        class MyAdapter(SimulatorAdapter):
            adapter_name = "my_sim"
            ...

    Args:
        adapter_cls: The adapter class to register.
        name: Explicit adapter name. If not provided, reads ``adapter_name``
            class attribute.

    Returns:
        The adapter class (unchanged).

    Raises:
        ValueError: If an adapter with the same name is already registered.
        AttributeError: If no name is provided and the class has no
            ``adapter_name`` attribute.
    """
    resolved_name: str = name if name is not None else str(getattr(adapter_cls, "adapter_name", ""))
    if not resolved_name:
        msg = (
            f"{adapter_cls.__name__} must define 'adapter_name' "
            "or pass 'name' to register()"
        )
        raise AttributeError(msg)
    if resolved_name in _registry:
        msg = f"Adapter already registered: {resolved_name}"
        raise ValueError(msg)
    _registry[resolved_name] = adapter_cls
    return adapter_cls


def get(name: str) -> type[SimulatorAdapter]:
    """Retrieve a registered adapter class by name.

    Args:
        name: Canonical adapter name.

    Returns:
        The adapter class.

    Raises:
        KeyError: If no adapter is registered under the given name.
    """
    if name not in _registry:
        msg = f"Unknown adapter: {name}. Available: {list(_registry)}"
        raise KeyError(msg)
    return _registry[name]


def list_adapters() -> list[str]:
    """Return the names of all registered adapters.

    Returns:
        Sorted list of adapter names.
    """
    return sorted(_registry)
