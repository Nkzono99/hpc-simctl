"""CLI commands for project initialization and environment checks."""

from __future__ import annotations

import logging
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Annotated, Any, Optional

import typer

from simctl.core.discovery import validate_uniqueness
from simctl.core.exceptions import DuplicateRunIdError, ProjectConfigError
from simctl.core.project import load_project

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

try:
    import tomli_w
except ImportError:
    tomli_w = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

_SIMPROJECT_FILE = "simproject.toml"
_SIMULATORS_FILE = "simulators.toml"
_LAUNCHERS_FILE = "launchers.toml"
_CLAUDE_MD = "CLAUDE.md"
_AGENTS_MD = "AGENTS.md"
_SKILLS_MD = "SKILLS.md"
_VSCODE_DIR = ".vscode"
_VSCODE_SETTINGS = "settings.json"

_GITIGNORE_CONTENT = """\
# Python venv
.venv/

# heavy run outputs
runs/**/work/outputs/
runs/**/work/restart/
runs/**/work/tmp/

# logs
runs/**/work/*.out
runs/**/work/*.err
runs/**/work/*.log

# analysis cache
runs/**/analysis/cache/
runs/**/analysis/.ipynb_checkpoints/
"""

_VSCODE_SETTINGS_CONTENT = """\
{
    "python.defaultInterpreterPath": "${workspaceFolder}/.venv/bin/python",
    "python.terminal.activateEnvironment": false,
    "terminal.integrated.env.linux": {
        "VIRTUAL_ENV": "${workspaceFolder}/.venv",
        "PATH": "${workspaceFolder}/.venv/bin:${env:PATH}",
        "VIRTUAL_ENV_DISABLE_PROMPT": "1"
    }
}
"""


def _write_if_missing(path: Path, content: str) -> bool:
    """Write content to path if the file does not already exist.

    Args:
        path: File path to create.
        content: File content to write.

    Returns:
        True if the file was created, False if it already existed.
    """
    if path.exists():
        return False
    path.write_text(content, encoding="utf-8")
    return True


def _mkdir_if_missing(path: Path) -> bool:
    """Create a directory if it does not already exist.

    Args:
        path: Directory path to create.

    Returns:
        True if the directory was created, False if it already existed.
    """
    if path.exists():
        return False
    path.mkdir(parents=True)
    return True


def _build_simulators_toml(simulator_names: list[str]) -> str:
    """Build simulators.toml content from adapter default configs.

    Args:
        simulator_names: List of simulator adapter names (e.g. ["emses", "beach"]).

    Returns:
        TOML string for simulators.toml.

    Raises:
        typer.BadParameter: If a simulator name is not recognized.
    """
    from simctl.adapters.registry import get_global_registry

    # Ensure built-in adapters are registered
    import simctl.adapters  # noqa: F401

    registry = get_global_registry()
    available = registry.list_adapters()

    config: dict[str, Any] = {"simulators": {}}
    for sim_name in simulator_names:
        if sim_name not in available:
            msg = (
                f"Unknown simulator: '{sim_name}'. "
                f"Available: {', '.join(available)}"
            )
            raise typer.BadParameter(msg)
        adapter_cls = registry.get(sim_name)
        config["simulators"][sim_name] = adapter_cls.default_config()

    if tomli_w is None:
        # Fallback to manual TOML generation
        lines = ["[simulators]", ""]
        for sim_name, sim_cfg in config["simulators"].items():
            lines.append(f"[simulators.{sim_name}]")
            for key, value in sim_cfg.items():
                if isinstance(value, list):
                    items = ", ".join(f'"{v}"' for v in value)
                    lines.append(f"{key} = [{items}]")
                elif isinstance(value, str):
                    lines.append(f'{key} = "{value}"')
                else:
                    lines.append(f"{key} = {value}")
            lines.append("")
        return "\n".join(lines) + "\n"

    import io

    buf = io.BytesIO()
    tomli_w.dump(config, buf)
    return buf.getvalue().decode("utf-8")


