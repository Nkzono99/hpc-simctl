"""Tests for the EMSES adapter — contract tests for all abstract methods."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from simctl.adapters.emses import EmseAdapter

SAMPLE_PREINP = """\
!!key dx=[0.5],to_c=[10000.0]
&real
/
&jobcon
    nstep = 2000
/
&plasma
    wc = 0.0
    phiz = 0.0
/
&tmgrid
    dt = 0.002
    nx = 1000, ny = 1, nz = 800
/
&system
    nspec = 2
/
"""


@pytest.fixture()
def adapter() -> EmseAdapter:
    """Return a fresh EmseAdapter instance."""
    return EmseAdapter()


@pytest.fixture()
def run_dir(tmp_path: Path) -> Path:
    """Create a minimal run directory structure."""
    for sub in ("input", "work", "analysis", "status", "submit"):
        (tmp_path / sub).mkdir()
    return tmp_path


@pytest.fixture()
def case_dir(tmp_path: Path) -> Path:
    """Create a case directory with a plasma.preinp template."""
    cdir = tmp_path / "case_flat"
    cdir.mkdir()
    (cdir / "plasma.preinp").write_text(SAMPLE_PREINP)
    return cdir


@pytest.fixture()
def case_data(case_dir: Path) -> dict[str, Any]:
    """Sample EMSES case data."""
    return {
        "case": {
            "name": "flat_surface",
            "simulator": "emses",
            "launcher": "srun",
            "case_dir": str(case_dir),
        },
        "params": {
            "nstep": 5000,
            "wc": 0.147,
        },
    }


# ===================================================================
# 1. name
# ===================================================================


class TestName:
    def test_name(self, adapter: EmseAdapter) -> None:
        assert adapter.name == "emses"


# ===================================================================
# 2. render_inputs
# ===================================================================


class TestRenderInputs:
    def test_renders_preinp_with_overrides(
        self, adapter: EmseAdapter, run_dir: Path, case_data: dict[str, Any]
    ) -> None:
        created = adapter.render_inputs(case_data, run_dir)
        assert "input/plasma.preinp" in created
        content = (run_dir / "input" / "plasma.preinp").read_text()
        assert "nstep = 5000" in content
        assert "wc = 0.147" in content

    def test_preserves_unmodified_params(
        self, adapter: EmseAdapter, run_dir: Path, case_data: dict[str, Any]
    ) -> None:
        adapter.render_inputs(case_data, run_dir)
        content = (run_dir / "input" / "plasma.preinp").read_text()
        # phiz was not overridden
        assert "phiz = 0.0" in content
        assert "dt = 0.002" in content

    def test_no_case_section_raises(
        self, adapter: EmseAdapter, run_dir: Path
    ) -> None:
        with pytest.raises(ValueError, match="case"):
            adapter.render_inputs({}, run_dir)

    def test_no_template_creates_no_files(
        self, adapter: EmseAdapter, run_dir: Path
    ) -> None:
        data: dict[str, Any] = {
            "case": {"name": "empty", "simulator": "emses", "case_dir": "/nonexistent"},
        }
        created = adapter.render_inputs(data, run_dir)
        assert created == []

    def test_copies_companion_plasma_inp(
        self, adapter: EmseAdapter, run_dir: Path, case_dir: Path
    ) -> None:
        (case_dir / "plasma.inp").write_text(
            "&jobcon\n    nstep = 2000\n/\n"
        )
        data: dict[str, Any] = {
            "case": {"name": "test", "simulator": "emses", "case_dir": str(case_dir)},
            "params": {"nstep": 9999},
        }
        created = adapter.render_inputs(data, run_dir)
        assert "input/plasma.preinp" in created
        assert "input/plasma.inp" in created
        content = (run_dir / "input" / "plasma.inp").read_text()
        assert "nstep = 9999" in content


# ===================================================================
# 3. resolve_runtime
# ===================================================================


class TestResolveRuntime:
    def test_package_mode(self, adapter: EmseAdapter) -> None:
        with patch("shutil.which", return_value="/usr/bin/mpiemses3D"):
            rt = adapter.resolve_runtime(
                {"executable": "mpiemses3D"}, "package"
            )
        assert rt["executable"] == "/usr/bin/mpiemses3D"

    def test_local_executable_mode(self, adapter: EmseAdapter) -> None:
        rt = adapter.resolve_runtime(
            {"executable": "/opt/emses/mpiemses3D"}, "local_executable"
        )
        assert rt["executable"] == "/opt/emses/mpiemses3D"

    def test_local_source_mode(self, adapter: EmseAdapter) -> None:
        rt = adapter.resolve_runtime(
            {"source_repo": "/src/EMSES", "executable": "mpiemses3D"},
            "local_source",
        )
        assert rt["source_repo"] == "/src/EMSES"

    def test_unsupported_mode(self, adapter: EmseAdapter) -> None:
        with pytest.raises(ValueError, match="Unsupported"):
            adapter.resolve_runtime({}, "conda")

    def test_local_source_missing_repo(self, adapter: EmseAdapter) -> None:
        with pytest.raises(ValueError, match="source_repo"):
            adapter.resolve_runtime({"executable": "x"}, "local_source")

    def test_local_executable_missing_exe(self, adapter: EmseAdapter) -> None:
        with pytest.raises(ValueError, match="executable"):
            adapter.resolve_runtime({}, "local_executable")


# ===================================================================
# 4. build_program_command
# ===================================================================


class TestBuildProgramCommand:
    def test_basic_command(
        self, adapter: EmseAdapter, run_dir: Path
    ) -> None:
        cmd = adapter.build_program_command(
            {"executable": "/opt/mpiemses3D"}, run_dir
        )
        assert cmd == ["/opt/mpiemses3D", "plasma.inp"]

    def test_default_executable(
        self, adapter: EmseAdapter, run_dir: Path
    ) -> None:
        cmd = adapter.build_program_command({}, run_dir)
        assert cmd[0] == "mpiemses3D"


# ===================================================================
# 5. detect_outputs
# ===================================================================


class TestDetectOutputs:
    def test_no_work_dir(self, adapter: EmseAdapter, tmp_path: Path) -> None:
        assert adapter.detect_outputs(tmp_path) == {}

    def test_detects_h5_files(
        self, adapter: EmseAdapter, run_dir: Path
    ) -> None:
        (run_dir / "work" / "ex00_0000.h5").write_bytes(b"")
        (run_dir / "work" / "ey00_0000.h5").write_bytes(b"")
        outputs = adapter.detect_outputs(run_dir)
        assert "hdf5_fields" in outputs
        assert len(outputs["hdf5_fields"]) == 2

    def test_detects_diagnostics(
        self, adapter: EmseAdapter, run_dir: Path
    ) -> None:
        (run_dir / "work" / "energy").write_text("0 1.0 2.0")
        (run_dir / "work" / "volt").write_text("0 0.5")
        outputs = adapter.detect_outputs(run_dir)
        assert "diagnostics" in outputs
        assert len(outputs["diagnostics"]) == 2

    def test_detects_snapshots(
        self, adapter: EmseAdapter, run_dir: Path
    ) -> None:
        snap_dir = run_dir / "work" / "SNAPSHOT1"
        snap_dir.mkdir()
        (snap_dir / "esdat0000.h5").write_bytes(b"")
        (snap_dir / "esdat0001.h5").write_bytes(b"")
        outputs = adapter.detect_outputs(run_dir)
        assert "snapshots" in outputs
        assert len(outputs["snapshots"]) == 2

    def test_detects_logs(
        self, adapter: EmseAdapter, run_dir: Path
    ) -> None:
        (run_dir / "work" / "stdout.12345.log").write_text("output")
        outputs = adapter.detect_outputs(run_dir)
        assert "logs" in outputs


# ===================================================================
# 6. detect_status
# ===================================================================


class TestDetectStatus:
    def test_unknown_no_work(
        self, adapter: EmseAdapter, tmp_path: Path
    ) -> None:
        assert adapter.detect_status(tmp_path) == "unknown"

    def test_unknown_empty_work(
        self, adapter: EmseAdapter, run_dir: Path
    ) -> None:
        assert adapter.detect_status(run_dir) == "unknown"

    def test_failed_on_error_log(
        self, adapter: EmseAdapter, run_dir: Path
    ) -> None:
        (run_dir / "work" / "stderr.123.log").write_text(
            "Segmentation fault"
        )
        assert adapter.detect_status(run_dir) == "failed"

    def test_completed_when_nstep_reached(
        self, adapter: EmseAdapter, run_dir: Path
    ) -> None:
        # Set up input with nstep = 100
        (run_dir / "input" / "plasma.inp").write_text(
            "&jobcon\n    nstep = 100\n/\n"
        )
        # Energy file showing step 100 reached
        (run_dir / "work" / "energy").write_text(
            "50 1.0 2.0\n100 1.1 2.1\n"
        )
        assert adapter.detect_status(run_dir) == "completed"

    def test_running_when_not_finished(
        self, adapter: EmseAdapter, run_dir: Path
    ) -> None:
        (run_dir / "input" / "plasma.inp").write_text(
            "&jobcon\n    nstep = 1000\n/\n"
        )
        (run_dir / "work" / "energy").write_text("50 1.0 2.0\n")
        assert adapter.detect_status(run_dir) == "running"

    def test_running_with_h5_files(
        self, adapter: EmseAdapter, run_dir: Path
    ) -> None:
        (run_dir / "work" / "ex00_0000.h5").write_bytes(b"")
        assert adapter.detect_status(run_dir) == "running"


# ===================================================================
# 7. summarize
# ===================================================================


class TestSummarize:
    def test_basic_summary(
        self, adapter: EmseAdapter, run_dir: Path
    ) -> None:
        summary = adapter.summarize(run_dir)
        assert summary["status"] == "unknown"
        assert "output_counts" in summary

    def test_summary_with_energy(
        self, adapter: EmseAdapter, run_dir: Path
    ) -> None:
        (run_dir / "work" / "energy").write_text("50 1.0\n100 1.1\n")
        summary = adapter.summarize(run_dir)
        assert summary["total_energy_lines"] == 2
        assert summary["last_step"] == 100

    def test_summary_reads_params(
        self, adapter: EmseAdapter, run_dir: Path
    ) -> None:
        (run_dir / "input" / "plasma.inp").write_text(
            "&tmgrid\n    nx = 512\n    dt = 0.001\n/\n"
            "&jobcon\n    nstep = 5000\n/\n"
        )
        summary = adapter.summarize(run_dir)
        assert summary["nx"] == "512"
        assert summary["nstep"] == "5000"


# ===================================================================
# 8. collect_provenance
# ===================================================================


class TestCollectProvenance:
    def test_basic_provenance(self, adapter: EmseAdapter) -> None:
        prov = adapter.collect_provenance(
            {"resolver_mode": "local_executable", "executable": "/x/solver"}
        )
        assert prov["resolver_mode"] == "local_executable"
        assert prov["exe_hash"] == ""  # file doesn't exist

    def test_provenance_with_real_file(
        self, adapter: EmseAdapter, tmp_path: Path
    ) -> None:
        exe = tmp_path / "mpiemses3D"
        exe.write_bytes(b"fake binary")
        prov = adapter.collect_provenance(
            {"resolver_mode": "local_executable", "executable": str(exe)}
        )
        assert prov["exe_hash"].startswith("sha256:")


# ===================================================================
# 9. Helper methods
# ===================================================================


class TestHelpers:
    def test_get_setup_commands(
        self, adapter: EmseAdapter, run_dir: Path
    ) -> None:
        cmds = adapter.get_setup_commands(run_dir)
        assert any("plasma" in c for c in cmds)
        assert any("preinp" in c for c in cmds)

    def test_get_modules(self, adapter: EmseAdapter) -> None:
        modules = adapter.get_modules()
        assert any("intel" in m for m in modules)
        assert any("hdf5" in m for m in modules)

    def test_get_extra_env(self, adapter: EmseAdapter) -> None:
        env = adapter.get_extra_env()
        assert "EMSES_DEBUG" in env
