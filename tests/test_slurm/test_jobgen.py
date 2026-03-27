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
        assert "#SBATCH --partition=debug" in content
        assert "#SBATCH --nodes=1" in content
        assert "#SBATCH --ntasks=4" in content
        assert "#SBATCH --time=00:10:00" in content
        assert "exec srun ./solver input.toml" in content

    def test_job_name_from_run_id(
        self, run_dir: Path, job_config: dict[str, object]
    ) -> None:
        path = generate_job_script(
            run_dir, job_config, "srun ./solver", run_id="R20260327-0001"
        )
        content = path.read_text()
        assert "#SBATCH --job-name=R20260327-0001" in content

    def test_custom_job_name(
        self, run_dir: Path, job_config: dict[str, object]
    ) -> None:
        job_config["job_name"] = "my-custom-name"
        path = generate_job_script(run_dir, job_config, "srun ./solver")
        content = path.read_text()
        assert "#SBATCH --job-name=my-custom-name" in content

    def test_default_job_name(
        self, run_dir: Path, job_config: dict[str, object]
    ) -> None:
        path = generate_job_script(run_dir, job_config, "srun ./solver")
        content = path.read_text()
        assert "#SBATCH --job-name=simctl-job" in content

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

    def test_missing_partition_raises(self, run_dir: Path) -> None:
        with pytest.raises(JobScriptError, match="partition"):
            generate_job_script(
                run_dir,
                {"nodes": 1, "ntasks": 4, "walltime": "00:10:00"},
                "srun ./solver",
            )

    def test_missing_multiple_keys_raises(self, run_dir: Path) -> None:
        with pytest.raises(JobScriptError, match=r"partition.*nodes"):
            generate_job_script(
                run_dir,
                {"ntasks": 4, "walltime": "00:10:00"},
                "srun ./solver",
            )

    def test_creates_submit_dir(
        self, tmp_path: Path, job_config: dict[str, object]
    ) -> None:
        """submit/ directory should be created even if it doesn't exist."""
        rd = tmp_path / "new_run"
        rd.mkdir()
        path = generate_job_script(rd, job_config, "srun ./solver")
        assert path.parent.is_dir()
        assert path.parent.name == "submit"


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
