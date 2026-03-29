"""Case loading and expansion.

Reads case.toml files and prepares case data for run generation.
A Case is a reusable base definition from which runs or surveys are generated.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

from simctl.core.exceptions import CaseConfigError, CaseNotFoundError

_CASE_FILE = "case.toml"


@dataclass(frozen=True)
class ClassificationData:
    """Classification metadata for a case or run.

    Attributes:
        model: Model category (e.g. "cavity").
        submodel: Sub-model category (e.g. "rectangular").
        tags: List of tags for filtering and organization.
    """

    model: str = ""
    submodel: str = ""
    tags: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class JobData:
    """Slurm job configuration.

    Attributes:
        partition: Slurm partition name.
        nodes: Number of nodes.
        ntasks: Number of MPI tasks.
        walltime: Wall-clock time limit string (HH:MM:SS).
    """

    partition: str = ""
    nodes: int = 1
    ntasks: int = 1
    walltime: str = "01:00:00"


@dataclass(frozen=True)
class CaseData:
    """Immutable representation of a case.toml configuration.

    Matches SPEC section 10.2.

    Attributes:
        name: Case name (required).
        simulator: Simulator name (required).
        launcher: Launcher profile name (required).
        description: Human-readable description.
        classification: Classification metadata.
        job: Slurm job configuration.
        params: Simulator-specific parameters.
        case_dir: Absolute path to the case directory.
        raw: The raw parsed case.toml dictionary.
    """

    name: str
    simulator: str
    launcher: str
    description: str = ""
    classification: ClassificationData = field(default_factory=ClassificationData)
    job: JobData = field(default_factory=JobData)
    params: dict[str, Any] = field(default_factory=dict)
    copy_files: list[str] = field(default_factory=list)
    case_dir: Path = field(default_factory=lambda: Path("."))
    raw: dict[str, Any] = field(default_factory=dict)


def _parse_classification(data: dict[str, Any]) -> ClassificationData:
    """Parse a [classification] section from TOML data.

    Args:
        data: Raw classification dictionary.

    Returns:
        ClassificationData instance.
    """
    tags = data.get("tags", [])
    if not isinstance(tags, list):
        tags = [str(tags)]
    return ClassificationData(
        model=str(data.get("model", "")),
        submodel=str(data.get("submodel", "")),
        tags=[str(t) for t in tags],
    )


def _parse_job(data: dict[str, Any]) -> JobData:
    """Parse a [job] section from TOML data.

    Args:
        data: Raw job dictionary.

    Returns:
        JobData instance.
    """
    return JobData(
        partition=str(data.get("partition", "")),
        nodes=int(data.get("nodes", 1)),
        ntasks=int(data.get("ntasks", 1)),
        walltime=str(data.get("walltime", "01:00:00")),
    )


def load_case(case_dir: Path) -> CaseData:
    """Load and validate a case.toml file.

    Args:
        case_dir: Directory containing case.toml.

    Returns:
        Validated CaseData instance.

    Raises:
        CaseNotFoundError: If case.toml does not exist.
        CaseConfigError: If required fields are missing or invalid.
    """
    case_dir = case_dir.resolve()
    case_file = case_dir / _CASE_FILE

    if not case_file.exists():
        raise CaseNotFoundError(f"{_CASE_FILE} not found in {case_dir}")

    try:
        with open(case_file, "rb") as f:
            raw = tomllib.load(f)
    except tomllib.TOMLDecodeError as e:
        raise CaseConfigError(f"Invalid TOML in {case_file}: {e}") from e

    case_section = raw.get("case")
    if not isinstance(case_section, dict):
        raise CaseConfigError(f"Missing or invalid [case] section in {case_file}")

    name = case_section.get("name")
    if not isinstance(name, str) or not name:
        raise CaseConfigError(f"Missing or empty 'case.name' in {case_file}")

    simulator = case_section.get("simulator")
    if not isinstance(simulator, str) or not simulator:
        raise CaseConfigError(f"Missing or empty 'case.simulator' in {case_file}")

    launcher = case_section.get("launcher")
    if not isinstance(launcher, str) or not launcher:
        raise CaseConfigError(f"Missing or empty 'case.launcher' in {case_file}")

    description = str(case_section.get("description", ""))

    # copy_files: paths relative to case_dir or absolute
    raw_copy_files = case_section.get("copy_files", [])
    if not isinstance(raw_copy_files, list):
        raw_copy_files = [str(raw_copy_files)]
    copy_files = [str(p) for p in raw_copy_files]

    classification = _parse_classification(raw.get("classification", {}))
    job = _parse_job(raw.get("job", {}))
    params = dict(raw.get("params", {}))

    return CaseData(
        name=name,
        simulator=simulator,
        launcher=launcher,
        description=description,
        classification=classification,
        job=job,
        params=params,
        copy_files=copy_files,
        case_dir=case_dir,
        raw=raw,
    )


def resolve_case(case_name: str, project_dir: Path) -> Path:
    """Resolve a case name to its directory path.

    Looks for ``cases/<case_name>/case.toml`` under the project root.

    Args:
        case_name: Logical name of the case.
        project_dir: Root of the simctl project.

    Returns:
        Path to the case directory.

    Raises:
        CaseNotFoundError: If the case directory or case.toml is not found.
    """
    case_dir = project_dir.resolve() / "cases" / case_name
    if not case_dir.is_dir():
        raise CaseNotFoundError(f"Case directory not found: {case_dir}")
    if not (case_dir / _CASE_FILE).exists():
        raise CaseNotFoundError(f"{_CASE_FILE} not found in {case_dir}")
    return case_dir
