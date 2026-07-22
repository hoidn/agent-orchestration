"""Closed, queue-neutral source and workspace bindings for retirement work.

The functions in this module deliberately use Git's NUL-delimited plumbing and
``lstat``/``O_NOFOLLOW`` snapshots.  A porcelain status code is only a locator;
the byte, type, mode, symlink-target, and index bindings are the authority.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import itertools
import json
import os
import re
import stat
import subprocess
import tarfile
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping, Sequence

from .safe_io import (
    AtomicPublishError,
    bind_logical_parent,
    capture_regular_file_at,
    conditional_publish_file_at,
    logical_parent_matches,
)


_SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_HEX40_RE = re.compile(r"^[0-9a-f]{40}$")
_WORKSPACE_KEYS = {
    "schema_version",
    "captured_at",
    "head",
    "index_sha256",
    "index_entries",
    "index_entry_count",
    "index_entry_set_sha256",
    "status_rows",
    "dirty_entries",
    "dirty_entry_count",
    "dirty_path_set_sha256",
    "dirty_entry_set_sha256",
    "protected_paths",
    "normalized_baseline_sha256",
    "claims_not_made",
}
_BOOTSTRAP_EXTRA_KEYS = {"bootstrap_capture_bindings", "raw_archive_not_persisted"}
_DURABLE_AUTHORITY_SCHEMAS = {
    "broad_evidence_bootstrap_subject.v1",
    "implementation_verification_subject.v1",
    "review.v1",
    "workflow_retirement_execution_ledger.v1",
    "workflow_retirement_execution_index.v1",
}


class SourceBindingError(RuntimeError):
    """A source binding could not be captured without weakening its contract."""


@dataclass(frozen=True)
class SourceBindingIssue:
    code: str
    path: str = ""
    detail: str = ""

    def as_dict(self) -> dict[str, str]:
        return {"code": self.code, "path": self.path, "detail": self.detail}

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, SourceBindingIssue):
            return NotImplemented
        return (self.path, self.code, self.detail) < (
            other.path,
            other.code,
            other.detail,
        )


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def _sha256_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _canonical_sha256(value: Any, *, exclude: Iterable[str] = ()) -> str:
    if not isinstance(value, Mapping):
        return _sha256_bytes(_canonical_bytes(value))
    excluded = set(exclude)
    return _sha256_bytes(_canonical_bytes({k: v for k, v in value.items() if k not in excluded}))


def _set_digest(rows: Iterable[Any]) -> str:
    values = sorted((_canonical_bytes(row) for row in rows))
    return _sha256_bytes(b"\n".join(values) + (b"\n" if values else b""))


def _path_list_digest(paths: Iterable[str]) -> str:
    values = sorted(paths)
    return _sha256_bytes(b"".join(path.encode("utf-8") + b"\n" for path in values))


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise SourceBindingError(f"duplicate_json_key:{key}")
        result[key] = value
    return result


def _open_repository_parent(
    root: Path, path: Path | str, *, create: bool = False
) -> tuple[int, str, str]:
    """Open a repository-relative parent without following any component."""
    relative = _relative_path(path)
    parts = PurePosixPath(relative).parts
    directory_flags = (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    try:
        descriptor = os.open(root, directory_flags)
        for component in parts[:-1]:
            try:
                child = os.open(component, directory_flags, dir_fd=descriptor)
            except FileNotFoundError:
                if not create:
                    raise
                os.mkdir(component, mode=0o755, dir_fd=descriptor)
                child = os.open(component, directory_flags, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
    except OSError as exc:
        try:
            os.close(descriptor)
        except (OSError, UnboundLocalError):
            pass
        raise SourceBindingError(
            f"repository_path_parent_unreadable:{relative}:{exc}"
        ) from exc
    return descriptor, parts[-1], relative


def _read_repository_bytes(root: Path, path: Path | str) -> bytes:
    parent, name, relative = _open_repository_parent(root, path)
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(name, flags, dir_fd=parent)
        try:
            before = os.fstat(descriptor)
            if not stat.S_ISREG(before.st_mode):
                raise SourceBindingError(f"repository_path_not_regular:{relative}")
            chunks: list[bytes] = []
            while True:
                chunk = os.read(descriptor, 1024 * 1024)
                if not chunk:
                    break
                chunks.append(chunk)
            after = os.fstat(descriptor)
            if (
                before.st_dev,
                before.st_ino,
                before.st_mode,
                before.st_size,
                before.st_mtime_ns,
                before.st_ctime_ns,
            ) != (
                after.st_dev,
                after.st_ino,
                after.st_mode,
                after.st_size,
                after.st_mtime_ns,
                after.st_ctime_ns,
            ):
                raise SourceBindingError(f"repository_path_raced:{relative}")
            return b"".join(chunks)
        finally:
            os.close(descriptor)
    except SourceBindingError:
        raise
    except OSError as exc:
        raise SourceBindingError(
            f"repository_path_unreadable:{relative}:{exc}"
        ) from exc
    finally:
        os.close(parent)


def _read_json(root: Path, path: Path | str) -> dict[str, Any]:
    try:
        data = _read_repository_bytes(root, path)
        return _json_object(data, path)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SourceBindingError(f"invalid_json:{path}:{exc}") from exc


def _json_object(data: bytes, path: Path | str) -> dict[str, Any]:
    try:
        value = json.loads(data.decode("utf-8"), object_pairs_hook=_strict_object)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise SourceBindingError(f"invalid_json:{path}:{exc}") from exc
    if not isinstance(value, dict):
        raise SourceBindingError(f"invalid_json_root:{path}")
    return value


def _write_repository_bytes(
    root: Path, path: Path | str, data: bytes, *, exclusive: bool = False
) -> None:
    parent, name, relative = _open_repository_parent(root, path, create=True)
    temporary_name = f".{name}.{os.getpid()}.{hashlib.sha256(os.urandom(32)).hexdigest()}.tmp"
    flags = (
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    temporary = -1
    cleanup_temporary = True
    try:
        logical_parent = bind_logical_parent(root, Path(relative).parent, parent)
        try:
            existing = capture_regular_file_at(
                parent, name, relative, missing_ok=True
            )
        except AtomicPublishError as exc:
            raise SourceBindingError(
                f"repository_path_output_not_regular:{relative}:{exc.code}"
            ) from exc
        if existing is not None:
            if exclusive:
                if existing.data != data:
                    raise SourceBindingError(f"external_control_collision:{relative}")
                if not logical_parent_matches(logical_parent):
                    raise AtomicPublishError(
                        "logical_parent_changed", relative
                    )
                return
        temporary = os.open(temporary_name, flags, 0o644, dir_fd=parent)
        offset = 0
        while offset < len(data):
            offset += os.write(temporary, data[offset:])
        os.fsync(temporary)
        os.close(temporary)
        temporary = -1
        conditional_publish_file_at(
            parent,
            temporary_name,
            name,
            existing,
            relative,
            logical_parent=logical_parent,
        )
    except AtomicPublishError as exc:
        cleanup_temporary = not exc.preserve_temporary
        code = (
            "repository_path_output_concurrent_mutation"
            if exc.code == "concurrent_mutation"
            else "repository_path_output_failed"
        )
        raise SourceBindingError(
            f"{code}:{relative}:{exc.code}"
        ) from exc
    except SourceBindingError:
        raise
    except OSError as exc:
        raise SourceBindingError(f"repository_path_output_failed:{relative}:{exc}") from exc
    finally:
        if temporary >= 0:
            os.close(temporary)
        if cleanup_temporary:
            try:
                os.unlink(temporary_name, dir_fd=parent)
            except FileNotFoundError:
                pass
        os.close(parent)


def _write_json(root: Path, path: Path | str, value: Mapping[str, Any]) -> None:
    data = _canonical_bytes(value) + b"\n"
    _write_repository_bytes(root, path, data)


def _git(root: Path, *args: str, input_bytes: bytes | None = None, env: Mapping[str, str] | None = None) -> bytes:
    completed = subprocess.run(
        ["git", *args],
        cwd=root,
        input=input_bytes,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        env=None if env is None else {**os.environ, **env},
    )
    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", "replace").strip()
        raise SourceBindingError(f"git_failed:{args[0] if args else 'git'}:{detail}")
    return completed.stdout


def _repository_root(root: Path | str) -> Path:
    candidate = Path(root).resolve()
    actual = Path(_git(candidate, "rev-parse", "--show-toplevel").decode().strip()).resolve()
    if candidate != actual:
        raise SourceBindingError(f"repository_root_mismatch:{candidate}:{actual}")
    return actual


def _relative_path(value: str | Path) -> str:
    text = value.as_posix() if isinstance(value, Path) else value
    try:
        text.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise SourceBindingError("non_utf8_path") from exc
    parsed = PurePosixPath(text)
    if not text or parsed.is_absolute() or text != parsed.as_posix() or any(part in {"", ".", ".."} for part in parsed.parts):
        raise SourceBindingError(f"invalid_repository_relative_path:{text!r}")
    return text


def _decode_path(data: bytes) -> str:
    try:
        return _relative_path(data.decode("utf-8", "strict"))
    except UnicodeDecodeError as exc:
        raise SourceBindingError("non_utf8_path") from exc


def _parse_status(data: bytes) -> list[dict[str, Any]]:
    fields = data.split(b"\0")
    if fields[-1:] == [b""]:
        fields.pop()
    rows: list[dict[str, Any]] = []
    index = 0
    while index < len(fields):
        field = fields[index]
        index += 1
        if len(field) < 4 or field[2:3] != b" ":
            raise SourceBindingError("malformed_porcelain_status")
        try:
            status_code = field[:2].decode("ascii")
        except UnicodeDecodeError as exc:
            raise SourceBindingError("malformed_porcelain_status") from exc
        path = _decode_path(field[3:])
        source_path: str | None = None
        if status_code[0] in "RC" or status_code[1] in "RC":
            if index >= len(fields):
                raise SourceBindingError("truncated_porcelain_rename")
            source_path = _decode_path(fields[index])
            index += 1
        operands = sorted({path, *([] if source_path is None else [source_path])})
        rows.append(
            {
                "status": status_code,
                "path": path,
                "source_path": source_path,
                "path_operands": operands,
            }
        )
    rows.sort(key=lambda row: (row["path"], row["source_path"] or "", row["status"]))
    for number, row in enumerate(rows, 1):
        row["row_id"] = f"status-{number:08d}"
    return rows


def _parse_index(data: bytes) -> list[dict[str, Any]]:
    records = data.split(b"\0")
    if records[-1:] == [b""]:
        records.pop()
    rows: list[dict[str, Any]] = []
    for record in records:
        try:
            prefix, raw_path = record.split(b"\t", 1)
            mode, oid, stage = prefix.decode("ascii").split(" ")
        except (ValueError, UnicodeDecodeError) as exc:
            raise SourceBindingError("malformed_index_entries") from exc
        if not re.fullmatch(r"[0-7]{6}", mode) or not re.fullmatch(r"[0-9a-f]{40,64}", oid) or stage not in {"0", "1", "2", "3"}:
            raise SourceBindingError("malformed_index_entries")
        rows.append({"path": _decode_path(raw_path), "stage": int(stage), "mode": mode, "oid": oid})
    rows.sort(key=lambda row: (row["path"], row["stage"], row["mode"], row["oid"]))
    return rows


def _capture_git(root: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str, str]:
    status_rows = _parse_status(_git(root, "status", "--porcelain=v1", "-z", "--untracked-files=all"))
    index_entries = _parse_index(_git(root, "ls-files", "--stage", "-z"))
    try:
        index_path = Path(_git(root, "rev-parse", "--path-format=absolute", "--git-path", "index").decode().strip())
        index_relative = index_path.relative_to(root)
        index_sha = _sha256_bytes(_read_repository_bytes(root, index_relative))
    except (OSError, ValueError, SourceBindingError) as exc:
        raise SourceBindingError(f"index_unreadable:{exc}") from exc
    head = _git(root, "rev-parse", "HEAD").decode("ascii").strip()
    if not _HEX40_RE.fullmatch(head):
        raise SourceBindingError("invalid_head")
    return status_rows, index_entries, index_sha, head


def _stat_identity(value: os.stat_result) -> tuple[int, int, int, int, int, int]:
    return (
        value.st_dev,
        value.st_ino,
        value.st_mode,
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
    )


def _regular_binding(
    parent: int, name: str, before: os.stat_result, display_path: str
) -> dict[str, Any]:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(name, flags, dir_fd=parent)
        try:
            opened = os.fstat(descriptor)
            if _stat_identity(opened) != _stat_identity(before):
                raise SourceBindingError(f"racing_file:{display_path}")
            digest = hashlib.sha256()
            size = 0
            while True:
                chunk = os.read(descriptor, 1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                digest.update(chunk)
            after = os.fstat(descriptor)
            if _stat_identity(after) != _stat_identity(opened):
                raise SourceBindingError(f"racing_file:{display_path}")
        finally:
            os.close(descriptor)
        final_entry = os.stat(name, dir_fd=parent, follow_symlinks=False)
        if _stat_identity(final_entry) != _stat_identity(before):
            raise SourceBindingError(f"racing_file:{display_path}")
    except OSError as exc:
        raise SourceBindingError(f"unreadable_file:{display_path}:{exc}") from exc
    return {"kind": "regular", "size": size, "sha256": "sha256:" + digest.hexdigest()}


def _symlink_binding(
    parent: int, name: str, before: os.stat_result, display_path: str
) -> dict[str, Any]:
    try:
        target = os.readlink(name, dir_fd=parent)
        after = os.stat(name, dir_fd=parent, follow_symlinks=False)
        if _stat_identity(after) != _stat_identity(before):
            raise SourceBindingError(f"racing_symlink:{display_path}")
    except OSError as exc:
        raise SourceBindingError(f"unreadable_symlink:{display_path}:{exc}") from exc
    target_bytes = target if isinstance(target, bytes) else os.fsencode(target)
    return {"kind": "symlink", "target_length": len(target_bytes), "target_sha256": _sha256_bytes(target_bytes)}


def _open_bound_directory(
    parent: int, name: str, before: os.stat_result, display_path: str
) -> int:
    flags = (
        os.O_RDONLY
        | os.O_DIRECTORY
        | os.O_NOFOLLOW
        | getattr(os, "O_CLOEXEC", 0)
    )
    try:
        descriptor = os.open(name, flags, dir_fd=parent)
        if _stat_identity(os.fstat(descriptor)) != _stat_identity(before):
            os.close(descriptor)
            raise SourceBindingError(f"racing_directory:{display_path}")
        return descriptor
    except SourceBindingError:
        raise
    except OSError as exc:
        raise SourceBindingError(f"unreadable_directory:{display_path}:{exc}") from exc


def _directory_descendants(
    descriptor: int, *, relative_prefix: str, display_prefix: str
) -> list[dict[str, Any]]:
    descendants: list[dict[str, Any]] = []
    try:
        names = sorted(os.listdir(descriptor))
    except OSError as exc:
        raise SourceBindingError(f"unreadable_directory:{display_prefix}:{exc}") from exc
    for name in names:
        relative = f"{relative_prefix}/{name}" if relative_prefix else name
        relative = _relative_path(relative)
        display = f"{display_prefix}/{name}" if display_prefix else name
        try:
            item_stat = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
        except OSError as exc:
            raise SourceBindingError(f"unreadable_file:{display}:{exc}") from exc
        mode = stat.S_IMODE(item_stat.st_mode)
        if stat.S_ISDIR(item_stat.st_mode):
            child_descriptor = _open_bound_directory(
                descriptor, name, item_stat, display
            )
            try:
                nested = _directory_descendants(
                    child_descriptor,
                    relative_prefix=relative,
                    display_prefix=display,
                )
                if _stat_identity(os.fstat(child_descriptor)) != _stat_identity(
                    item_stat
                ):
                    raise SourceBindingError(f"racing_directory:{display}")
            finally:
                os.close(child_descriptor)
            after = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
            if _stat_identity(after) != _stat_identity(item_stat):
                raise SourceBindingError(f"racing_directory:{display}")
            descendants.append({"path": relative, "file_type": "directory", "lstat_mode": mode, "size": None, "sha256": None})
            descendants.extend(nested)
        elif stat.S_ISREG(item_stat.st_mode):
            content = _regular_binding(descriptor, name, item_stat, display)
            descendants.append({"path": relative, "file_type": "regular", "lstat_mode": mode, "size": content["size"], "sha256": content["sha256"]})
        elif stat.S_ISLNK(item_stat.st_mode):
            content = _symlink_binding(descriptor, name, item_stat, display)
            descendants.append({"path": relative, "file_type": "symlink", "lstat_mode": mode, "size": content["target_length"], "sha256": content["target_sha256"]})
        else:
            raise SourceBindingError(f"unsupported_file_type:{display}")
    return descendants


def _directory_binding(
    parent: int, name: str, before: os.stat_result, display_path: str
) -> dict[str, Any]:
    descriptor = _open_bound_directory(parent, name, before, display_path)
    try:
        descendants = _directory_descendants(
            descriptor, relative_prefix="", display_prefix=display_path
        )
        if _stat_identity(os.fstat(descriptor)) != _stat_identity(before):
            raise SourceBindingError(f"racing_directory:{display_path}")
    finally:
        os.close(descriptor)
    after = os.stat(name, dir_fd=parent, follow_symlinks=False)
    if _stat_identity(after) != _stat_identity(before):
        raise SourceBindingError(f"racing_directory:{display_path}")
    descendants.sort(key=lambda row: row["path"])
    return {
        "kind": "directory",
        "descendants": descendants,
        "descendant_count": len(descendants),
        "descendant_set_sha256": _set_digest(descendants),
    }


def _git_at(descriptor: int, *args: str) -> bytes:
    completed = subprocess.run(
        ["git", *args],
        cwd=f"/proc/self/fd/{descriptor}",
        pass_fds=(descriptor,),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", "replace").strip()
        raise SourceBindingError(f"git_failed:{args[0] if args else 'git'}:{detail}")
    return completed.stdout


def _snapshot_path(root: Path, relative: str, *, status_row_ids: Sequence[str], index_entries: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    relative = _relative_path(relative)
    matching_index = [dict(row) for row in index_entries if row["path"] == relative]
    try:
        parent, name, _ = _open_repository_parent(root, relative)
        try:
            try:
                item_stat = os.stat(name, dir_fd=parent, follow_symlinks=False)
            except FileNotFoundError:
                file_type = "absent"
                mode = None
                content = {"kind": "absent", "size": None, "sha256": None}
                existence = "absent"
            else:
                existence = "present"
                mode = stat.S_IMODE(item_stat.st_mode)
                if stat.S_ISREG(item_stat.st_mode):
                    file_type = "regular"
                    content = _regular_binding(parent, name, item_stat, relative)
                elif stat.S_ISLNK(item_stat.st_mode):
                    file_type = "symlink"
                    content = _symlink_binding(parent, name, item_stat, relative)
                elif stat.S_ISDIR(item_stat.st_mode):
                    if any(row["mode"] == "160000" for row in matching_index):
                        file_type = "gitlink"
                        nested_head = None
                        nested_status = None
                        descriptor = _open_bound_directory(
                            parent, name, item_stat, relative
                        )
                        try:
                            try:
                                nested_head = _git_at(descriptor, "rev-parse", "HEAD").decode("ascii").strip()
                                nested_status = _sha256_bytes(_git_at(descriptor, "status", "--porcelain=v1", "-z", "--untracked-files=all"))
                            except SourceBindingError:
                                pass
                        finally:
                            os.close(descriptor)
                        after = os.stat(
                            name, dir_fd=parent, follow_symlinks=False
                        )
                        if _stat_identity(after) != _stat_identity(item_stat):
                            raise SourceBindingError(f"racing_directory:{relative}")
                        content = {"kind": "gitlink", "index_oid": next((row["oid"] for row in matching_index if row["mode"] == "160000"), None), "nested_head": nested_head, "nested_status_sha256": nested_status}
                    else:
                        file_type = "directory"
                        content = _directory_binding(parent, name, item_stat, relative)
                else:
                    raise SourceBindingError(f"unsupported_file_type:{relative}")
        finally:
            os.close(parent)
    except SourceBindingError:
        raise
    row: dict[str, Any] = {
        "path": relative,
        "status_row_ids": sorted(set(status_row_ids)),
        "existence": existence,
        "file_type": file_type,
        "lstat_mode": mode,
        "index_entries": matching_index,
        "content_binding": content,
    }
    row["normalized_entry_sha256"] = _canonical_sha256(row, exclude={"normalized_entry_sha256"})
    return row


def _validate_workspace_tree(
    descriptor: int, *, relative_prefix: str = "", repository_root: bool = False
) -> None:
    try:
        names = sorted(os.listdir(descriptor))
    except OSError as exc:
        raise SourceBindingError(
            f"workspace_tree_unreadable:{relative_prefix}:{exc}"
        ) from exc
    for name in names:
        if repository_root and name == ".git":
            continue
        relative = _relative_path(
            f"{relative_prefix}/{name}" if relative_prefix else name
        )
        try:
            item_stat = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
        except OSError as exc:
            raise SourceBindingError(f"unreadable_file:{relative}:{exc}") from exc
        if stat.S_ISREG(item_stat.st_mode) or stat.S_ISLNK(item_stat.st_mode):
            continue
        if not stat.S_ISDIR(item_stat.st_mode):
            raise SourceBindingError(f"unsupported_file_type:{relative}")
        child = _open_bound_directory(descriptor, name, item_stat, relative)
        try:
            _validate_workspace_tree(child, relative_prefix=relative)
            if _stat_identity(os.fstat(child)) != _stat_identity(item_stat):
                raise SourceBindingError(f"racing_directory:{relative}")
        finally:
            os.close(child)
        after = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
        if _stat_identity(after) != _stat_identity(item_stat):
            raise SourceBindingError(f"racing_directory:{relative}")


def _capture_from_git(root: Path, protected_paths: Sequence[str] = ()) -> dict[str, Any]:
    root_descriptor = os.open(
        root,
        os.O_RDONLY
        | os.O_DIRECTORY
        | os.O_NOFOLLOW
        | getattr(os, "O_CLOEXEC", 0),
    )
    try:
        _validate_workspace_tree(root_descriptor, repository_root=True)
    finally:
        os.close(root_descriptor)
    status_rows, index_entries, index_sha, head = _capture_git(root)
    path_to_rows: dict[str, list[str]] = {}
    for row in status_rows:
        for path in row["path_operands"]:
            path_to_rows.setdefault(path, []).append(row["row_id"])
    dirty_entries = [
        _snapshot_path(root, path, status_row_ids=row_ids, index_entries=index_entries)
        for path, row_ids in sorted(path_to_rows.items())
    ]
    protected = []
    for path in sorted({_relative_path(path) for path in protected_paths}):
        protected.append(_snapshot_path(root, path, status_row_ids=path_to_rows.get(path, []), index_entries=index_entries))
    record: dict[str, Any] = {
        "schema_version": "workspace_baseline.v1",
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "head": head,
        "index_sha256": index_sha,
        "index_entries": index_entries,
        "index_entry_count": len(index_entries),
        "index_entry_set_sha256": _set_digest(index_entries),
        "status_rows": status_rows,
        "dirty_entries": dirty_entries,
        "dirty_entry_count": len(dirty_entries),
        "dirty_path_set_sha256": _path_list_digest(row["path"] for row in dirty_entries),
        "dirty_entry_set_sha256": _set_digest(dirty_entries),
        "protected_paths": protected,
        "claims_not_made": [
            "The baseline does not claim ownership of pre-existing dirty content.",
            "The baseline does not authorize mutation of a captured path.",
        ],
    }
    record["normalized_baseline_sha256"] = _canonical_sha256(record, exclude={"normalized_baseline_sha256"})
    return record


def capture_workspace_baseline(repository_root: Path | str, protected_paths: Sequence[str] = ()) -> dict[str, Any]:
    """Capture the complete dirty operand and semantic-index baseline."""
    return _capture_from_git(_repository_root(repository_root), protected_paths)


def _valid_relative(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    try:
        return _relative_path(value) == value
    except SourceBindingError:
        return False


def _valid_index_entry(value: Any) -> bool:
    return (
        isinstance(value, Mapping)
        and set(value) == {"path", "stage", "mode", "oid"}
        and _valid_relative(value["path"])
        and type(value["stage"]) is int
        and value["stage"] in {0, 1, 2, 3}
        and isinstance(value["mode"], str)
        and re.fullmatch(r"[0-7]{6}", value["mode"]) is not None
        and isinstance(value["oid"], str)
        and re.fullmatch(r"[0-9a-f]{40,64}", value["oid"]) is not None
    )


def _valid_content_binding(value: Any, file_type: Any) -> bool:
    if not isinstance(value, Mapping):
        return False
    if file_type == "absent":
        return set(value) == {"kind", "size", "sha256"} and dict(value) == {
            "kind": "absent",
            "size": None,
            "sha256": None,
        }
    if file_type == "regular":
        return (
            set(value) == {"kind", "size", "sha256"}
            and value["kind"] == "regular"
            and type(value["size"]) is int
            and value["size"] >= 0
            and _SHA256_RE.fullmatch(str(value["sha256"])) is not None
        )
    if file_type == "symlink":
        return (
            set(value) == {"kind", "target_length", "target_sha256"}
            and value["kind"] == "symlink"
            and type(value["target_length"]) is int
            and value["target_length"] >= 0
            and _SHA256_RE.fullmatch(str(value["target_sha256"])) is not None
        )
    if file_type == "gitlink":
        return (
            set(value)
            == {"kind", "index_oid", "nested_head", "nested_status_sha256"}
            and value["kind"] == "gitlink"
            and (
                value["index_oid"] is None
                or re.fullmatch(r"[0-9a-f]{40,64}", str(value["index_oid"]))
                is not None
            )
            and (
                value["nested_head"] is None
                or _HEX40_RE.fullmatch(str(value["nested_head"])) is not None
            )
            and (
                value["nested_status_sha256"] is None
                or _SHA256_RE.fullmatch(str(value["nested_status_sha256"]))
                is not None
            )
        )
    if file_type != "directory" or set(value) != {
        "kind",
        "descendants",
        "descendant_count",
        "descendant_set_sha256",
    }:
        return False
    descendants = value["descendants"]
    descendant_keys = {"path", "file_type", "lstat_mode", "size", "sha256"}
    if (
        value["kind"] != "directory"
        or not isinstance(descendants, list)
        or any(
            not isinstance(row, Mapping)
            or set(row) != descendant_keys
            or not _valid_relative(row["path"])
            or not isinstance(row["file_type"], str)
            or row["file_type"] not in {"directory", "regular", "symlink"}
            or type(row["lstat_mode"]) is not int
            or not 0 <= row["lstat_mode"] <= 0o7777
            or (
                row["file_type"] == "directory"
                and (row["size"] is not None or row["sha256"] is not None)
            )
            or (
                row["file_type"] != "directory"
                and (
                    type(row["size"]) is not int
                    or row["size"] < 0
                    or _SHA256_RE.fullmatch(str(row["sha256"])) is None
                )
            )
            for row in descendants
        )
    ):
        return False
    paths = [row["path"] for row in descendants]
    return (
        paths == sorted(set(paths))
        and type(value["descendant_count"]) is int
        and value["descendant_count"] >= 0
        and value["descendant_count"] == len(descendants)
        and value["descendant_set_sha256"] == _set_digest(descendants)
    )


def _valid_workspace_entry(value: Any) -> bool:
    keys = {
        "path",
        "status_row_ids",
        "existence",
        "file_type",
        "lstat_mode",
        "index_entries",
        "content_binding",
        "normalized_entry_sha256",
    }
    if (
        not isinstance(value, Mapping)
        or set(value) != keys
        or not _valid_relative(value["path"])
        or not isinstance(value["status_row_ids"], list)
        or any(
            not isinstance(row_id, str)
            or re.fullmatch(r"status-[0-9]{8}", row_id) is None
            for row_id in value["status_row_ids"]
        )
        or value["status_row_ids"] != sorted(set(value["status_row_ids"]))
        or not isinstance(value["existence"], str)
        or value["existence"] not in {"present", "absent"}
        or not isinstance(value["file_type"], str)
        or value["file_type"]
        not in {"regular", "symlink", "directory", "gitlink", "absent"}
        or not isinstance(value["index_entries"], list)
        or any(not _valid_index_entry(row) for row in value["index_entries"])
        or any(row["path"] != value["path"] for row in value["index_entries"])
        or value["index_entries"]
        != sorted(
            value["index_entries"],
            key=lambda row: (row["path"], row["stage"], row["mode"], row["oid"]),
        )
        or not _valid_content_binding(value["content_binding"], value["file_type"])
        or value["normalized_entry_sha256"]
        != _canonical_sha256(value, exclude={"normalized_entry_sha256"})
    ):
        return False
    if value["existence"] == "absent":
        return value["file_type"] == "absent" and value["lstat_mode"] is None
    return (
        value["file_type"] != "absent"
        and type(value["lstat_mode"]) is int
        and 0 <= value["lstat_mode"] <= 0o7777
    )


def _validate_workspace_shape(record: Mapping[str, Any], *, bootstrap: bool) -> list[SourceBindingIssue]:
    issues: list[SourceBindingIssue] = []
    expected = _WORKSPACE_KEYS | (_BOOTSTRAP_EXTRA_KEYS if bootstrap else set())
    if set(record) != expected:
        issues.append(SourceBindingIssue("schema_keys_mismatch", detail=f"expected={sorted(expected)!r};actual={sorted(record)!r}"))
        return issues
    expected_schema = "bootstrap_workspace_baseline.v1" if bootstrap else "workspace_baseline.v1"
    if record.get("schema_version") != expected_schema:
        issues.append(SourceBindingIssue("schema_version_mismatch"))
    if record.get("normalized_baseline_sha256") != _canonical_sha256(record, exclude={"normalized_baseline_sha256"}):
        issues.append(SourceBindingIssue("normalized_digest_mismatch"))
    try:
        captured = datetime.fromisoformat(record.get("captured_at"))
        if captured.tzinfo is None:
            raise ValueError
    except (TypeError, ValueError):
        issues.append(SourceBindingIssue("captured_at_invalid"))
    if _HEX40_RE.fullmatch(str(record.get("head"))) is None:
        issues.append(SourceBindingIssue("head_invalid"))
    if _SHA256_RE.fullmatch(str(record.get("index_sha256"))) is None:
        issues.append(SourceBindingIssue("index_sha256_invalid"))
    claims = record.get("claims_not_made")
    if (
        not isinstance(claims, list)
        or not claims
        or any(not isinstance(claim, str) or not claim for claim in claims)
    ):
        issues.append(SourceBindingIssue("claims_not_made_invalid"))
    entries = record.get("dirty_entries")
    rows = record.get("status_rows")
    index = record.get("index_entries")
    protected = record.get("protected_paths")
    if not all(isinstance(value, list) for value in (entries, rows, index, protected)):
        issues.append(SourceBindingIssue("invalid_collection_type"))
        return issues
    status_invalid = any(
        not isinstance(row, Mapping)
        or set(row) != {"row_id", "status", "path", "source_path", "path_operands"}
        or re.fullmatch(r"status-[0-9]{8}", str(row.get("row_id"))) is None
        or not isinstance(row.get("status"), str)
        or re.fullmatch(r"[ MADRCU?!]{2}", row["status"]) is None
        or not _valid_relative(row.get("path"))
        or (row.get("source_path") is not None and not _valid_relative(row["source_path"]))
        or not isinstance(row.get("path_operands"), list)
        or row["path_operands"]
        != sorted({row["path"], *([] if row["source_path"] is None else [row["source_path"]])})
        for row in rows
    ) or [row.get("row_id") for row in rows] != [
        f"status-{number:08d}" for number in range(1, len(rows) + 1)
    ] or rows != sorted(
        rows,
        key=lambda row: (
            row.get("path", ""),
            row.get("source_path") or "",
            row.get("status", ""),
        ),
    )
    if status_invalid:
        issues.append(SourceBindingIssue("status_row_invalid"))
    index_invalid = any(not _valid_index_entry(row) for row in index) or index != sorted(
        index, key=lambda row: (row.get("path", ""), row.get("stage", -1), row.get("mode", ""), row.get("oid", ""))
    )
    if index_invalid:
        issues.append(SourceBindingIssue("index_entry_invalid"))
    entries_valid = all(
        _valid_workspace_entry(entry) for entry in [*entries, *protected]
    )
    if not entries_valid:
        issues.append(SourceBindingIssue("workspace_entry_invalid"))
    if entries_valid and (
        [entry["path"] for entry in entries]
        != sorted({entry["path"] for entry in entries})
        or [entry["path"] for entry in protected]
        != sorted({entry["path"] for entry in protected})
    ):
        issues.append(SourceBindingIssue("workspace_entry_partition_invalid"))
    if entries_valid and not status_invalid:
        status_ids = {row["row_id"] for row in rows if isinstance(row, Mapping)}
        if any(
            not set(entry["status_row_ids"]) <= status_ids
            for entry in [*entries, *protected]
        ):
            issues.append(SourceBindingIssue("workspace_status_reference_invalid"))
    if status_invalid or index_invalid or not entries_valid:
        return sorted(set(issues))
    paths = [entry.get("path") for entry in entries if isinstance(entry, dict)]
    operands = sorted({path for row in rows if isinstance(row, dict) for path in row.get("path_operands", [])})
    if paths != sorted(set(paths)) or sorted(paths) != operands:
        issues.append(SourceBindingIssue("dirty_path_partition_mismatch"))
    if type(record.get("dirty_entry_count")) is not int or record.get("dirty_entry_count") != len(entries):
        issues.append(SourceBindingIssue("dirty_entry_count_mismatch"))
    if record.get("dirty_path_set_sha256") != _path_list_digest(paths):
        issues.append(SourceBindingIssue("dirty_path_set_digest_mismatch"))
    if record.get("dirty_entry_set_sha256") != _set_digest(entries):
        issues.append(SourceBindingIssue("dirty_entry_set_digest_mismatch"))
    if type(record.get("index_entry_count")) is not int or record.get("index_entry_count") != len(index) or record.get("index_entry_set_sha256") != _set_digest(index):
        issues.append(SourceBindingIssue("index_entry_set_mismatch"))
    for entry in [*entries, *protected]:
        if not isinstance(entry, dict) or entry.get("normalized_entry_sha256") != _canonical_sha256(entry, exclude={"normalized_entry_sha256"}):
            issues.append(SourceBindingIssue("entry_digest_mismatch", str(entry.get("path", "")) if isinstance(entry, dict) else ""))
    if bootstrap:
        if record.get("raw_archive_not_persisted") is not True:
            issues.append(SourceBindingIssue("raw_archive_persistence_claim_invalid"))
        bindings = record.get("bootstrap_capture_bindings")
        expected_binding_keys = {"producer_contract_version", "head_file_sha256", "status_file_sha256", "index_entries_file_sha256", "index_file_sha256", "archive_sha256", "tar_stderr_sha256"}
        if not isinstance(bindings, dict) or set(bindings) != expected_binding_keys:
            issues.append(SourceBindingIssue("bootstrap_capture_binding_keys_mismatch"))
        elif bindings.get("producer_contract_version") != "task1_first_write_capture.v1" or any(not isinstance(bindings.get(key), str) or not _SHA256_RE.fullmatch(bindings[key]) for key in expected_binding_keys - {"producer_contract_version"}):
            issues.append(SourceBindingIssue("bootstrap_capture_binding_invalid"))
    return issues


def _valid_claims(value: Any) -> bool:
    return (
        isinstance(value, list)
        and bool(value)
        and all(isinstance(row, str) and bool(row) for row in value)
    )


def _valid_file_binding_shape(
    value: Any, *, schema_field: str | None = None
) -> bool:
    expected = {"path", "size", "sha256"}
    if schema_field is not None:
        expected.add(schema_field)
    return (
        isinstance(value, Mapping)
        and set(value) == expected
        and _valid_relative(value.get("path"))
        and type(value.get("size")) is int
        and value["size"] >= 0
        and isinstance(value.get("sha256"), str)
        and _SHA256_RE.fullmatch(value["sha256"]) is not None
        and (
            schema_field is None
            or (
                isinstance(value.get(schema_field), str)
                and bool(value.get(schema_field))
            )
        )
    )


def _durable_authority_rows_valid(
    value: Any, *, allowed_paths: set[str] | None = None
) -> bool:
    if (
        not isinstance(value, list)
        or not value
        or len(value) > 20
        or any(
            not _valid_file_binding_shape(row, schema_field="schema_version")
            or row["schema_version"] not in _DURABLE_AUTHORITY_SCHEMAS
            for row in value
        )
        or value != sorted(value, key=lambda row: row["path"])
        or len({row["path"] for row in value}) != len(value)
    ):
        return False
    return allowed_paths is None or {row["path"] for row in value} <= allowed_paths


_NON_TARGET_TRACKED_QUEUE_SIZES = (1, 1, 7)


def _non_target_partition_valid(rows: Sequence[Mapping[str, Any]]) -> bool:
    tracked_rows = [
        row for row in rows if row.get("binding_source") == "tracked_source_binding"
    ]
    protected_rows = [
        row
        for row in rows
        if row.get("binding_source") == "workspace_protected_binding"
    ]
    if len(rows) != 10 or len(tracked_rows) != 9 or len(protected_rows) != 1:
        return False
    tracked_counts: dict[str, int] = {}
    for row in tracked_rows:
        queue_id = row.get("queue_id")
        if not isinstance(queue_id, str):
            return False
        tracked_counts[queue_id] = tracked_counts.get(queue_id, 0) + 1
    protected_queue_id = protected_rows[0].get("queue_id")
    return (
        sorted(tracked_counts.values()) == list(_NON_TARGET_TRACKED_QUEUE_SIZES)
        and isinstance(protected_queue_id, str)
        and protected_queue_id not in tracked_counts
    )


def _non_target_authority_partition_matches(
    rows: Sequence[Mapping[str, Any]], queues: Mapping[str, Mapping[str, Any]]
) -> bool:
    selected_paths: dict[str, list[str]] = {}
    for row in rows:
        queue_id = row.get("queue_id")
        path = row.get("path")
        if not isinstance(queue_id, str) or not isinstance(path, str):
            return False
        selected_paths.setdefault(queue_id, []).append(path)
    return all(
        queue_id in queues
        and queues[queue_id].get("paths") == sorted(paths)
        for queue_id, paths in selected_paths.items()
    )


def _validate_non_target_shape(record: Mapping[str, Any]) -> list[SourceBindingIssue]:
    expected = {
        "schema_version", "handoff_binding", "workspace_baseline_binding",
        "source_rows", "source_count", "path_list_sha256", "row_set_sha256",
        "normalized_record_sha256", "claims_not_made",
    }
    if set(record) != expected or record.get("schema_version") != "non_target_queue_sources.v1":
        return [SourceBindingIssue("schema_mismatch")]
    issues: list[SourceBindingIssue] = []
    handoff = record.get("handoff_binding")
    baseline = record.get("workspace_baseline_binding")
    if not (
        isinstance(handoff, Mapping)
        and set(handoff) == {"path", "sha256", "handoff_schema_version"}
        and _valid_relative(handoff.get("path"))
        and isinstance(handoff.get("sha256"), str)
        and _SHA256_RE.fullmatch(handoff["sha256"]) is not None
        and isinstance(handoff.get("handoff_schema_version"), str)
        and handoff["handoff_schema_version"]
    ):
        issues.append(SourceBindingIssue("handoff_binding_invalid"))
    if not (
        isinstance(baseline, Mapping)
        and set(baseline) == {"path", "sha256", "schema_version", "protected_path_count"}
        and _valid_relative(baseline.get("path"))
        and isinstance(baseline.get("sha256"), str)
        and _SHA256_RE.fullmatch(baseline["sha256"]) is not None
        and baseline.get("schema_version") == "workspace_baseline.v1"
        and type(baseline.get("protected_path_count")) is int
        and baseline["protected_path_count"] >= 0
    ):
        issues.append(SourceBindingIssue("workspace_baseline_binding_invalid"))
    rows = record.get("source_rows")
    row_keys = {
        "queue_id", "path", "disposition_owner", "binding_source", "tracked_mode",
        "blob_oid", "lstat_mode", "size", "sha256", "protected_binding",
    }
    rows_valid = isinstance(rows, list)
    if rows_valid:
        for row in rows:
            if not isinstance(row, Mapping) or set(row) != row_keys:
                rows_valid = False
                break
            path = row.get("path")
            queue = row.get("queue_id")
            if not _valid_relative(path) or not isinstance(queue, str) or not queue or row.get("disposition_owner") != queue:
                rows_valid = False
                break
            if row.get("binding_source") == "tracked_source_binding":
                rows_valid = (
                    row.get("protected_binding") is None
                    and isinstance(row.get("tracked_mode"), str)
                    and re.fullmatch(r"[0-7]{6}", row["tracked_mode"]) is not None
                    and isinstance(row.get("blob_oid"), str)
                    and _HEX40_RE.fullmatch(row["blob_oid"]) is not None
                    and type(row.get("lstat_mode")) is int
                    and 0 <= row["lstat_mode"] <= 0o7777
                    and type(row.get("size")) is int
                    and row["size"] >= 0
                    and isinstance(row.get("sha256"), str)
                    and _SHA256_RE.fullmatch(row["sha256"]) is not None
                )
            elif row.get("binding_source") == "workspace_protected_binding":
                protected = row.get("protected_binding")
                rows_valid = (
                    all(row.get(key) is None for key in ("tracked_mode", "blob_oid", "lstat_mode", "size", "sha256"))
                    and isinstance(protected, Mapping)
                    and set(protected) == {"path", "normalized_entry_sha256"}
                    and protected.get("path") == path
                    and isinstance(protected.get("normalized_entry_sha256"), str)
                    and _SHA256_RE.fullmatch(protected["normalized_entry_sha256"]) is not None
                )
            else:
                rows_valid = False
            if not rows_valid:
                break
    if not rows_valid:
        issues.append(SourceBindingIssue("source_rows_invalid"))
    else:
        paths = [row["path"] for row in rows]
        if (
            paths != sorted(set(paths))
            or not _non_target_partition_valid(rows)
            or type(record.get("source_count")) is not int
            or record.get("source_count") != len(rows)
            or record.get("path_list_sha256") != _path_list_digest(paths)
            or record.get("row_set_sha256") != _set_digest(rows)
        ):
            issues.append(SourceBindingIssue("source_partition_mismatch"))
    if not _valid_claims(record.get("claims_not_made")):
        issues.append(SourceBindingIssue("claims_not_made_invalid"))
    if record.get("normalized_record_sha256") != _canonical_sha256(record, exclude={"normalized_record_sha256"}):
        issues.append(SourceBindingIssue("normalized_digest_mismatch"))
    return issues


def _validate_query_shape(record: Mapping[str, Any]) -> list[SourceBindingIssue]:
    expected = {
        "schema_version", "authority", "queue_id", "paths", "path_count",
        "path_encoding", "path_list_sha256", "capture_commit",
        "claims_not_made", "normalized_query_sha256",
    }
    if set(record) != expected or record.get("schema_version") != "query.v1":
        return [SourceBindingIssue("query_schema_mismatch")]
    issues: list[SourceBindingIssue] = []
    authority = record.get("authority")
    if not (
        isinstance(authority, Mapping)
        and set(authority) == {"path", "sha256", "schema_version"}
        and _valid_relative(authority.get("path"))
        and isinstance(authority.get("sha256"), str)
        and _SHA256_RE.fullmatch(authority["sha256"]) is not None
        and isinstance(authority.get("schema_version"), str)
        and authority["schema_version"]
    ):
        issues.append(SourceBindingIssue("query_authority_invalid"))
    paths = record.get("paths")
    if (
        not isinstance(record.get("queue_id"), str)
        or not record["queue_id"]
        or not isinstance(paths, list)
        or any(not _valid_relative(path) for path in paths)
        or paths != sorted(set(paths))
        or type(record.get("path_count")) is not int
        or record.get("path_count") != len(paths or [])
        or (isinstance(paths, list) and record.get("path_list_sha256") != _path_list_digest(paths))
        or record.get("path_encoding") != "utf8_repository_relative_posix_lf.v1"
    ):
        issues.append(SourceBindingIssue("query_partition_invalid"))
    if not isinstance(record.get("capture_commit"), str) or _HEX40_RE.fullmatch(record["capture_commit"]) is None:
        issues.append(SourceBindingIssue("query_capture_commit_invalid"))
    if not _valid_claims(record.get("claims_not_made")):
        issues.append(SourceBindingIssue("claims_not_made_invalid"))
    if record.get("normalized_query_sha256") != _canonical_sha256(record, exclude={"normalized_query_sha256"}):
        issues.append(SourceBindingIssue("normalized_digest_mismatch"))
    return issues


def _validate_precommit_control_shape(record: Mapping[str, Any]) -> list[SourceBindingIssue]:
    expected = {
        "schema_version", "transaction_id", "bootstrap_workspace_baseline_binding",
        "workspace_baseline_binding", "durable_authority_bindings",
        "durable_authority_set_sha256", "prior_control_trailers", "base_head",
        "pre_commit_index_binding", "allowed_delta_rows", "allowed_delta_count",
        "allowed_path_set_sha256", "expected_index_binding", "expected_commit_tree_oid",
        "pathspec_file_binding", "base_message_binding", "final_message_binding",
        "normalized_control_sha256", "claims_not_made",
    }
    if set(record) != expected or record.get("schema_version") != "precommit_control.v1":
        return [SourceBindingIssue("control_schema_mismatch")]
    issues: list[SourceBindingIssue] = []
    bootstrap, workspace = (
        record.get("bootstrap_workspace_baseline_binding"),
        record.get("workspace_baseline_binding"),
    )
    if (bootstrap is None) == (workspace is None):
        issues.append(SourceBindingIssue("workspace_binding_partition_invalid"))
    baseline = bootstrap if bootstrap is not None else workspace
    expected_schema = "bootstrap_workspace_baseline.v1" if bootstrap is not None else "workspace_baseline.v1"
    if not _valid_file_binding_shape(baseline, schema_field="schema_version") or baseline.get("schema_version") != expected_schema:
        issues.append(SourceBindingIssue("workspace_binding_invalid"))
    authorities = record.get("durable_authority_bindings")
    authorities_valid = _durable_authority_rows_valid(authorities)
    if not authorities_valid:
        issues.append(SourceBindingIssue("durable_authority_invalid"))
        authority_digest = None
    else:
        authority_digest = _set_digest(authorities)
        if record.get("durable_authority_set_sha256") != authority_digest:
            issues.append(SourceBindingIssue("durable_authority_digest_mismatch"))
    base_head = record.get("base_head")
    transaction = record.get("transaction_id")
    if not isinstance(base_head, str) or _HEX40_RE.fullmatch(base_head) is None:
        issues.append(SourceBindingIssue("base_head_invalid"))
    if not isinstance(transaction, str) or re.fullmatch(r"[0-9a-f]{64}", transaction) is None:
        issues.append(SourceBindingIssue("transaction_id_invalid"))
    elif authority_digest is not None and isinstance(base_head, str) and _HEX40_RE.fullmatch(base_head):
        expected_transaction = hashlib.sha256(
            b"precommit-control.v1\0" + base_head.encode("ascii") + b"\0"
            + authority_digest.removeprefix("sha256:").encode("ascii")
        ).hexdigest()
        if transaction != expected_transaction:
            issues.append(SourceBindingIssue("transaction_binding_mismatch"))
    index_keys = {"entry_count", "entry_set_sha256"}
    for field in ("pre_commit_index_binding", "expected_index_binding"):
        value = record.get(field)
        if not (
            isinstance(value, Mapping) and set(value) == index_keys
            and type(value.get("entry_count")) is int and value["entry_count"] >= 0
            and isinstance(value.get("entry_set_sha256"), str)
            and _SHA256_RE.fullmatch(value["entry_set_sha256"]) is not None
        ):
            issues.append(SourceBindingIssue(f"{field}_invalid"))
    rows = record.get("allowed_delta_rows")
    rows_valid = isinstance(rows, list) and bool(rows)
    if rows_valid:
        for row in rows:
            if not isinstance(row, Mapping) or set(row) != {"path", "before", "after"} or not _valid_relative(row.get("path")):
                rows_valid = False
                break
            for side in ("before", "after"):
                entry = row.get(side)
                if entry is None:
                    continue
                if not _valid_index_entry(entry) or entry.get("path") != row["path"] or entry.get("stage") != 0:
                    rows_valid = False
                    break
            if row.get("before") is None and row.get("after") is None:
                rows_valid = False
            if not rows_valid:
                break
    if not rows_valid:
        issues.append(SourceBindingIssue("allowed_delta_rows_invalid"))
    else:
        paths = [row["path"] for row in rows]
        if (
            paths != sorted(set(paths))
            or type(record.get("allowed_delta_count")) is not int
            or record.get("allowed_delta_count") != len(rows)
            or record.get("allowed_path_set_sha256") != _path_list_digest(paths)
        ):
            issues.append(SourceBindingIssue("allowed_delta_partition_mismatch"))
        if authorities_valid and not _durable_authority_rows_valid(
            authorities, allowed_paths=set(paths)
        ):
            issues.append(SourceBindingIssue("durable_authority_invalid"))
    trailers = record.get("prior_control_trailers")
    if not isinstance(trailers, list) or any(
        not isinstance(row, Mapping)
        or set(row) != {"commit", "transaction_id", "normalized_control_sha256"}
        or not isinstance(row.get("commit"), str) or _HEX40_RE.fullmatch(row["commit"]) is None
        or not isinstance(row.get("transaction_id"), str) or re.fullmatch(r"[0-9a-f]{64}", row["transaction_id"]) is None
        or not isinstance(row.get("normalized_control_sha256"), str) or _SHA256_RE.fullmatch(row["normalized_control_sha256"]) is None
        for row in trailers or []
    ):
        issues.append(SourceBindingIssue("prior_control_trailers_invalid"))
    if not isinstance(record.get("expected_commit_tree_oid"), str) or _HEX40_RE.fullmatch(record["expected_commit_tree_oid"]) is None:
        issues.append(SourceBindingIssue("expected_commit_tree_invalid"))
    external_specs = {
        "pathspec_file_binding": {"path", "sha256", "byte_count", "row_count", "encoding"},
        "base_message_binding": {"path", "sha256", "byte_count"},
        "final_message_binding": {"path", "sha256", "byte_count", "cleanup"},
    }
    external_names = {
        "pathspec_file_binding": "paths.nul",
        "base_message_binding": "message.txt",
        "final_message_binding": "final-message.txt",
    }
    for field, keys in external_specs.items():
        value = record.get(field)
        expected_path = (
            f".git/retirement-commit-controls/{transaction}/{external_names[field]}"
            if isinstance(transaction, str)
            and re.fullmatch(r"[0-9a-f]{64}", transaction) is not None
            else None
        )
        valid = (
            isinstance(value, Mapping) and set(value) == keys
            and _valid_relative(value.get("path"))
            and value.get("path") == expected_path
            and isinstance(value.get("sha256"), str) and _SHA256_RE.fullmatch(value["sha256"]) is not None
            and type(value.get("byte_count")) is int and value["byte_count"] >= 0
        )
        if field == "pathspec_file_binding":
            valid = valid and type(value.get("row_count")) is int and value["row_count"] == record.get("allowed_delta_count") and value.get("encoding") == "nul_terminated_literal_paths"
        if field == "final_message_binding":
            valid = valid and value.get("cleanup") == "verbatim"
        if not valid:
            issues.append(SourceBindingIssue(f"{field}_invalid"))
    if not _valid_claims(record.get("claims_not_made")):
        issues.append(SourceBindingIssue("claims_not_made_invalid"))
    if record.get("normalized_control_sha256") != _canonical_sha256(record, exclude={"normalized_control_sha256", "final_message_binding"}):
        issues.append(SourceBindingIssue("control_digest_mismatch"))
    return issues


def validate_workspace_record_shape(record: Any) -> list[SourceBindingIssue]:
    """Validate a registered source fixture without consulting a live repository."""

    if not isinstance(record, Mapping):
        return [SourceBindingIssue("record_not_object")]
    schema = record.get("schema_version")
    if schema == "workspace_baseline.v1":
        return sorted(set(_validate_workspace_shape(record, bootstrap=False)))
    if schema == "bootstrap_workspace_baseline.v1":
        return sorted(set(_validate_workspace_shape(record, bootstrap=True)))
    if schema == "non_target_queue_sources.v1":
        return sorted(set(_validate_non_target_shape(record)))
    if schema == "query.v1":
        return sorted(set(_validate_query_shape(record)))
    if schema == "precommit_control.v1":
        return sorted(set(_validate_precommit_control_shape(record)))
    return [SourceBindingIssue("schema_version_mismatch")]


def _addition_allowed(path: str, allowed: set[str]) -> bool:
    return path in allowed


def _same_or_descendant(path: str, parent: str) -> bool:
    return path == parent or path.startswith(parent + "/")


def _validate_workspace_live(
    root: Path,
    record: Mapping[str, Any],
    *,
    allowed_additions: Sequence[str],
    committed_head: str | None = None,
    committed_paths: Sequence[str] = (),
) -> list[SourceBindingIssue]:
    issues: list[SourceBindingIssue] = []
    try:
        normalized_allowed = [_relative_path(path) for path in allowed_additions]
    except SourceBindingError as exc:
        return [SourceBindingIssue("allowed_addition_partition_invalid", detail=str(exc))]
    if normalized_allowed != sorted(set(normalized_allowed)):
        return [SourceBindingIssue("allowed_addition_partition_invalid")]
    try:
        normalized_committed = [_relative_path(path) for path in committed_paths]
    except SourceBindingError as exc:
        return [
            SourceBindingIssue(
                "committed_path_partition_invalid", detail=str(exc)
            )
        ]
    if (
        normalized_committed != sorted(set(normalized_committed))
        or set(normalized_allowed) & set(normalized_committed)
        or (
            normalized_committed
            and (
                not isinstance(committed_head, str)
                or _HEX40_RE.fullmatch(committed_head) is None
            )
        )
    ):
        return [SourceBindingIssue("committed_path_partition_invalid")]
    try:
        live_status, live_index, _, _ = _capture_git(root)
    except SourceBindingError as exc:
        return [SourceBindingIssue("workspace_capture_failed", detail=str(exc))]
    baseline_entries = {row["path"]: row for row in record.get("dirty_entries", []) if isinstance(row, dict) and isinstance(row.get("path"), str)}
    baseline_paths = set(baseline_entries)
    protected_entries = {
        row["path"]: row
        for row in record.get("protected_paths", [])
        if isinstance(row, dict) and isinstance(row.get("path"), str)
    }
    allowed = set(normalized_allowed)
    if baseline_paths & allowed:
        issues.append(SourceBindingIssue("allowed_addition_intersects_baseline", sorted(baseline_paths & allowed)[0]))
    protected_overlaps = sorted(
        candidate
        for candidate in allowed
        if any(
            _same_or_descendant(candidate, protected)
            for protected in protected_entries
        )
    )
    if protected_overlaps:
        issues.append(
            SourceBindingIssue(
                "allowed_addition_intersects_protected", protected_overlaps[0]
            )
        )
    live_path_to_rows: dict[str, list[str]] = {}
    for row in live_status:
        for path in row["path_operands"]:
            live_path_to_rows.setdefault(path, []).append(row["row_id"])
    for path, expected in baseline_entries.items():
        try:
            observed = _snapshot_path(root, path, status_row_ids=expected.get("status_row_ids", []), index_entries=live_index)
        except SourceBindingError as exc:
            issues.append(SourceBindingIssue("dirty_entry_unreadable", path, str(exc)))
            continue
        # Row IDs are stable bindings to captured status rows, not recaptured IDs.
        observed["status_row_ids"] = expected.get("status_row_ids", [])
        observed["normalized_entry_sha256"] = _canonical_sha256(observed, exclude={"normalized_entry_sha256"})
        if observed != expected:
            issues.append(SourceBindingIssue("dirty_entry_changed", path))
    for path, expected in protected_entries.items():
        try:
            observed = _snapshot_path(
                root,
                path,
                status_row_ids=expected.get("status_row_ids", []),
                index_entries=live_index,
            )
        except SourceBindingError as exc:
            issues.append(SourceBindingIssue("protected_entry_unreadable", path, str(exc)))
            continue
        if observed != expected:
            issues.append(SourceBindingIssue("protected_entry_changed", path))
    expected_rows = record.get("status_rows", [])
    expected_by_operands = {(row.get("status"), tuple(row.get("path_operands", [])), row.get("path"), row.get("source_path")) for row in expected_rows if isinstance(row, dict)}
    live_baseline_rows = {(row.get("status"), tuple(row.get("path_operands", [])), row.get("path"), row.get("source_path")) for row in live_status if set(row.get("path_operands", [])) & baseline_paths}
    if live_baseline_rows != expected_by_operands:
        issues.append(SourceBindingIssue("baseline_status_rows_changed"))
    for path in sorted(set(live_path_to_rows) - baseline_paths):
        if not _addition_allowed(path, allowed):
            issues.append(SourceBindingIssue("outside_candidate_change", path))
    baseline_index = list(record.get("index_entries", []))
    committed_set = set(normalized_committed)
    if committed_set:
        baseline_index = [
            row for row in baseline_index if row.get("path") not in committed_set
        ]
        try:
            for path in normalized_committed:
                entry = _tree_entry(root, committed_head, path)
                if entry is not None:
                    baseline_index.append(entry)
        except SourceBindingError as exc:
            issues.append(
                SourceBindingIssue(
                    "committed_index_reconstruction_failed", detail=str(exc)
                )
            )
        baseline_index.sort(
            key=lambda row: (
                row.get("path", ""),
                row.get("stage", -1),
                row.get("mode", ""),
                row.get("oid", ""),
            )
        )
    candidate_paths = set(allowed)
    expected_preserved = [row for row in baseline_index if row.get("path") not in candidate_paths]
    observed_preserved = [row for row in live_index if row.get("path") not in candidate_paths]
    if expected_preserved != observed_preserved:
        issues.append(SourceBindingIssue("semantic_index_changed"))
    return sorted(set(issues))


def validate_workspace_baseline(repository_root: Path | str, record: Mapping[str, Any] | Path | str, allowed_additions: Sequence[str] = ()) -> list[SourceBindingIssue]:
    root = _repository_root(repository_root)
    record_path = Path(record) if isinstance(record, (str, Path)) else None
    if record_path is not None:
        value = _read_json(root, record_path)
    elif isinstance(record, Mapping):
        value = dict(record)
    else:
        return [SourceBindingIssue("record_not_object")]
    issues = validate_workspace_record_shape(value)
    if value.get("schema_version") != "workspace_baseline.v1":
        return sorted(set(issues))
    if not issues:
        issues.extend(_validate_workspace_live(root, value, allowed_additions=allowed_additions))
    return sorted(set(issues))


def validate_bootstrap_workspace(repository_root: Path | str, record: Mapping[str, Any] | Path | str, allowed_additions: Sequence[str] = ()) -> list[SourceBindingIssue]:
    root = _repository_root(repository_root)
    record_path = Path(record) if isinstance(record, (str, Path)) else None
    if record_path is not None:
        value = _read_json(root, record_path)
    elif isinstance(record, Mapping):
        value = dict(record)
    else:
        return [SourceBindingIssue("record_not_object")]
    issues = validate_workspace_record_shape(value)
    if value.get("schema_version") != "bootstrap_workspace_baseline.v1":
        return sorted(set(issues))
    if not issues:
        issues.extend(_validate_workspace_live(root, value, allowed_additions=allowed_additions))
    return sorted(set(issues))


def _archive_members(archive: bytes) -> tuple[tarfile.TarFile, dict[str, tarfile.TarInfo]]:
    try:
        opened = tarfile.open(fileobj=io.BytesIO(archive), mode="r:")
    except (OSError, tarfile.TarError) as exc:
        raise SourceBindingError(f"invalid_bootstrap_archive:{exc}") from exc
    members: dict[str, tarfile.TarInfo] = {}
    try:
        for member in opened.getmembers():
            name = member.name
            if name in {".", "./"}:
                continue
            if name.startswith("./"):
                name = name[2:]
            name = name.rstrip("/") if member.isdir() else name
            normalized = _relative_path(name)
            if normalized == ".git" or normalized.startswith(".git/"):
                raise SourceBindingError("bootstrap_archive_contains_git")
            if normalized in members:
                raise SourceBindingError(f"duplicate_archive_member:{normalized}")
            if not (member.isfile() or member.isdir() or member.issym()):
                raise SourceBindingError(f"unsupported_file_type:{normalized}")
            members[normalized] = member
    except Exception:
        opened.close()
        raise
    return opened, members


def _archive_snapshot(
    opened: tarfile.TarFile,
    members: Mapping[str, tarfile.TarInfo],
    relative: str,
    *,
    status_row_ids: Sequence[str],
    index_entries: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    member = members.get(relative)
    matching_index = [dict(row) for row in index_entries if row["path"] == relative]
    if member is None:
        existence = "absent"
        file_type = "absent"
        mode = None
        content: dict[str, Any] = {"kind": "absent", "size": None, "sha256": None}
    elif member.isfile():
        extracted = opened.extractfile(member)
        if extracted is None:
            raise SourceBindingError(f"archive_member_unreadable:{relative}")
        data = extracted.read()
        existence = "present"
        file_type = "regular"
        mode = member.mode
        content = {"kind": "regular", "size": len(data), "sha256": _sha256_bytes(data)}
    elif member.issym():
        target = member.linkname.encode("utf-8")
        existence = "present"
        file_type = "symlink"
        mode = member.mode
        content = {"kind": "symlink", "target_length": len(target), "target_sha256": _sha256_bytes(target)}
    elif member.isdir():
        if any(row["mode"] == "160000" for row in matching_index):
            raise SourceBindingError(f"bootstrap_gitlink_unsupported:{relative}")
        prefix = relative + "/"
        descendants: list[dict[str, Any]] = []
        for child_path, child in sorted(members.items()):
            if not child_path.startswith(prefix):
                continue
            child_relative = child_path[len(prefix) :]
            if child.isfile():
                extracted = opened.extractfile(child)
                if extracted is None:
                    raise SourceBindingError(f"archive_member_unreadable:{child_path}")
                data = extracted.read()
                descendants.append({"path": child_relative, "file_type": "regular", "lstat_mode": child.mode, "size": len(data), "sha256": _sha256_bytes(data)})
            elif child.issym():
                target = child.linkname.encode("utf-8")
                descendants.append({"path": child_relative, "file_type": "symlink", "lstat_mode": child.mode, "size": len(target), "sha256": _sha256_bytes(target)})
            else:
                descendants.append({"path": child_relative, "file_type": "directory", "lstat_mode": child.mode, "size": None, "sha256": None})
        content = {"kind": "directory", "descendants": descendants, "descendant_count": len(descendants), "descendant_set_sha256": _set_digest(descendants)}
        existence = "present"
        file_type = "directory"
        mode = member.mode
    else:  # pragma: no cover - filtered while indexing the archive
        raise SourceBindingError(f"unsupported_file_type:{relative}")
    row: dict[str, Any] = {
        "path": relative,
        "status_row_ids": sorted(set(status_row_ids)),
        "existence": existence,
        "file_type": file_type,
        "lstat_mode": mode,
        "index_entries": matching_index,
        "content_binding": content,
    }
    row["normalized_entry_sha256"] = _canonical_sha256(row, exclude={"normalized_entry_sha256"})
    return row


def adopt_bootstrap_workspace(repository_root: Path | str, bootstrap_root: Path | str) -> dict[str, Any]:
    """Adopt a private pre-first-write capture without persisting its bytes."""
    root = _repository_root(repository_root)
    capture = Path(bootstrap_root).absolute()
    capture_descriptor = -1
    try:
        capture_descriptor = os.open(
            capture,
            os.O_RDONLY
            | os.O_DIRECTORY
            | os.O_NOFOLLOW
            | getattr(os, "O_CLOEXEC", 0),
        )
        if stat.S_IMODE(os.fstat(capture_descriptor).st_mode) != 0o700:
            raise SourceBindingError("bootstrap_root_mode_mismatch")
        actual_names = set(os.listdir(capture_descriptor))
    except SourceBindingError:
        raise
    except OSError as exc:
        raise SourceBindingError(f"bootstrap_root_unreadable:{exc}") from exc
    finally:
        if capture_descriptor >= 0:
            os.close(capture_descriptor)
    expected_names = {"head.txt", "status.z", "index-entries.z", "index.sha256", "worktree.tar", "worktree.tar.sha256", "tar.stderr"}
    if actual_names != expected_names:
        raise SourceBindingError(f"bootstrap_capture_file_set_mismatch:{sorted(actual_names)!r}")
    raw = {name: _read_repository_bytes(capture, name) for name in expected_names}
    if raw["tar.stderr"]:
        raise SourceBindingError("bootstrap_capture_warning")
    expected_archive_sha = raw["worktree.tar.sha256"].decode("ascii").strip()
    if expected_archive_sha != hashlib.sha256(raw["worktree.tar"]).hexdigest():
        raise SourceBindingError("bootstrap_archive_digest_mismatch")
    head = raw["head.txt"].decode("ascii").strip()
    if not _HEX40_RE.fullmatch(head):
        raise SourceBindingError("bootstrap_head_invalid")
    index_sha = "sha256:" + raw["index.sha256"].decode("ascii").strip()
    if not _SHA256_RE.fullmatch(index_sha):
        raise SourceBindingError("bootstrap_index_digest_invalid")
    status_rows = _parse_status(raw["status.z"])
    index_entries = _parse_index(raw["index-entries.z"])
    path_to_rows: dict[str, list[str]] = {}
    for row in status_rows:
        for path in row["path_operands"]:
            path_to_rows.setdefault(path, []).append(row["row_id"])
    opened, members = _archive_members(raw["worktree.tar"])
    archive_member_paths = set(members)
    try:
        dirty_entries = [_archive_snapshot(opened, members, path, status_row_ids=row_ids, index_entries=index_entries) for path, row_ids in sorted(path_to_rows.items())]
    finally:
        opened.close()
    live_head = _git(root, "rev-parse", "HEAD").decode("ascii").strip()
    if live_head != head:
        raise SourceBindingError("bootstrap_head_changed")
    live_index_path = Path(_git(root, "rev-parse", "--path-format=absolute", "--git-path", "index").decode().strip())
    try:
        live_index_relative = live_index_path.relative_to(root)
        live_index_bytes = _read_repository_bytes(root, live_index_relative)
    except (ValueError, SourceBindingError) as exc:
        raise SourceBindingError(f"bootstrap_live_index_unreadable:{exc}") from exc
    if _sha256_bytes(live_index_bytes) != index_sha:
        raise SourceBindingError("bootstrap_index_changed")
    live_status_rows = _parse_status(
        _git(root, "status", "--porcelain=v1", "-z", "--untracked-files=all")
    )
    live_operands = {
        path for row in live_status_rows for path in row["path_operands"]
    }
    captured_operands = set(path_to_rows)
    preexisting_omissions = sorted(
        path
        for path in live_operands - captured_operands
        if path in archive_member_paths
    )
    if preexisting_omissions:
        raise SourceBindingError(
            f"archive_status_candidate_mismatch:{preexisting_omissions[0]}"
        )
    record: dict[str, Any] = {
        "schema_version": "bootstrap_workspace_baseline.v1",
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "head": head,
        "index_sha256": index_sha,
        "index_entries": index_entries,
        "index_entry_count": len(index_entries),
        "index_entry_set_sha256": _set_digest(index_entries),
        "status_rows": status_rows,
        "dirty_entries": dirty_entries,
        "dirty_entry_count": len(dirty_entries),
        "dirty_path_set_sha256": _path_list_digest(path_to_rows),
        "dirty_entry_set_sha256": _set_digest(dirty_entries),
        "protected_paths": [],
        "bootstrap_capture_bindings": {
            "producer_contract_version": "task1_first_write_capture.v1",
            "head_file_sha256": _sha256_bytes(raw["head.txt"]),
            "status_file_sha256": _sha256_bytes(raw["status.z"]),
            "index_entries_file_sha256": _sha256_bytes(raw["index-entries.z"]),
            "index_file_sha256": index_sha,
            "archive_sha256": _sha256_bytes(raw["worktree.tar"]),
            "tar_stderr_sha256": _sha256_bytes(raw["tar.stderr"]),
        },
        "raw_archive_not_persisted": True,
        "claims_not_made": [
            "The adopted baseline does not persist or claim ownership of captured user bytes.",
            "The adopted baseline does not authorize mutation outside the reviewed bootstrap candidate.",
        ],
    }
    record["normalized_baseline_sha256"] = _canonical_sha256(record, exclude={"normalized_baseline_sha256"})
    issues = _validate_workspace_live(root, record, allowed_additions=())
    if issues:
        raise SourceBindingError("bootstrap_live_mismatch:" + ",".join(issue.code for issue in issues))
    return record


def _handoff(document: Mapping[str, Any]) -> Mapping[str, Any]:
    if document.get("schema_version") == "procedure_first_yaml_retirement_handoff.v1":
        return document
    nested = document.get("yaml_retirement_handoff")
    if isinstance(nested, dict) and nested.get("schema_version") == "procedure_first_yaml_retirement_handoff.v1":
        return nested
    raise SourceBindingError("handoff_schema_mismatch")


def _handoff_queues(handoff: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    queues = handoff.get("queues")
    if not isinstance(queues, list):
        raise SourceBindingError("handoff_queues_invalid")
    result: dict[str, Mapping[str, Any]] = {}
    for row in queues:
        if not isinstance(row, dict) or not isinstance(row.get("queue_id"), str) or not isinstance(row.get("paths"), list):
            raise SourceBindingError("handoff_queue_invalid")
        queue_id = row["queue_id"]
        if queue_id in result:
            raise SourceBindingError(f"duplicate_queue_id:{queue_id}")
        paths = [_relative_path(path) for path in row["paths"]]
        if paths != sorted(set(paths)):
            raise SourceBindingError(f"queue_paths_not_sorted_unique:{queue_id}")
        result[queue_id] = row
    return result


def build_non_target_sources(
    repository_root: Path | str,
    handoff_path: Path | str,
    workspace_baseline_path: Path | str,
    tracked_queue_ids: Sequence[str],
    protected_queue_id: str,
) -> dict[str, Any]:
    root = _repository_root(repository_root)
    handoff_file = _relative_path(handoff_path)
    baseline_file = _relative_path(workspace_baseline_path)
    handoff_bytes = _read_repository_bytes(root, handoff_file)
    baseline_bytes = _read_repository_bytes(root, baseline_file)
    document = _json_object(handoff_bytes, handoff_file)
    queues = _handoff_queues(_handoff(document))
    requested = [*tracked_queue_ids, protected_queue_id]
    if len(requested) != len(set(requested)) or any(queue_id not in queues for queue_id in requested):
        raise SourceBindingError("non_target_queue_partition_invalid")
    baseline = _json_object(baseline_bytes, baseline_file)
    if _validate_workspace_shape(baseline, bootstrap=False):
        raise SourceBindingError("workspace_baseline_invalid")
    protected_by_path = {row["path"]: row for row in baseline["protected_paths"]}
    _, index_entries, _, _ = _capture_git(root)
    index_by_path: dict[str, list[Mapping[str, Any]]] = {}
    for entry in index_entries:
        index_by_path.setdefault(entry["path"], []).append(entry)
    source_rows: list[dict[str, Any]] = []
    for queue_id in tracked_queue_ids:
        for path in queues[queue_id]["paths"]:
            entries = index_by_path.get(path, [])
            if len(entries) != 1 or entries[0]["stage"] != 0 or entries[0]["mode"] == "160000":
                raise SourceBindingError(f"tracked_source_index_invalid:{path}")
            snapshot = _snapshot_path(root, path, status_row_ids=[], index_entries=index_entries)
            if snapshot["file_type"] != "regular":
                raise SourceBindingError(f"tracked_source_not_regular:{path}")
            source_rows.append({
                "queue_id": queue_id,
                "path": path,
                "disposition_owner": queue_id,
                "binding_source": "tracked_source_binding",
                "tracked_mode": entries[0]["mode"],
                "blob_oid": entries[0]["oid"],
                "lstat_mode": snapshot["lstat_mode"],
                "size": snapshot["content_binding"]["size"],
                "sha256": snapshot["content_binding"]["sha256"],
                "protected_binding": None,
            })
    for path in queues[protected_queue_id]["paths"]:
        protected = protected_by_path.get(path)
        if protected is None:
            raise SourceBindingError(f"protected_source_binding_missing:{path}")
        source_rows.append({
            "queue_id": protected_queue_id,
            "path": path,
            "disposition_owner": protected_queue_id,
            "binding_source": "workspace_protected_binding",
            "tracked_mode": None,
            "blob_oid": None,
            "lstat_mode": None,
            "size": None,
            "sha256": None,
            "protected_binding": {"path": path, "normalized_entry_sha256": protected["normalized_entry_sha256"]},
        })
    source_rows.sort(key=lambda row: row["path"])
    paths = [row["path"] for row in source_rows]
    if len(paths) != len(set(paths)):
        raise SourceBindingError("non_target_source_overlap")
    if len(source_rows) != 10 or sum(row["binding_source"] == "tracked_source_binding" for row in source_rows) != 9 or sum(row["binding_source"] == "workspace_protected_binding" for row in source_rows) != 1:
        raise SourceBindingError("non_target_source_count_invalid")
    if not _non_target_partition_valid(source_rows):
        raise SourceBindingError("non_target_queue_partition_invalid")
    record: dict[str, Any] = {
        "schema_version": "non_target_queue_sources.v1",
        "handoff_binding": {"path": handoff_file, "sha256": _sha256_bytes(handoff_bytes), "handoff_schema_version": _handoff(document)["schema_version"]},
        "workspace_baseline_binding": {"path": baseline_file, "sha256": _sha256_bytes(baseline_bytes), "schema_version": baseline["schema_version"], "protected_path_count": len(baseline["protected_paths"])},
        "source_rows": source_rows,
        "source_count": len(source_rows),
        "path_list_sha256": _path_list_digest(paths),
        "row_set_sha256": _set_digest(source_rows),
        "claims_not_made": ["This record does not authorize mutation of any bound source."],
    }
    record["normalized_record_sha256"] = _canonical_sha256(record, exclude={"normalized_record_sha256"})
    return record


def validate_non_target_sources(repository_root: Path | str, record: Mapping[str, Any] | Path | str) -> list[SourceBindingIssue]:
    root = _repository_root(repository_root)
    record_path = Path(record) if isinstance(record, (str, Path)) else None
    if record_path is not None:
        value = _read_json(root, record_path)
    elif isinstance(record, Mapping):
        value = dict(record)
    else:
        return [SourceBindingIssue("record_not_object")]
    issues = _validate_non_target_shape(value)
    if issues:
        return sorted(set(issues))
    rows = value["source_rows"]
    handoff_binding = value.get("handoff_binding", {})
    baseline_binding = value.get("workspace_baseline_binding", {})
    try:
        handoff_path = _relative_path(handoff_binding["path"])
        baseline_path = _relative_path(baseline_binding["path"])
        handoff_bytes = _read_repository_bytes(root, handoff_path)
        baseline_bytes = _read_repository_bytes(root, baseline_path)
        handoff = _handoff(_json_object(handoff_bytes, handoff_path))
        queues = _handoff_queues(handoff)
        if _sha256_bytes(handoff_bytes) != handoff_binding.get("sha256") or handoff["schema_version"] != handoff_binding.get("handoff_schema_version"):
            issues.append(SourceBindingIssue("handoff_binding_changed"))
        baseline = _json_object(baseline_bytes, baseline_path)
        if _sha256_bytes(baseline_bytes) != baseline_binding.get("sha256") or baseline.get("schema_version") != baseline_binding.get("schema_version"):
            issues.append(SourceBindingIssue("workspace_baseline_binding_changed"))
    except (KeyError, OSError, SourceBindingError) as exc:
        return sorted([*issues, SourceBindingIssue("source_authority_unreadable", detail=str(exc))])
    if not _non_target_authority_partition_matches(rows, queues):
        issues.append(SourceBindingIssue("source_authority_partition_mismatch"))
    protected_by_path = {row["path"]: row for row in baseline.get("protected_paths", [])}
    _, index_entries, _, _ = _capture_git(root)
    expected_row_keys = {"queue_id", "path", "disposition_owner", "binding_source", "tracked_mode", "blob_oid", "lstat_mode", "size", "sha256", "protected_binding"}
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("path"), str):
            issues.append(SourceBindingIssue("source_row_invalid"))
            continue
        path = row["path"]
        if set(row) != expected_row_keys:
            issues.append(SourceBindingIssue("source_row_schema_mismatch", path))
        queue_id = row.get("queue_id")
        queue = queues.get(queue_id) if isinstance(queue_id, str) else None
        if queue is None or path not in queue.get("paths", []) or row.get("disposition_owner") != queue_id:
            issues.append(SourceBindingIssue("source_queue_membership_mismatch", path))
        if row.get("binding_source") == "tracked_source_binding":
            if row.get("protected_binding") is not None:
                issues.append(SourceBindingIssue("tracked_source_union_mismatch", path))
            entries = [entry for entry in index_entries if entry["path"] == path]
            try:
                snapshot = _snapshot_path(root, path, status_row_ids=[], index_entries=index_entries)
            except SourceBindingError as exc:
                issues.append(SourceBindingIssue("source_unreadable", path, str(exc)))
                continue
            actual = entries[0] if len(entries) == 1 and entries[0]["stage"] == 0 else {}
            content = snapshot.get("content_binding", {})
            if snapshot.get("file_type") != "regular" or actual.get("mode") != row.get("tracked_mode") or actual.get("oid") != row.get("blob_oid") or snapshot.get("lstat_mode") != row.get("lstat_mode") or content.get("size") != row.get("size") or content.get("sha256") != row.get("sha256"):
                issues.append(SourceBindingIssue("tracked_source_changed", path))
        elif row.get("binding_source") == "workspace_protected_binding":
            if any(row.get(key) is not None for key in ("tracked_mode", "blob_oid", "lstat_mode", "size", "sha256")):
                issues.append(SourceBindingIssue("protected_source_union_mismatch", path))
            protected = protected_by_path.get(path)
            binding = row.get("protected_binding")
            if not isinstance(binding, dict) or protected is None or binding != {"path": path, "normalized_entry_sha256": protected.get("normalized_entry_sha256")}:
                issues.append(SourceBindingIssue("protected_source_binding_changed", path))
            else:
                observed = _snapshot_path(root, path, status_row_ids=protected.get("status_row_ids", []), index_entries=index_entries)
                if observed != protected:
                    issues.append(SourceBindingIssue("protected_source_changed", path))
        else:
            issues.append(SourceBindingIssue("binding_source_invalid", path))
    return sorted(set(issues))


def build_query(root: Path, handoff_path: Path | str, queue_id: str) -> dict[str, Any]:
    relative = _relative_path(handoff_path)
    data = _read_repository_bytes(root, relative)
    document = _json_object(data, relative)
    handoff = _handoff(document)
    queues = _handoff_queues(handoff)
    if queue_id not in queues:
        raise SourceBindingError(f"unknown_queue_id:{queue_id}")
    paths = list(queues[queue_id]["paths"])
    record: dict[str, Any] = {
        "schema_version": "query.v1",
        "authority": {"path": relative, "sha256": _sha256_bytes(data), "schema_version": handoff["schema_version"]},
        "queue_id": queue_id,
        "paths": paths,
        "path_count": len(paths),
        "path_encoding": "utf8_repository_relative_posix_lf.v1",
        "path_list_sha256": _path_list_digest(paths),
        "capture_commit": handoff.get("captured_at_commit"),
        "claims_not_made": ["This query does not authorize deletion or classify references."],
    }
    record["normalized_query_sha256"] = _canonical_sha256(record, exclude={"normalized_query_sha256"})
    return record


def materialize_query(repository_root: Path | str, handoff_path: Path | str, queue_id: str, generation: int, output_path: Path | str) -> dict[str, Any]:
    root = _repository_root(repository_root)
    handoff_file = Path(_relative_path(handoff_path))
    output_relative = Path(_relative_path(output_path))
    # Validate all caller-selectable data before entering the publication lock.
    query = build_query(root, handoff_file, queue_id)
    try:
        from .materialization import materialize_transaction
    except ImportError as exc:  # pragma: no cover - bootstrap import ordering
        raise SourceBindingError("materialization_unavailable") from exc
    receipt = materialize_transaction(
        repository_root=root,
        evidence_root=output_relative.parent,
        record_kind="query",
        output_path=output_relative,
        generation=generation,
        input_paths={"handoff": handoff_file},
        parameters={"queue_id": queue_id, "capture_commit": query["capture_commit"]},
    )
    return receipt.as_dict() if hasattr(receipt, "as_dict") else dict(receipt)


def _binding(root: Path, path: Path) -> dict[str, Any]:
    relative = _relative_path(path)
    data = _read_repository_bytes(root, relative)
    schema = None
    try:
        schema = _json_object(data, relative).get("schema_version")
    except SourceBindingError:
        pass
    return {"path": relative, "size": len(data), "sha256": _sha256_bytes(data), "schema_version": schema}


def _index_binding(root: Path, entries: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    return {"entry_count": len(entries), "entry_set_sha256": _set_digest(entries)}


def _tree_entries(root: Path, commit: str) -> list[dict[str, Any]]:
    raw = _git(root, "ls-tree", "-r", "-z", commit)
    result: list[dict[str, Any]] = []
    for record in raw.removesuffix(b"\0").split(b"\0") if raw else []:
        prefix, raw_path = record.split(b"\t", 1)
        mode, _kind, oid = prefix.decode("ascii").split(" ")
        result.append({"path": _decode_path(raw_path), "stage": 0, "mode": mode, "oid": oid})
    return sorted(result, key=lambda row: (row["path"], row["stage"], row["mode"], row["oid"]))


def _raw_commit_message(root: Path, commit: str) -> bytes:
    raw = _git(root, "cat-file", "commit", commit)
    separator = raw.find(b"\n\n")
    if separator < 0:
        raise SourceBindingError("commit_message_separator_missing")
    return raw[separator + 2 :]


def _trailer_coordinates(message: bytes) -> tuple[str, str] | None:
    pattern = re.compile(rb"\nRetirement-Control-Schema: precommit_control\.v1\nRetirement-Transaction-ID: ([0-9a-f]{64})\nRetirement-Control-SHA256: ([0-9a-f]{64})\n\Z")
    matches = list(pattern.finditer(message))
    if not matches:
        return None
    if len(matches) != 1:
        raise SourceBindingError("commit_control_trailer_invalid")
    return matches[0].group(1).decode("ascii"), "sha256:" + matches[0].group(2).decode("ascii")


def derive_committed_predecessor_lineage(
    repository_root: Path | str,
    *,
    baseline_head: str,
    intended_predecessor_head: str,
    require_uncovered_paths: bool = False,
) -> dict[str, Any]:
    """Project the closed first-parent delta between two committed states.

    A valid retirement-control trailer covers only the paths changed by that
    particular commit.  The projection deliberately retains a path in both
    aggregate coverage sets when separate commit occurrences changed it under
    different control states.
    """

    root = _repository_root(repository_root)
    for name, value in (
        ("baseline_head", baseline_head),
        ("intended_predecessor_head", intended_predecessor_head),
    ):
        if not isinstance(value, str) or _HEX40_RE.fullmatch(value) is None:
            raise SourceBindingError(f"{name}_invalid")
        resolved = _git(root, "rev-parse", "--verify", f"{value}^{{commit}}")
        if resolved.decode("ascii", "strict").strip() != value:
            raise SourceBindingError(f"{name}_invalid")

    merge_base = _git(root, "merge-base", baseline_head, intended_predecessor_head)
    if merge_base.decode("ascii", "strict").strip() != baseline_head:
        raise SourceBindingError("predecessor_baseline_not_ancestor")

    commits = (
        _git(
            root,
            "rev-list",
            "--first-parent",
            "--reverse",
            f"{baseline_head}..{intended_predecessor_head}",
        )
        .decode("ascii", "strict")
        .splitlines()
    )
    if commits and commits[-1] != intended_predecessor_head:
        raise SourceBindingError("predecessor_first_parent_lineage_invalid")
    if not commits and baseline_head != intended_predecessor_head:
        raise SourceBindingError("predecessor_first_parent_lineage_invalid")

    commit_rows: list[dict[str, Any]] = []
    changed: set[str] = set()
    controlled: set[str] = set()
    uncovered: set[str] = set()
    expected_parent = baseline_head
    for commit in commits:
        parents = (
            _git(root, "rev-list", "--parents", "-n", "1", commit)
            .decode("ascii", "strict")
            .split()
        )
        if len(parents) != 2 or parents[0] != commit:
            raise SourceBindingError("predecessor_merge_topology_invalid")
        parent = parents[1]
        if parent != expected_parent:
            raise SourceBindingError("predecessor_first_parent_lineage_invalid")

        raw_paths = _git(
            root,
            "diff-tree",
            "--no-commit-id",
            "--name-only",
            "--no-renames",
            "-r",
            "-z",
            commit,
        )
        path_fields = raw_paths.split(b"\0")
        if path_fields[-1:] == [b""]:
            path_fields.pop()
        paths = [_decode_path(field) for field in path_fields]
        if len(paths) != len(set(paths)):
            raise SourceBindingError("duplicate_predecessor_path")
        paths.sort()

        message = _raw_commit_message(root, commit)
        coordinates = _trailer_coordinates(message)
        marker_present = (
            b"Retirement-Control-" in message
            or b"Retirement-Transaction-ID:" in message
        )
        if coordinates is None and marker_present:
            raise SourceBindingError("commit_control_trailer_invalid")
        if coordinates is not None:
            canonical_trailer = (
                b"\nRetirement-Control-Schema: precommit_control.v1\n"
                b"Retirement-Transaction-ID: "
                + coordinates[0].encode("ascii")
                + b"\nRetirement-Control-SHA256: "
                + coordinates[1].removeprefix("sha256:").encode("ascii")
                + b"\n"
            )
            prefix = message.removesuffix(canonical_trailer)
            if (
                len(prefix) + len(canonical_trailer) != len(message)
                or b"Retirement-Control-" in prefix
                or b"Retirement-Transaction-ID:" in prefix
            ):
                raise SourceBindingError("commit_control_trailer_invalid")

        tree = _git(root, "rev-parse", f"{commit}^{{tree}}").decode("ascii").strip()
        control_coordinates = (
            None
            if coordinates is None
            else {
                "transaction_id": coordinates[0],
                "normalized_control_sha256": coordinates[1],
            }
        )
        commit_rows.append(
            {
                "commit": commit,
                "parent": parent,
                "tree": tree,
                "raw_message_sha256": _sha256_bytes(message),
                "changed_paths": paths,
                "changed_path_set_sha256": _path_list_digest(paths),
                "control_coordinates": control_coordinates,
            }
        )
        changed.update(paths)
        (controlled if coordinates is not None else uncovered).update(paths)
        expected_parent = commit

    changed_paths = sorted(changed)
    controlled_paths = sorted(controlled)
    uncovered_paths = sorted(uncovered)
    if require_uncovered_paths and not uncovered_paths:
        raise SourceBindingError("predecessor_uncovered_paths_required")

    projection: dict[str, Any] = {
        "baseline_head": baseline_head,
        "intended_predecessor_head": intended_predecessor_head,
        "intended_predecessor_tree": _git(
            root, "rev-parse", f"{intended_predecessor_head}^{{tree}}"
        )
        .decode("ascii", "strict")
        .strip(),
        "first_parent_commits": commit_rows,
        "commit_count": len(commit_rows),
        "changed_paths": changed_paths,
        "changed_path_count": len(changed_paths),
        "changed_path_set_sha256": _path_list_digest(changed_paths),
        "controlled_paths": controlled_paths,
        "controlled_path_set_sha256": _path_list_digest(controlled_paths),
        "uncovered_paths": uncovered_paths,
        "uncovered_path_set_sha256": _path_list_digest(uncovered_paths),
    }
    projection["normalized_projection_sha256"] = _canonical_sha256(projection)
    return projection


def _prior_trailers(root: Path, baseline_head: str, base_head: str) -> list[dict[str, str]]:
    if baseline_head == base_head:
        return []
    commits = _git(root, "rev-list", "--first-parent", "--reverse", f"{baseline_head}..{base_head}").decode("ascii").splitlines()
    rows: list[dict[str, str]] = []
    for commit in commits:
        coordinates = _trailer_coordinates(_raw_commit_message(root, commit))
        if coordinates is not None:
            rows.append({"commit": commit, "transaction_id": coordinates[0], "normalized_control_sha256": coordinates[1]})
    return rows


def _prior_control_paths(
    root: Path, trailers: Sequence[Mapping[str, Any]]
) -> list[str]:
    paths: set[str] = set()
    for trailer in trailers:
        raw = _git(
            root,
            "diff-tree",
            "--no-commit-id",
            "--name-only",
            "-r",
            "-z",
            trailer["commit"],
        )
        paths.update(_decode_path(item) for item in raw.split(b"\0") if item)
    return sorted(paths)


def _tree_entry(root: Path, commit: str, path: str) -> dict[str, Any] | None:
    raw = _git(root, "ls-tree", "-z", commit, "--", path)
    if not raw:
        return None
    records = raw.removesuffix(b"\0").split(b"\0")
    if len(records) != 1:
        raise SourceBindingError(f"tree_entry_ambiguous:{path}")
    try:
        prefix, raw_path = records[0].split(b"\t", 1)
        mode, _kind, oid = prefix.decode("ascii").split(" ")
        decoded = _decode_path(raw_path)
    except (ValueError, UnicodeDecodeError) as exc:
        raise SourceBindingError(f"tree_entry_malformed:{path}") from exc
    if decoded != path:
        raise SourceBindingError(f"tree_entry_ambiguous:{path}")
    return {"path": path, "stage": 0, "mode": mode, "oid": oid}


def _changed_paths(root: Path, base: str) -> list[str]:
    raw = _git(root, "diff", "--cached", "--name-only", "-z", base, "--")
    fields = raw.split(b"\0")
    if fields[-1:] == [b""]:
        fields.pop()
    paths = [_decode_path(field) for field in fields]
    if len(paths) != len(set(paths)):
        raise SourceBindingError("duplicate_staged_path")
    return sorted(paths)


def _unstaged_paths(root: Path, paths: Sequence[str]) -> list[str]:
    if not paths:
        return []
    raw = _git(
        root,
        "--literal-pathspecs",
        "diff",
        "--name-only",
        "-z",
        "--",
        *paths,
    )
    return sorted(_decode_path(item) for item in raw.split(b"\0") if item)


def _expected_tree(root: Path, base: str, allowed_paths: Sequence[str], index_entries: Sequence[Mapping[str, Any]]) -> str:
    index_by_path = {row["path"]: row for row in index_entries if row["stage"] == 0}
    descriptor, temporary_name = tempfile.mkstemp(prefix="retirement-index-")
    os.close(descriptor)
    os.unlink(temporary_name)
    env = {"GIT_INDEX_FILE": temporary_name}
    try:
        _git(root, "read-tree", base, env=env)
        for path in allowed_paths:
            entry = index_by_path.get(path)
            if entry is None:
                _git(root, "update-index", "--force-remove", "--", path, env=env)
            else:
                _git(root, "update-index", "--add", "--cacheinfo", entry["mode"], entry["oid"], path, env=env)
        tree = _git(root, "write-tree", env=env).decode("ascii").strip()
    finally:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
    if not _HEX40_RE.fullmatch(tree):
        raise SourceBindingError("expected_tree_invalid")
    return tree


def _derive_precommit_index_contract(
    root: Path,
    base_head: str,
    allowed_paths: Sequence[str],
    current_index: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any], str]:
    allowed = set(allowed_paths)
    current_by_path = {
        row["path"]: dict(row) for row in current_index if row["stage"] == 0
    }
    allowed_delta_rows: list[dict[str, Any]] = []
    for path in allowed_paths:
        allowed_delta_rows.append(
            {
                "path": path,
                "before": _tree_entry(root, base_head, path),
                "after": current_by_path.get(path),
            }
        )
    pre_index = [dict(row) for row in current_index if row["path"] not in allowed]
    for row in allowed_delta_rows:
        before = row["before"]
        if before is not None:
            pre_index.append(dict(before))
    pre_index.sort(
        key=lambda row: (row["path"], row["stage"], row["mode"], row["oid"])
    )
    return (
        allowed_delta_rows,
        _index_binding(root, pre_index),
        _index_binding(root, current_index),
        _expected_tree(root, base_head, allowed_paths, current_index),
    )


def _exclusive_bytes(root: Path, path: Path | str, data: bytes) -> None:
    _write_repository_bytes(root, path, data, exclusive=True)


def _derive_pathspec_bytes(allowed_delta_rows: Sequence[Mapping[str, Any]]) -> bytes:
    paths = sorted(row["path"] for row in allowed_delta_rows)
    return b"".join(path.encode("utf-8") + b"\0" for path in paths)


def _base_message_bytes_valid(value: bytes) -> bool:
    return (
        bool(value)
        and value.endswith(b"\n")
        and not value.endswith(b"\n\n")
        and b"\r" not in value
        and b"Retirement-Control-" not in value
    )


def _commit_subject_bytes(value: Any, *, error_code: str) -> bytes:
    if (
        not isinstance(value, str)
        or not value
        or "\r" in value
        or "\n" in value
        or "Retirement-Control-" in value
    ):
        raise SourceBindingError(error_code)
    try:
        encoded = value.encode("utf-8") + b"\n"
    except UnicodeEncodeError as exc:
        raise SourceBindingError(error_code) from exc
    if not _base_message_bytes_valid(encoded):
        raise SourceBindingError(error_code)
    return encoded


def _derive_final_message_bytes(
    base_message: bytes, transaction_id: str, normalized_control_sha256: str
) -> bytes:
    if not _base_message_bytes_valid(base_message):
        raise SourceBindingError("base_message_invalid")
    if re.fullmatch(r"[0-9a-f]{64}", transaction_id) is None:
        raise SourceBindingError("transaction_id_invalid")
    if _SHA256_RE.fullmatch(normalized_control_sha256) is None:
        raise SourceBindingError("normalized_control_sha256_invalid")
    return (
        base_message
        + b"\nRetirement-Control-Schema: precommit_control.v1\n"
        + b"Retirement-Transaction-ID: "
        + transaction_id.encode("ascii")
        + b"\nRetirement-Control-SHA256: "
        + normalized_control_sha256.removeprefix("sha256:").encode("ascii")
        + b"\n"
    )


def _bound_workspace_issues(
    root: Path,
    binding: Mapping[str, Any],
    *,
    expected_schema: str,
    allowed_additions: Sequence[str],
    committed_head: str | None = None,
    committed_paths: Sequence[str] = (),
) -> list[SourceBindingIssue]:
    try:
        observed_binding = _binding(root, Path(binding["path"]))
        record = _read_json(root, binding["path"])
    except (KeyError, SourceBindingError) as exc:
        return [SourceBindingIssue("workspace_binding_unreadable", detail=str(exc))]
    issues: list[SourceBindingIssue] = []
    if observed_binding != dict(binding):
        issues.append(SourceBindingIssue("workspace_binding_mismatch"))
    if record.get("schema_version") != expected_schema:
        issues.append(SourceBindingIssue("workspace_binding_schema_mismatch"))
        return sorted(set(issues))
    shape = _validate_workspace_shape(
        record, bootstrap=expected_schema == "bootstrap_workspace_baseline.v1"
    )
    if shape:
        issues.append(SourceBindingIssue("workspace_binding_record_invalid"))
        return sorted(set(issues))
    live = _validate_workspace_live(
        root,
        record,
        allowed_additions=allowed_additions,
        committed_head=committed_head,
        committed_paths=committed_paths,
    )
    if live:
        issues.append(SourceBindingIssue("workspace_binding_live_invalid"))
    return sorted(set(issues))


def _durable_authority_live_issues(
    root: Path,
    bindings: Sequence[Mapping[str, Any]],
    *,
    allowed_paths: set[str],
) -> list[SourceBindingIssue]:
    if not _durable_authority_rows_valid(
        bindings, allowed_paths=allowed_paths
    ):
        return [SourceBindingIssue("durable_authority_invalid")]
    issues: list[SourceBindingIssue] = []
    for binding in bindings:
        try:
            observed = _binding(root, Path(binding["path"]))
        except SourceBindingError as exc:
            issues.append(
                SourceBindingIssue(
                    "durable_authority_unreadable", binding["path"], str(exc)
                )
            )
            continue
        if observed != dict(binding):
            issues.append(
                SourceBindingIssue(
                    "durable_authority_binding_mismatch", binding["path"]
                )
            )
    return sorted(set(issues))


def _eligible_new_workspace_baselines(
    root: Path,
    *,
    base_head: str,
    allowed_paths: Sequence[str],
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for path in allowed_paths:
        if _tree_entry(root, base_head, path) is not None:
            continue
        try:
            binding = _binding(root, Path(path))
            schema = binding["schema_version"]
            if schema not in {
                "bootstrap_workspace_baseline.v1",
                "workspace_baseline.v1",
            }:
                continue
            record = _read_json(root, Path(path))
        except SourceBindingError:
            continue
        if not _validate_workspace_shape(
            record,
            bootstrap=schema == "bootstrap_workspace_baseline.v1",
        ) and record.get("head") == base_head:
            candidates.append(binding)
    return sorted(candidates, key=lambda row: row["path"])


def _latest_controlled_workspace_baseline_binding(
    root: Path, commit: str
) -> dict[str, Any] | None:
    ancestors = (
        _git(root, "rev-list", "--first-parent", commit)
        .decode("ascii")
        .splitlines()
    )
    for ancestor in ancestors:
        if _trailer_coordinates(_raw_commit_message(root, ancestor)) is None:
            continue
        prior_control, _, _, _ = _reconstruct_precommit_control(root, ancestor)
        prior_binding = (
            prior_control.get("bootstrap_workspace_baseline_binding")
            or prior_control.get("workspace_baseline_binding")
        )
        if not isinstance(prior_binding, dict):
            raise SourceBindingError("prior_workspace_baseline_binding_missing")
        return dict(prior_binding)
    return None


def _require_live_inherited_workspace_baseline(
    root: Path,
    binding: Mapping[str, Any],
    *,
    base_head: str,
    allowed_paths: Sequence[str],
) -> dict[str, Any]:
    try:
        path = binding["path"]
        observed = _binding(root, Path(path))
        record = _read_json(root, Path(path))
        parent_entry = _tree_entry(root, base_head, path)
        index_entries = [
            row
            for row in _parse_index(_git(root, "ls-files", "--stage", "-z"))
            if row["path"] == path
        ]
    except (KeyError, SourceBindingError) as exc:
        raise SourceBindingError("workspace_baseline_inheritance_invalid") from exc
    if (
        observed != dict(binding)
        or parent_entry is None
        or index_entries != [parent_entry]
    ):
        raise SourceBindingError("workspace_baseline_inheritance_invalid")
    schema = binding.get("schema_version")
    if schema not in {
        "bootstrap_workspace_baseline.v1",
        "workspace_baseline.v1",
    }:
        raise SourceBindingError("workspace_baseline_inheritance_invalid")
    try:
        prior_trailers = _prior_trailers(root, record["head"], base_head)
        prior_paths = _prior_control_paths(root, prior_trailers)
    except (KeyError, SourceBindingError) as exc:
        raise SourceBindingError(
            "workspace_baseline_inheritance_invalid"
        ) from exc
    if _bound_workspace_issues(
        root,
        binding,
        expected_schema=schema,
        allowed_additions=allowed_paths,
        committed_head=base_head,
        committed_paths=prior_paths,
    ):
        raise SourceBindingError("workspace_baseline_inheritance_invalid")
    return record


def _require_workspace_baseline_transition(
    *,
    inherited_binding: Mapping[str, Any] | None,
    selected_binding: Mapping[str, Any],
    selected_is_new: bool,
) -> None:
    selected_schema = selected_binding.get("schema_version")
    if inherited_binding is None:
        valid = (
            selected_is_new
            and selected_schema == "bootstrap_workspace_baseline.v1"
        )
    elif inherited_binding.get("schema_version") == "bootstrap_workspace_baseline.v1":
        valid = (
            selected_is_new
            and selected_schema == "workspace_baseline.v1"
        )
    elif inherited_binding.get("schema_version") == "workspace_baseline.v1":
        valid = (
            not selected_is_new
            and dict(selected_binding) == dict(inherited_binding)
        )
    else:
        valid = False
    if not valid:
        raise SourceBindingError("workspace_baseline_transition_invalid")


def _workspace_baseline_rows_preserved(
    inherited: Mapping[str, Any], selected: Mapping[str, Any]
) -> bool:
    selected_protected = selected.get("protected_paths", [])
    return (
        selected.get("dirty_entries") == inherited.get("dirty_entries")
        and isinstance(selected_protected, list)
        and all(
            row in selected_protected
            for row in inherited.get("protected_paths", [])
        )
    )


def _validate_precommit_workspace_baseline_selection(
    root: Path,
    *,
    base_head: str,
    allowed_paths: Sequence[str],
    baseline_binding: Mapping[str, Any],
) -> None:
    selected_path = baseline_binding["path"]
    new_candidates = _eligible_new_workspace_baselines(
        root,
        base_head=base_head,
        allowed_paths=allowed_paths,
    )
    inherited_binding = _latest_controlled_workspace_baseline_binding(
        root, base_head
    )
    inherited_record: dict[str, Any] | None = None
    if inherited_binding is not None:
        inherited_record = _require_live_inherited_workspace_baseline(
            root,
            inherited_binding,
            base_head=base_head,
            allowed_paths=allowed_paths,
        )
    selected_is_new = _tree_entry(root, base_head, selected_path) is None
    if selected_is_new:
        if new_candidates != [dict(baseline_binding)]:
            raise SourceBindingError("workspace_baseline_candidate_set_invalid")
    elif new_candidates:
        raise SourceBindingError("workspace_baseline_candidate_set_invalid")
    _require_workspace_baseline_transition(
        inherited_binding=inherited_binding,
        selected_binding=baseline_binding,
        selected_is_new=selected_is_new,
    )
    if inherited_record is not None and selected_is_new:
        try:
            selected_record = _read_json(root, Path(selected_path))
        except SourceBindingError as exc:
            raise SourceBindingError(
                "workspace_baseline_inheritance_invalid"
            ) from exc
        if not _workspace_baseline_rows_preserved(
            inherited_record, selected_record
        ):
            raise SourceBindingError("workspace_baseline_inheritance_invalid")


def build_precommit_control(
    repository_root: Path | str,
    *,
    allowed_paths: Sequence[str],
    durable_authority_paths: Sequence[Path | str],
    commit_subject: str,
    bootstrap_workspace_baseline: Path | str | None = None,
    workspace_baseline: Path | str | None = None,
    prior_control_trailers: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """Derive the external NUL pathspec and exact commit-message contract."""
    root = _repository_root(repository_root)
    allowed = sorted({_relative_path(path) for path in allowed_paths})
    if not allowed or len(allowed) != len(allowed_paths):
        raise SourceBindingError("allowed_path_set_invalid")
    if (bootstrap_workspace_baseline is None) == (workspace_baseline is None):
        raise SourceBindingError("workspace_binding_partition_invalid")
    base_message = _commit_subject_bytes(
        commit_subject, error_code="commit_subject_invalid"
    )
    authority_paths = [_relative_path(path) for path in durable_authority_paths]
    if (
        not authority_paths
        or len(authority_paths) > 20
        or len(set(authority_paths)) != len(authority_paths)
        or not set(authority_paths) <= set(allowed)
    ):
        raise SourceBindingError("durable_authority_set_invalid")
    base_head = _git(root, "rev-parse", "HEAD").decode("ascii").strip()
    staged_paths = _changed_paths(root, base_head)
    unexpected = sorted(set(staged_paths) - set(allowed))
    missing = sorted(set(allowed) - set(staged_paths))
    unstaged_allowed = _unstaged_paths(root, allowed)
    # Unrelated pre-existing staged rows are permitted only when represented by
    # the immutable baseline.  They remain in the ambient index but not tree.
    baseline_path = bootstrap_workspace_baseline or workspace_baseline
    assert baseline_path is not None
    baseline_relative = Path(_relative_path(baseline_path))
    baseline = _read_json(root, baseline_relative)
    expected_baseline_schema = (
        "bootstrap_workspace_baseline.v1"
        if bootstrap_workspace_baseline is not None
        else "workspace_baseline.v1"
    )
    if baseline.get("schema_version") != expected_baseline_schema or _validate_workspace_shape(
        baseline, bootstrap=bootstrap_workspace_baseline is not None
    ):
        raise SourceBindingError("workspace_baseline_invalid:workspace_binding_record_invalid")
    baseline_binding = _binding(root, baseline_relative)
    derived_prior_trailers = _prior_trailers(root, baseline["head"], base_head)
    if prior_control_trailers and list(prior_control_trailers) != derived_prior_trailers:
        raise SourceBindingError("prior_control_trailer_chain_mismatch")
    _validate_precommit_workspace_baseline_selection(
        root,
        base_head=base_head,
        allowed_paths=allowed,
        baseline_binding=baseline_binding,
    )
    if unstaged_allowed:
        raise SourceBindingError(
            f"allowed_path_worktree_index_mismatch:{unstaged_allowed[0]}"
        )
    prior_paths = _prior_control_paths(root, derived_prior_trailers)
    baseline_issues = _bound_workspace_issues(
        root,
        baseline_binding,
        expected_schema=expected_baseline_schema,
        allowed_additions=allowed,
        committed_head=base_head,
        committed_paths=prior_paths,
    )
    if baseline_issues:
        raise SourceBindingError(
            f"workspace_baseline_invalid:{baseline_issues[0].code}"
        )
    baseline_dirty = {row["path"] for row in baseline.get("dirty_entries", [])}
    if set(allowed) & baseline_dirty:
        raise SourceBindingError("allowed_path_intersects_baseline")
    if missing:
        raise SourceBindingError(f"allowed_path_not_staged:{missing[0]}")
    if unexpected and not set(unexpected).issubset(baseline_dirty):
        raise SourceBindingError(f"unrelated_staged_drift:{unexpected[0]}")
    _, current_index, _, _ = _capture_git(root)
    (
        allowed_delta_rows,
        pre_commit_index_binding,
        expected_index_binding,
        expected_commit_tree_oid,
    ) = _derive_precommit_index_contract(root, base_head, allowed, current_index)
    authorities = sorted(
        (_binding(root, Path(path)) for path in authority_paths),
        key=lambda row: row["path"],
    )
    if not _durable_authority_rows_valid(
        authorities, allowed_paths=set(allowed)
    ):
        raise SourceBindingError("durable_authority_empty")
    authority_digest = _set_digest(authorities)
    transaction_id = hashlib.sha256(b"precommit-control.v1\0" + base_head.encode("ascii") + b"\0" + authority_digest.removeprefix("sha256:").encode("ascii")).hexdigest()
    control_root = Path(_git(root, "rev-parse", "--path-format=absolute", "--git-path", f"retirement-commit-controls/{transaction_id}").decode().strip())
    pathspec = _derive_pathspec_bytes(allowed_delta_rows)
    pathspec_path = control_root / "paths.nul"
    base_path = control_root / "message.txt"
    final_path = control_root / "final-message.txt"
    control_path = control_root / "control.json"
    bootstrap_binding = baseline_binding if bootstrap_workspace_baseline is not None else None
    workspace_binding = baseline_binding if workspace_baseline is not None else None
    control: dict[str, Any] = {
        "schema_version": "precommit_control.v1",
        "transaction_id": transaction_id,
        "bootstrap_workspace_baseline_binding": bootstrap_binding,
        "workspace_baseline_binding": workspace_binding,
        "durable_authority_bindings": authorities,
        "durable_authority_set_sha256": authority_digest,
        "prior_control_trailers": derived_prior_trailers,
        "base_head": base_head,
        "pre_commit_index_binding": pre_commit_index_binding,
        "allowed_delta_rows": allowed_delta_rows,
        "allowed_delta_count": len(allowed_delta_rows),
        "allowed_path_set_sha256": _path_list_digest(allowed),
        "expected_index_binding": expected_index_binding,
        "expected_commit_tree_oid": expected_commit_tree_oid,
        "pathspec_file_binding": {"path": pathspec_path.relative_to(root).as_posix(), "sha256": _sha256_bytes(pathspec), "byte_count": len(pathspec), "row_count": len(allowed), "encoding": "nul_terminated_literal_paths"},
        "base_message_binding": {"path": base_path.relative_to(root).as_posix(), "sha256": _sha256_bytes(base_message), "byte_count": len(base_message)},
        "final_message_binding": None,
        "claims_not_made": ["This control does not invoke Git commit or authorize an ambient-index commit."],
    }
    control["normalized_control_sha256"] = _canonical_sha256(control, exclude={"normalized_control_sha256", "final_message_binding"})
    final_message = _derive_final_message_bytes(
        base_message, transaction_id, control["normalized_control_sha256"]
    )
    control["final_message_binding"] = {"path": final_path.relative_to(root).as_posix(), "sha256": _sha256_bytes(final_message), "byte_count": len(final_message), "cleanup": "verbatim"}
    shape_issues = _validate_precommit_control_shape(control)
    if shape_issues:
        raise SourceBindingError(f"precommit_control_invalid:{shape_issues[0].code}")
    _exclusive_bytes(root, pathspec_path.relative_to(root), pathspec)
    _exclusive_bytes(root, base_path.relative_to(root), base_message)
    _exclusive_bytes(root, final_path.relative_to(root), final_message)
    _exclusive_bytes(root, control_path.relative_to(root), _canonical_bytes(control) + b"\n")
    return {"transaction_id": transaction_id, "control_path": control_path.relative_to(root).as_posix(), "pathspec_path": pathspec_path.relative_to(root).as_posix(), "final_message_path": final_path.relative_to(root).as_posix(), "normalized_control_sha256": control["normalized_control_sha256"]}


def _blob_bytes(root: Path, commit: str, path: str) -> bytes:
    return _git(root, "show", f"{commit}:{path}")


def _blob_binding(root: Path, commit: str, path: str) -> dict[str, Any]:
    data = _blob_bytes(root, commit, path)
    schema = None
    try:
        value = json.loads(data.decode("utf-8"), object_pairs_hook=_strict_object)
        if isinstance(value, dict):
            schema = value.get("schema_version")
    except (UnicodeError, json.JSONDecodeError, SourceBindingError):
        pass
    return {"path": path, "size": len(data), "sha256": _sha256_bytes(data), "schema_version": schema}


def _reconstruct_precommit_control(root: Path, commit: str) -> tuple[dict[str, Any], bytes, bytes, bytes]:
    commit_oid = _git(root, "rev-parse", commit).decode("ascii").strip()
    parent = _git(root, "rev-parse", f"{commit_oid}^").decode("ascii").strip()
    message = _raw_commit_message(root, commit_oid)
    coordinates = _trailer_coordinates(message)
    if coordinates is None:
        raise SourceBindingError("commit_control_trailer_missing")
    transaction_id, normalized_control_sha = coordinates
    suffix = b"\nRetirement-Control-Schema: precommit_control.v1\nRetirement-Transaction-ID: " + transaction_id.encode("ascii") + b"\nRetirement-Control-SHA256: " + normalized_control_sha.removeprefix("sha256:").encode("ascii") + b"\n"
    if not message.endswith(suffix) or message.count(suffix) != 1:
        raise SourceBindingError("commit_control_trailer_invalid")
    base_message = message[: -len(suffix)]
    if not _base_message_bytes_valid(base_message):
        raise SourceBindingError("base_message_inverse_invalid")
    if (
        _derive_final_message_bytes(
            base_message, transaction_id, normalized_control_sha
        )
        != message
    ):
        raise SourceBindingError("final_message_inverse_invalid")
    allowed_paths_raw = _git(root, "diff-tree", "--no-commit-id", "--name-only", "-r", "-z", commit_oid)
    allowed_paths = sorted(_decode_path(item) for item in allowed_paths_raw.split(b"\0") if item)
    if not allowed_paths or len(allowed_paths) != len(set(allowed_paths)):
        raise SourceBindingError("committed_path_set_invalid")
    inherited_binding = _latest_controlled_workspace_baseline_binding(root, parent)
    inherited_current: dict[str, Any] | None = None
    inherited_record: dict[str, Any] | None = None
    if inherited_binding is not None:
        try:
            inherited_path = inherited_binding["path"]
            parent_entry = _tree_entry(root, parent, inherited_path)
            child_entry = _tree_entry(root, commit_oid, inherited_path)
            parent_binding = _blob_binding(root, parent, inherited_path)
            inherited_current = _blob_binding(
                root, commit_oid, inherited_path
            )
            inherited_record = json.loads(
                _blob_bytes(root, parent, inherited_path).decode("utf-8"),
                object_pairs_hook=_strict_object,
            )
        except (
            KeyError,
            UnicodeError,
            json.JSONDecodeError,
            SourceBindingError,
        ) as exc:
            raise SourceBindingError(
                "workspace_baseline_changed_since_prior_control"
            ) from exc
        if (
            parent_entry is None
            or child_entry != parent_entry
            or parent_binding != inherited_binding
            or inherited_current != inherited_binding
        ):
            raise SourceBindingError(
                "workspace_baseline_changed_since_prior_control"
            )
    json_bindings: list[dict[str, Any]] = []
    baseline_candidates: list[tuple[str, dict[str, Any], dict[str, Any]]] = []
    for path in allowed_paths:
        binding = _blob_binding(root, commit_oid, path)
        schema = binding["schema_version"]
        if schema in _DURABLE_AUTHORITY_SCHEMAS:
            json_bindings.append(binding)
        if (
            schema in {"bootstrap_workspace_baseline.v1", "workspace_baseline.v1"}
            and _tree_entry(root, parent, path) is None
        ):
            value = json.loads(
                _blob_bytes(root, commit_oid, path).decode("utf-8"),
                object_pairs_hook=_strict_object,
            )
            if not _validate_workspace_shape(
                value,
                bootstrap=schema == "bootstrap_workspace_baseline.v1",
            ) and value.get("head") == parent:
                baseline_candidates.append((path, binding, value))
    if not baseline_candidates and inherited_binding is not None:
        assert inherited_current is not None
        inherited_path = inherited_binding["path"]
        value = json.loads(
            _blob_bytes(root, commit_oid, inherited_path).decode("utf-8"),
            object_pairs_hook=_strict_object,
        )
        baseline_candidates.append(
            (inherited_path, inherited_current, value)
        )
    if len(baseline_candidates) != 1:
        raise SourceBindingError("commit_workspace_baseline_not_unique")
    _baseline_path, baseline_binding, baseline = baseline_candidates[0]
    baseline_schema = baseline.get("schema_version")
    if baseline_schema not in {
        "bootstrap_workspace_baseline.v1",
        "workspace_baseline.v1",
    } or _validate_workspace_shape(
        baseline, bootstrap=baseline_schema == "bootstrap_workspace_baseline.v1"
    ):
        raise SourceBindingError("commit_workspace_baseline_invalid")
    selected_is_new = _tree_entry(root, parent, _baseline_path) is None
    _require_workspace_baseline_transition(
        inherited_binding=inherited_binding,
        selected_binding=baseline_binding,
        selected_is_new=selected_is_new,
    )
    if inherited_record is not None and selected_is_new:
        if not _workspace_baseline_rows_preserved(
            inherited_record, baseline
        ):
            raise SourceBindingError(
                "workspace_baseline_semantic_inheritance_invalid"
            )
    if len(json_bindings) > 20:
        raise SourceBindingError("durable_authority_candidate_set_too_large")
    matching_authorities: list[list[dict[str, Any]]] = []
    for count in range(1, len(json_bindings) + 1):
        for combination in itertools.combinations(json_bindings, count):
            rows = sorted((dict(row) for row in combination), key=lambda row: row["path"])
            digest = _set_digest(rows)
            candidate_id = hashlib.sha256(b"precommit-control.v1\0" + parent.encode("ascii") + b"\0" + digest.removeprefix("sha256:").encode("ascii")).hexdigest()
            if candidate_id == transaction_id:
                matching_authorities.append(rows)
    if len(matching_authorities) != 1:
        raise SourceBindingError("durable_authority_reconstruction_ambiguous")
    authorities = matching_authorities[0]
    if not _durable_authority_rows_valid(
        authorities, allowed_paths=set(allowed_paths)
    ):
        raise SourceBindingError("durable_authority_reconstruction_invalid")
    authority_digest = _set_digest(authorities)
    dirty_paths = {row["path"] for row in baseline["dirty_entries"]}
    pre_index = [row for row in _tree_entries(root, parent) if row["path"] not in dirty_paths]
    pre_index.extend(row for row in baseline["index_entries"] if row["path"] in dirty_paths)
    pre_index.sort(key=lambda row: (row["path"], row["stage"], row["mode"], row["oid"]))
    committed_index = _tree_entries(root, commit_oid)
    expected_index = [row for row in pre_index if row["path"] not in set(allowed_paths)]
    expected_index.extend(row for row in committed_index if row["path"] in set(allowed_paths))
    expected_index.sort(key=lambda row: (row["path"], row["stage"], row["mode"], row["oid"]))
    allowed_delta_rows = [{"path": path, "before": _tree_entry(root, parent, path), "after": _tree_entry(root, commit_oid, path)} for path in allowed_paths]
    control_root = Path(_git(root, "rev-parse", "--path-format=absolute", "--git-path", f"retirement-commit-controls/{transaction_id}").decode().strip())
    pathspec_path = control_root / "paths.nul"
    base_path = control_root / "message.txt"
    final_path = control_root / "final-message.txt"
    pathspec = _derive_pathspec_bytes(allowed_delta_rows)
    control: dict[str, Any] = {
        "schema_version": "precommit_control.v1",
        "transaction_id": transaction_id,
        "bootstrap_workspace_baseline_binding": baseline_binding if baseline["schema_version"] == "bootstrap_workspace_baseline.v1" else None,
        "workspace_baseline_binding": baseline_binding if baseline["schema_version"] == "workspace_baseline.v1" else None,
        "durable_authority_bindings": authorities,
        "durable_authority_set_sha256": authority_digest,
        "prior_control_trailers": _prior_trailers(root, baseline["head"], parent),
        "base_head": parent,
        "pre_commit_index_binding": {"entry_count": len(pre_index), "entry_set_sha256": _set_digest(pre_index)},
        "allowed_delta_rows": allowed_delta_rows,
        "allowed_delta_count": len(allowed_delta_rows),
        "allowed_path_set_sha256": _path_list_digest(allowed_paths),
        "expected_index_binding": _index_binding(root, expected_index),
        "expected_commit_tree_oid": _git(root, "rev-parse", f"{commit_oid}^{{tree}}").decode("ascii").strip(),
        "pathspec_file_binding": {"path": pathspec_path.relative_to(root).as_posix(), "sha256": _sha256_bytes(pathspec), "byte_count": len(pathspec), "row_count": len(allowed_paths), "encoding": "nul_terminated_literal_paths"},
        "base_message_binding": {"path": base_path.relative_to(root).as_posix(), "sha256": _sha256_bytes(base_message), "byte_count": len(base_message)},
        "final_message_binding": {"path": final_path.relative_to(root).as_posix(), "sha256": _sha256_bytes(message), "byte_count": len(message), "cleanup": "verbatim"},
        "normalized_control_sha256": normalized_control_sha,
        "claims_not_made": ["This control does not invoke Git commit or authorize an ambient-index commit."],
    }
    if _canonical_sha256(control, exclude={"normalized_control_sha256", "final_message_binding"}) != normalized_control_sha:
        raise SourceBindingError("reconstructed_control_digest_mismatch")
    shape_issues = _validate_precommit_control_shape(control)
    if shape_issues:
        raise SourceBindingError(
            f"reconstructed_control_shape_invalid:{shape_issues[0].code}"
        )
    return control, pathspec, base_message, message


def validate_commit_boundary(
    repository_root: Path | str,
    *,
    control_path: Path | str | None = None,
    commit: str | None = None,
    expected_commit_subject: str | None = None,
    post_commit: bool = False,
    reconstruct: bool = False,
) -> list[SourceBindingIssue]:
    root = _repository_root(repository_root)
    if reconstruct:
        try:
            control, pathspec, base_message, final_message = _reconstruct_precommit_control(root, commit or "HEAD")
            if expected_commit_subject is None:
                return [SourceBindingIssue("expected_commit_subject_missing")]
            expected_base_message = _commit_subject_bytes(
                expected_commit_subject,
                error_code="expected_commit_subject_invalid",
            )
            if base_message != expected_base_message:
                return [SourceBindingIssue("base_message_subject_mismatch")]
            transaction_id = control["transaction_id"]
            control_root = Path(_git(root, "rev-parse", "--path-format=absolute", "--git-path", f"retirement-commit-controls/{transaction_id}").decode().strip())
            control_relative = control_root.relative_to(root)
            _exclusive_bytes(root, control_relative / "paths.nul", pathspec)
            _exclusive_bytes(root, control_relative / "message.txt", base_message)
            _exclusive_bytes(root, control_relative / "final-message.txt", final_message)
            _exclusive_bytes(root, control_relative / "control.json", _canonical_bytes(control) + b"\n")
            return []
        except SourceBindingError as exc:
            return [SourceBindingIssue("commit_reconstruction_failed", detail=str(exc))]
    if control_path is None:
        return [SourceBindingIssue("control_path_missing")]
    try:
        control = _read_json(root, Path(control_path))
    except SourceBindingError as exc:
        return [SourceBindingIssue("control_unreadable", detail=str(exc))]
    issues = _validate_precommit_control_shape(control)
    if issues:
        return sorted(set(issues))
    if expected_commit_subject is None:
        return [SourceBindingIssue("expected_commit_subject_missing")]
    try:
        expected_base_message = _commit_subject_bytes(
            expected_commit_subject,
            error_code="expected_commit_subject_invalid",
        )
    except SourceBindingError as exc:
        return [SourceBindingIssue(str(exc))]
    control_relative = _relative_path(control_path)
    expected_control_path = (
        f".git/retirement-commit-controls/{control['transaction_id']}/control.json"
    )
    if control_relative != expected_control_path:
        issues.append(SourceBindingIssue("control_path_mismatch", control_relative))
    allowed_rows = control["allowed_delta_rows"]
    allowed = [row["path"] for row in allowed_rows]
    allowed_paths = set(allowed)
    authorities = control["durable_authority_bindings"]
    authority_digest = _set_digest(authorities)
    transaction = hashlib.sha256(b"precommit-control.v1\0" + control["base_head"].encode("ascii") + b"\0" + authority_digest.removeprefix("sha256:").encode("ascii")).hexdigest()
    if authority_digest != control.get("durable_authority_set_sha256") or transaction != control.get("transaction_id"):
        issues.append(SourceBindingIssue("transaction_binding_mismatch"))
    baseline_binding = (
        control["bootstrap_workspace_baseline_binding"]
        or control["workspace_baseline_binding"]
    )
    expected_baseline_schema = (
        "bootstrap_workspace_baseline.v1"
        if control["bootstrap_workspace_baseline_binding"] is not None
        else "workspace_baseline.v1"
    )
    try:
        baseline_record = _read_json(root, baseline_binding["path"])
        baseline_head = baseline_record.get("head")
        if not isinstance(baseline_head, str) or _HEX40_RE.fullmatch(
            baseline_head
        ) is None:
            raise SourceBindingError("workspace_baseline_head_invalid")
        expected_prior_trailers = _prior_trailers(
            root, baseline_head, control["base_head"]
        )
        if control["prior_control_trailers"] != expected_prior_trailers:
            issues.append(SourceBindingIssue("prior_control_trailer_chain_mismatch"))
        prior_paths = _prior_control_paths(root, expected_prior_trailers)
    except (KeyError, SourceBindingError) as exc:
        issues.append(
            SourceBindingIssue("prior_control_path_set_unreadable", detail=str(exc))
        )
        baseline_record = {}
        prior_paths = []
    commit_oid: str | None = None
    try:
        current_head = _git(root, "rev-parse", "HEAD").decode("ascii").strip()
        _, current_index, _, _ = _capture_git(root)
        if post_commit:
            commit_oid = _git(root, "rev-parse", commit or "HEAD").decode(
                "ascii"
            ).strip()
            if commit_oid != current_head:
                issues.append(SourceBindingIssue("post_commit_head_mismatch"))
            workspace_allowed: list[str] = []
            workspace_committed = sorted({*prior_paths, *allowed_paths})
            workspace_head = commit_oid
        else:
            if current_head != control["base_head"]:
                issues.append(SourceBindingIssue("base_head_mismatch"))
            workspace_allowed = allowed
            workspace_committed = prior_paths
            workspace_head = control["base_head"]
    except SourceBindingError as exc:
        issues.append(
            SourceBindingIssue("commit_boundary_unreadable", detail=str(exc))
        )
        current_index = []
        workspace_allowed = allowed if not post_commit else []
        workspace_committed = prior_paths
        workspace_head = control["base_head"]
    issues.extend(
        _bound_workspace_issues(
            root,
            baseline_binding,
            expected_schema=expected_baseline_schema,
            allowed_additions=workspace_allowed,
            committed_head=workspace_head,
            committed_paths=workspace_committed,
        )
    )
    issues.extend(
        _durable_authority_live_issues(
            root, authorities, allowed_paths=allowed_paths
        )
    )
    external_bytes: dict[str, bytes] = {}
    for binding_name in ("pathspec_file_binding", "base_message_binding", "final_message_binding"):
        binding = control[binding_name]
        try:
            data = _read_repository_bytes(root, _relative_path(binding["path"]))
            external_bytes[binding_name] = data
            if _sha256_bytes(data) != binding.get("sha256") or len(data) != binding.get("byte_count"):
                issues.append(SourceBindingIssue(f"{binding_name}_mismatch"))
        except (KeyError, OSError, SourceBindingError):
            issues.append(SourceBindingIssue(f"{binding_name}_unreadable"))
    expected_pathspec = _derive_pathspec_bytes(allowed_rows)
    if external_bytes.get("pathspec_file_binding") != expected_pathspec:
        issues.append(SourceBindingIssue("pathspec_derivation_mismatch"))
    base_message = external_bytes.get("base_message_binding")
    final_message = external_bytes.get("final_message_binding")
    if base_message is None or not _base_message_bytes_valid(base_message):
        issues.append(SourceBindingIssue("base_message_derivation_mismatch"))
    else:
        if base_message != expected_base_message:
            issues.append(SourceBindingIssue("base_message_subject_mismatch"))
        expected_final = _derive_final_message_bytes(
            base_message,
            control["transaction_id"],
            control["normalized_control_sha256"],
        )
        if final_message != expected_final:
            issues.append(SourceBindingIssue("final_message_derivation_mismatch"))
    if post_commit:
        try:
            if commit_oid is None:
                raise SourceBindingError("post_commit_oid_unavailable")
            parent = _git(root, "rev-parse", f"{commit_oid}^").decode("ascii").strip()
            if parent != control["base_head"]:
                issues.append(SourceBindingIssue("commit_parent_mismatch"))
            if _git(root, "rev-parse", f"{commit_oid}^{{tree}}").decode().strip() != control["expected_commit_tree_oid"]:
                issues.append(SourceBindingIssue("commit_tree_mismatch"))
            actual_paths = _git(root, "diff-tree", "--no-commit-id", "--name-only", "-r", "-z", commit_oid).split(b"\0")
            actual = sorted(_decode_path(item) for item in actual_paths if item)
            if actual != sorted(allowed_paths):
                issues.append(SourceBindingIssue("committed_path_set_mismatch"))
            reconstructed, _, _, _ = _reconstruct_precommit_control(
                root, commit_oid
            )
            if _canonical_bytes(reconstructed) != _canonical_bytes(control):
                issues.append(SourceBindingIssue("commit_reconstruction_mismatch"))
            if _index_binding(root, current_index) != control["expected_index_binding"]:
                issues.append(SourceBindingIssue("index_binding_mismatch"))
            unstaged = _unstaged_paths(root, allowed)
            if unstaged:
                issues.append(
                    SourceBindingIssue(
                        "allowed_path_worktree_index_mismatch", unstaged[0]
                    )
                )
        except SourceBindingError as exc:
            issues.append(
                SourceBindingIssue("commit_reconstruction_failed", detail=str(exc))
            )
    else:
        try:
            unstaged = _unstaged_paths(root, allowed)
            if unstaged:
                issues.append(
                    SourceBindingIssue(
                        "allowed_path_worktree_index_mismatch", unstaged[0]
                    )
                )
            baseline_dirty = {
                row["path"]
                for row in baseline_record.get("dirty_entries", [])
                if isinstance(row, Mapping) and isinstance(row.get("path"), str)
            }
            staged_paths = set(_changed_paths(root, control["base_head"]))
            missing = sorted(allowed_paths - staged_paths)
            unexpected = sorted(staged_paths - allowed_paths - baseline_dirty)
            if missing:
                issues.append(SourceBindingIssue("allowed_path_not_staged", missing[0]))
            if unexpected:
                issues.append(SourceBindingIssue("unrelated_staged_drift", unexpected[0]))
            (
                derived_rows,
                derived_pre_index,
                derived_expected_index,
                derived_expected_tree,
            ) = _derive_precommit_index_contract(
                root, control["base_head"], allowed, current_index
            )
            if derived_rows != allowed_rows:
                issues.append(SourceBindingIssue("allowed_delta_rows_mismatch"))
            if derived_pre_index != control["pre_commit_index_binding"]:
                issues.append(SourceBindingIssue("pre_commit_index_binding_mismatch"))
            if derived_expected_index != control["expected_index_binding"]:
                issues.append(SourceBindingIssue("index_binding_mismatch"))
            if derived_expected_tree != control["expected_commit_tree_oid"]:
                issues.append(SourceBindingIssue("expected_commit_tree_mismatch"))
        except SourceBindingError as exc:
            issues.append(SourceBindingIssue("commit_boundary_unreadable", detail=str(exc)))
    return sorted(set(issues))


def _print_issues(issues: Sequence[SourceBindingIssue]) -> int:
    if not issues:
        return 0
    print(json.dumps({"status": "rejected", "issues": [issue.as_dict() for issue in issues]}, sort_keys=True))
    return 2


def _main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)

    capture = commands.add_parser("capture-workspace-baseline")
    capture.add_argument("--repository-root", type=Path, required=True)
    capture.add_argument("--protected-path", action="append", default=[])
    capture.add_argument("--out", type=Path, required=True)

    build_sources = commands.add_parser("build-non-target-sources")
    build_sources.add_argument("--repository-root", type=Path, required=True)
    build_sources.add_argument("--handoff", type=Path, required=True)
    build_sources.add_argument("--workspace-baseline", type=Path, required=True)
    build_sources.add_argument("--tracked-queue-id", action="append", required=True)
    build_sources.add_argument("--protected-queue-id", required=True)
    build_sources.add_argument("--out", type=Path, required=True)

    validate_workspace = commands.add_parser("validate-workspace-baseline")
    validate_workspace.add_argument("--repository-root", type=Path, required=True)
    validate_workspace.add_argument("--record", type=Path, required=True)
    validate_workspace.add_argument("--allowed-addition", action="append", default=[])

    validate_sources = commands.add_parser("validate-non-target-sources")
    validate_sources.add_argument("--repository-root", type=Path, required=True)
    validate_sources.add_argument("--record", type=Path, required=True)

    query = commands.add_parser("materialize-query")
    query.add_argument("--repository-root", type=Path, required=True)
    query.add_argument("--handoff", type=Path, required=True)
    query.add_argument("--queue-id", required=True)
    query.add_argument("--generation", type=int, required=True)
    query.add_argument("--out", type=Path, required=True)

    control = commands.add_parser("build-precommit-control")
    control.add_argument("--repository-root", type=Path, required=True)
    control.add_argument("--allowed-path", action="append", required=True)
    control.add_argument("--durable-authority", type=Path, action="append", required=True)
    control.add_argument("--commit-subject", required=True)
    control.add_argument("--bootstrap-workspace-baseline", type=Path)
    control.add_argument("--workspace-baseline", type=Path)
    control.add_argument("--prior-control-trailer", action="append", default=[])

    boundary = commands.add_parser("validate-commit-boundary")
    boundary.add_argument("--repository-root", type=Path, required=True)
    boundary.add_argument("--control", type=Path)
    boundary.add_argument("--commit")
    boundary.add_argument("--expected-commit-subject", required=True)
    boundary.add_argument("--post-commit", action="store_true")
    boundary.add_argument("--reconstruct", action="store_true")

    adopt = commands.add_parser("adopt-bootstrap-workspace")
    adopt.add_argument("--repository-root", type=Path, required=True)
    adopt.add_argument("--bootstrap-root", type=Path, required=True)
    adopt.add_argument("--out", type=Path, required=True)
    validate = commands.add_parser("validate-bootstrap-workspace")
    validate.add_argument("--repository-root", type=Path, required=True)
    validate.add_argument("--record", type=Path, required=True)
    validate.add_argument("--allowed-addition", action="append", default=[])
    args = parser.parse_args(argv)
    try:
        if args.command == "capture-workspace-baseline":
            root = _repository_root(args.repository_root)
            _write_json(root, args.out, capture_workspace_baseline(root, args.protected_path))
            return 0
        if args.command == "build-non-target-sources":
            value = build_non_target_sources(args.repository_root, args.handoff, args.workspace_baseline, args.tracked_queue_id, args.protected_queue_id)
            _write_json(_repository_root(args.repository_root), args.out, value)
            return 0
        if args.command == "validate-workspace-baseline":
            return _print_issues(validate_workspace_baseline(args.repository_root, args.record, args.allowed_addition))
        if args.command == "validate-non-target-sources":
            return _print_issues(validate_non_target_sources(args.repository_root, args.record))
        if args.command == "materialize-query":
            print(json.dumps(materialize_query(args.repository_root, args.handoff, args.queue_id, args.generation, args.out), sort_keys=True, separators=(",", ":")))
            return 0
        if args.command == "build-precommit-control":
            trailers = []
            for encoded in args.prior_control_trailer:
                value = json.loads(encoded, object_pairs_hook=_strict_object)
                if not isinstance(value, dict):
                    raise SourceBindingError("prior_control_trailer_not_object")
                trailers.append(value)
            receipt = build_precommit_control(
                args.repository_root,
                allowed_paths=args.allowed_path,
                durable_authority_paths=args.durable_authority,
                commit_subject=args.commit_subject,
                bootstrap_workspace_baseline=args.bootstrap_workspace_baseline,
                workspace_baseline=args.workspace_baseline,
                prior_control_trailers=trailers,
            )
            print(json.dumps(receipt, sort_keys=True, separators=(",", ":")))
            return 0
        if args.command == "validate-commit-boundary":
            return _print_issues(
                validate_commit_boundary(
                    args.repository_root,
                    control_path=args.control,
                    commit=args.commit,
                    expected_commit_subject=args.expected_commit_subject,
                    post_commit=args.post_commit,
                    reconstruct=args.reconstruct,
                )
            )
        if args.command == "adopt-bootstrap-workspace":
            record = adopt_bootstrap_workspace(args.repository_root, args.bootstrap_root)
            _write_json(_repository_root(args.repository_root), args.out, record)
            return 0
        if args.command == "validate-bootstrap-workspace":
            return _print_issues(
                validate_bootstrap_workspace(
                    args.repository_root, args.record, args.allowed_addition
                )
            )
        raise SourceBindingError(f"unknown_command:{args.command}")
    except (SourceBindingError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "rejected", "code": str(exc)}, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(_main())
