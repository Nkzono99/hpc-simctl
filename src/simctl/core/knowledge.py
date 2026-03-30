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
INSIGHT_TYPES = frozenset(
    {
        "constraint",  # Stability/constraint findings
        "result",  # Experiment result summaries
        "analysis",  # Physical interpretation / discussion
        "dependency",  # Parameter dependency trends
    }
)

# Valid fact types
FACT_TYPES = frozenset(
    {
        "observation",  # Directly observed from run output
        "constraint",  # Stability / CFL / resolution constraint
        "dependency",  # Parameter dependency relationship
        "policy",  # Operational rule (e.g. "always use dt < X")
        "hypothesis",  # Unverified conjecture
    }
)


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
                v.strip().strip("\"'") for v in value[1:-1].split(",") if v.strip()
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
    created = insight.created or datetime.now(timezone.utc).strftime("%Y-%m-%d")

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


# ---------- Structured Facts ----------

_FACTS_FILE = "facts.toml"


@dataclass
class Fact:
    """A structured, machine-readable knowledge claim.

    Unlike Insight (free-form markdown), a Fact is designed for
    programmatic consumption by AI agents and validation tools.

    Attributes:
        id: Unique fact identifier (e.g. ``"f001"``).
        claim: The knowledge claim (one sentence).
        fact_type: One of :data:`FACT_TYPES`
            (``"observation"``, ``"constraint"``, ``"dependency"``,
            ``"policy"``, ``"hypothesis"``).
        simulator: Simulator this fact applies to (empty = general).
        scope_case: Case pattern this applies to (e.g. ``"mag_scan"``).
        scope_text: Free-text scope description for humans.
        param_name: Parameter name this fact is about (dot-notation).
        confidence: ``"high"``, ``"medium"``, or ``"low"``.
        source_run: Run ID that produced this evidence (if any).
        source_project: Project where the fact was established.
        evidence_kind: Type of evidence (``"run_observation"``,
            ``"calculation"``, ``"literature"``, ``"heuristic"``).
        evidence_ref: Reference to evidence source
            (e.g. ``"run:R20260330-0004"``).
        created_at: ISO-format timestamp.
        tags: Searchable tags.
        supersedes: ID of the fact this one replaces (if any).
    """

    id: str
    claim: str
    fact_type: str = "observation"
    simulator: str = ""
    scope_case: str = ""
    scope_text: str = ""
    param_name: str = ""
    confidence: str = "medium"
    source_run: str = ""
    source_project: str = ""
    evidence_kind: str = ""
    evidence_ref: str = ""
    created_at: str = ""
    tags: list[str] = field(default_factory=list)
    supersedes: str = ""

    # Kept for backward compatibility with old facts.toml files
    # that use "scope" and "evidence" as flat strings.
    @property
    def scope(self) -> str:
        """Backward-compatible scope string."""
        parts = []
        if self.simulator:
            parts.append(self.simulator)
        if self.scope_case:
            parts.append(self.scope_case)
        if self.scope_text:
            parts.append(self.scope_text)
        return ", ".join(parts) if parts else ""

    @property
    def evidence(self) -> str:
        """Backward-compatible evidence string."""
        parts = []
        if self.evidence_kind:
            parts.append(self.evidence_kind)
        if self.evidence_ref:
            parts.append(self.evidence_ref)
        return ": ".join(parts) if parts else ""


def load_facts(project_root: Path) -> list[Fact]:
    """Load structured facts from .simctl/facts.toml.

    Handles both the new structured schema (with ``fact_type``,
    ``simulator``, ``scope_case``, etc.) and the legacy flat schema
    (with ``scope`` and ``evidence`` as plain strings).
    """
    facts_file = project_root / _SIMCTL_DIR / _FACTS_FILE
    if not facts_file.is_file():
        return []

    with open(facts_file, "rb") as f:
        raw = tomllib.load(f)

    facts: list[Fact] = []
    for d in raw.get("facts", []):
        if not isinstance(d, dict):
            continue

        # Migrate legacy "scope" string -> scope_text
        scope_case = d.get("scope_case", "")
        scope_text = d.get("scope_text", "")
        if not scope_case and not scope_text:
            legacy_scope = d.get("scope", "")
            if legacy_scope:
                scope_text = legacy_scope

        # Migrate legacy "evidence" string -> evidence_kind
        evidence_kind = d.get("evidence_kind", "")
        evidence_ref = d.get("evidence_ref", "")
        if not evidence_kind and not evidence_ref:
            legacy_evidence = d.get("evidence", "")
            if legacy_evidence:
                evidence_kind = legacy_evidence

        facts.append(
            Fact(
                id=d.get("id", ""),
                claim=d.get("claim", ""),
                fact_type=d.get("fact_type", "observation"),
                simulator=d.get("simulator", ""),
                scope_case=scope_case,
                scope_text=scope_text,
                param_name=d.get("param_name", ""),
                confidence=d.get("confidence", "medium"),
                source_run=d.get("source_run", ""),
                source_project=d.get("source_project", ""),
                evidence_kind=evidence_kind,
                evidence_ref=evidence_ref,
                created_at=d.get("created_at", ""),
                tags=list(d.get("tags", [])),
                supersedes=d.get("supersedes", ""),
            )
        )
    return facts


