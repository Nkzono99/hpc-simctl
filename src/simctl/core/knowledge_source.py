"""Knowledge source management: external knowledge integration.

Handles attaching, syncing, validating, rendering, and importing
knowledge sources defined in simproject.toml's ``[knowledge]`` section.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
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

from simctl.core.exceptions import KnowledgeSourceError

logger = logging.getLogger(__name__)

_PROJECT_FILE = "simproject.toml"
_DEFAULT_MOUNT_DIR = "refs/knowledge"
_DEFAULT_DERIVED_DIR = ".simctl/knowledge"
_SOURCE_TYPES = frozenset({"git", "path"})
_SOURCE_KINDS = frozenset({"profiles", "project", "insights"})


# ---------- Data model ----------


@dataclass(frozen=True)
class KnowledgeSource:
    """A single external knowledge source.

    Attributes:
        name: Source identifier (e.g. ``"shared-lab-knowledge"``).
        source_type: ``"git"`` or ``"path"``.
        kind: How the source is consumed.
            ``"profiles"`` mounts shared knowledge profiles and agent docs.
            ``"project"`` imports insights from another simctl project.
            ``"insights"`` imports insights from a shared knowledge store.
        url: Git URL or filesystem path to the source.
        ref: Git ref to checkout (default ``"main"``).
        mount: Relative checkout/mount path from project root.
            Required for git sources and ``profiles`` sources.
        profiles: List of enabled profile names from this source
            (``profiles`` kind only).
    """

    name: str
    source_type: str
    url: str
    kind: str = "profiles"
    ref: str = "main"
    mount: str = ""
    profiles: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class KnowledgeConfig:
    """Knowledge integration configuration from simproject.toml.

    Attributes:
        enabled: Whether knowledge integration is active.
        mount_dir: Base directory for mounting sources.
        derived_dir: Directory for generated/derived knowledge files.
        auto_sync_on_setup: Sync sources during ``simctl setup``.
        generate_claude_imports: Generate CLAUDE.md import stubs.
        sources: List of configured knowledge sources.
    """

    enabled: bool = True
    mount_dir: str = _DEFAULT_MOUNT_DIR
    derived_dir: str = _DEFAULT_DERIVED_DIR
    auto_sync_on_setup: bool = True
    generate_claude_imports: bool = True
    sources: list[KnowledgeSource] = field(default_factory=list)


@dataclass(frozen=True)
class ExternalKnowledgeMount:
    """Normalized view of an attached knowledge source.

    Attributes:
        name: User-facing identifier.
        source_type: Concrete transport type such as ``"git"`` or ``"path"``.
        kind: Content shape such as ``"profiles"``, ``"project"``,
            or ``"insights"``.
        path: Resolved absolute path for this source.
        display_path: Relative mount path or resolved source path to show in CLI.
        exists: Whether the source is currently available locally.
        profiles_enabled: Enabled profile names for ``profiles`` sources.
        profiles_available: Discovered profile names for ``profiles`` sources.
    """

    name: str
    source_type: str
    kind: str
    path: Path
    display_path: str
    exists: bool
    profiles_enabled: list[str] = field(default_factory=list)
    profiles_available: list[str] = field(default_factory=list)


def _normalize_source_type(value: Any) -> str:
    source_type = str(value or "git")
    if source_type not in _SOURCE_TYPES:
        logger.warning("Unknown knowledge source type '%s'; using 'git'", value)
        return "git"
    return source_type


def _normalize_source_kind(value: Any) -> str:
    kind = str(value or "profiles")
    if kind not in _SOURCE_KINDS:
        logger.warning(
            "Unknown knowledge source kind '%s'; using 'profiles'",
            value,
        )
        return "profiles"
    return kind


def _default_mount(name: str, mount_dir: str, *, source_type: str, kind: str) -> str:
    if source_type == "git" or kind == "profiles":
        return f"{mount_dir}/{name}"
    return ""


def _resolve_path_source(project_root: Path, raw_path: str) -> Path:
    resolved = Path(raw_path).expanduser()
    if not resolved.is_absolute():
        resolved = (project_root / resolved).resolve()
    return resolved


def _mount_path(project_root: Path, source: KnowledgeSource) -> Path | None:
    if not source.mount:
        return None
    return project_root / source.mount


def _source_root(project_root: Path, source: KnowledgeSource) -> Path:
    if source.source_type == "path" and source.kind != "profiles":
        return _resolve_path_source(project_root, source.url)

    mount_path = _mount_path(project_root, source)
    if mount_path is None:
        msg = f"Knowledge source '{source.name}' requires a mount path"
        raise KnowledgeSourceError(msg)
    return mount_path


def _insight_source_dir(project_root: Path, source: KnowledgeSource) -> Path | None:
    root = _source_root(project_root, source)
    if source.kind == "project":
        return root / ".simctl" / "insights"
    if source.kind == "insights":
        return root / "insights"
    return None


def _repo_name_from_url(url: str) -> str:
    """Extract repository name from a git URL."""
    stem = url.rsplit("/", 1)[-1].rsplit(":", 1)[-1]
    if stem.endswith(".git"):
        stem = stem[:-4]
    return stem


def _safe_namespace(value: str) -> str:
    """Return a filesystem-safe namespace token for imported knowledge."""
    normalized = [
        ch.lower() if ch.isalnum() else "_"
        for ch in value.strip()
    ]
    token = "".join(normalized).strip("_")
    while "__" in token:
        token = token.replace("__", "_")
    return token or "source"


def _namespaced_insight_filename(source: KnowledgeSource, insight_name: str) -> str:
    """Build the destination filename for an imported insight."""
    namespace = _safe_namespace(source.name)
    return f"{namespace}__{insight_name}.md"


# ---------- Config I/O ----------


def load_knowledge_config(project_root: Path) -> KnowledgeConfig | None:
    """Load knowledge configuration from simproject.toml.

    Returns:
        KnowledgeConfig if ``[knowledge]`` section exists, None otherwise.
    """
    project_file = project_root / _PROJECT_FILE
    if not project_file.is_file():
        return None

    with open(project_file, "rb") as f:
        raw = tomllib.load(f)

    knowledge_raw = raw.get("knowledge")
    if not isinstance(knowledge_raw, dict):
        return None

    sources: list[KnowledgeSource] = []
    mount_dir = str(knowledge_raw.get("mount_dir", _DEFAULT_MOUNT_DIR))
    for src in knowledge_raw.get("sources", []):
        if not isinstance(src, dict):
            continue
        name = src.get("name", "")
        if not name:
            continue
        source_type = _normalize_source_type(src.get("type", "git"))
        kind = _normalize_source_kind(src.get("kind", "profiles"))
        url = str(src.get("url") or src.get("path") or "")
        ref = src.get("ref", "main")
        default_mount = _default_mount(
            name,
            mount_dir,
            source_type=source_type,
            kind=kind,
        )
        mount = str(src.get("mount", default_mount))
        profiles = list(src.get("profiles", [])) if kind == "profiles" else []
        sources.append(
            KnowledgeSource(
                name=name,
                source_type=source_type,
                kind=kind,
                url=url,
                ref=ref,
                mount=mount,
                profiles=profiles,
            )
        )

    return KnowledgeConfig(
        enabled=knowledge_raw.get("enabled", True),
        mount_dir=mount_dir,
        derived_dir=knowledge_raw.get("derived_dir", _DEFAULT_DERIVED_DIR),
        auto_sync_on_setup=knowledge_raw.get("auto_sync_on_setup", True),
        generate_claude_imports=knowledge_raw.get("generate_claude_imports", True),
        sources=sources,
    )


def _read_project_toml(project_root: Path) -> dict[str, Any]:
    """Read simproject.toml as raw dict."""
    project_file = project_root / _PROJECT_FILE
    with open(project_file, "rb") as f:
        return tomllib.load(f)


def _write_project_toml(project_root: Path, data: dict[str, Any]) -> None:
    """Write simproject.toml from dict."""
    if tomli_w is None:
        msg = "tomli_w is required to write simproject.toml"
        raise KnowledgeSourceError(msg)
    project_file = project_root / _PROJECT_FILE
    with open(project_file, "wb") as f:
        tomli_w.dump(data, f)


def save_knowledge_source(project_root: Path, source: KnowledgeSource) -> None:
    """Add or update a knowledge source in simproject.toml.

    Creates the ``[knowledge]`` section if it does not exist.
    If a source with the same name exists, it is replaced.
    """
    raw = _read_project_toml(project_root)

    knowledge = raw.setdefault("knowledge", {})
    knowledge.setdefault("enabled", True)
    knowledge.setdefault("mount_dir", _DEFAULT_MOUNT_DIR)
    knowledge.setdefault("derived_dir", _DEFAULT_DERIVED_DIR)
    knowledge.setdefault("auto_sync_on_setup", True)
    knowledge.setdefault("generate_claude_imports", True)

    sources_list: list[dict[str, Any]] = list(knowledge.get("sources", []))

    entry: dict[str, Any] = {
        "name": source.name,
        "type": source.source_type,
        "kind": source.kind,
    }
    if source.source_type == "git":
        entry["url"] = source.url
        if source.ref and source.ref != "main":
            entry["ref"] = source.ref
    else:
        entry["path"] = source.url
    if source.mount:
        entry["mount"] = source.mount
    if source.profiles and source.kind == "profiles":
        entry["profiles"] = source.profiles

    # Replace existing source with same name, or append
    replaced = False
    for i, existing in enumerate(sources_list):
        if existing.get("name") == source.name:
            sources_list[i] = entry
            replaced = True
            break
    if not replaced:
        sources_list.append(entry)

    knowledge["sources"] = sources_list
    _write_project_toml(project_root, raw)


def remove_knowledge_source(project_root: Path, name: str) -> bool:
    """Remove a knowledge source from simproject.toml by name.

    Returns:
        True if the source was found and removed.
    """
    raw = _read_project_toml(project_root)
    knowledge = raw.get("knowledge")
    if not isinstance(knowledge, dict):
        return False

    sources_list: list[dict[str, Any]] = list(knowledge.get("sources", []))
    original_len = len(sources_list)
    sources_list = [s for s in sources_list if s.get("name") != name]

    if len(sources_list) == original_len:
        return False

    knowledge["sources"] = sources_list
    _write_project_toml(project_root, raw)
    return True


def collect_external_knowledge(project_root: Path) -> list[ExternalKnowledgeMount]:
    """Return configured knowledge sources."""
    entries: list[ExternalKnowledgeMount] = []

    config = load_knowledge_config(project_root)
    if config is not None:
        for source in config.sources:
            try:
                source_path = _source_root(project_root, source)
            except KnowledgeSourceError:
                fallback_mount = _mount_path(project_root, source)
                source_path = fallback_mount or project_root
            available = source_path.is_dir()
            entries.append(
                ExternalKnowledgeMount(
                    name=source.name,
                    source_type=source.source_type,
                    kind=source.kind,
                    path=source_path,
                    display_path=source.mount or str(source_path),
                    exists=available,
                    profiles_enabled=(
                        list(source.profiles) if source.kind == "profiles" else []
                    ),
                    profiles_available=(
                        discover_profiles(source_path)
                        if available and source.kind == "profiles"
                        else []
                    ),
                )
            )

    return sorted(entries, key=lambda entry: entry.name.lower())


# ---------- Source sync ----------


def sync_source(project_root: Path, source: KnowledgeSource) -> str:
    """Synchronize a single knowledge source.

    For git sources: clone if missing, pull if existing.
    For path sources: verify existence.

    Returns:
        Status string describing what happened.

    Raises:
        KnowledgeSourceError: If sync fails.
    """
    if source.source_type == "path":
        resolved = _resolve_path_source(project_root, source.url)
        if not resolved.is_dir():
            raise KnowledgeSourceError(
                f"Knowledge source path not found: {resolved}"
            )
        if source.kind != "profiles":
            return "available"

        mount_path = _mount_path(project_root, source)
        if mount_path is None:
            raise KnowledgeSourceError(
                f"Knowledge source '{source.name}' requires a mount path"
            )
        mount_path.parent.mkdir(parents=True, exist_ok=True)

        if mount_path.exists():
            if mount_path.is_symlink():
                return "exists"
            if mount_path.is_dir():
                shutil.copytree(resolved, mount_path, dirs_exist_ok=True)
                return "updated-copy"
            return "exists"

        try:
            mount_path.symlink_to(resolved, target_is_directory=True)
            return "linked"
        except OSError as e:
            logger.info(
                "Symlink unavailable for knowledge source %s (%s); "
                "falling back to directory copy",
                source.name,
                e,
            )
            shutil.copytree(resolved, mount_path, dirs_exist_ok=True)
            return "copied"

    # git source
    mount_path = _mount_path(project_root, source)
    if mount_path is None:
        raise KnowledgeSourceError(
            f"Knowledge source '{source.name}' requires a mount path"
        )
    if mount_path.is_dir() and (mount_path / ".git").exists():
        # Pull
        result = subprocess.run(
            ["git", "-C", str(mount_path), "pull", "--ff-only"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        if result.returncode != 0:
            logger.warning("git pull failed for %s: %s", source.name, result.stderr)
            return "pull-failed"
        return "updated"

    # Clone
    mount_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["git", "clone", source.url, str(mount_path)]
    if source.ref:
        cmd.extend(["--branch", source.ref])
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.returncode != 0:
        raise KnowledgeSourceError(
            f"git clone failed for {source.name}: "
            f"{(result.stderr or '').strip()[:300]}"
        )
    return "cloned"


def sync_all_sources(
    project_root: Path, config: KnowledgeConfig
) -> list[tuple[str, str]]:
    """Synchronize all knowledge sources.

    Returns:
        List of (source_name, status) tuples.
    """
    results: list[tuple[str, str]] = []
    for source in config.sources:
        try:
            status = sync_source(project_root, source)
        except KnowledgeSourceError as e:
            logger.warning("Failed to sync %s: %s", source.name, e)
            status = f"error: {e}"
        results.append((source.name, status))
    return results


def import_external_insights(
    project_root: Path,
    sources: list[KnowledgeSource],
    *,
    simulator: str = "",
) -> tuple[int, int]:
    """Import insights from configured external sources.

    Imported insight filenames are namespaced by source name to avoid
    collisions across multiple upstream projects or knowledge stores.
    """
    from simctl.core.knowledge import get_insights_dir, parse_insight

    our_insights_dir = get_insights_dir(project_root)
    imported = 0
    skipped = 0

    for source in sources:
        source_dir = _insight_source_dir(project_root, source)
        if source_dir is None or not source_dir.is_dir():
            continue

        for md_file in sorted(source_dir.glob("*.md")):
            insight = parse_insight(md_file)
            if insight is None:
                continue
            if simulator and insight.simulator != simulator:
                continue

            dest = our_insights_dir / _namespaced_insight_filename(source, md_file.stem)
            if dest.exists():
                skipped += 1
                continue

            shutil.copy2(md_file, dest)
            imported += 1

    return imported, skipped


# ---------- Validation ----------


def validate_source_structure(source_path: Path) -> list[str]:
    """Validate that a knowledge source has the expected structure.

    Checks for required files/directories:
    - ``profiles/`` directory
    - ``README.md``

    Returns:
        List of issue descriptions (empty = valid).
    """
    issues: list[str] = []

    if not source_path.is_dir():
        issues.append(f"Source directory not found: {source_path}")
        return issues

    if not (source_path / "profiles").is_dir():
        issues.append("Missing required directory: profiles/")

    if not (source_path / "README.md").is_file():
        issues.append("Missing required file: README.md")

    return issues


def discover_profiles(source_path: Path) -> list[str]:
    """List available profile names from a knowledge source.

    Scans ``profiles/*.md`` and returns stems.
    """
    profiles_dir = source_path / "profiles"
    if not profiles_dir.is_dir():
        return []
    return sorted(p.stem for p in profiles_dir.glob("*.md"))


# ---------- Rendering ----------


def render_imports(
    project_root: Path,
    config: KnowledgeConfig,
    *,
    extra_imports: list[str] | None = None,
) -> Path:
    """Generate imports.md from enabled profiles.

    Reads each enabled profile file and generates a single
    ``imports.md`` that uses ``@import`` directives to reference
    source content.

    Args:
        project_root: Project root directory.
        config: Knowledge configuration.
        extra_imports: Additional relative paths to include as
            ``@import`` directives (e.g. agent docs from refs/).

    Returns:
        Path to the generated imports.md file.
    """
    enabled_dir = project_root / config.derived_dir / "enabled"
    enabled_dir.mkdir(parents=True, exist_ok=True)
    imports_path = enabled_dir / "imports.md"

    lines: list[str] = [
        "<!-- Auto-generated by simctl knowledge source render. Do not edit. -->",
        "",
    ]

    for source in config.sources:
        if source.kind != "profiles":
            continue

        mount_path = _mount_path(project_root, source)
        if mount_path is None:
            lines.append(f"<!-- source {source.name}: mount not configured -->")
            continue
        if not mount_path.is_dir():
            lines.append(f"<!-- source {source.name}: not mounted -->")
            continue

        if not source.profiles:
            # No profiles enabled — import source CLAUDE.md if it exists
            claude_md = mount_path / "CLAUDE.md"
            if claude_md.is_file():
                lines.append(f"@{source.mount}/CLAUDE.md")
            continue

        for profile_name in source.profiles:
            profile_path = mount_path / "profiles" / f"{profile_name}.md"
            if profile_path.is_file():
                lines.append(f"@{source.mount}/profiles/{profile_name}.md")
            else:
                lines.append(
                    f"<!-- profile {profile_name} not found "
                    f"in {source.name} -->"
                )

    if extra_imports:
        lines.append("")
        for path in extra_imports:
            lines.append(f"@{path}")

    lines.append("")  # trailing newline
    imports_path.write_text("\n".join(lines), encoding="utf-8")
    return imports_path
