"""Simulator adapters for abstracting simulator-specific behavior.

Importing this package automatically registers the built-in adapters
(e.g. ``GenericAdapter``) in the global registry.
"""

from __future__ import annotations

from simctl.adapters.base import SimulatorAdapter
from simctl.adapters.generic import GenericAdapter
from simctl.adapters.registry import get, get_global_registry, list_adapters, register

# Register built-in adapters on import
register(GenericAdapter)

__all__ = [
    "GenericAdapter",
    "SimulatorAdapter",
    "get",
    "get_global_registry",
    "list_adapters",
    "register",
]
