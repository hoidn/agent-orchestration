"""Baseline snapshot and candidate workspace copy helpers."""

from __future__ import annotations

import json
import os
import shutil
from dataclasses import asdict
from pathlib import Path
from typing import Any, Mapping, Sequence

from .models import (
    BASELINE_COPY_POLICY,
    LOCAL_SECRET_DENYLIST,
    BaselineExcludedPathError,
    BaselineManifest,
    ManifestEntry,
    PathSurface,
    _EXCLUDED_ROOT_NAMES,
    _SECRET_DIR_SUFFIXES,
    _SECRET_FILE_NAMES,
    _SECRET_FILE_SUFFIXES,
)
from .utils import (
    _atomic_write_text,
    _canonical_json,
    _hash_file,
    _is_within,
    _join_rel,
    _jsonable,
    _matching_exclusion,
    _relative_posix,
    _safe_relpath,
    _stable_hash,
)

def create_baseline_snapshot(
    *,
    parent_workspace: Path,
    run_root: Path,
    visit_paths: AdjudicationVisitPaths,
    workflow_checksum: str,
    resolved_consumes: Mapping[str, Any],
    required_path_surfaces: Sequence[PathSurface],
    optional_path_surfaces: Sequence[PathSurface],
) -> BaselineManifest:
    del run_root
    parent_workspace = parent_workspace.resolve()
    baseline_workspace = visit_paths.baseline_workspace
    if baseline_workspace.exists():
        shutil.rmtree(baseline_workspace)
    baseline_workspace.mkdir(parents=True, exist_ok=True)

    included: list[ManifestEntry] = []
    excluded: list[ManifestEntry] = []
    _copy_baseline_tree(parent_workspace, baseline_workspace, included, excluded)
    included.sort(key=lambda entry: entry.path)
    excluded.sort(key=lambda entry: entry.path)

    null_path_results = _build_null_path_results(
        parent_workspace=parent_workspace,
        baseline_workspace=baseline_workspace,
        included=included,
        excluded=excluded,
        required_path_surfaces=required_path_surfaces,
        optional_path_surfaces=optional_path_surfaces,
    )
    manifest_payload = {
        "copy_policy": BASELINE_COPY_POLICY,
        "local_secret_denylist": LOCAL_SECRET_DENYLIST,
        "workflow_checksum": workflow_checksum,
        "parent_workspace": parent_workspace.as_posix(),
        "baseline_workspace": baseline_workspace.as_posix(),
        "resolved_consumes": _jsonable(resolved_consumes),
        "included": [asdict(entry) for entry in included],
        "excluded": [asdict(entry) for entry in excluded],
        "null_path_results": null_path_results,
    }
    digest = _stable_hash(manifest_payload)
    manifest_payload["baseline_digest"] = digest
    visit_paths.baseline_manifest_path.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write_text(visit_paths.baseline_manifest_path, _canonical_json(manifest_payload) + "\n")
    return BaselineManifest(
        copy_policy=BASELINE_COPY_POLICY,
        local_secret_denylist=LOCAL_SECRET_DENYLIST,
        workflow_checksum=workflow_checksum,
        parent_workspace=parent_workspace.as_posix(),
        baseline_workspace=baseline_workspace.as_posix(),
        resolved_consumes=dict(resolved_consumes),
        included=tuple(included),
        excluded=tuple(excluded),
        null_path_results=null_path_results,
        baseline_digest=digest,
    )


def load_baseline_manifest(path: Path) -> BaselineManifest:
    document = json.loads(path.read_text(encoding="utf-8"))
    return BaselineManifest(
        copy_policy=document["copy_policy"],
        local_secret_denylist=document["local_secret_denylist"],
        workflow_checksum=document["workflow_checksum"],
        parent_workspace=document["parent_workspace"],
        baseline_workspace=document["baseline_workspace"],
        resolved_consumes=document.get("resolved_consumes", {}),
        included=tuple(ManifestEntry(**entry) for entry in document.get("included", [])),
        excluded=tuple(ManifestEntry(**entry) for entry in document.get("excluded", [])),
        null_path_results=document.get("null_path_results", {}),
        baseline_digest=document["baseline_digest"],
    )

def prepare_candidate_workspace_from_baseline(
    *,
    baseline_workspace: Path,
    candidate_workspace: Path,
) -> None:
    if candidate_workspace.exists():
        shutil.rmtree(candidate_workspace)
    candidate_workspace.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(baseline_workspace, candidate_workspace, symlinks=True)

