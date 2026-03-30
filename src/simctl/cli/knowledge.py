"""CLI commands for knowledge management."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Optional

import typer

from simctl.core.exceptions import SimctlError
from simctl.core.knowledge import (
    INSIGHT_TYPES,
    Insight,
    get_insights_dir,
    list_insights,
    load_links,
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
            "Create .simctl/links.toml with:"
        )
        typer.echo("")
        typer.echo('  [projects]')
        typer.echo('  other-project = "../other-project"')
        typer.echo("")
        typer.echo("  [shared]")
        typer.echo('  knowledge = "~/.simctl/knowledge"')
        return

    for link in links:
        exists = link.path.is_dir()
        status = "OK" if exists else "NOT FOUND"
        typer.echo(
            f"  [{link.link_type}] {link.name}: "
            f"{link.path} ({status})"
        )
