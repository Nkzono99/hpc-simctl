"""Tests for simctl.core.knowledge_source module."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from simctl.core.knowledge_source import (
    KnowledgeConfig,
    KnowledgeSource,
    discover_profiles,
    load_knowledge_config,
    remove_knowledge_source,
    render_imports,
    save_knowledge_source,
    sync_source,
    validate_source_structure,
)


def _create_project(tmp_path: Path, extra_toml: str = "") -> Path:
    content = f'[project]\nname = "test-project"\n{extra_toml}'
    (tmp_path / "simproject.toml").write_text(content)
    return tmp_path


def _create_knowledge_source(tmp_path: Path, name: str = "test-kb") -> Path:
    """Create a minimal knowledge source directory."""
    kb_dir = tmp_path / name
    kb_dir.mkdir()
    (kb_dir / "README.md").write_text("# Test Knowledge\n")
    profiles_dir = kb_dir / "profiles"
    profiles_dir.mkdir()
    (profiles_dir / "common.md").write_text("# Common Profile\nCommon knowledge.\n")
    (profiles_dir / "advanced.md").write_text("# Advanced Profile\nAdvanced.\n")
    return kb_dir


# ---------- load_knowledge_config ----------


def test_load_knowledge_config_returns_none_when_no_section(tmp_path: Path) -> None:
    _create_project(tmp_path)
    assert load_knowledge_config(tmp_path) is None


def test_load_knowledge_config_parses_sources(tmp_path: Path) -> None:
    toml = """
[knowledge]
enabled = true
mount_dir = "refs/knowledge"

[[knowledge.sources]]
name = "shared-kb"
type = "git"
url = "https://github.com/lab/kb.git"
ref = "main"
mount = "refs/knowledge/shared-kb"
profiles = ["common", "emses"]

