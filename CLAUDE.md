# CLAUDE.md — hpc-simctl

## プロジェクト概要

HPC 環境における Slurm ベースのシミュレーション実行管理 CLI ツール。
run ディレクトリを日常運用の主単位とし、パラメータサーベイ展開・job 投入・状態追跡・provenance 記録・解析補助を一貫して管理する。

仕様書: `SPEC.md`

## 技術スタック

- 言語: Python 3.10+
- パッケージ管理: uv (pyproject.toml)
- CLI フレームワーク: typer (click ベース)
- 設定ファイル形式: TOML (tomli / tomli-w)
- テスト: pytest
- Lint/Format: ruff
- 型チェック: mypy (strict)

## ディレクトリ構成

```
hpc-simctl/
  pyproject.toml
  src/
    simctl/
      __init__.py
      cli/              # CLI エントリポイント (typer)
        __init__.py
        main.py
        init.py         # simctl init / doctor
        create.py       # simctl create / sweep
        submit.py       # simctl submit
        status.py       # simctl status / sync
        list.py         # simctl list
        clone.py        # simctl clone
        analyze.py      # simctl summarize / collect
        manage.py       # simctl archive / purge-work
      core/             # ドメインロジック
        __init__.py
        project.py      # Project 読込・検証
        case.py         # Case 読込・展開
        survey.py       # Survey 展開・parameter 直積
        run.py          # Run 生成・run_id 採番
        manifest.py     # manifest.toml 読書き
        state.py        # 状態遷移管理
        provenance.py   # コード provenance 取得
        discovery.py    # runs/ 再帰探索・run_id 一意性検証
      adapters/         # Simulator Adapter
        __init__.py
        base.py         # SimulatorAdapter 抽象基底クラス
        registry.py     # Adapter 登録・lookup
      launchers/        # Launcher Profile
        __init__.py
        base.py         # Launcher 抽象基底クラス
        srun.py
        mpirun.py
        mpiexec.py
      jobgen/           # job.sh 生成
        __init__.py
        generator.py
        templates/
      slurm/            # Slurm 連携 (sbatch / squeue / sacct)
        __init__.py
        submit.py
        query.py
  tests/
    conftest.py
    test_core/
    test_cli/
    test_adapters/
    test_launchers/
    test_slurm/
    fixtures/           # テスト用 TOML ファイル等
```

## 主要コマンド

| コマンド | 説明 |
|---------|------|
| `simctl init` | Project 初期化 (simproject.toml 等生成) |
| `simctl doctor` | 環境検査 |
| `simctl create CASE --dest DIR` | Case から単一 run 生成 |
| `simctl sweep DIR` | survey.toml から全 run 一括生成 |
| `simctl submit RUN` | sbatch で job 投入 |
| `simctl submit --all DIR` | survey 内全 run 投入 |
| `simctl status RUN` | run 状態確認・同期 |
| `simctl sync RUN` | Slurm 状態を manifest に反映 |
| `simctl list [PATH]` | run 一覧表示 |
| `simctl clone RUN --dest DIR` | run 複製・派生 |
| `simctl summarize RUN` | run 解析 summary 生成 |
| `simctl collect DIR` | survey 集計 |
| `simctl archive RUN` | run アーカイブ |
| `simctl purge-work RUN` | work/ 内の不要ファイル削除 |

## 開発ルール

### コーディング規約

- ruff format / ruff check を CI で強制
- mypy strict モード
- テストカバレッジ 80% 以上を目標
- docstring は Google style

### 設計原則

- **run ディレクトリが主単位**: すべての操作は run_id または run ディレクトリを基点とする
- **不変と可変の分離**: run_id は不変、パスは可変（分類・整理用）
- **Simulator Adapter パターン**: simulator 固有処理は Adapter に閉じ込める。core は simulator に依存しない
- **Launcher Profile パターン**: MPI 起動方式は Launcher に閉じ込める
- **MPI に介入しない**: Python ツールは rank ごとのラッパにならない。job.sh で srun/mpirun を直接実行
- **manifest.toml が正本**: run の状態・由来・provenance はすべて manifest.toml に記録

### テスト方針

- Slurm 依存部分はモック化 (実 HPC なしでテスト可能にする)
- TOML 読書きは fixtures ディレクトリのサンプルファイルを使用
- CLI テストは typer の CliRunner を使用
- Adapter / Launcher は抽象基底クラスの contract test を用意

### Git 管理

- run の大容量出力 (work/outputs/, work/restart/, work/tmp/) は .gitignore で除外
- テスト fixtures の TOML ファイルは Git 管理対象

## ビルド・実行

```bash
# 開発環境セットアップ
uv sync --dev

# テスト
uv run pytest

# Lint
uv run ruff check src/ tests/
uv run ruff format --check src/ tests/

# 型チェック
uv run mypy src/

# CLI 実行 (開発中)
uv run simctl --help
```

## 状態遷移

```
created → submitted → running → completed
created/submitted/running → failed
submitted/running → cancelled
completed → archived → purged
```

## Adapter 実装時の注意

新しい Simulator Adapter を追加する場合:
1. `src/simctl/adapters/base.py` の `SimulatorAdapter` を継承
2. 全抽象メソッドを実装: render_inputs, resolve_runtime, build_program_command, detect_outputs, detect_status, summarize, collect_provenance
3. `adapters/registry.py` に登録
4. `simulators.toml` に設定エントリを追加
5. テストを `tests/test_adapters/` に追加
