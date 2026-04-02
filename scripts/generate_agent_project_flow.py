"""Generate the AI-agent project flow guide using Python Diagrams."""

from __future__ import annotations

try:
    from diagrams import Cluster, Edge
    from diagrams.generic.compute import Rack
    from diagrams.generic.storage import Storage
    from diagrams.onprem.client import User
    from diagrams.onprem.vcs import Git
    from diagrams.programming.language import Python
except ModuleNotFoundError as exc:
    raise SystemExit(
        "Python package 'diagrams' is not installed.\n"
        "Use the Docker renderer instead:\n"
        "  python scripts/render_diagrams_in_docker.py"
    ) from exc

from diagram_utils import (
    DOCS_ROOT,
    markdown_image,
    make_diagram,
    node_attrs,
    png_path,
    prepare_figure_dir,
    require_graphviz,
)


DOC_PATH = DOCS_ROOT / "project-flow.md"

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


def _concept_table() -> str:
    lines = [
        "| 層 / file | 概念上の役割 | Agent から見た意味 |",
        "|---|---|---|",
    ]
    for name, role, meaning in CONCEPT_ROWS:
        lines.append(f"| {name} | {role} | {meaning} |")
    return "\n".join(lines)


def _build_init_world(figure_dir: str) -> str:
    base = prepare_figure_dir(figure_dir) / "init-world"
    with make_diagram(
        name="simctl init 後の project と Agent の見る世界",
        filename=base,
        direction="LR",
        graph_attr={"nodesep": "0.8", "ranksep": "1.0"},
    ):
        human = User(
            "研究者 / user\n研究テーマ・仮説\n・ベース入力の方針",
            **node_attrs("human"),
        )
        init = Rack("simctl init / simctl setup", **node_attrs("runtime"))
        context = Python("simctl context --json\nAgent の最初の入口", **node_attrs("agent"))
        agent = Python("AI Agent\n設計、実行、解析、\n学習を支援", **node_attrs("agent"))

        with Cluster("生成された project root"):
            config = Storage(
                "simproject.toml\nsimulators.toml\nlaunchers.toml\nsite.toml",
                **node_attrs("config"),
            )
            campaign = Storage("campaign.toml\n研究意図", **node_attrs("config"))
            cases = Storage("cases/<sim>/...\n再利用テンプレート", **node_attrs("config"))
            runs = Rack("runs/...\nsurvey と run の置き場", **node_attrs("artifact"))
            refs = Git(
                "refs/<repo>/...\nsimulator docs / shared knowledge",
                **node_attrs("artifact"),
            )
            memory = Storage(
                ".simctl/\nenvironment / insights / facts / knowledge",
                **node_attrs("artifact"),
            )
            agent_boot = Rack(
                "CLAUDE.md / AGENTS.md\nskills / rules",
                **node_attrs("artifact"),
            )

        human >> Edge(label="初期条件を渡す") >> init
        init >> Edge(label="scaffold を生成") >> config
        config >> Edge(label="context bundle を生成") >> context
        config >> Edge(label="実行環境の制約") >> agent
        campaign >> Edge(label="研究意図") >> agent
        cases >> Edge(label="ベース設定") >> agent
        refs >> Edge(label="simulator 知識") >> agent
        memory >> Edge(label="過去の知見") >> agent
        agent_boot >> Edge(label="作業ルール") >> agent
        context >> Edge(label="最初の俯瞰") >> agent

    return markdown_image(DOC_PATH, png_path(base), "simctl init 後の project と Agent の見る世界")


