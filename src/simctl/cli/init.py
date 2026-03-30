"""CLI commands for project initialization and environment checks."""

from __future__ import annotations

import importlib.resources
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
_CAMPAIGN_FILE = "campaign.toml"
_CLAUDE_MD = "CLAUDE.md"
_AGENTS_MD = "AGENTS.md"
_SKILLS_MD = "SKILLS.md"
_VSCODE_DIR = ".vscode"
_VSCODE_SETTINGS = "settings.json"

_SCHEMA_BASE_URL = "https://raw.githubusercontent.com/Nkzono99/hpc-simctl/main/schemas"
_DEFAULT_SIMCTL_REPO = "https://github.com/Nkzono99/hpc-simctl.git"

_GITIGNORE_CONTENT = """\
# Python venv
.venv/

# simctl tool (cloned by simctl init)
tools/

# Reference repos (cloned by simctl init)
refs/

# Auto-generated knowledge indexes
.simctl/

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
            msg = f"Unknown simulator: '{sim_name}'. Available: {', '.join(available)}"
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


def _collect_doc_repos(simulator_names: list[str]) -> list[tuple[str, str]]:
    """Collect unique doc repos from adapters."""
    from simctl.adapters.registry import get_global_registry

    import simctl.adapters  # noqa: F401

    registry = get_global_registry()
    seen: set[str] = set()
    repos: list[tuple[str, str]] = []
    for sim_name in simulator_names:
        try:
            adapter_cls = registry.get(sim_name)
            for url, dest in adapter_cls.doc_repos():
                if dest not in seen:
                    seen.add(dest)
                    repos.append((url, dest))
        except KeyError:
            pass
    return repos


def _clone_doc_repos(
    project_dir: Path, simulator_names: list[str]
) -> tuple[list[str], list[str]]:
    """Clone documentation repos into project_dir/refs/.

    Returns:
        Tuple of (created_list, skipped_list).
    """
    repos = _collect_doc_repos(simulator_names)
    if not repos:
        return [], []

    created: list[str] = []
    skipped: list[str] = []
    refs_dir = project_dir / "refs"
    refs_dir.mkdir(exist_ok=True)

    for url, dest in repos:
        dest_path = refs_dir / dest
        rel = f"refs/{dest}"
        if dest_path.exists():
            skipped.append(rel)
            continue
        result = subprocess.run(
            ["git", "clone", "--depth", "1", url, str(dest_path)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        if result.returncode == 0:
            created.append(rel)
        else:
            logger.warning("git clone %s failed: %s", url, (result.stderr or "").strip())

    return created, skipped


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


def _build_agent_md(
    doc_name: str,
    project_name: str,
    simulator_names: list[str],
) -> str:
    """Build shared agent instructions for CLAUDE.md / AGENTS.md."""
    sim_section = ""
    if simulator_names:
        guides = _build_simulator_guides(simulator_names)
        sim_section = f"""
## シミュレータ固有知識

{guides}
"""

    # Build refs section
    doc_repos = _collect_doc_repos(simulator_names) if simulator_names else []
    refs_section = ""
    if doc_repos:
        refs_lines = "\n".join(
            f"- **`refs/{dest}/`** — {url}" for url, dest in doc_repos
        )
        refs_section = f"""
## リファレンスリポジトリ

`refs/` 以下にシミュレータのソースコード・ドキュメントを配置している (Git 管理外)。
パラメータの意味や入力ファイル形式を調べる際に参照すること。

{refs_lines}
"""

    return f"""\
# {doc_name} — {project_name}

このプロジェクトは simctl (HPC シミュレーション管理 CLI) で管理されています。
人がベース入力ファイルと計算資源方針を与え、AI エージェントが
campaign 設計、case / survey 編集、run 生成、投入、監視、解析、
知見整理を半自動で進めることを想定しています。

## 運用モード

- 人が主に決めるもの: ベース入力ファイル、計算資源の上限、研究目的、公開してよい知見
- Agent が進めてよいもの:
  `campaign.toml` / `case.toml` / `survey.toml` の編集、run 生成、
  個別 run の投入、状態同期、ログ確認、要約・集計、知見整理
- 確認が必要なもの:
  初回の大規模 survey、`simctl run --all`、資源増加を伴う retry、
  `archive` / `purge-work`、実行バイナリやモジュール設定の変更
