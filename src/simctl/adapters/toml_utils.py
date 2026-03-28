"""Shared TOML configuration utilities for simulator adapters.

Provides deep-merge and dot-notation override for TOML-based configs.
Supports both dict navigation and list-index access for array-of-tables
(e.g. ``species.0.wp`` targets ``config["species"][0]["wp"]``).
"""

from __future__ import annotations

import copy
from typing import Any


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Deep-merge *override* into *base*.

    Dicts are recursively merged; all other values (including lists)
    are replaced.

    Args:
        base: Base configuration dictionary.
        override: Overrides to apply.

    Returns:
        New merged dictionary (neither input is mutated).
    """
    result = copy.deepcopy(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def apply_dotted_overrides(
    config: dict[str, Any],
    overrides: dict[str, Any],
) -> dict[str, Any]:
    """Apply flat dot-notation overrides to a nested config dict.

    Supports both dict keys and numeric list indices::

        {"sim.dt": 1e-8}             -> config["sim"]["dt"] = 1e-8
        {"species.0.wp": 2.1}        -> config["species"][0]["wp"] = 2.1
        {"tmgrid.nx": 512}           -> config["tmgrid"]["nx"] = 512

    Args:
        config: Base config dictionary.
        overrides: Flat dot-notation key-value pairs.

    Returns:
        New dict with overrides applied (input not mutated).
    """
    result = copy.deepcopy(config)
    for key, value in overrides.items():
        parts = key.split(".")
        target: Any = result
        for part in parts[:-1]:
            if isinstance(target, list):
                target = target[int(part)]
            elif part.isdigit() and isinstance(target.get(part), type(None)):
                # Numeric key not present as string; skip if target is a list-like
                idx = int(part)
                # Check if the parent is storing a list
                target = target[idx] if isinstance(target, list) else target.setdefault(part, {})
            else:
                if part not in target:
                    target[part] = {}
                target = target[part]
        # Set the final value
        leaf = parts[-1]
        if isinstance(target, list):
            target[int(leaf)] = value
        else:
            target[leaf] = value
    return result
