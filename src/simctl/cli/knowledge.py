"""CLI commands for knowledge management."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Optional

import typer

from simctl.core.actions import ActionStatus
from simctl.core.actions import add_fact as add_fact_action
from simctl.core.exceptions import KnowledgeSourceError, SimctlError
from simctl.core.knowledge import (
    FACT_TYPES,
    INSIGHT_TYPES,
    Insight,
    add_link,
    get_insights_dir,
    list_insights,
    load_links,
    query_facts,
    remove_link,
    sync_insights,
    write_insight,
)
from simctl.core.knowledge_source import (
    ExternalKnowledgeMount,
    KnowledgeSource,
    collect_external_knowledge,
    load_knowledge_config,
    remove_knowledge_source,
    render_imports,
    save_knowledge_source,
    sync_all_sources,
    sync_source,
    validate_source_structure,
)
from simctl.core.project import find_project_root

knowledge_app = typer.Typer(
    name="knowledge",
    help="Manage project knowledge, external sources, and legacy links.",
    no_args_is_help=True,
)

source_app = typer.Typer(
    name="source",
    help="Manage configured external knowledge sources.",
    no_args_is_help=True,
)


def _find_root() -> Path:
    """Find project root or exit."""
    try:
        return find_project_root(Path.cwd().resolve())
    except SimctlError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1) from None


@knowledge_app.command("save")
def save(
    name: Annotated[
        str,
        typer.Argument(help="Insight name (used as filename)."),
    ],
    insight_type: Annotated[
        str,
        typer.Option(
            "--type",
            "-t",
            help=("Insight type: constraint, result, analysis, or dependency."),
        ),
    ] = "result",
    simulator: Annotated[
        str,
        typer.Option(
            "--simulator",
            "-s",
            help="Simulator this insight applies to.",
        ),
    ] = "",
    tags: Annotated[
        Optional[str],
        typer.Option(
            "--tags",
            help="Comma-separated tags.",
        ),
    ] = None,
    message: Annotated[
        Optional[str],
        typer.Option(
            "--message",
            "-m",
            help="Insight content (markdown). If omitted, reads from stdin.",
        ),
    ] = None,
) -> None:
    """Save a knowledge insight to .simctl/insights/.

    Examples:
      simctl knowledge save emses_cfl -t constraint -s emses \\
        -m "dt > 1.5 causes instability with nx=64 grid"
      echo "Survey results..." | simctl knowledge save mag_results -t result
    """
    if insight_type not in INSIGHT_TYPES:
        typer.echo(
            f"Invalid type '{insight_type}'. "
            f"Must be one of: {', '.join(sorted(INSIGHT_TYPES))}",
            err=True,
        )
        raise typer.Exit(code=1)

    root = _find_root()

    if message is None:
        typer.echo("Enter insight content (Ctrl+D to finish):")
        import sys

        message = sys.stdin.read()

    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []

    insight = Insight(
        name=name,
        type=insight_type,
        simulator=simulator,
        tags=tag_list,
        source_project=root.name,
        content=message.strip(),
    )

    insights_dir = get_insights_dir(root)
    path = write_insight(insights_dir, insight)
    typer.echo(f"Saved: {path.relative_to(root)}")


@knowledge_app.command("list")
def list_cmd(
    simulator: Annotated[
        Optional[str],
        typer.Option(
            "--simulator",
            "-s",
            help="Filter by simulator.",
        ),
    ] = None,
    insight_type: Annotated[
        Optional[str],
        typer.Option("--type", "-t", help="Filter by type."),
    ] = None,
    tag: Annotated[
        Optional[str],
        typer.Option("--tag", help="Filter by tag."),
    ] = None,
    sources: Annotated[
        bool,
        typer.Option(
            "--sources",
            help="Show external knowledge sources instead of insights.",
        ),
    ] = False,
) -> None:
    """List knowledge insights or sources.

    Examples:
      simctl knowledge list
      simctl knowledge list --sources
      simctl knowledge list -s emses -t constraint
    """
    root = _find_root()

    if sources:
        _list_sources(root)
        return

    insights = list_insights(
        root,
        simulator=simulator or "",
        insight_type=insight_type or "",
        tag=tag or "",
    )

    if not insights:
        typer.echo("No insights found.")
        return

    for ins in insights:
        type_badge = f"[{ins.type}]"
        sim_badge = f"({ins.simulator})" if ins.simulator else ""
        tags_str = " " + ", ".join(f"#{t}" for t in ins.tags) if ins.tags else ""
        typer.echo(f"  {ins.name} {type_badge} {sim_badge}{tags_str}")


def _list_sources(root: Path) -> None:
    """Display external knowledge sources and legacy links."""
    entries = collect_external_knowledge(root)
    if not entries:
        typer.echo("No external knowledge configured.")
        return

    _print_external_status(entries, detailed=False)


def _split_external_entries(
    entries: list[ExternalKnowledgeMount],
) -> tuple[list[ExternalKnowledgeMount], list[ExternalKnowledgeMount]]:
    """Split normalized external knowledge entries by origin."""
    sources = [entry for entry in entries if entry.origin == "source"]
    legacy_links = [entry for entry in entries if entry.origin == "legacy_link"]
    return sources, legacy_links


def _print_external_status(
    entries: list[ExternalKnowledgeMount],
    *,
    detailed: bool,
) -> None:
    """Render configured sources and legacy links from a shared view."""
    sources, legacy_links = _split_external_entries(entries)

    if sources:
        typer.echo("Configured knowledge sources:")
        for entry in sources:
            enabled = (
                ", ".join(entry.profiles_enabled)
                if entry.profiles_enabled
                else "(none)"
            )
            available = (
                ", ".join(entry.profiles_available)
                if entry.profiles_available
                else "(none)"
            )
            if detailed:
                status = "mounted" if entry.exists else "not mounted"
                typer.echo(f"\n  [{entry.source_type}] {entry.name} ({status})")
                typer.echo(f"    mount: {entry.display_path}")
                typer.echo(f"    available profiles: {available}")
                typer.echo(f"    enabled profiles: {enabled}")
                continue

            status = "OK" if entry.exists else "NOT MOUNTED"
            typer.echo(f"  {entry.name} [{entry.source_type}] ({status})")
            typer.echo(f"    mount: {entry.display_path}")
            typer.echo(f"    available profiles: {available}")
            typer.echo(f"    enabled profiles:   {enabled}")

    if legacy_links:
        if sources:
            typer.echo("")
        typer.echo("Legacy knowledge links:")
        for entry in legacy_links:
            if detailed:
                status = "available" if entry.exists else "not found"
                typer.echo(
                    f"\n  [{entry.source_type}] {entry.name} (legacy, {status})"
                )
                typer.echo(f"    path: {entry.display_path}")
                continue

            status = "OK" if entry.exists else "NOT FOUND"
            typer.echo(f"  {entry.name} [legacy {entry.source_type}] ({status})")
            typer.echo(f"    path: {entry.display_path}")


@knowledge_app.command("show")
def show(
    name: Annotated[
        str,
        typer.Argument(help="Insight name to display."),
    ],
) -> None:
    """Show a specific insight.

    Examples:
      simctl knowledge show emses_cfl_limit
    """
    root = _find_root()
    insights_dir = root / ".simctl" / "insights"
    path = insights_dir / f"{name}.md"

    if not path.is_file():
        typer.echo(f"Insight not found: {name}", err=True)
        raise typer.Exit(code=1)

    typer.echo(path.read_text())


@knowledge_app.command("sync")
def sync(
    source_name: Annotated[
        Optional[str],
        typer.Argument(help="Sync only this knowledge source (optional)."),
    ] = None,
    simulator: Annotated[
        Optional[str],
        typer.Option(
            "--simulator",
            "-s",
            help="Sync only insights for this simulator.",
        ),
    ] = None,
) -> None:
    """Sync knowledge sources and import insights from linked projects.

    When a source name is given, only that source is synced.
    Otherwise, all knowledge sources are synced, then insight
    links are imported. Legacy links from ``.simctl/links.toml``
    are still supported and can be synced by name.

    Examples:
      simctl knowledge sync
      simctl knowledge sync shared-lab-knowledge
      simctl knowledge sync -s emses
    """
    root = _find_root()
    matched_source = False
    matched_link = False

    # Sync knowledge sources
    config = load_knowledge_config(root)
    if config is not None and config.sources:
        if source_name:
            # Sync single source
            matched = [s for s in config.sources if s.name == source_name]
            for src in matched:
                matched_source = True
                try:
                    status = sync_source(root, src)
                    typer.echo(f"  [{src.source_type}] {src.name}: {status}")
                except KnowledgeSourceError as e:
                    typer.echo(f"  [{src.source_type}] {src.name}: error - {e}")
        else:
            # Sync all sources
            matched_source = True
            typer.echo("Syncing knowledge sources...")
            results = sync_all_sources(root, config)
            for name, status in results:
                typer.echo(f"  {name}: {status}")

        if matched_source:
            # Re-render imports after source sync
            try:
                render_imports(root, config)
                typer.echo("Rendered imports.md")
            except Exception as e:
                typer.echo(f"Warning: failed to render imports: {e}", err=True)

    # Sync insights from project links (existing behavior)
    links = load_links(root)
    selected_links = (
        [link for link in links if link.name == source_name] if source_name else links
    )
    if selected_links:
        matched_link = True
        typer.echo("Syncing insights from legacy linked projects...")
        for link in selected_links:
            exists = link.path.is_dir()
            status_str = "" if exists else " (not found)"
            typer.echo(f"  [{link.link_type}] {link.name}: {link.path}{status_str}")
        imported, skipped = sync_insights(
            root,
            simulator=simulator or "",
            link_names=[link.name for link in selected_links],
        )
        typer.echo(f"Imported: {imported}, Skipped (exists): {skipped}")

    if source_name and not matched_source and not matched_link:
        typer.echo(f"Source or legacy link not found: {source_name}", err=True)
        raise typer.Exit(code=1)
    if not matched_source and not matched_link:
        typer.echo("No knowledge sources or links configured.")


@knowledge_app.command("links")
def links_cmd() -> None:
    """Show configured legacy project links.

    Examples:
      simctl knowledge links
    """
    root = _find_root()
    links = load_links(root)

    if not links:
        typer.echo(
            "No legacy links configured. Use "
            "'simctl knowledge link <path_or_url>' to add one."
        )
        return

    for link in links:
        exists = link.path.is_dir()
        status = "OK" if exists else "NOT FOUND"
        typer.echo(f"  [{link.link_type}] {link.name}: {link.path} ({status})")


@knowledge_app.command("link")
def link_cmd(
    target: Annotated[
        str,
        typer.Argument(
            help="Local path or git URL (https://*.git).",
        ),
    ],
    name: Annotated[
        Optional[str],
        typer.Option(
            "--name",
            "-n",
            help="Link name (auto-detected from path/URL).",
        ),
    ] = None,
) -> None:
    """Add a link to another project or shared knowledge repo.

    Local paths are added as project links.
    Git URLs are cloned to .simctl/shared/ and added as shared links.

    Examples:
      simctl knowledge link ../other-experiment
      simctl knowledge link https://github.com/user/knowledge-base.git
      simctl knowledge link ../shared-data --name shared-kb
    """
    root = _find_root()
    try:
        link_name, link_type, resolved = add_link(
            root,
            target,
            name=name or "",
        )
    except RuntimeError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1) from None

    typer.echo(f"Linked [{link_type}] {link_name}: {resolved}")


@knowledge_app.command("unlink")
def unlink_cmd(
    name: Annotated[
        str,
        typer.Argument(help="Link name to remove."),
    ],
) -> None:
    """Remove a project link.

    Examples:
      simctl knowledge unlink other-experiment
    """
    root = _find_root()
    try:
        removed = remove_link(root, name)
    except RuntimeError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1) from None

    if removed:
        typer.echo(f"Unlinked: {name}")
    else:
        typer.echo(f"Link not found: {name}", err=True)
        raise typer.Exit(code=1)


@knowledge_app.command("add-fact")
def add_fact(
    claim: Annotated[
        str,
        typer.Argument(help="The knowledge claim (one sentence)."),
    ],
    fact_type: Annotated[
        str,
        typer.Option(
            "--type",
            "-t",
            help="Fact type: observation, constraint, dependency, policy, hypothesis.",
        ),
    ] = "observation",
    simulator: Annotated[
        str,
        typer.Option(
            "--simulator",
            "-s",
            help="Simulator this fact applies to.",
        ),
    ] = "",
    scope: Annotated[
        str,
        typer.Option(
            "--scope",
            help="Deprecated alias for --scope-text.",
        ),
    ] = "",
    scope_case: Annotated[
        str,
        typer.Option(
            "--scope-case",
            help="Case or case pattern this fact applies to.",
        ),
    ] = "",
    scope_text: Annotated[
        str,
        typer.Option(
            "--scope-text",
            help="Free-text scope description.",
        ),
    ] = "",
    param_name: Annotated[
        str,
        typer.Option(
            "--param-name",
            help="Parameter name this fact is about.",
        ),
    ] = "",
    evidence: Annotated[
        str,
        typer.Option(
            "--evidence",
            help="Deprecated alias for --evidence-kind.",
        ),
    ] = "",
    evidence_kind: Annotated[
        str,
        typer.Option(
            "--evidence-kind",
            help="Evidence kind, e.g. run_observation or calculation.",
        ),
    ] = "",
    evidence_ref: Annotated[
        str,
        typer.Option(
            "--evidence-ref",
            help="Reference to evidence source, e.g. run:R20260330-0001.",
        ),
    ] = "",
    confidence: Annotated[
        str,
        typer.Option(
            "--confidence",
            "-c",
            help="Confidence level: high, medium, low.",
        ),
    ] = "medium",
    source_run: Annotated[
        str,
        typer.Option("--run", help="Source run ID."),
    ] = "",
    tags: Annotated[
        Optional[str],
        typer.Option("--tags", help="Comma-separated tags."),
    ] = None,
    supersedes: Annotated[
        str,
        typer.Option(
            "--supersedes",
            help="ID of an older fact this one replaces.",
        ),
    ] = "",
) -> None:
    """Add a structured fact to .simctl/facts.toml.

    Facts are machine-readable knowledge claims with provenance.
    Unlike insights (free-form markdown), facts are designed for
    programmatic use by AI agents.

    Examples:
      simctl knowledge add-fact "CFL limit: dt must be < 1.0 for emses" \\
        --type constraint --simulator emses --param-name tmgrid.dt \\
        --scope-text "baseline scan" --confidence high \\
        --evidence-kind run_observation --evidence-ref run:R20260330-0001
    """
    if confidence not in ("high", "medium", "low"):
        typer.echo(
            f"Invalid confidence '{confidence}'. Must be: high, medium, low.",
            err=True,
        )
        raise typer.Exit(code=1)
    if fact_type not in FACT_TYPES:
        typer.echo(
            f"Invalid type '{fact_type}'. "
            f"Must be one of: {', '.join(sorted(FACT_TYPES))}.",
            err=True,
        )
        raise typer.Exit(code=1)

    root = _find_root()
    existing_facts = list(query_facts(root, exclude_superseded=False))
    if supersedes and all(f.id != supersedes for f in existing_facts):
        typer.echo(f"Error: superseded fact not found: {supersedes}", err=True)
        raise typer.Exit(code=1)

    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []

    result = add_fact_action(
        root,
        claim=claim,
        fact_type=fact_type,
        simulator=simulator,
        scope_case=scope_case,
        scope_text=scope_text or scope,
        param_name=param_name,
        confidence=confidence,
        source_run=source_run,
        evidence_kind=evidence_kind or evidence,
        evidence_ref=evidence_ref,
        tags=tag_list,
        supersedes=supersedes,
    )
    if result.status is not ActionStatus.SUCCESS:
        typer.echo(f"Error: {result.message}", err=True)
        raise typer.Exit(code=1)

    typer.echo(f"Saved fact [{result.data['fact_id']}]: {claim}")


@knowledge_app.command("facts")
def facts_cmd(
    scope: Annotated[
        Optional[str],
        typer.Option("--scope", help="Filter by scope."),
    ] = None,
    tag: Annotated[
        Optional[str],
        typer.Option("--tag", help="Filter by tag."),
    ] = None,
    confidence: Annotated[
        Optional[str],
        typer.Option(
            "--confidence",
            "-c",
            help="Minimum confidence: high, medium, low.",
        ),
    ] = None,
) -> None:
    """List structured facts from .simctl/facts.toml.

    Examples:
      simctl knowledge facts
      simctl knowledge facts --scope emses --confidence high
    """
    root = _find_root()
    facts = query_facts(
        root,
        scope=scope or "",
        tag=tag or "",
        min_confidence=confidence or "",
    )

    if not facts:
        typer.echo("No facts found.")
        return

    for f in facts:
        conf_badge = f"[{f.confidence}]"
        scope_str = f" ({f.scope})" if f.scope else ""
        typer.echo(f"  {f.id} {conf_badge}{scope_str}: {f.claim}")


# ---------- Knowledge source commands ----------


@knowledge_app.command("attach", hidden=True)
def attach(
    source_type: Annotated[
        str,
        typer.Argument(help="Source type: git or path."),
    ],
    name: Annotated[
        str,
        typer.Argument(help="Source name (identifier)."),
    ],
    url_or_path: Annotated[
        str,
        typer.Argument(help="Git URL or filesystem path."),
    ],
    ref: Annotated[
        str,
        typer.Option("--ref", help="Git ref to checkout (git sources only)."),
    ] = "main",
    mount: Annotated[
        Optional[str],
        typer.Option("--mount", help="Override mount path."),
    ] = None,
    profiles: Annotated[
        Optional[str],
        typer.Option("--profiles", help="Comma-separated profile names to enable."),
    ] = None,
    no_sync: Annotated[
        bool,
        typer.Option("--no-sync", help="Skip initial sync."),
    ] = False,
) -> None:
    """Attach an external knowledge source to this project.

    Examples:
      simctl knowledge attach git shared-kb git@github.com:lab/kb.git
      simctl knowledge attach path personal-kb ../hpc-knowledge
      simctl knowledge attach git lab-kb \\
        https://github.com/lab/kb.git --profiles common,emses
    """
    if source_type not in ("git", "path"):
        msg = f"Invalid source type: {source_type}. Must be 'git' or 'path'."
        typer.echo(msg, err=True)
        raise typer.Exit(code=1)

    root = _find_root()
    mount_path = mount or f"refs/knowledge/{name}"
    profile_list = (
        [p.strip() for p in profiles.split(",") if p.strip()] if profiles else []
    )

    source = KnowledgeSource(
        name=name,
        source_type=source_type,
        url=url_or_path,
        ref=ref if source_type == "git" else "main",
        mount=mount_path,
        profiles=profile_list,
    )

    try:
        save_knowledge_source(root, source)
    except KnowledgeSourceError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1) from None

    typer.echo(f"Attached [{source_type}] {name}: {url_or_path}")
    typer.echo(f"  mount: {mount_path}")
    if profile_list:
        typer.echo(f"  profiles: {', '.join(profile_list)}")

    if not no_sync:
        typer.echo("Syncing...")
        try:
            status = sync_source(root, source)
            typer.echo(f"  {name}: {status}")
        except KnowledgeSourceError as e:
            typer.echo(f"  Sync failed: {e}", err=True)

        # Validate structure
        source_dir = root / mount_path
        if source_dir.is_dir():
            issues = validate_source_structure(source_dir)
            if issues:
                typer.echo("Validation warnings:")
                for issue in issues:
                    typer.echo(f"  - {issue}")


@knowledge_app.command("detach", hidden=True)
def detach(
    name: Annotated[
        str,
        typer.Argument(help="Source name to remove."),
    ],
    keep_files: Annotated[
        bool,
        typer.Option("--keep-files", help="Keep mounted files."),
    ] = False,
) -> None:
    """Detach a knowledge source from this project.

    Examples:
      simctl knowledge detach shared-kb
      simctl knowledge detach shared-kb --keep-files
    """
    root = _find_root()

    # Find mount path before removing
    config = load_knowledge_config(root)
    mount_path: Path | None = None
    if config:
        for src in config.sources:
            if src.name == name:
                mount_path = root / src.mount
                break

    try:
        removed = remove_knowledge_source(root, name)
    except KnowledgeSourceError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1) from None

    if not removed:
        typer.echo(f"Source not found: {name}", err=True)
        raise typer.Exit(code=1)

    typer.echo(f"Detached: {name}")

    if not keep_files and mount_path and mount_path.exists():
        import shutil

        if mount_path.is_symlink():
            mount_path.unlink()
        else:
            shutil.rmtree(mount_path)
        typer.echo(f"  Removed: {mount_path.relative_to(root)}")


@knowledge_app.command("render", hidden=True)
def render() -> None:
    """Render imports.md from enabled knowledge profiles.

    Generates .simctl/knowledge/enabled/imports.md containing
    @import directives for each enabled profile.

    Examples:
      simctl knowledge render
    """
    root = _find_root()
    config = load_knowledge_config(root)

    if config is None:
        typer.echo("No [knowledge] section in simproject.toml.")
        raise typer.Exit(code=1)

    imports_path = render_imports(root, config)
    rel = imports_path.relative_to(root)
    typer.echo(f"Rendered: {rel}")

    content = imports_path.read_text().strip()
    if content:
        for line in content.split("\n"):
            if line.startswith("@"):
                typer.echo(f"  {line}")


@knowledge_app.command("status", hidden=True)
def status_cmd() -> None:
    """Show knowledge integration status.

    Examples:
      simctl knowledge status
    """
    root = _find_root()
    config = load_knowledge_config(root)
    external_entries = collect_external_knowledge(root)
    configured_sources, legacy_links = _split_external_entries(external_entries)

    if config is None:
        typer.echo("Knowledge integration: not configured")
        typer.echo(
            "  Add [knowledge] section to simproject.toml"
            " or use 'simctl knowledge attach'. Legacy links remain supported."
        )
    else:
        status = "enabled" if config.enabled else "disabled"
        typer.echo(f"Knowledge integration: {status}")
        typer.echo(f"  mount_dir: {config.mount_dir}")
        typer.echo(f"  derived_dir: {config.derived_dir}")
    typer.echo(f"  sources: {len(configured_sources)}")
    typer.echo(f"  legacy_links: {len(legacy_links)}")

    if external_entries:
        _print_external_status(external_entries, detailed=True)

    if config is None:
        return

    # Check imports.md status
    imports_path = root / config.derived_dir / "enabled" / "imports.md"
    if imports_path.is_file():
        typer.echo(f"\n  imports.md: {imports_path.relative_to(root)} (exists)")
    else:
        typer.echo("\n  imports.md: not generated (run 'simctl knowledge render')")


@source_app.command("list")
def source_list_cmd() -> None:
    """Show configured external knowledge sources and legacy links."""
    root = _find_root()
    _list_sources(root)


source_app.command("attach")(attach)
source_app.command("detach")(detach)
source_app.command("sync")(sync)
source_app.command("render")(render)
source_app.command("status")(status_cmd)

knowledge_app.add_typer(source_app, name="source")
