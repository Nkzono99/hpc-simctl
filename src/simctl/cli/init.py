"""CLI commands for project initialization and environment checks."""

from __future__ import annotations

import importlib.resources
import logging
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any, Optional

import jinja2
import typer

from simctl.core.discovery import validate_uniqueness
from simctl.core.exceptions import DuplicateRunIdError, ProjectConfigError
from simctl.core.project import load_project

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

try:
    import tomli_w
except ImportError:
    tomli_w = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

_SIMPROJECT_FILE = "simproject.toml"
_SIMULATORS_FILE = "simulators.toml"
_LAUNCHERS_FILE = "launchers.toml"
_CAMPAIGN_FILE = "campaign.toml"
_CLAUDE_MD = "CLAUDE.md"
_AGENTS_MD = "AGENTS.md"
_SKILLS_DIR = ".claude/skills"
_RULES_DIR = ".claude/rules"
_CLAUDE_SETTINGS = ".claude/settings.json"
_VSCODE_DIR = ".vscode"
_VSCODE_SETTINGS = "settings.json"

_SCHEMA_BASE_URL = "https://raw.githubusercontent.com/Nkzono99/hpc-simctl/main/schemas"
_DEFAULT_SIMCTL_REPO = "https://github.com/Nkzono99/hpc-simctl.git"

_GITIGNORE_CONTENT = """\
# Python venv
.venv/

# simctl tool (cloned by simctl init)
tools/

# Reference repos (cloned by simctl init)
refs/

# Auto-generated knowledge indexes (insights/, facts.toml, links.toml are tracked)
.simctl/knowledge/
.simctl/environment.toml
.simctl/shared/

# heavy run outputs
runs/**/work/outputs/
runs/**/work/restart/
runs/**/work/tmp/

# logs
runs/**/work/*.out
runs/**/work/*.err
runs/**/work/*.log

# analysis cache
runs/**/analysis/cache/
runs/**/analysis/.ipynb_checkpoints/

# Personal agent overrides (not shared)
CLAUDE.local.md
.claude/settings.local.json
"""

_VSCODE_SETTINGS_CONTENT = """\
{
    "python.defaultInterpreterPath": "${workspaceFolder}/.venv/bin/python",
    "python.terminal.activateEnvironment": false,
    "terminal.integrated.env.linux": {
        "VIRTUAL_ENV": "${workspaceFolder}/.venv",
        "PATH": "${workspaceFolder}/.venv/bin:${env:PATH}",
        "VIRTUAL_ENV_DISABLE_PROMPT": "1"
    }
}
"""

_CLAUDE_SETTINGS_CONTENT = """\
{
  "permissions": {
    "allow": [
      "Bash(simctl *)",
      "Bash(uv run pytest*)",
      "Bash(uv run ruff*)",
      "Bash(uv run mypy*)",
      "Bash(source .venv/bin/activate*)",
      "Bash(cat runs/*/work/*.out*)",
      "Bash(cat runs/*/work/*.err*)",
      "Bash(git status*)",
      "Bash(git log*)",
      "Bash(git diff*)"
    ],
    "deny": [
      "Bash(rm -rf *)",
      "Bash(git push --force*)",
      "Bash(git reset --hard*)"
    ]
  }
}
"""

_RULE_SIMCTL_WORKFLOW = """\
# simctl ワークフロールール

## ファイル操作の制約
- run ディレクトリ (`Rxxxx/`) は手で作らない
- `manifest.toml` は手動編集しない
- `Rxxxx/input/*` は直接作らない
- `Rxxxx/submit/job.sh` は手書きしない
- run は必ず `simctl create` または `simctl sweep` で生成する
- `work/` と `.simctl/knowledge/` の自動生成物は手で整形しない
- `runs/**/input/*` を緊急修正した場合は、同じ修正を上流へ戻す
- `tools/hpc-simctl/` は参照用。通常は編集しない

## venv
- **simctl コマンド実行前に `.venv/` を activate する**

## case 作成
- **case は `simctl new` で生成する** (case.toml を手書きしない)

## 知見の記録
- 実験の知見・結果は Agent の memory ではなく `/learn` で保存する
- 保存先: `.simctl/insights/`, `.simctl/facts.toml`
- `high` confidence は複数 run の再現か deterministic 確認がある場合だけ使う
"""

_RULE_PLAN_BEFORE_ACT = """\
# 実行前ルール

複数ファイル編集または高コスト操作の前には、短い plan を出す。

```json
{
  "goal": "what you want to achieve",
  "edits": ["file1.toml", "file2.toml"],
  "commands": ["simctl sweep ...", "simctl run --all ..."],
  "checkpoints": ["Confirm survey size before bulk submit"]
}
```

- 高コスト操作では run 数・queue・retry 理由を書く
- plan にない高コスト操作をいきなり実行しない
- approval が必要な操作は、plan を出したところで止まる
"""


def _write_if_missing(path: Path, content: str) -> bool:
    """Write content to path if the file does not already exist.

    Args:
        path: File path to create.
        content: File content to write.

    Returns:
        True if the file was created, False if it already existed.
    """
    if path.exists():
        return False
    path.write_text(content, encoding="utf-8")
    return True


def _mkdir_if_missing(path: Path) -> bool:
    """Create a directory if it does not already exist.

    Args:
        path: Directory path to create.

    Returns:
        True if the directory was created, False if it already existed.
    """
    if path.exists():
        return False
    path.mkdir(parents=True)
    return True


_FACTS_DEFAULT = "# Structured facts\nfacts = []\n"
_LINKS_DEFAULT = "# Project links\n[projects]\n\n[shared]\n"


def _create_simctl_skeleton(project_dir: Path, created: list[str]) -> None:
    """Create .simctl/ skeleton (insights/, facts.toml, links.toml, knowledge/).

    Args:
        project_dir: Project root directory.
        created: Mutable list to append created items.
    """
    simctl_dir = project_dir / ".simctl"
    if _mkdir_if_missing(simctl_dir):
        created.append(".simctl/")
    if _mkdir_if_missing(simctl_dir / "insights"):
        created.append(".simctl/insights/")
    if _write_if_missing(simctl_dir / "facts.toml", _FACTS_DEFAULT):
        created.append(".simctl/facts.toml")
    if _write_if_missing(simctl_dir / "links.toml", _LINKS_DEFAULT):
        created.append(".simctl/links.toml")
    # Knowledge integration directories
    if _mkdir_if_missing(simctl_dir / "knowledge"):
        created.append(".simctl/knowledge/")
    if _mkdir_if_missing(simctl_dir / "knowledge" / "enabled"):
        created.append(".simctl/knowledge/enabled/")


