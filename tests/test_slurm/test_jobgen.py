"""Tests for job script generation."""

from __future__ import annotations

from pathlib import Path

import pytest

from simctl.jobgen.generator import (
    JobScriptError,
    generate_job_script,
    write_job_script,
)


@pytest.fixture()
def run_dir(tmp_path: Path) -> Path:
    """Create a minimal run directory with work/ subdirectory."""
    rd = tmp_path / "R20260327-0001"
    rd.mkdir()
    (rd / "work").mkdir()
    return rd


@pytest.fixture()
def job_config() -> dict[str, object]:
    """Return a valid minimal job config."""
    return {
        "partition": "debug",
        "nodes": 1,
        "ntasks": 4,
        "walltime": "00:10:00",
    }


# ---------------------------------------------------------------------------
# generate_job_script
# ---------------------------------------------------------------------------


class TestGenerateJobScript:
    """Tests for generate_job_script."""

    def test_basic_generation(
        self, run_dir: Path, job_config: dict[str, object]
    ) -> None:
        path = generate_job_script(run_dir, job_config, "srun ./solver input.toml")
        assert path.exists()
        assert path.name == "job.sh"
        assert path.parent.name == "submit"

        content = path.read_text()
        assert content.startswith("#!/bin/bash\n")
        assert "#SBATCH -p debug" in content
        assert "#SBATCH --nodes=1" in content
        assert "#SBATCH --ntasks=4" in content
        assert "#SBATCH -t 00:10:00" in content
        assert "exec srun ./solver input.toml" in content

    def test_job_name_from_run_id(
        self, run_dir: Path, job_config: dict[str, object]
    ) -> None:
        path = generate_job_script(
            run_dir, job_config, "srun ./solver", run_id="R20260327-0001"
        )
        content = path.read_text()
        assert "#SBATCH -J R20260327-0001" in content

    def test_custom_job_name(
        self, run_dir: Path, job_config: dict[str, object]
    ) -> None:
        job_config["job_name"] = "my-custom-name"
        path = generate_job_script(run_dir, job_config, "srun ./solver")
        content = path.read_text()
        assert "#SBATCH -J my-custom-name" in content

    def test_default_job_name(
        self, run_dir: Path, job_config: dict[str, object]
    ) -> None:
        path = generate_job_script(run_dir, job_config, "srun ./solver")
        content = path.read_text()
        assert "#SBATCH -J simctl-job" in content

    def test_output_and_error_paths(
        self, run_dir: Path, job_config: dict[str, object]
    ) -> None:
        path = generate_job_script(run_dir, job_config, "srun ./solver")
        content = path.read_text()
        work = str(run_dir / "work")
        assert f"#SBATCH --output={work}" in content
        assert f"#SBATCH --error={work}" in content

    def test_extra_sbatch_directives(
        self, run_dir: Path, job_config: dict[str, object]
    ) -> None:
        path = generate_job_script(
            run_dir,
            job_config,
            "srun ./solver",
            extra_sbatch=["--mem=8G", "--exclusive"],
        )
        content = path.read_text()
        assert "#SBATCH --mem=8G" in content
        assert "#SBATCH --exclusive" in content

    def test_module_loads(self, run_dir: Path, job_config: dict[str, object]) -> None:
        path = generate_job_script(
            run_dir,
            job_config,
            "srun ./solver",
            modules=["gcc/12.0", "openmpi/4.1"],
        )
        content = path.read_text()
        assert "module load gcc/12.0" in content
        assert "module load openmpi/4.1" in content

    def test_extra_env_vars(self, run_dir: Path, job_config: dict[str, object]) -> None:
        path = generate_job_script(
            run_dir,
            job_config,
            "srun ./solver",
            extra_env={"OMP_NUM_THREADS": "4"},
        )
        content = path.read_text()
        assert "export OMP_NUM_THREADS='4'" in content

    def test_cd_to_work_dir(self, run_dir: Path, job_config: dict[str, object]) -> None:
        path = generate_job_script(run_dir, job_config, "srun ./solver")
        content = path.read_text()
        assert f"cd {run_dir / 'work'}" in content

    def test_set_euo_pipefail(
        self, run_dir: Path, job_config: dict[str, object]
    ) -> None:
        path = generate_job_script(run_dir, job_config, "srun ./solver")
        content = path.read_text()
        assert "set -euo pipefail" in content

    def test_executable_bit(self, run_dir: Path, job_config: dict[str, object]) -> None:
        path = generate_job_script(run_dir, job_config, "srun ./solver")
        assert path.stat().st_mode & 0o100  # owner execute bit

    def test_missing_walltime_raises(self, run_dir: Path) -> None:
        with pytest.raises(JobScriptError, match="walltime"):
            generate_job_script(
                run_dir,
                {"partition": "debug", "ntasks": 4},
                "srun ./solver",
            )

    def test_no_partition_omits_directive(self, run_dir: Path) -> None:
        """Partition is optional (can be set at submit time with -qn)."""
        path = generate_job_script(
            run_dir,
            {"walltime": "01:00:00", "ntasks": 4},
            "srun ./solver",
        )
        content = path.read_text()
        assert "#SBATCH -p" not in content

    def test_creates_submit_dir(
        self, tmp_path: Path, job_config: dict[str, object]
    ) -> None:
        """submit/ directory should be created even if it doesn't exist."""
        rd = tmp_path / "new_run"
        rd.mkdir()
        path = generate_job_script(rd, job_config, "srun ./solver")
        assert path.parent.is_dir()
        assert path.parent.name == "submit"

    def test_setup_commands(
        self, run_dir: Path, job_config: dict[str, object]
    ) -> None:
        """Setup commands appear before the exec line."""
        path = generate_job_script(
            run_dir,
            job_config,
            "srun ./solver",
            setup_commands=["cp input/* .", "preinp"],
        )
        content = path.read_text()
        assert "cp input/* ." in content
        assert "preinp" in content
        # Setup should come before exec
        setup_idx = content.index("cp input/*")
        exec_idx = content.index("srun ./solver")
        assert setup_idx < exec_idx

    def test_post_commands(
        self, run_dir: Path, job_config: dict[str, object]
    ) -> None:
        """Post commands appear after the main command, without exec prefix."""
        path = generate_job_script(
            run_dir,
            job_config,
            "srun ./solver",
            post_commands=["date", "echo done"],
        )
        content = path.read_text()
        assert "date" in content
        assert "echo done" in content
        # Main command should NOT have exec prefix when post_commands exist
        assert "exec srun" not in content

    def test_optional_nodes_ntasks(self, run_dir: Path) -> None:
        """nodes and ntasks are optional and omitted from SBATCH if absent."""
        config = {"partition": "debug", "walltime": "01:00:00"}
        path = generate_job_script(run_dir, config, "srun ./solver")
        content = path.read_text()
        assert "#SBATCH -p debug" in content
        assert "--nodes" not in content
        assert "--ntasks" not in content

    def test_rsc_resource_style(self, run_dir: Path) -> None:
        """resource_style='rsc' emits --rsc instead of --ntasks."""
        config = {"partition": "gr10451a", "walltime": "120:00:00", "ntasks": 32}
        path = generate_job_script(
            run_dir,
            config,
            "srun ./mpiemses3D plasma.inp",
            resource_style="rsc",
            stdout_format="stdout.%J.log",
            stderr_format="stderr.%J.log",
        )
        content = path.read_text()
        assert "#SBATCH --rsc p=32:t=1:c=1" in content
        assert "#SBATCH --ntasks" not in content
        assert "#SBATCH -o stdout.%J.log" in content
        assert "#SBATCH -e stderr.%J.log" in content


# ---------------------------------------------------------------------------
# write_job_script
# ---------------------------------------------------------------------------


class TestWriteJobScript:
    """Tests for write_job_script."""

    def test_writes_content(self, run_dir: Path) -> None:
        content = "#!/bin/bash\necho hello\n"
        path = write_job_script(run_dir, content)
        assert path.read_text() == content

    def test_creates_submit_dir(self, tmp_path: Path) -> None:
        rd = tmp_path / "R0001"
        rd.mkdir()
        path = write_job_script(rd, "#!/bin/bash\n")
        assert path.exists()
        assert path.parent.name == "submit"

    def test_overwrites_existing(self, run_dir: Path) -> None:
        write_job_script(run_dir, "old content")
        path = write_job_script(run_dir, "new content")
        assert path.read_text() == "new content"
