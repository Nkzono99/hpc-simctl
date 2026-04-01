"""Tests for survey analysis helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import tomli_w

from simctl.core.analysis import prepare_survey_plot_data
from simctl.core.exceptions import SimctlError


def _create_run(
    parent: Path,
    run_id: str,
    *,
    manifest: dict[str, Any],
    summary: dict[str, Any],
) -> Path:
    run_dir = parent / run_id
    run_dir.mkdir(parents=True)
    for sub in ("input", "submit", "work", "analysis", "status"):
        (run_dir / sub).mkdir()

    with open(run_dir / "manifest.toml", "wb") as f:
        tomli_w.dump(manifest, f)
    with open(run_dir / "analysis" / "summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f)

    return run_dir


def test_prepare_survey_plot_data_uses_numeric_manifest_columns(
    tmp_path: Path,
) -> None:
    _create_run(
        tmp_path,
        "R20260401-0001",
        manifest={
            "run": {
                "id": "R20260401-0001",
                "display_name": "baseline",
                "status": "completed",
            },
            "origin": {"case": "cavity_base"},
            "simulator": {"name": "test_sim", "adapter": "test_adapter"},
            "params_snapshot": {"u": 400000.0},
        },
        summary={"energy": 10.0},
    )

    plot_data = prepare_survey_plot_data(tmp_path, x="param.u", y="energy")

    assert plot_data.kind == "line"
    assert plot_data.points_plotted == 1
    assert plot_data.series[0].label == "all"
    assert plot_data.series[0].points[0][0] == 400000.0
    assert plot_data.series[0].points[0][1] == 10.0


def test_prepare_survey_plot_data_auto_uses_bar_for_categorical_x(
    tmp_path: Path,
) -> None:
    _create_run(
        tmp_path,
        "R20260401-0001",
        manifest={
            "run": {
                "id": "R20260401-0001",
                "display_name": "baseline",
                "status": "completed",
            },
            "origin": {"case": "flat_surface"},
            "simulator": {"name": "test_sim", "adapter": "test_adapter"},
        },
        summary={"energy": 10.0},
    )

    plot_data = prepare_survey_plot_data(tmp_path, x="origin.case", y="energy")

    assert plot_data.kind == "bar"
    assert plot_data.series[0].points[0][0] == "flat_surface"


def test_prepare_survey_plot_data_rejects_unknown_columns(tmp_path: Path) -> None:
    _create_run(
        tmp_path,
        "R20260401-0001",
        manifest={
            "run": {
                "id": "R20260401-0001",
                "display_name": "baseline",
                "status": "completed",
            },
            "simulator": {"name": "test_sim", "adapter": "test_adapter"},
        },
        summary={"energy": 10.0},
    )

    with pytest.raises(SimctlError, match="Unknown x column"):
        prepare_survey_plot_data(tmp_path, x="param.u", y="energy")
