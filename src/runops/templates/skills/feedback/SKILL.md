---
name: feedback
description: Send feedback (bug report, feature request, improvement suggestion) to the runops upstream repository. Trigger when the user says "/feedback" or when the agent notices a runops bug/limitation worth reporting.
---

# runops へフィードバックを送る

`/feedback` は runops 本体への **バグ報告・機能要望・改善提案** を
GitHub issue として起票するスキル。現在の作業を止めずにサイドチャネルとして
フィードバックを送れる。

## 手順

### 1. フィードバック内容を整理する

ユーザーの入力 (引数テキスト) または Agent が発見した問題から、
以下を整理する:

- **種別**: bug / feature / improvement / docs
- **要約**: 1 行のタイトル
- **詳細**: 概要・再現手順・期待する挙動

### 2. 重複 issue を確認する

```bash
gh issue list --repo Nkzono99/runops --search "<キーワード>" --state all --limit 10
```

類似の既存 issue があれば、ユーザーに知らせて重複を避ける。

### 3. 環境情報を自動収集する

```bash
runops --version 2>/dev/null || echo "unknown"
python3 --version
uname -srm
```

### 4. ユーザーに確認する

起票する issue の内容 (タイトル + 本文) を **必ずユーザーに表示し、
確認を得てから** 起票する。勝手に issue を投げない。

### 5. issue を作成する

```bash
gh issue create \
  --repo Nkzono99/runops \
  --title "<タイトル>" \
  --body "$(cat <<'EOF'
## 概要
<何が問題か / どんな改善を提案するか>

## 再現手順 (bug の場合)
1. ...
2. ...

## 期待する挙動
<どうあるべきか>

## 補足
<ログ抜粋, 関連情報, 既に試した workaround など>

## 環境
- runops version: <収集した情報>
- OS: <収集した情報>
- Python: <収集した情報>
EOF
)"
```

### 6. lab notebook に記録する

作成した issue の URL を lab notebook に追記する:

```bash
runops notes append "upstream feedback" "Filed <issue-url>: <タイトル>"
```

## 注意事項

- **ユーザー確認なしに issue を投げない** — 必ず内容を見せて OK をもらう
- プロジェクト固有の private 情報 (実データパス, クラスタ固有の秘密) を
  issue 本文に含めない
- 同じ内容の重複 issue を切らない
- フィードバックを理由に **現在の研究タスクを止めない** — workaround で
  作業を進めつつ、サイドチャネルとして issue を投げる
