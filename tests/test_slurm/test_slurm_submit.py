"""Tests for Slurm submission module."""

from __future__ import annotations

import pytest

from simctl.slurm.submit import sbatch


def test_sbatch_not_implemented() -> None:
    with pytest.raises(NotImplementedError):
        from pathlib import Path

        sbatch(Path("/nonexistent/job.sh"))
