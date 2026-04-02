"""Generate a Mermaid-based guide for the src/simctl package structure.

This script writes docs/src-structure.md from declarative diagram definitions
plus a lightweight scan of the current package tree.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_ROOT = REPO_ROOT / "src" / "simctl"
DOC_PATH = REPO_ROOT / "docs" / "src-structure.md"


@dataclass(frozen=True)
class Node:
    """One Mermaid node."""

    node_id: str
    label: str
    style_class: str


@dataclass(frozen=True)
class Edge:
    """One Mermaid edge."""

    source: str
    target: str
    label: str = ""


@dataclass(frozen=True)
class Diagram:
    """A flowchart diagram."""

    title: str
    direction: str
    nodes: tuple[Node, ...]
    edges: tuple[Edge, ...]


STYLE_DEFS: dict[str, str] = {
    "entry": "fill:#e8f1ff,stroke:#4e79a7,stroke-width:1px,color:#132238;",
    "domain": "fill:#eaf7ea,stroke:#59a14f,stroke-width:1px,color:#132238;",
    "plugin": "fill:#fff4dd,stroke:#f28e2b,stroke-width:1px,color:#132238;",
    "config": "fill:#fcebf1,stroke:#d37295,stroke-width:1px,color:#132238;",
    "artifact": "fill:#f2f3f5,stroke:#7f7f7f,stroke-width:1px,color:#132238;",
}


DIRECTORY_LABELS: dict[str, str] = {
    "cli": "Typer ベースの CLI エントリポイントと対話 UX",
    "core": "ドメインモデル、実行オーケストレーション、manifest、state、knowledge",
    "adapters": "シミュレータ固有処理と adapter registry",
    "launchers": "MPI 起動ラッパーと launcher factory",
    "jobgen": "job、launcher、site から job.sh を組み立てる層",
    "slurm": "sbatch / squeue / sacct の薄いラッパー",
    "sites": "simctl init だけが読む bundled site preset",
    "templates": "project / case / survey にコピーされる静的テンプレート",
}


KEY_FILES: tuple[tuple[str, str], ...] = (
    ("src/simctl/cli/main.py", "最上位のコマンド登録。"),
    (
        "src/simctl/core/actions.py",
        "CLI と agent が使う薄い action facade。",
    ),
    (
        "src/simctl/core/run_creation.py",
        "case -> adapter -> launcher -> site -> job.sh をつなぐ実行時の中心。",
    ),
    (
        "src/simctl/core/site.py",
        "runtime の site 解決。site.toml、legacy launcher fallback、STANDARD_SITE を扱う。",
    ),
    (
        "src/simctl/adapters/registry.py",
        "simulator adapter の registry と import-by-name 解決。",
    ),
    (
        "src/simctl/launchers/base.py",
        "Launcher.from_config() による launcher factory と profile 読み込み。",
    ),
    (
        "src/simctl/jobgen/generator.py",
        "site 固有の module / directive を含む最終的な Slurm job script 生成。",
    ),
    (
        "src/simctl/slurm/query.py",
        "Slurm state の問い合わせと simctl RunState への写像。",
    ),
    (
        "src/simctl/cli/init.py",
        "init 時に src/simctl/sites/*.toml を読み、project 側の site.toml を書く。",
    ),
)


def _escape_label(text: str) -> str:
    """Escape a label for Mermaid."""
    return text.replace('"', "&quot;")


def _render_mermaid(diagram: Diagram) -> str:
    """Render one Mermaid flowchart."""
    lines: list[str] = [f"flowchart {diagram.direction}"]

    for node in diagram.nodes:
        lines.append(f'    {node.node_id}["{_escape_label(node.label)}"]')

    lines.append("")

    for edge in diagram.edges:
        if edge.label:
            lines.append(
                f"    {edge.source} -->|{_escape_label(edge.label)}| {edge.target}"
            )
        else:
            lines.append(f"    {edge.source} --> {edge.target}")

    lines.append("")

    used_classes = {node.style_class for node in diagram.nodes}
    for class_name in sorted(used_classes):
        lines.append(f"    classDef {class_name} {STYLE_DEFS[class_name]}")

    for node in diagram.nodes:
        lines.append(f"    class {node.node_id} {node.style_class}")

    return "\n".join(lines)


def _count_directory_entries(path: Path) -> str:
    """Return a small human-readable summary for one top-level directory."""
    if path.name == "sites":
        toml_count = len(list(path.glob("*.toml")))
        md_count = len(list(path.glob("*.md")))
        return f"{toml_count} 個の preset TOML、{md_count} 個の companion doc"

    if path.name == "templates":
        file_count = len([p for p in path.rglob("*") if p.is_file()])
        return f"{file_count} 個の template asset"

    file_count = len([p for p in path.rglob("*.py") if "__pycache__" not in p.parts])
    return f"{file_count} 個の Python module"


def _build_directory_table() -> str:
    """Generate a Markdown table of top-level src/simctl directories."""
    header = [
        "| Directory | 役割 | 現在の規模 |",
        "|---|---|---|",
    ]
    rows: list[str] = []
    for name in (
        "cli",
        "core",
        "adapters",
        "launchers",
        "jobgen",
        "slurm",
        "sites",
        "templates",
    ):
        path = SRC_ROOT / name
        rows.append(
            f"| `{name}/` | {DIRECTORY_LABELS[name]} | {_count_directory_entries(path)} |"
        )
    return "\n".join(header + rows)


def _overview_diagram() -> Diagram:
    return Diagram(
        title="全体構造",
        direction="LR",
        nodes=(
            Node("CLI", "cli/<br/>Typer command と command grouping", "entry"),
            Node(
                "CORE",
                "core/<br/>Project、Case、Survey、Run、Actions、State、Knowledge",
                "domain",
            ),
            Node(
                "ADAPTERS",
                "adapters/<br/>Simulator adapter と registry",
                "plugin",
            ),
            Node(
                "LAUNCHERS",
                "launchers/<br/>srun / mpirun / mpiexec factory",
                "plugin",
            ),
            Node(
                "SITECORE",
                "core/site.py<br/>runtime site abstraction",
                "domain",
            ),
            Node(
                "JOBGEN",
                "jobgen/<br/>submit/job.sh 生成",
                "domain",
            ),
            Node(
                "SLURM",
                "slurm/<br/>sbatch / squeue / sacct wrapper",
                "domain",
            ),
            Node(
                "TEMPLATES",
                "templates/<br/>case、survey、scaffold、agent asset",
                "config",
            ),
            Node(
                "BUNDLEDSITES",
                "sites/<br/>init 専用の bundled site preset",
                "config",
            ),
            Node(
                "PROJECTFILES",
                "project files<br/>simproject.toml / simulators.toml / launchers.toml / site.toml / case.toml / survey.toml",
                "artifact",
            ),
        ),
        edges=(
            Edge("CLI", "CORE", "多くの command はここへ委譲"),
            Edge("CLI", "ADAPTERS", "config/new/update-refs は registry を使う"),
            Edge("CLI", "BUNDLEDSITES", "init が preset TOML/MD を読む"),
            Edge("CLI", "TEMPLATES", "init/new が scaffold をコピー"),
            Edge("PROJECTFILES", "CORE", "Project/Case/Survey data に変換"),
            Edge("CORE", "ADAPTERS", "run_creation / analysis が simulator 依存を解決"),
            Edge("CORE", "LAUNCHERS", "run_creation が MPI 起動方式を解決"),
            Edge("CORE", "SITECORE", "runtime site profile を解決"),
            Edge("CORE", "JOBGEN", "job.sh を組み立てる"),
            Edge("CORE", "SLURM", "submit と sync"),
            Edge("ADAPTERS", "TEMPLATES", "adapter template と guide"),
            Edge("SITECORE", "JOBGEN", "module/env/sbatch option"),
            Edge("SLURM", "CORE", "Slurm state を RunState へ戻す"),
        ),
    )


def _run_creation_diagram() -> Diagram:
    return Diagram(
        title="runs create / sweep の依存解決",
        direction="TB",
        nodes=(
            Node(
                "CREATECLI",
                "simctl runs create / runs sweep<br/>src/simctl/cli/create.py",
                "entry",
            ),
            Node(
                "ACTIONS",
                "core/actions.py<br/>execute_action('create_run' / 'create_survey')",
                "domain",
            ),
            Node(
                "PROJECT",
                "load_project()<br/>simproject.toml + simulators.toml + launchers.toml",
                "config",
            ),
            Node(
                "CASE",
                "load_case() / load_survey()<br/>case.toml と optional survey.toml",
                "config",
            ),
            Node(
                "ADREG",
                "load_adapter_for_simulator()<br/>adapter 名 = sim_cfg['adapter'] or simulator 名",
                "plugin",
            ),
            Node(
                "ADIMPORT",
                "AdapterRegistry.load_from_config()<br/>import simctl.adapters.contrib.<adapter><br/>or simctl.adapters.<adapter>",
                "plugin",
            ),
            Node(
                "ADAPTER",
                "adapter instance<br/>render_inputs / resolve_runtime / build_program_command / collect_provenance",
                "plugin",
            ),
            Node(
                "LAUNCHER",
                "load_launcher_for_name()<br/>load_launchers() -> Launcher.from_config(type)",
                "plugin",
            ),
            Node(
                "SITE",
                "load_site_profile()<br/>site.toml -> legacy launchers.toml -> STANDARD_SITE",
                "domain",
            ),
            Node(
                "JOBGEN",
                "generate_job_script()<br/>launcher exec line + site modules/env/directive",
                "domain",
            ),
            Node(
                "RUNARTIFACT",
                "run directory<br/>input/ + submit/job.sh + manifest.toml",
                "artifact",
            ),
        ),
        edges=(
            Edge("CREATECLI", "ACTIONS", "Typer command dispatch"),
            Edge("ACTIONS", "PROJECT", "project config を読む"),
            Edge("ACTIONS", "CASE", "case / survey を解決"),
            Edge("PROJECT", "ADREG", "project.simulators"),
            Edge("CASE", "ADREG", "case.simulator または survey override"),
            Edge("ADREG", "ADIMPORT", "adapter module を import"),
            Edge("ADIMPORT", "ADAPTER", "adapter class を instantiate"),
            Edge("PROJECT", "LAUNCHER", "project.launchers"),
            Edge("CASE", "LAUNCHER", "case.launcher または survey override"),
            Edge("PROJECT", "SITE", "project root"),
            Edge("ADAPTER", "JOBGEN", "build_program_command()"),
            Edge("LAUNCHER", "JOBGEN", "build_exec_line()"),
            Edge("SITE", "JOBGEN", "site module/env/sbatch"),
            Edge("JOBGEN", "RUNARTIFACT", "submit/job.sh を書く"),
            Edge("ADAPTER", "RUNARTIFACT", "input と provenance を書く"),
            Edge("CASE", "RUNARTIFACT", "job params と display name"),
        ),
    )


def _site_diagram() -> Diagram:
    return Diagram(
        title="site の init 時 preset と runtime 解決",
        direction="TB",
        nodes=(
            Node(
                "BUNDLED",
                "src/simctl/sites/*.toml + *.md<br/>例: camphor.toml / camphor.md",
                "config",
            ),
            Node(
                "INITCLI",
                "simctl init<br/>src/simctl/cli/init.py",
                "entry",
            ),
            Node(
                "PROJSITE",
                "project site.toml<br/>runtime site の source of truth",
                "config",
            ),
            Node(
                "PROJLAUNCHERS",
                "project launchers.toml<br/>init 時に launcher default をコピー",
                "config",
            ),
            Node(
                "CASENEW",
                "simctl case new<br/>resource_style を見て job field 形状を変える",
                "entry",
            ),
            Node(
                "RUNTIME",
                "core/site.load_site_profile()",
                "domain",
            ),
            Node(
                "STANDARD",
                "STANDARD_SITE<br/>site customisation なし",
                "artifact",
            ),
            Node(
                "JOBGEN",
                "jobgen.generate_job_script()",
                "domain",
            ),
            Node(
                "JOBSH",
                "submit/job.sh<br/>module load / export / #SBATCH / stdout-stderr format",
                "artifact",
            ),
        ),
        edges=(
            Edge("BUNDLED", "INITCLI", "init 時に preset を選ぶ"),
            Edge("INITCLI", "PROJSITE", "[site] section を書く"),
            Edge("INITCLI", "PROJLAUNCHERS", "[launcher] default をコピー"),
            Edge("PROJSITE", "RUNTIME", "第1優先"),
            Edge("PROJLAUNCHERS", "RUNTIME", "legacy fallback"),
            Edge("STANDARD", "RUNTIME", "最終 fallback"),
            Edge("PROJSITE", "CASENEW", "resource_style が case template に効く"),
            Edge("RUNTIME", "JOBGEN", "SiteProfile"),
            Edge("JOBGEN", "JOBSH", "最終 script を生成"),
        ),
    )


def _build_document() -> str:
    """Build the generated Markdown guide."""
    diagrams = (
        _overview_diagram(),
        _run_creation_diagram(),
        _site_diagram(),
    )

    mermaid_blocks = []
    for diagram in diagrams:
        mermaid_blocks.append(f"## {diagram.title}\n")
        mermaid_blocks.append("```mermaid")
        mermaid_blocks.append(_render_mermaid(diagram))
        mermaid_blocks.append("```")
        mermaid_blocks.append("")

    key_files_lines = [
        f"- `{path}`: {description}" for path, description in KEY_FILES
    ]

    lines = [
        "# src/simctl 構成ガイド",
        "",
        "> このファイルは `python scripts/generate_architecture_diagrams.py` で生成しています。",
        "> package 境界や依存解決を変えたら script を再実行してください。",
        "",
        "simctl の `src/` は、まず次の 3 つを分けて考えると読みやすくなります。",
        "",
        "- `cli/` は人間や agent が直接叩く Typer ベースの入り口です。",
        "- `core/` は domain model だけでなく、project 設定から adapter / launcher / site / Slurm をつなぐ orchestration module も持っています。",
        "- `adapters/`、`launchers/`、`core/site.py` はそれぞれ別の可変軸です。",
        "  simulator 固有差分、MPI 起動方式、cluster/site 固有差分を分離しています。",
        "",
        "いまの実装で特に混乱しやすいのは `site` まわりです。",
        "",
        "- `src/simctl/sites/` は project の runtime site 設定そのものではありません。",
        "- ここは `simctl init` が一度だけ読む bundled preset 集です。",
        "- 実行時に使われる site の本体は project root の `site.toml` で、解決ロジックは `src/simctl/core/site.py` にあります。",
        "",
        "## top-level directory 一覧",
        "",
        _build_directory_table(),
        "",
        *mermaid_blocks,
        "## adapter / launcher 解決の要点",
        "",
        "たとえば `case.toml` に `simulator = \"emses\"`、`launcher = \"camphor\"` と書かれているとき、",
        "実行時の解決は次の順で進みます。",
        "",
        "- `core/run_creation.py` が project、case、必要なら survey override を読みます。",
        "- simulator entry は `project.simulators` から引かれます。",
        "- `load_adapter_for_simulator()` がその entry から adapter 名を取り出します。",
        "- `AdapterRegistry.load_from_config()` は `simctl.adapters.contrib.<adapter>` を先に、次に `simctl.adapters.<adapter>` を import しようとします。",
        "- import に成功すると registry から adapter class を取り出し、instance 化します。",
        "- launcher 側はより単純で、`load_launchers()` が `launchers.toml` をたどり、`Launcher.from_config()` が `type` / `kind` に応じて `SrunLauncher`、`MpirunLauncher`、`MpiexecLauncher` を選びます。",
        "- `core/site.load_site_profile()` は launcher と独立に site を解決し、最後に `jobgen.generate_job_script()` が launcher 出力と site 固有の module、environment variable、stdout/stderr format、追加 `#SBATCH` directive を合成します。",
        "",
        "つまり責務分担は次のように切られています。",
        "",
        "- Adapter は `何を実行するか` と `入出力がどう見えるか` を決めます。",
        "- Launcher は `その program command を MPI でどう包むか` を決めます。",
        "- Site は `その cluster が job script に何を要求するか` を決めます。",
        "",
        "## 次に読むと理解しやすい file",
        "",
        *key_files_lines,
        "",
    ]
    return "\n".join(lines) + "\n"


def main() -> None:
    """Write the generated guide to docs/src-structure.md."""
    DOC_PATH.write_text(_build_document(), encoding="utf-8")
    relative = DOC_PATH.relative_to(REPO_ROOT)
    print(f"Wrote {relative}")


if __name__ == "__main__":
    main()