def _collect_pip_packages(simulator_names: list[str]) -> list[str]:
    """Collect unique pip packages from adapters."""
    from simctl.adapters.registry import get_global_registry

    import simctl.adapters  # noqa: F401

    registry = get_global_registry()
    seen: set[str] = set()
    packages: list[str] = []
    for sim_name in simulator_names:
        try:
            adapter_cls = registry.get(sim_name)
            for pkg in adapter_cls.pip_packages():
                if pkg not in seen:
                    seen.add(pkg)
                    packages.append(pkg)
        except KeyError:
            pass
    return packages


def _build_simulator_guides(simulator_names: list[str]) -> str:
    """Collect agent_guide() from adapters for the given simulators."""
    from simctl.adapters.registry import get_global_registry

    import simctl.adapters  # noqa: F401

    registry = get_global_registry()
    parts: list[str] = []
    for sim_name in simulator_names:
        try:
            adapter_cls = registry.get(sim_name)
            parts.append(adapter_cls.agent_guide())
        except KeyError:
            pass
    return "\n".join(parts)


def _build_claude_md(project_name: str, simulator_names: list[str]) -> str:
    """Build CLAUDE.md content."""
    sim_section = ""
    if simulator_names:
        guides = _build_simulator_guides(simulator_names)
        sim_section = f"""
## シミュレータ固有知識

{guides}
"""

    # Build pip packages info for env section
    pip_pkgs = _collect_pip_packages(simulator_names) if simulator_names else []
    pip_line = " ".join(pip_pkgs) if pip_pkgs else "<必要なパッケージ>"

    return f"""\
# CLAUDE.md — {project_name}

このプロジェクトは simctl (HPC シミュレーション管理 CLI) で管理されています。
AI エージェントがシミュレーションの準備・投入・監視・解析を自律的に行います。

## プロジェクト構成

```
{project_name}/
  simproject.toml      # プロジェクト設定
  simulators.toml      # シミュレータ定義 (adapter, executable, modules)
  launchers.toml       # MPI ランチャー設定
  cases/               # ケーステンプレート (入力ファイル + case.toml)
  runs/                # 実行ディレクトリ (自動生成)
    <survey_or_group>/
      Rxxxx/           # 各 run ディレクトリ
        manifest.toml  # run のメタデータ・状態 (正本)
        input/         # 入力ファイル (不変)
        work/          # 実行出力 (大容量)
        analysis/      # 解析結果
```

## simctl コマンド一覧

| コマンド | 用途 |
|---------|------|
| `simctl init [SIMULATORS...] -p PATH` | プロジェクト初期化 |
| `simctl doctor` | 環境・設定検査 |
| `simctl create CASE --dest DIR` | ケースから単一 run 生成 |
| `simctl sweep DIR` | survey.toml から全 run 一括生成 |
| `simctl submit RUN` | sbatch で job 投入 |
| `simctl submit --all DIR` | survey 内全 run 一括投入 |
| `simctl status RUN` | run 状態確認 |
| `simctl sync RUN` | Slurm 状態を manifest に反映 |
| `simctl list [PATH]` | run 一覧表示 |
| `simctl clone RUN --dest DIR` | run 複製 |
| `simctl summarize RUN` | 解析 summary 生成 |
| `simctl collect DIR` | survey 結果集計 |
| `simctl archive RUN` | run アーカイブ |
| `simctl purge-work RUN` | work/ 不要ファイル削除 |

## 状態遷移

```
created → submitted → running → completed
created/submitted/running → failed
submitted/running → cancelled
completed → archived → purged
```

## 重要なファイル

- **`manifest.toml`** — run の正本。状態・パラメータ・provenance をすべて記録
- **`simproject.toml`** — プロジェクト名・説明
- **`simulators.toml`** — シミュレータの adapter / executable / modules 定義
- **`launchers.toml`** — MPI ランチャーの設定
- **`case.toml`** — ケーステンプレートの定義
- **`survey.toml`** — パラメータサーベイの定義 (直積展開)
{sim_section}
## 環境構築

プロジェクトルートに `.venv` を作って Python 環境を管理する。
詳細な手順は `SKILLS.md` の `/setup-env` を参照。

```bash
# uv のインストール (未インストールの場合)
curl -LsSf https://astral.sh/uv/install.sh | sh

# .venv 作成 + パッケージインストール
uv venv
uv pip install hpc-simctl {pip_line}

# 確認
source .venv/bin/activate
simctl doctor
```

## 運用ルール

- run ディレクトリ (`Rxxxx/`) が全操作の基点
- `manifest.toml` が正本。手動編集は避け、simctl コマンド経由で更新する
- `input/` 内のファイルは run 生成後に変更しない (不変)
- `work/` の大容量ファイルは Git 管理外 (.gitignore 済み)
- `.venv/` はプロジェクトルートに配置。Git 管理外
- パラメータ変更は case.toml / survey.toml で管理し、新しい run を生成する
"""


