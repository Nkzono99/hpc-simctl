"""Common test fixtures for runops tests."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest


@pytest.fixture()
def tmp_project(tmp_path: Path) -> Path:
    """Create a minimal runops project directory structure.

    Returns:
        Path to the temporary project root.
    """
    (tmp_path / "runops.toml").write_text('[project]\nname = "test-project"\n')
    (tmp_path / "cases").mkdir()
    (tmp_path / "runs").mkdir()
    return tmp_path


@pytest.fixture()
def sample_case_data() -> dict[str, Any]:
    """Return sample case.toml data as a dictionary."""
    return {
        "case": {
            "name": "test_case",
            "simulator": "test_sim",
            "launcher": "slurm_srun",
            "description": "A test case",
        },
        "job": {
            "partition": "debug",
            "nodes": 1,
            "ntasks": 4,
            "walltime": "00:10:00",
        },
        "params": {
            "nx": 64,
            "ny": 64,
            "dt": 1.0e-6,
        },
    }


@pytest.fixture()
def sample_manifest_data() -> dict[str, Any]:
    """Return sample manifest.toml data as a dictionary."""
    return {
        "run": {
            "id": "R20260327-0001",
            "display_name": "test_run",
            "status": "created",
            "created_at": "2026-03-27T13:00:00+09:00",
        },
        "origin": {
            "case": "test_case",
            "survey": "",
            "parent_run": "",
        },
        "simulator": {
            "name": "test_sim",
            "adapter": "test_adapter",
        },
        "job": {
            "scheduler": "slurm",
            "job_id": "",
            "partition": "debug",
            "nodes": 1,
            "ntasks": 4,
            "walltime": "00:10:00",
        },
    }