def _build_simulators_toml(simulator_names: list[str]) -> str:
    """Build simulators.toml content from adapter default configs.

    Args:
        simulator_names: List of simulator adapter names (e.g. ["emses", "beach"]).

    Returns:
        TOML string for simulators.toml.

    Raises:
        typer.BadParameter: If a simulator name is not recognized.
    """
    # Ensure built-in adapters are registered
    import simctl.adapters  # noqa: F401
    from simctl.adapters.registry import get_global_registry

    registry = get_global_registry()
    available = registry.list_adapters()

    config: dict[str, Any] = {"simulators": {}}
    for sim_name in simulator_names:
        if sim_name not in available:
            msg = f"Unknown simulator: '{sim_name}'. Available: {', '.join(available)}"
            raise typer.BadParameter(msg)
        adapter_cls = registry.get(sim_name)
        config["simulators"][sim_name] = adapter_cls.default_config()

    if tomli_w is None:
        # Fallback to manual TOML generation
        lines = ["[simulators]", ""]
        for sim_name, sim_cfg in config["simulators"].items():
            lines.append(f"[simulators.{sim_name}]")
            for key, value in sim_cfg.items():
                if isinstance(value, list):
                    items = ", ".join(f'"{v}"' for v in value)
                    lines.append(f"{key} = [{items}]")
                elif isinstance(value, str):
                    lines.append(f'{key} = "{value}"')
                else:
                    lines.append(f"{key} = {value}")
            lines.append("")
        return "\n".join(lines) + "\n"

    import io

    buf = io.BytesIO()
    tomli_w.dump(config, buf)
    return buf.getvalue().decode("utf-8")


def _collect_pip_packages(simulator_names: list[str]) -> list[str]:
    """Collect unique pip packages from adapters."""
    import simctl.adapters  # noqa: F401
    from simctl.adapters.registry import get_global_registry

    registry = get_global_registry()
    seen: set[str] = set()
    packages: list[str] = []
    for sim_name in simulator_names:
        try:
            adapter_cls = registry.get(sim_name)
            for pkg in adapter_cls.pip_packages():
                if pkg not in seen:
                    seen.add(pkg)
                    packages.append(pkg)
        except KeyError:
            pass
    return packages


def _collect_doc_repos(simulator_names: list[str]) -> list[tuple[str, str]]:
    """Collect unique doc repos from adapters."""
    import simctl.adapters  # noqa: F401
    from simctl.adapters.registry import get_global_registry

    registry = get_global_registry()
    seen: set[str] = set()
    repos: list[tuple[str, str]] = []
    for sim_name in simulator_names:
        try:
            adapter_cls = registry.get(sim_name)
            for url, dest in adapter_cls.doc_repos():
                if dest not in seen:
                    seen.add(dest)
                    repos.append((url, dest))
        except KeyError:
            pass
    return repos


def _clone_doc_repos(
    project_dir: Path, simulator_names: list[str]
) -> tuple[list[str], list[str]]:
    """Clone documentation repos into project_dir/refs/.

    Returns:
        Tuple of (created_list, skipped_list).
    """
    repos = _collect_doc_repos(simulator_names)
    if not repos:
        return [], []

    created: list[str] = []
    skipped: list[str] = []
    refs_dir = project_dir / "refs"
    refs_dir.mkdir(exist_ok=True)

    for url, dest in repos:
        dest_path = refs_dir / dest
        rel = f"refs/{dest}"
        if dest_path.exists():
            skipped.append(rel)
            continue
        result = subprocess.run(
            ["git", "clone", "--depth", "1", url, str(dest_path)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        if result.returncode == 0:
            created.append(rel)
        else:
            logger.warning(
                "git clone %s failed: %s", url, (result.stderr or "").strip()
            )

    return created, skipped


def _build_simulator_guides(simulator_names: list[str]) -> str:
    """Collect agent_guide() from adapters for the given simulators."""
    import simctl.adapters  # noqa: F401
    from simctl.adapters.registry import get_global_registry

    registry = get_global_registry()
    parts: list[str] = []
    for sim_name in simulator_names:
        try:
            adapter_cls = registry.get(sim_name)
            parts.append(adapter_cls.agent_guide())
        except KeyError:
            pass
    return "\n".join(parts)


def _get_jinja_env() -> jinja2.Environment:
    """Return a Jinja2 environment that loads from simctl/templates/."""
    templates_dir = Path(__file__).resolve().parent.parent / "templates"
    return jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(templates_dir)),
        keep_trailing_newline=True,
        undefined=jinja2.StrictUndefined,
    )


def _discover_agent_docs(
    project_dir: Path, doc_repos: list[tuple[str, str]]
) -> list[str]:
    """Discover docs/agent-*.md files in cloned refs.

    Returns:
        List of relative paths like ``refs/MPIEMSES3D/docs/agent-user-guide.md``.
    """
    refs_dir = project_dir / "refs"
    paths: list[str] = []
    for _url, dest in doc_repos:
        docs_dir = refs_dir / dest / "docs"
        if not docs_dir.is_dir():
            continue
        for md in sorted(docs_dir.glob("agent-*.md")):
            if md.is_file():
                paths.append(f"refs/{dest}/docs/{md.name}")
    # Also check simctl's own agent docs in tools/hpc-simctl/docs/
    simctl_docs = project_dir / "tools" / "hpc-simctl" / "docs"
    if simctl_docs.is_dir():
        for md in sorted(simctl_docs.glob("agent-*.md")):
            if md.is_file():
                paths.append(f"tools/hpc-simctl/docs/{md.name}")
    return paths


def _build_agent_md(
    doc_name: str,
    project_name: str,
    simulator_names: list[str],
    *,
    agent_doc_imports: list[str] | None = None,
    knowledge_imports_path: str = "",
) -> str:
    """Build shared agent instructions for CLAUDE.md / AGENTS.md."""
    simulator_guides = ""
    if simulator_names:
        simulator_guides = _build_simulator_guides(simulator_names)

    doc_repos = _collect_doc_repos(simulator_names) if simulator_names else []

    env = _get_jinja_env()
    template = env.get_template("agent.md")
    return template.render(
        doc_name=doc_name,
        project_name=project_name,
        simulator_guides=simulator_guides,
        doc_repos=doc_repos,
        agent_doc_imports=agent_doc_imports or [],
        knowledge_imports_path=knowledge_imports_path,
    )


def _build_claude_md(
    project_name: str,
    simulator_names: list[str],
    *,
    agent_doc_imports: list[str] | None = None,
    knowledge_imports_path: str = "",
) -> str:
    """Build CLAUDE.md content."""
    return _build_agent_md(
        "CLAUDE.md",
        project_name,
        simulator_names,
        agent_doc_imports=agent_doc_imports,
        knowledge_imports_path=knowledge_imports_path,
    )


