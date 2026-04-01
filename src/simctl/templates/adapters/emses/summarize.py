from __future__ import annotations

from pathlib import Path
from typing import Any


def _append_figure(summary: dict[str, Any], rel_path: str, caption: str) -> None:
    figures = summary.setdefault("figures", [])
    if not isinstance(figures, list):
        return
    figures.append({"path": rel_path, "caption": caption})


def _load_text_table(path: Path):
    try:
        import numpy as np
    except ImportError:
        return None

    if not path.is_file():
        return None

    try:
        data = np.loadtxt(path)
    except Exception:
        return None

    if getattr(data, "ndim", 0) == 1:
        data = data.reshape(1, -1)
    return data


def _save_line_plot(
    x_values,
    y_values,
    *,
    title: str,
    xlabel: str,
    ylabel: str,
    output_path: Path,
) -> bool:
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        return False

    fig, ax = plt.subplots(figsize=(6.0, 4.0))
    ax.plot(x_values, y_values, linewidth=1.6)
    ax.set_title(title)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.grid(True, linestyle=":", alpha=0.35)
    fig.tight_layout()
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return True


def _try_make_emout_plot(run_dir: Path, fig_dir: Path, summary: dict[str, Any]) -> None:
    try:
        import emout
    except Exception:
        return

    work_dir = run_dir / "work"
    try:
        data = emout.Emout(work_dir)
    except Exception:
        return

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


def summarize(run_dir: Path, base_summary: dict[str, Any]) -> dict[str, Any]:
    """EMSES post-process scaffold.

    This starter extracts a few common diagnostics from ASCII outputs and, when
    ``emout`` is available, saves a representative potential slice figure.
    """

    summary = dict(base_summary)
    analysis_dir = run_dir / "analysis"
    fig_dir = analysis_dir / "figures"
    fig_dir.mkdir(parents=True, exist_ok=True)
    work_dir = run_dir / "work"

    energy = _load_text_table(work_dir / "energy")
    if energy is not None and len(energy) > 0:
        steps = energy[:, 0]
        summary["energy_samples"] = int(len(steps))
        summary["energy_last_step"] = int(float(steps[-1]))
        if energy.shape[1] >= 3:
            total_energy = energy[:, 1:].sum(axis=1)
            summary["energy_total_initial"] = float(total_energy[0])
            summary["energy_total_final"] = float(total_energy[-1])
            if total_energy[0] != 0:
                summary["energy_total_ratio"] = float(
                    total_energy[-1] / total_energy[0]
                )
            if _save_line_plot(
                steps,
                total_energy,
                title="Total Energy",
                xlabel="Step",
                ylabel="Energy",
                output_path=fig_dir / "energy_total.png",
            ):
                _append_figure(
                    summary,
                    "figures/energy_total.png",
                    "Total energy time history",
                )

    pbody = _load_text_table(work_dir / "pbody")
    if pbody is not None and pbody.shape[1] >= 3:
        steps = pbody[:, 0]
        floating_potential = pbody[:, 1] - pbody[:, -1]
        summary["floating_potential_final"] = float(floating_potential[-1])
        summary["floating_potential_min"] = float(floating_potential.min())
        summary["floating_potential_max"] = float(floating_potential.max())
        if len(floating_potential) >= 8:
            tail = floating_potential[len(floating_potential) // 2 :]
            diffs = abs(tail[1:] - tail[:-1])
            denom = abs(tail[:-1]) + 1.0e-30
            if len(diffs) > 0:
                summary["floating_potential_tail_mean_rel_change"] = float(
                    (diffs / denom).mean()
                )
        if _save_line_plot(
            steps,
            floating_potential,
            title="Floating Potential",
            xlabel="Step",
            ylabel="Potential",
            output_path=fig_dir / "floating_potential.png",
        ):
            _append_figure(
                summary,
                "figures/floating_potential.png",
                "Floating potential time history",
            )

    _try_make_emout_plot(run_dir, fig_dir, summary)

    return summary