- destructive / 高コスト操作には、実行前に理由と想定影響を短く残す

## 最初にやること

1. `simctl context --json` で project / campaign / runs / recent_failures を把握する
2. **simctl の使い方がわからなければ `tools/hpc-simctl/docs/toml-reference.md` を読む**
   - TOML のフォーマットはここに全て書いてある。src/ は読まない
3. `campaign.toml`、関連する `cases/*/case.toml`、
   `runs/**/survey.toml`、`.simctl/facts.toml`、
   必要なら最近の log を読む
4. action の前に plan を JSON で明示する

```json
{{
  "goal": "map stability boundary for dt and nx",
  "edits": [
    "campaign.toml",
    "cases/plasma/case.toml",
    "runs/plasma/stability/survey.toml"
  ],
  "commands": [
    "simctl sweep runs/plasma/stability",
    "simctl run --all runs/plasma/stability"
  ],
  "checkpoints": [
    "Confirm survey size and queue before bulk submit",
    "Review failed logs before retry"
  ]
}}
```

plan にない高コスト操作をいきなり実行しないこと。

## 編集優先順位

1. `campaign.toml` で研究意図、変数、観測量を整理する
2. `cases/*/case.toml` で共通パラメータ、job 設定、分類を管理する
3. `runs/**/survey.toml` で掃引軸を定義する
4. `runs/**/input/*` の直接編集は、adapter で表現できない差分か、
   log を見たうえでの緊急修正に限る

- `runs/**/input/*` を直接直したら、同じ修正を上流の `case.toml` やテンプレートへ戻す
- `manifest.toml` は正本だが手動編集しない
- `work/` と `.simctl/knowledge/` の自動生成物は手で整形しない

## Case / Survey / Run の作り方 (Agent 向けチートシート)

**TOML フォーマットの詳細は `tools/hpc-simctl/docs/toml-reference.md` を参照すること。**
ここでは手順だけを示す。フィールドの意味・省略可否はドキュメントを見ること。

### 新しい Case を作る

1. `cases/<case_name>/` ディレクトリを作る
2. `cases/<case_name>/case.toml` を書く (フォーマットは `tools/hpc-simctl/docs/toml-reference.md` の case.toml セクション参照)
3. シミュレータの入力ファイル (例: `plasma.toml`) を同じディレクトリに置く
   - case ディレクトリ内の全ファイル (`case.toml` を除く) が自動で `input/` にコピーされる

```bash
# 例
mkdir -p cases/my_new_case
# → cases/my_new_case/case.toml を編集
# → cases/my_new_case/plasma.toml を配置
```

### 新しい Survey を作る

1. `runs/` 以下に survey ディレクトリを作る (分類階層は自由)
2. `survey.toml` を書く (フォーマットは `tools/hpc-simctl/docs/toml-reference.md` の survey.toml セクション参照)
3. `simctl sweep <survey_dir>` で run を一括生成する

```bash
# 例
mkdir -p runs/sheath/angle_scan
# → runs/sheath/angle_scan/survey.toml を編集
simctl sweep runs/sheath/angle_scan
# → runs/sheath/angle_scan/R20260330-0001/ 等が自動生成される
```

### 単一 Run を作る

```bash
simctl create <case_name> --dest <path>
# 例: simctl create my_case --dest runs/sheath/test
```

### やってはいけないこと

- `Rxxxx/` ディレクトリを mkdir で作る
- `manifest.toml` を Write で書く
- `Rxxxx/input/` にファイルを直接置く
- `Rxxxx/submit/job.sh` を手書きする
- これらは全て `simctl create` / `simctl sweep` が自動で行う

## 推奨ワークフロー

- Design: `campaign.toml`, `case.toml`, `survey.toml`
  Commands: `simctl context --json`, `simctl config show`,
  `simctl knowledge list`, `simctl knowledge facts`
- Create: `cases/`, `runs/**/survey.toml`
  Commands: `simctl new`, `simctl create`, `simctl sweep`
- Submit: `runs/**/R*/`
  Commands: `simctl run`, `simctl run --all`
- Monitor: `manifest.toml`, `work/*.out`, `work/*.err`
  Commands: `simctl status`, `simctl sync`, `simctl log`,
  `simctl jobs`, `simctl history`, `simctl list`
