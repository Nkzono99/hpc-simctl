"""Build a Docker image and render all documentation diagrams inside it."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
IMAGE_NAME = "runops-diagrams"


def _run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True, cwd=REPO_ROOT)


def main() -> None:
    dockerfile = REPO_ROOT / "Dockerfile.diagrams"
    if not dockerfile.is_file():
        raise SystemExit(f"Missing Dockerfile: {dockerfile}")

    _run(
        [
            "docker",
            "build",
            "-t",
            IMAGE_NAME,
            "-f",
            str(dockerfile),
            ".",
        ]
    )

    mount = f"{REPO_ROOT}:/work"
    _run(
        [
            "docker",
            "run",
            "--rm",
            "-v",
            mount,
            "-w",
            "/work",
            IMAGE_NAME,
            "python",
            "scripts/generate_agent_project_flow.py",
        ]
    )
    _run(
        [
            "docker",
            "run",
            "--rm",
            "-v",
            mount,
            "-w",
            "/work",
            IMAGE_NAME,
            "python",
            "scripts/generate_architecture_diagrams.py",
        ]
    )
    print("Rendered docs/ diagrams in Docker.")


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as exc:
        raise SystemExit(exc.returncode) from exc