def _build_agents_md(project_name: str, simulator_names: list[str]) -> str:
    """Build AGENTS.md content."""
    sim_names_str = ", ".join(simulator_names) if simulator_names else "(未設定)"

    return f"""\
# AGENTS.md — {project_name}

AI エージェントによるシミュレーション管理の運用ガイドライン。

## エージェントの役割

このプロジェクトでは AI エージェントが以下を自律的に実行する:

1. **計画**: パラメータサーベイの設計・survey.toml の作成
2. **準備**: case テンプレート作成、run 生成 (`simctl create` / `simctl sweep`)
3. **投入**: job 投入 (`simctl submit`)、リソース配分の調整
4. **監視**: 状態追跡 (`simctl status` / `simctl sync`)、異常検出
5. **解析**: 結果の要約 (`simctl summarize`)、集計 (`simctl collect`)
6. **管理**: アーカイブ・クリーンアップ (`simctl archive` / `simctl purge-work`)

## 対象シミュレータ

{sim_names_str}

各シミュレータの詳細は CLAUDE.md のシミュレータ固有知識セクションを参照。

## 典型的なワークフロー

### 新規パラメータサーベイ

```bash
# 1. ケーステンプレートを確認
ls cases/

# 2. survey.toml を作成 (直積パラメータを定義)
# 3. 全 run を一括生成
simctl sweep surveys/my_survey/

# 4. 生成された run を確認
simctl list surveys/my_survey/

# 5. 全 run を投入
simctl submit --all surveys/my_survey/

# 6. 状態を監視
simctl status surveys/my_survey/R0001
simctl sync surveys/my_survey/R0001

# 7. 完了後に結果を集計
simctl collect surveys/my_survey/
```

### 単一 run の実行

```bash
simctl create cases/my_case --dest runs/test/
simctl submit runs/test/R0001
simctl status runs/test/R0001
simctl summarize runs/test/R0001
```

### 失敗した run のデバッグ

```bash
# 1. 状態確認
simctl status runs/.../Rxxxx

# 2. ログを確認
cat runs/.../Rxxxx/work/*.err
cat runs/.../Rxxxx/work/*.out

# 3. manifest.toml で投入情報を確認
cat runs/.../Rxxxx/manifest.toml

# 4. 必要に応じて clone して再実行
simctl clone runs/.../Rxxxx --dest runs/retry/
```

## 判断基準

### run が failed のとき
1. `work/*.err` のエラーメッセージを読む
2. メモリ不足 (OOM) → ノード数・タスク数を増やして再投入
3. セグフォ → 入力パラメータの妥当性を確認
4. タイムアウト → wall time を延長して再投入

### パラメータサーベイの設計
- 変数が 2 つ以下なら直積で十分
- 変数が 3 つ以上なら段階的に (まず粗いスキャン → 注目領域を細かく)
- 1 run あたりの実行時間を見積もってから投入数を決める

## ファイル編集の注意

- **編集してよい**: `case.toml`, `survey.toml`, `simulators.toml`, `launchers.toml`
- **編集しない**: `manifest.toml` (simctl コマンド経由で更新), `input/` 内のファイル (不変)
- **参照のみ**: `work/` 内の出力ファイル
"""


