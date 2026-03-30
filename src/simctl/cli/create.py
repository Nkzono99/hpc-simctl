"""CLI commands for run and survey creation."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Annotated, Any, Optional

import typer

from simctl.adapters import get as get_adapter
from simctl.adapters.base import SimulatorAdapter
from simctl.adapters.registry import load_from_config
from simctl.core.case import CaseData, load_case, resolve_case
from simctl.core.discovery import collect_existing_run_ids
from simctl.core.exceptions import ParameterValidationError, SimctlError
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


def _build_job_config(job: Any) -> dict[str, Any]:
    """Build a job config dict from a JobData instance or raw dict.

    Supports both standard mode (nodes/ntasks) and rsc mode
    (processes/threads/cores).

    Args:
        job: JobData instance or raw job dict.

    Returns:
        Job configuration dictionary for job script generation.
    """
    from simctl.core.case import JobData

    if isinstance(job, JobData):
        config: dict[str, Any] = {
            "partition": job.partition,
            "walltime": job.walltime,
        }
        if job.rsc:
            config["rsc"] = True
            config["processes"] = job.processes
            config["threads"] = job.threads
            config["cores"] = job.cores
        else:
            config["nodes"] = job.nodes
            config["ntasks"] = job.ntasks
        if job.modules:
            config["modules"] = list(job.modules)
        if job.pre_commands:
            config["pre_commands"] = list(job.pre_commands)
        if job.post_commands:
            config["post_commands"] = list(job.post_commands)
        return config

    # Fallback for raw dict
    result: dict[str, Any] = {
        "partition": job.get("partition", ""),
        "walltime": job.get("walltime", "01:00:00"),
    }
    if job.get("rsc"):
        result["rsc"] = True
        result["processes"] = job.get("processes", 1)
        result["threads"] = job.get("threads", 1)
        result["cores"] = job.get("cores", 1)
    else:
        result["nodes"] = job.get("nodes", 1)
        result["ntasks"] = job.get("ntasks", 1)
    for key in ("modules", "pre_commands", "post_commands"):
        if key in job:
            result[key] = list(job[key])
    return result


def _build_manifest_job(job: Any) -> dict[str, Any]:
    """Build the [job] section for manifest.toml from JobData.

    Args:
        job: JobData instance.

    Returns:
        Job section dict for the manifest.
    """
    from simctl.core.case import JobData

    if not isinstance(job, JobData):
        return {
            "scheduler": "slurm",
            "job_id": "",
            "submitted_at": "",
        }

    result: dict[str, Any] = {
        "scheduler": "slurm",
        "job_id": "",
        "partition": job.partition,
        "walltime": job.walltime,
        "submitted_at": "",
    }
    if job.rsc:
        result["rsc"] = True
        result["processes"] = job.processes
        result["threads"] = job.threads
        result["cores"] = job.cores
    else:
        result["nodes"] = job.nodes
        result["ntasks"] = job.ntasks
    return result


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
        job=_build_manifest_job(case_data.job),
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


def _copy_case_files(case_dir: Path, input_dir: Path) -> None:
    """Copy input template files from the case directory into the run's input/.

    Copies from ``case_dir/input/`` if it exists, preserving directory
    structure.  ``case.toml`` and other top-level metadata are never copied.
    """
    src_dir = case_dir / "input"
    if not src_dir.is_dir():
        return
    input_dir.mkdir(parents=True, exist_ok=True)
    for src in src_dir.rglob("*"):
        if not src.is_file():
            continue
        rel = src.relative_to(src_dir)
        dest = input_dir / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)


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
    # 1. Validate parameters (before creating directories)
    case_section = {**case_data.raw.get("case", {}), "case_dir": str(case_data.case_dir)}
    validation_data = {"case": case_section, "params": params}
    issues = adapter.validate_params(validation_data)
    if issues:
        warnings = [i for i in issues if i.severity == "warning"]
        errors = [i for i in issues if i.severity == "error"]
        for w in warnings:
            typer.echo(f"  Warning: {w.message}", err=True)
        if errors:
            for e in errors:
                typer.echo(f"  Error: {e.message}", err=True)
            raise ParameterValidationError(issues)

    # 2. Create run directory
    run_info = create_run(
        parent_dir,
        existing_ids,
        display_name=display_name,
        params=params,
    )

    # 3. Copy all files from case directory into input/
    _copy_case_files(case_data.case_dir, run_info.run_dir / "input")

    # 3b. Render input files via adapter (overwrites copied templates with
    #     parameter-applied versions)
    adapter.render_inputs(
        validation_data,
        run_info.run_dir,
    )

    # 4. Resolve runtime and build execution command
    sim_config = _get_simulator_config(project, case_data.simulator)
    resolver_mode = sim_config.get("resolver_mode", "package")
    runtime_info = adapter.resolve_runtime(sim_config, resolver_mode)
    program_cmd = adapter.build_program_command(runtime_info, run_info.run_dir)

    # 5. Build launcher exec line and generate job.sh
    ntasks = case_data.job.processes if case_data.job.rsc else case_data.job.ntasks
    exec_line = launcher.build_exec_line(
        program_cmd,
        ntasks,
    )
    job_config = _build_job_config(case_data.job)

    # Build setup commands: venv activation + launcher setup
    setup_cmds: list[str] = []
    venv_activate = project.root_dir / ".venv" / "bin" / "activate"
    if venv_activate.exists():
        setup_cmds.append(f"source {venv_activate}")
    setup_cmds.extend(launcher.setup_commands)

    generate_job_script(
        run_info.run_dir,
        job_config,
        exec_line,
        run_id=run_info.run_id,
        resource_style=launcher.resource_style,
        modules=launcher.modules + list(sim_config.get("modules", [])),
        extra_sbatch=launcher.extra_sbatch,
        extra_env=launcher.site_env,
        setup_commands=setup_cmds,
        stdout_format=launcher.stdout_format,
        stderr_format=launcher.stderr_format,
    )

    # 6. Build and write manifest
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

    # 7. Track the new ID so subsequent runs in the same sweep won't collide
    existing_ids.add(run_info.run_id)

    return run_info


def create(
    case_name: Annotated[
        str,
        typer.Argument(
            help=(
                "Case name to create a run from, or 'survey' to expand "
                "survey.toml in the current directory."
            ),
        ),
    ],
    dest: Annotated[
        Optional[Path],
        typer.Option("--dest", "-d", help="Destination directory (defaults to cwd)."),
    ] = None,
) -> None:
    """Create run(s) in the current directory.

    Examples:
      cd runs/experiment && simctl create flat_surface
      cd runs/mag_scan   && simctl create survey
    """
    target_dir = (dest or Path.cwd()).resolve()

    if case_name == "survey":
        _create_survey(target_dir)
    else:
        _create_single(case_name, target_dir)


def _create_single(case_name: str, target_dir: Path) -> None:
    """Create a single run from a case template."""
    # Load project
    project = _load_project_config(target_dir)

    # Resolve and load case
    try:
        case_dir = resolve_case(case_name, project.root_dir)
        case_data = load_case(case_dir)
    except SimctlError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    # Validate cross-references
    if case_data.simulator not in project.simulators:
        typer.echo(
            f"Error: simulator '{case_data.simulator}' in case.toml "
            f"not found in simulators.toml. "
            f"Available: {', '.join(project.simulators) or '(none)'}",
            err=True,
        )
        raise typer.Exit(code=1)
    if case_data.launcher not in project.launchers:
        typer.echo(
            f"Error: launcher '{case_data.launcher}' in case.toml "
            f"not found in launchers.toml. "
            f"Available: {', '.join(project.launchers) or '(none)'}",
            err=True,
        )
        raise typer.Exit(code=1)

    # Get adapter and launcher
    adapter = _get_adapter_instance(project, case_data.simulator)
    launcher = _get_launcher(project, case_data.launcher)

    # Collect existing run IDs for dedup
    runs_dir = project.root_dir / "runs"
    existing_ids = collect_existing_run_ids(runs_dir)

    # Ensure destination exists
    target_dir.mkdir(parents=True, exist_ok=True)

    # Generate the run
    try:
        run_info = _generate_run(
            parent_dir=target_dir,
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


def _create_survey(survey_dir: Path) -> None:
    """Expand survey.toml into multiple runs."""
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
        merged_params = {**case_data.params, **combo}
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

    typer.echo(f"Created {len(created_runs)} runs in {survey_dir}")
    for run_info in created_runs:
        name_part = f" ({run_info.display_name})" if run_info.display_name else ""
        typer.echo(f"  {run_info.run_id}{name_part}")


# Keep sweep as an alias for backwards compatibility
def sweep(
    survey_dir: Annotated[
        Optional[Path],
        typer.Argument(help="Directory containing survey.toml (defaults to cwd)."),
    ] = None,
) -> None:
    """Generate all runs from a survey.toml parameter sweep.

    Alias for 'simctl create survey'. Kept for backwards compatibility.
    """
    target = (survey_dir or Path.cwd()).resolve()
    _create_survey(target)
