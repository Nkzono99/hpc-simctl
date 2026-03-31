---
name: setup-env
description: Set up or repair the project Python environment. Use when initializing a project or fixing environment issues.
disable-model-invocation: true
---

# プロジェクト環境のセットアップ

## 方法 1: ブートストラップ (新規プロジェクト)

```bash
uvx --from hpc-simctl simctl init
source .venv/bin/activate
simctl doctor
```

## 方法 2: 手動セットアップ (既存プロジェクト)

```bash
uv venv .venv
mkdir -p tools && git clone https://github.com/Nkzono99/hpc-simctl.git tools/hpc-simctl
uv pip install -e ./tools/hpc-simctl
{{ pip_install_line }}
source .venv/bin/activate
simctl doctor
```

## 注意

- `.venv/` と `tools/` は `.gitignore` に追加済み
- HPC ノードでは login ノードで環境構築し、compute ノードでは同じ `.venv` を使う
- `module load` が必要なモジュールは `simulators.toml` の `modules` に定義済み
- simctl 更新: `cd tools/hpc-simctl && git pull`