def _build_skills_md(project_name: str, simulator_names: list[str]) -> str:
    """Build SKILLS.md content."""
    # Build pip packages section
    pip_pkgs = _collect_pip_packages(simulator_names) if simulator_names else []
    pip_install_line = ""
    if pip_pkgs:
        pkgs_str = " ".join(pip_pkgs)
        pip_install_line = f"uv pip install {pkgs_str}"
    else:
        pip_install_line = "# uv pip install <必要なパッケージ>"

    return f"""\
# SKILLS.md — {project_name}

AI エージェントが実行できるスキル (定型タスク) の一覧。

## /setup-env

プロジェクトの Python 環境をセットアップする。

**前提**: プロジェクトルートで実行すること。

**手順**:

### 1. uv のインストール (未インストールの場合)

```bash
# uv がインストールされていない場合
curl -LsSf https://astral.sh/uv/install.sh | sh
# または
pip install uv
```

### 2. .venv の作成

```bash
# プロジェクトルートに .venv を作成
uv venv
```

### 3. パッケージのインストール

```bash
# simctl 本体のインストール
uv pip install hpc-simctl

# シミュレータ用の解析パッケージ
{pip_install_line}
```

### 4. 確認

```bash
# venv の activate
source .venv/bin/activate

# simctl が使えることを確認
simctl --help

# doctor で環境検査
simctl doctor
```

**注意事項**:
- `.venv/` は `.gitignore` に追加済み
- HPC ノードでは login ノードで環境構築し、compute ノードでは同じ .venv を使う
- `module load` が必要なモジュールは `simulators.toml` の `modules` に定義済み

## /survey-design

パラメータサーベイを設計する。

**入力**: ケース名、変動パラメータ、値の範囲
**出力**: `survey.toml` ファイル

**手順**:
1. 指定されたケースの `case.toml` と入力ファイルを読む
2. パラメータの妥当な範囲を確認する
3. `survey.toml` を生成する (直積展開)
4. 生成される run 数を報告する

## /run-all

サーベイの全 run を生成して投入する。

**入力**: survey ディレクトリパス
**出力**: 全 run が submitted 状態

**手順**:
1. `simctl sweep <survey_dir>` で run 生成
2. `simctl list <survey_dir>` で確認
3. `simctl submit --all <survey_dir>` で投入
4. 投入結果を報告

## /check-status

run やサーベイの状態を確認・同期する。

**入力**: run パスまたはサーベイディレクトリ
**出力**: 状態一覧 (completed / running / failed / submitted)

**手順**:
1. `simctl list <path>` で一覧取得
2. 各 run に対して `simctl sync` で Slurm と同期
3. 状態をサマリーとして報告 (完了数 / 実行中 / 失敗)

## /analyze

完了した run の結果を解析・集計する。

**入力**: run パスまたはサーベイディレクトリ
**出力**: 解析サマリー

**手順**:
1. `simctl summarize <run>` で各 run の要約を生成
2. サーベイの場合は `simctl collect <dir>` で集計
3. 結果の概要と注目すべき傾向を報告

## /debug-failed

失敗した run を診断する。

**入力**: failed 状態の run パス
**出力**: 原因の診断と対処方針

**手順**:
1. `manifest.toml` から投入情報を読む
2. `work/*.err`, `work/*.out` からエラーメッセージを抽出
3. 原因を分類 (OOM / segfault / timeout / input error)
4. 対処方針を提案 (リソース変更 / パラメータ修正 / 再投入)

## /cleanup

完了・不要な run を整理する。

**入力**: 対象ディレクトリ
**出力**: アーカイブ・削除結果

**手順**:
1. `simctl list <dir>` で状態を確認
2. completed な run を `simctl archive` でアーカイブ
3. 必要に応じて `simctl purge-work` で大容量ファイルを削除
4. 整理結果を報告
"""


