"""Tests for MpiexecLauncher command generation."""

from __future__ import annotations

from runops.launchers.mpiexec import MpiexecLauncher


class TestBuildLaunchCommand:
    """Tests for MpiexecLauncher.build_launch_command."""

    def test_basic_command(self) -> None:
        """Basic mpiexec command with -n."""
        launcher = MpiexecLauncher(name="e", command="mpiexec")
        cmd = launcher.build_launch_command(
            ["./solver", "--config", "input.toml"], ntasks=8
        )
        assert cmd == ["mpiexec", "-n", "8", "./solver", "--config", "input.toml"]

    def test_custom_n_flag(self) -> None:
        """Custom n_flag is used instead of default."""
        launcher = MpiexecLauncher(name="e", command="mpiexec", n_flag="--nproc")
        cmd = launcher.build_launch_command(["./solver"], ntasks=4)
        assert cmd[:3] == ["mpiexec", "--nproc", "4"]

    def test_extra_options_from_init(self) -> None:
        """Instance-level extra options are included."""
        launcher = MpiexecLauncher(
            name="e",
            command="mpiexec",
            extra_options=["--verbose"],
        )
        cmd = launcher.build_launch_command(["./solver"], ntasks=4)
        assert "--verbose" in cmd

    def test_extra_options_from_call(self) -> None:
        """Per-call extra options are included."""
        launcher = MpiexecLauncher(name="e", command="mpiexec")
        cmd = launcher.build_launch_command(
            ["./solver"], ntasks=4, extra_options={"hosts": "node1,node2"}
        )
        assert "--hosts" in cmd
        assert "node1,node2" in cmd

    def test_program_command_at_end(self) -> None:
        """Program command always comes last."""
        launcher = MpiexecLauncher(name="e", command="mpiexec")
        cmd = launcher.build_launch_command(["./solver", "arg1"], ntasks=2)
        assert cmd[-2:] == ["./solver", "arg1"]


class TestBuildExecLine:
    """Tests for MpiexecLauncher.build_exec_line."""

    def test_use_slurm_ntasks(self) -> None:
        """When use_slurm_ntasks=True, ${SLURM_NTASKS} appears in exec line."""
        launcher = MpiexecLauncher(name="e", command="mpiexec", use_slurm_ntasks=True)
        line = launcher.build_exec_line(["./solver"], ntasks=4)
        assert "${SLURM_NTASKS}" in line
        assert "-n" in line
        assert "mpiexec" in line

    def test_explicit_ntasks(self) -> None:
        """When use_slurm_ntasks=False, literal ntasks value appears."""
        launcher = MpiexecLauncher(name="e", command="mpiexec")
        line = launcher.build_exec_line(["./solver"], ntasks=16)
        assert "-n 16" in line
        assert "${SLURM_NTASKS}" not in line

    def test_custom_n_flag_in_exec_line(self) -> None:
        """Custom n_flag is used in exec line."""
        launcher = MpiexecLauncher(name="e", command="mpiexec", n_flag="--nproc")
        line = launcher.build_exec_line(["./solver"], ntasks=4)
        assert "--nproc 4" in line

    def test_exec_line_with_extra_options(self) -> None:
        """Extra options from init appear in exec line."""
        launcher = MpiexecLauncher(
            name="e",
            command="mpiexec",
            extra_options=["--verbose"],
        )
        line = launcher.build_exec_line(["./solver"], ntasks=2)
        assert "--verbose" in line
