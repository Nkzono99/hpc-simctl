"""Campaign definition: research intent and experimental design."""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

from runops.core.exceptions import SimctlError

_CAMPAIGN_FILE = "campaign.toml"


@dataclass(frozen=True)
class Variable:
    """A variable in the experimental design.

    Attributes:
        name: Dot-notation parameter path.
        role: ``"independent"`` (swept), ``"dependent"`` (observed),
            ``"fixed"`` (constant), or ``"controlled"`` (held constant
            but might be varied in future).
        range: ``[min, max]`` for independent variables.
        values: Explicit list of values (alternative to range).
        unit: Physical unit string.
        reason: Why this variable is set this way.
    """

    name: str
    role: str
    range: list[float] | None = None
    values: list[Any] | None = None
    unit: str = ""
    reason: str = ""


@dataclass(frozen=True)
class Observable:
    """An observable (output quantity) to measure.

    Attributes:
        name: Observable name.
        source: Path or glob to the output file.
        column: Column index or name in the output file.
        description: What this observable represents.
        unit: Physical unit.
    """

    name: str
    source: str = ""
    column: str | int = ""
    description: str = ""
    unit: str = ""


@dataclass(frozen=True)
class CampaignData:
    """Parsed campaign.toml data.

    Attributes:
        name: Campaign name.
        description: Research motivation.
        hypothesis: Scientific hypothesis being tested.
        simulator: Primary simulator for this campaign.
        variables: Parameter definitions.
        observables: Output quantities to measure.
        raw: Raw TOML dict.
    """

    name: str
    description: str = ""
    hypothesis: str = ""
    simulator: str = ""
    variables: list[Variable] = field(default_factory=list)
    observables: list[Observable] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)


def load_campaign(project_dir: Path) -> CampaignData | None:
    """Load campaign.toml from the project root.

    Returns:
        CampaignData if campaign.toml exists, None otherwise.
    """
    campaign_file = project_dir / _CAMPAIGN_FILE
    if not campaign_file.is_file():
        return None

    try:
        with open(campaign_file, "rb") as f:
            raw = tomllib.load(f)
    except tomllib.TOMLDecodeError as e:
        raise SimctlError(f"Invalid campaign.toml: {e}") from e

    camp = raw.get("campaign", {})

    # Parse variables
    variables: list[Variable] = []
    for param_name, var_data in raw.get("variables", {}).items():
        if isinstance(var_data, dict):
            variables.append(
                Variable(
                    name=param_name,
                    role=var_data.get("role", "independent"),
                    range=var_data.get("range"),
                    values=var_data.get("values"),
                    unit=var_data.get("unit", ""),
                    reason=var_data.get("reason", ""),
                )
            )
        else:
            # Simple value: treated as fixed
            variables.append(
                Variable(
                    name=param_name,
                    role="fixed",
                    values=[var_data],
                )
            )

    # Parse observables
    observables: list[Observable] = []
    for obs_name, obs_data in raw.get("observables", {}).items():
        if isinstance(obs_data, dict):
            observables.append(
                Observable(
                    name=obs_name,
                    source=obs_data.get("source", ""),
                    column=obs_data.get("column", ""),
                    description=obs_data.get("description", ""),
                    unit=obs_data.get("unit", ""),
                )
            )
        else:
            observables.append(
                Observable(
                    name=obs_name,
                    source=str(obs_data),
                )
            )

    return CampaignData(
        name=camp.get("name", ""),
        description=camp.get("description", ""),
        hypothesis=camp.get("hypothesis", ""),
        simulator=camp.get("simulator", ""),
        variables=variables,
        observables=observables,
        raw=raw,
    )
