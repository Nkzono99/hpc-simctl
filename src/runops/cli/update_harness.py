"""CLI command for updating harness files in an existing project.

``runops update-harness`` re-renders all agent-harness templates (CLAUDE.md,
AGENTS.md, .claude/skills/, .claude/rules/, .claude/settings.json, etc.)
from the current version of runops and writes them into the project.

Collision detection:  If the on-disk file matches the hash recorded in
``.runops/harness.lock``, it is assumed to be unedited and is silently
overwritten.  Otherwise the new content is written to ``<path>.new`` so
the user can merge manually.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Annotated, Optional

import typer

from runops.core.exceptions import SimctlError
from runops.core.project import find_project_root, load_project
from runops.harness.builder import (
    build_harness_bundle,
    hash_file,
    load_harness_lock,
    read_upstream_feedback_setting,
    save_harness_lock,
)


def _pull_tools_repo(project_dir: Path) -> str | None:
    """``git pull`` the ``tools/runops`` clone.

    Returns:
        Short status message, or ``None`` if the repo does not exist.
    """
    runops_dir = project_dir / "tools" / "runops"
    if not (runops_dir / ".git").is_dir():
        return None

    result = subprocess.run(
        ["git", "pull", "--ff-only"],
        cwd=str(runops_dir),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.returncode == 0:
        stdout = (result.stdout or "").strip()
        if "Already up to date" in stdout:
            return "already up to date"
        return "updated"
    return f"pull failed: {(result.stderr or '').strip()[:200]}"


def _get_knowledge_imports_path(project_dir: Path) -> str:
    """Return the knowledge imports relative path, if any."""
    imports_file = project_dir / ".runops" / "knowledge" / "enabled" / "imports.md"
    if imports_file.is_file():
        return ".runops/knowledge/enabled/imports.md"
    return ""


def update_harness(
    path: Annotated[
        Optional[Path],
        typer.Argument(help="Project directory (defaults to cwd)."),
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Show what would be updated without writing."),
    ] = False,
    force: Annotated[
        bool,
        typer.Option("--force", "-f", help="Overwrite even if user-edited."),
    ] = False,
    adopt: Annotated[
        bool,
        typer.Option(
            "--adopt",
            help="Adopt current on-disk files into the lock without overwriting.",
        ),
    ] = False,
    skip_pull: Annotated[
        bool,
        typer.Option("--skip-pull", help="Skip 'git pull' on tools/runops."),
    ] = False,
    only: Annotated[
        Optional[str],
        typer.Option(
            "--only",
            help=(
                "Comma-separated list of files to update"
                " (e.g. 'CLAUDE.md,.claude/rules')."
            ),
        ),
    ] = None,
) -> None:
    """Re-render harness files from the current runops templates.

    Files that have not been manually edited since the last init/update
    are silently overwritten.  Files with user edits are written as
    ``<path>.new`` — review the diff and merge manually.

    Use ``--force`` to overwrite all files regardless of user edits.
    Use ``--adopt`` to accept the current on-disk state into the lock
    (useful for first-time migration of an existing project).

    Examples:
      runops update-harness                   # update all harness files
      runops update-harness --dry-run         # preview changes
      runops update-harness --force           # force-overwrite everything
      runops update-harness --adopt           # lock current state
      runops update-harness --only CLAUDE.md  # update a single file
    """
    project_dir = (path or Path.cwd()).resolve()

    # Locate project root
    try:
        project_dir = find_project_root(project_dir)
    except SimctlError:
        typer.echo("No runops.toml found. Are you inside a runops project?")
        raise typer.Exit(code=1) from None

    # Pull tools/runops
    if not skip_pull and not dry_run:
        pull_status = _pull_tools_repo(project_dir)
        if pull_status is not None:
            typer.echo(f"tools/runops: {pull_status}")

    # Load project info
    project = load_project(project_dir)
    project_name = project.name
    simulator_names = list(project.simulators.keys())

    # Read [harness] settings
    upstream_feedback = read_upstream_feedback_setting(project_dir)

    knowledge_imports_path = _get_knowledge_imports_path(project_dir)

    harness = build_harness_bundle(
        project_name,
        simulator_names,
        upstream_feedback=upstream_feedback,
        knowledge_imports_path=knowledge_imports_path,
    )

    # Filter by --only
    only_prefixes: list[str] | None = None
    if only:
        only_prefixes = [p.strip() for p in only.split(",") if p.strip()]

    lock = load_harness_lock(project_dir)
    new_hashes = harness.hashes()

    overwritten: list[str] = []
    written_new: list[str] = []
    unchanged: list[str] = []
    adopted: list[str] = []
    updated_lock = dict(lock)

    for rel_path in sorted(harness.files):
        if only_prefixes and not any(
            rel_path == prefix or rel_path.startswith(prefix)
            for prefix in only_prefixes
        ):
            continue

        full_path = project_dir / rel_path
        content = harness.files[rel_path]
        template_hash = new_hashes[rel_path]

        if adopt:
            # Lock the current on-disk state (or the template if new)
            disk_hash = hash_file(full_path)
            if disk_hash is not None:
                updated_lock[rel_path] = disk_hash
                adopted.append(rel_path)
            else:
                # File doesn't exist — write it and lock the template hash
                if not dry_run:
                    full_path.parent.mkdir(parents=True, exist_ok=True)
                    full_path.write_text(content, encoding="utf-8")
                    updated_lock[rel_path] = template_hash
                overwritten.append(rel_path)
            continue

        if not full_path.exists():
            # New file — just create it
            if not dry_run:
                full_path.parent.mkdir(parents=True, exist_ok=True)
                full_path.write_text(content, encoding="utf-8")
                updated_lock[rel_path] = template_hash
            overwritten.append(rel_path)
            continue

        disk_hash = hash_file(full_path)
        locked_hash = lock.get(rel_path)

        # Check whether the template itself changed
        if disk_hash == template_hash:
            # Already up to date
            updated_lock[rel_path] = template_hash
            unchanged.append(rel_path)
            continue

        if force or (locked_hash is not None and disk_hash == locked_hash):
            # Unedited (matches lock) or --force: safe to overwrite
            if not dry_run:
                full_path.write_text(content, encoding="utf-8")
                updated_lock[rel_path] = template_hash
            overwritten.append(rel_path)
        else:
            # User-edited: write .new file
            new_path = full_path.parent / (full_path.name + ".new")
            if not dry_run:
                new_path.write_text(content, encoding="utf-8")
                updated_lock[rel_path] = template_hash
            written_new.append(rel_path)

    if not dry_run:
        save_harness_lock(project_dir, updated_lock)

    # Report
    prefix = "[dry-run] " if dry_run else ""
    if adopt and adopted:
        typer.echo(f"{prefix}Adopted {len(adopted)} file(s) into harness.lock:")
        for p in adopted:
            typer.echo(f"  {p}")
    if overwritten:
        typer.echo(f"{prefix}Updated {len(overwritten)} file(s):")
        for p in overwritten:
            typer.echo(f"  {p}")
    if written_new:
        n_new = len(written_new)
        typer.echo(f"{prefix}Wrote {n_new} .new file(s) (manual merge needed):")
        for p in written_new:
            typer.echo(f"  {p} -> {p}.new")
    if unchanged:
        typer.echo(f"{prefix}{len(unchanged)} file(s) already up to date.")
    if not overwritten and not written_new and not adopted:
        typer.echo(f"{prefix}All harness files are up to date.")
