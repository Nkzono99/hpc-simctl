"""Publication-facing export helpers for project-side paper integration."""

from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from runops import __version__
from runops.core.analysis import (
    collect_survey_summaries,
    extract_run_figures,
    generate_run_summary,
)
from runops.core.discovery import discover_runs
from runops.core.exceptions import ProvenanceError, SimctlError
from runops.core.manifest import read_manifest
from runops.core.project import find_project_root, load_project
from runops.core.provenance import collect_git_provenance
from runops.core.state import RunState

_EXPORT_MODES = {"copy", "symlink"}


@dataclass(frozen=True)
class PublicationExportFile:
    """One exported artifact inside a publication bundle."""

    role: str
    source_path: Path
    export_path: Path


@dataclass(frozen=True)
class PublicationExportResult:
    """Result of exporting project artifacts for a paper/manuscript."""

    paper_id: str
    export_name: str
    target_kind: str
    target_path: Path
    export_dir: Path
    manifest_path: Path
    readme_path: Path
    mode: str
    source_run_ids: tuple[str, ...]
    files: tuple[PublicationExportFile, ...]
    warnings: tuple[str, ...] = ()


def _slugify(value: str) -> str:
    text = value.strip().lower()
    chars: list[str] = []
    last_dash = False
    for ch in text:
        if ch.isalnum():
            chars.append(ch)
            last_dash = False
            continue
        if (ch in {"-", "_", ".", "/"} or ch.isspace()) and not last_dash:
            chars.append("-")
            last_dash = True
    slug = "".join(chars).strip("-")
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _relative_to_project(project_root: Path, path: Path) -> str:
    return str(path.resolve().relative_to(project_root.resolve())).replace("\\", "/")


def _infer_target_kind(target_path: Path) -> str:
    if (target_path / "manifest.toml").is_file():
        return "run"
    if discover_runs(target_path):
        return "survey"
    raise SimctlError(
        "Export target must be a run directory or a directory containing runs."
    )


def _default_export_name(
    *,
    target_kind: str,
    target_path: Path,
    project_root: Path,
) -> str:
    if target_kind == "run":
        try:
            run_id = str(
                read_manifest(target_path).run.get("id", target_path.name)
            ).strip()
        except SimctlError:
            run_id = target_path.name
        base = _slugify(run_id) or "run"
    else:
        base = _slugify(_relative_to_project(project_root, target_path)) or "survey"
    return f"{target_kind}-{base}-{_utc_timestamp().lower()}"


def _ensure_export_dir(path: Path, *, force: bool) -> None:
    if not path.exists():
        return
    if not force:
        raise SimctlError(
            f"Export already exists: {path}. Use --name to choose another slot "
            "or --force to replace it."
        )
    shutil.rmtree(path)


def _link_or_copy(source_path: Path, dest_path: Path, *, mode: str) -> None:
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    if mode == "copy":
        shutil.copy2(source_path, dest_path)
        return

    if mode != "symlink":
        raise SimctlError(
            f"Unknown export mode: {mode!r}. Use one of: "
            f"{', '.join(sorted(_EXPORT_MODES))}"
        )

    target = os.path.relpath(source_path, start=dest_path.parent)
    dest_path.symlink_to(target)


def _collect_project_git_info(project_root: Path) -> dict[str, Any]:
    try:
        provenance = collect_git_provenance(project_root)
    except ProvenanceError:
        return {}
    return {
        "git_commit": provenance.git_commit,
        "git_dirty": provenance.git_dirty,
    }


def _load_json_summary(path: Path) -> dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise SimctlError(f"Invalid JSON object at {path}")
    return data


def _collect_run_export_sources(
    run_dir: Path,
    *,
    include_figures: bool,
) -> tuple[list[tuple[str, Path]], tuple[str, ...], list[str]]:
    manifest = read_manifest(run_dir)
    run_id = str(manifest.run.get("id", run_dir.name)).strip() or run_dir.name
    warnings: list[str] = []

    summary_path = run_dir / "analysis" / "summary.json"
    if not summary_path.is_file():
        state = str(manifest.run.get("status", "")).strip()
        if state != RunState.COMPLETED.value:
            raise SimctlError(
                f"Run {run_id} has no analysis/summary.json and is not completed."
            )
        generated = generate_run_summary(run_dir)
        summary_path = generated.summary_path
        warnings.extend(generated.warnings)

    files: list[tuple[str, Path]] = [
        ("run_manifest", run_dir / "manifest.toml"),
        ("run_summary", summary_path),
    ]
    if include_figures:
        summary = _load_json_summary(summary_path)
        for figure in extract_run_figures(run_dir, summary):
            figure_path = run_dir / "analysis" / figure["path"]
            if not figure_path.is_file():
                warnings.append(
                    f"{run_id}: missing figure referenced by summary: {figure['path']}"
                )
                continue
            files.append(("run_figure", figure_path))

    return files, (run_id,), warnings


def _collect_survey_export_sources(
    survey_dir: Path,
    *,
    include_figures: bool,
    include_plots: bool,
) -> tuple[list[tuple[str, Path]], tuple[str, ...], list[str]]:
    collection = collect_survey_summaries(survey_dir)
    files: list[tuple[str, Path]] = [
        ("survey_summary_csv", collection.csv_path),
        ("survey_summary_json", collection.json_path),
        ("survey_figures_index", collection.figures_path),
        ("survey_report", collection.report_path),
    ]
    warnings = list(collection.warnings)

    survey_toml = survey_dir / "survey.toml"
    if survey_toml.is_file():
        files.append(("survey_config", survey_toml))

    if include_plots:
        plots_dir = survey_dir / "summary" / "plots"
        if plots_dir.is_dir():
            for path in sorted(plots_dir.rglob("*")):
                if path.is_file():
                    files.append(("survey_plot", path))

    if include_figures:
        for figure in collection.figures:
            path = survey_dir / figure["path"]
            if not path.is_file():
                warnings.append(
                    f"missing figure indexed in figures_index.json: {figure['path']}"
                )
                continue
            files.append(("run_figure", path))

    run_ids: list[str] = []
    for run_dir in discover_runs(survey_dir):
        try:
            run_id = str(read_manifest(run_dir).run.get("id", run_dir.name)).strip()
        except SimctlError:
            run_id = run_dir.name
        if run_id:
            run_ids.append(run_id)

    return files, tuple(sorted(set(run_ids))), warnings


