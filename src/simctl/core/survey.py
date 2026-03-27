"""Survey expansion and parameter cartesian product.

Reads survey.toml and expands parameter axes into individual run configurations.
"""

from __future__ import annotations

import itertools
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

from simctl.core.case import (
    ClassificationData,
    JobData,
    _parse_classification,
    _parse_job,
)
from simctl.core.exceptions import SurveyConfigError

_SURVEY_FILE = "survey.toml"


@dataclass(frozen=True)
class SurveyData:
    """Immutable representation of a survey.toml configuration.

    Matches SPEC section 11.2.

    Attributes:
        id: Survey identifier (e.g. "S20260327-cavity-u-a").
        name: Human-readable survey name.
        base_case: Name of the base case to derive runs from.
        simulator: Simulator name.
        launcher: Launcher profile name.
        classification: Classification metadata.
        axes: Parameter axes for cartesian product expansion.
        naming_template: Template string for generating display_name.
        job: Slurm job configuration.
        survey_dir: Absolute path to the survey directory.
        raw: The raw parsed survey.toml dictionary.
    """

    id: str
    name: str
    base_case: str
    simulator: str
    launcher: str
    classification: ClassificationData = field(default_factory=ClassificationData)
    axes: dict[str, list[Any]] = field(default_factory=dict)
    naming_template: str = ""
    job: JobData = field(default_factory=JobData)
    survey_dir: Path = field(default_factory=lambda: Path("."))
    raw: dict[str, Any] = field(default_factory=dict)


def load_survey(survey_dir: Path) -> SurveyData:
    """Load and validate a survey.toml file.

    Args:
        survey_dir: Directory containing survey.toml.

    Returns:
        Validated SurveyData instance.

    Raises:
        SurveyConfigError: If survey.toml is missing, invalid, or lacks
            required fields.
    """
    survey_dir = survey_dir.resolve()
    survey_file = survey_dir / _SURVEY_FILE

    if not survey_file.exists():
        raise SurveyConfigError(f"{_SURVEY_FILE} not found in {survey_dir}")

    try:
        with open(survey_file, "rb") as f:
            raw = tomllib.load(f)
    except tomllib.TOMLDecodeError as e:
        raise SurveyConfigError(f"Invalid TOML in {survey_file}: {e}") from e

    survey_section = raw.get("survey")
    if not isinstance(survey_section, dict):
        raise SurveyConfigError(f"Missing or invalid [survey] section in {survey_file}")

    survey_id = survey_section.get("id")
    if not isinstance(survey_id, str) or not survey_id:
        raise SurveyConfigError(f"Missing or empty 'survey.id' in {survey_file}")

    name = str(survey_section.get("name", ""))
    base_case = survey_section.get("base_case")
    if not isinstance(base_case, str) or not base_case:
        raise SurveyConfigError(f"Missing or empty 'survey.base_case' in {survey_file}")

    simulator = survey_section.get("simulator")
    if not isinstance(simulator, str) or not simulator:
        raise SurveyConfigError(f"Missing or empty 'survey.simulator' in {survey_file}")

    launcher = survey_section.get("launcher")
    if not isinstance(launcher, str) or not launcher:
        raise SurveyConfigError(f"Missing or empty 'survey.launcher' in {survey_file}")

    classification = _parse_classification(raw.get("classification", {}))

    # Parse axes
    axes_section = raw.get("axes", {})
    if not isinstance(axes_section, dict):
        raise SurveyConfigError(f"Invalid [axes] section in {survey_file}")
    axes: dict[str, list[Any]] = {}
    for key, values in axes_section.items():
        if not isinstance(values, list):
            raise SurveyConfigError(f"Axis '{key}' must be a list in {survey_file}")
        if len(values) == 0:
            raise SurveyConfigError(f"Axis '{key}' must not be empty in {survey_file}")
        axes[key] = values

    # Parse naming template
    naming_section = raw.get("naming", {})
    naming_template = ""
    if isinstance(naming_section, dict):
        naming_template = str(naming_section.get("display_name", ""))

    job = _parse_job(raw.get("job", {}))

    return SurveyData(
        id=survey_id,
        name=name,
        base_case=base_case,
        simulator=simulator,
        launcher=launcher,
        classification=classification,
        axes=axes,
        naming_template=naming_template,
        job=job,
        survey_dir=survey_dir,
        raw=raw,
    )


def expand_axes(axes: dict[str, list[Any]]) -> list[dict[str, Any]]:
    """Compute the cartesian product of parameter axes.

    Args:
        axes: Mapping of parameter names to lists of values.

    Returns:
        List of parameter dictionaries, one per combination.
        Empty list if axes is empty.

    Example:
        >>> expand_axes({"a": [1, 2], "b": [10, 20]})
        [{"a": 1, "b": 10}, {"a": 1, "b": 20}, {"a": 2, "b": 10}, {"a": 2, "b": 20}]
    """
    if not axes:
        return []

    keys = list(axes.keys())
    value_lists = [axes[k] for k in keys]

    return [
        dict(zip(keys, combo, strict=True)) for combo in itertools.product(*value_lists)
    ]


def generate_display_name(template: str, params: dict[str, Any]) -> str:
    """Generate a display_name from a naming template and parameters.

    Uses Python str.format_map with parameter values. Non-string
    values are formatted directly (floats use default repr).

    Args:
        template: Naming template string (e.g. "u{u}_a{aspect}_s{seed}").
        params: Parameter dictionary to substitute into the template.

    Returns:
        Rendered display name string. Returns empty string if template
        is empty.
    """
    if not template:
        return ""

    # Build a string-safe mapping
    fmt_params: dict[str, str] = {}
    for key, value in params.items():
        formatted = f"{value:g}" if isinstance(value, float) else str(value)
        fmt_params[key] = formatted

    try:
        return template.format_map(fmt_params)
    except KeyError:
        # Missing key in params - return template with available substitutions
        return template.format_map(
            {**{k: f"{{{k}}}" for k in _extract_keys(template)}, **fmt_params}
        )


def _extract_keys(template: str) -> list[str]:
    """Extract format keys from a template string.

    Args:
        template: A Python format string.

    Returns:
        List of key names found in the template.
    """
    import string

    formatter = string.Formatter()
    keys: list[str] = []
    for _, field_name, _, _ in formatter.parse(template):
        if field_name is not None:
            keys.append(field_name)
    return keys