def save_fact(project_root: Path, fact: Fact) -> None:
    """Append a structured fact to .simctl/facts.toml.

    Uses the new structured schema.  Facts are append-only by convention;
    to supersede an existing fact, create a new one with ``supersedes``
    set to the old fact's ID.
    """
    if tomli_w is None:
        msg = "tomli_w is required to write facts.toml"
        raise RuntimeError(msg)

    simctl_dir = project_root / _SIMCTL_DIR
    simctl_dir.mkdir(exist_ok=True)
    facts_file = simctl_dir / _FACTS_FILE

    # Load existing
    existing: list[dict[str, Any]] = []
    if facts_file.is_file():
        with open(facts_file, "rb") as f:
            raw = tomllib.load(f)
        existing = list(raw.get("facts", []))

    # Build new entry (structured schema)
    entry: dict[str, Any] = {
        "id": fact.id,
        "claim": fact.claim,
        "fact_type": fact.fact_type,
    }
    if fact.simulator:
        entry["simulator"] = fact.simulator
    if fact.scope_case:
        entry["scope_case"] = fact.scope_case
    if fact.scope_text:
        entry["scope_text"] = fact.scope_text
    if fact.param_name:
        entry["param_name"] = fact.param_name
    entry["confidence"] = fact.confidence
    if fact.source_run:
        entry["source_run"] = fact.source_run
    if fact.source_project:
        entry["source_project"] = fact.source_project
    if fact.evidence_kind:
        entry["evidence_kind"] = fact.evidence_kind
    if fact.evidence_ref:
        entry["evidence_ref"] = fact.evidence_ref
    entry["created_at"] = fact.created_at or datetime.now(timezone.utc).isoformat(
        timespec="seconds"
    )
    if fact.tags:
        entry["tags"] = fact.tags
    if fact.supersedes:
        entry["supersedes"] = fact.supersedes

    existing.append(entry)

    with open(facts_file, "wb") as f:
        tomli_w.dump({"facts": existing}, f)


def query_facts(
    project_root: Path,
    *,
    scope: str = "",
    tag: str = "",
    min_confidence: str = "",
    simulator: str = "",
    fact_type: str = "",
    param_name: str = "",
    exclude_superseded: bool = True,
) -> list[Fact]:
    """Query facts with optional filters.

    Args:
        project_root: Project root directory.
        scope: Free-text scope substring match (searches scope property).
        tag: Must appear in tags list.
        min_confidence: Minimum confidence level.
        simulator: Must match simulator field exactly.
        fact_type: Must match fact_type field exactly.
        param_name: Must match param_name field exactly.
        exclude_superseded: If True, exclude facts that have been
            superseded by newer facts.
    """
    confidence_order = {"high": 3, "medium": 2, "low": 1}
    min_level = confidence_order.get(min_confidence, 0)

    facts = load_facts(project_root)

    # Build set of superseded IDs
    superseded_ids: set[str] = set()
    if exclude_superseded:
        for f in facts:
            if f.supersedes:
                superseded_ids.add(f.supersedes)

    results: list[Fact] = []
    for f in facts:
        if exclude_superseded and f.id in superseded_ids:
            continue
        if scope and scope not in f.scope:
            continue
        if tag and tag not in f.tags:
            continue
        if min_level and confidence_order.get(f.confidence, 0) < min_level:
            continue
        if simulator and f.simulator != simulator:
            continue
        if fact_type and f.fact_type != fact_type:
            continue
        if param_name and f.param_name != param_name:
            continue
        results.append(f)
    return results
