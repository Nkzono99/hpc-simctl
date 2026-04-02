# AI エージェントではじめる hpc-simctl

このガイドは、`simctl init` 済みのプロジェクトを AI エージェントと一緒に立ち上げるための最短導線です。
`campaign.toml`、`case.toml`、`survey.toml` の詳細を最初から手で書く前提ではなく、基本はエージェントに設計と更新を任せる使い方を想定しています。

生成されるディレクトリ構造や初期ファイルの一覧は [README.md](../README.md) を参照してください。

## 前提

人間が最初に用意するのは主に次の 3 点です。

- 利用する simulator / launcher の設定
- ベースとなる入力テンプレート (`plasma.toml`, `beach.toml` など)
- 研究テーマ、仮説、探索したい変数、気になっている観測量

この土台があれば、以降の campaign 設計、case 作成、survey 設計、run 生成、投入、解析、知見整理はエージェントに支援させられます。

## 1. プロジェクトを用意する

新規プロジェクト:

```bash
uvx --from hpc-simctl simctl init
source .venv/bin/activate
simctl doctor
```

既存プロジェクトのセットアップ:

```bash
uvx --from hpc-simctl simctl setup https://github.com/user/my-project.git
cd my-project
source .venv/bin/activate
simctl doctor
```

`simctl init` が基本的な骨格を作るため、初期セットアップの説明を細かく追うより、すぐにエージェントへ研究内容を渡して構成を整えてもらう方が早いです。

## 2. 最初の依頼をそのまま渡す

最初の依頼では、何を調べたいかと、どの入力を土台にするかをまとめて伝えるのが効果的です。

```text
この simctl project を AI エージェント前提でセットアップしたい。
simulator は emses、launcher は slurm_srun。
ベース入力テンプレートは cases/emses/flat_surface/plasma.toml を使いたい。
テーマは、月面平面に太陽風プラズマが入射し、光電子放出があるときの表面帯電。
照射角を主な独立変数として調べたい。

まず project を確認して、plan を示したうえで campaign.toml と case 定義を整えて。
必要なら survey の雛形まで作って。
```

この段階では SKILL 名を明示しなくても構いません。多くの Agent 環境では、依頼内容に応じて必要な SKILL が自動選択されます。

## 3. よくある依頼パターン

細かい TOML を説明する代わりに、やりたい作業をそのまま依頼します。

- 研究意図を整理したい
  `campaign.toml を整えて。仮説、独立変数、観測量がわかる形にして。`
- case を作りたい
  `このテンプレートをベースに case を作って。共通 job 設定と params は case に寄せて。`
- survey を作りたい
  `campaign の independent variables をもとに survey.toml を作って。命名規則も入れて。`
- run を展開したい
  `この survey から run を生成して。created 状態まで進めて。`
- 投入前レビューをしたい
  `submit 前に plan と対象 run を確認して。初回 bulk submit なので確認を挟んで。`
- 失敗 run を診断したい
  `failed run を確認して。log を読んで failure_reason を整理し、retry 方針を提案して。`
- 解析と知見整理をしたい
  `completed run を summarize / collect して、insight と fact の候補を分けてまとめて。`

重要なのは、run の場当たり修正ではなく、再利用すべき変更を `campaign.toml`、`case.toml`、`survey.toml` に戻すよう依頼することです。

## 4. SKILL への言及は補助的でよい

通常は「何をしてほしいか」を書けば十分です。
それでも意図がずれるときだけ、SKILL を使う前提をひと言添えてください。

```text
campaign 設計用の SKILL を使って campaign.toml を整理して。
```

```text
知見整理用の SKILL を使って、今回の結果を insight として保存して。
```

SKILL 名を厳密に覚える必要はありません。まずはタスクを自然言語で伝え、必要なときだけ補助的に明示する運用で十分です。

## 5. 人間が確認を入れる場面

エージェント中心で進めても、次の操作は確認を挟む前提で使うのが安全です。

- 新しい survey の初回 bulk submit
- walltime / memory / node 数を増やす retry
- `archive` や `purge-work`
- 研究仮説の意味が変わる `campaign.toml` の編集

要するに、コストが高い操作、破壊的な操作、研究上の意味が変わる操作だけは人間が境界を握ります。

## 次に読む

- [README.md](../README.md): 生成される構造と全体像
- [agent-user-guide.md](agent-user-guide.md): Agent が守る基本ルール
- [toml-reference.md](toml-reference.md): 個別フィールドを手で確認したいとき