def _build_agents_md(
    project_name: str,
    simulator_names: list[str],
    *,
    agent_doc_imports: list[str] | None = None,
    knowledge_imports_path: str = "",
) -> str:
    """Build AGENTS.md content."""
    return _build_agent_md(
        "AGENTS.md",
        project_name,
        simulator_names,
        agent_doc_imports=agent_doc_imports,
        knowledge_imports_path=knowledge_imports_path,
    )


def _build_skills(project_name: str, simulator_names: list[str]) -> dict[str, str]:
    """Build individual SKILL.md contents for .claude/skills/.

    Returns:
        Mapping of ``<skill-name>/SKILL.md`` relative path to rendered content.
    """
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
        # Apply Jinja2 substitutions only if template variables are present
        if "{{" in content:
            env = _get_jinja_env()
            template = env.from_string(content)
            content = template.render(
                project_name=project_name,
                pip_install_line=pip_install_line,
            )
        rel = f"{skill_path.name}/SKILL.md"
        results[rel] = content
    return results


def _get_data_path() -> Path:
    """Return the path to the package's bundled _data directory.

    Falls back to the repository root when running in editable/dev mode
    where force-include has not been applied.
    """
    pkg_data = Path(str(importlib.resources.files("simctl") / "_data"))
    if (pkg_data / "README.md").is_file():
        return pkg_data
    # Dev mode fallback: walk up from this file to the repo root
    repo_root = Path(__file__).resolve().parent.parent.parent.parent
    if (repo_root / "README.md").is_file() and (repo_root / "docs").is_dir():
        return repo_root
    return pkg_data


def _copy_docs(project_dir: Path) -> tuple[list[str], list[str]]:
    """Copy bundled README.md and docs/ into the project directory.

    Returns:
        Tuple of (created_list, skipped_list).
    """
    created: list[str] = []
    skipped: list[str] = []
    data_path = _get_data_path()

    # README.md -> docs/simctl-guide.md
    readme_src = data_path / "README.md"
    readme_dst = project_dir / "docs" / "simctl-guide.md"
    if readme_dst.exists():
        skipped.append("docs/simctl-guide.md")
    elif readme_src.exists():
        readme_dst.parent.mkdir(exist_ok=True)
        shutil.copy2(readme_src, readme_dst)
        created.append("docs/simctl-guide.md")

    # docs/*.md
    docs_src = data_path / "docs"
    if docs_src.is_dir():
        docs_dst = project_dir / "docs"
        docs_dst.mkdir(exist_ok=True)
        for src_file in sorted(docs_src.iterdir()):
            if src_file.suffix == ".md":
                dst_file = docs_dst / src_file.name
                rel = f"docs/{src_file.name}"
                if dst_file.exists():
                    skipped.append(rel)
                else:
                    shutil.copy2(src_file, dst_file)
                    created.append(rel)

    return created, skipped


