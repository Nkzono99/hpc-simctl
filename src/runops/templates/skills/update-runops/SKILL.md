---
name: update-runops
description: Update runops itself and refresh harness files. Use when runops has a new release or harness templates need updating.
---

# runops を最新版に更新する

## 1. tools/runops を pull

```bash
cd tools/runops && git pull && cd -
```

pull が失敗した場合 (diverge 等):

```bash
cd tools/runops && git fetch origin && git reset --hard origin/main && cd -
```

## 2. ハーネスファイルを再生成

```bash
runops update-harness
```

- 未編集のファイルは自動で上書きされる
- ユーザーが編集済みのファイルは `<path>.new` として出力される → diff を確認してマージ
- `--dry-run` で事前確認、`--force` で全上書き

## 3. シミュレータパッケージを更新

```bash
runops update
```

## 一括実行

```bash
runops update-harness && runops update
```

`update-harness` が内部で `tools/runops` の `git pull` も行うため、手順 1 を個別に実行する必要はない。

## 注意

- `tools/runops/` に未コミットの変更がある場合は pull 前にコミットまたは stash する
- `update-harness` で `.new` ファイルが生成されたら、差分を確認してから元ファイルに反映する
- 更新後は `runops doctor` で環境が正常か確認するとよい
