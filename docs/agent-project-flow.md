# AI Agent 前提の project 運用概念図

> このファイルは `python scripts/generate_agent_project_flow.py` で生成しています。

このガイドは、`simctl init` で生成された project を人間と AI Agent がどう運用していくかを
概念図としてまとめたものです。

ポイントは、simctl の project を単なる directory 群ではなく、
`研究意図`、`再利用テンプレート`、`実行記録`、`学習結果` を持つ運用系として捉えることです。

## 概念の対応表

| 層 / file | 概念上の役割 | Agent から見た意味 |
|---|---|---|
| `campaign.toml` | 研究意図の正本 | 何を明らかにしたいか、どの変数を動かし、何を観測するかを Agent に渡す。 |
| `cases/**/case.toml` | 再利用可能な実験テンプレート | 共通の job 設定、ベース入力、固定パラメータを保持する。 |
| `runs/**/survey.toml` | サーベイ設計 | どの軸をどう振るか、命名や job override をどうするかを定義する。 |
| `runs/**/Rxxxx/manifest.toml` | run の正本 | 各実行の state、origin、provenance、job 情報を記録する。 |
| `refs/` | 外部知識と simulator docs | Agent が simulator 固有知識や cookbook を参照する入口。 |
| `.simctl/insights/` と `facts.toml` | 学習結果の蓄積 | 解析後に得られた知見を次の設計へ戻すための project memory。 |

## `simctl init` 後の project と Agent の見る世界

```mermaid
flowchart LR
    HUMAN["研究者 / user<br/>研究テーマ・仮説・ベース入力の方針"]
    INIT["simctl init / simctl setup"]
    PROJECT["生成された project root"]
    CONFIG["simproject.toml / simulators.toml / launchers.toml / site.toml"]
    CAMPAIGN["campaign.toml<br/>研究意図"]
    CASES["cases/<sim>/...<br/>再利用テンプレート"]
    RUNS["runs/...<br/>survey と run の置き場"]
    REFS["refs/<repo>/...<br/>simulator docs / shared knowledge"]
    MEMORY[".simctl/<br/>environment / insights / facts / knowledge"]
    AGENTBOOT["CLAUDE.md / AGENTS.md / skills / rules"]
    CONTEXT["simctl context --json<br/>Agent の最初の入口"]
    AGENT["AI Agent<br/>設計、実行、解析、学習を支援"]

    HUMAN -->|初期条件を渡す| INIT
    INIT -->|scaffold を生成| PROJECT
    PROJECT --> CONFIG
    PROJECT --> CAMPAIGN
    PROJECT --> CASES
    PROJECT --> RUNS
    PROJECT --> REFS
    PROJECT --> MEMORY
    PROJECT --> AGENTBOOT
    PROJECT -->|context bundle を生成できる| CONTEXT
    CONFIG -->|実行環境の制約| AGENT
    CAMPAIGN -->|研究意図| AGENT
    CASES -->|ベース設定| AGENT
    REFS -->|simulator 知識| AGENT
    MEMORY -->|過去の知見| AGENT
    AGENTBOOT -->|作業ルール| AGENT
    CONTEXT -->|最初の俯瞰| AGENT

    classDef agent fill:#eaf7ea,stroke:#59a14f,stroke-width:1px,color:#132238;
    classDef artifact fill:#f2f3f5,stroke:#7f7f7f,stroke-width:1px,color:#132238;
    classDef config fill:#fcebf1,stroke:#d37295,stroke-width:1px,color:#132238;
    classDef human fill:#e8f1ff,stroke:#4e79a7,stroke-width:1px,color:#132238;
    classDef runtime fill:#fff4dd,stroke:#f28e2b,stroke-width:1px,color:#132238;
    class HUMAN human
    class INIT runtime
    class PROJECT artifact
    class CONFIG config
    class CAMPAIGN config
    class CASES config
    class RUNS artifact
    class REFS artifact
    class MEMORY artifact
    class AGENTBOOT artifact
    class CONTEXT agent
    class AGENT agent
```

## AI Agent 前提の運用ループ