- Analyze: `analysis/`, survey directory
  Commands: `simctl summarize`, `simctl collect`
- Learn: `.simctl/insights/`, `.simctl/facts.toml`
  Commands: `simctl knowledge save`, `simctl knowledge add-fact`,
  `simctl knowledge sync`

## 失敗時の扱い

- `submitted` / `running` が長く止まって見えるときは、
  まず `simctl sync` で状態を合わせる
- `timeout` / `oom` / `preempted` は retry 候補だが、job 条件の変更理由を plan に書く
- `exit_error` は必ず `simctl log -e` や `work/*.err` を確認してから再試行する
- 同じ run の試行回数が 3 回前後に達したら、自動 retry を止めて原因を要約する
- action registry を使う agent では `retry_run` は再投入そのものではなく、
  `failed -> created` の再準備とみなす

## 知見の記録

- 人向けの考察や途中メモは `simctl knowledge save` で `.simctl/insights/` に保存する
- 機械可読な安定知見は `simctl knowledge add-fact` で `.simctl/facts.toml` に追加する
- `high` confidence は、複数 run の再現か deterministic な確認がある場合だけ使う
- 既存 fact を修正するときは上書きせず、
  新しい fact を追加して `--supersedes fNNN` を使う

## 重要なファイル

- **`manifest.toml`** — run の正本。状態・パラメータ・provenance をすべて記録
- **`campaign.toml`** — 研究意図、仮説、変数、観測量
- **`simproject.toml`** — プロジェクト名・説明
- **`simulators.toml`** — シミュレータの adapter / executable / modules 定義
- **`launchers.toml`** — MPI ランチャーの設定
- **`case.toml`** — ケーステンプレートの定義
- **`survey.toml`** — パラメータサーベイの定義 (直積展開)
- **`tools/hpc-simctl/`** — simctl 本体のソースコード・ドキュメント (Git 管理外)
  - `docs/` — アーキテクチャ、TOML リファレンス等
  - `SPEC.md` — 仕様書
{sim_section}{refs_section}
## 環境構築

`simctl init` がプロジェクトルートに `.venv` と `tools/hpc-simctl/` を自動構築する。
手動セットアップが必要な場合は `SKILLS.md` の `/setup-env` を参照。

```bash
# ブートストラップ (simctl 未インストールでも実行可能)
uvx --from git+https://github.com/Nkzono99/hpc-simctl.git simctl init

# activate して利用開始
source .venv/bin/activate
simctl doctor
```

## 運用ルール

- run ディレクトリ (`Rxxxx/`) が全操作の基点
- `manifest.toml` が正本。手動編集は避け、simctl コマンド経由で更新する
- `work/` の大容量ファイルは Git 管理外 (.gitignore 済み)
- `.venv/` はプロジェクトルートに配置。Git 管理外
- `tools/hpc-simctl/` はプロジェクトルートに配置。Git 管理外
- パラメータ変更は case.toml / survey.toml で管理し、新しい run を生成する
- `refs/` 以下はシミュレータの参考資料。パラメータの意味を調べる際に参照する
- simctl のドキュメント・仕様書は `tools/hpc-simctl/` を参照する
- `.simctl/knowledge/` にナレッジインデックスがある。ドキュメントの所在はここで把握する
- シミュレータ更新時は `simctl update-refs` でリファレンスとナレッジを最新化する

## 絶対禁止事項

### run ディレクトリを手で作らない

run ディレクトリ (`Rxxxx/`) 内のファイル群 (`manifest.toml`, `input/`, `submit/job.sh`) を
**手動で作成・Write してはいけない**。必ず simctl CLI で生成する。

- 単一 run: `simctl create <case_name>` (cwd に run を生成)
- survey 展開: `simctl sweep <survey_dir>` (survey.toml から全 run を一括生成)

Agent が編集してよいのは以下のみ:
- `campaign.toml` / `case.toml` / `survey.toml` — 設計ファイル
- `runs/**/survey.toml` — 掃引軸の定義
- `cases/**/` 内のテンプレート入力ファイル (例: `plasma.toml`)

Agent が自分で書いてはいけないもの:
- `Rxxxx/manifest.toml` — simctl が自動生成・管理する
- `Rxxxx/input/*` — simctl create / sweep が case テンプレートからコピーする
- `Rxxxx/submit/job.sh` — simctl が launcher 設定から自動生成する

