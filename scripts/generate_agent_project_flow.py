"""Generate an AI-agent-oriented project flow guide with Mermaid diagrams."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
DOC_PATH = REPO_ROOT / "docs" / "agent-project-flow.md"


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
    """One Mermaid flowchart."""

    title: str
    direction: str
    nodes: tuple[Node, ...]
    edges: tuple[Edge, ...]


STYLE_DEFS: dict[str, str] = {
    "human": "fill:#e8f1ff,stroke:#4e79a7,stroke-width:1px,color:#132238;",
    "agent": "fill:#eaf7ea,stroke:#59a14f,stroke-width:1px,color:#132238;",
    "config": "fill:#fcebf1,stroke:#d37295,stroke-width:1px,color:#132238;",
    "runtime": "fill:#fff4dd,stroke:#f28e2b,stroke-width:1px,color:#132238;",
    "artifact": "fill:#f2f3f5,stroke:#7f7f7f,stroke-width:1px,color:#132238;",
    "gate": "fill:#fde2e2,stroke:#e15759,stroke-width:1px,color:#132238;",
}


CONCEPT_ROWS: tuple[tuple[str, str, str], ...] = (
    (
        "`campaign.toml`",
        "研究意図の正本",
        "何を明らかにしたいか、どの変数を動かし、何を観測するかを Agent に渡す。",
    ),
    (
        "`cases/**/case.toml`",
        "再利用可能な実験テンプレート",
        "共通の job 設定、ベース入力、固定パラメータを保持する。",
    ),
    (
        "`runs/**/survey.toml`",
        "サーベイ設計",
        "どの軸をどう振るか、命名や job override をどうするかを定義する。",
    ),
    (
        "`runs/**/Rxxxx/manifest.toml`",
        "run の正本",
        "各実行の state、origin、provenance、job 情報を記録する。",
    ),
    (
        "`refs/`",
        "外部知識と simulator docs",
        "Agent が simulator 固有知識や cookbook を参照する入口。",
    ),
    (
        "`.simctl/insights/` と `facts.toml`",
        "学習結果の蓄積",
        "解析後に得られた知見を次の設計へ戻すための project memory。",
    ),
)


def _escape_label(text: str) -> str:
    """Escape labels for Mermaid."""
    return text.replace('"', "&quot;")


def _render_mermaid(diagram: Diagram) -> str:
    """Render a Mermaid flowchart."""
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


def _init_structure_diagram() -> Diagram:
    return Diagram(
        title="`simctl init` 後の project と Agent の見る世界",
        direction="LR",
        nodes=(
            Node("HUMAN", "研究者 / user<br/>研究テーマ・仮説・ベース入力の方針", "human"),
            Node("INIT", "simctl init / simctl setup", "runtime"),
            Node(
                "PROJECT",
                "生成された project root",
                "artifact",
            ),
            Node(
                "CONFIG",
                "simproject.toml / simulators.toml / launchers.toml / site.toml",
                "config",
            ),
            Node(
                "CAMPAIGN",
                "campaign.toml<br/>研究意図",
                "config",
            ),
            Node(
                "CASES",
                "cases/<sim>/...<br/>再利用テンプレート",
                "config",
            ),
            Node(
                "RUNS",
                "runs/...<br/>survey と run の置き場",
                "artifact",
            ),
            Node(
                "REFS",
                "refs/<repo>/...<br/>simulator docs / shared knowledge",
                "artifact",
            ),
            Node(
                "MEMORY",
                ".simctl/<br/>environment / insights / facts / knowledge",
                "artifact",
            ),
            Node(
                "AGENTBOOT",
                "CLAUDE.md / AGENTS.md / skills / rules",
                "artifact",
            ),
            Node(
                "CONTEXT",
                "simctl context --json<br/>Agent の最初の入口",
                "agent",
            ),
            Node(
                "AGENT",
                "AI Agent<br/>設計、実行、解析、学習を支援",
                "agent",
            ),
        ),
        edges=(
            Edge("HUMAN", "INIT", "初期条件を渡す"),
            Edge("INIT", "PROJECT", "scaffold を生成"),
            Edge("PROJECT", "CONFIG"),
            Edge("PROJECT", "CAMPAIGN"),
            Edge("PROJECT", "CASES"),
            Edge("PROJECT", "RUNS"),
            Edge("PROJECT", "REFS"),
            Edge("PROJECT", "MEMORY"),
            Edge("PROJECT", "AGENTBOOT"),
            Edge("PROJECT", "CONTEXT", "context bundle を生成できる"),
            Edge("CONFIG", "AGENT", "実行環境の制約"),
            Edge("CAMPAIGN", "AGENT", "研究意図"),
            Edge("CASES", "AGENT", "ベース設定"),
            Edge("REFS", "AGENT", "simulator 知識"),
            Edge("MEMORY", "AGENT", "過去の知見"),
            Edge("AGENTBOOT", "AGENT", "作業ルール"),
            Edge("CONTEXT", "AGENT", "最初の俯瞰"),
        ),
    )


def _operation_loop_diagram() -> Diagram:
    return Diagram(
        title="AI Agent 前提の運用ループ",
        direction="LR",
        nodes=(
            Node("INTENT", "1. 研究意図を確認<br/>campaign.toml を更新", "human"),
            Node(
                "UNDERSTAND",
                "2. Agent が project を把握<br/>simctl context --json / refs / .simctl",
                "agent",
            ),
            Node(
                "DESIGN",
                "3. 実験設計<br/>case.toml / survey.toml を整備",
                "agent",
            ),
            Node(
                "CREATE",
                "4. run 生成<br/>simctl runs create / sweep",
                "runtime",
            ),
            Node(
                "SUBMIT",
                "5. 実行<br/>simctl runs submit / submit --all",
                "runtime",
            ),
            Node(
                "OBSERVE",
                "6. 観測<br/>status / sync / log",
                "runtime",
            ),
            Node(
                "ANALYZE",
                "7. 解析<br/>analyze summarize / collect",
                "runtime",
            ),
            Node(
                "LEARN",
                "8. 学習を保存<br/>knowledge save / add-fact",
                "agent",
            ),
            Node(
                "REFINE",
                "9. 設計へ戻す<br/>campaign / case / survey を更新",
                "agent",
            ),
            Node(
                "FAIL",
                "失敗時<br/>log を読んで retry 方針を作る",
                "gate",
            ),
        ),
        edges=(
            Edge("INTENT", "UNDERSTAND", "テーマを渡す"),
            Edge("UNDERSTAND", "DESIGN", "制約と既知知識を反映"),
            Edge("DESIGN", "CREATE", "run を具体化"),
            Edge("CREATE", "SUBMIT", "created 状態"),
            Edge("SUBMIT", "OBSERVE", "submitted / running"),
            Edge("OBSERVE", "ANALYZE", "completed"),
            Edge("OBSERVE", "FAIL", "failed"),
            Edge("FAIL", "DESIGN", "retry か設計修正"),
            Edge("ANALYZE", "LEARN", "結果を構造化"),
            Edge("LEARN", "REFINE", "知見を次回へ反映"),
            Edge("REFINE", "DESIGN", "次のサーベイへ"),
        ),
    )


def _gate_diagram() -> Diagram:
    return Diagram(
        title="人が確認を入れるべきゲート",
        direction="TB",
        nodes=(
            Node("AGENTPLAN", "Agent が plan / 提案を作る", "agent"),
            Node(
                "COST",
                "高コスト操作<br/>新しい survey の初回 bulk submit<br/>walltime / memory / node 数を増やす retry",
                "gate",
            ),
            Node(
                "MEANING",
                "研究意味の変更<br/>campaign.toml の仮説や方向性を変える",
                "gate",
            ),
            Node(
                "DESTRUCTIVE",
                "破壊的操作<br/>archive / purge-work",
                "gate",
            ),
            Node("HUMAN", "研究者 / user が確認する", "human"),
            Node("EXEC", "Agent が実行する", "runtime"),
        ),
        edges=(
            Edge("AGENTPLAN", "COST"),
            Edge("AGENTPLAN", "MEANING"),
            Edge("AGENTPLAN", "DESTRUCTIVE"),
            Edge("COST", "HUMAN", "確認"),
            Edge("MEANING", "HUMAN", "確認"),
            Edge("DESTRUCTIVE", "HUMAN", "確認"),
            Edge("HUMAN", "EXEC", "合意後に実行"),
        ),
    )


def _concept_table() -> str:
    """Build a concept table."""
    lines = [
        "| 層 / file | 概念上の役割 | Agent から見た意味 |",
        "|---|---|---|",
    ]
    for name, role, meaning in CONCEPT_ROWS:
        lines.append(f"| {name} | {role} | {meaning} |")
    return "\n".join(lines)


def _build_document() -> str:
    diagrams = (
        _init_structure_diagram(),
        _operation_loop_diagram(),
        _gate_diagram(),
    )

    diagram_blocks: list[str] = []
    for diagram in diagrams:
        diagram_blocks.append(f"## {diagram.title}\n")
        diagram_blocks.append("```mermaid")
        diagram_blocks.append(_render_mermaid(diagram))
        diagram_blocks.append("```")
        diagram_blocks.append("")

    lines = [
        "# AI Agent 前提の project 運用概念図",
        "",
        "> このファイルは `python scripts/generate_agent_project_flow.py` で生成しています。",
        "",
        "このガイドは、`simctl init` で生成された project を人間と AI Agent がどう運用していくかを",
        "概念図としてまとめたものです。",
        "",
        "ポイントは、simctl の project を単なる directory 群ではなく、",
        "`研究意図`、`再利用テンプレート`、`実行記録`、`学習結果` を持つ運用系として捉えることです。",
        "",
        "## 概念の対応表",
        "",
        _concept_table(),
        "",
        *diagram_blocks,
        "## 読み方の要点",
        "",
        "- `simctl init` 後の project は、Agent にとっての作業場であると同時に memory でもあります。",
        "- `campaign.toml` は研究意図、`case.toml` は再利用可能な基底条件、`survey.toml` は探索計画です。",
        "- `manifest.toml` は各 run の正本で、ここに state と provenance が残ります。",
        "- 解析後の結果は `insight` や `fact` として `.simctl/` に戻すことで、次の設計に再利用できます。",
        "- つまり日常運用は `設計 -> 実行 -> 観測 -> 解析 -> 学習 -> 設計` のループです。",
        "",
        "## 実務上のおすすめ",
        "",
        "- 最初の依頼では、研究テーマ、仮説、独立変数、観測量、使いたいベース入力だけを Agent に渡す。",
        "- run ごとの場当たり的な修正は避け、再利用価値がある変更は `campaign.toml`、`case.toml`、`survey.toml` に戻す。",
        "- 毎回いきなり大量投入せず、Agent に `context` と `plan` を見せてもらってから初回 bulk submit に進む。",
        "- 解析が終わったら `knowledge save` や `add-fact` まで含めて 1 セットで閉じると、次の実験設計が速くなります。",
        "",
    ]
    return "\n".join(lines) + "\n"


def main() -> None:
    """Write the generated guide."""
    DOC_PATH.write_text(_build_document(), encoding="utf-8")
    print(f"Wrote {DOC_PATH.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