[[knowledge.sources]]
name = "local-kb"
type = "path"
path = "../my-kb"
mount = "refs/knowledge/local-kb"
"""
    _create_project(tmp_path, toml)
    config = load_knowledge_config(tmp_path)

    assert config is not None
    assert config.enabled is True
    assert len(config.sources) == 2

    git_src = config.sources[0]
    assert git_src.name == "shared-kb"
    assert git_src.source_type == "git"
    assert git_src.url == "https://github.com/lab/kb.git"
    assert git_src.ref == "main"
    assert git_src.profiles == ["common", "emses"]

    path_src = config.sources[1]
    assert path_src.name == "local-kb"
    assert path_src.source_type == "path"
    assert path_src.url == "../my-kb"


def test_load_knowledge_config_defaults(tmp_path: Path) -> None:
    _create_project(tmp_path, "\n[knowledge]\n")
    config = load_knowledge_config(tmp_path)

    assert config is not None
    assert config.enabled is True
    assert config.mount_dir == "refs/knowledge"
    assert config.derived_dir == ".simctl/knowledge"
    assert config.auto_sync_on_setup is True
    assert config.generate_claude_imports is True
    assert config.sources == []


# ---------- save_knowledge_source ----------


def test_save_knowledge_source_creates_section(tmp_path: Path) -> None:
    _create_project(tmp_path)
    source = KnowledgeSource(
        name="test-kb",
        source_type="git",
        url="https://github.com/lab/kb.git",
        mount="refs/knowledge/test-kb",
        profiles=["common"],
    )
    save_knowledge_source(tmp_path, source)

    config = load_knowledge_config(tmp_path)
    assert config is not None
    assert len(config.sources) == 1
    assert config.sources[0].name == "test-kb"
    assert config.sources[0].profiles == ["common"]


def test_save_knowledge_source_replaces_existing(tmp_path: Path) -> None:
    _create_project(tmp_path)
    source1 = KnowledgeSource(
        name="kb", source_type="git", url="https://old.git",
        mount="refs/knowledge/kb",
    )
    save_knowledge_source(tmp_path, source1)

    source2 = KnowledgeSource(
        name="kb", source_type="git", url="https://new.git",
        mount="refs/knowledge/kb", profiles=["updated"],
    )
    save_knowledge_source(tmp_path, source2)

    config = load_knowledge_config(tmp_path)
    assert config is not None
    assert len(config.sources) == 1
    assert config.sources[0].url == "https://new.git"
    assert config.sources[0].profiles == ["updated"]


def test_save_knowledge_source_path_type(tmp_path: Path) -> None:
    _create_project(tmp_path)
    source = KnowledgeSource(
        name="local-kb", source_type="path", url="../my-kb",
        mount="refs/knowledge/local-kb",
    )
    save_knowledge_source(tmp_path, source)

    config = load_knowledge_config(tmp_path)
    assert config is not None
    assert config.sources[0].source_type == "path"
    assert config.sources[0].url == "../my-kb"


# ---------- remove_knowledge_source ----------


def test_remove_knowledge_source_removes(tmp_path: Path) -> None:
    _create_project(tmp_path)
    source = KnowledgeSource(
        name="kb", source_type="git", url="https://x.git",
        mount="refs/knowledge/kb",
    )
    save_knowledge_source(tmp_path, source)

    assert remove_knowledge_source(tmp_path, "kb") is True
    config = load_knowledge_config(tmp_path)
    assert config is not None
    assert len(config.sources) == 0


def test_remove_knowledge_source_not_found(tmp_path: Path) -> None:
    _create_project(tmp_path, "\n[knowledge]\nsources = []\n")
    assert remove_knowledge_source(tmp_path, "nonexistent") is False


# ---------- sync_source ----------


def test_sync_source_path_exists(tmp_path: Path) -> None:
    kb_dir = _create_knowledge_source(tmp_path)
    project = tmp_path / "project"
    project.mkdir()

    source = KnowledgeSource(
        name="test-kb", source_type="path", url=str(kb_dir),
        mount="refs/knowledge/test-kb",
    )
    status = sync_source(project, source)
    assert status in ("linked", "exists")


def test_sync_source_path_not_found(tmp_path: Path) -> None:
    from simctl.core.exceptions import KnowledgeSourceError

    project = tmp_path / "project"
    project.mkdir()

    source = KnowledgeSource(
        name="missing", source_type="path", url="/nonexistent/path",
        mount="refs/knowledge/missing",
    )
    with pytest.raises(KnowledgeSourceError, match="not found"):
        sync_source(project, source)


def test_sync_source_git_clone(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()

    source = KnowledgeSource(
        name="git-kb", source_type="git",
        url="https://github.com/lab/kb.git",
        mount="refs/knowledge/git-kb",
    )

    with patch("simctl.core.knowledge_source.subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        status = sync_source(project, source)

    assert status == "cloned"
    mock_run.assert_called_once()
    call_args = mock_run.call_args[0][0]
    assert call_args[0] == "git"
    assert call_args[1] == "clone"


def test_sync_source_git_pull(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    mount = project / "refs" / "knowledge" / "git-kb"
    mount.mkdir(parents=True)
    (mount / ".git").mkdir()  # fake git dir

    source = KnowledgeSource(
        name="git-kb", source_type="git",
        url="https://github.com/lab/kb.git",
        mount="refs/knowledge/git-kb",
    )

    with patch("simctl.core.knowledge_source.subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        status = sync_source(project, source)

    assert status == "updated"
    call_args = mock_run.call_args[0][0]
    assert "pull" in call_args


# ---------- validate_source_structure ----------


def test_validate_source_structure_valid(tmp_path: Path) -> None:
    kb_dir = _create_knowledge_source(tmp_path)
    issues = validate_source_structure(kb_dir)
    assert issues == []


def test_validate_source_structure_missing_profiles(tmp_path: Path) -> None:
    kb_dir = tmp_path / "kb"
    kb_dir.mkdir()
    (kb_dir / "README.md").write_text("# KB\n")

    issues = validate_source_structure(kb_dir)
    assert any("profiles/" in i for i in issues)


def test_validate_source_structure_missing_readme(tmp_path: Path) -> None:
    kb_dir = tmp_path / "kb"
    kb_dir.mkdir()
    (kb_dir / "profiles").mkdir()

    issues = validate_source_structure(kb_dir)
    assert any("README.md" in i for i in issues)


def test_validate_source_structure_not_found(tmp_path: Path) -> None:
    issues = validate_source_structure(tmp_path / "nonexistent")
    assert len(issues) == 1
    assert "not found" in issues[0]


# ---------- discover_profiles ----------


def test_discover_profiles(tmp_path: Path) -> None:
    kb_dir = _create_knowledge_source(tmp_path)
    profiles = discover_profiles(kb_dir)
    assert profiles == ["advanced", "common"]


def test_discover_profiles_no_dir(tmp_path: Path) -> None:
    assert discover_profiles(tmp_path) == []


# ---------- render_imports ----------


def test_render_imports_with_profiles(tmp_path: Path) -> None:
    kb_dir = _create_knowledge_source(tmp_path, "kb")
    project = tmp_path / "project"
    project.mkdir()

    # Mount the kb at the expected location
    mount_dir = project / "refs" / "knowledge" / "kb"
    mount_dir.parent.mkdir(parents=True)
    import shutil
    shutil.copytree(kb_dir, mount_dir)

    config = KnowledgeConfig(
        sources=[
            KnowledgeSource(
                name="kb", source_type="path", url=str(kb_dir),
                mount="refs/knowledge/kb", profiles=["common"],
            ),
        ],
    )

    imports_path = render_imports(project, config)
    assert imports_path.is_file()
    content = imports_path.read_text()
    assert "@refs/knowledge/kb/profiles/common.md" in content
    assert "advanced" not in content


def test_render_imports_no_profiles_uses_claude_md(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    mount_dir = project / "refs" / "knowledge" / "kb"
    mount_dir.mkdir(parents=True)
    (mount_dir / "CLAUDE.md").write_text("# Knowledge\n")

    config = KnowledgeConfig(
        sources=[
            KnowledgeSource(
                name="kb", source_type="path", url=".",
                mount="refs/knowledge/kb", profiles=[],
            ),
        ],
    )

    imports_path = render_imports(project, config)
    content = imports_path.read_text()
    assert "@refs/knowledge/kb/CLAUDE.md" in content


def test_render_imports_missing_profile_adds_comment(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    mount_dir = project / "refs" / "knowledge" / "kb"
    mount_dir.mkdir(parents=True)
    (mount_dir / "profiles").mkdir()

    config = KnowledgeConfig(
        sources=[
            KnowledgeSource(
                name="kb", source_type="path", url=".",
                mount="refs/knowledge/kb", profiles=["nonexistent"],
            ),
        ],
    )

    imports_path = render_imports(project, config)
    content = imports_path.read_text()
    assert "<!-- profile nonexistent not found" in content
