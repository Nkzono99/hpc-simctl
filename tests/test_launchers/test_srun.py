"""Tests for SrunLauncher command generation."""

from __future__ import annotations

from simctl.launchers.srun import SrunLauncher


class TestBuildLaunchCommand:
    """Tests for SrunLauncher.build_launch_command."""

    def test_basic_command(self) -> None:
        """Basic srun command with ntasks."""
        launcher = SrunLauncher(name="s", command="srun")
        cmd = launcher.build_launch_command(
            ["./solver", "--config", "input.toml"], ntasks=4
        )
        assert cmd == ["srun", "--ntasks=4", "./solver", "--config", "input.toml"]

    def test_use_slurm_ntasks_omits_ntasks_flag(self) -> None:
        """When use_slurm_ntasks=True, --ntasks is omitted."""
        launcher = SrunLauncher(name="s", command="srun", use_slurm_ntasks=True)
        cmd = launcher.build_launch_command(["./solver"], ntasks=4)
        assert cmd == ["srun", "./solver"]
        assert "--ntasks=4" not in cmd

    def test_extra_options_from_init(self) -> None:
        """Extra options passed at init are included."""
        launcher = SrunLauncher(
            name="s",
            command="srun",
            extra_options=["--mpi=pmix", "--export=ALL"],
        )
        cmd = launcher.build_launch_command(["./solver"], ntasks=2)
        assert cmd == [
            "srun",
            "--ntasks=2",
            "--mpi=pmix",
            "--export=ALL",
            "./solver",
        ]

    def test_extra_options_from_call(self) -> None:
        """Extra options passed at call time are included."""
        launcher = SrunLauncher(name="s", command="srun")
        cmd = launcher.build_launch_command(
            ["./solver"],
            ntasks=4,
            extra_options={"cpus-per-task": 2, "exclusive": True},
        )
        assert "--cpus-per-task=2" in cmd
        assert "--exclusive" in cmd

    def test_false_option_excluded(self) -> None:
        """Boolean False options are excluded."""
        launcher = SrunLauncher(name="s", command="srun")
        cmd = launcher.build_launch_command(
            ["./solver"], ntasks=4, extra_options={"exclusive": False}
        )
        assert "--exclusive" not in cmd

    def test_program_command_at_end(self) -> None:
        """Program command always comes after all options."""
        launcher = SrunLauncher(
            name="s",
            command="srun",
            extra_options=["--mpi=pmix"],
        )
        cmd = launcher.build_launch_command(
            ["./solver", "arg1"], ntasks=4, extra_options={"verbose": True}
        )
        # Program command should be last.
        assert cmd[-2:] == ["./solver", "arg1"]


class TestBuildExecLine:
    """Tests for SrunLauncher.build_exec_line."""

    def test_basic_exec_line(self) -> None:
        """Basic exec line with ntasks."""
        launcher = SrunLauncher(name="s", command="srun")
        line = launcher.build_exec_line(["./solver", "input.toml"], ntasks=4)
        assert "srun" in line
        assert "--ntasks=4" in line
        assert "./solver" in line
        assert "input.toml" in line

    def test_use_slurm_ntasks_no_flag(self) -> None:
        """When use_slurm_ntasks=True, no --ntasks in exec line."""
        launcher = SrunLauncher(name="s", command="srun", use_slurm_ntasks=True)
        line = launcher.build_exec_line(["./solver"], ntasks=4)
        assert "--ntasks" not in line
        assert "srun" in line
        assert "./solver" in line

    def test_exec_line_with_extra_options(self) -> None:
        """Extra options appear in exec line."""
        launcher = SrunLauncher(name="s", command="srun", extra_options=["--mpi=pmix"])
        line = launcher.build_exec_line(["./solver"], ntasks=2)
        assert "--mpi=pmix" in line