**正しい手順**: case.toml / survey.toml を編集 → `simctl sweep` or `simctl create` → run が自動生成される

## simctl の使い方を調べるとき

**ドキュメントを先に読むこと。ソースコードを読みに行かないこと。**

simctl の TOML フォーマット、コマンド体系、設計思想を知りたいときは、
以下の順序で情報源を参照する:

1. **`tools/hpc-simctl/docs/toml-reference.md`** — 全 TOML ファイルのフィールド定義・例
2. **`tools/hpc-simctl/docs/getting-started.md`** — ワークフロー・コマンド例
3. **`tools/hpc-simctl/SPEC.md`** — 仕様の詳細 (設計判断の根拠)
4. **`tools/hpc-simctl/docs/architecture.md`** — 内部設計 (adapter / launcher の仕組み)
5. **`schemas/*.json`** — JSON Schema (TOML の機械可読な定義)
6. **`simctl --help` / `simctl <command> --help`** — コマンドのオプション確認

`tools/hpc-simctl/src/` のソースコードを直接読むのは **最終手段**。
ドキュメントと `--help` で解決しない場合にのみ参照すること。

理由: src/ を読んでも実装の詳細に引きずられて正しい使い方がわからなくなる。
ドキュメントには「何をすべきか」が、ソースコードには「どう実装されているか」しか書かれていない。
"""


def _build_claude_md(project_name: str, simulator_names: list[str]) -> str:
    """Build CLAUDE.md content."""
    return _build_agent_md("CLAUDE.md", project_name, simulator_names)


def _build_agents_md(project_name: str, simulator_names: list[str]) -> str:
    """Build AGENTS.md content."""
    return _build_agent_md("AGENTS.md", project_name, simulator_names)


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
{pip_install_line}
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
4. `.simctl/knowledge/{{simulator}}.md` にナレッジインデックスを再生成
5. 更新サマリーを確認

**ナレッジインデックスの使い方**:
- `.simctl/knowledge/{{simulator}}.md` にドキュメントの所在一覧がある
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
simctl knowledge save mag_scan_summary -t result -s emses \\
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
"""


def _get_data_path() -> Path:
    """Return the path to the package's bundled _data directory.

    Falls back to the repository root when running in editable/dev mode
    where force-include has not been applied.
    """
    pkg_data = Path(str(importlib.resources.files("simctl") / "_data"))
    if (pkg_data / "README.md").is_file():
        return pkg_data
    # Dev mode fallback: walk up from this file to the repo root
    repo_root = Path(__file__).resolve().parent.parent.parent.parent
    if (repo_root / "README.md").is_file() and (repo_root / "docs").is_dir():
        return repo_root
    return pkg_data


def _copy_docs(project_dir: Path) -> tuple[list[str], list[str]]:
    """Copy bundled README.md and docs/ into the project directory.

    Returns:
        Tuple of (created_list, skipped_list).
    """
    created: list[str] = []
    skipped: list[str] = []
    data_path = _get_data_path()

    # README.md -> docs/simctl-guide.md
    readme_src = data_path / "README.md"
    readme_dst = project_dir / "docs" / "simctl-guide.md"
    if readme_dst.exists():
        skipped.append("docs/simctl-guide.md")
    elif readme_src.exists():
        readme_dst.parent.mkdir(exist_ok=True)
        shutil.copy2(readme_src, readme_dst)
        created.append("docs/simctl-guide.md")

    # docs/*.md
    docs_src = data_path / "docs"
    if docs_src.is_dir():
        docs_dst = project_dir / "docs"
        docs_dst.mkdir(exist_ok=True)
        for src_file in sorted(docs_src.iterdir()):
            if src_file.suffix == ".md":
                dst_file = docs_dst / src_file.name
                rel = f"docs/{src_file.name}"
                if dst_file.exists():
                    skipped.append(rel)
                else:
                    shutil.copy2(src_file, dst_file)
                    created.append(rel)

    return created, skipped


