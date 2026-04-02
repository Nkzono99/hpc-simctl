"""Shared helpers for Diagrams-based figure and markdown generation."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from diagrams import Diagram


REPO_ROOT = Path(__file__).resolve().parent.parent
DOCS_ROOT = REPO_ROOT / "docs"
FIGURES_ROOT = DOCS_ROOT / "figures"

DEFAULT_GRAPH_ATTR: dict[str, str] = {
    "pad": "0.35",
    "nodesep": "0.7",
    "ranksep": "0.9",
    "splines": "ortho",
    "fontname": "Noto Sans CJK JP",
    "fontsize": "18",
    "labelloc": "t",
    "bgcolor": "white",
}

DEFAULT_NODE_ATTR: dict[str, str] = {
    "fontname": "Noto Sans CJK JP",
    "fontsize": "12",
}

DEFAULT_EDGE_ATTR: dict[str, str] = {
    "fontname": "Noto Sans CJK JP",
    "fontsize": "11",
}

CATEGORY_ATTRS: dict[str, dict[str, str]] = {
    "human": {
        "style": "filled,rounded",
        "fillcolor": "#e8f1ff",
        "color": "#4e79a7",
        "fontcolor": "#132238",
    },
    "agent": {
        "style": "filled,rounded",
        "fillcolor": "#eaf7ea",
        "color": "#59a14f",
        "fontcolor": "#132238",
    },
    "config": {
        "style": "filled,rounded",
        "fillcolor": "#fcebf1",
        "color": "#d37295",
        "fontcolor": "#132238",
    },
    "runtime": {
        "style": "filled,rounded",
        "fillcolor": "#fff4dd",
        "color": "#f28e2b",
        "fontcolor": "#132238",
    },
    "artifact": {
        "style": "filled,rounded",
        "fillcolor": "#f2f3f5",
        "color": "#7f7f7f",
        "fontcolor": "#132238",
    },
    "gate": {
        "style": "filled,rounded",
        "fillcolor": "#fde2e2",
        "color": "#e15759",
        "fontcolor": "#132238",
    },
}


def require_graphviz() -> None:
    """Fail with a Docker-oriented message when ``dot`` is unavailable."""
    if shutil.which("dot") is not None:
        return
    raise RuntimeError(
        "Graphviz 'dot' executable is not available on PATH.\n"
        "Run the generators inside Docker, for example:\n"
        "  python scripts/render_diagrams_in_docker.py"
    )


def prepare_figure_dir(name: str) -> Path:
    """Create and return a figure output directory under docs/figures."""
    path = FIGURES_ROOT / name
    path.mkdir(parents=True, exist_ok=True)
    return path


def png_path(base_path: Path) -> Path:
    """Return the PNG path emitted by Diagrams for a filename base path."""
    return base_path.with_suffix(".png")


def markdown_image(doc_path: Path, image_path: Path, alt: str) -> str:
    """Return a markdown image reference relative to a doc path."""
    rel = image_path.relative_to(doc_path.parent)
    return f"![{alt}]({rel.as_posix()})"


def node_attrs(kind: str) -> dict[str, str]:
    """Return Graphviz node attributes for a semantic category."""
    return dict(CATEGORY_ATTRS[kind])


def make_diagram(
    *,
    name: str,
    filename: Path,
    direction: str,
    graph_attr: dict[str, str] | None = None,
) -> Diagram:
    """Create a Diagrams diagram with project-wide styling defaults."""
    from diagrams import Diagram

    effective_graph_attr = dict(DEFAULT_GRAPH_ATTR)
    if graph_attr:
        effective_graph_attr.update(graph_attr)
    return Diagram(
        name=name,
        filename=str(filename),
        direction=direction,
        outformat="png",
        show=False,
        graph_attr=effective_graph_attr,
        node_attr=dict(DEFAULT_NODE_ATTR),
        edge_attr=dict(DEFAULT_EDGE_ATTR),
    )
