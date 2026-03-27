"""CLI commands for run and survey creation."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any

import typer

from simctl.adapters import get as get_adapter
from simctl.adapters.base import SimulatorAdapter
from simctl.adapters.registry import load_from_config
from simctl.core.case import CaseData, load_case, resolve_case
from simctl.core.discovery import collect_existing_run_ids
from simctl.core.exceptions import SimctlError
from simctl.core.manifest import ManifestData, write_manifest
from simctl.core.project import ProjectConfig, find_project_root, load_project
from simctl.core.run import RunInfo, create_run
from simctl.core.survey import (
    expand_axes,
    generate_display_name,
    load_survey,
)
from simctl.jobgen.generator import generate_job_script
from simctl.launchers.base import Launcher, load_launchers


def _load_project_config(dest: Path) -> ProjectConfig:
    """Locate project root and load configuration.

    Args:
        dest: A path inside the project (used to locate the root).

    Returns:
        Loaded project configuration.

    Raises:
        typer.Exit: If the project root cannot be found.
    """
    try:
        root = find_project_root(dest)
    except SimctlError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    try:
        return load_project(root)
    except SimctlError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc


def _get_adapter_instance(
    project: ProjectConfig,
    simulator_name: str,
) -> SimulatorAdapter:
    """Load adapters from project config and return the requested one.

    Resolves the adapter name from the simulator's config entry
    (``simulators.<name>.adapter``), then looks it up in the global
    adapter registry.

    Args:
        project: Loaded project configuration.
        simulator_name: Name of the simulator to look up.

    Returns:
        Instantiated simulator adapter.

    Raises:
        typer.Exit: If the adapter cannot be found.
    """
    load_from_config(project.simulators)
    sim_config = project.simulators.get(simulator_name, {})
    adapter_name = sim_config.get("adapter", simulator_name)
    try:
        adapter_cls = get_adapter(adapter_name)
    except KeyError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    return adapter_cls()


def _get_launcher(
    project: ProjectConfig,
    launcher_name: str,
) -> Launcher:
    """Look up a launcher profile from project configuration.

    Args:
        project: Loaded project configuration.
        launcher_name: Name of the launcher profile.

    Returns:
        Launcher instance.

    Raises:
        typer.Exit: If the launcher profile is not found or invalid.
    """
    try:
        launchers = load_launchers(project.launchers)
    except Exception as exc:
        typer.echo(f"Error loading launchers: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    if launcher_name not in launchers:
        typer.echo(
            f"Error: Launcher profile '{launcher_name}' not found. "
            f"Available: {sorted(launchers.keys())}",
            err=True,
        )
        raise typer.Exit(code=1)
    return launchers[launcher_name]


def _get_simulator_config(
    project: ProjectConfig,
    simulator_name: str,
) -> dict[str, Any]:
    """Retrieve the simulator configuration dict from the project.

    Args:
        project: Loaded project configuration.
        simulator_name: Name of the simulator.

    Returns:
        Simulator configuration dictionary.
    """
    return dict(project.simulators.get(simulator_name, {}))


def _build_job_config(case_job: dict[str, Any]) -> dict[str, Any]:
    """Build a job config dict from case/survey job data.

    Args:
        case_job: Job section dict (partition, nodes, ntasks, walltime).

    Returns:
        Job configuration dictionary for job script generation.
    """
    return {
        "partition": case_job.get("partition", ""),
        "nodes": case_job.get("nodes", 1),
        "ntasks": case_job.get("ntasks", 1),
        "walltime": case_job.get("walltime", "01:00:00"),
    }


def _build_manifest(
    run_info: RunInfo,
    case_data: CaseData,
    project: ProjectConfig,
    runtime_info: dict[str, Any],
    adapter: SimulatorAdapter,
    *,
    survey_id: str = "",
    variation_keys: list[str] | None = None,
) -> ManifestData:
    """Build a ManifestData for a newly created run.

    Args:
        run_info: Information about the created run.
        case_data: The case configuration.
        project: Project configuration.
        runtime_info: Runtime resolution result from the adapter.
        adapter: The simulator adapter.
        survey_id: Survey identifier, if this run is part of a survey.
        variation_keys: Parameter keys that vary across the survey.

    Returns:
        Populated ManifestData ready to write.
    """
    sim_config = _get_simulator_config(project, case_data.simulator)
    provenance = adapter.collect_provenance(runtime_info)

    return ManifestData(
        run={
            "id": run_info.run_id,
            "display_name": run_info.display_name,
            "status": "created",
            "created_at": run_info.created_at,
        },
        path={
            "run_dir": str(run_info.run_dir),
        },
        origin={
            "case": case_data.name,
            "survey": survey_id,
            "parent_run": "",
        },
        classification={
            "model": case_data.classification.model,
            "submodel": case_data.classification.submodel,
            "tags": list(case_data.classification.tags),
        },
        simulator={
            "name": case_data.simulator,
            "adapter": sim_config.get("adapter", ""),
            "resolver_mode": sim_config.get("resolver_mode", "package"),
        },
        launcher={
            "name": case_data.launcher,
        },
        simulator_source=provenance,
        job={
            "scheduler": "slurm",
            "job_id": "",
            "partition": case_data.job.partition,
            "nodes": case_data.job.nodes,
            "ntasks": case_data.job.ntasks,
            "walltime": case_data.job.walltime,
            "submitted_at": "",
        },
        variation={
            "changed_keys": list(variation_keys) if variation_keys else [],
        },
        params_snapshot=dict(run_info.params),
        files={
            "input_dir": "input",
            "submit_dir": "submit",
            "work_dir": "work",
            "analysis_dir": "analysis",
            "status_dir": "status",
        },
    )


def _generate_run(
    parent_dir: Path,
    case_data: CaseData,
    project: ProjectConfig,
    adapter: SimulatorAdapter,
    launcher: Launcher,
    existing_ids: set[str],
    params: dict[str, Any],
    *,
    display_name: str = "",
    survey_id: str = "",
    variation_keys: list[str] | None = None,
) -> RunInfo:
    """Generate a single run: directory, inputs, job script, manifest.

    This is the shared implementation for both ``create`` and ``sweep``.

    Args:
        parent_dir: Directory under which to create the run.
        case_data: Loaded case definition.
        project: Loaded project configuration.
        adapter: Simulator adapter instance.
        launcher: Launcher profile instance.
        existing_ids: Already-known run IDs (for dedup).
        params: Full parameter snapshot for this run.
        display_name: Human-readable name for the run.
        survey_id: Survey identifier (empty for single creates).
        variation_keys: Keys that vary across the sweep.

    Returns:
        RunInfo for the created run.

    Raises:
        SimctlError: On any domain error during generation.
    """
    # 1. Create run directory
    run_info = create_run(
        parent_dir,
        existing_ids,
        display_name=display_name,
        params=params,
    )

    # 2. Render input files via adapter
    adapter.render_inputs(
        {"case": case_data.raw.get("case", {}), "params": params},
        run_info.run_dir,
    )

    # 3. Resolve runtime and build execution command
    sim_config = _get_simulator_config(project, case_data.simulator)
    resolver_mode = sim_config.get("resolver_mode", "package")
    runtime_info = adapter.resolve_runtime(sim_config, resolver_mode)
    program_cmd = adapter.build_program_command(runtime_info, run_info.run_dir)

    # 4. Build launcher exec line and generate job.sh
    exec_line = launcher.build_exec_line(
        program_cmd,
        case_data.job.ntasks,
    )
    job_config = _build_job_config(
        {
            "partition": case_data.job.partition,
            "nodes": case_data.job.nodes,
            "ntasks": case_data.job.ntasks,
            "walltime": case_data.job.walltime,
        }
    )
    generate_job_script(
        run_info.run_dir,
        job_config,
        exec_line,
        run_id=run_info.run_id,
    )

    # 5. Build and write manifest
    manifest = _build_manifest(
        run_info,
        case_data,
        project,
        runtime_info,
        adapter,
        survey_id=survey_id,
        variation_keys=variation_keys,
    )
    write_manifest(run_info.run_dir, manifest)

    # 6. Track the new ID so subsequent runs in the same sweep won't collide
    existing_ids.add(run_info.run_id)

    return run_info


def create(
    case_name: Annotated[
        str,
        typer.Argument(help="Name of the case to create a run from."),
    ],
    dest: Annotated[
        Path,
        typer.Option("--dest", help="Destination survey directory."),
    ],
) -> None:
    """Create a single run from a case definition."""
    dest = dest.resolve()

    # Load project
    project = _load_project_config(dest)

    # Resolve and load case
    try:
        case_dir = resolve_case(case_name, project.root_dir)
        case_data = load_case(case_dir)
    except SimctlError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    # Get adapter and launcher
    adapter = _get_adapter_instance(project, case_data.simulator)
    launcher = _get_launcher(project, case_data.launcher)

    # Collect existing run IDs for dedup
    runs_dir = project.root_dir / "runs"
    existing_ids = collect_existing_run_ids(runs_dir)

    # Ensure destination exists
    dest.mkdir(parents=True, exist_ok=True)

    # Generate the run
    try:
        run_info = _generate_run(
            parent_dir=dest,
            case_data=case_data,
            project=project,
            adapter=adapter,
            launcher=launcher,
            existing_ids=existing_ids,
            params=dict(case_data.params),
            display_name=case_data.name,
        )
    except SimctlError as exc:
        typer.echo(f"Error creating run: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    typer.echo(f"Created run: {run_info.run_id}")
    typer.echo(f"  Path: {run_info.run_dir}")


def sweep(
    survey_dir: Annotated[
        Path,
        typer.Argument(help="Directory containing survey.toml."),
    ],
) -> None:
    """Generate all runs from a survey.toml parameter sweep."""
    survey_dir = survey_dir.resolve()

    # Load project
    project = _load_project_config(survey_dir)

    # Load survey
    try:
        survey_data = load_survey(survey_dir)
    except SimctlError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    # Resolve and load base case
    try:
        case_dir = resolve_case(survey_data.base_case, project.root_dir)
        case_data = load_case(case_dir)
    except SimctlError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    # Get adapter and launcher (prefer survey-level overrides)
    simulator_name = survey_data.simulator or case_data.simulator
    launcher_name = survey_data.launcher or case_data.launcher
    adapter = _get_adapter_instance(project, simulator_name)
    launcher = _get_launcher(project, launcher_name)

    # Expand parameter axes
    combinations = expand_axes(survey_data.axes)
    if not combinations:
        typer.echo("No parameter combinations to expand.")
        raise typer.Exit(code=0)

    # Collect existing run IDs for dedup
    runs_dir = project.root_dir / "runs"
    existing_ids = collect_existing_run_ids(runs_dir)

    # Override case_data with survey-level settings where appropriate
    # Build a modified CaseData that reflects survey overrides
    effective_case = CaseData(
        name=case_data.name,
        simulator=simulator_name,
        launcher=launcher_name,
        description=case_data.description,
        classification=(
            survey_data.classification
            if survey_data.classification.model
            else case_data.classification
        ),
        job=survey_data.job if survey_data.job.partition else case_data.job,
        params=case_data.params,
        case_dir=case_data.case_dir,
        raw=case_data.raw,
    )

    variation_keys = list(survey_data.axes.keys())
    created_runs: list[RunInfo] = []

    for combo in combinations:
        # Merge base case params with sweep params (sweep overrides)
        merged_params = {**case_data.params, **combo}

        # Generate display_name from naming template
        display_name = generate_display_name(survey_data.naming_template, merged_params)

        try:
            run_info = _generate_run(
                parent_dir=survey_dir,
                case_data=effective_case,
                project=project,
                adapter=adapter,
                launcher=launcher,
                existing_ids=existing_ids,
                params=merged_params,
                display_name=display_name,
                survey_id=survey_data.id,
                variation_keys=variation_keys,
            )
            created_runs.append(run_info)
        except SimctlError as exc:
            typer.echo(f"Error creating run for {combo}: {exc}", err=True)
            raise typer.Exit(code=1) from exc

    # Print summary
    typer.echo(f"Created {len(created_runs)} runs in {survey_dir}")
    for run_info in created_runs:
        name_part = f" ({run_info.display_name})" if run_info.display_name else ""
        typer.echo(f"  {run_info.run_id}{name_part}")
