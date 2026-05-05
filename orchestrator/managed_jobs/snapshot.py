"""Immutable snapshot helpers for managed-job execution."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any


def file_sha256(path: Path) -> str:
    """Hash one file as a hex SHA-256 digest."""

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_relpath(value: str) -> Path:
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"snapshot path must be workspace-relative: {value}")
    return path


def _copy_root(workspace: Path, snapshot_workspace: Path, root: str) -> dict[str, str]:
    relroot = _safe_relpath(root)
    source = workspace / relroot
    hashes: dict[str, str] = {}
    if not source.exists():
        return hashes
    if source.is_file():
        target = snapshot_workspace / relroot
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        hashes[relroot.as_posix()] = file_sha256(source)
        return hashes

    for path in sorted(item for item in source.rglob("*") if item.is_file()):
        relpath = path.relative_to(workspace)
        target = snapshot_workspace / relpath
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
        hashes[relpath.as_posix()] = file_sha256(path)
    return hashes


def _hash_globs(workspace: Path, patterns: tuple[str, ...]) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for pattern in patterns:
        _safe_relpath(pattern)
        for path in sorted(item for item in workspace.glob(pattern) if item.is_file()):
            relpath = path.relative_to(workspace).as_posix()
            hashes[relpath] = file_sha256(path)
    return hashes


def materialize_snapshot(
    *,
    workspace: Path,
    snapshot_root: Path,
    roots: tuple[str, ...],
    config_globs: tuple[str, ...] = (),
) -> dict[str, Any]:
    """Copy declared roots into a snapshot workspace and write a manifest."""

    workspace = workspace.resolve()
    snapshot_workspace = snapshot_root / "workspace"
    snapshot_workspace.mkdir(parents=True, exist_ok=True)

    inputs: dict[str, str] = {}
    for root in roots:
        inputs.update(_copy_root(workspace, snapshot_workspace, root))
    configs = _hash_globs(workspace, config_globs)
    manifest_path = snapshot_root / "manifest.json"
    manifest = {
        "snapshot_workspace": str(snapshot_workspace),
        "inputs": dict(sorted(inputs.items())),
        "configs": dict(sorted(configs.items())),
        "manifest_path": str(manifest_path),
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest
