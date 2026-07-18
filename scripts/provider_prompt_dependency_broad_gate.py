#!/usr/bin/env python3
"""Closed evidence gate for provider prompt-dependency implementation work.

This module only captures, validates, and compares evidence.  It deliberately
does not launch pytest, workflows, or providers.
"""

from __future__ import annotations

import argparse
import ast
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import stat
import subprocess
import sys
from typing import Any, Iterable, Mapping, Sequence
import xml.etree.ElementTree as ET


class GateError(ValueError):
    """Evidence violates a closed gate contract."""


SUBJECT_KEYS = frozenset({
    "schema", "head", "index_tree", "protected_paths", "allowed_untracked_paths",
    "task_subject_paths", "allowed_post_launch_updates", "generated_evidence_paths",
    "ignored_evidence_roots", "frozen_overlay", "inventory", "full_status", "record_sha256",
})
OVERLAY_KEYS = frozenset({
    "schema", "head", "index_tree", "eligible_paths", "selected_paths", "inventory", "record_sha256",
})
REVIEW_SUBJECT_KEYS = frozenset({
    "schema", "subject", "allowed_post_launch_updates", "staged_status", "review_patch_sha256",
    "review_tree", "generated_evidence", "frozen_overlay", "record_sha256",
})
INVENTORY_KEYS = frozenset({"path", "status", "type", "mode", "bytes", "sha256"})
STATUS_KEYS = frozenset({"path", "status"})
FILE_BINDING_KEYS = frozenset({"path", "bytes", "sha256"})
EXIT_STATUS_KEYS = frozenset({"schema", "phase", "argv", "exit_code", "record_sha256"})

REVIEW_LAYOUT = ("review-subject.json",)
BROAD_LAYOUT = (
    "collection.log", "collection.status.json", "junit.xml", "broad.log", "broad.status.json",
    "pane.log", "outcome.json", "review-subject.json",
    *(f"isolated/row-{i:02d}{suffix}" for i in range(6) for suffix in (".log", ".xml", ".status.json")),
)

_LOGGING_LINE = re.compile(r"(?m)^(?P<prefix>[A-Z]+\s+[^\s:]+:[^\s:]+\.py:)\d+(?=\s)")
_PYTEST_SESSION_ROOT = re.compile(
    r"(?<![A-Za-z0-9_.-])(?:"
    r"\\\\[^\\/\s'\"<>!=|&+*]+[\\/][^\\/\s'\"<>!=|&+*]+(?:[\\/][^\\/\s'\"<>!=|&+*]+)*[\\/]pytest-of-[^\\/\s'\"<>!=|&+*]+[\\/]pytest-\d+"
    r"|[A-Za-z]:[\\/](?:[^\\/\s'\"<>!=|&+*]+[\\/])*pytest-of-[^\\/\s'\"<>!=|&+*]+[\\/]pytest-\d+"
    r"|/(?:[^/\s'\"<>!=|&+*]+/)*pytest-of-[^/\s'\"<>!=|&+*]+/pytest-\d+)"
)
_ELAPSED = re.compile(
    r"(?m)^(?P<prefix>\d+ (?:failed|passed|skipped|deselected|xfailed|xpassed|error|errors|warning|warnings)(?:, \d+ (?:failed|passed|skipped|deselected|xfailed|xpassed|error|errors|warning|warnings))* in )\d+(?:\.\d+)?s(?: \(\d+:[0-5]\d:[0-5]\d\))?(?P<line_ending>\r?)$"
)
_REPR_ADDR = re.compile(r"(?P<prefix><[^\s<][^\r\n]*?\bat )0x[0-9A-Fa-f]+(?=>)")


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")


def _payload_without_digest(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if key != "record_sha256"}


def record_digest(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical(_payload_without_digest(payload))).hexdigest()


def _seal(payload: dict[str, Any]) -> dict[str, Any]:
    payload["record_sha256"] = record_digest(payload)
    return payload


def _require_keys(payload: Mapping[str, Any], keys: frozenset[str], label: str) -> None:
    if set(payload) != keys:
        raise GateError(f"{label} keys are not closed: expected {sorted(keys)}, got {sorted(payload)}")


def _validate_digest(payload: Mapping[str, Any], label: str) -> None:
    digest = payload.get("record_sha256")
    if not isinstance(digest, str) or digest != record_digest(payload):
        raise GateError(f"{label} record digest mismatch")


def _git(repo_root: Path, *args: str) -> bytes:
    completed = subprocess.run(
        ["git", *args], cwd=repo_root, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False
    )
    if completed.returncode:
        raise GateError(
            f"git {' '.join(args)} failed ({completed.returncode}): "
            f"{completed.stderr.decode('utf-8', 'replace').strip()}"
        )
    return completed.stdout


def _repo_path(value: str | Path) -> str:
    text = value.as_posix() if isinstance(value, Path) else value
    if not isinstance(text, str) or not text or "\x00" in text or "\\" in text:
        raise GateError(f"invalid repo-relative path: {text!r}")
    pure = PurePosixPath(text)
    if pure.is_absolute() or any(part in ("", ".", "..") for part in pure.parts):
        raise GateError(f"path must be normalized and repo-relative: {text!r}")
    text.encode("utf-8", "strict")
    return pure.as_posix()


def _closed_paths(values: Iterable[str | Path], label: str) -> list[str]:
    rows = [_repo_path(value) for value in values]
    if len(rows) != len(set(rows)):
        raise GateError(f"duplicate {label} path")
    return sorted(rows)


def _status(repo_root: Path) -> list[dict[str, str]]:
    raw = _git(repo_root, "status", "--porcelain=v1", "-z", "--untracked-files=all")
    fields = raw.split(b"\0")
    if fields and fields[-1] == b"":
        fields.pop()
    result: list[dict[str, str]] = []
    index = 0
    while index < len(fields):
        field = fields[index]
        if len(field) < 4 or field[2:3] != b" ":
            raise GateError("malformed git status record")
        xy_raw, path_raw = field[:2], field[3:]
        if b"R" in xy_raw or b"C" in xy_raw:
            raise GateError("rename/copy status is prohibited")
        try:
            xy = xy_raw.decode("ascii", "strict")
            path = path_raw.decode("utf-8", "strict")
        except UnicodeDecodeError as exc:
            raise GateError("Git status contains a path that is not valid UTF-8") from exc
        result.append({"path": _repo_path(path), "status": xy})
        index += 1
    result.sort(key=lambda row: row["path"])
    if len({row["path"] for row in result}) != len(result):
        raise GateError("duplicate Git status path")
    return result


def _status_v2_complete(repo_root: Path) -> list[dict[str, str]]:
    raw = _git(repo_root, "status", "--porcelain=v2", "-z", "--untracked-files=all")
    fields = raw.split(b"\0")
    if fields and fields[-1] == b"":
        fields.pop()
    result: list[dict[str, str]] = []

    def decode_path(value: bytes) -> str:
        try:
            return _repo_path(value.decode("utf-8", "strict"))
        except UnicodeDecodeError as exc:
            raise GateError("Git status contains a path that is not valid UTF-8") from exc

    def decode_xy(value: bytes) -> str:
        try:
            text = value.decode("ascii", "strict").replace(".", " ")
        except UnicodeDecodeError as exc:
            raise GateError("malformed porcelain-v2 status") from exc
        if len(text) != 2:
            raise GateError("malformed porcelain-v2 XY status")
        return text

    index = 0
    while index < len(fields):
        field = fields[index]
        kind = field[:1]
        if kind == b"1":
            parts = field.split(b" ", 8)
            if len(parts) != 9:
                raise GateError("malformed porcelain-v2 ordinary record")
            result.append({"path": decode_path(parts[8]), "status": decode_xy(parts[1])})
        elif kind == b"2":
            parts = field.split(b" ", 9)
            if len(parts) != 10 or index + 1 >= len(fields):
                raise GateError("malformed porcelain-v2 rename/copy record")
            xy = decode_xy(parts[1])
            destination = decode_path(parts[9])
            index += 1
            origin = decode_path(fields[index])
            result.append({"path": destination, "status": xy})
            origin_status = "D " if xy[0] not in (" ", "?") else " D"
            result.append({"path": origin, "status": origin_status})
        elif kind == b"u":
            parts = field.split(b" ", 10)
            if len(parts) != 11:
                raise GateError("malformed porcelain-v2 unmerged record")
            result.append({"path": decode_path(parts[10]), "status": decode_xy(parts[1])})
        elif kind == b"?" and field.startswith(b"? "):
            result.append({"path": decode_path(field[2:]), "status": "??"})
        elif kind == b"!" and field.startswith(b"! "):
            pass
        else:
            raise GateError("unknown porcelain-v2 status record")
        index += 1
    result.sort(key=lambda row: row["path"])
    if len({row["path"] for row in result}) != len(result):
        raise GateError("duplicate porcelain-v2 Git status path")
    return result


def _status_map(rows: Sequence[Mapping[str, str]]) -> dict[str, str]:
    return {row["path"]: row["status"] for row in rows}


def _index_tree(repo_root: Path) -> str:
    return _git(repo_root, "write-tree").decode("ascii").strip()


def _head(repo_root: Path) -> str:
    return _git(repo_root, "rev-parse", "HEAD").decode("ascii").strip()


def _inventory(repo_root: Path, path: str, statuses: Mapping[str, str]) -> dict[str, Any]:
    full = repo_root / path
    try:
        details = full.lstat()
    except FileNotFoundError:
        return {"path": path, "status": statuses.get(path, "ABSENT"), "type": "missing", "mode": None, "bytes": 0, "sha256": None}
    mode = f"{stat.S_IMODE(details.st_mode):04o}"
    if stat.S_ISREG(details.st_mode):
        data = full.read_bytes()
        kind = "regular"
    elif stat.S_ISLNK(details.st_mode):
        data = os.readlink(full).encode("utf-8", "surrogateescape")
        kind = "symlink"
    else:
        raise GateError(f"declared non-file path is prohibited: {path}")
    return {
        "path": path, "status": statuses.get(path, "CLEAN"), "type": kind, "mode": mode,
        "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(),
    }


def _is_nonnegative_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _validate_porcelain_status(value: Any, *, allow_staged: bool, label: str) -> None:
    if not isinstance(value, str) or len(value) != 2:
        raise GateError(f"invalid {label} porcelain status")
    if value == "??":
        if allow_staged:
            raise GateError(f"invalid staged {label} porcelain status")
        return
    if "?" in value or "!" in value or "R" in value or "C" in value:
        raise GateError(f"invalid {label} porcelain status")
    if any(char not in " MTADU" for char in value) or value == "  ":
        raise GateError(f"invalid {label} porcelain status")
    is_staged = value[0] != " "
    if is_staged != allow_staged:
        raise GateError(f"invalid {label} staged-status domain")


def _validate_status_row(row: Mapping[str, Any], *, staged: bool, label: str) -> None:
    _require_keys(row, STATUS_KEYS, label)
    _repo_path(row["path"])
    _validate_porcelain_status(row["status"], allow_staged=staged, label=label)


def _validate_inventory_row(
    row: Mapping[str, Any], *, allow_staged_status: bool = False,
    allow_any_status: bool = False,
) -> None:
    _require_keys(row, INVENTORY_KEYS, "inventory row")
    _repo_path(row["path"])
    status = row["status"]
    if status not in ("CLEAN", "ABSENT"):
        staged = allow_staged_status
        if allow_any_status:
            staged = status != "??" and status[0] != " "
        _validate_porcelain_status(
            status, allow_staged=staged, label="inventory"
        )
    if row["type"] not in ("regular", "symlink", "missing"):
        raise GateError("invalid inventory type")
    if row["type"] == "missing":
        if row["mode"] is not None or row["bytes"] != 0 or row["sha256"] is not None:
            raise GateError("invalid missing inventory row")
    elif not (isinstance(row["mode"], str) and re.fullmatch(r"[0-7]{4}", row["mode"]) and _is_nonnegative_int(row["bytes"]) and isinstance(row["sha256"], str) and re.fullmatch(r"[0-9a-f]{64}", row["sha256"])):
        raise GateError("invalid file inventory row")


