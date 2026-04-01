from __future__ import annotations

from pathlib import Path
from typing import Any


def _append_figure(summary: dict[str, Any], rel_path: str, caption: str) -> None:
    figures = summary.setdefault("figures", [])
    if not isinstance(figures, list):
        return
    figures.append({"path": rel_path, "caption": caption})


def _save_fig(fig, output_path: Path) -> bool:
    try:
        fig.savefig(output_path, dpi=150, bbox_inches="tight")
        import matplotlib.pyplot as plt

        plt.close(fig)
    except Exception:
        return False
    return True


def _get_conductor_count(data) -> int:
    inp = getattr(data, "inp", None)
    try:
        return max(int(inp.npc), 0)
    except Exception:
        pass

    toml = getattr(data, "toml", None)
    if toml is None:
        return 0

    try:
        ptcond = getattr(toml, "ptcond", None)
        objects = getattr(ptcond, "objects", None)
        if isinstance(objects, list):
            return len(objects)
    except Exception:
        pass

    try:
        physical = getattr(getattr(toml, "meta", None), "physical", None)
        conductors = getattr(physical, "conductors", None)
        if isinstance(conductors, list):
            return len(conductors)
    except Exception:
        pass

    return 0


def _get_conductor_labels(data, conductor_count: int) -> list[str]:
    labels = [f"body{i + 1}" for i in range(conductor_count)]

    toml = getattr(data, "toml", None)
    if toml is None:
        return labels

    try:
        physical = getattr(getattr(toml, "meta", None), "physical", None)
        conductors = getattr(physical, "conductors", None)
    except Exception:
        return labels

    if not isinstance(conductors, list):
        return labels

    for idx, conductor in enumerate(conductors[:conductor_count]):
        try:
            label = str(getattr(conductor, "label", "")).strip()
        except Exception:
            label = ""
        if label:
            labels[idx] = label

    return labels


def _get_species_count(data) -> int:
    inp = getattr(data, "inp", None)
    try:
        return max(int(inp.nspec), 0)
    except Exception:
        pass

    toml = getattr(data, "toml", None)
    if toml is None:
        return 0

    for attr_chain in (("species",), ("plasma", "species")):
        try:
            value = toml
            for attr in attr_chain:
                value = getattr(value, attr)
        except Exception:
            continue
        if isinstance(value, list):
            return len(value)

    return 0


def _to_time_axis(data, steps):
    unit = getattr(data, "unit", None)
    if unit is None:
        return steps, "Step"

    try:
        return unit.t.reverse(steps), "Time [s]"
    except Exception:
        return steps, "Step"


def _to_potential_values(data, values):
    unit = getattr(data, "unit", None)
    if unit is None:
        return values, "Potential [EMSES-U]", False

    try:
        return unit.phi.reverse(values), "Potential [V]", True
    except Exception:
        return values, "Potential [EMSES-U]", False


