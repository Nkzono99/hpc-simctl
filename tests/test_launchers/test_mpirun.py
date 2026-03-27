"""Tests for MpirunLauncher command generation."""

from __future__ import annotations

from simctl.launchers.mpirun import MpirunLauncher


class TestBuildLaunchCommand:
    """Tests for MpirunLauncher.build_launch_command."""

    def test_basic_command(self) -> None:
        """Basic mpirun command with -np."""
        launcher = MpirunLauncher(name="m", command="mpirun")
        cmd = launcher.build_launch_command(
            ["./solver", "--config", "input.toml"], ntasks=8
        )
        assert cmd == ["mpirun", "-np", "8", "./solver", "--config", "input.toml"]

    def test_custom_np_flag(self) -> None:
        """Custom np_flag is used instead of default."""
        launcher = MpirunLauncher(name="m", command="mpirun", np_flag="--np")
        cmd = launcher.build_launch_command(["./solver"], ntasks=4)
        assert cmd[:3] == ["mpirun", "--np", "4"]

    def test_extra_options_from_init(self) -> None:
        """Instance-level extra options are included."""
        launcher = MpirunLauncher(
            name="m",
            command="mpirun",
            extra_options=["--bind-to", "core"],
        )
        cmd = launcher.build_launch_command(["./solver"], ntasks=4)
        assert "--bind-to" in cmd
        assert "core" in cmd

    def test_extra_options_from_call(self) -> None:
        """Per-call extra options are included."""
        launcher = MpirunLauncher(name="m", command="mpirun")
        cmd = launcher.build_launch_command(
            ["./solver"], ntasks=4, extra_options={"map-by": "node"}
        )
        assert "--map-by" in cmd
        assert "node" in cmd

    def test_program_command_at_end(self) -> None:
        """Program command always comes last."""
        launcher = MpirunLauncher(name="m", command="mpirun")
        cmd = launcher.build_launch_command(["./solver", "arg1"], ntasks=2)
        assert cmd[-2:] == ["./solver", "arg1"]


class TestBuildExecLine:
    """Tests for MpirunLauncher.build_exec_line."""

    def test_use_slurm_ntasks(self) -> None:
        """When use_slurm_ntasks=True, ${SLURM_NTASKS} appears in exec line."""
        launcher = MpirunLauncher(name="m", command="mpirun", use_slurm_ntasks=True)
        line = launcher.build_exec_line(["./solver"], ntasks=4)
        assert "${SLURM_NTASKS}" in line
        assert "-np" in line
        assert "mpirun" in line

    def test_explicit_ntasks(self) -> None:
        """When use_slurm_ntasks=False, literal ntasks value appears."""
        launcher = MpirunLauncher(name="m", command="mpirun")
        line = launcher.build_exec_line(["./solver"], ntasks=16)
        assert "-np 16" in line
        assert "${SLURM_NTASKS}" not in line

    def test_custom_np_flag_in_exec_line(self) -> None:
        """Custom np_flag is used in exec line."""
        launcher = MpirunLauncher(name="m", command="mpirun", np_flag="--np")
        line = launcher.build_exec_line(["./solver"], ntasks=4)
        assert "--np 4" in line

    def test_exec_line_with_extra_options(self) -> None:
        """Extra options from init appear in exec line."""
        launcher = MpirunLauncher(
            name="m",
            command="mpirun",
            extra_options=["--bind-to", "core"],
        )
        line = launcher.build_exec_line(["./solver"], ntasks=2)
        assert "--bind-to" in line
        assert "core" in line