def _validate_file_binding_shape(
    binding: Mapping[str, Any], *, include_record_digest: bool, label: str
) -> None:
    expected = set(FILE_BINDING_KEYS)
    if include_record_digest:
        expected.add("record_sha256")
    if set(binding) != expected:
        raise GateError(f"{label} binding is not closed")
    _repo_path(binding["path"])
    if not _is_nonnegative_int(binding["bytes"]):
        raise GateError(f"{label} binding bytes are invalid")
    if not isinstance(binding["sha256"], str) or not re.fullmatch(r"[0-9a-f]{64}", binding["sha256"]):
        raise GateError(f"{label} binding digest is invalid")
    if include_record_digest and (
        not isinstance(binding["record_sha256"], str)
        or not re.fullmatch(r"[0-9a-f]{64}", binding["record_sha256"])
    ):
        raise GateError(f"{label} record digest is invalid")


def _validate_frozen_overlay_binding(overlay: Mapping[str, Any], *, label: str) -> None:
    expected = {
        "path", "bytes", "sha256", "record_sha256", "selected_paths",
        "inventory", "inventory_sha256",
    }
    if set(overlay) != expected:
        raise GateError(f"{label} frozen-overlay binding is not closed")
    _validate_file_binding_shape(
        {key: overlay[key] for key in (*FILE_BINDING_KEYS, "record_sha256")},
        include_record_digest=True,
        label=f"{label} frozen-overlay",
    )
    if (
        overlay["selected_paths"] != _closed_paths(overlay["selected_paths"], "selected")
        or not overlay["selected_paths"]
        or not isinstance(overlay["inventory"], list)
        or not overlay["inventory"]
    ):
        raise GateError(f"{label} frozen-overlay inventory is empty or duplicated")
    for row in overlay["inventory"]:
        _validate_inventory_row(row)
    if [row["path"] for row in overlay["inventory"]] != overlay["selected_paths"]:
        raise GateError(f"{label} frozen-overlay inventory/selection mismatch")
    if (
        not isinstance(overlay["inventory_sha256"], str)
        or overlay["inventory_sha256"] != hashlib.sha256(_canonical(overlay["inventory"])).hexdigest()
    ):
        raise GateError(f"{label} frozen-overlay inventory digest mismatch")


def _ignored_root(repo_root: Path, root: str, *, must_be_absent: bool) -> None:
    root = _repo_path(root)
    if not root.startswith(".orchestrate/tmp/"):
        raise GateError("ignored evidence root must be beneath .orchestrate/tmp/")
    completed = subprocess.run(
        ["git", "check-ignore", "-q", "--", root], cwd=repo_root, check=False
    )
    if completed.returncode != 0:
        raise GateError(f"ignored evidence root is not proven ignored: {root}")
    current = repo_root
    missing = False
    for part in PurePosixPath(root).parts:
        current /= part
        try:
            details = current.lstat()
        except FileNotFoundError:
            missing = True
            break
        if not stat.S_ISDIR(details.st_mode):
            raise GateError(
                f"ignored evidence root component must be a real non-symlink directory: {current}"
            )
    if must_be_absent:
        if not missing:
            raise GateError(f"ignored evidence root must be absent: {root}")
    elif missing:
        raise GateError(f"ignored evidence root must be a present real directory: {root}")


def _write_new_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o644)
    except FileExistsError as exc:
        raise GateError(f"refusing to clobber evidence: {path}") from exc
    with os.fdopen(fd, "wb") as stream:
        stream.write(_canonical(payload))


def _write_replace_json(path: Path, payload: Mapping[str, Any]) -> None:
    if path.is_symlink():
        raise GateError(f"refusing symlink output: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_canonical(payload))


def _publish_new_json_atomically(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.parent / f".{path.name}.tmp-{os.getpid()}"
    try:
        fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o644)
        with os.fdopen(fd, "wb") as stream:
            stream.write(_canonical(payload))
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temp, path)
        except FileExistsError as exc:
            raise GateError(f"refusing to clobber evidence: {path}") from exc
        directory_fd = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        try:
            temp.unlink()
        except FileNotFoundError:
            pass