def _copy_baseline_tree(
    source_root: Path,
    dest_root: Path,
    included: list[ManifestEntry],
    excluded: list[ManifestEntry],
) -> None:
    for root, dir_names, file_names in os.walk(source_root, topdown=True, followlinks=False):
        root_path = Path(root)
        rel_root = _relative_posix(root_path, source_root)
        kept_dirs: list[str] = []
        for dir_name in sorted(dir_names):
            rel = _join_rel(rel_root, dir_name)
            reason = _exclude_reason(Path(rel), is_dir=True)
            full_path = root_path / dir_name
            if reason is not None:
                excluded.append(ManifestEntry(path=rel, entry_type="directory", reason=reason))
                continue
            if full_path.is_symlink():
                entry = _copy_symlink(
                    full_path,
                    dest_root / rel,
                    rel,
                    source_root,
                    included,
                    excluded,
                )
                if entry:
                    kept_dirs.append(dir_name)
                continue
            (dest_root / rel).mkdir(parents=True, exist_ok=True)
            stat = full_path.stat()
            included.append(
                ManifestEntry(
                    path=rel,
                    entry_type="directory",
                    mode=stat.st_mode & 0o777,
                )
            )
            kept_dirs.append(dir_name)
        dir_names[:] = kept_dirs

        for file_name in sorted(file_names):
            rel = _join_rel(rel_root, file_name)
            source = root_path / file_name
            reason = _exclude_reason(Path(rel), is_dir=False)
            if reason is not None:
                excluded.append(ManifestEntry(path=rel, entry_type="file", reason=reason))
                continue
            if source.is_symlink():
                _copy_symlink(source, dest_root / rel, rel, source_root, included, excluded)
                continue
            dest = dest_root / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, dest)
            stat = source.stat()
            included.append(
                ManifestEntry(
                    path=rel,
                    entry_type="file",
                    size=stat.st_size,
                    sha256=_hash_file(source),
                    mode=stat.st_mode & 0o777,
                )
            )


def _copy_symlink(
    source: Path,
    dest: Path,
    rel: str,
    source_root: Path,
    included: list[ManifestEntry],
    excluded: list[ManifestEntry],
) -> bool:
    link_text = os.readlink(source)
    target_path = Path(link_text)
    if target_path.is_absolute():
        excluded.append(ManifestEntry(path=rel, entry_type="symlink", reason="absolute_symlink", link_text=link_text))
        return False
    resolved = (source.parent / target_path).resolve()
    if not _is_within(resolved, source_root):
        excluded.append(ManifestEntry(path=rel, entry_type="symlink", reason="escaping_symlink", link_text=link_text))
        return False
    if not resolved.exists():
        excluded.append(ManifestEntry(path=rel, entry_type="symlink", reason="broken_symlink", link_text=link_text))
        return False
    resolved_rel = resolved.relative_to(source_root)
    reason = _exclude_reason(resolved_rel, is_dir=resolved.is_dir())
    if reason is not None:
        excluded.append(ManifestEntry(path=rel, entry_type="symlink", reason="excluded_target_symlink", link_text=link_text))
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() or dest.is_symlink():
        dest.unlink()
    dest.symlink_to(link_text)
    included.append(
        ManifestEntry(
            path=rel,
            entry_type="symlink",
            link_text=link_text,
            resolved_target=resolved_rel.as_posix(),
        )
    )
    return resolved.is_dir()


def _build_null_path_results(
    *,
    parent_workspace: Path,
    baseline_workspace: Path,
    included: Sequence[ManifestEntry],
    excluded: Sequence[ManifestEntry],
    required_path_surfaces: Sequence[PathSurface],
    optional_path_surfaces: Sequence[PathSurface],
) -> dict[str, Any]:
    included_paths = {entry.path for entry in included}
    excluded_by_path = {entry.path: entry for entry in excluded}
    results: dict[str, Any] = {}
    for required, surfaces in ((True, required_path_surfaces), (False, optional_path_surfaces)):
        for surface in surfaces:
            rel = _safe_relpath(surface.path)
            parent = parent_workspace / rel
            baseline = baseline_workspace / rel
            excluded_entry = _matching_exclusion(rel, excluded_by_path)
            if excluded_entry is not None:
                if required and parent.exists():
                    raise BaselineExcludedPathError(surface.surface, rel, excluded_entry.reason or "excluded")
                state = "excluded"
            elif rel in included_paths or baseline.exists() or baseline.is_symlink():
                state = "included"
            elif parent.exists() or parent.is_symlink():
                state = "missing_from_baseline"
            else:
                state = "absent"
            results[surface.surface] = {
                "path": rel,
                "required": required,
                "state": state,
            }
    return results

def _exclude_reason(relpath: Path, *, is_dir: bool) -> str | None:
    parts = relpath.parts
    if not parts:
        return None
    if any(part in _EXCLUDED_ROOT_NAMES for part in parts):
        return "excluded_root"
    if is_dir and any(part in _SECRET_DIR_SUFFIXES for part in parts):
        return "secret_denylist"
    name = parts[-1]
    if name == ".env":
        return "secret_denylist"
    if name.startswith(".env.") and name not in {".env.example", ".env.sample", ".env.template"}:
        return "secret_denylist"
    if name in _SECRET_FILE_NAMES:
        return "secret_denylist"
    if name in {"config.json"} and len(parts) >= 2 and parts[-2] == ".docker":
        return "secret_denylist"
    if relpath.as_posix().endswith(".config/gcloud"):
        return "secret_denylist"
    if any(name.endswith(suffix) for suffix in _SECRET_FILE_SUFFIXES):
        return "secret_denylist"
    return None
