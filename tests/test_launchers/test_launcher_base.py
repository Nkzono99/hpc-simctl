"""Tests for launcher base class and concrete stubs."""

from __future__ import annotations

from simctl.launchers.srun import SrunLauncher


def test_srun_launcher_kind() -> None:
    launcher = SrunLauncher()
    assert launcher.kind == "srun"
