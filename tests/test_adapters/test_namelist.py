"""Tests for the Fortran namelist parser/writer utilities."""

from __future__ import annotations

import pytest

from simctl.adapters._utils.namelist import (
    apply_overrides,
    find_current_group,
    format_value,
    parse_metadata_line,
    parse_namelist_params,
)

# ===================================================================
# Sample data
# ===================================================================

SAMPLE_NAMELIST = """\
!!key dx=[0.5],to_c=[10000.0]
&real
/
&realcv
/
&esorem
    emflag = 0
/
&jobcon
    jobnum(1:2) = 0, 1
    nstep = 2000
/
&plasma
    wp(1:3) = 2.10390362104881, 0.04909886429062906, 2.10390362104881
    wc = 0.0
    cv = 10000.0
    phiz = 0.0, phixy = 0.0
/
&tmgrid
    dt = 0.002
    nx = 1000, ny = 1, nz = 800
/
&system
    nspec = 2
/
"""

SAMPLE_PREINP = """\
!!key dx=[0.5],to_c=[10000.0]
&tmgrid
    dt = 0.002
    nx = 1000, ny = 1, nz = 800
/
&intp
    qm(1:3) = -1.0, 0.00054464638986836, 1.0
!!> npin(1:3) = nx*ny*nz*30, nx*ny*nz*30, 0
    vdri(1:3) = 0.0, 0.0, 0.0
/
"""


# ===================================================================
# parse_metadata_line
# ===================================================================


class TestParseMetadataLine:
    """Tests for parse_metadata_line."""

    def test_valid_metadata(self) -> None:
        result = parse_metadata_line("!!key dx=[0.5],to_c=[10000.0]")
        assert result == {"dx": "0.5", "to_c": "10000.0"}

    def test_no_metadata(self) -> None:
        assert parse_metadata_line("&real") == {}

    def test_empty_line(self) -> None:
        assert parse_metadata_line("") == {}

    def test_single_key(self) -> None:
        result = parse_metadata_line("!!key dx=[1.0]")
        assert result == {"dx": "1.0"}


# ===================================================================
# format_value
# ===================================================================


class TestFormatValue:
    """Tests for format_value."""

    def test_int(self) -> None:
        assert format_value(42) == "42"

    def test_float_normal(self) -> None:
        assert format_value(0.002) == "0.002"

    def test_float_zero(self) -> None:
        assert format_value(0.0) == "0.0"

    def test_float_scientific(self) -> None:
        result = format_value(1.5e-8)
        assert "e" in result.lower()

    def test_bool_true(self) -> None:
        assert format_value(True) == ".true."

    def test_bool_false(self) -> None:
        assert format_value(False) == ".false."

    def test_string(self) -> None:
        assert format_value("flat-surface") == '"flat-surface"'

    def test_list(self) -> None:
        assert format_value([1, 2, 3]) == "1, 2, 3"


# ===================================================================
# find_current_group
# ===================================================================


class TestFindCurrentGroup:
    """Tests for find_current_group."""

    def test_finds_group(self) -> None:
        lines = ["&plasma", "    wc = 0.0", "/"]
        assert find_current_group(lines, 1) == "plasma"

    def test_outside_group(self) -> None:
        lines = ["&plasma", "/", "    wc = 0.0"]
        assert find_current_group(lines, 2) == ""

    def test_empty_lines(self) -> None:
        lines: list[str] = []
        assert find_current_group(lines, 0) == ""


# ===================================================================
# parse_namelist_params
# ===================================================================


class TestParseNamelistParams:
    """Tests for parse_namelist_params."""

    def test_parse_groups(self) -> None:
        result = parse_namelist_params(SAMPLE_NAMELIST)
        assert "jobcon" in result
        assert "plasma" in result
        assert "tmgrid" in result
        assert "system" in result

    def test_parse_scalar(self) -> None:
        result = parse_namelist_params(SAMPLE_NAMELIST)
        assert result["jobcon"]["nstep"] == "2000"

    def test_parse_float(self) -> None:
        result = parse_namelist_params(SAMPLE_NAMELIST)
        assert result["plasma"]["wc"] == "0.0"

    def test_parse_array(self) -> None:
        result = parse_namelist_params(SAMPLE_NAMELIST)
        assert "jobnum(1:2)" in result["jobcon"]
        assert result["jobcon"]["jobnum(1:2)"] == "0, 1"

    def test_empty_groups(self) -> None:
        result = parse_namelist_params(SAMPLE_NAMELIST)
        # &real and &realcv have no parameters
        assert result.get("real", {}) == {}

    def test_nspec(self) -> None:
        result = parse_namelist_params(SAMPLE_NAMELIST)
        assert result["system"]["nspec"] == "2"

    def test_empty_input(self) -> None:
        assert parse_namelist_params("") == {}


# ===================================================================
# apply_overrides
# ===================================================================


class TestApplyOverrides:
    """Tests for apply_overrides."""

    def test_override_scalar(self) -> None:
        result = apply_overrides(SAMPLE_NAMELIST, {"nstep": 5000})
        assert "nstep = 5000" in result

    def test_override_float(self) -> None:
        result = apply_overrides(SAMPLE_NAMELIST, {"wc": 0.147})
        assert "wc = 0.147" in result

    def test_override_with_group(self) -> None:
        result = apply_overrides(SAMPLE_NAMELIST, {"plasma.wc": 0.294})
        assert "wc = 0.294" in result

    def test_override_preserves_other_lines(self) -> None:
        result = apply_overrides(SAMPLE_NAMELIST, {"nstep": 5000})
        # Other parameters should be unchanged
        assert "wc = 0.0" in result
        assert "dt = 0.002" in result

    def test_override_preserves_metadata(self) -> None:
        result = apply_overrides(SAMPLE_NAMELIST, {"nstep": 5000})
        assert result.startswith("!!key dx=[0.5],to_c=[10000.0]")

    def test_no_overrides(self) -> None:
        result = apply_overrides(SAMPLE_NAMELIST, {})
        assert result == SAMPLE_NAMELIST

    def test_override_dt(self) -> None:
        result = apply_overrides(SAMPLE_NAMELIST, {"dt": 0.001})
        assert "dt = 0.001" in result

    def test_override_string(self) -> None:
        namelist = '&ptcond\n    boundary_type = "flat-surface"\n/'
        result = apply_overrides(namelist, {"boundary_type": "rectangle-hole"})
        assert '"rectangle-hole"' in result

    def test_override_preinp_directive(self) -> None:
        result = apply_overrides(
            SAMPLE_PREINP,
            {"npin": [48000000, 48000000, 0]},
        )
        assert "npin" in result
        assert "48000000, 48000000, 0" in result

    def test_group_disambiguation(self) -> None:
        """When the same param name exists in multiple groups,
        dot-notation selects the correct one."""
        namelist = "&a\n    val = 1\n/\n&b\n    val = 2\n/"
        result = apply_overrides(namelist, {"b.val": 99})
        lines = result.split("\n")
        # &a.val should remain 1
        assert lines[1].strip() == "val = 1"
        # &b.val should be 99
        assert lines[4].strip() == "val = 99"

    def test_preserves_indentation(self) -> None:
        result = apply_overrides(SAMPLE_NAMELIST, {"nstep": 5000})
        for line in result.split("\n"):
            if "nstep" in line and "=" in line:
                assert line.startswith("    ")
                break
