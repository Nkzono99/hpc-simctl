# simctl ワークフロールール

## ファイル操作の制約
- run ディレクトリ (`Rxxxx/`) は手で作らない
- `manifest.toml` は手動編集しない
- `Rxxxx/input/*` は直接作らない
- `Rxxxx/submit/job.sh` は手書きしない
- run は必ず `simctl runs create` または `simctl runs sweep` で生成する
- `work/` と `.simctl/knowledge/` の自動生成物は手で整形しない
- `.simctl/insights/` と `.simctl/facts.toml` は直接編集せず、`simctl knowledge save` / `add-fact` を使う
- `SITE.md` は site profile 由来の生成ドキュメントとして直接編集しない
- `runs/**/input/*` を緊急修正した場合は、同じ修正を上流へ戻す
- `tools/hpc-simctl/` は参照用。通常は編集しない
- `simproject.toml` / `simulators.toml` / `launchers.toml` / `CLAUDE.md` / `.claude/` の変更は確認を挟む

## venv
- **simctl コマンド実行前に `.venv/` を activate する**

## case 作成
- **case は `simctl case new <name> -s <simulator>` で生成する** (cases/<sim>/ に自動配置)
- 生成された case.toml や入力テンプレートの編集は自由

## ジョブ投入の承認フロー
- `simctl runs submit` はフックにより毎回確認を求められる
- 実行前に、投入内容（コマンド、対象 run、queue、資源量）をユーザーに提示して承認を求める
- `--dry-run` は確認用なのでそのまま実行してよい
- 承認なしに実ジョブ投入を繰り返し試行しない

## 知見の記録
- 実験の知見・結果は Agent の memory ではなく `/learn` で保存する
- 保存先: `.simctl/insights/`, `.simctl/facts.toml`
- 外部 source から来た候補 fact は `.simctl/knowledge/candidates/facts/` に入る
- 候補 fact を採用するときは `simctl knowledge promote-fact <source>:<fact_id>` を使う
- `high` confidence は複数 run の再現か deterministic 確認がある場合だけ使う

## 解析 scratch
- 試行中の図・ノート・一時集計は `runs/**/analysis/scratch/` に置く
- `analysis/summary.json` や curated figure を scratch 出力で上書きしない
