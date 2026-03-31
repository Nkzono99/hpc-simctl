"""CLI command for creating new case templates."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Optional

import typer

from simctl.core.exceptions import SimctlError
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
) -> None:
    """Create a new case template with simulator-specific boilerplate.

    Auto-detects the simulator from the current directory if under cases/<sim>/.

    Examples:
      cd cases/emses && simctl new flat_surface
      cd cases/beach && simctl new periodic
      simctl new mycase -s emses -d cases/emses
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

    # Resolve default launcher name from project config
    default_launcher = "srun"
    try:
        project_root = find_project_root(target_dir)
        if project_root:
            from simctl.core.project import load_project

            project = load_project(project_root)
            launcher_names = list(project.launchers.keys())
            if launcher_names:
                default_launcher = launcher_names[0]
    except Exception:
        pass  # Fall back to "srun"

    # Look for rich template files in refs/<repo>/
    ref_templates: dict[str, Path] = {}
    try:
        project_root = find_project_root(target_dir)
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
