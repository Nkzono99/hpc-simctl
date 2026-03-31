"""CLI command for creating new case templates."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Optional

import typer

from simctl.core.project import find_project_root


def _detect_simulator(cwd: Path) -> str | None:
    """Detect simulator name from cwd path.

    If cwd is under cases/<simulator>/, return the simulator name.
    """
    parts = cwd.parts
    for i, part in enumerate(parts):
        if part == "cases" and i + 1 < len(parts):
            return parts[i + 1]
    return None


def new(
    case_name: Annotated[
        str,
        typer.Argument(help="Name of the new case to create."),
    ],
    simulator: Annotated[
        Optional[str],
        typer.Option(
            "--simulator", "-s",
            help="Simulator name (auto-detected from cwd if under cases/<sim>/).",
        ),
    ] = None,
    dest: Annotated[
        Optional[Path],
        typer.Option("--dest", "-d", help="Destination directory (defaults to cwd)."),
    ] = None,
    survey: Annotated[
        bool,
        typer.Option(
            "--survey",
            help="Also generate a survey.toml stub in runs/<case_name>/.",
        ),
    ] = False,
) -> None:
    """Create a new case template with simulator-specific boilerplate.

    Auto-detects the simulator from the current directory if under cases/<sim>/.

    Examples:
      cd cases/emses && simctl new flat_surface
      cd cases/beach && simctl new periodic
      simctl new mycase -s emses -d cases/emses
      simctl new mycase -s emses --survey  # also generate survey.toml
    """
    target_dir = (dest or Path.cwd()).resolve()

    # Detect simulator
    sim_name = simulator or _detect_simulator(target_dir)
    if sim_name is None:
        typer.echo(
            "Cannot detect simulator from current directory.\n"
            "Use --simulator/-s or run from inside cases/<simulator>/."
        )
        raise typer.Exit(code=1)

    # Load adapter
    try:
        from simctl.adapters.registry import get_global_registry

        import simctl.adapters  # noqa: F401

        registry = get_global_registry()
        available = registry.list_adapters()

        if sim_name not in available:
            typer.echo(
                f"Unknown simulator: '{sim_name}'. "
                f"Available: {', '.join(available)}"
            )
            raise typer.Exit(code=1)

        adapter_cls = registry.get(sim_name)
    except KeyError as e:
        typer.echo(f"Error: {e}")
        raise typer.Exit(code=1) from None

    # Create case directory
    case_dir = target_dir / case_name
    if case_dir.exists():
        typer.echo(f"Error: {case_dir} already exists.")
        raise typer.Exit(code=1)

    case_dir.mkdir(parents=True)

    # Resolve project root (used for launcher, site profile, and ref templates)
    default_launcher = "srun"
    site_resource_style = "standard"
    project_root: Path | None = None
    try:
        project_root = find_project_root(target_dir)
    except Exception:
        pass

    if project_root:
        try:
            from simctl.core.project import load_project

            project = load_project(project_root)
            launcher_names = list(project.launchers.keys())
            if launcher_names:
                default_launcher = launcher_names[0]

            from simctl.core.site import load_site_profile

            site = load_site_profile(project_root)
            site_resource_style = site.resource_style
        except Exception:
            pass  # Fall back to defaults

    # Look for rich template files in refs/<repo>/
    ref_templates: dict[str, Path] = {}
    try:
        if project_root and hasattr(adapter_cls, "doc_repos"):
            refs_dir = project_root / "refs"
            for _url, repo_name in adapter_cls.doc_repos():
                repo_dir = refs_dir / repo_name
                if not repo_dir.is_dir():
                    continue
                # Look for template input files at repo root
                for candidate_name in ("plasma.toml", "beach.toml"):
                    candidate = repo_dir / candidate_name
                    if candidate.is_file():
                        ref_templates[candidate_name] = candidate
    except Exception:
        pass

    # Write template files
    templates = adapter_cls.case_template()
    created: list[str] = []

    for filename, content in templates.items():
        filepath = case_dir / filename
        # Fill in case name and launcher in case.toml
        if filename == "case.toml":
            content = content.replace('name = ""', f'name = "{case_name}"', 1)
            content = content.replace(
                'launcher = "default"', f'launcher = "{default_launcher}"', 1
            )
            # Replace job fields based on site resource style
            if site_resource_style == "rsc":
                content = content.replace(
                    'partition = ""\nnodes = 1\nntasks = 1\n'
                    'walltime = "01:00:00"\n',
                    'partition = ""\nprocesses = 1\nthreads = 1\n'
                    'cores = 1\nwalltime = "01:00:00"\n',
                )
        # Override with rich template from refs/ if available
        if filename in ref_templates:
            content = ref_templates[filename].read_text(encoding="utf-8")
        filepath.write_text(content, encoding="utf-8")
        created.append(filename)

    typer.echo(f"Created case '{case_name}' for simulator '{sim_name}':")
    typer.echo(f"  Path: {case_dir}")
    for f in created:
        typer.echo(f"    {f}")
    typer.echo(f"\nEdit {case_dir / 'case.toml'} to configure parameters and job settings.")

    # Optionally generate survey.toml stub
    if survey:
        _generate_survey_stub(
            case_name, sim_name, default_launcher,
            project_root=project_root,
            resource_style=site_resource_style,
        )


def _generate_survey_stub(
    case_name: str,
    simulator: str,
    launcher: str,
    *,
    project_root: Path | None = None,
    resource_style: str = "standard",
) -> None:
    """Generate a survey.toml stub under runs/<case_name>/.

    Args:
        case_name: Name of the base case.
        simulator: Simulator name.
        launcher: Launcher profile name.
        project_root: Project root directory (if already resolved).
        resource_style: Site resource style ("standard" or "rsc").
    """
    if project_root is None:
        typer.echo("  Warning: Could not find project root; skipping survey.toml.")
        return

    survey_dir = project_root / "runs" / case_name
    survey_dir.mkdir(parents=True, exist_ok=True)

    # Build the case reference path: <sim>/<case_name> for multi-sim layout
    base_case_ref = f"{simulator}/{case_name}"

    if resource_style == "rsc":
        job_comment = (
            '# partition = ""\n'
            "# processes = 1\n"
            "# threads = 1\n"
            "# cores = 1\n"
            '# walltime = "01:00:00"'
        )
    else:
        job_comment = (
            '# partition = ""\n'
            "# nodes = 1\n"
            "# ntasks = 1\n"
            '# walltime = "01:00:00"'
        )

    content = f"""\
#:schema https://raw.githubusercontent.com/Nkzono99/hpc-simctl/main/schemas/survey.json
[survey]
name = "{case_name} sweep"
base_case = "{base_case_ref}"
simulator = "{simulator}"
launcher = "{launcher}"

[axes]
# Define parameter axes for cartesian product expansion.
# Each key is a dotted parameter path, and the value is a list.
# Example:
# "tmgrid.dt" = [0.5, 1.0, 2.0]
# "species[2].ray_zenith_angle_deg" = [0, 30, 60, 90]

[naming]
# Template for run display names. Use parameter leaf names or underscore forms.
# Example: display_name = "dt{{tmgrid_dt}}_angle{{ray_zenith_angle_deg}}"
display_name = ""

[job]
# Override job settings from case.toml (optional).
{job_comment}
"""
    survey_file = survey_dir / "survey.toml"
    if survey_file.exists():
        typer.echo(f"\n  survey.toml already exists at {survey_dir}, skipping.")
        return

    survey_file.write_text(content, encoding="utf-8")
    typer.echo(f"\nCreated survey stub:")
    typer.echo(f"  Path: {survey_dir / 'survey.toml'}")
    typer.echo(f"  Edit axes and naming, then run: cd {survey_dir} && simctl sweep")
