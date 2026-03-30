"""Knowledge layer: insights, links, and cross-project knowledge sharing."""

from __future__ import annotations

import logging
import shutil
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

try:
    import tomli_w
except ImportError:
    tomli_w = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

_SIMCTL_DIR = ".simctl"
_INSIGHTS_DIR = "insights"
_KNOWLEDGE_DIR = "knowledge"
_LINKS_FILE = "links.toml"

# Valid insight types
INSIGHT_TYPES = frozenset({
    "constraint",   # Stability/constraint findings
    "result",       # Experiment result summaries
    "analysis",     # Physical interpretation / discussion
    "dependency",   # Parameter dependency trends
})


@dataclass(frozen=True)
class Insight:
    """A single knowledge insight.

    Attributes:
        name: Filename stem (e.g. ``"emses_cfl_limit"``).
        type: One of :data:`INSIGHT_TYPES`.
        simulator: Simulator name this insight applies to.
        tags: Searchable tags.
        source_project: Project where this insight originated.
        created: ISO-format creation timestamp.
        content: Markdown body of the insight.
    """

    name: str
    type: str
    simulator: str
    tags: list[str] = field(default_factory=list)
    source_project: str = ""
    created: str = ""
    content: str = ""


@dataclass(frozen=True)
class ProjectLink:
    """A link to another project or shared knowledge location.

    Attributes:
        name: Link name (key in links.toml).
        path: Resolved absolute path.
        link_type: ``"project"`` or ``"shared"``.
    """

    name: str
    path: Path
    link_type: str


def get_simctl_dir(project_root: Path) -> Path:
    """Return the .simctl directory for a project, creating if needed."""
    d = project_root / _SIMCTL_DIR
    d.mkdir(exist_ok=True)
    return d


def get_insights_dir(project_root: Path) -> Path:
    """Return the .simctl/insights directory, creating if needed."""
    d = get_simctl_dir(project_root) / _INSIGHTS_DIR
    d.mkdir(exist_ok=True)
    return d


def get_knowledge_dir(project_root: Path) -> Path:
    """Return the .simctl/knowledge directory, creating if needed."""
    d = get_simctl_dir(project_root) / _KNOWLEDGE_DIR
    d.mkdir(exist_ok=True)
    return d


# ---------- Insight I/O ----------


def parse_insight(path: Path) -> Insight | None:
    """Parse an insight markdown file with YAML-like frontmatter.

    The frontmatter is delimited by ``---`` lines and contains
    key-value pairs.
    """
    try:
        text = path.read_text()
    except OSError:
        return None

    lines = text.split("\n")
    if not lines or lines[0].strip() != "---":
        return None

    # Find closing ---
    end_idx = -1
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end_idx = i
            break
    if end_idx < 0:
        return None

    # Parse frontmatter
    meta: dict[str, Any] = {}
    for line in lines[1:end_idx]:
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()
        # Handle list values: [a, b, c]
        if value.startswith("[") and value.endswith("]"):
            value = [
                v.strip().strip("\"'")
                for v in value[1:-1].split(",")
                if v.strip()
            ]
        meta[key] = value

    content = "\n".join(lines[end_idx + 1 :]).strip()

    tags = meta.get("tags", [])
    if isinstance(tags, str):
        tags = [tags]

    return Insight(
        name=path.stem,
        type=meta.get("type", "result"),
        simulator=meta.get("simulator", ""),
        tags=tags,
        source_project=meta.get("source_project", ""),
        created=meta.get("created", ""),
        content=content,
    )


def write_insight(insights_dir: Path, insight: Insight) -> Path:
    """Write an insight to a markdown file.

    Returns:
        Path to the written file.
    """
    tags_str = ", ".join(insight.tags) if insight.tags else ""
    created = insight.created or datetime.now(
        timezone.utc
    ).strftime("%Y-%m-%d")

    frontmatter = [
        "---",
        f"type: {insight.type}",
        f"simulator: {insight.simulator}",
    ]
    if tags_str:
        frontmatter.append(f"tags: [{tags_str}]")
    if insight.source_project:
        frontmatter.append(f"source_project: {insight.source_project}")
    frontmatter.append(f"created: {created}")
    frontmatter.append("---")

    text = "\n".join(frontmatter) + "\n\n" + insight.content + "\n"
    filepath = insights_dir / f"{insight.name}.md"
    filepath.write_text(text)
    return filepath


def list_insights(
    project_root: Path,
    *,
    simulator: str = "",
    insight_type: str = "",
    tag: str = "",
) -> list[Insight]:
    """List insights, optionally filtered."""
    insights_dir = project_root / _SIMCTL_DIR / _INSIGHTS_DIR
    if not insights_dir.is_dir():
        return []

    results: list[Insight] = []
    for md_file in sorted(insights_dir.glob("*.md")):
        insight = parse_insight(md_file)
        if insight is None:
            continue
        if simulator and insight.simulator != simulator:
            continue
        if insight_type and insight.type != insight_type:
            continue
        if tag and tag not in insight.tags:
            continue
        results.append(insight)
    return results


# ---------- Links ----------


def load_links(project_root: Path) -> list[ProjectLink]:
    """Load .simctl/links.toml and resolve paths."""
    links_file = project_root / _SIMCTL_DIR / _LINKS_FILE
    if not links_file.is_file():
        return []

    with open(links_file, "rb") as f:
        raw = tomllib.load(f)

    results: list[ProjectLink] = []

    for name, path_str in raw.get("projects", {}).items():
        resolved = _resolve_link_path(project_root, path_str)
        results.append(ProjectLink(name=name, path=resolved, link_type="project"))

    for name, path_str in raw.get("shared", {}).items():
        resolved = _resolve_link_path(project_root, path_str)
        results.append(ProjectLink(name=name, path=resolved, link_type="shared"))

    return results


def _resolve_link_path(project_root: Path, path_str: str) -> Path:
    """Resolve a link path (supports ~, relative, absolute)."""
    p = Path(path_str).expanduser()
    if not p.is_absolute():
        p = (project_root / p).resolve()
    return p


def sync_insights(
    project_root: Path,
    *,
    simulator: str = "",
) -> tuple[int, int]:
    """Import insights from linked projects.

    Returns:
        Tuple of (imported_count, skipped_count).
    """
    links = load_links(project_root)
    our_insights_dir = get_insights_dir(project_root)

    imported = 0
    skipped = 0

    for link in links:
        if link.link_type == "shared":
            # Shared knowledge: look for insights/ directly
            source_dir = link.path / _INSIGHTS_DIR
        else:
            # Project link: look in .simctl/insights/
            source_dir = link.path / _SIMCTL_DIR / _INSIGHTS_DIR

        if not source_dir.is_dir():
            continue

        for md_file in sorted(source_dir.glob("*.md")):
            insight = parse_insight(md_file)
            if insight is None:
                continue
            if simulator and insight.simulator != simulator:
                continue

            dest = our_insights_dir / md_file.name
            if dest.exists():
                skipped += 1
                continue

            shutil.copy2(md_file, dest)
            imported += 1

    return imported, skipped