def _prompt_simulators() -> tuple[list[str], dict[str, dict[str, Any]]]:
    """Interactively prompt the user to select and configure simulators.

    Returns:
        Tuple of (simulator_names, {name: config_dict}).
    """
    from simctl.adapters.registry import get_global_registry

    import simctl.adapters  # noqa: F401

    registry = get_global_registry()
    available = registry.list_adapters()

    typer.echo("\nAvailable simulators:")
    for i, name in enumerate(available, 1):
        typer.echo(f"  {i}. {name}")

    selection = typer.prompt(
        "\nSelect simulators (comma-separated numbers or names, Enter to skip)",
        default="",
    )

    if not selection.strip():
        return [], {}

    # Parse selection — accept both numbers and names
    selected: list[str] = []
    for token in selection.split(","):
        token = token.strip()
        if not token:
            continue
        if token.isdigit():
            idx = int(token) - 1
            if 0 <= idx < len(available):
                selected.append(available[idx])
            else:
                typer.echo(f"  Warning: ignoring invalid number '{token}'")
        elif token in available:
            selected.append(token)
        else:
            typer.echo(f"  Warning: unknown simulator '{token}', skipping")

    if not selected:
        return [], {}

    # Interactive config for each selected simulator
    use_interactive = typer.confirm("\nCustomize simulator settings?", default=False)

    configs: dict[str, dict[str, Any]] = {}
    for sim_name in selected:
        adapter_cls = registry.get(sim_name)
        if use_interactive:
            configs[sim_name] = adapter_cls.interactive_config()
        else:
            configs[sim_name] = adapter_cls.default_config()

    return selected, configs


_SITE_PROFILES: dict[str, dict[str, Any]] = {
    "cmaphor": {
        "type": "srun",
        "use_slurm_ntasks": True,
        "resource_style": "rsc",
        "modules": [
            "intel/2023.2",
            "intelmpi/2023.2",
            "hdf5/1.12.2_intel-2023.2-impi",
            "fftw/3.3.10_intel-2022.3-impi",
        ],
        "stdout": "stdout.%J.log",
        "stderr": "stderr.%J.log",
    },
}


def _prompt_launchers() -> dict[str, dict[str, Any]]:
    """Interactively prompt for launcher configuration.

    Returns:
        Launcher config dict for launchers.toml.
    """
    typer.echo("\nLauncher configuration:")
    typer.echo("  Site profiles (preconfigured):")
    site_names = list(_SITE_PROFILES.keys())
    for i, sname in enumerate(site_names, start=1):
        typer.echo(f"    {i}. {sname}")
    offset = len(site_names)
    typer.echo("  Launcher types:")
    typer.echo(f"    {offset + 1}. srun (Slurm)")
    typer.echo(f"    {offset + 2}. mpirun (OpenMPI)")
    typer.echo(f"    {offset + 3}. mpiexec (MPICH)")

    selection = typer.prompt(
        "\nSelect site profile or launcher type (number or name, Enter to skip)",
        default="",
    )

    sel = selection.strip()
    if not sel:
        return {}

    # Check site profiles first
    site_map = {str(i): name for i, name in enumerate(site_names, start=1)}
    if sel in site_map:
        profile_name = site_map[sel]
        return {profile_name: dict(_SITE_PROFILES[profile_name])}
    if sel in _SITE_PROFILES:
        return {sel: dict(_SITE_PROFILES[sel])}

    # Launcher types
    launcher_map = {
        str(offset + 1): "srun",
        str(offset + 2): "mpirun",
        str(offset + 3): "mpiexec",
    }
    launcher_type = launcher_map.get(sel, sel)

    if launcher_type not in ("srun", "mpirun", "mpiexec"):
        typer.echo(f"  Unknown selection '{sel}', skipping")
        return {}

    launcher_name = typer.prompt("  Launcher profile name", default=launcher_type)

    config: dict[str, Any] = {"type": launcher_type}

    if launcher_type == "srun":
        use_slurm = typer.confirm(
            "  Use SLURM_NTASKS (rely on #SBATCH --ntasks)?", default=True
        )
        config["use_slurm_ntasks"] = use_slurm
        config["args"] = typer.prompt(
            "  Extra srun arguments (e.g. --mpi=pmix)", default=""
        )
    elif launcher_type in ("mpirun", "mpiexec"):
        config["args"] = typer.prompt(f"  Extra {launcher_type} arguments", default="")

    # Module loading
    modules_str = typer.prompt(
        "  Modules to load (space-separated, Enter to skip)", default=""
    )
    if modules_str.strip():
        config["modules"] = modules_str.strip().split()

    # Clean empty args
    if not config.get("args"):
        config.pop("args", None)

    return {launcher_name: config}


