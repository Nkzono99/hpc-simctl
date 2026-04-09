"""Harness file generation shared by ``simctl init`` and ``simctl update-harness``.

The builder renders every harness file (``CLAUDE.md``, ``AGENTS.md``,
``.claude/skills/*``, ``.claude/rules/*``, ``.claude/settings.json``,
``cases/CLAUDE.md``, ``runs/CLAUDE.md``) into an in-memory mapping of
``relative_path -> rendered_content``.

``simctl init`` iterates the mapping and writes each file (``_write_if_missing``),
then persists template hashes to ``.simctl/harness.lock``.  ``simctl update-harness``
re-renders the same mapping, compares the current on-disk hash against the lock
to detect user edits, and then overwrites / emits ``.new`` files accordingly.
"""

from __future__ import annotations

import hashlib
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

HARNESS_LOCK_PATH = ".simctl/harness.lock"

# File paths that `build_harness_bundle` may emit, as project-relative strings.
CLAUDE_MD = "CLAUDE.md"
AGENTS_MD = "AGENTS.md"
CLAUDE_SETTINGS = ".claude/settings.json"
CASES_CLAUDE_MD = "cases/CLAUDE.md"
RUNS_CLAUDE_MD = "runs/CLAUDE.md"
RULE_WORKFLOW = ".claude/rules/simctl-workflow.md"
RULE_PLAN_BEFORE_ACT = ".claude/rules/plan-before-act.md"
RULE_COOKBOOK = ".claude/rules/cookbook.md"
RULE_UPSTREAM_FEEDBACK = ".claude/rules/upstream-feedback.md"

# Files that update-harness is allowed to touch.  Any other file under the
# project root (campaign.toml, cases/**, runs/**, etc.) is user-owned and
# must never be rewritten by update-harness.
_ALL_HARNESS_PREFIXES: tuple[str, ...] = (
    CLAUDE_MD,
    AGENTS_MD,
    CLAUDE_SETTINGS,
    CASES_CLAUDE_MD,
    RUNS_CLAUDE_MD,
    ".claude/skills/",
    ".claude/rules/",
)


def is_harness_path(rel_path: str) -> bool:
    """Return True if ``rel_path`` is owned by the harness builder."""
    normalized = rel_path.replace("\\", "/")
    return any(
        normalized == prefix or normalized.startswith(prefix)
        for prefix in _ALL_HARNESS_PREFIXES
    )


@dataclass(frozen=True)
class HarnessBundle:
    """Rendered harness file contents keyed by project-relative path."""

    files: dict[str, str] = field(default_factory=dict)
    upstream_feedback: bool = True

    def hashes(self) -> dict[str, str]:
        """Return ``{relative_path: sha256}`` for every file in the bundle."""
        return {rel: hash_text(content) for rel, content in self.files.items()}


