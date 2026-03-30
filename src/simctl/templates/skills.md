# SKILLS.md — {{ project_name }}

AI エージェントが実行できるスキル (定型タスク) の一覧。

## /setup-env

プロジェクトの Python 環境をセットアップする。

**前提**: プロジェクトルートで実行すること。uv がインストール済みであること。

**手順**:

```bash
# 方法 1: ブートストラップ (新規プロジェクト)
uvx --from git+https://github.com/Nkzono99/hpc-simctl.git simctl init
source .venv/bin/activate

# 方法 2: 手動セットアップ (既存プロジェクト)
uv venv .venv
mkdir -p tools && git clone https://github.com/Nkzono99/hpc-simctl.git tools/hpc-simctl
uv pip install -e ./tools/hpc-simctl
{{ pip_install_line }}
source .venv/bin/activate
simctl doctor
```

**注意事項**:
- `.venv/` と `tools/` は `.gitignore` に追加済み
- HPC ノードでは login ノードで環境構築し、compute ノードでは同じ .venv を使う
- `module load` が必要なモジュールは `simulators.toml` の `modules` に定義済み
- simctl 更新: `cd tools/hpc-simctl && git pull`

## /survey-design

パラメータサーベイを設計する。

**入力**: ケース名、変動パラメータ、値の範囲
**出力**: `survey.toml` ファイル

**手順**:
1. 指定されたケースの `case.toml` と入力ファイルを読む
2. `refs/` 以下のシミュレータドキュメントでパラメータの意味と妥当な範囲を確認する
3. `survey.toml` を生成する (直積展開)
4. 生成される run 数を報告する

## /run-all

サーベイの全 run を生成して投入する。

**入力**: survey ディレクトリパス
**出力**: 全 run が submitted 状態

**手順**:
1. `simctl sweep <survey_dir>` で run 生成
2. `simctl list <survey_dir>` で確認
3. `simctl run --all` で投入 (`-qn QUEUE` でパーティション指定可)
4. 投入結果を報告

## /check-status

run やサーベイの状態を確認・同期する。

**入力**: run パスまたはサーベイディレクトリ
**出力**: 状態一覧 (completed / running / failed / submitted)

**手順**:
1. `simctl jobs` で実行中ジョブ一覧を確認
2. `simctl list <path>` で一覧取得
3. 各 run に対して `simctl sync` で Slurm と同期
4. 状態をサマリーとして報告 (完了数 / 実行中 / 失敗)

## /analyze

完了した run の結果を解析・集計する。

**入力**: run パスまたはサーベイディレクトリ
**出力**: 解析サマリー

**手順**:
1. `simctl summarize` で各 run の要約を生成
2. サーベイの場合は `simctl collect <dir>` で集計
3. 結果の概要と注目すべき傾向を報告

## /debug-failed

失敗した run を診断する。

**入力**: failed 状態の run パス
**出力**: 原因の診断と対処方針

**手順**:
1. `manifest.toml` から投入情報を読む
2. `simctl log -e` で stderr を確認
3. `work/*.err`, `work/*.out` からエラーメッセージを抽出
4. 原因を分類 (OOM / segfault / timeout / input error)
5. 対処方針を提案 (リソース変更 / パラメータ修正 / clone して再投入)

## /cleanup

完了・不要な run を整理する。

**入力**: 対象ディレクトリ
**出力**: アーカイブ・削除結果

**手順**:
1. `simctl list <dir>` で状態を確認
2. completed な run を `simctl archive` でアーカイブ
3. 必要に応じて `simctl purge-work` で大容量ファイルを削除
4. 整理結果を報告

## /update-refs

リファレンスリポジトリを更新し、ナレッジインデックスを再生成する。

**前提**: プロジェクトルートで実行すること。ネットワーク接続が必要。

**手順**:
1. `simctl update-refs` を実行
2. `refs/` 以下の全リポジトリが `git fetch --depth 1` + `git reset` で最新化される
3. 変更があったリポジトリを検出 (コミットハッシュ比較)
4. `.simctl/knowledge/{simulator}.md` にナレッジインデックスを再生成
5. 更新サマリーを確認

**ナレッジインデックスの使い方**:
- `.simctl/knowledge/{simulator}.md` にドキュメントの所在一覧がある
- パラメータの意味・制約・物理的安定性条件は `refs/` 内のドキュメントを直接読む
- 前回更新からの変更差分は Change Log セクションに記録される

**注意事項**:
- `refs/` のリポジトリは shallow clone なので通常の `git pull` は使わない
- `.simctl/knowledge/` は自動生成ファイル。手動編集しないこと
- シミュレータのバージョンアップ時は必ずこのコマンドを実行すること

## /learn

実験結果や経験から知見を `.simctl/insights/` に保存する。

**手順**:
1. 完了した run の結果 (`simctl summarize`, ログ, 出力) を読む
2. 新たに分かったこと・期待と異なる結果を特定する
3. 知見の種類を判断する:
   - `constraint`: 安定性・制約の発見 (例: CFL 条件違反で不安定)
   - `result`: 実験結果のサマリー (例: サーベイ全体の傾向)
   - `analysis`: 物理的考察・解釈 (例: 加熱メカニズムの推定)
   - `dependency`: パラメータ依存性 (例: 密度と帯電量の関係)
4. `simctl knowledge save <name> -t <type> -s <simulator> -m "<内容>"` で保存
5. 必要に応じてタグを付与 (`--tags "stability,cfl,grid"`)

**例**:
```bash
simctl knowledge save mag_scan_summary -t result -s emses \
  -m "磁場角度 0-90 度のサーベイ。45度で最もイオン加速が効率的。"
```

## /recall

現在のタスクに関連する知見を検索・提示する。

**手順**:
1. 現在の campaign.toml / case.toml からシミュレータとパラメータを読む
2. `simctl knowledge list -s <simulator>` で関連 insights を検索
3. リンク先プロジェクトの知見も `simctl knowledge sync` でインポート
4. 関連する知見をサマリーとして提示し、パラメータ設定に反映する

## /sync-knowledge

リンク先プロジェクトから知見をインポートする。

**手順**:
1. `.simctl/links.toml` を確認
2. `simctl knowledge sync` で全リンク先から新しい insights をインポート
3. インポート結果を報告