```mermaid
flowchart LR
    INTENT["1. 研究意図を確認<br/>campaign.toml を更新"]
    UNDERSTAND["2. Agent が project を把握<br/>simctl context --json / refs / .simctl"]
    DESIGN["3. 実験設計<br/>case.toml / survey.toml を整備"]
    CREATE["4. run 生成<br/>simctl runs create / sweep"]
    SUBMIT["5. 実行<br/>simctl runs submit / submit --all"]
    OBSERVE["6. 観測<br/>status / sync / log"]
    ANALYZE["7. 解析<br/>analyze summarize / collect"]
    LEARN["8. 学習を保存<br/>knowledge save / add-fact"]
    REFINE["9. 設計へ戻す<br/>campaign / case / survey を更新"]
    FAIL["失敗時<br/>log を読んで retry 方針を作る"]

    INTENT -->|テーマを渡す| UNDERSTAND
    UNDERSTAND -->|制約と既知知識を反映| DESIGN
    DESIGN -->|run を具体化| CREATE
    CREATE -->|created 状態| SUBMIT
    SUBMIT -->|submitted / running| OBSERVE
    OBSERVE -->|completed| ANALYZE
    OBSERVE -->|failed| FAIL
    FAIL -->|retry か設計修正| DESIGN
    ANALYZE -->|結果を構造化| LEARN
    LEARN -->|知見を次回へ反映| REFINE
    REFINE -->|次のサーベイへ| DESIGN

    classDef agent fill:#eaf7ea,stroke:#59a14f,stroke-width:1px,color:#132238;
    classDef gate fill:#fde2e2,stroke:#e15759,stroke-width:1px,color:#132238;
    classDef human fill:#e8f1ff,stroke:#4e79a7,stroke-width:1px,color:#132238;
    classDef runtime fill:#fff4dd,stroke:#f28e2b,stroke-width:1px,color:#132238;
    class INTENT human
    class UNDERSTAND agent
    class DESIGN agent
    class CREATE runtime
    class SUBMIT runtime
    class OBSERVE runtime
    class ANALYZE runtime
    class LEARN agent
    class REFINE agent
    class FAIL gate
```

## 人が確認を入れるべきゲート

```mermaid
flowchart TB
    AGENTPLAN["Agent が plan / 提案を作る"]
    COST["高コスト操作<br/>新しい survey の初回 bulk submit<br/>walltime / memory / node 数を増やす retry"]
    MEANING["研究意味の変更<br/>campaign.toml の仮説や方向性を変える"]
    DESTRUCTIVE["破壊的操作<br/>archive / purge-work"]
    HUMAN["研究者 / user が確認する"]
    EXEC["Agent が実行する"]

    AGENTPLAN --> COST
    AGENTPLAN --> MEANING
    AGENTPLAN --> DESTRUCTIVE
    COST -->|確認| HUMAN
    MEANING -->|確認| HUMAN
    DESTRUCTIVE -->|確認| HUMAN
    HUMAN -->|合意後に実行| EXEC

    classDef agent fill:#eaf7ea,stroke:#59a14f,stroke-width:1px,color:#132238;
    classDef gate fill:#fde2e2,stroke:#e15759,stroke-width:1px,color:#132238;
    classDef human fill:#e8f1ff,stroke:#4e79a7,stroke-width:1px,color:#132238;
    classDef runtime fill:#fff4dd,stroke:#f28e2b,stroke-width:1px,color:#132238;
    class AGENTPLAN agent
    class COST gate
    class MEANING gate
    class DESTRUCTIVE gate
    class HUMAN human
    class EXEC runtime
```

## 読み方の要点

- `simctl init` 後の project は、Agent にとっての作業場であると同時に memory でもあります。
- `campaign.toml` は研究意図、`case.toml` は再利用可能な基底条件、`survey.toml` は探索計画です。
- `manifest.toml` は各 run の正本で、ここに state と provenance が残ります。
- 解析後の結果は `insight` や `fact` として `.simctl/` に戻すことで、次の設計に再利用できます。
- つまり日常運用は `設計 -> 実行 -> 観測 -> 解析 -> 学習 -> 設計` のループです。

## 実務上のおすすめ

- 最初の依頼では、研究テーマ、仮説、独立変数、観測量、使いたいベース入力だけを Agent に渡す。
- run ごとの場当たり的な修正は避け、再利用価値がある変更は `campaign.toml`、`case.toml`、`survey.toml` に戻す。
- 毎回いきなり大量投入せず、Agent に `context` と `plan` を見せてもらってから初回 bulk submit に進む。
- 解析が終わったら `knowledge save` や `add-fact` まで含めて 1 セットで閉じると、次の実験設計が速くなります。

