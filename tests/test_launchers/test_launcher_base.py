"""Tests for launcher base class, from_config, and load_launchers."""

from __future__ import annotations

from typing import Any

import pytest

from simctl.launchers.base import Launcher, LauncherConfigError, load_launchers
from simctl.launchers.mpiexec import MpiexecLauncher
from simctl.launchers.mpirun import MpirunLauncher
from simctl.launchers.srun import SrunLauncher

# ---------------------------------------------------------------------------
# Contract tests: all concrete launchers satisfy the ABC interface
# ---------------------------------------------------------------------------


def _make_all_launchers() -> list[Launcher]:
    """Create one instance of each concrete launcher for contract testing."""
    return [
        SrunLauncher(name="test_srun", command="srun"),
        MpirunLauncher(name="test_mpirun", command="mpirun"),
        MpiexecLauncher(name="test_mpiexec", command="mpiexec"),
    ]


@pytest.mark.parametrize("launcher", _make_all_launchers(), ids=lambda lnch: lnch.kind)
def test_contract_kind_is_string(launcher: Launcher) -> None:
    """All launchers must return a non-empty string kind."""
    assert isinstance(launcher.kind, str)
    assert len(launcher.kind) > 0


@pytest.mark.parametrize("launcher", _make_all_launchers(), ids=lambda lnch: lnch.kind)
def test_contract_name_is_string(launcher: Launcher) -> None:
    """All launchers must return a non-empty string name."""
    assert isinstance(launcher.name, str)
    assert len(launcher.name) > 0


@pytest.mark.parametrize("launcher", _make_all_launchers(), ids=lambda lnch: lnch.kind)
def test_contract_build_launch_command_returns_list(launcher: Launcher) -> None:
    """build_launch_command must return a list of strings."""
    cmd = launcher.build_launch_command(["./solver"], ntasks=4)
    assert isinstance(cmd, list)
    assert all(isinstance(s, str) for s in cmd)


@pytest.mark.parametrize("launcher", _make_all_launchers(), ids=lambda lnch: lnch.kind)
def test_contract_build_exec_line_returns_string(launcher: Launcher) -> None:
    """build_exec_line must return a non-empty string."""
    line = launcher.build_exec_line(["./solver"], ntasks=4)
    assert isinstance(line, str)
    assert len(line) > 0


@pytest.mark.parametrize("launcher", _make_all_launchers(), ids=lambda lnch: lnch.kind)
def test_contract_build_env_vars_returns_dict(launcher: Launcher) -> None:
    """build_env_vars must return a dict[str, str]."""
    env = launcher.build_env_vars()
    assert isinstance(env, dict)


@pytest.mark.parametrize("launcher", _make_all_launchers(), ids=lambda lnch: lnch.kind)
def test_contract_empty_program_command_raises(launcher: Launcher) -> None:
    """All launchers must raise on empty program_command."""
    with pytest.raises(LauncherConfigError):
        launcher.build_launch_command([], ntasks=4)
    with pytest.raises(LauncherConfigError):
        launcher.build_exec_line([], ntasks=4)


# ---------------------------------------------------------------------------
# build_env_vars
# ---------------------------------------------------------------------------


def test_build_env_vars_omp_num_threads() -> None:
    """build_env_vars sets OMP_NUM_THREADS from cpus_per_task."""
    launcher = SrunLauncher(name="s", command="srun")
    env = launcher.build_env_vars({"cpus_per_task": 8})
    assert env == {"OMP_NUM_THREADS": "8"}


def test_build_env_vars_no_config() -> None:
    """build_env_vars with no config returns empty dict."""
    launcher = SrunLauncher(name="s", command="srun")
    assert launcher.build_env_vars() == {}


# ---------------------------------------------------------------------------
# from_config
# ---------------------------------------------------------------------------


def test_from_config_srun() -> None:
    """from_config creates SrunLauncher for kind=srun."""
    launcher = Launcher.from_config(
        "my_srun", {"kind": "srun", "command": "srun", "use_slurm_ntasks": True}
    )
    assert isinstance(launcher, SrunLauncher)
    assert launcher.name == "my_srun"
    assert launcher.kind == "srun"
    assert launcher.use_slurm_ntasks is True


def test_from_config_mpirun() -> None:
    """from_config creates MpirunLauncher with custom np_flag."""
    launcher = Launcher.from_config(
        "openmpi",
        {"kind": "mpirun", "command": "mpirun", "np_flag": "--np"},
    )
    assert isinstance(launcher, MpirunLauncher)
    assert launcher.np_flag == "--np"


def test_from_config_mpiexec() -> None:
    """from_config creates MpiexecLauncher with custom n_flag."""
    launcher = Launcher.from_config(
        "exec",
        {"kind": "mpiexec", "command": "mpiexec", "n_flag": "--nproc"},
    )
    assert isinstance(launcher, MpiexecLauncher)
    assert launcher.n_flag == "--nproc"


def test_from_config_missing_kind() -> None:
    """from_config raises on missing kind."""
    with pytest.raises(LauncherConfigError, match="missing required field 'kind'"):
        Launcher.from_config("bad", {"command": "srun"})


def test_from_config_missing_command() -> None:
    """from_config raises on missing command."""
    with pytest.raises(LauncherConfigError, match="missing required field 'command'"):
        Launcher.from_config("bad", {"kind": "srun"})


def test_from_config_unknown_kind() -> None:
    """from_config raises on unknown kind."""
    with pytest.raises(LauncherConfigError, match="Unknown launcher kind"):
        Launcher.from_config("bad", {"kind": "flux", "command": "flux"})


# ---------------------------------------------------------------------------
# load_launchers
# ---------------------------------------------------------------------------

_SAMPLE_LAUNCHERS_TOML: dict[str, Any] = {
    "slurm_srun": {
        "kind": "srun",
        "command": "srun",
        "use_slurm_ntasks": True,
    },
    "openmpi": {
        "kind": "mpirun",
        "command": "mpirun",
        "np_flag": "-np",
        "use_slurm_ntasks": True,
    },
    "mpiexec": {
        "kind": "mpiexec",
        "command": "mpiexec",
        "n_flag": "-n",
        "use_slurm_ntasks": True,
    },
}


def test_load_launchers_all_profiles() -> None:
    """load_launchers creates all three launcher types."""
    launchers = load_launchers(_SAMPLE_LAUNCHERS_TOML)
    assert len(launchers) == 3
    assert isinstance(launchers["slurm_srun"], SrunLauncher)
    assert isinstance(launchers["openmpi"], MpirunLauncher)
    assert isinstance(launchers["mpiexec"], MpiexecLauncher)


def test_load_launchers_invalid_profile_type() -> None:
    """load_launchers raises on non-dict profile."""
    with pytest.raises(LauncherConfigError, match="must be a table"):
        load_launchers({"bad": "not a dict"})  # type: ignore[dict-item]
