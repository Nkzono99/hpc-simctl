# simctl ワークフロールール

## ファイル操作の制約
- run ディレクトリ (`Rxxxx/`) は手で作らない
- `manifest.toml` は手動編集しない
- `Rxxxx/input/*` は直接作らない
- `Rxxxx/submit/job.sh` は手書きしない
- run は必ず `simctl create` または `simctl sweep` で生成する
- `work/` と `.simctl/knowledge/` の自動生成物は手で整形しない
- `runs/**/input/*` を緊急修正した場合は、同じ修正を上流へ戻す
- `tools/hpc-simctl/` は参照用。通常は編集しない

## venv
- **simctl コマンド実行前に `.venv/` を activate する**

## case 作成
- **case は `simctl new <name> -s <simulator>` で生成する** (cases/<sim>/ に自動配置)
- 生成された case.toml や入力テンプレートの編集は自由

## ジョブ投入の承認フロー
- `simctl run` はフックにより自動ブロックされる
- ブロックされたら、投入内容（コマンド、対象 run、queue 等）をユーザーに提示して承認を求める
- ユーザーが承認したら `touch .claude/hooks/.approve-run-token` してから `simctl run` を再実行する
- 承認なしに `simctl run` を繰り返し試行しない

## 知見の記録
- 実験の知見・結果は Agent の memory ではなく `/learn` で保存する
- 保存先: `.simctl/insights/`, `.simctl/facts.toml`
- `high` confidence は複数 run の再現か deterministic 確認がある場合だけ使う
