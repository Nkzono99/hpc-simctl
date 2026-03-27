"""Tests for core survey module."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from simctl.core.exceptions import SurveyConfigError
from simctl.core.survey import (
    expand_axes,
    generate_display_name,
    load_survey,
)

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


class TestLoadSurvey:
    """Tests for load_survey()."""

    def test_load_sample_survey(self, tmp_path: Path) -> None:
        shutil.copy(FIXTURES_DIR / "sample_survey.toml", tmp_path / "survey.toml")
        survey = load_survey(tmp_path)
        assert survey.id == "S20260327-cavity-u-a"
        assert survey.name == "u-aspect scan"
        assert survey.base_case == "cavity_base"
        assert survey.simulator == "lunar_pic"
        assert survey.launcher == "slurm_srun"
        assert survey.classification.model == "cavity"
        assert survey.classification.tags == ["scan", "paper1"]
        assert len(survey.axes) == 3
        assert survey.axes["u"] == [2.0e5, 4.0e5, 8.0e5]
        assert survey.naming_template == "u{u}_a{aspect}_s{seed}"
        assert survey.job.partition == "gr20001a"

    def test_missing_survey_toml(self, tmp_path: Path) -> None:
        with pytest.raises(SurveyConfigError, match=r"survey\.toml not found"):
            load_survey(tmp_path)

    def test_missing_survey_section(self, tmp_path: Path) -> None:
        (tmp_path / "survey.toml").write_text("[axes]\nu = [1, 2]\n")
        with pytest.raises(SurveyConfigError, match="\\[survey\\] section"):
            load_survey(tmp_path)

    def test_missing_required_fields(self, tmp_path: Path) -> None:
        (tmp_path / "survey.toml").write_text(
            '[survey]\nid = "S1"\nbase_case = "c"\nsimulator = "s"\n'
        )
        with pytest.raises(SurveyConfigError, match=r"survey\.launcher"):
            load_survey(tmp_path)

    def test_empty_axis(self, tmp_path: Path) -> None:
        (tmp_path / "survey.toml").write_text(
            '[survey]\nid = "S1"\nname = "t"\nbase_case = "c"\n'
            'simulator = "s"\nlauncher = "l"\n\n'
            "[axes]\nu = []\n"
        )
        with pytest.raises(SurveyConfigError, match="must not be empty"):
            load_survey(tmp_path)

    def test_invalid_toml(self, tmp_path: Path) -> None:
        (tmp_path / "survey.toml").write_text("bad toml [[[")
        with pytest.raises(SurveyConfigError, match="Invalid TOML"):
            load_survey(tmp_path)


class TestExpandAxes:
    """Tests for expand_axes()."""

    def test_single_axis(self) -> None:
        result = expand_axes({"x": [1, 2, 3]})
        assert result == [{"x": 1}, {"x": 2}, {"x": 3}]

    def test_two_axes(self) -> None:
        result = expand_axes({"a": [1, 2], "b": [10, 20]})
        assert len(result) == 4
        assert {"a": 1, "b": 10} in result
        assert {"a": 2, "b": 20} in result

    def test_three_axes(self) -> None:
        result = expand_axes({
            "u": [2e5, 4e5],
            "aspect": [2.0, 4.0],
            "seed": [1, 2],
        })
        assert len(result) == 8

    def test_empty_axes(self) -> None:
        assert expand_axes({}) == []

    def test_preserves_order(self) -> None:
        result = expand_axes({"a": [1, 2], "b": [10, 20]})
        # Cartesian product order
        assert result[0] == {"a": 1, "b": 10}
        assert result[1] == {"a": 1, "b": 20}
        assert result[2] == {"a": 2, "b": 10}
        assert result[3] == {"a": 2, "b": 20}


class TestGenerateDisplayName:
    """Tests for generate_display_name()."""

    def test_basic_template(self) -> None:
        result = generate_display_name(
            "u{u}_a{aspect}_s{seed}",
            {"u": 4e5, "aspect": 4.0, "seed": 3},
        )
        assert result == "u400000_a4_s3"

    def test_empty_template(self) -> None:
        assert generate_display_name("", {"a": 1}) == ""

    def test_integer_values(self) -> None:
        result = generate_display_name("nx{nx}", {"nx": 256})
        assert result == "nx256"

    def test_string_values(self) -> None:
        result = generate_display_name("mode_{mode}", {"mode": "fast"})
        assert result == "mode_fast"