def hash_text(text: str) -> str:
    """Return hex sha256 of ``text`` encoded as UTF-8."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def hash_file(path: Path) -> str | None:
    """Return hex sha256 of the file at ``path``, or ``None`` if unreadable."""
    try:
        return hash_text(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, UnicodeDecodeError):
        return None


# ---------------------------------------------------------------------------
# Adapter lookups (private to harness builder; duplicated here to avoid a
# circular import with simctl.cli.init which also depends on this module).
# ---------------------------------------------------------------------------


def _collect_doc_repos(simulator_names: list[str]) -> list[tuple[str, str]]:
    """Return unique ``(url, dest)`` pairs from the given adapters."""
    import simctl.adapters  # noqa: F401
    from simctl.adapters.registry import get_global_registry

    registry = get_global_registry()
    seen: set[str] = set()
    repos: list[tuple[str, str]] = []
    for sim_name in simulator_names:
        try:
            adapter_cls = registry.get(sim_name)
        except KeyError:
            continue
        for url, dest in adapter_cls.doc_repos():
            if dest in seen:
                continue
            seen.add(dest)
            repos.append((url, dest))
    return repos


def _collect_pip_packages(simulator_names: list[str]) -> list[str]:
    """Return unique pip packages declared by the given adapters."""
    import simctl.adapters  # noqa: F401
    from simctl.adapters.registry import get_global_registry

    registry = get_global_registry()
    seen: set[str] = set()
    packages: list[str] = []
    for sim_name in simulator_names:
        try:
            adapter_cls = registry.get(sim_name)
        except KeyError:
            continue
        for pkg in adapter_cls.pip_packages():
            if pkg in seen:
                continue
            seen.add(pkg)
            packages.append(pkg)
    return packages


# ---------------------------------------------------------------------------
# Individual file renderers
# ---------------------------------------------------------------------------


def _render_agent_md(
    doc_name: str,
    project_name: str,
    simulator_names: list[str],
    *,
    knowledge_imports_path: str,
) -> str:
    """Render the shared ``agent.md`` Jinja template for CLAUDE/AGENTS md."""
    from simctl.templates import get_jinja_env

    env = get_jinja_env()
    template = env.get_template("agent.md")
    return template.render(
        doc_name=doc_name,
        project_name=project_name,
        doc_repos=_collect_doc_repos(simulator_names) if simulator_names else [],
        knowledge_imports_path=knowledge_imports_path,
    )


def _render_skill_files(
    project_name: str,
    simulator_names: list[str],
) -> dict[str, str]:
    """Return ``{"<skill-name>/SKILL.md": content}`` for all bundled skills."""
    pip_pkgs = _collect_pip_packages(simulator_names) if simulator_names else []
    if pip_pkgs:
        pip_install_line = f"uv pip install {' '.join(pip_pkgs)}"
    else:
        pip_install_line = "# uv pip install <必要なパッケージ>"

    skills_dir = Path(__file__).resolve().parent.parent / "templates" / "skills"
    results: dict[str, str] = {}
    for skill_path in sorted(skills_dir.iterdir()):
        if not skill_path.is_dir():
            continue
        skill_md = skill_path / "SKILL.md"
        if not skill_md.exists():
            continue
        content = skill_md.read_text(encoding="utf-8")
        if "{{" in content:
            from simctl.templates import get_jinja_env

            env = get_jinja_env()
            template = env.from_string(content)
            content = template.render(
                project_name=project_name,
                pip_install_line=pip_install_line,
            )
        results[f"{skill_path.name}/SKILL.md"] = content
    return results


# ---------------------------------------------------------------------------
# Main entry points
# ---------------------------------------------------------------------------


def build_harness_bundle(
    project_name: str,
    simulator_names: list[str],
    *,
    upstream_feedback: bool = True,
    knowledge_imports_path: str = "",
) -> HarnessBundle:
    """Render every harness file into an in-memory bundle.

    Args:
        project_name: Project name used in CLAUDE.md / AGENTS.md headers.
        simulator_names: Simulator adapter names (e.g. ``["emses", "beach"]``).
        upstream_feedback: Include the ``.claude/rules/upstream-feedback.md``
            rule.  ``simctl init --no-upstream-feedback`` sets this to False.
        knowledge_imports_path: Relative path to the rendered imports file,
            or empty string if knowledge imports are not configured.

    Returns:
        Bundle keyed by project-relative path; consumers iterate it to write
        files or to compute template hashes for ``.simctl/harness.lock``.
    """
    from simctl.harness import build_claude_settings
    from simctl.templates import load_static

    files: dict[str, str] = {}

    files[CLAUDE_MD] = _render_agent_md(
        CLAUDE_MD,
        project_name,
        simulator_names,
        knowledge_imports_path=knowledge_imports_path,
    )
    files[AGENTS_MD] = _render_agent_md(
        AGENTS_MD,
        project_name,
        simulator_names,
        knowledge_imports_path=knowledge_imports_path,
    )

    files[CLAUDE_SETTINGS] = build_claude_settings()

    for rel_path, content in _render_skill_files(project_name, simulator_names).items():
        files[f".claude/skills/{rel_path}"] = content

    files[RULE_WORKFLOW] = load_static("scaffold/rules/simctl-workflow.md")
    files[RULE_PLAN_BEFORE_ACT] = load_static("scaffold/rules/plan-before-act.md")
    if simulator_names and _collect_doc_repos(simulator_names):
        files[RULE_COOKBOOK] = load_static("rules/cookbook.md")
    if upstream_feedback:
        files[RULE_UPSTREAM_FEEDBACK] = load_static(
            "scaffold/rules/upstream-feedback.md"
        )

    files[CASES_CLAUDE_MD] = load_static("scaffold/cases_claude.md")
    files[RUNS_CLAUDE_MD] = load_static("scaffold/runs_claude.md")

    return HarnessBundle(files=files, upstream_feedback=upstream_feedback)


# ---------------------------------------------------------------------------
# harness.lock persistence
# ---------------------------------------------------------------------------


def load_harness_lock(project_dir: Path) -> dict[str, str]:
    """Load the ``harness.lock`` mapping ``relative_path -> template sha256``.

    Returns an empty dict when the lock file is missing, malformed, or when
    the project predates this feature.
    """
    lock_path = project_dir / HARNESS_LOCK_PATH
    if not lock_path.is_file():
        return {}
    try:
        raw = json.loads(lock_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    if not isinstance(raw, dict):
        return {}
    hashes = raw.get("hashes")
    if not isinstance(hashes, dict):
        return {}
    return {
        str(k): str(v)
        for k, v in hashes.items()
        if isinstance(k, str) and isinstance(v, str)
    }


def save_harness_lock(project_dir: Path, hashes: dict[str, str]) -> None:
    """Write the harness lock with sorted entries for stable diffs."""
    lock_path = project_dir / HARNESS_LOCK_PATH
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "version": 1,
        "hashes": dict(sorted(hashes.items())),
    }
    lock_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# simproject.toml [harness] helpers
# ---------------------------------------------------------------------------


def read_upstream_feedback_setting(project_dir: Path) -> bool:
    """Return ``[harness].upstream_feedback`` from simproject.toml.

    Defaults to True when the key, table, or file is absent so that projects
    predating this feature get upstream-feedback guidance by default once they
    run ``simctl update-harness``.
    """
    project_file = project_dir / "simproject.toml"
    if not project_file.is_file():
        return True
    try:
        with open(project_file, "rb") as f:
            data = tomllib.load(f)
    except (tomllib.TOMLDecodeError, OSError):
        return True
    harness = data.get("harness")
    if not isinstance(harness, dict):
        return True
    value = harness.get("upstream_feedback", True)
    return bool(value)