def _make_floating_potential_plot(data, fig_dir: Path, summary: dict[str, Any]) -> None:
    conductor_count = _get_conductor_count(data)
    if conductor_count <= 0:
        return

    try:
        import matplotlib
        import numpy as np
        import pandas as pd

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        return

    try:
        pbody = data.pbody
    except Exception:
        return

    if not isinstance(pbody, pd.DataFrame) or pbody.empty:
        return

    try:
        steps = pbody["step"].to_numpy(dtype=float)
    except Exception:
        return

    if len(steps) == 0:
        return

    try:
        reference = pbody.iloc[:, -1].to_numpy(dtype=float)
    except Exception:
        return

    floating_series: list[tuple[str, Any]] = []
    labels = _get_conductor_labels(data, conductor_count)
    y_label = "Potential [EMSES-U]"
    in_si = False

    for idx in range(conductor_count):
        column = f"body{idx + 1}"
        if column not in pbody.columns:
            continue
        raw_values = pbody[column].to_numpy(dtype=float) - reference
        values, y_label, in_si = _to_potential_values(data, raw_values)
        floating_series.append((labels[idx], values))

    if not floating_series:
        return

    x_values, x_label = _to_time_axis(data, steps)
    first_values = floating_series[0][1]
    summary["conductor_count"] = len(floating_series)
    if in_si:
        summary["floating_potential_final_v"] = float(first_values[-1])
        summary["floating_potential_min_v"] = float(np.min(first_values))
        summary["floating_potential_max_v"] = float(np.max(first_values))
    else:
        summary["floating_potential_final_emses"] = float(first_values[-1])
        summary["floating_potential_min_emses"] = float(np.min(first_values))
        summary["floating_potential_max_emses"] = float(np.max(first_values))

    if len(first_values) >= 8:
        tail = np.asarray(first_values[len(first_values) // 2 :], dtype=float)
        diffs = np.abs(tail[1:] - tail[:-1])
        denom = np.abs(tail[:-1]) + 1.0e-30
        if len(diffs) > 0:
            summary["floating_potential_tail_mean_rel_change"] = float(
                np.mean(diffs / denom)
            )

    fig, ax = plt.subplots(figsize=(6.2, 4.2))
    for label, values in floating_series:
        ax.plot(x_values, values, linewidth=1.6, label=label)
    ax.set_title("Floating Potential")
    ax.set_xlabel(x_label)
    ax.set_ylabel(y_label)
    ax.grid(True, linestyle=":", alpha=0.35)
    if len(floating_series) > 1:
        ax.legend()
    fig.tight_layout()

    if _save_fig(fig, fig_dir / "floating_potential.png"):
        _append_figure(
            summary,
            "figures/floating_potential.png",
            "Floating potential time history",
        )


def _make_potential_slice_plot(data, fig_dir: Path, summary: dict[str, Any]) -> None:
    phisp = getattr(data, "phisp", None)
    if phisp is None or len(phisp) == 0:
        return

    try:
        last_frame = phisp[-1]
        nz, ny, nx = last_frame.shape
        output_path = fig_dir / "potential_xz.png"
        phisp[-1, :, ny // 2, :].plot(
            savefilename=str(output_path),
            cmap="RdBu_r",
            title=f"Potential XZ slice (y={ny // 2}, nx={nx}, nz={nz})",
        )
        _append_figure(summary, "figures/potential_xz.png", "Potential xz slice")
    except Exception:
        return


def _make_potential_density_profile_plot(
    data,
    fig_dir: Path,
    summary: dict[str, Any],
) -> None:
    phisp = getattr(data, "phisp", None)
    if phisp is None or len(phisp) == 0:
        return

    try:
        import matplotlib
        import numpy as np

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        return

    try:
        last_frame = phisp[-1]
        _nz, ny, nx = last_frame.shape
        phi_profile = phisp[-1, :, ny // 2, nx // 2]
    except Exception:
        return

    use_si = getattr(data, "unit", None) is not None
    try:
        z_axis = np.asarray(phi_profile.z_si if use_si else phi_profile.z, dtype=float)
        phi_values = np.asarray(
            phi_profile.val_si if use_si else phi_profile,
            dtype=float,
        )
    except Exception:
        return

    if z_axis.size == 0 or phi_values.size == 0:
        return

    if use_si:
        summary["centerline_potential_min_v"] = float(np.nanmin(phi_values))
        summary["centerline_potential_max_v"] = float(np.nanmax(phi_values))
        x_label = "z [m]"
        phi_label = "Potential [V]"
        density_label = "Number density [m^-3]"
    else:
        x_label = "z [cell]"
        phi_label = "Potential [EMSES-U]"
        density_label = "Number density [EMSES-U]"

    fig, (ax_phi, ax_density) = plt.subplots(
        2,
        1,
        figsize=(6.4, 6.0),
        sharex=True,
        height_ratios=(1.0, 1.0),
    )
    ax_phi.plot(z_axis, phi_values, color="tab:blue", linewidth=1.6)
    ax_phi.set_title("Centerline Potential and Density")
    ax_phi.set_ylabel(phi_label)
    ax_phi.grid(True, linestyle=":", alpha=0.35)

    density_count = 0
    density_total = None
    for species_idx in range(1, _get_species_count(data) + 1):
        try:
            density_series = getattr(data, f"nd{species_idx}p")
            density_profile = density_series[-1, :, ny // 2, nx // 2]
            density_values = np.asarray(
                density_profile.val_si if use_si else density_profile,
                dtype=float,
            )
        except Exception:
            continue

        valid = np.isfinite(density_values) & (density_values > 0.0)
        if not valid.any():
            continue

        ax_density.plot(
            z_axis[valid],
            density_values[valid],
            linewidth=1.4,
            label=f"nd{species_idx}p",
        )
        density_count += 1

        if density_total is None:
            density_total = np.zeros_like(density_values, dtype=float)
        density_total[np.isfinite(density_values)] += density_values[
            np.isfinite(density_values)
        ]

    if density_count == 0:
        plt.close(fig)
        return

    if density_total is not None and density_count > 1:
        valid_total = np.isfinite(density_total) & (density_total > 0.0)
        if valid_total.any():
            ax_density.plot(
                z_axis[valid_total],
                density_total[valid_total],
                linewidth=1.8,
                linestyle="--",
                color="black",
                label="total",
            )

    ax_density.set_xlabel(x_label)
    ax_density.set_ylabel(density_label)
    ax_density.set_yscale("log")
    ax_density.grid(True, linestyle=":", alpha=0.35)
    ax_density.legend()
    fig.tight_layout()

    summary["density_profile_species_count"] = density_count
    if _save_fig(fig, fig_dir / "potential_density_profile.png"):
        _append_figure(
            summary,
            "figures/potential_density_profile.png",
            "Centerline potential and density profiles",
        )


def _try_make_emout_plots(
    run_dir: Path,
    fig_dir: Path,
    summary: dict[str, Any],
) -> None:
    try:
        import emout
    except Exception:
        return

    work_dir = run_dir / "work"
    try:
        data = emout.Emout(work_dir)
    except Exception:
        return

    _make_floating_potential_plot(data, fig_dir, summary)
    _make_potential_slice_plot(data, fig_dir, summary)
    _make_potential_density_profile_plot(data, fig_dir, summary)


def summarize(run_dir: Path, base_summary: dict[str, Any]) -> dict[str, Any]:
    """EMSES post-process scaffold.

    This starter focuses on conductor potential diagnostics and field/density
    profiles via ``emout``.
    """

    summary = dict(base_summary)
    analysis_dir = run_dir / "analysis"
    fig_dir = analysis_dir / "figures"
    fig_dir.mkdir(parents=True, exist_ok=True)

    _try_make_emout_plots(run_dir, fig_dir, summary)

    return summary
