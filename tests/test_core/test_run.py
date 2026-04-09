"""Tests for core run module."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from runops.core.exceptions import DuplicateRunIdError, SimctlError
from runops.core.run import (
    create_run,
    create_run_directory,
    generate_run_id,
    next_run_id,
)


class TestGenerateRunId:
    """Tests for generate_run_id()."""

    def test_basic_format(self) -> None:
        assert generate_run_id("20260327", 1) == "R20260327-0001"

    def test_large_sequence(self) -> None:
        assert generate_run_id("20260327", 9999) == "R20260327-9999"

    def test_zero_padded(self) -> None:
        assert generate_run_id("20260101", 42) == "R20260101-0042"

    def test_invalid_date(self) -> None:
        with pytest.raises(SimctlError, match="Invalid date string"):
            generate_run_id("2026033", 1)

    def test_invalid_sequence_zero(self) -> None:
        with pytest.raises(SimctlError, match="Invalid sequence"):
            generate_run_id("20260327", 0)

    def test_invalid_sequence_overflow(self) -> None:
        with pytest.raises(SimctlError, match="Invalid sequence"):
            generate_run_id("20260327", 10000)


class TestNextRunId:
    """Tests for next_run_id()."""

    def test_first_run(self) -> None:
        result = next_run_id(set(), date(2026, 3, 27))
        assert result == "R20260327-0001"

    def test_increment_existing(self) -> None:
        existing = {"R20260327-0001", "R20260327-0002"}
        result = next_run_id(existing, date(2026, 3, 27))
        assert result == "R20260327-0003"

    def test_different_date(self) -> None:
        existing = {"R20260327-0005"}
        result = next_run_id(existing, date(2026, 3, 28))
        assert result == "R20260328-0001"

    def test_mixed_dates(self) -> None:
        existing = {"R20260327-0001", "R20260328-0003"}
        result = next_run_id(existing, date(2026, 3, 28))
        assert result == "R20260328-0004"

    def test_overflow(self) -> None:
        existing = {"R20260327-9999"}
        with pytest.raises(SimctlError, match="overflow"):
            next_run_id(existing, date(2026, 3, 27))


class TestCreateRunDirectory:
    """Tests for create_run_directory()."""

    def test_creates_all_subdirs(self, tmp_path: Path) -> None:
        run_dir = create_run_directory(tmp_path, "R20260327-0001")
        assert run_dir.is_dir()
        for subdir in ("input", "submit", "work", "analysis", "status"):
            assert (run_dir / subdir).is_dir()

    def test_duplicate_raises(self, tmp_path: Path) -> None:
        create_run_directory(tmp_path, "R20260327-0001")
        with pytest.raises(DuplicateRunIdError):
            create_run_directory(tmp_path, "R20260327-0001")

    def test_returns_absolute_path(self, tmp_path: Path) -> None:
        run_dir = create_run_directory(tmp_path, "R20260327-0001")
        assert run_dir.is_absolute()


class TestCreateRun:
    """Tests for create_run()."""

    def test_creates_run_with_info(self, tmp_path: Path) -> None:
        info = create_run(
            tmp_path,
            set(),
            display_name="test_run",
            params={"nx": 64},
            target_date=date(2026, 3, 27),
        )
        assert info.run_id == "R20260327-0001"
        assert info.run_dir.is_dir()
        assert info.display_name == "test_run"
        assert info.params == {"nx": 64}
        assert info.created_at != ""

    def test_auto_increment(self, tmp_path: Path) -> None:
        info1 = create_run(tmp_path, set(), target_date=date(2026, 3, 27))
        info2 = create_run(tmp_path, {info1.run_id}, target_date=date(2026, 3, 27))
        assert info1.run_id == "R20260327-0001"
        assert info2.run_id == "R20260327-0002"
