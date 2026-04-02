# AI エージェントではじめる hpc-simctl

AI エージェントと一緒にシミュレーションプロジェクトを立ち上げるためのガイドです。
TOML ファイルを最初から手で書く必要はありません。研究内容をエージェントに伝えれば、campaign・case・survey の設計から run 管理まで支援してもらえます。

## あなたが用意するもの

エージェントに渡す前に、次の 3 つだけ決めておいてください。

1. **シミュレータとランチャー** — 使う simulator と launcher の組み合わせ
2. **入力テンプレート** — ベースとなる入力ファイル (`plasma.toml`, `beach.toml` など)
3. **研究の方向性** — テーマ、仮説、探索したい変数、注目する観測量

あとはエージェントが campaign 設計、case 作成、survey 展開、run 生成・投入・解析・知見整理を進めます。

## プロジェクトを用意する

新規作成の場合:

```bash
uvx --from hpc-simctl simctl init
source .venv/bin/activate
simctl doctor
```

既存プロジェクトをセットアップする場合:

```bash
uvx --from hpc-simctl simctl setup https://github.com/user/my-project.git
cd my-project
source .venv/bin/activate
simctl doctor
```

`simctl init` がディレクトリ構造と初期ファイルを作ります（詳細は [README.md](../README.md) を参照）。
初期セットアップを細かく確認するより、すぐにエージェントへ研究内容を渡して構成を整えてもらう方が早いです。

## 最初の依頼の出し方

何を調べたいか、どの入力を土台にするかをまとめて伝えるのが効果的です。

```text
この simctl project を AI エージェント前提でセットアップしたい。
simulator は emses、launcher は slurm_srun。
ベース入力テンプレートは cases/emses/flat_surface/plasma.toml を使いたい。
テーマは、月面平面に太陽風プラズマが入射し、光電子放出があるときの表面帯電。
照射角を主な独立変数として調べたい。

まず project を確認して、plan を示したうえで campaign.toml と case 定義を整えて。
必要なら survey の雛形まで作って。
```

SKILL 名を明示する必要はありません。依頼内容に応じて必要な SKILL は自動選択されます。

## よくある依頼パターン

細かい TOML 構文を知らなくても、やりたいことをそのまま伝えれば動きます。

| やりたいこと | 依頼の例 |
|---|---|
| 研究意図を整理する | `campaign.toml を整えて。仮説、独立変数、観測量がわかる形にして。` |
| case を作る | `このテンプレートをベースに case を作って。共通 job 設定と params は case に寄せて。` |
| survey を作る | `campaign の independent variables をもとに survey.toml を作って。命名規則も入れて。` |
| run を展開する | `この survey から run を生成して。created 状態まで進めて。` |
| 投入前にレビューする | `submit 前に plan と対象 run を確認して。初回 bulk submit なので確認を挟んで。` |
| 失敗 run を診断する | `failed run を確認して。log を読んで failure_reason を整理し、retry 方針を提案して。` |
| 解析・知見を整理する | `completed run を summarize / collect して、insight と fact の候補を分けてまとめて。` |

ポイントは、run の入力を場当たり的に直すのではなく、再利用すべき変更を `campaign.toml` → `case.toml` → `survey.toml` に戻すよう依頼することです。

## SKILL を明示するとき

通常は「何をしてほしいか」を書けば十分です。意図がずれるときだけ、ひと言添えてください。

```text
campaign 設計用の SKILL を使って campaign.toml を整理して。
```

```text
知見整理用の SKILL を使って、今回の結果を insight として保存して。
```

## 人間が確認を入れる場面

エージェント中心で進めても、以下の操作だけは確認を挟んでください。

- **コストが高い操作** — 新しい survey の初回 bulk submit、walltime / memory / node 数を増やす retry
- **破壊的な操作** — `archive`、`purge-work`
- **研究の意味が変わる操作** — 仮説の方向性が変わる `campaign.toml` の編集

それ以外はエージェントに任せて大丈夫です。

## 次に読む

- [README.md](../README.md) — 生成される構造と全体像
- [agent-user-guide.md](agent-user-guide.md) — Agent が守る基本ルール
- [toml-reference.md](toml-reference.md) — TOML フィールドを手で確認したいとき