def _build_simulators_toml_from_configs(
    configs: dict[str, dict[str, Any]],
) -> str:
    """Serialize simulator configs to TOML string."""
    full_config: dict[str, Any] = {"simulators": configs}

    if tomli_w is None:
        lines = ["[simulators]", ""]
        for sim_name, sim_cfg in configs.items():
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
    tomli_w.dump(full_config, buf)
    return buf.getvalue().decode("utf-8")


def _build_launchers_toml(launchers: dict[str, dict[str, Any]]) -> str:
    """Serialize launcher configs to TOML string."""
    if not launchers:
        return "[launchers]\n"

    full_config: dict[str, Any] = {"launchers": launchers}

    if tomli_w is None:
        lines = ["[launchers]", ""]
        for name, cfg in launchers.items():
            lines.append(f"[launchers.{name}]")
            for key, value in cfg.items():
                if isinstance(value, list):
                    items = ", ".join(f'"{v}"' for v in value)
                    lines.append(f"{key} = [{items}]")
                elif isinstance(value, str):
                    lines.append(f'{key} = "{value}"')
                elif isinstance(value, bool):
                    lines.append(f"{key} = {str(value).lower()}")
                else:
                    lines.append(f"{key} = {value}")
            lines.append("")
        return "\n".join(lines) + "\n"

    import io

    buf = io.BytesIO()
    tomli_w.dump(full_config, buf)
    return buf.getvalue().decode("utf-8")


def _build_campaign_toml(project_name: str, simulator_names: list[str]) -> str:
    """Build a minimal campaign.toml skeleton."""
    lines = [
        f"#:schema {_SCHEMA_BASE_URL}/campaign.json",
        "[campaign]",
        f'name = "{project_name}"',
        'description = ""',
        'hypothesis = ""',
    ]
    if simulator_names:
        lines.append(f'simulator = "{simulator_names[0]}"')
    lines.extend([
        "",
        "[variables]",
        "",
        "[observables]",
        "",
    ])
    return "\n".join(lines)


def _venv_pip_executable(venv_dir: Path) -> Path:
    """Return the pip executable path inside a virtual environment."""
    if sys.platform == "win32":
        return venv_dir / "Scripts" / "pip.exe"
    return venv_dir / "bin" / "pip"


def _find_uv() -> str:
    """Find the uv executable, falling back to 'uv'."""
    uv_path = shutil.which("uv")
    return uv_path if uv_path else "uv"