def init(
    simulators: Annotated[
        Optional[list[str]],
        typer.Argument(help="Simulator names to configure (e.g. emses beach)."),
    ] = None,
    path: Annotated[
        Optional[Path],
        typer.Option("--path", "-p", help="Directory to initialize (defaults to cwd)."),
    ] = None,
    name: Annotated[
        Optional[str],
        typer.Option("--name", "-n", help="Project name (defaults to directory name)."),
    ] = None,
) -> None:
    """Initialize a new simctl project (simproject.toml etc.).

    Optionally specify simulator names to generate default simulators.toml
    entries. Example: simctl init emses beach
    """
    project_dir = (path or Path.cwd()).resolve()

    if not project_dir.exists():
        project_dir.mkdir(parents=True)

    project_name = name or project_dir.name

    created: list[str] = []
    skipped: list[str] = []

    # simproject.toml
    simproject_content = f'[project]\nname = "{project_name}"\ndescription = ""\n'
    if _write_if_missing(project_dir / _SIMPROJECT_FILE, simproject_content):
        created.append(_SIMPROJECT_FILE)
    else:
        skipped.append(_SIMPROJECT_FILE)

    # simulators.toml
    if simulators:
        sim_content = _build_simulators_toml(simulators)
    else:
        sim_content = "[simulators]\n"
    if _write_if_missing(project_dir / _SIMULATORS_FILE, sim_content):
        created.append(_SIMULATORS_FILE)
    else:
        skipped.append(_SIMULATORS_FILE)

    # launchers.toml
    if _write_if_missing(project_dir / _LAUNCHERS_FILE, "[launchers]\n"):
        created.append(_LAUNCHERS_FILE)
    else:
        skipped.append(_LAUNCHERS_FILE)

    # cases/ directory
    if _mkdir_if_missing(project_dir / "cases"):
        created.append("cases/")
    else:
        skipped.append("cases/")

    # runs/ directory
    if _mkdir_if_missing(project_dir / "runs"):
        created.append("runs/")
    else:
        skipped.append("runs/")

    # .gitignore
    if _write_if_missing(project_dir / ".gitignore", _GITIGNORE_CONTENT):
        created.append(".gitignore")
    else:
        skipped.append(".gitignore")

    # CLAUDE.md
    sim_names = simulators or []
    claude_content = _build_claude_md(project_name, sim_names)
    if _write_if_missing(project_dir / _CLAUDE_MD, claude_content):
        created.append(_CLAUDE_MD)
    else:
        skipped.append(_CLAUDE_MD)

    # AGENTS.md
    agents_content = _build_agents_md(project_name, sim_names)
    if _write_if_missing(project_dir / _AGENTS_MD, agents_content):
        created.append(_AGENTS_MD)
    else:
        skipped.append(_AGENTS_MD)

    # SKILLS.md
    skills_content = _build_skills_md(project_name, sim_names)
    if _write_if_missing(project_dir / _SKILLS_MD, skills_content):
        created.append(_SKILLS_MD)
    else:
        skipped.append(_SKILLS_MD)

    # .vscode/settings.json
    vscode_dir = project_dir / _VSCODE_DIR
    vscode_settings = vscode_dir / _VSCODE_SETTINGS
    if vscode_settings.exists():
        skipped.append(f"{_VSCODE_DIR}/{_VSCODE_SETTINGS}")
    else:
        vscode_dir.mkdir(exist_ok=True)
        vscode_settings.write_text(_VSCODE_SETTINGS_CONTENT, encoding="utf-8")
        created.append(f"{_VSCODE_DIR}/{_VSCODE_SETTINGS}")

    # git init
    if (project_dir / ".git").exists():
        skipped.append("git init")
    else:
        result = subprocess.run(
            ["git", "init"],
            cwd=project_dir,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            created.append("git init")
        else:
            typer.echo(f"  Warning: git init failed: {result.stderr.strip()}")

    # Print results
    typer.echo(f"Initialized project '{project_name}' in {project_dir}")
    if created:
        typer.echo("  Created:")
        for item in created:
            typer.echo(f"    {item}")
    if skipped:
        typer.echo("  Skipped (already exist):")
        for item in skipped:
            typer.echo(f"    {item}")


def doctor(
    path: Annotated[
        Optional[Path],
        typer.Argument(help="Project directory to check."),
    ] = None,
) -> None:
    """Check the environment and project configuration for issues."""
    project_dir = (path or Path.cwd()).resolve()
    failures: list[str] = []

    # Check simproject.toml exists and is valid
    simproject_path = project_dir / _SIMPROJECT_FILE
    if not simproject_path.exists():
        typer.echo("[FAIL] simproject.toml not found")
        failures.append(_SIMPROJECT_FILE)
    else:
        try:
            load_project(project_dir)
            typer.echo("[PASS] simproject.toml is valid")
        except ProjectConfigError as e:
            typer.echo(f"[FAIL] simproject.toml: {e}")
            failures.append(_SIMPROJECT_FILE)

    # Check simulators.toml exists
    if (project_dir / _SIMULATORS_FILE).exists():
        typer.echo("[PASS] simulators.toml found")
    else:
        typer.echo("[FAIL] simulators.toml not found")
        failures.append(_SIMULATORS_FILE)

    # Check launchers.toml exists
    if (project_dir / _LAUNCHERS_FILE).exists():
        typer.echo("[PASS] launchers.toml found")
    else:
        typer.echo("[FAIL] launchers.toml not found")
        failures.append(_LAUNCHERS_FILE)

    # Check sbatch availability
    if shutil.which("sbatch") is not None:
        typer.echo("[PASS] sbatch is available")
    else:
        typer.echo("[FAIL] sbatch not found in PATH")
        failures.append("sbatch")

    # Check simulator adapters from simulators.toml
    simulators_path = project_dir / _SIMULATORS_FILE
    if simulators_path.exists():
        try:
            with open(simulators_path, "rb") as f:
                sim_data = tomllib.load(f)
            simulators: dict[str, Any] = sim_data.get("simulators", {})
            if simulators:
                from simctl.adapters.registry import AdapterRegistry

                registry = AdapterRegistry()
                for sim_name, sim_cfg in simulators.items():
                    if not isinstance(sim_cfg, dict):
                        continue
                    adapter_name = sim_cfg.get("adapter", "")
                    if not adapter_name:
                        continue
                    try:
                        registry.load_from_config(
                            {"simulators": {sim_name: sim_cfg}}
                        )
                        typer.echo(
                            f"[PASS] Simulator adapter '{adapter_name}' "
                            f"for '{sim_name}' is importable"
                        )
                    except Exception as e:
                        typer.echo(
                            f"[FAIL] Simulator adapter '{adapter_name}' "
                            f"for '{sim_name}': {e}"
                        )
                        failures.append(f"adapter:{adapter_name}")
        except tomllib.TOMLDecodeError as e:
            typer.echo(f"[FAIL] simulators.toml parse error: {e}")
            failures.append(_SIMULATORS_FILE)

    # Check launcher configs from launchers.toml
    launchers_path = project_dir / _LAUNCHERS_FILE
    if launchers_path.exists():
        try:
            with open(launchers_path, "rb") as f:
                launcher_data = tomllib.load(f)
            launchers: dict[str, Any] = launcher_data.get("launchers", {})
            if launchers:
                from simctl.launchers.base import Launcher, LauncherConfigError

                for lname, lcfg in launchers.items():
                    if not isinstance(lcfg, dict):
                        continue
                    try:
                        Launcher.from_config(lname, lcfg)
                        typer.echo(
                            f"[PASS] Launcher profile '{lname}' is valid"
                        )
                    except LauncherConfigError as e:
                        typer.echo(f"[FAIL] Launcher profile '{lname}': {e}")
                        failures.append(f"launcher:{lname}")
        except tomllib.TOMLDecodeError as e:
            typer.echo(f"[FAIL] launchers.toml parse error: {e}")
            failures.append(_LAUNCHERS_FILE)

    # Check run_id uniqueness
    runs_dir = project_dir / "runs"
    if runs_dir.is_dir():
        try:
            validate_uniqueness(runs_dir)
            typer.echo("[PASS] No duplicate run_ids")
        except DuplicateRunIdError as e:
            typer.echo(f"[FAIL] Duplicate run_id: {e}")
            failures.append("run_id uniqueness")
    else:
        typer.echo("[PASS] No runs/ directory (nothing to check)")

    # Final verdict
    if failures:
        typer.echo(f"\n{len(failures)} check(s) failed.")
        raise typer.Exit(code=1)
    else:
        typer.echo("\nAll checks passed.")
