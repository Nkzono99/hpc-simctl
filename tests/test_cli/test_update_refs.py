"""Tests for the ``runops update-refs`` CLI command and helpers."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from typer.testing import CliRunner

from runops.cli.main import app
from runops.cli.update_refs import (
    _collect_knowledge_files,
    _detect_remote_ref,
    _generate_knowledge_md,
    _pull_shallow,
    _read_existing_changelog,
)

runner = CliRunner()


def test_collect_knowledge_files_deduplicates_matches(tmp_path: Path) -> None:
    repo = tmp_path / "refs" / "emses-docs"
    (repo / "docs").mkdir(parents=True)
    (repo / "README.md").write_text("# README\n", encoding="utf-8")
    (repo / "docs" / "guide.md").write_text("# Guide\n", encoding="utf-8")

    files = _collect_knowledge_files(
        tmp_path / "refs",
        "emses-docs",
        ["README.md", "docs/**/*.md", "README.md"],
    )

    assert files == ["README.md", "docs/guide.md"]


def test_read_existing_changelog_extracts_bullet_entries(tmp_path: Path) -> None:
    knowledge_file = tmp_path / "emses.md"
    knowledge_file.write_text(
        "# Knowledge Index: emses\n\n"
        "## Change Log\n\n"
        "- first entry\n"
        "- second entry\n\n"
        "## Other Section\n"
        "- ignored\n",
        encoding="utf-8",
    )

    assert _read_existing_changelog(knowledge_file) == [
        "- first entry",
        "- second entry",
    ]


def test_generate_knowledge_md_includes_files_commits_and_changes() -> None:
    content = _generate_knowledge_md(
        "emses",
        {"emses-docs": ["README.md", "docs/guide.md"]},
        {"emses-docs": "bbbbbbbb12345678"},
        {"emses-docs": ("aaaaaaaa12345678", "bbbbbbbb12345678")},
        ["- older entry"],
    )

    assert "# Knowledge Index: emses" in content
    assert "**Commit**: `bbbbbbbb`" in content
    assert "- `refs/emses-docs/README.md`" in content
    assert "## Change Log" in content
    assert "emses-docs (`aaaaaaaa` -> `bbbbbbbb`)" in content
    assert "- older entry" in content


def test_detect_remote_ref_falls_back_to_origin_main_then_fetch_head() -> None:
    missing = SimpleNamespace(returncode=1, stdout="", stderr="missing")
    found = SimpleNamespace(returncode=0, stdout="ok\n", stderr="")

    with patch(
        "runops.cli.update_refs.subprocess.run",
        side_effect=[missing, found],
    ):
        assert _detect_remote_ref(Path("/tmp/repo")) == "origin/main"

    with patch(
        "runops.cli.update_refs.subprocess.run",
        side_effect=[missing, missing, missing],
    ):
        assert _detect_remote_ref(Path("/tmp/repo")) == "FETCH_HEAD"


def test_pull_shallow_handles_fetch_failure() -> None:
    failed_fetch = SimpleNamespace(returncode=1, stdout="", stderr="network down")

    with (
        patch("runops.cli.update_refs._get_commit_hash", return_value="aaaaaaaa"),
        patch("runops.cli.update_refs.subprocess.run", return_value=failed_fetch),
    ):
        old_hash, new_hash, message = _pull_shallow(Path("/tmp/repo"))

    assert (old_hash, new_hash) == ("aaaaaaaa", "aaaaaaaa")
    assert "git fetch failed" in message


def test_pull_shallow_reports_updated_repo() -> None:
    ok = SimpleNamespace(returncode=0, stdout="", stderr="")

    with (
        patch(
            "runops.cli.update_refs._get_commit_hash",
            side_effect=["aaaaaaaa", "bbbbbbbb"],
        ),
        patch("runops.cli.update_refs._detect_remote_ref", return_value="origin/main"),
        patch("runops.cli.update_refs.subprocess.run", side_effect=[ok, ok]),
    ):
        old_hash, new_hash, message = _pull_shallow(Path("/tmp/repo"))

    assert (old_hash, new_hash, message) == ("aaaaaaaa", "bbbbbbbb", "updated")


def test_update_refs_dry_run_reports_repos_and_indexes(tmp_path: Path) -> None:
    class FakeAdapter:
        @staticmethod
        def doc_repos() -> list[tuple[str, str]]:
            return [("https://example.invalid/emses-docs.git", "emses-docs")]

        @staticmethod
        def knowledge_sources() -> dict[str, list[str]]:
            return {}

    (tmp_path / "refs" / "emses-docs").mkdir(parents=True)

    with (
        patch(
            "runops.cli.update_refs._get_project_simulators",
            return_value=(tmp_path, {"emses": "emses"}),
        ),
        patch("runops.cli.update_refs._get_adapter_class", return_value=FakeAdapter),
    ):
        result = runner.invoke(app, ["update-refs", "--dry-run"])

    assert result.exit_code == 0, result.output
    assert "Would update the following repos:" in result.output
    assert "refs/emses-docs/ (exists)" in result.output
    assert ".runops/knowledge/emses.md" in result.output


def test_update_refs_generates_knowledge_indexes(tmp_path: Path) -> None:
    class FakeAdapter:
        @staticmethod
        def doc_repos() -> list[tuple[str, str]]:
            return [("https://example.invalid/emses-docs.git", "emses-docs")]

        @staticmethod
        def knowledge_sources() -> dict[str, list[str]]:
            return {"emses-docs": ["README.md", "docs/**/*.md"]}

    repo = tmp_path / "refs" / "emses-docs"
    (repo / "docs").mkdir(parents=True)
    (repo / "README.md").write_text("# README\n", encoding="utf-8")
    (repo / "docs" / "guide.md").write_text("# Guide\n", encoding="utf-8")

    with (
        patch(
            "runops.cli.update_refs._get_project_simulators",
            return_value=(tmp_path, {"emses": "emses"}),
        ),
        patch("runops.cli.update_refs._get_adapter_class", return_value=FakeAdapter),
        patch(
            "runops.cli.update_refs._pull_shallow",
            return_value=("aaaaaaaa", "bbbbbbbb", "updated"),
        ),
    ):
        result = runner.invoke(app, ["update-refs"])

    assert result.exit_code == 0, result.output
    assert "refs/emses-docs/ — updated (aaaaaaaa -> bbbbbbbb)" in result.output
    assert ".runops/knowledge/emses.md — 2 files indexed" in result.output
    assert "Done." in result.output

    knowledge_file = tmp_path / ".runops" / "knowledge" / "emses.md"
    content = knowledge_file.read_text(encoding="utf-8")
    assert "refs/emses-docs/README.md" in content
    assert "refs/emses-docs/docs/guide.md" in content
    assert "emses-docs (`aaaaaaaa` -> `bbbbbbbb`)" in content


def test_update_refs_warns_when_adapter_is_missing(tmp_path: Path) -> None:
    with (
        patch(
            "runops.cli.update_refs._get_project_simulators",
            return_value=(tmp_path, {"emses": "emses"}),
        ),
        patch("runops.cli.update_refs._get_adapter_class", return_value=None),
    ):
        result = runner.invoke(app, ["update-refs"])

    assert result.exit_code == 0, result.output
    assert "Warning: no adapter 'emses' for 'emses', skipping." in result.output
    assert "No reference repos configured for the selected simulators." in result.output
