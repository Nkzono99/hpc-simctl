from __future__ import annotations

import csv
from pathlib import Path
from typing import Any


def _append_figure(summary: dict[str, Any], rel_path: str, caption: str) -> None:
    figures = summary.setdefault("figures", [])
    if not isinstance(figures, list):
        return
    figures.append({"path": rel_path, "caption": caption})


def _find_output_dir(work_dir: Path) -> Path:
    for candidate in (work_dir / "outputs" / "latest", work_dir / "outputs", work_dir):
        if candidate.is_dir():
            return candidate
    return work_dir


def _parse_summary_txt(path: Path) -> dict[str, Any]:
    data: dict[str, Any] = {}
    if not path.is_file():
        return data

    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        value = value.strip()
        try:
            data[key] = int(value)
            continue
        except ValueError:
            pass
        try:
            data[key] = float(value)
            continue
        except ValueError:
            pass
        data[key] = value
    return data


def _read_numeric_column(path: Path, field_name: str) -> list[float]:
    if not path.is_file():
        return []

    values: list[float] = []
    with open(path, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row is None:
                continue
            raw = row.get(field_name, "").strip()
            if not raw:
                continue
            try:
                values.append(float(raw))
            except ValueError:
                continue
    return values


def _save_fig(fig, output_path: Path) -> bool:
    try:
        fig.savefig(output_path, dpi=150, bbox_inches="tight")
        import matplotlib.pyplot as plt

        plt.close(fig)
    except Exception:
        return False
    return True


def _save_line_plot(
    x_values: list[float],
    y_values: list[float],
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
    return _save_fig(fig, output_path)


def _save_bar_plot(
    x_values: list[float],
    y_values: list[float],
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

    fig, ax = plt.subplots(figsize=(6.4, 4.0))
    ax.bar(x_values, y_values, width=0.9)
    ax.set_title(title)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.grid(True, axis="y", linestyle=":", alpha=0.35)
    fig.tight_layout()
    return _save_fig(fig, output_path)


def _try_make_beach_plots(
    output_dir: Path,
    fig_dir: Path,
    summary: dict[str, Any],
) -> None:
    try:
        from beach import Beach
    except Exception:
        return

    try:
        run = Beach(output_dir)
    except Exception:
        return

    try:
        fig, _ = run.plot_bar()
        if _save_fig(fig, fig_dir / "charges_bar.png"):
            _append_figure(summary, "figures/charges_bar.png", "Charge bar chart")
    except Exception:
        pass

    try:
        result = run.result
        if result.triangles is not None:
            fig, _ = run.plot_mesh()
            if _save_fig(fig, fig_dir / "charge_mesh.png"):
                _append_figure(summary, "figures/charge_mesh.png", "Charge mesh")
    except Exception:
        pass

    try:
        result = run.result
        if result.triangles is not None:
            fig, _ = run.plot_potential()
            if _save_fig(fig, fig_dir / "potential_mesh.png"):
                _append_figure(
                    summary,
                    "figures/potential_mesh.png",
                    "Reconstructed potential mesh",
                )
    except Exception:
        pass


def summarize(run_dir: Path, base_summary: dict[str, Any]) -> dict[str, Any]:
    """BEACH post-process scaffold."""

    summary = dict(base_summary)
    analysis_dir = run_dir / "analysis"
    fig_dir = analysis_dir / "figures"
    fig_dir.mkdir(parents=True, exist_ok=True)

    output_dir = _find_output_dir(run_dir / "work")

    for key, value in _parse_summary_txt(output_dir / "summary.txt").items():
        summary.setdefault(key, value)

    charges = _read_numeric_column(output_dir / "charges.csv", "charge_C")
    if charges:
        summary["charge_elements"] = len(charges)
        summary["charge_total_c"] = float(sum(charges))
        summary["charge_abs_sum_c"] = float(sum(abs(value) for value in charges))
        summary["charge_abs_max_c"] = float(max(abs(value) for value in charges))
        if _save_bar_plot(
            [float(idx) for idx in range(len(charges))],
            charges,
            title="Charge by Element",
            xlabel="Element index",
            ylabel="Charge [C]",
            output_path=fig_dir / "charge_distribution.png",
        ):
            _append_figure(
                summary,
                "figures/charge_distribution.png",
                "Element charge distribution",
            )

    charge_history = _read_numeric_column(output_dir / "charge_history.csv", "charge_C")
    if charge_history:
        summary["charge_history_samples"] = len(charge_history)
        if _save_line_plot(
            [float(idx) for idx in range(len(charge_history))],
            charge_history,
            title="Charge History",
            xlabel="Sample",
            ylabel="Charge [C]",
            output_path=fig_dir / "charge_history.png",
        ):
            _append_figure(
                summary,
                "figures/charge_history.png",
                "Charge history trace",
            )

    potential_history = _read_numeric_column(
        output_dir / "potential_history.csv",
        "potential_V",
    )
    if potential_history:
        summary["potential_history_samples"] = len(potential_history)
        summary["potential_final_v"] = float(potential_history[-1])
        if _save_line_plot(
            [float(idx) for idx in range(len(potential_history))],
            potential_history,
            title="Potential History",
            xlabel="Sample",
            ylabel="Potential [V]",
            output_path=fig_dir / "potential_history.png",
        ):
            _append_figure(
                summary,
                "figures/potential_history.png",
                "Potential history trace",
            )

    performance_path = output_dir / "performance_profile.csv"
    if performance_path.is_file():
        try:
            from beach.cli.plot_performance_profile import load_performance_profile
        except Exception:
            pass
        else:
            try:
                _metadata, rows = load_performance_profile(performance_path)
                if rows:
                    hottest = max(rows, key=lambda row: float(row["rank_max_s"]))
                    summary["profile_region_hottest"] = str(hottest["region"])
                    summary["profile_rank_max_s"] = float(hottest["rank_max_s"])
            except Exception:
                pass

    _try_make_beach_plots(output_dir, fig_dir, summary)

    return summary
