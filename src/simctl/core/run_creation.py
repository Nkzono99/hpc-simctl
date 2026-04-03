"""Shared run creation workflows used by CLI commands and agents."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from simctl.adapters import get as get_adapter
from simctl.adapters.base import SimulatorAdapter
from simctl.adapters.registry import load_from_config
from simctl.core.case import CaseData, JobData, load_case, resolve_case
from simctl.core.discovery import collect_existing_run_ids
from simctl.core.exceptions import ParameterValidationError, ProjectConfigError
from simctl.core.manifest import ManifestData, write_manifest
from simctl.core.project import ProjectConfig, find_project_root, load_project
from simctl.core.run import RunInfo, create_run
from simctl.core.site import SiteProfile, load_site_profile
from simctl.core.survey import expand_survey, generate_display_name, load_survey
from simctl.jobgen.generator import generate_job_script
from simctl.launchers.base import Launcher, load_launchers


@dataclass(frozen=True)
class CreatedRunResult:
    """One created run plus non-fatal validation warnings."""

    run_info: RunInfo
    warnings: tuple[str, ...] = ()


def load_project_from_path(path: Path) -> ProjectConfig:
    """Locate the project root for a path and load its configuration."""
    root = find_project_root(path)
    return load_project(root)


def load_adapter_for_simulator(
    project: ProjectConfig,
    simulator_name: str,
) -> SimulatorAdapter:
    """Instantiate the adapter referenced by a simulator entry."""
    load_from_config(project.simulators)
    sim_config = project.simulators.get(simulator_name, {})
    adapter_name = sim_config.get("adapter", simulator_name)
    try:
        adapter_cls = get_adapter(adapter_name)
    except KeyError as exc:
        raise ProjectConfigError(str(exc)) from exc
    return adapter_cls()


def load_launcher_for_name(
    project: ProjectConfig,
    launcher_name: str,
) -> Launcher:
    """Instantiate a launcher from project configuration."""
    try:
        launchers = load_launchers(project.launchers)
    except Exception as exc:
        raise ProjectConfigError(f"Error loading launchers: {exc}") from exc

    if launcher_name not in launchers:
        available = sorted(launchers.keys())
        raise ProjectConfigError(
            f"Launcher profile '{launcher_name}' not found. Available: {available}"
        )
    return launchers[launcher_name]


def validate_case_references(project: ProjectConfig, case_data: CaseData) -> None:
    """Ensure a case refers to known simulator and launcher entries."""
    if case_data.simulator not in project.simulators:
        available = ", ".join(project.simulators) or "(none)"
        raise ProjectConfigError(
            f"simulator '{case_data.simulator}' in case.toml "
            f"not found in simulators.toml. Available: {available}"
        )
    if case_data.launcher not in project.launchers:
        available = ", ".join(project.launchers) or "(none)"
        raise ProjectConfigError(
            f"launcher '{case_data.launcher}' in case.toml "
            f"not found in launchers.toml. Available: {available}"
        )


def _get_simulator_config(
    project: ProjectConfig,
    simulator_name: str,
) -> dict[str, Any]:
    return dict(project.simulators.get(simulator_name, {}))


def _build_job_config(job: JobData | dict[str, Any]) -> dict[str, Any]:
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
            if job.memory:
                config["memory"] = job.memory
            if job.gpus:
                config["gpus"] = job.gpus
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

    result: dict[str, Any] = {
        "partition": job.get("partition", ""),
        "walltime": job.get("walltime", "01:00:00"),
    }
    if job.get("rsc"):
        result["rsc"] = True
        result["processes"] = job.get("processes", 1)
        result["threads"] = job.get("threads", 1)
        result["cores"] = job.get("cores", 1)
        if job.get("memory"):
            result["memory"] = job["memory"]
        if job.get("gpus"):
            result["gpus"] = job["gpus"]
    else:
        result["nodes"] = job.get("nodes", 1)
        result["ntasks"] = job.get("ntasks", 1)
    for key in ("modules", "pre_commands", "post_commands"):
        if key in job:
            result[key] = list(job[key])
    return result


def _build_manifest_job(job: JobData | dict[str, Any]) -> dict[str, Any]:
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
        if job.memory:
            result["memory"] = job.memory
        if job.gpus:
            result["gpus"] = job.gpus
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


def _merge_site_modules(
    site: SiteProfile,
    simulator_name: str,
    sim_config: dict[str, Any],
) -> SiteProfile:
    sim_extra_modules = list(sim_config.get("modules", []))
    if not sim_extra_modules:
        return site

    merged_sim_modules = dict(site.simulator_modules)
    existing = list(merged_sim_modules.get(simulator_name, []))
    for module in sim_extra_modules:
        if module not in existing:
            existing.append(module)
    merged_sim_modules[simulator_name] = existing
    return SiteProfile(
        name=site.name,
        resource_style=site.resource_style,
        modules=list(site.modules),
        simulator_modules=merged_sim_modules,
        stdout_format=site.stdout_format,
        stderr_format=site.stderr_format,
        extra_sbatch=list(site.extra_sbatch),
        env=dict(site.env),
        setup_commands=list(site.setup_commands),
    )


def create_prepared_run(
    parent_dir: Path,
    case_data: CaseData,
    project: ProjectConfig,
    adapter: SimulatorAdapter,
    launcher: Launcher,
    site: SiteProfile,
    *,
    existing_ids: set[str] | None = None,
    params: dict[str, Any] | None = None,
    display_name: str = "",
    survey_id: str = "",
    variation_keys: list[str] | None = None,
) -> CreatedRunResult:
    """Generate one run from already-resolved project/case dependencies."""
    effective_params = dict(case_data.params)
    if params:
        effective_params.update(params)

    case_section = {
        **case_data.raw.get("case", {}),
        "case_dir": str(case_data.case_dir),
    }
    validation_data = {"case": case_section, "params": effective_params}
    issues = adapter.validate_params(validation_data)

    warnings = tuple(i.message for i in issues if i.severity == "warning")
    errors = [i for i in issues if i.severity == "error"]
    if errors:
        raise ParameterValidationError(issues)

    known_ids = existing_ids
    if known_ids is None:
        known_ids = collect_existing_run_ids(project.root_dir / "runs")

    run_info = create_run(
        parent_dir,
        known_ids,
        display_name=display_name,
        params=effective_params,
    )

    _copy_case_files(case_data.case_dir, run_info.run_dir / "input")
    adapter.render_inputs(validation_data, run_info.run_dir)

    sim_config = _get_simulator_config(project, case_data.simulator)
    resolver_mode = sim_config.get("resolver_mode", "package")
    runtime_info = adapter.resolve_runtime(sim_config, resolver_mode)
    program_cmd = adapter.build_program_command(runtime_info, run_info.run_dir)
    version_commands = adapter.build_version_capture_commands(
        runtime_info,
        program_cmd,
        run_info.run_dir,
    )

    ntasks = case_data.job.processes if case_data.job.rsc else case_data.job.ntasks
    exec_line = launcher.build_exec_line(program_cmd, ntasks)
    job_config = _build_job_config(case_data.job)

    extra_setup: list[str] = []
    venv_activate = project.root_dir / ".venv" / "bin" / "activate"
    if venv_activate.exists():
        extra_setup.append(f"source {venv_activate}")

    effective_site = _merge_site_modules(site, case_data.simulator, sim_config)
    generate_job_script(
        run_info.run_dir,
        job_config,
        exec_line,
        run_id=run_info.run_id,
        site=effective_site,
        simulator_name=case_data.simulator,
        extra_setup_commands=extra_setup,
        version_commands=version_commands,
    )

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
    known_ids.add(run_info.run_id)

    return CreatedRunResult(run_info=run_info, warnings=warnings)


def create_case_run(
    project: ProjectConfig,
    case_name: str,
    *,
    dest_dir: Path | None = None,
    display_name: str = "",
    params: dict[str, Any] | None = None,
) -> CreatedRunResult:
    """Resolve a case and create one run."""
    case_dir = resolve_case(case_name, project.root_dir)
    case_data = load_case(case_dir)
    validate_case_references(project, case_data)

    adapter = load_adapter_for_simulator(project, case_data.simulator)
    launcher = load_launcher_for_name(project, case_data.launcher)
    site = load_site_profile(project.root_dir)
    target_dir = dest_dir or (project.root_dir / "runs" / case_name)
    target_dir.mkdir(parents=True, exist_ok=True)

    return create_prepared_run(
        parent_dir=target_dir,
        case_data=case_data,
        project=project,
        adapter=adapter,
        launcher=launcher,
        site=site,
        params=params,
        display_name=display_name or case_data.name,
        existing_ids=collect_existing_run_ids(project.root_dir / "runs"),
    )


def create_survey_runs(
    project: ProjectConfig,
    survey_dir: Path,
) -> list[CreatedRunResult]:
    """Expand a survey and create all runs declared by it."""
    survey_data = load_survey(survey_dir)
    case_dir = resolve_case(survey_data.base_case, project.root_dir)
    case_data = load_case(case_dir)

    simulator_name = survey_data.simulator or case_data.simulator
    launcher_name = survey_data.launcher or case_data.launcher
    adapter = load_adapter_for_simulator(project, simulator_name)
    launcher = load_launcher_for_name(project, launcher_name)
    site = load_site_profile(project.root_dir)

    combinations = expand_survey(survey_data.axes, survey_data.linked)
    if not combinations:
        return []

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
    for group in survey_data.linked:
        variation_keys.extend(group.keys())

    existing_ids = collect_existing_run_ids(project.root_dir / "runs")
    results: list[CreatedRunResult] = []
    for combo in combinations:
        merged_params = {**case_data.params, **combo}
        display_name = generate_display_name(
            survey_data.naming_template,
            merged_params,
        )
        results.append(
            create_prepared_run(
                parent_dir=survey_dir,
                case_data=effective_case,
                project=project,
                adapter=adapter,
                launcher=launcher,
                site=site,
                existing_ids=existing_ids,
                params=merged_params,
                display_name=display_name,
                survey_id=survey_data.id,
                variation_keys=variation_keys,
            )
        )
    return results
