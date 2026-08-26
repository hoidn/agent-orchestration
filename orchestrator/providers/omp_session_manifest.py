"""Bounded immutable manifests for one OMP session tree."""

from __future__ import annotations

import hashlib
import json
import stat
from dataclasses import dataclass

from orchestrator._common.safe_tree import (
    SafeTreeError,
    read_regular_file,
    walk_regular_files,
)
from orchestrator.providers.omp_launch_fs import PRIMARY_HASH_LIMIT
from orchestrator.providers.omp_session import OmpSessionError

SESSION_MANIFEST_SCHEMA = "omp_session_manifest.v1"
_SESSION_TREE_MAX_FILES = 2048
_SESSION_TREE_MAX_DEPTH = 64
_SESSION_TREE_MAX_BYTES = PRIMARY_HASH_LIMIT


@dataclass(frozen=True, slots=True)
class SessionManifestRow:
    """One session-tree file and its captured content identity."""

    relative_path: str
    size_bytes: int
    sha256: str
    mode: str


@dataclass(frozen=True, slots=True)
class SessionManifest:
    """One canonical manifest plus the immutable bytes it describes."""

    rows: tuple[SessionManifestRow, ...]
    contents: tuple[tuple[str, bytes], ...]
    manifest_bytes: bytes
    manifest_sha256: str


def build_session_manifest(root_fd: int) -> SessionManifest:
    """Capture one bounded no-follow session tree as a stable snapshot."""
    try:
        rows = sorted(
            walk_regular_files(
                root_fd,
                max_depth=_SESSION_TREE_MAX_DEPTH,
                max_entries=_SESSION_TREE_MAX_FILES,
            ),
            key=lambda row: row.relative_path.encode("utf-8"),
        )
        if sum(row.size_bytes for row in rows) > _SESSION_TREE_MAX_BYTES:
            raise OmpSessionError("session tree exceeds the byte bound")
        hardlinked = next((row for row in rows if row.link_count != 1), None)
        if hardlinked is not None:
            raise OmpSessionError(
                f"hard-linked session file: {hardlinked.relative_path!r}"
            )
        contents = tuple(
            (
                row.relative_path,
                read_regular_file(root_fd, row.relative_path, expected=row),
            )
            for row in rows
        )
    except SafeTreeError as exc:
        raise OmpSessionError(str(exc)) from exc
    content_by_path = dict(contents)
    records = tuple(
        SessionManifestRow(
            row.relative_path,
            len(content_by_path[row.relative_path]),
            hashlib.sha256(content_by_path[row.relative_path]).hexdigest(),
            f"{stat.S_IMODE(row.mode):04o}",
        )
        for row in rows
    )
    files = [
        {
            "mode": row.mode,
            "path": row.relative_path,
            "sha256": row.sha256,
            "size": row.size_bytes,
        }
        for row in records
    ]
    manifest_bytes = json.dumps(
        {"schema_version": SESSION_MANIFEST_SCHEMA, "files": files},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return SessionManifest(
        records,
        contents,
        manifest_bytes,
        hashlib.sha256(manifest_bytes).hexdigest(),
    )