def _search_knowledge_repos() -> list[tuple[str, str]]:
    """Search GitHub for shared knowledge repos using ``gh``.

    Looks for repos matching ``*shared_knowledge*`` in the
    authenticated user's repositories.

    Returns:
        List of (full_name, clone_url) tuples.
    """
    result = subprocess.run(
        [
            "gh",
            "repo",
            "list",
            "--limit",
            "50",
            "--json",
            "nameWithOwner,sshUrl,description",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.returncode != 0:
        return []

    import json

    try:
        repos = json.loads(result.stdout)
    except (json.JSONDecodeError, TypeError):
        return []

    candidates: list[tuple[str, str]] = []
    for repo in repos:
        name = repo.get("nameWithOwner", "")
        # Match *shared_knowledge* pattern (case-insensitive)
        repo_name = name.rsplit("/", 1)[-1] if "/" in name else name
        if "shared_knowledge" in repo_name.lower():
            ssh_url = repo.get("sshUrl", "")
            if ssh_url:
                candidates.append((name, ssh_url))

    return candidates


def _prompt_knowledge_sources(
    project_dir: Path,
) -> list[Any]:
    """Interactively prompt the user to attach knowledge sources.

    Searches GitHub for repos matching ``*shared_knowledge*`` and
    offers them as candidates. Also allows manual URL entry.

    Returns:
        List of KnowledgeSource to attach.
    """
    from simctl.core.knowledge_source import KnowledgeSource

    want = typer.confirm("\nAttach shared knowledge repositories?", default=False)
    if not want:
        return []

    # Search for candidates
    typer.echo("  Searching GitHub for *shared_knowledge* repos...")
    candidates = _search_knowledge_repos()

    selected_sources: list[KnowledgeSource] = []

    if candidates:
        typer.echo("\n  Found knowledge repositories:")
        for i, (full_name, _url) in enumerate(candidates, 1):
            typer.echo(f"    {i}. {full_name}")

        selection = typer.prompt(
            "\n  Select repos (comma-separated numbers, Enter to skip)",
            default="",
        )

        for token in selection.split(","):
            token = token.strip()
            if not token:
                continue
            if token.isdigit():
                idx = int(token) - 1
                if 0 <= idx < len(candidates):
                    full_name, url = candidates[idx]
                    repo_name = full_name.rsplit("/", 1)[-1]
                    selected_sources.append(
                        KnowledgeSource(
                            name=repo_name,
                            source_type="git",
                            url=url,
                            ref="main",
                            mount=f"refs/knowledge/{repo_name}",
                        )
                    )
                else:
                    typer.echo(f"    Warning: ignoring invalid number '{token}'")
    else:
        typer.echo("  No *shared_knowledge* repos found on GitHub.")

    # Allow manual entry
    while True:
        manual = typer.prompt(
            "\n  Add a knowledge source manually? "
            "(git URL, local path, or Enter to finish)",
            default="",
        )
        if not manual.strip():
            break

        manual = manual.strip()
        # Detect type
        is_git = (
            manual.startswith("https://")
            or manual.startswith("http://")
            or manual.startswith("git@")
        )
        if is_git:
            # Extract name from URL
            stem = manual.rsplit("/", 1)[-1].rsplit(":", 1)[-1]
            if stem.endswith(".git"):
                stem = stem[:-4]
            source_name = typer.prompt("    Source name", default=stem)
            selected_sources.append(
                KnowledgeSource(
                    name=source_name,
                    source_type="git",
                    url=manual,
                    ref="main",
                    mount=f"refs/knowledge/{source_name}",
                )
            )
        else:
            # Local path
            p = Path(manual).expanduser()
            source_name = typer.prompt("    Source name", default=p.name)
            selected_sources.append(
                KnowledgeSource(
                    name=source_name,
                    source_type="path",
                    url=manual,
                    mount=f"refs/knowledge/{source_name}",
                )
            )
        typer.echo(f"    Added: {source_name}")

    if selected_sources:
        typer.echo(f"\n  {len(selected_sources)} knowledge source(s) selected.")
    return selected_sources


def _prompt_simulators() -> tuple[list[str], dict[str, dict[str, Any]]]:
    """Interactively prompt the user to select and configure simulators.

    Returns:
        Tuple of (simulator_names, {name: config_dict}).
    """
    import simctl.adapters  # noqa: F401
    from simctl.adapters.registry import get_global_registry

    registry = get_global_registry()
    available = registry.list_adapters()

    typer.echo("\nAvailable simulators:")
    for i, name in enumerate(available, 1):
        typer.echo(f"  {i}. {name}")

    selection = typer.prompt(
        "\nSelect simulators (comma-separated numbers or names, Enter to skip)",
        default="",
    )

    if not selection.strip():
        return [], {}

    # Parse selection — accept both numbers and names
    selected: list[str] = []
    for token in selection.split(","):
        token = token.strip()
        if not token:
            continue
        if token.isdigit():
            idx = int(token) - 1
            if 0 <= idx < len(available):
                selected.append(available[idx])
            else:
                typer.echo(f"  Warning: ignoring invalid number '{token}'")
        elif token in available:
            selected.append(token)
        else:
            typer.echo(f"  Warning: unknown simulator '{token}', skipping")

    if not selected:
        return [], {}

    # Interactive config for each selected simulator
    use_interactive = typer.confirm("\nCustomize simulator settings?", default=False)

    configs: dict[str, dict[str, Any]] = {}
    for sim_name in selected:
        adapter_cls = registry.get(sim_name)
        if use_interactive:
            configs[sim_name] = adapter_cls.interactive_config()
        else:
            configs[sim_name] = adapter_cls.default_config()

    return selected, configs


@dataclass
class _BundledSiteProfile:
    """A bundled site profile loaded from sites/*.toml.

    Used during ``simctl init`` to offer preconfigured site choices.
    The file uses the same ``[site]`` format as project-level ``site.toml``,
    plus an optional ``[launcher]`` section for launcher defaults.

    Attributes:
        name: Site name (file stem, e.g. "camphor").
        launcher: Launcher-only configuration dict for launchers.toml.
        source_path: Path to the bundled .toml file (copied as site.toml).
        docs_path: Path to companion .md documentation (may not exist).
    """

    name: str
    launcher: dict[str, Any]
    source_path: Path
    docs_path: Path | None = None


# Legacy alias for backward compatibility with code that references the old name.
SiteProfile = _BundledSiteProfile


def _load_site_profiles() -> dict[str, _BundledSiteProfile]:
    """Load site profiles from bundled TOML files in simctl/sites/.

    Each file uses the unified format:
    - ``[site]`` section → copied as-is to project ``site.toml``
    - ``[launcher]`` section → used for ``launchers.toml`` defaults
    """
    sites_dir = Path(__file__).resolve().parent.parent / "sites"
    profiles: dict[str, _BundledSiteProfile] = {}
    if not sites_dir.is_dir():
        return profiles
    for toml_file in sorted(sites_dir.glob("*.toml")):
        with open(toml_file, "rb") as f:
            data = tomllib.load(f)
        # Require at least a [site] or [launcher] section
        if "site" not in data and "launcher" not in data:
            continue
        launcher_data = dict(data.get("launcher", {}))
        docs_file = toml_file.with_suffix(".md")
        profiles[toml_file.stem] = _BundledSiteProfile(
            name=toml_file.stem,
            launcher=launcher_data,
            source_path=toml_file,
            docs_path=docs_file if docs_file.is_file() else None,
        )
    return profiles


def _prompt_launchers() -> tuple[dict[str, dict[str, Any]], _BundledSiteProfile | None]:
    """Interactively prompt for launcher configuration.

    Returns:
        Tuple of (launcher config dict, selected _BundledSiteProfile or None).
    """
    site_profiles = _load_site_profiles()

    typer.echo("\nLauncher configuration:")
    typer.echo("  Site profiles (preconfigured):")
    site_names = list(site_profiles.keys())
    for i, sname in enumerate(site_names, start=1):
        typer.echo(f"    {i}. {sname}")
    offset = len(site_names)
    typer.echo("  Launcher types:")
    typer.echo(f"    {offset + 1}. srun (Slurm)")
    typer.echo(f"    {offset + 2}. mpirun (OpenMPI)")
    typer.echo(f"    {offset + 3}. mpiexec (MPICH)")

    selection = typer.prompt(
        "\nSelect site profile or launcher type (number or name, Enter to skip)",
        default="",
    )

    sel = selection.strip()
    if not sel:
        return {}, None

    # Check site profiles first
    site_map = {str(i): name for i, name in enumerate(site_names, start=1)}
    if sel in site_map:
        profile_name = site_map[sel]
        profile = site_profiles[profile_name]
        return {profile_name: dict(profile.launcher)}, profile
    if sel in site_profiles:
        profile = site_profiles[sel]
        return {sel: dict(profile.launcher)}, profile

    # Launcher types
    launcher_map = {
        str(offset + 1): "srun",
        str(offset + 2): "mpirun",
        str(offset + 3): "mpiexec",
    }
    launcher_type = launcher_map.get(sel, sel)

    if launcher_type not in ("srun", "mpirun", "mpiexec"):
        typer.echo(f"  Unknown selection '{sel}', skipping")
        return {}, None

    launcher_name = typer.prompt("  Launcher profile name", default=launcher_type)

    config: dict[str, Any] = {"type": launcher_type}

    if launcher_type == "srun":
        use_slurm = typer.confirm(
            "  Use SLURM_NTASKS (rely on #SBATCH --ntasks)?", default=True
        )
        config["use_slurm_ntasks"] = use_slurm
        config["args"] = typer.prompt(
            "  Extra srun arguments (e.g. --mpi=pmix)", default=""
        )
    elif launcher_type in ("mpirun", "mpiexec"):
        config["args"] = typer.prompt(f"  Extra {launcher_type} arguments", default="")

    # Module loading
    modules_str = typer.prompt(
        "  Modules to load (space-separated, Enter to skip)", default=""
    )
    if modules_str.strip():
        config["modules"] = modules_str.strip().split()

    # Clean empty args
    if not config.get("args"):
        config.pop("args", None)

    return {launcher_name: config}, None


def _build_simulators_toml_from_configs(
    configs: dict[str, dict[str, Any]],
) -> str:
    """Serialize simulator configs to TOML string."""
    full_config: dict[str, Any] = {"simulators": configs}

    if tomli_w is None:
        lines = ["[simulators]", ""]
        for sim_name, sim_cfg in configs.items():
            lines.append(f"[simulators.{sim_name}]")
            for key, value in sim_cfg.items():
                if isinstance(value, list):
                    items = ", ".join(f'"{v}"' for v in value)
                    lines.append(f"{key} = [{items}]")
                elif isinstance(value, str):
                    lines.append(f'{key} = "{value}"')
                else:
                    lines.append(f"{key} = {value}")
            lines.append("")
        return "\n".join(lines) + "\n"

    import io

    buf = io.BytesIO()
    tomli_w.dump(full_config, buf)
    return buf.getvalue().decode("utf-8")


def _build_launchers_toml(launchers: dict[str, dict[str, Any]]) -> str:
    """Serialize launcher configs to TOML string."""
    if not launchers:
        return "[launchers]\n"

    full_config: dict[str, Any] = {"launchers": launchers}

    if tomli_w is None:
        lines = ["[launchers]", ""]
        for name, cfg in launchers.items():
            lines.append(f"[launchers.{name}]")
            for key, value in cfg.items():
                if isinstance(value, list):
                    items = ", ".join(f'"{v}"' for v in value)
                    lines.append(f"{key} = [{items}]")
                elif isinstance(value, str):
                    lines.append(f'{key} = "{value}"')
                elif isinstance(value, bool):
                    lines.append(f"{key} = {str(value).lower()}")
                else:
                    lines.append(f"{key} = {value}")
            lines.append("")
        return "\n".join(lines) + "\n"

    import io

    buf = io.BytesIO()
    tomli_w.dump(full_config, buf)
    return buf.getvalue().decode("utf-8")


def _build_campaign_toml(project_name: str, simulator_names: list[str]) -> str:
    """Build a minimal campaign.toml skeleton."""
    lines = [
        f"#:schema {_SCHEMA_BASE_URL}/campaign.json",
        "[campaign]",
        f'name = "{project_name}"',
        'description = ""',
        'hypothesis = ""',
    ]
    if simulator_names:
        lines.append(f'simulator = "{simulator_names[0]}"')
    lines.extend(
        [
            "",
            "[variables]",
            "",
            "[observables]",
            "",
        ]
    )
    return "\n".join(lines)


def _venv_pip_executable(venv_dir: Path) -> Path:
    """Return the pip executable path inside a virtual environment."""
    if sys.platform == "win32":
        return venv_dir / "Scripts" / "pip.exe"
    return venv_dir / "bin" / "pip"


def _find_uv() -> str:
    """Find the uv executable, falling back to 'uv'."""
    uv_path = shutil.which("uv")
    return uv_path if uv_path else "uv"


def _bootstrap_environment(
    project_dir: Path,
    sim_names: list[str],
    simctl_repo: str,
    created: list[str],
    skipped: list[str],
) -> None:
    """Bootstrap .venv, clone hpc-simctl into tools/, and editable-install.

    Args:
        project_dir: Project root directory.
        sim_names: List of simulator names for pip packages.
        simctl_repo: Git URL for hpc-simctl repository.
        created: Mutable list to append created items.
        skipped: Mutable list to append skipped items.
    """
    uv = _find_uv()
    venv_dir = project_dir / ".venv"
    tools_dir = project_dir / "tools"
    simctl_dir = tools_dir / "hpc-simctl"

    # 1. Create .venv via uv
    if venv_dir.exists():
        skipped.append(".venv")
    else:
        typer.echo("  Creating .venv ...")
        venv_result = subprocess.run(
            [uv, "venv", str(venv_dir)],
            cwd=str(project_dir),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        if venv_result.returncode == 0:
            created.append(".venv")
        else:
            typer.echo(
                f"  Warning: uv venv failed: {(venv_result.stderr or '').strip()}"
            )
            return

    # 2. Clone hpc-simctl into tools/
    if simctl_dir.exists():
        skipped.append("tools/hpc-simctl")
    else:
        typer.echo("  Cloning hpc-simctl into tools/ ...")
        tools_dir.mkdir(exist_ok=True)
        clone_result = subprocess.run(
            ["git", "clone", simctl_repo, str(simctl_dir)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        if clone_result.returncode == 0:
            created.append("tools/hpc-simctl")
        else:
            typer.echo(
                f"  Warning: git clone failed: "
                f"{(clone_result.stderr or '').strip()[:300]}"
            )
            return

    # 3. Editable install simctl into .venv
    typer.echo("  Installing hpc-simctl (editable) ...")
    install_result = subprocess.run(
        [
            uv,
            "pip",
            "install",
            "-e",
            str(simctl_dir),
            "--python",
            str(
                venv_dir
                / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
            ),
        ],
        cwd=str(project_dir),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if install_result.returncode == 0:
        created.append("uv pip install -e tools/hpc-simctl")
    else:
        typer.echo(
            f"  Warning: editable install failed:\n"
            f"    {(install_result.stderr or '').strip()[:300]}"
        )

    # 4. Install simulator-specific packages
    pip_pkgs = _collect_pip_packages(sim_names) if sim_names else []
    if pip_pkgs:
        typer.echo(f"  Installing: {', '.join(pip_pkgs)} ...")
        pkg_result = subprocess.run(
            [
                uv,
                "pip",
                "install",
                *pip_pkgs,
                "--python",
                str(
                    venv_dir
                    / (
                        "Scripts/python.exe"
                        if sys.platform == "win32"
                        else "bin/python"
                    )
                ),
            ],
            cwd=str(project_dir),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        if pkg_result.returncode == 0:
            created.append(f"pip install ({len(pip_pkgs)} packages)")
        else:
            typer.echo(
                f"  Warning: pip install failed:\n"
                f"    {(pkg_result.stderr or '').strip()[:300]}"
            )

    # 5. Activation hint
    if sys.platform == "win32":
        activate_cmd = r".venv\Scripts\activate"
    else:
        activate_cmd = "source .venv/bin/activate"
    typer.echo(f"\n  Next: {activate_cmd}")
    typer.echo("  Then: simctl doctor")


def _create_subdirectory_claude_md(
    project_dir: Path,
    sim_names: list[str],
    created: list[str],
    skipped: list[str],
) -> None:
    """Create context-specific CLAUDE.md in cases/ and runs/ subdirectories.

    These are lazily loaded by Claude Code when the agent navigates into
    the subdirectory, providing focused context without bloating the root
    CLAUDE.md.
    """
    # cases/CLAUDE.md
    cases_md = project_dir / "cases" / "CLAUDE.md"
    if cases_md.parent.exists():
        if _write_if_missing(cases_md, _CASES_CLAUDE_MD):
            created.append("cases/CLAUDE.md")
        else:
            skipped.append("cases/CLAUDE.md")

    # runs/CLAUDE.md
    runs_md = project_dir / "runs" / "CLAUDE.md"
    if runs_md.parent.exists():
        if _write_if_missing(runs_md, _RUNS_CLAUDE_MD):
            created.append("runs/CLAUDE.md")
        else:
            skipped.append("runs/CLAUDE.md")


_CASES_CLAUDE_MD = """\
# cases/ ディレクトリ

ここには simulation case の定義を置く。

## 構造

```
cases/<simulator>/<case-name>/
  case.toml          # パラメータ定義
  survey.toml        # (optional) パラメータ掃引定義
  templates/         # 入力テンプレート
```

## ルール

- case は `simctl new <name>` で生成する (手書きしない)
- survey 付きは `simctl new <name> --survey`
- case.toml の編集は自由だが、フォーマットは `simctl-reference` スキルを参照
- テンプレートの Jinja2 変数は case.toml の `[parameters]` から展開される
"""

_RUNS_CLAUDE_MD = """\
# runs/ ディレクトリ

ここには simulation run が格納される。すべて `simctl create` / `simctl sweep` で生成。

## 構造

```
runs/<path>/Rxxxx/
  manifest.toml      # 正本 (状態・由来・provenance)
  input/             # 入力ファイル (自動生成)
  submit/            # job.sh 等 (自動生成)
  work/              # 実行時出力 (.gitignore 対象)
  analysis/          # 解析結果
```

## ルール

- run ディレクトリ (`Rxxxx/`) を手で作らない
- `manifest.toml` を手動編集しない
- `input/*`, `submit/job.sh` を直接作らない
- 状態確認は `simctl status`、同期は `simctl sync`
- 解析は `simctl summarize` / `simctl collect`
"""


def init(
    simulators: Annotated[
        Optional[list[str]],
        typer.Argument(help="Simulator names to configure (e.g. emses beach)."),
    ] = None,
    path: Annotated[
        Optional[Path],
        typer.Option("--path", "-p", help="Directory to initialize (defaults to cwd)."),
    ] = None,
    name: Annotated[
        Optional[str],
        typer.Option("--name", "-n", help="Project name (defaults to directory name)."),
    ] = None,
    yes: Annotated[
        bool,
        typer.Option("--yes", "-y", help="Skip interactive prompts, use defaults."),
    ] = False,
    simctl_repo: Annotated[
        str,
        typer.Option(
            "--simctl-repo",
            help="Git URL for hpc-simctl repository.",
        ),
    ] = _DEFAULT_SIMCTL_REPO,
) -> None:
    """Initialize a new simctl project (simproject.toml etc.).

    By default, runs in interactive mode with guided prompts.
    Use --yes / -y to skip prompts and use defaults.

    Simulator names can also be passed directly:
      simctl init emses beach

    Bootstrap usage (no prior install needed):
      uvx --from hpc-simctl simctl init
    """
    interactive = not yes
    project_dir = (path or Path.cwd()).resolve()

    if not project_dir.exists():
        project_dir.mkdir(parents=True)

    # Interactive project name
    if interactive and not name:
        project_name = typer.prompt("Project name", default=project_dir.name)
    else:
        project_name = name or project_dir.name

    created: list[str] = []
    skipped: list[str] = []

    # simproject.toml
    simproject_content = (
        f"#:schema {_SCHEMA_BASE_URL}/simproject.json\n"
        f'[project]\nname = "{project_name}"\ndescription = ""\n'
    )
    if _write_if_missing(project_dir / _SIMPROJECT_FILE, simproject_content):
        created.append(_SIMPROJECT_FILE)
    else:
        skipped.append(_SIMPROJECT_FILE)

    # simulators.toml
    sim_configs: dict[str, dict[str, Any]] = {}
    sim_names: list[str] = []

    if simulators:
        sim_names = simulators
        sim_content = _build_simulators_toml(simulators)
    elif interactive:
        sim_names, sim_configs = _prompt_simulators()
        if sim_configs:
            sim_content = _build_simulators_toml_from_configs(sim_configs)
        else:
            sim_content = "[simulators]\n"
    else:
        sim_content = "[simulators]\n"

    sim_schema = f"#:schema {_SCHEMA_BASE_URL}/simulators.json\n"
    sim_content = sim_schema + sim_content
    if _write_if_missing(project_dir / _SIMULATORS_FILE, sim_content):
        created.append(_SIMULATORS_FILE)
    else:
        skipped.append(_SIMULATORS_FILE)

    # launchers.toml
    site_profile: _BundledSiteProfile | None = None
    if interactive:
        launcher_configs, site_profile = _prompt_launchers()
        launcher_content = _build_launchers_toml(launcher_configs)
    else:
        launcher_configs = {
            "srun": {"type": "srun", "use_slurm_ntasks": True},
        }
        launcher_content = _build_launchers_toml(launcher_configs)

    launcher_schema = f"#:schema {_SCHEMA_BASE_URL}/launchers.json\n"
    launcher_content = launcher_schema + launcher_content
    if _write_if_missing(project_dir / _LAUNCHERS_FILE, launcher_content):
        created.append(_LAUNCHERS_FILE)
    else:
        skipped.append(_LAUNCHERS_FILE)

    # site.toml — copy from bundled site profile
    if site_profile:
        from simctl.core.site import _load_site_toml

        site_file = project_dir / "site.toml"
        if not site_file.exists():
            # Read bundled file, write only the [site] sections (strip [launcher])
            with open(site_profile.source_path, "rb") as f:
                bundled_data = tomllib.load(f)
            site_only: dict[str, Any] = {}
            if "site" in bundled_data:
                site_only["site"] = bundled_data["site"]
            if site_only and tomli_w is not None:
                with open(site_file, "wb") as f:
                    tomli_w.dump(site_only, f)
                created.append("site.toml")
            elif site_only:
                skipped.append("site.toml (tomli_w not available)")
        else:
            skipped.append("site.toml")

        # Apply per-simulator modules from site profile to simulators.toml
        site_data_loaded = _load_site_toml(site_profile.source_path)
        if site_data_loaded.simulator_modules:
            sim_file = project_dir / _SIMULATORS_FILE
            if sim_file.exists():
                with open(sim_file, "rb") as f:
                    existing = tomllib.load(f)
                sims = existing.get("simulators", {})
                updated = False
                for (
                    sim_name,
                    site_modules,
                ) in site_data_loaded.simulator_modules.items():
                    if sim_name in sims and site_modules:
                        sims[sim_name]["modules"] = site_modules
                        updated = True
                if updated and tomli_w is not None:
                    existing["simulators"] = sims
                    with open(sim_file, "wb") as f:
                        tomli_w.dump(existing, f)

    # SITE.md — copy companion docs from bundled site profile
    if site_profile and site_profile.docs_path:
        site_md = project_dir / "SITE.md"
        if site_md.exists():
            skipped.append("SITE.md")
        else:
            shutil.copy2(site_profile.docs_path, site_md)
            created.append("SITE.md")

    # campaign.toml
    campaign_content = _build_campaign_toml(project_name, sim_names)
    if _write_if_missing(project_dir / _CAMPAIGN_FILE, campaign_content):
        created.append(_CAMPAIGN_FILE)
    else:
        skipped.append(_CAMPAIGN_FILE)

    # cases/ directory (with per-simulator subdirectories)
    if _mkdir_if_missing(project_dir / "cases"):
        created.append("cases/")
    else:
        skipped.append("cases/")
    for sim in sim_names:
        sim_cases_dir = project_dir / "cases" / sim
        if _mkdir_if_missing(sim_cases_dir):
            created.append(f"cases/{sim}/")

    # runs/ directory
    if _mkdir_if_missing(project_dir / "runs"):
        created.append("runs/")
    else:
        skipped.append("runs/")

    # .simctl/ skeleton (insights, facts, links)
    _create_simctl_skeleton(project_dir, created)

    # refs/ — clone simulator doc repos
    if sim_names:
        refs_created, refs_skipped = _clone_doc_repos(project_dir, sim_names)
        created.extend(refs_created)
        skipped.extend(refs_skipped)

    # .gitignore
    if _write_if_missing(project_dir / ".gitignore", _GITIGNORE_CONTENT):
        created.append(".gitignore")
    else:
        skipped.append(".gitignore")

    # Interactive knowledge source selection
    if interactive:
        knowledge_sources = _prompt_knowledge_sources(project_dir)
        if knowledge_sources:
            from simctl.core.knowledge_source import save_knowledge_source

            for ks in knowledge_sources:
                save_knowledge_source(project_dir, ks)

    # Discover agent docs from refs/ and tools/hpc-simctl/docs/
    doc_repos = _collect_doc_repos(sim_names) if sim_names else []
    agent_doc_imports = _discover_agent_docs(project_dir, doc_repos)

    # Knowledge integration: sync sources and render imports if configured
    knowledge_imports_path = ""
    from simctl.core.knowledge_source import (
        load_knowledge_config as _load_kc,
    )
    from simctl.core.knowledge_source import (
        render_imports as _render_imports,
    )
    from simctl.core.knowledge_source import (
        sync_all_sources as _sync_all,
    )

    kc = _load_kc(project_dir)
    if kc is not None and kc.sources:
        typer.echo("Syncing knowledge sources...")
        for name, status in _sync_all(project_dir, kc):
            typer.echo(f"  {name}: {status}")
        _render_imports(project_dir, kc)
    if kc is not None and kc.generate_claude_imports:
        imports_file = project_dir / kc.derived_dir / "enabled" / "imports.md"
        if imports_file.is_file():
            knowledge_imports_path = f"{kc.derived_dir}/enabled/imports.md"

    # CLAUDE.md (use sim_names from earlier — may come from args or interactive)
    claude_content = _build_claude_md(
        project_name,
        sim_names,
        agent_doc_imports=agent_doc_imports,
        knowledge_imports_path=knowledge_imports_path,
    )
    if _write_if_missing(project_dir / _CLAUDE_MD, claude_content):
        created.append(_CLAUDE_MD)
    else:
        skipped.append(_CLAUDE_MD)

    # AGENTS.md
    agents_content = _build_agents_md(
        project_name,
        sim_names,
        agent_doc_imports=agent_doc_imports,
        knowledge_imports_path=knowledge_imports_path,
    )
    if _write_if_missing(project_dir / _AGENTS_MD, agents_content):
        created.append(_AGENTS_MD)
    else:
        skipped.append(_AGENTS_MD)

    # .claude/skills/<name>/SKILL.md
    skills = _build_skills(project_name, sim_names)
    skills_base = project_dir / _SKILLS_DIR
    skills_base.mkdir(parents=True, exist_ok=True)
    for rel_path, content in skills.items():
        skill_file = skills_base / rel_path
        skill_file.parent.mkdir(parents=True, exist_ok=True)
        display = f"{_SKILLS_DIR}/{rel_path}"
        if _write_if_missing(skill_file, content):
            created.append(display)
        else:
            skipped.append(display)

    # .claude/settings.json (team-shared permissions)
    claude_settings_path = project_dir / _CLAUDE_SETTINGS
    claude_settings_path.parent.mkdir(parents=True, exist_ok=True)
    if _write_if_missing(claude_settings_path, _CLAUDE_SETTINGS_CONTENT):
        created.append(_CLAUDE_SETTINGS)
    else:
        skipped.append(_CLAUDE_SETTINGS)

    # .claude/rules/ (project-wide rules, split from CLAUDE.md)
    rules_base = project_dir / _RULES_DIR
    rules_base.mkdir(parents=True, exist_ok=True)
    for rule_name, rule_content in [
        ("simctl-workflow.md", _RULE_SIMCTL_WORKFLOW),
        ("plan-before-act.md", _RULE_PLAN_BEFORE_ACT),
    ]:
        rule_path = rules_base / rule_name
        display = f"{_RULES_DIR}/{rule_name}"
        if _write_if_missing(rule_path, rule_content):
            created.append(display)
        else:
            skipped.append(display)

    # Subdirectory CLAUDE.md files (lazy-loaded context)
    _create_subdirectory_claude_md(project_dir, sim_names, created, skipped)

    # .vscode/settings.json
    vscode_dir = project_dir / _VSCODE_DIR
    vscode_settings = vscode_dir / _VSCODE_SETTINGS
    if vscode_settings.exists():
        skipped.append(f"{_VSCODE_DIR}/{_VSCODE_SETTINGS}")
    else:
        vscode_dir.mkdir(exist_ok=True)
        vscode_settings.write_text(_VSCODE_SETTINGS_CONTENT, encoding="utf-8")
        created.append(f"{_VSCODE_DIR}/{_VSCODE_SETTINGS}")

    # git init
    fresh_git = False
    if (project_dir / ".git").exists():
        skipped.append("git init")
    else:
        result = subprocess.run(
            ["git", "init"],
            cwd=project_dir,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        if result.returncode == 0:
            created.append("git init")
            fresh_git = True
        else:
            typer.echo(f"  Warning: git init failed: {(result.stderr or '').strip()}")

    # Bootstrap: .venv + tools/hpc-simctl + editable install
    _bootstrap_environment(project_dir, sim_names, simctl_repo, created, skipped)

    # Initial commit (only for freshly created repos)
    if fresh_git:
        subprocess.run(
            ["git", "add", "."],
            cwd=project_dir,
            capture_output=True,
            check=False,
        )
        result = subprocess.run(
            ["git", "commit", "-m", "Initial commit"],
            cwd=project_dir,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        if result.returncode == 0:
            created.append("git commit (Initial commit)")
        else:
            typer.echo(
                f"  Warning: initial commit failed: {(result.stderr or '').strip()}"
            )

    # Print results
    typer.echo(f"Initialized project '{project_name}' in {project_dir}")
    if created:
        typer.echo("  Created:")
        for item in created:
            typer.echo(f"    {item}")
    if skipped:
        typer.echo("  Skipped (already exist):")
        for item in skipped:
            typer.echo(f"    {item}")


def doctor(
    path: Annotated[
        Optional[Path],
        typer.Argument(help="Project directory to check."),
    ] = None,
) -> None:
    """Check the environment and project configuration for issues."""
    project_dir = (path or Path.cwd()).resolve()
    failures: list[str] = []

    # Check simproject.toml exists and is valid
    simproject_path = project_dir / _SIMPROJECT_FILE
    if not simproject_path.exists():
        typer.echo("[FAIL] simproject.toml not found")
        failures.append(_SIMPROJECT_FILE)
    else:
        try:
            load_project(project_dir)
            typer.echo("[PASS] simproject.toml is valid")
        except ProjectConfigError as e:
            typer.echo(f"[FAIL] simproject.toml: {e}")
            failures.append(_SIMPROJECT_FILE)

    # Check simulators.toml exists
    if (project_dir / _SIMULATORS_FILE).exists():
        typer.echo("[PASS] simulators.toml found")
    else:
        typer.echo("[FAIL] simulators.toml not found")
        failures.append(_SIMULATORS_FILE)

    # Check launchers.toml exists
    if (project_dir / _LAUNCHERS_FILE).exists():
        typer.echo("[PASS] launchers.toml found")
    else:
        typer.echo("[FAIL] launchers.toml not found")
        failures.append(_LAUNCHERS_FILE)

    # Check sbatch availability
    if shutil.which("sbatch") is not None:
        typer.echo("[PASS] sbatch is available")
    else:
        typer.echo("[FAIL] sbatch not found in PATH")
        failures.append("sbatch")

    # Check simulator adapters from simulators.toml
    simulators_path = project_dir / _SIMULATORS_FILE
    if simulators_path.exists():
        try:
            with open(simulators_path, "rb") as f:
                sim_data = tomllib.load(f)
            simulators: dict[str, Any] = sim_data.get("simulators", {})
            if simulators:
                from simctl.adapters.registry import AdapterRegistry

                registry = AdapterRegistry()
                for sim_name, sim_cfg in simulators.items():
                    if not isinstance(sim_cfg, dict):
                        continue
                    adapter_name = sim_cfg.get("adapter", "")
                    if not adapter_name:
                        continue
                    try:
                        registry.load_from_config({"simulators": {sim_name: sim_cfg}})
                        typer.echo(
                            f"[PASS] Simulator adapter '{adapter_name}' "
                            f"for '{sim_name}' is importable"
                        )
                    except Exception as e:
                        typer.echo(
                            f"[FAIL] Simulator adapter '{adapter_name}' "
                            f"for '{sim_name}': {e}"
                        )
                        failures.append(f"adapter:{adapter_name}")
        except tomllib.TOMLDecodeError as e:
            typer.echo(f"[FAIL] simulators.toml parse error: {e}")
            failures.append(_SIMULATORS_FILE)

    # Check launcher configs from launchers.toml
    launchers_path = project_dir / _LAUNCHERS_FILE
    if launchers_path.exists():
        try:
            with open(launchers_path, "rb") as f:
                launcher_data = tomllib.load(f)
            launchers: dict[str, Any] = launcher_data.get("launchers", {})
            if launchers:
                from simctl.launchers.base import Launcher, LauncherConfigError

                for lname, lcfg in launchers.items():
                    if not isinstance(lcfg, dict):
                        continue
                    try:
                        Launcher.from_config(lname, lcfg)
                        typer.echo(f"[PASS] Launcher profile '{lname}' is valid")
                    except LauncherConfigError as e:
                        typer.echo(f"[FAIL] Launcher profile '{lname}': {e}")
                        failures.append(f"launcher:{lname}")
        except tomllib.TOMLDecodeError as e:
            typer.echo(f"[FAIL] launchers.toml parse error: {e}")
            failures.append(_LAUNCHERS_FILE)

    # Check run_id uniqueness
    runs_dir = project_dir / "runs"
    if runs_dir.is_dir():
        try:
            validate_uniqueness(runs_dir)
            typer.echo("[PASS] No duplicate run_ids")
        except DuplicateRunIdError as e:
            typer.echo(f"[FAIL] Duplicate run_id: {e}")
            failures.append("run_id uniqueness")
    else:
        typer.echo("[PASS] No runs/ directory (nothing to check)")

    # Environment detection
    typer.echo("\n--- Environment ---")
    try:
        from simctl.core.environment import (
            detect_environment,
            load_environment,
            save_environment,
        )

        existing = load_environment(project_dir)
        if existing:
            typer.echo(
                f"[PASS] environment.toml found (cluster: {existing.cluster_name})"
            )
            if existing.partitions:
                for p in existing.partitions:
                    default_mark = " (default)" if p.default else ""
                    typer.echo(f"       partition: {p.name}{default_mark}")
        else:
            typer.echo("[INFO] Detecting environment...")
            env_info = detect_environment()
            if env_info.partitions:
                typer.echo(
                    f"       Detected {len(env_info.partitions)} Slurm partition(s)"
                )
            try:
                env_path = save_environment(project_dir, env_info)
                typer.echo(
                    f"[PASS] Saved environment to {env_path.relative_to(project_dir)}"
                )
            except RuntimeError:
                typer.echo(
                    "[WARN] Could not save environment.toml (tomli_w not installed)"
                )
    except Exception as e:
        typer.echo(f"[WARN] Environment detection failed: {e}")

    # Campaign check
    campaign_file = project_dir / "campaign.toml"
    if campaign_file.is_file():
        try:
            from simctl.core.campaign import load_campaign

            campaign = load_campaign(project_dir)
            if campaign:
                typer.echo(f"[PASS] campaign.toml: {campaign.name}")
        except Exception as e:
            typer.echo(f"[FAIL] campaign.toml: {e}")
            failures.append("campaign.toml")
    else:
        typer.echo("[INFO] No campaign.toml (optional)")

    # Final verdict
    if failures:
        typer.echo(f"\n{len(failures)} check(s) failed.")
        raise typer.Exit(code=1)
    else:
        typer.echo("\nAll checks passed.")