def _build_operation_loop(figure_dir: str) -> str:
    base = prepare_figure_dir(figure_dir) / "operation-loop"
    with make_diagram(
        name="AI Agent 前提の運用ループ",
        filename=base,
        direction="LR",
        graph_attr={"nodesep": "0.65", "ranksep": "0.95"},
    ):
        intent = User("1. 研究意図を確認\ncampaign.toml を更新", **node_attrs("human"))
        understand = Python(
            "2. Agent が project を把握\nsimctl context --json / refs / .simctl",
            **node_attrs("agent"),
        )
        design = Python(
            "3. 実験設計\ncase.toml / survey.toml を整備",
            **node_attrs("agent"),
        )
        create = Rack("4. run 生成\nsimctl runs create / sweep", **node_attrs("runtime"))
        submit = Rack(
            "5. 実行\nsimctl runs submit / submit --all",
            **node_attrs("runtime"),
        )
        observe = Rack("6. 観測\nstatus / sync / log", **node_attrs("runtime"))
        analyze = Rack(
            "7. 解析\nanalyze summarize / collect",
            **node_attrs("runtime"),
        )
        learn = Python(
            "8. 学習を保存\nknowledge save / add-fact",
            **node_attrs("agent"),
        )
        refine = Python(
            "9. 設計へ戻す\ncampaign / case \n/ survey を更新",
            **node_attrs("agent"),
        )
        fail = Rack("失敗時\nlog を読んで retry 方針を作る", **node_attrs("gate"))

        intent >> Edge(label="テーマを渡す") >> understand
        understand >> Edge(label="制約と既知知識を反映") >> design
        design >> Edge(label="run を具体化") >> create
        create >> Edge(label="created 状態") >> submit
        submit >> Edge(label="submitted / running") >> observe
        observe >> Edge(label="completed") >> analyze
        observe >> Edge(label="failed") >> fail
        fail >> Edge(label="retry か設計修正") >> design
        analyze >> Edge(label="結果を構造化") >> learn
        learn >> Edge(label="知見を次回へ反映") >> refine
        refine >> Edge(label="次のサーベイへ") >> design

    return markdown_image(DOC_PATH, png_path(base), "AI Agent 前提の運用ループ")


def _build_gates(figure_dir: str) -> str:
    base = prepare_figure_dir(figure_dir) / "human-gates"
    with make_diagram(
        name="人が確認を入れるべきゲート",
        filename=base,
        direction="TB",
        graph_attr={"nodesep": "0.95", "ranksep": "1.05", "splines": "spline"},
    ):
        agent_plan = Python("Agent の提案\nplan / proposal", **node_attrs("agent"))
        cost = Rack(
            "高コスト操作\n初回 bulk submit\n大きな retry",
            **node_attrs("gate"),
        )
        meaning = Rack(
            "研究意図の変更\ncampaign.toml\n仮説や方向性",
            **node_attrs("gate"),
        )
        destructive = Rack(
            "破壊的操作\narchive\npurge-work",
            **node_attrs("gate"),
        )
        human = User("研究者 / user\n確認", **node_attrs("human"))
        execute = Rack("Agent 実行", **node_attrs("runtime"))

        agent_plan >> cost
        agent_plan >> meaning
        agent_plan >> destructive
        cost >> human
        meaning >> human
        destructive >> human
        human >> Edge(label="合意後") >> execute

    return markdown_image(DOC_PATH, png_path(base), "人が確認を入れるべきゲート")


def _build_document() -> str:
    figure_dir = "agent-project-flow"
    init_world = _build_init_world(figure_dir)
    operation_loop = _build_operation_loop(figure_dir)
    gates = _build_gates(figure_dir)

    lines = [
        "# AI Agent 前提の project 運用概念図",
        "",
        "> このファイルは `python scripts/generate_agent_project_flow.py` で生成しています。",
        "> 標準の再生成手順は `python scripts/render_diagrams_in_docker.py` です。",
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
        "## `simctl init` 後の project と Agent の見る世界",
        "",
        init_world,
        "",
        "## AI Agent 前提の運用ループ",
        "",
        operation_loop,
        "",
        "## 人が確認を入れるべきゲート",
        "",
        gates,
        "",
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
    require_graphviz()
    DOC_PATH.write_text(_build_document(), encoding="utf-8")
    print(f"Wrote {DOC_PATH.relative_to(DOCS_ROOT.parent)}")


if __name__ == "__main__":
    main()