def capture_subject(
    *, repo_root: Path, output: Path, protected_paths: Iterable[str | Path],
    allowed_untracked_paths: Iterable[str | Path], task_subject_paths: Iterable[str | Path],
    allowed_post_launch_updates: Iterable[str | Path], generated_evidence_paths: Iterable[str | Path],
    ignored_evidence_roots: Iterable[str | Path], generated_evidence_layout: str | None,
    frozen_overlay_path: Path | None,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    protected = _closed_paths(protected_paths, "protected")
    allowed_untracked = _closed_paths(allowed_untracked_paths, "allowed-untracked")
    task_subject = _closed_paths(task_subject_paths, "task-subject")
    post = _closed_paths(allowed_post_launch_updates, "allowed-post-launch")
    roots = _closed_paths(ignored_evidence_roots, "ignored-evidence-root")
    if not set(post) <= set(task_subject):
        raise GateError("allowed post-launch paths must be an exact task-subject subset")
    authorities = [set(protected), set(allowed_untracked), set(task_subject)]
    if any(authorities[i] & authorities[j] for i in range(3) for j in range(i + 1, 3)):
        raise GateError("protected/allowed-untracked/task-subject authority overlap")
    output_path = output if output.is_absolute() else repo_root / output
    output_rel = Path(os.path.abspath(output_path)).relative_to(repo_root).as_posix()
    if not any(output_rel == root + "/subject.json" for root in roots):
        raise GateError("subject output must be the implicit subject.json in an ignored root")
    for root in roots:
        _ignored_root(repo_root, root, must_be_absent=True)
    layout = ()
    if generated_evidence_layout == "review-v1":
        layout = REVIEW_LAYOUT
    elif generated_evidence_layout == "broad-v1":
        layout = BROAD_LAYOUT
    elif generated_evidence_layout is not None:
        raise GateError("unknown generated evidence layout")
    generated = _closed_paths(generated_evidence_paths, "generated evidence")
    generated += [f"{root}/{leaf}" for root in roots for leaf in layout]
    generated = _closed_paths(generated, "generated evidence")
    status = _status(repo_root)
    status_by_path = _status_map(status)
    declared = set(protected) | set(allowed_untracked) | set(task_subject)
    undisclosed = sorted(set(status_by_path) - declared)
    if undisclosed:
        raise GateError(f"undisclosed dirty/untracked paths: {undisclosed}")
    staged = sorted(path for path, xy in status_by_path.items() if xy[0] not in (" ", "?"))
    if any(path not in task_subject for path in staged):
        raise GateError(f"unexpected staged path outside task subject: {staged}")
    if staged:
        raise GateError(f"task-subject capture requires non-staged paths: {staged}")
    for path in allowed_untracked:
        if status_by_path.get(path) != "??":
            raise GateError(f"allowed-untracked path is not untracked: {path}")
    inventory = [_inventory(repo_root, path, status_by_path) for path in sorted(declared)]
    overlay_binding = None
    if frozen_overlay_path is not None:
        overlay = _load_json(frozen_overlay_path)
        validate_frozen_overlay(overlay, repo_root=repo_root, record_path=frozen_overlay_path)
        if not set(overlay["selected_paths"]) <= set(task_subject):
            raise GateError("every frozen overlay row must be repeated as task-subject")
        if set(overlay["selected_paths"]) & set(post):
            raise GateError("frozen overlay rows cannot be allowed post-launch updates")
        current = {row["path"]: row for row in inventory}
        if any(current[path] != row for row in overlay["inventory"] for path in [row["path"]]):
            raise GateError("post-edit subject overlay rows do not equal frozen record")
        overlay_binding = {
            **_file_binding(frozen_overlay_path, repo_root),
            "record_sha256": overlay["record_sha256"],
            "selected_paths": overlay["selected_paths"],
            "inventory": overlay["inventory"],
            "inventory_sha256": hashlib.sha256(_canonical(overlay["inventory"])).hexdigest(),
        }
    payload = _seal({
        "schema": "workflow_verification_subject.v1", "head": _head(repo_root),
        "index_tree": _index_tree(repo_root), "protected_paths": protected,
        "allowed_untracked_paths": allowed_untracked, "task_subject_paths": task_subject,
        "allowed_post_launch_updates": post, "generated_evidence_paths": generated,
        "ignored_evidence_roots": roots, "frozen_overlay": overlay_binding,
        "inventory": inventory, "full_status": status,
    })
    _write_new_json(output, payload)
    validate_subject(payload, repo_root=repo_root)
    return payload


def validate_subject(payload: Mapping[str, Any], *, repo_root: Path) -> None:
    _require_keys(payload, SUBJECT_KEYS, "subject")
    if payload["schema"] != "workflow_verification_subject.v1":
        raise GateError("wrong subject schema")
    _validate_digest(payload, "subject")
    if not isinstance(payload["head"], str) or not re.fullmatch(r"[0-9a-f]{40,64}", payload["head"]):
        raise GateError("invalid subject HEAD")
    if not isinstance(payload["index_tree"], str) or not re.fullmatch(r"[0-9a-f]{40,64}", payload["index_tree"]):
        raise GateError("invalid subject index tree")
    for key in ("protected_paths", "allowed_untracked_paths", "task_subject_paths", "allowed_post_launch_updates", "generated_evidence_paths", "ignored_evidence_roots"):
        if payload[key] != _closed_paths(payload[key], key):
            raise GateError(f"{key} is not sorted")
    authorities = [
        set(payload["protected_paths"]),
        set(payload["allowed_untracked_paths"]),
        set(payload["task_subject_paths"]),
    ]
    if any(
        authorities[left] & authorities[right]
        for left in range(len(authorities))
        for right in range(left + 1, len(authorities))
    ):
        raise GateError("protected/allowed-untracked/task-subject authorities must be disjoint")
    if not set(payload["allowed_post_launch_updates"]) <= set(payload["task_subject_paths"]):
        raise GateError("invalid allowed post-launch subset")
    if not isinstance(payload["inventory"], list):
        raise GateError("subject inventory must be a list")
    for row in payload["inventory"]:
        _validate_inventory_row(row)
    if [row["path"] for row in payload["inventory"]] != sorted(row["path"] for row in payload["inventory"]):
        raise GateError("inventory is not sorted")
    if not isinstance(payload["full_status"], list):
        raise GateError("subject full status must be a list")
    for row in payload["full_status"]:
        _validate_status_row(row, staged=False, label="subject status row")
    if payload["full_status"] != sorted(payload["full_status"], key=lambda row: row["path"]):
        raise GateError("full status is not sorted")
    if len({row["path"] for row in payload["full_status"]}) != len(payload["full_status"]):
        raise GateError("subject full status contains duplicate paths")
    authority_paths = sorted(
        set(payload["protected_paths"])
        | set(payload["allowed_untracked_paths"])
        | set(payload["task_subject_paths"])
    )
    if [row["path"] for row in payload["inventory"]] != authority_paths:
        raise GateError("subject inventory does not reconcile with declared authorities")
    full_status = _status_map(payload["full_status"])
    dirty_inventory_paths = {
        row["path"]
        for row in payload["inventory"]
        if row["status"] not in ("CLEAN", "ABSENT")
    }
    if set(full_status) != dirty_inventory_paths:
        raise GateError(
            "subject full status paths do not equal dirty authority inventory paths"
        )
    for row in payload["inventory"]:
        expected_status = full_status.get(row["path"], "ABSENT" if row["type"] == "missing" else "CLEAN")
        if row["status"] != expected_status:
            raise GateError(f"subject inventory/status mismatch: {row['path']}")
    if any(full_status.get(path) != "??" for path in payload["allowed_untracked_paths"]):
        raise GateError("allowed-untracked authority is not exactly untracked")
    for root in payload["ignored_evidence_roots"]:
        leaves = sorted(
            path.removeprefix(root + "/")
            for path in payload["generated_evidence_paths"]
            if path.startswith(root + "/")
        )
        if tuple(leaves) not in (tuple(sorted(REVIEW_LAYOUT)), tuple(sorted(BROAD_LAYOUT))):
            raise GateError("generated-evidence layout is not a closed review-v1 or broad-v1 layout")
    if any(
        not any(path.startswith(root + "/") for root in payload["ignored_evidence_roots"])
        for path in payload["generated_evidence_paths"]
    ):
        raise GateError("generated evidence path is outside ignored evidence roots")
    overlay = payload["frozen_overlay"]
    if overlay is not None:
        _validate_frozen_overlay_binding(overlay, label="subject")
        selected = set(overlay["selected_paths"])
        if not selected <= set(payload["task_subject_paths"]):
            raise GateError("subject frozen overlay selection is outside task subject")
        if selected & set(payload["allowed_post_launch_updates"]):
            raise GateError("subject frozen overlay selection overlaps allowed post-launch updates")
    for root in payload["ignored_evidence_roots"]:
        _ignored_root(repo_root, root, must_be_absent=False)


def capture_frozen_overlay(
    *, repo_root: Path, output: Path, eligible_paths: Iterable[str | Path]
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    eligible = _closed_paths(eligible_paths, "eligible")
    output_path = output if output.is_absolute() else repo_root / output
    output_rel = Path(os.path.abspath(output_path)).relative_to(repo_root).as_posix()
    root = str(PurePosixPath(output_rel).parent)
    _ignored_root(repo_root, root, must_be_absent=True)
    status = _status(repo_root)
    by_path = _status_map(status)
    dirty_eligible = sorted(path for path in eligible if path in by_path)
    selected = dirty_eligible
    if not selected:
        raise GateError("frozen overlay selected set must be non-empty")
    if any(by_path[path][0] not in (" ", "?") for path in selected):
        raise GateError("frozen overlay path may not be staged")
    inventory = [_inventory(repo_root, path, by_path) for path in selected]
    if any(row["type"] != "regular" for row in inventory):
        raise GateError("frozen overlay supports ordinary regular files only")
    payload = _seal({
        "schema": "workflow_verification_frozen_overlay.v1", "head": _head(repo_root),
        "index_tree": _index_tree(repo_root), "eligible_paths": eligible,
        "selected_paths": selected, "inventory": inventory,
    })
    _write_new_json(output, payload)
    validate_frozen_overlay(payload, repo_root=repo_root, record_path=output)
    return payload


def validate_frozen_overlay(
    payload: Mapping[str, Any],
    *,
    repo_root: Path,
    record_path: Path,
    expected_index_tree: str | None = None,
) -> None:
    _require_keys(payload, OVERLAY_KEYS, "frozen overlay")
    if payload["schema"] != "workflow_verification_frozen_overlay.v1":
        raise GateError("wrong frozen overlay schema")
    _validate_digest(payload, "frozen overlay")
    if (
        not isinstance(payload["head"], str)
        or not re.fullmatch(r"[0-9a-f]{40,64}", payload["head"])
        or payload["head"] != _head(repo_root)
        or not isinstance(payload["index_tree"], str)
        or not re.fullmatch(r"[0-9a-f]{40,64}", payload["index_tree"])
        or payload["index_tree"]
        != (_index_tree(repo_root) if expected_index_tree is None else expected_index_tree)
    ):
        raise GateError("frozen overlay HEAD/index-tree binding is invalid")
    if payload["eligible_paths"] != _closed_paths(payload["eligible_paths"], "eligible") or payload["selected_paths"] != _closed_paths(payload["selected_paths"], "selected"):
        raise GateError("frozen overlay paths are not sorted")
    if not payload["selected_paths"] or not set(payload["selected_paths"]) <= set(payload["eligible_paths"]):
        raise GateError("invalid frozen overlay selection")
    status = _status(repo_root)
    by_path = _status_map(status)
    dirty_eligible = sorted(path for path in payload["eligible_paths"] if path in by_path)
    if payload["selected_paths"] != dirty_eligible:
        raise GateError("frozen overlay selection does not equal every dirty eligible path")
    if not isinstance(payload["inventory"], list) or not payload["inventory"]:
        raise GateError("frozen overlay inventory must be non-empty")
    for row in payload["inventory"]:
        _validate_inventory_row(row)
    if [row["path"] for row in payload["inventory"]] != payload["selected_paths"]:
        raise GateError("frozen overlay inventory/selection mismatch")
    if any(row["type"] != "regular" for row in payload["inventory"]):
        raise GateError("frozen overlay inventory supports regular files only")
    current = [_inventory(repo_root, path, by_path) for path in payload["selected_paths"]]
    if current != payload["inventory"]:
        raise GateError("frozen overlay endpoint drift/mismatch")
    if any(by_path.get(path, "  ")[0] not in (" ", "?") for path in payload["selected_paths"]):
        raise GateError("frozen overlay row is staged")
    if record_path.is_symlink() or not record_path.is_file():
        raise GateError("frozen overlay record must be a regular non-symlink file")


def _require_regular_file(path: Path, *, label: str) -> None:
    try:
        details = path.lstat()
    except FileNotFoundError as exc:
        raise GateError(f"{label} is missing: {path}") from exc
    if not stat.S_ISREG(details.st_mode):
        raise GateError(f"{label} must be a regular non-symlink file: {path}")


def _file_binding(path: Path, repo_root: Path) -> dict[str, Any]:
    _require_regular_file(path, label="evidence")
    data = path.read_bytes()
    try:
        rel = path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError as exc:
        raise GateError(f"evidence is outside repository: {path}") from exc
    return {"path": rel, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def subject_binding(subject: Mapping[str, Any], *, subject_path: str | Path) -> dict[str, Any]:
    path = Path(subject_path)
    if not path.is_absolute():
        path = Path.cwd() / path
    data = path.read_bytes()
    return {
        "path": str(subject_path) if isinstance(subject_path, str) else path.as_posix(),
        "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(),
        "record_sha256": subject["record_sha256"], "head": subject["head"],
        "index_tree": subject["index_tree"], "full_status": subject["full_status"],
        "inventory": subject["inventory"],
    }


def _generated_entries(repo_root: Path, subject: Mapping[str, Any]) -> set[str]:
    found: set[str] = set()
    implicit = {f"{root}/subject.json" for root in subject["ignored_evidence_roots"]}
    allowed = set(subject["generated_evidence_paths"]) | implicit
    for root in subject["ignored_evidence_roots"]:
        base = repo_root / root
        if not base.exists():
            continue
        for path in base.rglob("*"):
            relative = path.relative_to(repo_root).as_posix()
            details = path.lstat()
            if stat.S_ISDIR(details.st_mode):
                if relative in allowed:
                    raise GateError(
                        f"declared ignored evidence must be a regular file: {relative}"
                    )
                continue
            found.add(relative)
            if relative in allowed and not stat.S_ISREG(details.st_mode):
                raise GateError(
                    f"declared ignored evidence must be a regular non-symlink file: {relative}"
                )
    for relative in allowed:
        path = repo_root / relative
        try:
            details = path.lstat()
        except FileNotFoundError:
            continue
        if not stat.S_ISREG(details.st_mode):
            raise GateError(
                f"declared ignored evidence must be a regular non-symlink file: {relative}"
            )
    extra = found - allowed
    if extra:
        raise GateError(f"undeclared ignored-root evidence: {sorted(extra)}")
    return found


def _validate_allowed_post_launch_transition(
    launch: Mapping[str, Any], current: Mapping[str, Any], *, phase: str
) -> None:
    if current["type"] != "regular":
        raise GateError("allowed post-launch transition must end as a regular file")
    if launch["type"] == "regular":
        if current["mode"] != launch["mode"]:
            raise GateError("allowed post-launch transition changed file mode")
    elif launch["type"] != "missing":
        raise GateError("allowed post-launch transition changed file type")
    if phase == "launch" and current["status"][0] not in (" ", "?"):
        raise GateError("allowed post-launch transition is staged before review")


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise GateError(f"invalid JSON evidence {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise GateError(f"expected JSON object: {path}")
    return payload


def verify_subject(
    subject: Mapping[str, Any], *, repo_root: Path, phase: str,
    generated_evidence: str | Path | None = None, review_subject: Mapping[str, Any] | None = None,
) -> None:
    repo_root = repo_root.resolve()
    validate_subject(subject, repo_root=repo_root)
    if _head(repo_root) != subject["head"]:
        raise GateError("HEAD drift")
    if subject["frozen_overlay"] is not None:
        binding = subject["frozen_overlay"]
        record_path = repo_root / binding["path"]
        record = _load_json(record_path)
        validate_frozen_overlay(
            record,
            repo_root=repo_root,
            record_path=record_path,
            expected_index_tree=subject["index_tree"],
        )
        file_binding = _file_binding(record_path, repo_root)
        if any(file_binding[key] != binding[key] for key in FILE_BINDING_KEYS):
            raise GateError("frozen overlay file binding drift")
        if record["record_sha256"] != binding["record_sha256"] or record["inventory"] != binding["inventory"]:
            raise GateError("frozen overlay copied binding drift")
    _generated_entries(repo_root, subject)
    current_status = _status_v2_complete(repo_root) if phase == "review" else _status(repo_root)
    current_by_path = _status_map(current_status)
    launch_rows = {row["path"]: row for row in subject["inventory"]}
    evidence_rel = None
    if generated_evidence is not None:
        evidence_path = Path(generated_evidence)
        if not evidence_path.is_absolute():
            evidence_path = repo_root / evidence_path
        evidence_rel = evidence_path.relative_to(repo_root).as_posix()
        allowed = set(subject["generated_evidence_paths"]) | set(subject["allowed_post_launch_updates"])
        if evidence_rel not in allowed:
            raise GateError("generated evidence path is not declared")
        _require_regular_file(evidence_path, label="supplied generated evidence")
        evidence_record = _load_json(evidence_path)
        validate_record(evidence_record, expected_schema=evidence_record.get("schema", ""))
        if evidence_record.get("subject", {}).get("record_sha256") != subject["record_sha256"]:
            raise GateError("generated evidence does not bind launch subject")
    if phase == "launch":
        allowed_transition = (
            set(subject["allowed_post_launch_updates"])
            if evidence_rel is not None
            else set()
        )
        expected_status = {row["path"]: row["status"] for row in subject["full_status"]}
        for path in allowed_transition:
            expected_status[path] = current_by_path.get(path, "CLEAN")
        if expected_status != current_by_path:
            raise GateError("launch full-status drift")
        for path, row in launch_rows.items():
            current = _inventory(repo_root, path, current_by_path)
            if path in allowed_transition:
                _validate_allowed_post_launch_transition(row, current, phase="launch")
            elif current != row:
                raise GateError(f"launch inventory drift: {path}")
        if _index_tree(repo_root) != subject["index_tree"]:
            raise GateError("launch index-tree drift")
        return
    if phase != "review" or review_subject is None:
        raise GateError("review phase requires review-subject envelope")
    validate_review_subject(review_subject)
    if review_subject["subject"]["record_sha256"] != subject["record_sha256"]:
        raise GateError("review envelope subject mismatch")
    subject_file = repo_root / review_subject["subject"]["path"]
    current_subject_binding = {**_file_binding(subject_file, repo_root), "record_sha256": subject["record_sha256"]}
    if current_subject_binding != review_subject["subject"]:
        raise GateError("review envelope launch-subject file binding drift")
    generated_path = repo_root / review_subject["generated_evidence"]["path"]
    if _evidence_binding(generated_path, repo_root) != review_subject["generated_evidence"]:
        raise GateError("review generated-evidence SHA binding drift")
    expected_review_status = {
        row["path"]: row["status"] for row in subject["full_status"]
    }
    for transition in review_subject["allowed_post_launch_updates"]:
        reviewed = transition["reviewed"]
        if reviewed["status"] in ("CLEAN", "ABSENT"):
            expected_review_status.pop(reviewed["path"], None)
        else:
            expected_review_status[reviewed["path"]] = reviewed["status"]
    for row in review_subject["staged_status"]:
        expected_review_status[row["path"]] = row["status"]
    if current_by_path != expected_review_status:
        raise GateError("review complete Git-status set drift or undeclared path")
    patch = hashlib.sha256(_git(repo_root, "diff", "--cached", "--binary")).hexdigest()
    if patch != review_subject["review_patch_sha256"] or _index_tree(repo_root) != review_subject["review_tree"]:
        raise GateError("review patch/tree drift")
    staged = [row for row in current_status if row["status"][0] not in (" ", "?")]
    if staged != review_subject["staged_status"]:
        raise GateError("review staged-status drift")
    if any(row["path"] not in subject["task_subject_paths"] for row in staged):
        raise GateError("review staged path outside task subject")
    if subject["frozen_overlay"] and any(row["path"] in subject["frozen_overlay"]["selected_paths"] for row in staged):
        raise GateError("frozen overlay row staged for review")
    allowed_post = set(subject["allowed_post_launch_updates"])
    for path, launch in launch_rows.items():
        current = _inventory(repo_root, path, current_by_path)
        if path in allowed_post:
            _validate_allowed_post_launch_transition(launch, current, phase="review")
        else:
            current = dict(current); current["status"] = launch["status"]
            if current != launch:
                raise GateError(f"review bytes drift outside allowed post-launch update: {path}")
    if review_subject["allowed_post_launch_updates"] != [
        {"launch": launch_rows[path], "reviewed": _inventory(repo_root, path, current_by_path)}
        for path in subject["allowed_post_launch_updates"]
    ]:
        raise GateError("review allowed-post-launch binding drift")


def _evidence_binding(path: Path, repo_root: Path) -> dict[str, Any]:
    binding = _file_binding(path, repo_root)
    payload = _load_json(path)
    if "record_sha256" in payload:
        binding["record_sha256"] = payload["record_sha256"]
    return binding


def build_review_subject(
    *, repo_root: Path, subject: Mapping[str, Any], subject_path: Path, generated_evidence: Path,
    review_patch_sha256: str, review_tree: str, output: Path,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    validate_subject(subject, repo_root=repo_root)
    current = _status(repo_root)
    by_path = _status_map(current)
    launch = {row["path"]: row for row in subject["inventory"]}
    staged = [row for row in current if row["status"][0] not in (" ", "?")]
    payload = _seal({
        "schema": "workflow_verification_review_subject.v1",
        "subject": {**_file_binding(subject_path, repo_root), "record_sha256": subject["record_sha256"]},
        "allowed_post_launch_updates": [
            {"launch": launch[path], "reviewed": _inventory(repo_root, path, by_path)}
            for path in subject["allowed_post_launch_updates"]
        ],
        "staged_status": staged, "review_patch_sha256": review_patch_sha256,
        "review_tree": review_tree, "generated_evidence": _evidence_binding(generated_evidence, repo_root),
        "frozen_overlay": subject["frozen_overlay"],
    })
    _write_new_json(output, payload)
    validate_review_subject(payload)
    return payload


def validate_review_subject(payload: Mapping[str, Any]) -> None:
    _require_keys(payload, REVIEW_SUBJECT_KEYS, "review subject")
    if payload["schema"] != "workflow_verification_review_subject.v1":
        raise GateError("wrong review-subject schema")
    _validate_digest(payload, "review subject")
    if not re.fullmatch(r"[0-9a-f]{64}", payload["review_patch_sha256"] or "") or not re.fullmatch(r"[0-9a-f]{40,64}", payload["review_tree"] or ""):
        raise GateError("invalid review patch/tree digest")
    _validate_file_binding_shape(
        payload["subject"], include_record_digest=True, label="review subject launch"
    )
    if not isinstance(payload["allowed_post_launch_updates"], list) or any(
        set(row) != {"launch", "reviewed"} for row in payload["allowed_post_launch_updates"]
    ):
        raise GateError("review allowed-post-launch domain is not closed")
    transition_paths: list[str] = []
    for transition in payload["allowed_post_launch_updates"]:
        _validate_inventory_row(transition["launch"])
        _validate_inventory_row(transition["reviewed"], allow_any_status=True)
        if transition["launch"]["path"] != transition["reviewed"]["path"]:
            raise GateError("review allowed-post-launch path mismatch")
        transition_paths.append(transition["launch"]["path"])
    if transition_paths != sorted(transition_paths) or len(set(transition_paths)) != len(transition_paths):
        raise GateError("review allowed-post-launch paths are not sorted and unique")
    if not isinstance(payload["staged_status"], list) or not payload["staged_status"]:
        raise GateError("review staged status must be a non-empty list")
    for row in payload["staged_status"]:
        _validate_status_row(row, staged=True, label="review staged status")
    if payload["staged_status"] != sorted(payload["staged_status"], key=lambda row: row["path"]):
        raise GateError("review staged status is not sorted")
    if len({row["path"] for row in payload["staged_status"]}) != len(payload["staged_status"]):
        raise GateError("review staged status contains duplicate paths")
    _validate_file_binding_shape(
        payload["generated_evidence"],
        include_record_digest=True,
        label="review generated-evidence",
    )
    if payload["frozen_overlay"] is not None:
        _validate_frozen_overlay_binding(payload["frozen_overlay"], label="review")


def write_exit_status(path: Path, *, phase: str, argv: Sequence[str], exit_code: int) -> dict[str, Any]:
    if phase not in ("collection", "broad") or not argv or not all(isinstance(arg, str) for arg in argv) or not isinstance(exit_code, int):
        raise GateError("invalid exit-status fields")
    payload = _seal({"schema": "workflow_broad_command_status.v1", "phase": phase, "argv": list(argv), "exit_code": exit_code})
    _publish_new_json_atomically(path, payload)
    return payload


def load_exit_status(path: Path, *, expected_phase: str, expected_exit: int) -> dict[str, Any]:
    payload = _load_json(path)
    _require_keys(payload, EXIT_STATUS_KEYS, "command status")
    _validate_digest(payload, "command status")
    if payload["schema"] != "workflow_broad_command_status.v1" or payload["phase"] != expected_phase or payload["exit_code"] != expected_exit:
        raise GateError(f"unexpected {expected_phase} command exit")
    if not isinstance(payload["argv"], list) or not payload["argv"] or not all(isinstance(arg, str) for arg in payload["argv"]):
        raise GateError("invalid command argv")
    return payload


def normalize_failure_text(text: str, *, repo_root: Path) -> str:
    normalized = text.replace(repo_root.resolve().as_posix(), "$REPO")
    normalized = _PYTEST_SESSION_ROOT.sub("$PYTEST_TMP", normalized)
    normalized = _ELAPSED.sub(
        lambda m: f"{m.group('prefix')}$TIME{m.group('line_ending')}", normalized
    )
    normalized = _REPR_ADDR.sub(lambda m: f"{m.group('prefix')}$ADDR", normalized)
    normalized = _LOGGING_LINE.sub(lambda m: f"{m.group('prefix')}$LINE", normalized)
    return normalized


def canonical_failure_from_junit(path: Path, *, nodeid: str, repo_root: Path) -> dict[str, Any]:
    try:
        root = ET.parse(path).getroot()
    except (ET.ParseError, OSError) as exc:
        raise GateError(f"invalid JUnit XML: {path}") from exc
    cases = root.findall(".//testcase")
    if len(cases) != 1:
        raise GateError("isolated JUnit must contain exactly one testcase")
    case = cases[0]
    expected_parts = nodeid.split("::")
    expected_name = expected_parts[-1]
    expected_classname = expected_parts[0].removesuffix(".py").replace("/", ".")
    if len(expected_parts) > 2:
        expected_classname += "." + ".".join(expected_parts[1:-1])
    if case.get("name") != expected_name or case.get("classname") != expected_classname:
        raise GateError("isolated JUnit testcase node ID does not equal invoked node")
    children = [child for child in case if child.tag in ("failure", "error")]
    if len(children) != 1 or children[0].tag != "failure":
        raise GateError("isolated JUnit must contain exactly one ordinary failure")
    failure = children[0]
    message = normalize_failure_text(failure.get("message", "").strip(), repo_root=repo_root)
    body = normalize_failure_text((failure.text or "").strip(), repo_root=repo_root)
    exception_match = re.match(r"([A-Za-z_][A-Za-z0-9_.]*(?:Error|Exception))(?::|$)", message)
    if exception_match:
        exception = exception_match.group(1)
    else:
        body_match = re.search(r"(?m)([A-Za-z_][A-Za-z0-9_.]*(?:Error|Exception))(?::|$)", body)
        exception = body_match.group(1) if body_match else "AssertionError"
    if exception != "AssertionError":
        detail = message.removeprefix(exception).removeprefix(":").strip()
        signature = f"{exception} | {_double_quote_python_strings(detail)}"
    else:
        source = _source_assertion(body)
        asserted = message.removeprefix("AssertionError:").strip().splitlines()[0]
        if asserted in ("", "AssertionError"):
            evidence = next((line[1:].strip() for line in body.splitlines() if line.startswith("E") and "assert " in line), "")
            asserted = evidence.removeprefix("AssertionError:").strip()
        if not source:
            source = asserted
        compared = asserted.removeprefix("assert ").strip()
        if " not in " in source and "is contained" in message:
            left, right = source.removeprefix("assert ").split(" not in ", 1)
            comparison = f"{left} is contained in {right}"
        elif not re.search(r"(?:==|!=|\bis\b|<=|>=|<|>)", compared):
            comparison = f"{compared} is truthy"
        else:
            comparison = compared
        signature = f"AssertionError | {source} | compared: {_double_quote_python_strings(comparison)}"
    if not signature:
        raise GateError("empty normalized failure signature")
    return {"schema": "workflow_broad_canonical_failure.v1", "nodeid": nodeid, "outcome": "failure", "exception_type": exception, "normalized_failure_signature": signature}


def _source_assertion(body: str) -> str:
    lines = body.splitlines()
    for index, line in enumerate(lines):
        if not line.startswith(">"):
            continue
        first = line[1:].strip()
        if not first.startswith("assert "):
            continue
        parts = [first]
        if first.endswith("("):
            for following in lines[index + 1 :]:
                if following.startswith("E"):
                    break
                stripped = following.strip()
                if stripped:
                    parts.append(stripped)
                if stripped == ")":
                    break
        source = " ".join(parts)
        source = re.sub(r"\(\s+", "(", source)
        source = re.sub(r"\s+\)", ")", source)
        return source
    return ""


def _double_quote_python_strings(text: str) -> str:
    def replace(match: re.Match[str]) -> str:
        try:
            value = ast.literal_eval(match.group(0))
        except (SyntaxError, ValueError):
            return match.group(0)
        return json.dumps(value, ensure_ascii=True) if isinstance(value, str) else match.group(0)
    return re.sub(r"'(?:[^'\\]|\\.)*'", replace, text)


def validate_record(payload: Mapping[str, Any], *, expected_schema: str) -> None:
    if payload.get("schema") != expected_schema:
        raise GateError(f"wrong schema: expected {expected_schema}")
    if "record_sha256" not in payload:
        raise GateError("record lacks self-digest")
    _validate_digest(payload, expected_schema)


def _row_identity(row: Mapping[str, Any]) -> tuple[str, str]:
    payload = row.get("canonical_payload")
    if not isinstance(payload, Mapping):
        raise GateError("failure row lacks canonical payload")
    digest = hashlib.sha256(_canonical(payload)).hexdigest()
    if digest != row.get("canonical_payload_sha256"):
        raise GateError("canonical failure payload digest mismatch")
    if row.get("nodeid") != payload.get("nodeid") or row.get("isolated_exit") != 1:
        raise GateError("invalid isolated failure row")
    stable = row.get("stable_signature_sha256")
    projection = {
        "nodeid": row["nodeid"],
        "normalized_failure_signature": row.get("normalized_failure_signature"),
    }
    if (
        not isinstance(stable, str)
        or not re.fullmatch(r"[0-9a-f]{64}", stable)
        or stable != hashlib.sha256(_canonical(projection)).hexdigest()
        or payload.get("normalized_failure_signature") != row.get("normalized_failure_signature")
    ):
        raise GateError("failure row lacks stable-signature digest")
    return row["nodeid"], stable


def _failure_identity_set(rows: Sequence[Mapping[str, Any]]) -> set[tuple[str, str]]:
    identities = [_row_identity(row) for row in rows]
    if len(set(identities)) != len(identities):
        raise GateError("duplicate failure rows")
    return set(identities)


def compare_outcome(
    baseline: Mapping[str, Any],
    outcome: Mapping[str, Any],
    *,
    remediations: Sequence[tuple[Mapping[str, Any], Path]],
    repo_root: Path,
) -> dict[str, Any]:
    validate_baseline(baseline, repo_root=repo_root)
    validate_outcome(outcome, repo_root=repo_root)
    _failure_identity_set(baseline["failure_rows"])
    _failure_identity_set(outcome["failure_rows"])
    base = {_row_identity(row): row for row in baseline["failure_rows"]}
    observed = {_row_identity(row): row for row in outcome["failure_rows"]}
    validated_remediations: list[Mapping[str, Any]] = []
    for remediation, remediation_path in remediations:
        validate_remediation(
            remediation, repo_root=repo_root, remediation_path=remediation_path
        )
        validated_remediations.append(remediation)
    if set(observed) == set(base) and outcome["broad"]["status"]["exit_code"] == (1 if base else 0):
        return {"accepted": True, "mode": "exact"}
    removed: dict[tuple[str, str], Mapping[str, Any]] = {}
    for remediation in validated_remediations:
        if remediation.get("baseline_record_sha256") != baseline["record_sha256"]:
            raise GateError("remediation baseline mismatch")
        for row in remediation.get("removed_rows", []):
            key = (row["nodeid"], row["stable_signature_sha256"])
            if key not in base or key in removed:
                raise GateError("overlapping, duplicate, or non-baseline remediation row")
            baseline_row = base[key]
            if (
                row["canonical_payload_sha256"] != baseline_row["canonical_payload_sha256"]
                or row["baseline_row_sha256"] != hashlib.sha256(_canonical(baseline_row)).hexdigest()
            ):
                raise GateError("remediation removed-row binding mismatch")
            removed[key] = row
    if not removed or set(observed) != set(base) - set(removed):
        raise GateError("outcome is neither exact baseline nor reviewed strict subset")
    expected_exit = 1 if observed else 0
    if outcome["broad"]["status"]["exit_code"] != expected_exit:
        raise GateError("subset broad exit mismatch")
    passing = {row.get("nodeid") for row in outcome["passing_rows"] if row.get("isolated_exit") == 0}
    if passing != {key[0] for key in removed}:
        raise GateError("remediated rows lack fresh isolated passing proof")
    return {"accepted": True, "mode": "reviewed_subset"}


def _artifact(path: Path, root: Path) -> dict[str, Any]:
    if not path.is_absolute():
        path = root / path
    path = path.resolve()
    data = path.read_bytes()
    return {"path": path.relative_to(root).as_posix(), "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def _authority_bindings(paths: Iterable[Path], repo_root: Path) -> dict[str, dict[str, Any]]:
    bindings = [_artifact(path, repo_root) for path in paths]
    return {binding["path"]: binding for binding in bindings}


def _junit_totals(path: Path) -> dict[str, int]:
    root = ET.parse(path).getroot()
    suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite"))
    totals = {key: sum(int(suite.get(key, "0")) for suite in suites) for key in ("tests", "failures", "errors", "skipped")}
    totals["passed"] = totals["tests"] - totals["failures"] - totals["errors"] - totals["skipped"]
    return totals


_SUMMARY_FIELDS = {
    "failed": "failures",
    "passed": "passed",
    "skipped": "skipped",
    "xfailed": "xfailed",
    "xpassed": "xpassed",
    "error": "errors",
    "errors": "errors",
}


def _pytest_summary_totals(path: Path) -> dict[str, int]:
    text = path.read_text(encoding="utf-8", errors="strict")
    matches = list(_ELAPSED.finditer(text))
    if not matches:
        raise GateError("cannot derive pytest broad summary totals")
    summary = matches[-1].group("prefix").removesuffix(" in ")
    totals = {
        "failures": 0,
        "errors": 0,
        "skipped": 0,
        "passed": 0,
        "xfailed": 0,
        "xpassed": 0,
    }
    for count_text, label in re.findall(r"(\d+) ([a-z]+)", summary):
        field = _SUMMARY_FIELDS.get(label)
        if field is not None:
            totals[field] += int(count_text)
    totals["tests"] = sum(totals.values())
    return {key: totals[key] for key in ("tests", "failures", "errors", "skipped", "passed", "xfailed", "xpassed")}


def _collection_nodeids(path: Path) -> list[str]:
    collected = _collection_count(path)
    nodeids = [
        line.strip()
        for line in path.read_text(encoding="utf-8", errors="strict").splitlines()
        if "::" in line and line.strip() == line
    ]
    if len(nodeids) != collected or len(set(nodeids)) != len(nodeids):
        raise GateError("collection node inventory is incomplete or duplicate")
    return nodeids


def _nodeid_junit_key(nodeid: str) -> tuple[str, str]:
    parts: list[str] = []
    start = 0
    bracket_depth = 0
    index = 0
    while index < len(nodeid):
        if nodeid[index] == "[":
            bracket_depth += 1
        elif nodeid[index] == "]" and bracket_depth:
            bracket_depth -= 1
        elif nodeid[index:index + 2] == "::" and bracket_depth == 0:
            parts.append(nodeid[start:index])
            start = index + 2
            index += 1
        index += 1
    parts.append(nodeid[start:])
    if len(parts) < 2 or not all(parts):
        raise GateError(f"invalid collected node ID: {nodeid}")
    classname = parts[0].removesuffix(".py").replace("/", ".")
    if len(parts) > 2:
        classname += "." + ".".join(parts[1:-1])
    return classname, parts[-1]


def _reconcile_collection_junit_inventory(collection_log: Path, junit_path: Path) -> dict[str, str]:
    nodeids = _collection_nodeids(collection_log)
    by_key: dict[tuple[str, str], str] = {}
    for nodeid in nodeids:
        key = _nodeid_junit_key(nodeid)
        if key in by_key:
            raise GateError("collection node inventory has ambiguous JUnit identities")
        by_key[key] = nodeid
    try:
        cases = ET.parse(junit_path).getroot().findall(".//testcase")
    except (ET.ParseError, OSError) as exc:
        raise GateError(f"invalid broad JUnit XML: {junit_path}") from exc
    result: dict[str, str] = {}
    for case in cases:
        key = (case.get("classname") or "", case.get("name") or "")
        nodeid = by_key.get(key)
        if nodeid is None:
            raise GateError(f"unknown JUnit testcase outside collection inventory: {key}")
        if nodeid in result:
            raise GateError(f"duplicate JUnit testcase inventory row: {nodeid}")
        children = [child for child in case if child.tag in ("failure", "error", "skipped")]
        if len(children) > 1:
            raise GateError(f"JUnit testcase has multiple outcomes: {nodeid}")
        if not children:
            result[nodeid] = "passed"
        elif children[0].tag == "skipped" and children[0].get("type") == "pytest.xfail":
            result[nodeid] = "xfailed"
        else:
            result[nodeid] = children[0].tag
    missing = sorted(set(nodeids) - set(result))
    if missing:
        raise GateError(f"missing JUnit testcase inventory rows: {missing}")
    return result


def _authoritative_broad_totals(
    collection_log: Path, broad_log: Path, junit_path: Path
) -> dict[str, int]:
    summary = _pytest_summary_totals(broad_log)
    inventory = _reconcile_collection_junit_inventory(collection_log, junit_path)
    classified = {
        label: sum(status == label for status in inventory.values())
        for label in ("passed", "failure", "error", "skipped", "xfailed")
    }
    junit = _junit_totals(junit_path)
    if (
        junit["tests"] != summary["tests"]
        or junit["failures"] != summary["failures"]
        or junit["errors"] != summary["errors"]
        or junit["skipped"] != summary["skipped"] + summary["xfailed"]
        or junit["passed"] != summary["passed"] + summary["xpassed"]
        or classified["failure"] != summary["failures"]
        or classified["error"] != summary["errors"]
        or classified["skipped"] != summary["skipped"]
        or classified["xfailed"] != summary["xfailed"]
        or classified["passed"] != summary["passed"] + summary["xpassed"]
    ):
        raise GateError("broad pytest summary/JUnit/collection totals do not reconcile")
    return summary


def build_baseline(
    *, repo_root: Path, authority_path: Path, correction_path: Path, normalizer_path: Path,
    subject_path: Path, capture_root: Path, output: Path,
) -> dict[str, Any]:
    pinned = {
        authority_path: "d7bcad2eabf075bcb1f5a5e62bee600add68f075f0b51f15dc53644a4105f9f2",
        correction_path: "4c1b7e3ce36872df9e9f522c5709801290d10541676d5e58cbd31facecac6cbd",
        normalizer_path: "f1157d11c8b8f8c1a2aacb72d4424ef3ddfc5c2cbe8ace076f6411ac6fc28dec",
    }
    authorities = _authority_bindings(pinned, repo_root)
    for path, expected in pinned.items():
        binding = authorities[_artifact(path, repo_root)["path"]]
        if binding["sha256"] != expected:
            raise GateError(f"authority digest mismatch: {path}")
    subject = _load_json(subject_path)
    validate_subject(subject, repo_root=repo_root)
    verify_subject(subject, repo_root=repo_root, phase="launch")
    collect_status = load_exit_status(capture_root / "collection.status.json", expected_phase="collection", expected_exit=0)
    broad_status = load_exit_status(capture_root / "broad.status.json", expected_phase="broad", expected_exit=1)
    authority = _load_json(authority_path)
    authority_rows = [row for row in authority["failures"] if row.get("category") == "established_unrelated"]
    if len(authority_rows) != 6:
        raise GateError("authority must contain exactly six established_unrelated rows")
    failures = []
    for index, accepted in enumerate(authority_rows):
        stem = capture_root / "isolated" / f"row-{index:02d}"
        status_path, log_path, junit_path = stem.with_suffix(".status.json"), stem.with_suffix(".log"), stem.with_suffix(".xml")
        status = _load_json(status_path)
        if set(status) != {"schema", "row_index", "nodeid", "argv", "exit_code"} or status.get("schema") != "workflow_broad_isolated_status.v1" or status.get("row_index") != index or status.get("nodeid") != accepted["nodeid"] or status.get("exit_code") != 1:
            raise GateError(f"invalid isolated status row {index}")
        payload = canonical_failure_from_junit(junit_path, nodeid=accepted["nodeid"], repo_root=repo_root)
        if payload["normalized_failure_signature"] != accepted["normalized_failure_signature"]:
            raise GateError(f"authority failure signature mismatch for {accepted['nodeid']}: {payload['normalized_failure_signature']!r}")
        payload_sha = hashlib.sha256(_canonical(payload)).hexdigest()
        signature_projection = {"nodeid": accepted["nodeid"], "normalized_failure_signature": accepted["normalized_failure_signature"]}
        row = {
            "nodeid": accepted["nodeid"], "normalized_failure_signature": accepted["normalized_failure_signature"],
            "isolated_argv": status["argv"], "isolated_exit": 1,
            "raw_log": _artifact(log_path, repo_root), "raw_junit": _artifact(junit_path, repo_root),
            "raw_status": _artifact(status_path, repo_root),
            "canonical_payload": payload, "canonical_payload_sha256": payload_sha,
            "stable_signature_sha256": hashlib.sha256(_canonical(signature_projection)).hexdigest(),
        }
        row["authority_row_sha256"] = hashlib.sha256(_canonical(accepted)).hexdigest()
        failures.append(row)
    junit = capture_root / "junit.xml"
    expected_failure_nodes = [row["nodeid"] for row in failures]
    if _broad_failed_nodeids(
        junit, expected_nodeids=expected_failure_nodes
    ) != set(expected_failure_nodes):
        raise GateError("broad JUnit failures do not equal exact authority failure rows")
    payload = _seal({
        "schema": "workflow_broad_known_failure_baseline.v1",
        "implementation_base_commit": subject["head"],
        "captured_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "subject": {**_file_binding(subject_path, repo_root), "record_sha256": subject["record_sha256"], "head": subject["head"], "index_tree": subject["index_tree"], "full_status": subject["full_status"], "inventory": subject["inventory"]},
        "environment": {"python": sys.version, "pytest": _pytest_version(), "platform": platform.platform()},
        "normalization": {"schema": "workflow_broad_failure_normalization.v1", "helper_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()},
        "authorities": authorities,
        "collection": {"status": collect_status, "log": _artifact(capture_root / "collection.log", repo_root), "collected": _collection_count(capture_root / "collection.log")},
        "broad": {
            "status": broad_status,
            "log": _artifact(capture_root / "broad.log", repo_root),
            "junit": _artifact(junit, repo_root),
            "totals": _authoritative_broad_totals(
                capture_root / "collection.log", capture_root / "broad.log", junit
            ),
        },
        "failure_rows": failures,
    })
    if payload["broad"]["totals"]["failures"] != 6 or payload["broad"]["totals"]["errors"] != 0:
        raise GateError("broad totals do not equal six ordinary failures")
    _write_new_json(output, payload)
    validate_baseline(payload, repo_root=repo_root)
    return payload


def _pytest_version() -> str:
    import pytest
    return pytest.__version__


def _collection_count(path: Path) -> int:
    text = path.read_text(encoding="utf-8")
    match = re.search(r"(?m)^(\d+) tests? collected", text)
    if not match:
        match = re.search(r"(?m)^collected (\d+) items", text)
    if not match:
        raise GateError("cannot derive collected count")
    return int(match.group(1))


def validate_baseline(payload: Mapping[str, Any], *, repo_root: Path) -> None:
    validate_record(payload, expected_schema="workflow_broad_known_failure_baseline.v1")
    expected_keys = {
        "schema", "implementation_base_commit", "captured_at", "subject", "environment",
        "normalization", "authorities", "collection", "broad", "failure_rows", "record_sha256",
    }
    if set(payload) != expected_keys:
        raise GateError("baseline keys are not closed")
    if payload.get("implementation_base_commit") != "451765a2ebd374111d2cbeab0969cec4830717fb":
        raise GateError("wrong implementation base commit")
    _validate_utc_timestamp(payload.get("captured_at"), "baseline capture timestamp")
    if set(payload.get("environment", {})) != {"python", "pytest", "platform"} or not all(
        isinstance(value, str) and value for value in payload["environment"].values()
    ):
        raise GateError("baseline environment domain is not closed")
    normalization = payload.get("normalization", {})
    if set(normalization) != {"schema", "helper_sha256"} or normalization.get("schema") != "workflow_broad_failure_normalization.v1":
        raise GateError("baseline normalization domain is not closed")
    if normalization.get("helper_sha256") != hashlib.sha256(Path(__file__).read_bytes()).hexdigest():
        raise GateError("baseline helper/normalizer digest drift")
    authority_pins = {
        "docs/plans/evidence/procedure-first-migration-waves/task8-baseline-replay/adjudication.json": "d7bcad2eabf075bcb1f5a5e62bee600add68f075f0b51f15dc53644a4105f9f2",
        "docs/plans/2026-07-13-procedure-migration-identity-compatibility-baseline-correction.json": "4c1b7e3ce36872df9e9f522c5709801290d10541676d5e58cbd31facecac6cbd",
        "tests/workflow_lisp_procedure_identity.py": "f1157d11c8b8f8c1a2aacb72d4424ef3ddfc5c2cbe8ace076f6411ac6fc28dec",
    }
    if set(payload.get("authorities", {})) != set(authority_pins):
        raise GateError("baseline authority domain is not closed")
    for path, expected_sha in authority_pins.items():
        binding = payload["authorities"][path]
        _validate_artifact_binding(binding, repo_root=repo_root)
        if binding["path"] != path or binding["sha256"] != expected_sha:
            raise GateError(f"baseline authority binding mismatch: {path}")
    subject_binding_value = payload.get("subject", {})
    if set(subject_binding_value) != {"path", "bytes", "sha256", "record_sha256", "head", "index_tree", "full_status", "inventory"}:
        raise GateError("baseline subject binding is not closed")
    _validate_artifact_binding({key: subject_binding_value[key] for key in FILE_BINDING_KEYS}, repo_root=repo_root)
    subject_path = repo_root / subject_binding_value["path"]
    subject = _load_json(subject_path)
    validate_subject(subject, repo_root=repo_root)
    for key in ("record_sha256", "head", "index_tree", "full_status", "inventory"):
        if subject_binding_value[key] != subject[key]:
            raise GateError(f"baseline subject {key} mismatch")
    if subject["head"] != payload["implementation_base_commit"]:
        raise GateError("baseline subject HEAD does not equal implementation base")
    collection = payload.get("collection", {})
    if set(collection) != {"status", "log", "collected"}:
        raise GateError("baseline collection domain is not closed")
    _validate_exit_status_payload(collection["status"], expected_phase="collection", expected_exit=0)
    if collection["status"]["argv"] != ["pytest", "--collect-only", "-q"]:
        raise GateError("baseline collection argv mismatch")
    _validate_artifact_binding(collection["log"], repo_root=repo_root)
    if collection["collected"] != _collection_count(repo_root / collection["log"]["path"]):
        raise GateError("baseline collected count mismatch")
    broad = payload.get("broad", {})
    if set(broad) != {"status", "log", "junit", "totals"}:
        raise GateError("baseline broad domain is not closed")
    _validate_exit_status_payload(broad["status"], expected_phase="broad", expected_exit=1)
    _validate_artifact_binding(broad["log"], repo_root=repo_root)
    _validate_artifact_binding(broad["junit"], repo_root=repo_root)
    expected_broad_argv = [
        "pytest", "-q", "-n", "16", "--dist=worksteal",
        f"--junitxml={broad['junit']['path']}",
    ]
    if broad["status"]["argv"] != expected_broad_argv:
        raise GateError("baseline broad argv mismatch")
    if set(broad["totals"]) != {"tests", "failures", "errors", "skipped", "passed", "xfailed", "xpassed"}:
        raise GateError("baseline totals domain is not closed")
    if broad["totals"] != _authoritative_broad_totals(
        repo_root / collection["log"]["path"],
        repo_root / broad["log"]["path"],
        repo_root / broad["junit"]["path"],
    ):
        raise GateError("baseline broad totals mismatch")
    totals = broad["totals"]
    if totals["tests"] != collection["collected"] or totals["failures"] != 6 or totals["errors"] != 0 or sum(totals[key] for key in ("passed", "failures", "errors", "skipped", "xfailed", "xpassed")) != totals["tests"]:
        raise GateError("baseline totals/count domain mismatch")
    if len(payload.get("failure_rows", [])) != 6:
        raise GateError("baseline must contain exactly six failure rows")
    authority = _load_json(repo_root / next(iter(authority_pins)))
    authority_rows = [row for row in authority["failures"] if row.get("category") == "established_unrelated"]
    failure_keys = {"nodeid", "normalized_failure_signature", "isolated_argv", "isolated_exit", "raw_log", "raw_junit", "raw_status", "canonical_payload", "canonical_payload_sha256", "stable_signature_sha256", "authority_row_sha256"}
    for index, (row, accepted) in enumerate(zip(payload["failure_rows"], authority_rows, strict=True)):
        if set(row) != failure_keys:
            raise GateError("baseline failure row keys are not closed")
        if row["nodeid"] != accepted["nodeid"] or row["normalized_failure_signature"] != accepted["normalized_failure_signature"] or row["authority_row_sha256"] != hashlib.sha256(_canonical(accepted)).hexdigest():
            raise GateError("baseline authority row mismatch")
        expected_argv = [sys.executable, "-m", "pytest", "-q", row["nodeid"], f"--junitxml={row['raw_junit']['path']}"]
        if row["isolated_exit"] != 1 or row["isolated_argv"] != expected_argv:
            raise GateError("baseline isolated argv/exit mismatch")
        _validate_artifact_binding(row["raw_log"], repo_root=repo_root)
        _validate_artifact_binding(row["raw_junit"], repo_root=repo_root)
        _validate_artifact_binding(row["raw_status"], repo_root=repo_root)
        isolated_status = _load_json(repo_root / row["raw_status"]["path"])
        if set(isolated_status) != {"schema", "row_index", "nodeid", "argv", "exit_code"} or isolated_status != {
            "schema": "workflow_broad_isolated_status.v1", "row_index": index,
            "nodeid": row["nodeid"], "argv": expected_argv, "exit_code": 1,
        }:
            raise GateError("baseline isolated status domain mismatch")
        canonical = canonical_failure_from_junit(repo_root / row["raw_junit"]["path"], nodeid=row["nodeid"], repo_root=repo_root)
        if canonical != row["canonical_payload"]:
            raise GateError("baseline canonical JUnit payload mismatch")
        projection = {"nodeid": row["nodeid"], "normalized_failure_signature": row["normalized_failure_signature"]}
        if row["stable_signature_sha256"] != hashlib.sha256(_canonical(projection)).hexdigest():
            raise GateError("baseline stable signature digest mismatch")
    identities = [_row_identity(row) for row in payload["failure_rows"]]
    if len(set(identities)) != 6:
        raise GateError("baseline failure identities are not unique")
    expected_failure_nodes = [row["nodeid"] for row in payload["failure_rows"]]
    if _broad_failed_nodeids(
        repo_root / broad["junit"]["path"], expected_nodeids=expected_failure_nodes
    ) != set(expected_failure_nodes):
        raise GateError("baseline broad JUnit failures do not equal authority failure rows")


def _validate_artifact_binding(binding: Mapping[str, Any], *, repo_root: Path) -> None:
    _validate_file_binding_shape(
        binding, include_record_digest=False, label="artifact"
    )
    path = _repo_path(binding["path"])
    actual = _artifact(Path(path), repo_root)
    if dict(binding) != actual:
        raise GateError(f"artifact binding mismatch: {path}")


def _validate_exit_status_payload(payload: Mapping[str, Any], *, expected_phase: str, expected_exit: int) -> None:
    _require_keys(payload, EXIT_STATUS_KEYS, "command status")
    _validate_digest(payload, "command status")
    if payload.get("schema") != "workflow_broad_command_status.v1" or payload.get("phase") != expected_phase or payload.get("exit_code") != expected_exit or not isinstance(payload.get("argv"), list) or not payload["argv"] or not all(isinstance(arg, str) for arg in payload["argv"]):
        raise GateError("invalid embedded command status")


def _validate_utc_timestamp(value: Any, label: str) -> None:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise GateError(f"invalid {label}")
    try:
        parsed = datetime.fromisoformat(value.removesuffix("Z") + "+00:00")
    except ValueError as exc:
        raise GateError(f"invalid {label}") from exc
    if parsed.tzinfo != timezone.utc:
        raise GateError(f"invalid {label}")


def _baseline_binding(path: Path, baseline: Mapping[str, Any], repo_root: Path) -> dict[str, Any]:
    return {**_file_binding(path, repo_root), "record_sha256": baseline["record_sha256"]}


def _subject_evidence_binding(path: Path, subject: Mapping[str, Any], repo_root: Path) -> dict[str, Any]:
    return {
        **_file_binding(path, repo_root),
        "record_sha256": subject["record_sha256"],
        "head": subject["head"],
        "index_tree": subject["index_tree"],
        "full_status": subject["full_status"],
        "inventory": subject["inventory"],
    }


def _testcase_matches_nodeid(case: ET.Element, nodeid: str) -> bool:
    return (case.get("classname"), case.get("name")) == _nodeid_junit_key(nodeid)


def _validate_passing_junit(path: Path, *, nodeid: str) -> None:
    try:
        cases = ET.parse(path).getroot().findall(".//testcase")
    except (ET.ParseError, OSError) as exc:
        raise GateError(f"invalid passing JUnit XML: {path}") from exc
    if len(cases) != 1 or not _testcase_matches_nodeid(cases[0], nodeid):
        raise GateError("passing isolated JUnit node ID mismatch")
    if any(child.tag in ("failure", "error", "skipped") for child in cases[0]):
        raise GateError("passing isolated JUnit is not one ordinary pass")


def _broad_failed_nodeids(path: Path, *, expected_nodeids: Sequence[str]) -> set[str]:
    try:
        cases = ET.parse(path).getroot().findall(".//testcase")
    except (ET.ParseError, OSError) as exc:
        raise GateError(f"invalid broad JUnit XML: {path}") from exc
    failed: set[str] = set()
    for case in cases:
        if not any(child.tag in ("failure", "error") for child in case):
            continue
        matches = [nodeid for nodeid in expected_nodeids if _testcase_matches_nodeid(case, nodeid)]
        if len(matches) != 1:
            raise GateError("broad JUnit failure does not map to exactly one baseline node ID")
        failed.add(matches[0])
    return failed


def build_outcome(
    *, repo_root: Path, baseline_path: Path, subject_path: Path, capture_root: Path, output: Path,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    baseline = _load_json(baseline_path)
    validate_baseline(baseline, repo_root=repo_root)
    subject = _load_json(subject_path)
    validate_subject(subject, repo_root=repo_root)
    verify_subject(subject, repo_root=repo_root, phase="launch")
    collection_status = load_exit_status(capture_root / "collection.status.json", expected_phase="collection", expected_exit=0)
    broad_status_payload = _load_json(capture_root / "broad.status.json")
    broad_exit = broad_status_payload.get("exit_code")
    if broad_exit not in (0, 1):
        raise GateError("outcome broad exit must be 0 or 1")
    _validate_exit_status_payload(broad_status_payload, expected_phase="broad", expected_exit=broad_exit)
    failure_rows: list[dict[str, Any]] = []
    passing_rows: list[dict[str, Any]] = []
    for index, baseline_row in enumerate(baseline["failure_rows"]):
        stem = capture_root / "isolated" / f"row-{index:02d}"
        status_path = stem.with_suffix(".status.json")
        log_path = stem.with_suffix(".log")
        junit_path = stem.with_suffix(".xml")
        status = _load_json(status_path)
        junit_binding = _artifact(junit_path, repo_root)
        expected_argv = [sys.executable, "-m", "pytest", "-q", baseline_row["nodeid"], f"--junitxml={junit_binding['path']}"]
        expected_status = {
            "schema": "workflow_broad_isolated_status.v1", "row_index": index,
            "nodeid": baseline_row["nodeid"], "argv": expected_argv,
            "exit_code": status.get("exit_code"),
        }
        if set(status) != set(expected_status) or status != expected_status or status["exit_code"] not in (0, 1):
            raise GateError(f"invalid outcome isolated status row {index}")
        common = {
            "nodeid": baseline_row["nodeid"], "isolated_argv": expected_argv,
            "isolated_exit": status["exit_code"], "raw_log": _artifact(log_path, repo_root),
            "raw_junit": junit_binding, "raw_status": _artifact(status_path, repo_root),
            "baseline_row_sha256": hashlib.sha256(_canonical(baseline_row)).hexdigest(),
        }
        if status["exit_code"] == 0:
            _validate_passing_junit(junit_path, nodeid=baseline_row["nodeid"])
            passing_rows.append(common)
            continue
        canonical = canonical_failure_from_junit(junit_path, nodeid=baseline_row["nodeid"], repo_root=repo_root)
        signature_projection = {"nodeid": baseline_row["nodeid"], "normalized_failure_signature": canonical["normalized_failure_signature"]}
        failure_rows.append({
            **common, "normalized_failure_signature": canonical["normalized_failure_signature"],
            "canonical_payload": canonical,
            "canonical_payload_sha256": hashlib.sha256(_canonical(canonical)).hexdigest(),
            "stable_signature_sha256": hashlib.sha256(_canonical(signature_projection)).hexdigest(),
        })
    junit_path = capture_root / "junit.xml"
    totals = _authoritative_broad_totals(
        capture_root / "collection.log", capture_root / "broad.log", junit_path
    )
    expected_nodeids = [row["nodeid"] for row in baseline["failure_rows"]]
    if _broad_failed_nodeids(junit_path, expected_nodeids=expected_nodeids) != {row["nodeid"] for row in failure_rows}:
        raise GateError("fresh isolated outcomes disagree with broad JUnit failures")
    payload = _seal({
        "schema": "workflow_broad_outcome.v1",
        "captured_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "baseline": _baseline_binding(baseline_path, baseline, repo_root),
        "subject": _subject_evidence_binding(subject_path, subject, repo_root),
        "environment": {"python": sys.version, "pytest": _pytest_version(), "platform": platform.platform()},
        "normalization": {"schema": "workflow_broad_failure_normalization.v1", "helper_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()},
        "collection": {"status": collection_status, "log": _artifact(capture_root / "collection.log", repo_root), "collected": _collection_count(capture_root / "collection.log")},
        "broad": {"status": broad_status_payload, "log": _artifact(capture_root / "broad.log", repo_root), "junit": _artifact(junit_path, repo_root), "totals": totals},
        "failure_rows": failure_rows,
        "passing_rows": passing_rows,
    })
    _write_new_json(output, payload)
    validate_outcome(payload, repo_root=repo_root)
    return payload


def validate_outcome(payload: Mapping[str, Any], *, repo_root: Path) -> None:
    validate_record(payload, expected_schema="workflow_broad_outcome.v1")
    expected_keys = {"schema", "captured_at", "baseline", "subject", "environment", "normalization", "collection", "broad", "failure_rows", "passing_rows", "record_sha256"}
    if set(payload) != expected_keys:
        raise GateError("outcome keys are not closed")
    _validate_utc_timestamp(payload["captured_at"], "outcome capture timestamp")
    if set(payload["environment"]) != {"python", "pytest", "platform"} or not all(
        isinstance(value, str) and value for value in payload["environment"].values()
    ):
        raise GateError("outcome environment domain is not closed")
    if set(payload["baseline"]) != {"path", "bytes", "sha256", "record_sha256"}:
        raise GateError("outcome baseline binding is not closed")
    _validate_artifact_binding({key: payload["baseline"][key] for key in FILE_BINDING_KEYS}, repo_root=repo_root)
    baseline = _load_json(repo_root / payload["baseline"]["path"])
    validate_baseline(baseline, repo_root=repo_root)
    if payload["baseline"]["record_sha256"] != baseline["record_sha256"]:
        raise GateError("outcome baseline record binding mismatch")
    if set(payload["subject"]) != {"path", "bytes", "sha256", "record_sha256", "head", "index_tree", "full_status", "inventory"}:
        raise GateError("outcome subject binding is not closed")
    _validate_artifact_binding({key: payload["subject"][key] for key in FILE_BINDING_KEYS}, repo_root=repo_root)
    subject = _load_json(repo_root / payload["subject"]["path"])
    validate_subject(subject, repo_root=repo_root)
    for key in ("record_sha256", "head", "index_tree", "full_status", "inventory"):
        if payload["subject"][key] != subject[key]:
            raise GateError(f"outcome subject {key} mismatch")
    normalization = payload["normalization"]
    if set(normalization) != {"schema", "helper_sha256"} or normalization["schema"] != "workflow_broad_failure_normalization.v1" or normalization["helper_sha256"] != baseline["normalization"]["helper_sha256"] or normalization["helper_sha256"] != hashlib.sha256(Path(__file__).read_bytes()).hexdigest():
        raise GateError("outcome normalization domain mismatch")
    collection = payload["collection"]
    if set(collection) != {"status", "log", "collected"}:
        raise GateError("outcome collection domain is not closed")
    _validate_exit_status_payload(collection["status"], expected_phase="collection", expected_exit=0)
    if collection["status"]["argv"] != ["pytest", "--collect-only", "-q"]:
        raise GateError("outcome collection argv mismatch")
    _validate_artifact_binding(collection["log"], repo_root=repo_root)
    if collection["collected"] != _collection_count(repo_root / collection["log"]["path"]):
        raise GateError("outcome collected count mismatch")
    broad = payload["broad"]
    if set(broad) != {"status", "log", "junit", "totals"}:
        raise GateError("outcome broad domain is not closed")
    broad_exit = broad["status"].get("exit_code")
    if broad_exit not in (0, 1):
        raise GateError("outcome broad exit mismatch")
    _validate_exit_status_payload(broad["status"], expected_phase="broad", expected_exit=broad_exit)
    for key in ("log", "junit"):
        _validate_artifact_binding(broad[key], repo_root=repo_root)
    if broad["status"]["argv"] != ["pytest", "-q", "-n", "16", "--dist=worksteal", f"--junitxml={broad['junit']['path']}"]:
        raise GateError("outcome broad argv mismatch")
    if set(broad["totals"]) != {"tests", "failures", "errors", "skipped", "passed", "xfailed", "xpassed"} or broad["totals"] != _authoritative_broad_totals(
        repo_root / collection["log"]["path"],
        repo_root / broad["log"]["path"],
        repo_root / broad["junit"]["path"],
    ):
        raise GateError("outcome broad totals mismatch")
    if broad["totals"]["tests"] != collection["collected"] or broad["totals"]["errors"] != 0 or broad["totals"]["failures"] != len(payload["failure_rows"]):
        raise GateError("outcome count domain mismatch")
    if broad_exit != (1 if payload["failure_rows"] else 0):
        raise GateError("outcome broad exit/failure mismatch")
    baseline_by_node = {row["nodeid"]: row for row in baseline["failure_rows"]}
    observed_nodes: list[str] = []
    failure_keys = {"nodeid", "normalized_failure_signature", "isolated_argv", "isolated_exit", "raw_log", "raw_junit", "raw_status", "baseline_row_sha256", "canonical_payload", "canonical_payload_sha256", "stable_signature_sha256"}
    passing_keys = {"nodeid", "isolated_argv", "isolated_exit", "raw_log", "raw_junit", "raw_status", "baseline_row_sha256"}
    for index, row in enumerate([*payload["failure_rows"], *payload["passing_rows"]]):
        is_failure = row in payload["failure_rows"]
        if set(row) != (failure_keys if is_failure else passing_keys):
            raise GateError("outcome isolated row keys are not closed")
        nodeid = row["nodeid"]
        if nodeid not in baseline_by_node or nodeid in observed_nodes:
            raise GateError("outcome isolated node inventory mismatch")
        observed_nodes.append(nodeid)
        baseline_row = baseline_by_node[nodeid]
        if row["baseline_row_sha256"] != hashlib.sha256(_canonical(baseline_row)).hexdigest():
            raise GateError("outcome baseline-row binding mismatch")
        for key in ("raw_log", "raw_junit", "raw_status"):
            _validate_artifact_binding(row[key], repo_root=repo_root)
        expected_index = next(i for i, candidate in enumerate(baseline["failure_rows"]) if candidate["nodeid"] == nodeid)
        expected_argv = [sys.executable, "-m", "pytest", "-q", nodeid, f"--junitxml={row['raw_junit']['path']}"]
        status = _load_json(repo_root / row["raw_status"]["path"])
        expected_exit = 1 if is_failure else 0
        if row["isolated_exit"] != expected_exit or row["isolated_argv"] != expected_argv or status != {"schema": "workflow_broad_isolated_status.v1", "row_index": expected_index, "nodeid": nodeid, "argv": expected_argv, "exit_code": expected_exit}:
            raise GateError("outcome isolated argv/status mismatch")
        if is_failure:
            canonical = canonical_failure_from_junit(repo_root / row["raw_junit"]["path"], nodeid=nodeid, repo_root=repo_root)
            if canonical != row["canonical_payload"] or _row_identity(row) != (
                nodeid,
                row["stable_signature_sha256"],
            ):
                raise GateError("outcome canonical failure mismatch")
            projection = {"nodeid": nodeid, "normalized_failure_signature": row["normalized_failure_signature"]}
            if row["stable_signature_sha256"] != hashlib.sha256(_canonical(projection)).hexdigest():
                raise GateError("outcome stable signature mismatch")
        else:
            _validate_passing_junit(repo_root / row["raw_junit"]["path"], nodeid=nodeid)
    if set(observed_nodes) != set(baseline_by_node):
        raise GateError("outcome does not account for every baseline isolated row")
    if _broad_failed_nodeids(repo_root / broad["junit"]["path"], expected_nodeids=list(baseline_by_node)) != {row["nodeid"] for row in payload["failure_rows"]}:
        raise GateError("outcome broad/isolated failure mismatch")


REMEDIATION_ROOT = "docs/plans/evidence/provider-prompt-dependencies/broad-remediations"


def _remediation_record_path(removed_rows: Sequence[Mapping[str, Any]]) -> str:
    digest = hashlib.sha256(_canonical(removed_rows)).hexdigest()
    return f"{REMEDIATION_ROOT}/{digest}.json"


def _validate_review_approval(value: Any, *, quality: bool) -> None:
    prefix = "APPROVED" if quality else "PASS"
    if not isinstance(value, str) or not re.fullmatch(
        rf"{prefix} [A-Za-z0-9][A-Za-z0-9._:/-]*", value
    ):
        raise GateError("remediation lacks ordered review approvals")


def _validate_reviewed_commit(
    *, repo_root: Path, commit: str, tree: str, reviews: Mapping[str, Any], label: str
) -> None:
    if set(reviews) != {"specification", "quality"}:
        raise GateError(f"remediation {label} reviews are not closed")
    _validate_review_approval(reviews["specification"], quality=False)
    _validate_review_approval(reviews["quality"], quality=True)
    message = _git(repo_root, "show", "-s", "--format=%B", commit).decode("utf-8", "strict")
    expected = [
        f"Review-Tree: {tree}",
        f"Spec-Review: {reviews['specification']}",
        f"Quality-Review: {reviews['quality']}",
    ]
    lines = message.splitlines()
    positions: list[int] = []
    for trailer in expected:
        found = [index for index, line in enumerate(lines) if line == trailer]
        if len(found) != 1:
            raise GateError(f"remediation {label} commit review trailers mismatch")
        positions.append(found[0])
    if positions != sorted(positions) or any(
        line.startswith(("Review-Tree:", "Spec-Review:", "Quality-Review:"))
        and line not in expected
        for line in lines
    ):
        raise GateError(f"remediation {label} commit review trailers are not exact and ordered")


def validate_remediation(
    payload: Mapping[str, Any], *, repo_root: Path, remediation_path: Path
) -> None:
    validate_record(payload, expected_schema="workflow_broad_failure_remediation.v1")
    expected_keys = {"schema", "captured_at", "baseline_record_sha256", "record_path", "removed_rows", "fixing_commit", "fixing_tree", "focused_proofs", "reviews", "record_sha256"}
    if set(payload) != expected_keys:
        raise GateError("remediation keys are not closed")
    _validate_utc_timestamp(payload["captured_at"], "remediation timestamp")
    if not isinstance(payload["baseline_record_sha256"], str) or not re.fullmatch(r"[0-9a-f]{64}", payload["baseline_record_sha256"]):
        raise GateError("remediation baseline digest is invalid")
    if not re.fullmatch(r"[0-9a-f]{40,64}", payload["fixing_commit"] or "") or not re.fullmatch(r"[0-9a-f]{40,64}", payload["fixing_tree"] or ""):
        raise GateError("remediation fixing commit/tree is invalid")
    if not isinstance(payload["removed_rows"], list) or not payload["removed_rows"]:
        raise GateError("remediation removed rows must be non-empty")
    removed_keys = {"nodeid", "canonical_payload_sha256", "stable_signature_sha256", "baseline_row_sha256"}
    for row in payload["removed_rows"]:
        if set(row) != removed_keys:
            raise GateError("remediation removed-row domain is not closed")
        if not isinstance(row["nodeid"], str) or not row["nodeid"].strip() or row["nodeid"] != row["nodeid"].strip():
            raise GateError("remediation removed-row node ID is invalid")
        if any(
            not isinstance(row[key], str) or not re.fullmatch(r"[0-9a-f]{64}", row[key])
            for key in removed_keys - {"nodeid"}
        ):
            raise GateError("remediation removed-row digest is invalid")
    if payload["removed_rows"] != sorted(payload["removed_rows"], key=lambda row: row["nodeid"]) or len(
        {row["nodeid"] for row in payload["removed_rows"]}
    ) != len(payload["removed_rows"]):
        raise GateError("remediation removed rows must be sorted and unique")
    expected_record_path = _remediation_record_path(payload["removed_rows"])
    if payload["record_path"] != expected_record_path:
        raise GateError("remediation record path is not canonical for removed rows")
    repo_root = repo_root.resolve()
    actual_path = remediation_path if remediation_path.is_absolute() else repo_root / remediation_path
    try:
        actual_rel = actual_path.resolve().relative_to(repo_root).as_posix()
    except ValueError as exc:
        raise GateError("remediation record is outside repository") from exc
    if actual_path.is_symlink() or not actual_path.is_file() or actual_rel != expected_record_path:
        raise GateError("remediation input path does not equal canonical record path")
    record_bytes = actual_path.read_bytes()
    if record_bytes != _canonical(payload):
        raise GateError("remediation record bytes are not canonical or do not equal input")
    commit = payload["fixing_commit"]
    try:
        resolved_commit = _git(repo_root, "rev-parse", "--verify", f"{commit}^{{commit}}").decode("ascii").strip()
        resolved_tree = _git(repo_root, "rev-parse", "--verify", f"{commit}^{{tree}}").decode("ascii").strip()
    except GateError as exc:
        raise GateError("remediation fixing commit does not exist") from exc
    if resolved_commit != commit or resolved_tree != payload["fixing_tree"]:
        raise GateError("remediation fixing commit/tree binding mismatch")
    if not isinstance(payload["focused_proofs"], list) or not payload["focused_proofs"]:
        raise GateError("remediation focused proofs must be non-empty")
    proof_paths: list[str] = []
    for binding in payload["focused_proofs"]:
        _validate_file_binding_shape(
            binding, include_record_digest=False, label="remediation focused proof"
        )
        proof_path = _repo_path(binding["path"])
        proof_paths.append(proof_path)
        try:
            proof_bytes = _git(repo_root, "show", f"{commit}:{proof_path}")
        except GateError as exc:
            raise GateError(
                f"remediation focused proof is missing from fixing commit: {proof_path}"
            ) from exc
        if (
            binding["bytes"] != len(proof_bytes)
            or binding["sha256"] != hashlib.sha256(proof_bytes).hexdigest()
        ):
            raise GateError(
                f"remediation focused proof digest does not match fixing commit: {proof_path}"
            )
    if proof_paths != sorted(proof_paths) or len(proof_paths) != len(set(proof_paths)):
        raise GateError("remediation focused proof paths must be sorted and unique")
    reviews = payload["reviews"]
    if set(reviews) != {"fixing", "record"}:
        raise GateError("remediation review domains are not independent and closed")
    _validate_reviewed_commit(
        repo_root=repo_root,
        commit=commit,
        tree=payload["fixing_tree"],
        reviews=reviews["fixing"],
        label="fixing",
    )
    additions = _git(
        repo_root, "log", "--format=%H", "--diff-filter=A", "--", expected_record_path
    ).decode("ascii").splitlines()
    if len(additions) != 1:
        raise GateError("remediation record must have one immutable addition commit")
    record_commit = additions[0]
    committed_bytes = _git(repo_root, "show", f"{record_commit}:{expected_record_path}")
    if committed_bytes != record_bytes:
        raise GateError("remediation addition commit does not contain exact record bytes/path")
    record_tree = _git(repo_root, "rev-parse", f"{record_commit}^{{tree}}").decode("ascii").strip()
    try:
        _git(repo_root, "merge-base", "--is-ancestor", commit, record_commit)
        _git(repo_root, "merge-base", "--is-ancestor", record_commit, "HEAD")
    except GateError as exc:
        raise GateError("remediation fixing/record commits are outside current ancestry scope") from exc
    if commit == record_commit:
        raise GateError("remediation fixing and record commits must be independent")
    _validate_reviewed_commit(
        repo_root=repo_root,
        commit=record_commit,
        tree=record_tree,
        reviews=reviews["record"],
        label="record",
    )
    if set(reviews["fixing"].values()) & set(reviews["record"].values()):
        raise GateError("remediation fixing and record reviews must use independent approvals")


def _cli() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    capture = sub.add_parser("capture-subject")
    capture.add_argument("--output", required=True, type=Path); capture.add_argument("--protected", action="append", default=[])
    capture.add_argument("--allowed-untracked", action="append", default=[]); capture.add_argument("--task-subject", action="append", default=[])
    capture.add_argument("--allowed-post-launch-update", action="append", default=[]); capture.add_argument("--generated-evidence", action="append", default=[])
    capture.add_argument("--ignored-evidence-root", action="append", default=[]); capture.add_argument("--generated-evidence-layout", choices=("review-v1", "broad-v1"))
    capture.add_argument("--frozen-overlay", type=Path)
    verify = sub.add_parser("verify-subject"); verify.add_argument("--manifest", required=True, type=Path); verify.add_argument("--phase", required=True, choices=("launch", "review")); verify.add_argument("--generated-evidence"); verify.add_argument("--review-subject", type=Path)
    overlay = sub.add_parser("capture-frozen-overlay"); overlay.add_argument("--output", required=True, type=Path); overlay.add_argument("--eligible-path", action="append", default=[])
    validate_overlay = sub.add_parser("validate-frozen-overlay"); validate_overlay.add_argument("--overlay", required=True, type=Path)
    review = sub.add_parser("build-review-subject"); review.add_argument("--subject-manifest", required=True, type=Path); review.add_argument("--generated-evidence", required=True, type=Path); review.add_argument("--review-patch-sha256", required=True); review.add_argument("--review-tree", required=True); review.add_argument("--output", required=True, type=Path)
    status = sub.add_parser("write-command-status"); status.add_argument("--output", required=True, type=Path); status.add_argument("--phase", required=True, choices=("collection", "broad")); status.add_argument("--exit-code", required=True, type=int); status.add_argument("--arg", action="append", required=True)
    baseline = sub.add_parser("build-baseline"); baseline.add_argument("--authority", required=True, type=Path); baseline.add_argument("--correction", required=True, type=Path); baseline.add_argument("--normalizer", required=True, type=Path); baseline.add_argument("--subject-manifest", required=True, type=Path); baseline.add_argument("--capture-root", required=True, type=Path); baseline.add_argument("--output", required=True, type=Path)
    valid = sub.add_parser("validate-baseline"); valid.add_argument("--baseline", required=True, type=Path)
    build_out = sub.add_parser("build-outcome"); build_out.add_argument("--baseline", required=True, type=Path); build_out.add_argument("--subject-manifest", required=True, type=Path); build_out.add_argument("--capture-root", required=True, type=Path); build_out.add_argument("--output", required=True, type=Path)
    outcome = sub.add_parser("validate-outcome"); outcome.add_argument("--outcome", required=True, type=Path)
    remediation = sub.add_parser("validate-remediation"); remediation.add_argument("--remediation", required=True, type=Path)
    compare = sub.add_parser("compare"); compare.add_argument("--baseline", required=True, type=Path); compare.add_argument("--outcome", required=True, type=Path); compare.add_argument("--remediation-dir", required=True, type=Path)
    return parser


def _load_remediation_directory(path: Path) -> list[tuple[dict[str, Any], Path]]:
    if not path.exists():
        return []
    if path.is_symlink() or not path.is_dir():
        raise GateError("remediation directory is not an ordinary directory")
    result: list[tuple[dict[str, Any], Path]] = []
    for entry in sorted(path.iterdir(), key=lambda candidate: candidate.name):
        if entry.is_symlink() or not entry.is_file() or entry.suffix != ".json":
            raise GateError(f"unexpected non-record remediation directory entry: {entry}")
        payload = _load_json(entry)
        if payload.get("schema") != "workflow_broad_failure_remediation.v1":
            raise GateError(f"unexpected non-remediation record: {entry}")
        result.append((payload, entry))
    return result


def main(argv: Sequence[str] | None = None) -> int:
    args = _cli().parse_args(argv)
    root = Path.cwd().resolve()
    try:
        if args.command == "capture-subject":
            capture_subject(repo_root=root, output=args.output, protected_paths=args.protected, allowed_untracked_paths=args.allowed_untracked, task_subject_paths=args.task_subject, allowed_post_launch_updates=args.allowed_post_launch_update, generated_evidence_paths=args.generated_evidence, ignored_evidence_roots=args.ignored_evidence_root, generated_evidence_layout=args.generated_evidence_layout, frozen_overlay_path=args.frozen_overlay)
        elif args.command == "verify-subject":
            subject = _load_json(args.manifest); review = _load_json(args.review_subject) if args.review_subject else None
            verify_subject(subject, repo_root=root, phase=args.phase, generated_evidence=args.generated_evidence, review_subject=review)
        elif args.command == "capture-frozen-overlay":
            capture_frozen_overlay(repo_root=root, output=args.output, eligible_paths=args.eligible_path)
        elif args.command == "validate-frozen-overlay":
            validate_frozen_overlay(
                _load_json(args.overlay), repo_root=root, record_path=args.overlay
            )
        elif args.command == "build-review-subject":
            subject = _load_json(args.subject_manifest)
            build_review_subject(repo_root=root, subject=subject, subject_path=args.subject_manifest, generated_evidence=args.generated_evidence, review_patch_sha256=args.review_patch_sha256, review_tree=args.review_tree, output=args.output)
        elif args.command == "write-command-status":
            write_exit_status(args.output, phase=args.phase, argv=args.arg, exit_code=args.exit_code)
        elif args.command == "build-baseline":
            build_baseline(repo_root=root, authority_path=args.authority, correction_path=args.correction, normalizer_path=args.normalizer, subject_path=args.subject_manifest, capture_root=args.capture_root, output=args.output)
        elif args.command == "validate-baseline":
            validate_baseline(_load_json(args.baseline), repo_root=root)
        elif args.command == "build-outcome":
            build_outcome(repo_root=root, baseline_path=args.baseline, subject_path=args.subject_manifest, capture_root=args.capture_root, output=args.output)
        elif args.command == "validate-outcome":
            validate_outcome(_load_json(args.outcome), repo_root=root)
        elif args.command == "validate-remediation":
            validate_remediation(
                _load_json(args.remediation), repo_root=root, remediation_path=args.remediation
            )
        elif args.command == "compare":
            result = compare_outcome(
                _load_json(args.baseline),
                _load_json(args.outcome),
                remediations=_load_remediation_directory(args.remediation_dir),
                repo_root=root,
            )
            print(json.dumps(result, sort_keys=True))
    except GateError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
