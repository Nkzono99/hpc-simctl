---
name: learn
description: Save knowledge insights and structured facts from experiment results. Use after analyzing runs to capture findings.
---

# 実験結果から知見を記録する

## 手順

1. 完了した run の結果 (`simctl analyze summarize`, ログ, 出力) を読む
2. 新たに分かったこと・期待と異なる結果を特定する
3. 知見の種類を判断する

## 人向け知見の保存

```bash
simctl knowledge save <name> -t <type> -s <simulator> -m "<内容>"
```

タイプ: `constraint`, `result`, `analysis`, `dependency`

例:

```bash
simctl knowledge save mag_scan_summary -t result -s emses \
  -m "磁場角度 0-90 度のサーベイ。45度で最もイオン加速が効率的。"
```

## 機械可読な fact の追加

```bash
simctl knowledge add-fact "<claim>" \
  -t <type> -s <simulator> \
  --param-name <param> --scope-text "<scope>" \
  --evidence-kind <kind> --evidence-ref <ref> \
  -c <confidence> --tags "<tags>"
```

タイプ: `observation`, `constraint`, `dependency`, `policy`, `hypothesis`

- `high` confidence は複数 run の再現か deterministic 確認がある場合だけ使う
- 既存 fact を修正するときは `--supersedes fNNN` を使う
- 外部 source から同期された candidate fact は `simctl knowledge facts` で確認できる
- 採用する candidate fact は `simctl knowledge promote-fact <source>:<fact_id>` で local fact に昇格する