def _write_export_readme(
    path: Path,
    *,
    paper_id: str,
    export_name: str,
    target_kind: str,
    target_relpath: str,
    mode: str,
    run_ids: tuple[str, ...],
    files: tuple[PublicationExportFile, ...],
) -> None:
    lines = [
        "# Publication Export",
        "",
        f"- Paper ID: `{paper_id}`",
        f"- Export name: `{export_name}`",
        f"- Target kind: `{target_kind}`",
        f"- Source target: `{target_relpath}`",
        f"- Export mode: `{mode}`",
        f"- Generated at: `{datetime.now(timezone.utc).isoformat(timespec='seconds')}`",
        "",
        "## Run IDs",
        "",
    ]
    if run_ids:
        for run_id in run_ids:
            lines.append(f"- `{run_id}`")
    else:
        lines.append("- None")

    lines.extend(["", "## Files", ""])
    for item in files:
        export_relpath = str(item.export_path.relative_to(path.parent)).replace(
            "\\",
            "/",
        )
        lines.append(f"- `{item.export_path.name}`: `{export_relpath}`")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def export_publication_bundle(
    target_path: Path,
    *,
    paper_id: str,
    name: str = "",
    mode: str = "copy",
    include_figures: bool = True,
    include_plots: bool = True,
    force: bool = False,
) -> PublicationExportResult:
    """Export publication-facing artifacts for one run or survey-like directory."""
    normalized_mode = mode.strip().lower()
    if normalized_mode not in _EXPORT_MODES:
        raise SimctlError(
            f"Unknown export mode: {mode!r}. Use one of: "
            f"{', '.join(sorted(_EXPORT_MODES))}"
        )

    target_path = target_path.resolve()
    if not target_path.is_dir():
        raise SimctlError(f"Directory not found: {target_path}")

    project_root = find_project_root(target_path)
    project = load_project(project_root)
    target_kind = _infer_target_kind(target_path)

    paper_dir_token = _slugify(paper_id)
    if not paper_dir_token:
        raise SimctlError("Paper ID must contain at least one alphanumeric character.")

    export_name = _slugify(name) if name.strip() else ""
    if not export_name:
        export_name = _default_export_name(
            target_kind=target_kind,
            target_path=target_path,
            project_root=project_root,
        )

    paper_root = project_root / "exports" / "papers" / paper_dir_token
    export_dir = paper_root / export_name
    _ensure_export_dir(export_dir, force=force)
    files_dir = export_dir / "files"

    if target_kind == "run":
        source_entries, run_ids, warnings = _collect_run_export_sources(
            target_path,
            include_figures=include_figures,
        )
    else:
        source_entries, run_ids, warnings = _collect_survey_export_sources(
            target_path,
            include_figures=include_figures,
            include_plots=include_plots,
        )

    exported_files: list[PublicationExportFile] = []
    seen_sources: set[Path] = set()
    for role, source_path in source_entries:
        resolved_source = source_path.resolve()
        if resolved_source in seen_sources:
            continue
        seen_sources.add(resolved_source)
        rel_source = resolved_source.relative_to(project_root)
        dest_path = files_dir / rel_source
        _link_or_copy(resolved_source, dest_path, mode=normalized_mode)
        exported_files.append(
            PublicationExportFile(
                role=role,
                source_path=resolved_source,
                export_path=dest_path,
            )
        )

    manifest_path = export_dir / "manifest.json"
    readme_path = export_dir / "README.md"
    target_relpath = _relative_to_project(project_root, target_path)

    manifest_payload: dict[str, Any] = {
        "schema_version": 1,
        "paper_id": paper_id,
        "paper_dir": paper_dir_token,
        "export_name": export_name,
        "target_kind": target_kind,
        "target_path": target_relpath,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "mode": normalized_mode,
        "project": {
            "name": project.name,
            "root": str(project_root),
            "runops_version": __version__,
            **_collect_project_git_info(project_root),
        },
        "source_run_ids": list(run_ids),
        "files": [
            {
                "role": item.role,
                "source_path": _relative_to_project(project_root, item.source_path),
                "export_path": str(item.export_path.relative_to(export_dir)).replace(
                    "\\",
                    "/",
                ),
            }
            for item in exported_files
        ],
        "warnings": list(warnings),
    }
    export_dir.mkdir(parents=True, exist_ok=True)
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest_payload, f, indent=2)
        f.write("\n")

    _write_export_readme(
        readme_path,
        paper_id=paper_id,
        export_name=export_name,
        target_kind=target_kind,
        target_relpath=target_relpath,
        mode=normalized_mode,
        run_ids=run_ids,
        files=tuple(exported_files),
    )

    return PublicationExportResult(
        paper_id=paper_id,
        export_name=export_name,
        target_kind=target_kind,
        target_path=target_path,
        export_dir=export_dir,
        manifest_path=manifest_path,
        readme_path=readme_path,
        mode=normalized_mode,
        source_run_ids=run_ids,
        files=tuple(exported_files),
        warnings=tuple(warnings),
    )
