"""CLI commands for knowledge management."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Optional

import typer

from simctl.core.exceptions import SimctlError
from simctl.core.knowledge import (
    FACT_TYPES,
    INSIGHT_TYPES,
    Fact,
    Insight,
    add_link,
    get_insights_dir,
    list_insights,
    load_links,
    next_fact_id,
    query_facts,
    remove_link,
    save_fact,
    sync_insights,
    write_insight,
)
from simctl.core.project import find_project_root

knowledge_app = typer.Typer(
    name="knowledge",
    help="Manage project knowledge: insights, links, and cross-project sharing.",
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
            "--type", "-t",
            help=(
                "Insight type: constraint, result, analysis, "
                "or dependency."
            ),
        ),
    ] = "result",
    simulator: Annotated[
        str,
        typer.Option(
            "--simulator", "-s",
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
            "--message", "-m",
            help="Insight content (markdown). "
            "If omitted, reads from stdin.",
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

    tag_list = (
        [t.strip() for t in tags.split(",") if t.strip()]
        if tags
        else []
    )

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
            "--simulator", "-s",
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
) -> None:
    """List knowledge insights.

    Examples:
      simctl knowledge list
      simctl knowledge list -s emses -t constraint
    """
    root = _find_root()
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
        tags_str = (
            " " + ", ".join(f"#{t}" for t in ins.tags)
            if ins.tags
            else ""
        )
        typer.echo(
            f"  {ins.name} {type_badge} {sim_badge}{tags_str}"
        )


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
    simulator: Annotated[
        Optional[str],
        typer.Option(
            "--simulator", "-s",
            help="Sync only insights for this simulator.",
        ),
    ] = None,
) -> None:
    """Import insights from linked projects.

    Reads .simctl/links.toml and copies new insights from linked
    projects into this project's .simctl/insights/.

    Examples:
      simctl knowledge sync
      simctl knowledge sync -s emses
    """
    root = _find_root()
    links = load_links(root)

    if not links:
        typer.echo(
            "No links configured. "
            "Create .simctl/links.toml to link projects."
        )
        return

    typer.echo("Syncing from linked projects...")
    for link in links:
        exists = link.path.is_dir()
        status = "" if exists else " (not found)"
        typer.echo(
            f"  [{link.link_type}] {link.name}: "
            f"{link.path}{status}"
        )

    imported, skipped = sync_insights(
        root, simulator=simulator or ""
    )
    typer.echo(f"\nImported: {imported}, Skipped (exists): {skipped}")


@knowledge_app.command("links")
def links_cmd() -> None:
    """Show configured project links.

    Examples:
      simctl knowledge links
    """
    root = _find_root()
    links = load_links(root)

    if not links:
        typer.echo(
            "No links configured. "
            "Use 'simctl knowledge link <path_or_url>' to add one."
        )
        return

    for link in links:
        exists = link.path.is_dir()
        status = "OK" if exists else "NOT FOUND"
        typer.echo(
            f"  [{link.link_type}] {link.name}: "
            f"{link.path} ({status})"
        )


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
            "--name", "-n",
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
            root, target, name=name or "",
        )
    except RuntimeError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1) from None

    typer.echo(
        f"Linked [{link_type}] {link_name}: {resolved}"
    )


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
            "--type", "-t",
            help="Fact type: observation, constraint, dependency, policy, hypothesis.",
        ),
    ] = "observation",
    simulator: Annotated[
        str,
        typer.Option(
            "--simulator", "-s",
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
            "--confidence", "-c",
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
            f"Invalid confidence '{confidence}'. "
            f"Must be: high, medium, low.",
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

    tag_list = (
        [t.strip() for t in tags.split(",") if t.strip()]
        if tags
        else []
    )

    from datetime import datetime, timezone

    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    fact_id = next_fact_id(root)

    fact = Fact(
        id=fact_id,
        claim=claim,
        fact_type=fact_type,
        simulator=simulator,
        scope_case=scope_case,
        scope_text=scope_text or scope,
        param_name=param_name,
        confidence=confidence,
        source_run=source_run,
        source_project=root.name,
        evidence_kind=evidence_kind or evidence,
        evidence_ref=evidence_ref,
        created_at=now,
        tags=tag_list,
        supersedes=supersedes,
    )

    try:
        save_fact(root, fact)
    except RuntimeError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1) from None

    typer.echo(f"Saved fact [{fact_id}]: {claim}")


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
            "--confidence", "-c",
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
