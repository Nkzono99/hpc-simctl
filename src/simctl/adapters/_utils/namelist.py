"""Fortran namelist utilities for EMSES plasma.inp/plasma.preinp files.

Provides simple line-based parsing and parameter override functionality
for EMSES-style Fortran namelist files. Not a full namelist parser;
handles the specific patterns used by EMSES.
"""

from __future__ import annotations

import re
from typing import Any


def parse_metadata_line(line: str) -> dict[str, str]:
    """Parse the ``!!key`` metadata line from EMSES input files.

    The metadata line has format: ``!!key dx=[0.5],to_c=[10000.0]``

    Args:
        line: The first line of the file.

    Returns:
        Dictionary of metadata key-value pairs.
    """
    if not line.startswith("!!key"):
        return {}

    metadata: dict[str, str] = {}
    content = line[5:].strip()
    for item in content.split(","):
        item = item.strip()
        if "=" not in item:
            continue
        key, value = item.split("=", 1)
        metadata[key.strip()] = value.strip().strip("[]")
    return metadata


def find_current_group(lines: list[str], line_idx: int) -> str:
    """Find which namelist group a given line belongs to.

    Walks backward from *line_idx* to find the enclosing ``&group`` marker.

    Args:
        lines: All lines of the file.
        line_idx: Index of the target line.

    Returns:
        Group name (without ``&``) or empty string if not inside a group.
    """
    if not lines:
        return ""
    for i in range(min(line_idx, len(lines) - 1), -1, -1):
        stripped = lines[i].strip()
        if stripped == "/":
            return ""
        match = re.match(r"&(\w+)", stripped)
        if match:
            return match.group(1)
    return ""


_PARAM_RE = re.compile(
    r"^(\s*)"  # leading whitespace
    r"(\w+)"  # parameter name
    r"(\([^)]*\))?"  # optional array index e.g. (1:3)
    r"\s*=\s*"  # equals sign
    r"(.+)$",  # value(s)
)

_PREINP_RE = re.compile(
    r"^(\s*!!>\s*)"  # preinp directive prefix
    r"(\w+)"  # parameter name
    r"(\([^)]*\))?"  # optional array index
    r"\s*=\s*"  # equals sign
    r"(.+)$",  # value(s) / expression
)


def format_value(value: Any) -> str:
    """Format a Python value as a Fortran namelist value string.

    Args:
        value: The Python value to format.

    Returns:
        Fortran-formatted value string.
    """
    if isinstance(value, bool):
        return ".true." if value else ".false."
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if value == 0.0:
            return "0.0"
        if abs(value) < 1e-3 or abs(value) > 1e6:
            return f"{value:.15e}"
        return f"{value}"
    if isinstance(value, str):
        return f'"{value}"'
    if isinstance(value, (list, tuple)):
        return ", ".join(format_value(v) for v in value)
    return str(value)


def apply_overrides(text: str, overrides: dict[str, Any]) -> str:
    """Apply parameter overrides to a namelist file.

    Searches for parameter assignments matching the override keys and
    replaces their values.  Supports both regular assignments and
    preinp (``!!>``) directive lines.

    Keys can use dot-notation to specify the namelist group explicitly:
    ``"plasma.wc"`` targets ``wc`` in the ``&plasma`` group.
    Plain keys like ``"nstep"`` match the first occurrence in any group.

    Args:
        text: Original namelist file content.
        overrides: Dict mapping parameter keys to new values.

    Returns:
        Modified namelist text with overrides applied.
    """
    if not overrides:
        return text

    lines = text.split("\n")

    # Parse overrides into (group_or_none, param_name, value) tuples
    parsed: list[tuple[str | None, str, Any]] = []
    for key, value in overrides.items():
        if "." in key:
            group, param = key.rsplit(".", 1)
            parsed.append((group, param, value))
        else:
            parsed.append((None, key, value))

    applied: set[int] = set()

    for i, line in enumerate(lines):
        stripped = line.strip()
        # Skip pure comments, group delimiters, and blanks
        if not stripped or stripped == "/":
            continue
        if stripped.startswith("!") and not stripped.startswith("!!>"):
            continue
        if stripped.startswith("&"):
            continue

        # Try both regular and preinp patterns
        for pattern in (_PARAM_RE, _PREINP_RE):
            match = pattern.match(stripped)
            if not match:
                continue

            param_name = match.group(2)
            array_idx = match.group(3) or ""

            for idx, (group, override_param, value) in enumerate(parsed):
                if idx in applied:
                    continue
                if param_name != override_param:
                    continue
                if group is not None:
                    current_group = find_current_group(lines, i)
                    if current_group != group:
                        continue

                formatted = format_value(value)

                if pattern is _PREINP_RE:
                    orig_match = _PREINP_RE.match(line)
                    prefix = orig_match.group(1) if orig_match else "!!> "
                    lines[i] = f"{prefix}{param_name}{array_idx} = {formatted}"
                else:
                    orig_match = _PARAM_RE.match(line)
                    indent = orig_match.group(1) if orig_match else "    "
                    lines[i] = f"{indent}{param_name}{array_idx} = {formatted}"

                applied.add(idx)
                break
            break

    return "\n".join(lines)


def parse_namelist_params(text: str) -> dict[str, dict[str, str]]:
    """Parse all parameter assignments from a namelist file.

    Args:
        text: Namelist file content.

    Returns:
        Nested dict: ``group_name -> param_name -> value_string``.
    """
    result: dict[str, dict[str, str]] = {}
    current_group = ""

    for line in text.split("\n"):
        stripped = line.strip()

        group_match = re.match(r"&(\w+)", stripped)
        if group_match:
            current_group = group_match.group(1)
            if current_group not in result:
                result[current_group] = {}
            continue

        if stripped == "/":
            current_group = ""
            continue

        if not stripped or stripped.startswith("!"):
            continue

        match = _PARAM_RE.match(stripped)
        if match and current_group:
            param_name = match.group(2)
            array_idx = match.group(3) or ""
            value = match.group(4).strip()
            # Strip trailing inline comments
            comment_pos = _find_comment_pos(value)
            if comment_pos >= 0:
                value = value[:comment_pos].strip()
            result[current_group][f"{param_name}{array_idx}"] = value

    return result


def _find_comment_pos(value_str: str) -> int:
    """Find position of trailing ``!`` comment, ignoring quoted strings.

    Returns:
        Index of the comment character, or -1 if none found.
    """
    in_string = False
    quote_char = ""
    for i, ch in enumerate(value_str):
        if in_string:
            if ch == quote_char:
                in_string = False
        elif ch in ('"', "'"):
            in_string = True
            quote_char = ch
        elif ch == "!":
            return i
    return -1
