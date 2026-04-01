"""Knowledge source management: external shared knowledge repo integration.

Handles attaching, syncing, validating, and rendering knowledge sources
defined in simproject.toml's ``[knowledge]`` section.
"""

from __future__ import annotations

import logging
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


# ---------- Data model ----------


@dataclass(frozen=True)
class KnowledgeSource:
    """A single external knowledge source.

    Attributes:
        name: Source identifier (e.g. ``"shared-lab-knowledge"``).
        source_type: ``"git"`` or ``"path"``.
        url: Git URL or filesystem path to the source.
        ref: Git ref to checkout (default ``"main"``).
        mount: Relative mount path from project root.
        profiles: List of enabled profile names from this source.
    """

    name: str
    source_type: str
    url: str
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
    for src in knowledge_raw.get("sources", []):
        if not isinstance(src, dict):
            continue
        name = src.get("name", "")
        if not name:
            continue
        source_type = src.get("type", "git")
        url = str(src.get("url") or src.get("path") or "")
        ref = src.get("ref", "main")
        default_mount = f"{knowledge_raw.get('mount_dir', _DEFAULT_MOUNT_DIR)}/{name}"
        mount = src.get("mount", default_mount)
        profiles = list(src.get("profiles", []))
        sources.append(
            KnowledgeSource(
                name=name,
                source_type=source_type,
                url=url,
                ref=ref,
                mount=mount,
                profiles=profiles,
            )
        )

    return KnowledgeConfig(
        enabled=knowledge_raw.get("enabled", True),
        mount_dir=knowledge_raw.get("mount_dir", _DEFAULT_MOUNT_DIR),
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
    }
    if source.source_type == "git":
        entry["url"] = source.url
        if source.ref and source.ref != "main":
            entry["ref"] = source.ref
    else:
        entry["path"] = source.url
    if source.mount:
        entry["mount"] = source.mount
    if source.profiles:
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
    mount_path = project_root / source.mount

    if source.source_type == "path":
        resolved = Path(source.url).expanduser()
        if not resolved.is_absolute():
            resolved = (project_root / resolved).resolve()
        if not resolved.is_dir():
            raise KnowledgeSourceError(
                f"Knowledge source path not found: {resolved}"
            )
        # For path sources, create symlink if mount doesn't exist
        if not mount_path.exists():
            mount_path.parent.mkdir(parents=True, exist_ok=True)
            mount_path.symlink_to(resolved)
            return "linked"
        return "exists"

    # git source
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
        "<!-- Auto-generated by simctl knowledge render. Do not edit. -->",
        "",
    ]

    for source in config.sources:
        mount_path = project_root / source.mount
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