def _bootstrap_environment(
    project_dir: Path,
    sim_names: list[str],
    simctl_repo: str,
    created: list[str],
    skipped: list[str],
) -> None:
    """Bootstrap .venv, clone hpc-simctl into tools/, and editable-install.

    Args:
        project_dir: Project root directory.
        sim_names: List of simulator names for pip packages.
        simctl_repo: Git URL for hpc-simctl repository.
        created: Mutable list to append created items.
        skipped: Mutable list to append skipped items.
    """
    uv = _find_uv()
    venv_dir = project_dir / ".venv"
    tools_dir = project_dir / "tools"
    simctl_dir = tools_dir / "hpc-simctl"

    # 1. Create .venv via uv
    if venv_dir.exists():
        skipped.append(".venv")
    else:
        typer.echo("  Creating .venv ...")
        venv_result = subprocess.run(
            [uv, "venv", str(venv_dir)],
            cwd=str(project_dir),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        if venv_result.returncode == 0:
            created.append(".venv")
        else:
            typer.echo(
                f"  Warning: uv venv failed: {(venv_result.stderr or '').strip()}"
            )
            return

    # 2. Clone hpc-simctl into tools/
    if simctl_dir.exists():
        skipped.append("tools/hpc-simctl")
    else:
        typer.echo("  Cloning hpc-simctl into tools/ ...")
        tools_dir.mkdir(exist_ok=True)
        clone_result = subprocess.run(
            ["git", "clone", simctl_repo, str(simctl_dir)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        if clone_result.returncode == 0:
            created.append("tools/hpc-simctl")
        else:
            typer.echo(
                f"  Warning: git clone failed: "
                f"{(clone_result.stderr or '').strip()[:300]}"
            )
            return

    # 3. Editable install simctl into .venv
    typer.echo("  Installing hpc-simctl (editable) ...")
    install_result = subprocess.run(
        [uv, "pip", "install", "-e", str(simctl_dir),
         "--python", str(venv_dir / ("Scripts/python.exe"
                                     if sys.platform == "win32"
                                     else "bin/python"))],
        cwd=str(project_dir),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if install_result.returncode == 0:
        created.append("uv pip install -e tools/hpc-simctl")
    else:
        typer.echo(
            f"  Warning: editable install failed:\n"
            f"    {(install_result.stderr or '').strip()[:300]}"
        )

    # 4. Install simulator-specific packages
    pip_pkgs = _collect_pip_packages(sim_names) if sim_names else []
    if pip_pkgs:
        typer.echo(f"  Installing: {', '.join(pip_pkgs)} ...")
        pkg_result = subprocess.run(
            [uv, "pip", "install", *pip_pkgs,
             "--python", str(venv_dir / ("Scripts/python.exe"
                                         if sys.platform == "win32"
                                         else "bin/python"))],
            cwd=str(project_dir),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        if pkg_result.returncode == 0:
            created.append(f"pip install ({len(pip_pkgs)} packages)")
        else:
            typer.echo(
                f"  Warning: pip install failed:\n"
                f"    {(pkg_result.stderr or '').strip()[:300]}"
            )

    # 5. Activation hint
    if sys.platform == "win32":
        activate_cmd = r".venv\Scripts\activate"
    else:
        activate_cmd = "source .venv/bin/activate"
    typer.echo(f"\n  Next: {activate_cmd}")
    typer.echo("  Then: simctl doctor")


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
    yes: Annotated[
        bool,
        typer.Option("--yes", "-y", help="Skip interactive prompts, use defaults."),
    ] = False,
    simctl_repo: Annotated[
        str,
        typer.Option(
            "--simctl-repo",
            help="Git URL for hpc-simctl repository.",
        ),
    ] = _DEFAULT_SIMCTL_REPO,
) -> None:
    """Initialize a new simctl project (simproject.toml etc.).

    By default, runs in interactive mode with guided prompts.
    Use --yes / -y to skip prompts and use defaults.

    Simulator names can also be passed directly:
      simctl init emses beach

    Bootstrap usage (no prior install needed):
      uvx --from git+https://github.com/Nkzono99/hpc-simctl.git simctl init
    """
    interactive = not yes
    project_dir = (path or Path.cwd()).resolve()

    if not project_dir.exists():
        project_dir.mkdir(parents=True)

    # Interactive project name
    if interactive and not name:
        project_name = typer.prompt("Project name", default=project_dir.name)
    else:
        project_name = name or project_dir.name

    created: list[str] = []
    skipped: list[str] = []

    # simproject.toml
    simproject_content = (
        f"#:schema {_SCHEMA_BASE_URL}/simproject.json\n"
        f'[project]\nname = "{project_name}"\ndescription = ""\n'
    )
    if _write_if_missing(project_dir / _SIMPROJECT_FILE, simproject_content):
        created.append(_SIMPROJECT_FILE)
    else:
        skipped.append(_SIMPROJECT_FILE)

    # simulators.toml
    sim_configs: dict[str, dict[str, Any]] = {}
    sim_names: list[str] = []

    if simulators:
        sim_names = simulators
        sim_content = _build_simulators_toml(simulators)
    elif interactive:
        sim_names, sim_configs = _prompt_simulators()
        if sim_configs:
            sim_content = _build_simulators_toml_from_configs(sim_configs)
        else:
            sim_content = "[simulators]\n"
    else:
        sim_content = "[simulators]\n"

    sim_schema = f"#:schema {_SCHEMA_BASE_URL}/simulators.json\n"
    sim_content = sim_schema + sim_content
    if _write_if_missing(project_dir / _SIMULATORS_FILE, sim_content):
        created.append(_SIMULATORS_FILE)
    else:
        skipped.append(_SIMULATORS_FILE)

    # launchers.toml
    if interactive:
        launcher_configs = _prompt_launchers()
        launcher_content = _build_launchers_toml(launcher_configs)
    else:
        # Default to srun with use_slurm_ntasks
        launcher_configs = {
            "srun": {"type": "srun", "use_slurm_ntasks": True},
        }
        launcher_content = _build_launchers_toml(launcher_configs)

    launcher_schema = f"#:schema {_SCHEMA_BASE_URL}/launchers.json\n"
    launcher_content = launcher_schema + launcher_content
    if _write_if_missing(project_dir / _LAUNCHERS_FILE, launcher_content):
        created.append(_LAUNCHERS_FILE)
    else:
        skipped.append(_LAUNCHERS_FILE)

    # campaign.toml
    campaign_content = _build_campaign_toml(project_name, sim_names)
    if _write_if_missing(project_dir / _CAMPAIGN_FILE, campaign_content):
        created.append(_CAMPAIGN_FILE)
    else:
        skipped.append(_CAMPAIGN_FILE)

    # cases/ directory (with per-simulator subdirectories)
    if _mkdir_if_missing(project_dir / "cases"):
        created.append("cases/")
    else:
        skipped.append("cases/")
    for sim in sim_names:
        sim_cases_dir = project_dir / "cases" / sim
        if _mkdir_if_missing(sim_cases_dir):
            created.append(f"cases/{sim}/")

    # runs/ directory
    if _mkdir_if_missing(project_dir / "runs"):
        created.append("runs/")
    else:
        skipped.append("runs/")

    # refs/ — clone simulator doc repos
    if sim_names:
        refs_created, refs_skipped = _clone_doc_repos(project_dir, sim_names)
        created.extend(refs_created)
        skipped.extend(refs_skipped)

    # .gitignore
    if _write_if_missing(project_dir / ".gitignore", _GITIGNORE_CONTENT):
        created.append(".gitignore")
    else:
        skipped.append(".gitignore")

    # CLAUDE.md (use sim_names from earlier — may come from args or interactive)
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
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        if result.returncode == 0:
            created.append("git init")
        else:
            typer.echo(f"  Warning: git init failed: {(result.stderr or '').strip()}")

    # Bootstrap: .venv + tools/hpc-simctl + editable install
    _bootstrap_environment(project_dir, sim_names, simctl_repo, created, skipped)

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
                        registry.load_from_config({"simulators": {sim_name: sim_cfg}})
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
                        typer.echo(f"[PASS] Launcher profile '{lname}' is valid")
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

    # Environment detection
    typer.echo("\n--- Environment ---")
    try:
        from simctl.core.environment import (
            detect_environment,
            load_environment,
            save_environment,
        )

        existing = load_environment(project_dir)
        if existing:
            typer.echo(
                f"[PASS] environment.toml found "
                f"(cluster: {existing.cluster_name})"
            )
            if existing.partitions:
                for p in existing.partitions:
                    default_mark = " (default)" if p.default else ""
                    typer.echo(
                        f"       partition: {p.name}{default_mark}"
                    )
        else:
            typer.echo("[INFO] Detecting environment...")
            env_info = detect_environment()
            if env_info.partitions:
                typer.echo(
                    f"       Detected {len(env_info.partitions)} "
                    f"Slurm partition(s)"
                )
            try:
                env_path = save_environment(project_dir, env_info)
                typer.echo(
                    f"[PASS] Saved environment to "
                    f"{env_path.relative_to(project_dir)}"
                )
            except RuntimeError:
                typer.echo(
                    "[WARN] Could not save environment.toml "
                    "(tomli_w not installed)"
                )
    except Exception as e:
        typer.echo(f"[WARN] Environment detection failed: {e}")

    # Campaign check
    campaign_file = project_dir / "campaign.toml"
    if campaign_file.is_file():
        try:
            from simctl.core.campaign import load_campaign

            campaign = load_campaign(project_dir)
            if campaign:
                typer.echo(
                    f"[PASS] campaign.toml: {campaign.name}"
                )
        except Exception as e:
            typer.echo(f"[FAIL] campaign.toml: {e}")
            failures.append("campaign.toml")
    else:
        typer.echo("[INFO] No campaign.toml (optional)")

    # Final verdict
    if failures:
        typer.echo(f"\n{len(failures)} check(s) failed.")
        raise typer.Exit(code=1)
    else:
        typer.echo("\nAll checks passed.")
