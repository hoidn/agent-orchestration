"""Deterministic workspace-delta capture for completed run-reference children."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import difflib
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
from typing import Any

from .contracts import (
    RepositoryRevisionId,
    canonical_json_bytes,
    canonical_sha256,
)
from .workspace import (
    TreeEntry,
    TreeManifest,
    WorkspaceFreezeError,
    freeze_tree,
    manifest_from_entries,
)


MAX_NORMALIZED_DIFF_BYTES = 8 * 1024 * 1024
MAX_NORMALIZED_TEXT_ENTRY_BYTES = 256 * 1024
_EXCLUDED_ROOTS = (".git", ".orchestrate")
_SHA256_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
_READ_CHUNK_SIZE = 1024 * 1024


class RunRefDeltaError(ValueError):
    """The final child workspace cannot produce the closed v1 delta."""

    code = "run_ref_delta_capture_failed"

    def __init__(
        self,
        detail: str,
        *,
        secondary_causes: tuple[str, ...],
    ) -> None:
        super().__init__(detail)
        self.secondary_causes = secondary_causes


@dataclass(frozen=True, slots=True)
class DeclaredArtifact:
    """One child-declared artifact name and clone-relative path."""

    name: str
    path: str

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name or "\0" in self.name:
            raise ValueError("declared artifact name must be non-empty NUL-free text")
        try:
            self.name.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise ValueError("declared artifact name must be UTF-8 text") from exc
        _canonical_relative_path(self.path, label="declared artifact path")


@dataclass(frozen=True, slots=True)
class WorkspaceDeltaCapture:
    """Immutable delta bytes, digest, and the exact final tree they describe."""

    _record_json: bytes
    digest: str
    final_manifest: TreeManifest

    @property
    def record(self) -> dict[str, Any]:
        return json.loads(self._record_json)


def _fail(detail: str, cause: str) -> RunRefDeltaError:
    return RunRefDeltaError(detail, secondary_causes=(cause,))


def _canonical_relative_path(value: object, *, label: str) -> str:
    if not isinstance(value, str) or not value or "\0" in value or "\\" in value:
        raise ValueError(f"{label} must be non-empty canonical relative POSIX text")
    parts = value.split("/")
    if value.startswith("/") or any(part in {"", ".", ".."} for part in parts):
        raise ValueError(f"{label} must be canonical relative POSIX text")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ValueError(f"{label} must be UTF-8 text") from exc
    if PurePosixPath(value).as_posix() != value:
        raise ValueError(f"{label} must be canonical relative POSIX text")
    return value


def _validate_manifest(manifest: object, *, label: str) -> TreeManifest:
    if type(manifest) is not TreeManifest:
        raise _fail(f"{label} must be an exact TreeManifest", "manifest_type_invalid")
    try:
        rebuilt = manifest_from_entries(manifest.entries)
    except (TypeError, ValueError, WorkspaceFreezeError) as exc:
        raise _fail(f"{label} is malformed", "manifest_invalid") from exc
    if rebuilt != manifest:
        raise _fail(f"{label} digest or ordering is invalid", "manifest_invalid")
    return manifest


def _entry_map(manifest: TreeManifest) -> dict[str, TreeEntry]:
    result: dict[str, TreeEntry] = {}
    for entry in manifest.entries:
        try:
            path = _canonical_relative_path(entry.path, label="tree entry path")
        except ValueError as exc:
            raise _fail("tree manifest contains a noncanonical path", "manifest_invalid") from exc
        if path in result:
            raise _fail("tree manifest contains a duplicate path", "manifest_invalid")
        result[path] = entry
    return result


def _base_record(base: RepositoryRevisionId) -> dict[str, str]:
    return {"digest": base.digest, **base.components}


def _entry_delta(
    path: str,
    old: TreeEntry | None,
    new: TreeEntry | None,
) -> dict[str, object]:
    represented = new if new is not None else old
    if represented is None:
        raise AssertionError("workspace entry delta requires one side")
    return {
        "path": path,
        "kind": represented.kind,
        "mode": represented.mode,
        "size": represented.size,
        "old_sha256": None if old is None else old.sha256,
        "new_sha256": None if new is None else new.sha256,
        "link_target": represented.link_target,
    }


def _freeze(root: Path, *, label: str) -> TreeManifest:
    try:
        return freeze_tree(root, excluded_roots=_EXCLUDED_ROOTS)
    except WorkspaceFreezeError as exc:
        cause = f"{label.replace(' ', '_')}_freeze_failed"
        raise _fail(f"cannot freeze {label}", cause) from exc


def _read_manifest_file(root: Path, entry: TreeEntry) -> bytes:
    path = root.joinpath(*PurePosixPath(entry.path).parts)
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise _fail("cannot open a manifest-bound text candidate", "workspace_changed") from exc
    try:
        opened = os.fstat(descriptor)
        if (
            not stat.S_ISREG(opened.st_mode)
            or stat.S_IMODE(opened.st_mode) != entry.mode
            or opened.st_size != entry.size
        ):
            raise _fail("manifest-bound file identity changed", "workspace_changed")
        digest = hashlib.sha256()
        chunks: list[bytes] = []
        size = 0
        while True:
            chunk = os.read(descriptor, _READ_CHUNK_SIZE)
            if not chunk:
                break
            digest.update(chunk)
            chunks.append(chunk)
            size += len(chunk)
        finished = os.fstat(descriptor)
        observed_digest = f"sha256:{digest.hexdigest()}"
        if (
            not stat.S_ISREG(finished.st_mode)
            or stat.S_IMODE(finished.st_mode) != entry.mode
            or finished.st_size != entry.size
            or size != entry.size
            or observed_digest != entry.sha256
        ):
            raise _fail("manifest-bound file content changed", "workspace_changed")
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def _text_content(root: Path, entry: TreeEntry | None) -> str | None:
    if entry is None:
        return ""
    if entry.kind != "file":
        return None
    content = _read_manifest_file(root, entry)
    if b"\0" in content:
        return None
    try:
        return content.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        return None


def _normalized_unified_diff(
    *,
    path: str,
    old_text: str,
    new_text: str,
    old_exists: bool,
    new_exists: bool,
) -> str:
    return "".join(
        difflib.unified_diff(
            old_text.splitlines(keepends=True),
            new_text.splitlines(keepends=True),
            fromfile=f"a/{path}" if old_exists else "/dev/null",
            tofile=f"b/{path}" if new_exists else "/dev/null",
            lineterm="\n",
        )
    )


def _utf8_prefix(text: str, maximum_bytes: int) -> tuple[str, int]:
    encoded = text.encode("utf-8")
    if len(encoded) <= maximum_bytes:
        return text, 0
    prefix = encoded[:maximum_bytes]
    while prefix:
        try:
            rendered = prefix.decode("utf-8", errors="strict")
            return rendered, len(encoded) - len(prefix)
        except UnicodeDecodeError as exc:
            prefix = prefix[: exc.start]
    return "", len(encoded)


def _build_normalized_diff(
    *,
    baseline_root: Path,
    workspace_root: Path,
    baseline_by_path: dict[str, TreeEntry],
    final_by_path: dict[str, TreeEntry],
    changed_paths: tuple[str, ...],
    deleted_paths: tuple[str, ...],
    untracked_paths: tuple[str, ...],
    max_total_bytes: int = MAX_NORMALIZED_DIFF_BYTES,
    max_entry_bytes: int = MAX_NORMALIZED_TEXT_ENTRY_BYTES,
) -> dict[str, Any]:
    if (
        isinstance(max_total_bytes, bool)
        or not isinstance(max_total_bytes, int)
        or max_total_bytes < 0
        or isinstance(max_entry_bytes, bool)
        or not isinstance(max_entry_bytes, int)
        or max_entry_bytes < 0
    ):
        raise ValueError("normalized diff limits must be non-negative integers")
    candidate_paths = tuple(
        sorted(
            (*changed_paths, *deleted_paths, *untracked_paths),
            key=lambda value: value.encode("utf-8"),
        )
    )
    entries: list[dict[str, object]] = []
    represented_bytes = 0
    omitted_bytes = 0
    omitted_entries = 0
    for path in candidate_paths:
        old = baseline_by_path.get(path)
        new = final_by_path.get(path)
        old_text = _text_content(baseline_root, old)
        new_text = _text_content(workspace_root, new)
        if old_text is None or new_text is None:
            continue
        text = _normalized_unified_diff(
            path=path,
            old_text=old_text,
            new_text=new_text,
            old_exists=old is not None,
            new_exists=new is not None,
        )
        if not text:
            continue
        encoded_size = len(text.encode("utf-8"))
        remaining = max(0, max_total_bytes - represented_bytes)
        allowed = min(max_entry_bytes, remaining)
        rendered, omitted = _utf8_prefix(text, allowed)
        if not rendered:
            omitted_bytes += encoded_size
            omitted_entries += 1
            continue
        rendered_size = len(rendered.encode("utf-8"))
        represented_bytes += rendered_size
        omitted_bytes += omitted
        entries.append(
            {
                "path": path,
                "text": rendered,
                "truncated": omitted > 0,
                "omitted_bytes": omitted,
            }
        )
    catalog = {
        "changed_files": [
            _entry_delta(path, baseline_by_path[path], final_by_path[path])
            for path in changed_paths
        ],
        "deleted_files": [
            _entry_delta(path, baseline_by_path[path], None)
            for path in deleted_paths
        ],
        "untracked_files": [
            _entry_delta(path, None, final_by_path[path])
            for path in untracked_paths
        ],
    }
    return {
        "entries": entries,
        "catalog_digest": canonical_sha256(catalog),
        "truncated": omitted_bytes > 0 or omitted_entries > 0,
        "omitted_bytes": omitted_bytes,
        "omitted_entries": omitted_entries,
    }


def _declared_artifact_rows(
    declared_artifacts: tuple[DeclaredArtifact, ...],
    final_by_path: dict[str, TreeEntry],
) -> list[dict[str, object]]:
    if not isinstance(declared_artifacts, tuple) or any(
        type(artifact) is not DeclaredArtifact for artifact in declared_artifacts
    ):
        raise _fail(
            "declared artifacts must be an exact tuple of DeclaredArtifact values",
            "declared_artifacts_invalid",
        )
    seen_names: set[str] = set()
    seen_paths: set[str] = set()
    rows: list[dict[str, object]] = []
    for artifact in sorted(
        declared_artifacts,
        key=lambda item: (item.name.encode("utf-8"), item.path.encode("utf-8")),
    ):
        if artifact.name in seen_names or artifact.path in seen_paths:
            raise _fail(
                "declared artifact names and paths must be unique",
                "declared_artifact_ambiguous",
            )
        seen_names.add(artifact.name)
        seen_paths.add(artifact.path)
        if artifact.path.split("/", 1)[0] in _EXCLUDED_ROOTS:
            raise _fail(
                "declared artifact uses a runtime-owned root",
                "declared_artifact_path_invalid",
            )
        entry = final_by_path.get(artifact.path)
        if entry is None:
            raise _fail(
                "declared artifact is absent from the final tree",
                "declared_artifact_missing",
            )
        rows.append(
            {
                "name": artifact.name,
                "path": entry.path,
                "kind": entry.kind,
                "mode": entry.mode,
                "size": entry.size,
                "sha256": entry.sha256,
                "link_target": entry.link_target,
            }
        )
    return rows


def build_workspace_delta(
    *,
    base: RepositoryRevisionId,
    baseline_root: Path,
    baseline_manifest: TreeManifest,
    workspace_root: Path,
    declared_artifacts: tuple[DeclaredArtifact, ...] = (),
) -> WorkspaceDeltaCapture:
    """Capture one exact post-setup-baseline to completed-workspace delta."""

    if type(base) is not RepositoryRevisionId:
        raise TypeError("workspace delta requires exact RepositoryRevisionId authority")
    baseline_manifest = _validate_manifest(
        baseline_manifest,
        label="post-setup baseline manifest",
    )
    baseline_root = Path(baseline_root)
    workspace_root = Path(workspace_root)
    observed_baseline = _freeze(baseline_root, label="baseline snapshot")
    if observed_baseline != baseline_manifest:
        raise _fail(
            "baseline snapshot does not match its bound manifest",
            "baseline_snapshot_mismatch",
        )
    final_manifest = _freeze(workspace_root, label="final workspace")
    baseline_by_path = _entry_map(baseline_manifest)
    final_by_path = _entry_map(final_manifest)
    all_paths = set(baseline_by_path) | set(final_by_path)
    changed_paths = tuple(
        sorted(
            (
                path
                for path in all_paths
                if path in baseline_by_path
                and path in final_by_path
                and baseline_by_path[path] != final_by_path[path]
            ),
            key=lambda value: value.encode("utf-8"),
        )
    )
    deleted_paths = tuple(
        sorted(
            set(baseline_by_path).difference(final_by_path),
            key=lambda value: value.encode("utf-8"),
        )
    )
    untracked_paths = tuple(
        sorted(
            set(final_by_path).difference(baseline_by_path),
            key=lambda value: value.encode("utf-8"),
        )
    )
    changed_rows = [
        _entry_delta(path, baseline_by_path[path], final_by_path[path])
        for path in changed_paths
    ]
    deleted_rows = [
        _entry_delta(path, baseline_by_path[path], None)
        for path in deleted_paths
    ]
    untracked_rows = [
        _entry_delta(path, None, final_by_path[path])
        for path in untracked_paths
    ]
    normalized_diff = _build_normalized_diff(
        baseline_root=baseline_root,
        workspace_root=workspace_root,
        baseline_by_path=baseline_by_path,
        final_by_path=final_by_path,
        changed_paths=changed_paths,
        deleted_paths=deleted_paths,
        untracked_paths=untracked_paths,
    )
    declared_rows = _declared_artifact_rows(declared_artifacts, final_by_path)
    if _freeze(baseline_root, label="baseline snapshot") != baseline_manifest:
        raise _fail("baseline snapshot changed during delta capture", "workspace_changed")
    if _freeze(workspace_root, label="final workspace") != final_manifest:
        raise _fail("final workspace changed during delta capture", "workspace_changed")
    record = {
        "base": _base_record(base),
        "changed_files": changed_rows,
        "deleted_files": deleted_rows,
        "untracked_files": untracked_rows,
        "normalized_diff": normalized_diff,
        "declared_artifacts": declared_rows,
    }
    record_json = canonical_json_bytes(record)
    return WorkspaceDeltaCapture(
        _record_json=record_json,
        digest=canonical_sha256(record),
        final_manifest=final_manifest,
    )


def validate_workspace_delta(
    record: Mapping[str, object],
    *,
    expected_digest: str,
    base: RepositoryRevisionId,
    baseline_root: Path,
    baseline_manifest: TreeManifest,
    workspace_root: Path,
    declared_artifacts: tuple[DeclaredArtifact, ...] = (),
) -> TreeManifest:
    """Rebuild and validate an exact persisted delta against both bound roots."""

    if not isinstance(record, Mapping):
        raise _fail("workspace delta record must be a mapping", "delta_record_invalid")
    if not isinstance(expected_digest, str) or _SHA256_RE.fullmatch(expected_digest) is None:
        raise _fail("workspace delta digest is malformed", "delta_digest_invalid")
    try:
        observed_digest = canonical_sha256(record)
        record_json = canonical_json_bytes(record)
    except (TypeError, ValueError) as exc:
        raise _fail("workspace delta record is not canonical JSON", "delta_record_invalid") from exc
    if observed_digest != expected_digest:
        raise _fail("workspace delta digest does not match its record", "delta_digest_mismatch")
    rebuilt = build_workspace_delta(
        base=base,
        baseline_root=baseline_root,
        baseline_manifest=baseline_manifest,
        workspace_root=workspace_root,
        declared_artifacts=declared_artifacts,
    )
    if record_json != rebuilt._record_json:
        raise _fail(
            "workspace delta record does not match the bound roots",
            "delta_record_mismatch",
        )
    if expected_digest != rebuilt.digest:
        raise _fail(
            "workspace delta digest does not match the bound roots",
            "delta_digest_mismatch",
        )
    return rebuilt.final_manifest


__all__ = [
    "DeclaredArtifact",
    "MAX_NORMALIZED_DIFF_BYTES",
    "MAX_NORMALIZED_TEXT_ENTRY_BYTES",
    "RunRefDeltaError",
    "WorkspaceDeltaCapture",
    "build_workspace_delta",
    "validate_workspace_delta",
]
