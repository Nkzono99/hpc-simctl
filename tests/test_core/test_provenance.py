"""Tests for core provenance module."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from simctl.core.exceptions import ProvenanceError
from simctl.core.provenance import (
    ProvenanceInfo,
    collect_git_provenance,
    compute_executable_hash,
)


class TestCollectGitProvenance:
    """Tests for collect_git_provenance()."""

    def test_collect_from_real_repo(self, tmp_path: Path) -> None:
        """Test collecting provenance from a real git repo."""
        cmd = f"cd {tmp_path} && git init -q && git commit --allow-empty -m init -q"
        os.system(cmd)
        info = collect_git_provenance(tmp_path)
        assert len(info.git_commit) == 40  # Full SHA
        assert info.git_dirty is False
        assert info.source_repo == str(tmp_path.resolve())

    def test_dirty_repo(self, tmp_path: Path) -> None:
        """Test that dirty state is detected."""
        cmd = f"cd {tmp_path} && git init -q && git commit --allow-empty -m init -q"
        os.system(cmd)
        (tmp_path / "dirty.txt").write_text("uncommitted")
        os.system(f"cd {tmp_path} && git add dirty.txt")
        info = collect_git_provenance(tmp_path)
        assert info.git_dirty is True

    def test_nonexistent_path(self, tmp_path: Path) -> None:
        with pytest.raises(ProvenanceError, match="not a directory"):
            collect_git_provenance(tmp_path / "nonexistent")

    def test_not_a_git_repo(self, tmp_path: Path) -> None:
        with pytest.raises(ProvenanceError, match="Failed to get git commit"):
            collect_git_provenance(tmp_path)

    def test_to_dict(self) -> None:
        info = ProvenanceInfo(
            source_repo="/path/to/repo",
            git_commit="abc123",
            git_dirty=False,
            executable="/path/to/exe",
            exe_hash="sha256:deadbeef",
        )
        d = info.to_dict()
        assert d["source_repo"] == "/path/to/repo"
        assert d["git_commit"] == "abc123"
        assert d["exe_hash"] == "sha256:deadbeef"


class TestComputeExecutableHash:
    """Tests for compute_executable_hash()."""

    def test_hash_file(self, tmp_path: Path) -> None:
        exe = tmp_path / "solver"
        exe.write_bytes(b"binary content here")
        result = compute_executable_hash(exe)
        assert result.startswith("sha256:")
        assert len(result) == len("sha256:") + 64

    def test_consistent_hash(self, tmp_path: Path) -> None:
        exe = tmp_path / "solver"
        exe.write_bytes(b"same content")
        h1 = compute_executable_hash(exe)
        h2 = compute_executable_hash(exe)
        assert h1 == h2

    def test_different_content_different_hash(self, tmp_path: Path) -> None:
        exe1 = tmp_path / "solver1"
        exe1.write_bytes(b"content A")
        exe2 = tmp_path / "solver2"
        exe2.write_bytes(b"content B")
        assert compute_executable_hash(exe1) != compute_executable_hash(exe2)

    def test_nonexistent_file(self, tmp_path: Path) -> None:
        with pytest.raises(ProvenanceError, match="Executable not found"):
            compute_executable_hash(tmp_path / "nonexistent")
