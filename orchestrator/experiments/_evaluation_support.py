"""Shared path, digest, diff, and package helpers for evaluation."""

from __future__ import annotations

import difflib
import hashlib
import json
import os
import re
import shutil
import stat
from collections.abc import Collection, Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import Any

from .contracts import canonical_json_bytes
from .workspace import TreeEntry, WorkspaceError, freeze_product


class EvaluationError(ValueError):
    """A blinded-evaluation contract failed with a stable reason code."""

    def __init__(self, code: str, detail: str = "") -> None:
        self.code = code
        message = code if not detail else f"{code}: {detail}"
        super().__init__(message)


def _fail(code: str, detail: str = "") -> None:
    raise EvaluationError(code, detail)


def _sha256_bytes(value: bytes) -> str:
    return f"sha256:{hashlib.sha256(value).hexdigest()}"


def _strict_json(path: Path, *, code: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EvaluationError(code, str(exc)) from exc
    if not isinstance(value, dict):
        _fail(code, "expected a JSON object")
    return value


def _relative_path(value: object) -> PurePosixPath:
    if not isinstance(value, str) or not value:
        _fail("evaluation_path_invalid", repr(value))
    if "\\" in value or "\x00" in value:
        _fail("evaluation_path_invalid", value)
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or not path.parts
        or any(part in {"", ".", ".."} for part in path.parts)
        or path.as_posix() != value
    ):
        _fail("evaluation_path_invalid", value)
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise EvaluationError("evaluation_path_invalid", value) from exc
    return path


def _safe_component(value: object) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value in {".", ".."}
        or "\x00" in value
        or "/" in value
        or "\\" in value
        or PurePosixPath(value).is_absolute()
    ):
        _fail("evaluation_id_invalid", repr(value))
    return value


def _canonical_root(path: Path, *, must_exist: bool) -> Path:
    try:
        resolved = path.resolve(strict=must_exist)
    except OSError as exc:
        raise EvaluationError("evaluation_root_invalid", str(path)) from exc
    if must_exist:
        try:
            identity = resolved.lstat()
        except OSError as exc:
            raise EvaluationError(
                "evaluation_root_invalid",
                str(path),
            ) from exc
        if not stat.S_ISDIR(identity.st_mode) or path.is_symlink():
            _fail("evaluation_root_invalid", str(path))
    return resolved


def _overlaps(left: Path, right: Path) -> bool:
    return left == right or left.is_relative_to(right) or right.is_relative_to(left)


def _validate_roots(
    *,
    base_root: Path,
    product_roots: Mapping[str, Path],
    output_root: Path,
    controller_root: Path,
) -> tuple[Path, dict[str, Path], Path, Path]:
    base = _canonical_root(base_root, must_exist=True)
    products = {
        key: _canonical_root(value, must_exist=True)
        for key, value in product_roots.items()
    }
    output = _canonical_root(output_root, must_exist=False)
    controller = _canonical_root(controller_root, must_exist=False)
    named = [
        ("base", base),
        ("output", output),
        ("controller", controller),
        *[(f"product:{key}", value) for key, value in products.items()],
    ]
    for index, (left_name, left) in enumerate(named):
        for right_name, right in named[index + 1 :]:
            if _overlaps(left, right):
                _fail(
                    "evaluation_root_overlap",
                    f"{left_name} overlaps {right_name}",
                )
    return base, products, output, controller


def _source_file(root: Path, relative: PurePosixPath) -> tuple[Path, bytes, int]:
    path = root.joinpath(*relative.parts)
    try:
        identity = path.lstat()
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise EvaluationError(
            "evaluation_source_missing",
            relative.as_posix(),
        ) from exc
    if (
        not stat.S_ISREG(identity.st_mode)
        or path.is_symlink()
        or not resolved.is_relative_to(root)
        or resolved != path
    ):
        _fail("evaluation_source_invalid", relative.as_posix())
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise EvaluationError(
            "evaluation_source_invalid",
            relative.as_posix(),
        ) from exc
    return path, data, stat.S_IMODE(identity.st_mode)


def _write_payload(path: Path, data: bytes, mode: int = 0o644) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    path.chmod(mode)


def _entry_row(entry: TreeEntry | None) -> object:
    if entry is None:
        return None
    return {
        "kind": entry.kind,
        "link_target": entry.link_target,
        "mode": entry.mode,
        "path": entry.path,
        "sha256": entry.sha256,
        "size": entry.size,
    }


def _diff_bytes(
    *,
    base_root: Path,
    product_root: Path,
    excluded_roots: Sequence[PurePosixPath],
) -> bytes:
    try:
        base_manifest = freeze_product(base_root, excluded_roots)
        product_manifest = freeze_product(product_root, excluded_roots)
    except WorkspaceError as exc:
        raise EvaluationError("evaluation_product_manifest_invalid", str(exc)) from exc
    before_entries = {entry.path: entry for entry in base_manifest.entries}
    after_entries = {entry.path: entry for entry in product_manifest.entries}
    pieces: list[str] = []
    paths = sorted(
        set(before_entries) | set(after_entries),
        key=lambda value: value.encode("utf-8"),
    )
    for path_text in paths:
        before_entry = before_entries.get(path_text)
        after_entry = after_entries.get(path_text)
        if before_entry == after_entry:
            continue
        pieces.append(f"diff --lean-tree a/{path_text} b/{path_text}\n")
        pieces.append(
            f"--- metadata {canonical_json_bytes(_entry_row(before_entry)).decode()}\n"
        )
        pieces.append(
            f"+++ metadata {canonical_json_bytes(_entry_row(after_entry)).decode()}\n"
        )
        if (
            before_entry is not None
            and before_entry.kind != "file"
            or after_entry is not None
            and after_entry.kind != "file"
        ):
            continue
        relative = _relative_path(path_text)
        base_bytes = b""
        final_bytes = b""
        if before_entry is not None:
            _base_path, base_bytes, _base_mode = _source_file(base_root, relative)
        if after_entry is not None:
            _final_path, final_bytes, _mode = _source_file(product_root, relative)
        try:
            before = base_bytes.decode("utf-8").splitlines(keepends=True)
            after = final_bytes.decode("utf-8").splitlines(keepends=True)
        except UnicodeDecodeError:
            if base_bytes != final_bytes:
                pieces.append(
                    "Binary files "
                    f"a/{relative.as_posix()} and b/{relative.as_posix()} differ\n"
                )
            continue
        pieces.extend(
            difflib.unified_diff(
                before,
                after,
                fromfile=f"a/{path_text}",
                tofile=f"b/{path_text}",
                lineterm="\n",
            )
        )
    text = "".join(pieces)
    if text and not text.endswith("\n"):
        text += "\n"
    return text.encode("utf-8")


def _manifest_rows(package_root: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for path in sorted(
        (
            item
            for item in package_root.rglob("*")
            if item.is_file() and item.name != "manifest.json"
        ),
        key=lambda item: item.relative_to(package_root).as_posix().encode("utf-8"),
    ):
        relative = path.relative_to(package_root).as_posix()
        identity = path.stat()
        data = path.read_bytes()
        rows.append(
            {
                "path": relative,
                "mode": stat.S_IMODE(identity.st_mode),
                "size": len(data),
                "sha256": _sha256_bytes(data),
            }
        )
    return rows


def _opaque_labels(seed: str, package_id: str, count: int) -> tuple[str, ...]:
    labels = []
    for index in range(count):
        digest = hashlib.sha256(
            f"{seed}\0{package_id}\0label\0{index}".encode("utf-8")
        ).hexdigest()
        labels.append(f"candidate-{digest[:12]}")
    return tuple(labels)


def _role_order(seed: str, package_id: str, roles: Collection[str]) -> tuple[str, ...]:
    return tuple(
        sorted(
            roles,
            key=lambda role: hashlib.sha256(
                f"{seed}\0{package_id}\0role\0{role}".encode("utf-8")
            ).digest(),
        )
    )


def _build_package(
    *,
    package_id: str,
    candidate_labels: Sequence[str],
    roots_by_label: Mapping[str, Path],
    base_root: Path,
    task_path: PurePosixPath,
    selected_by_label: Mapping[str, Sequence[PurePosixPath]],
    checks_by_label: Mapping[str, Sequence[PurePosixPath]],
    product_exclusions: Sequence[PurePosixPath],
    controller_root: Path,
    output_root: Path,
) -> Path:
    package_root = output_root / package_id
    if os.path.lexists(package_root):
        _fail("evaluation_output_exists", str(package_root))
    package_root.mkdir(parents=True)

    _task_source, task_bytes, task_mode = _source_file(base_root, task_path)
    _write_payload(package_root / "task.md", task_bytes, task_mode)

    for label in candidate_labels:
        selected = selected_by_label[label]
        root = roots_by_label[label]
        candidate_root = package_root / "candidates" / label
        _write_payload(
            candidate_root / "diff.patch",
            _diff_bytes(
                base_root=base_root,
                product_root=root,
                excluded_roots=product_exclusions,
            ),
        )
        for relative in selected:
            _source, data, mode = _source_file(root, relative)
            _write_payload(
                candidate_root / "files" / Path(*relative.parts),
                data,
                mode,
            )
        for index, relative in enumerate(checks_by_label[label], start=1):
            _source, data, mode = _source_file(controller_root, relative)
            check_name = f"check-{index:03d}-{relative.name}"
            _write_payload(candidate_root / "checks" / check_name, data, mode)

    manifest = {
        "package_id": package_id,
        "task_path": "task.md",
        "candidate_labels": list(candidate_labels),
        "files": _manifest_rows(package_root),
    }
    _write_payload(
        package_root / "manifest.json",
        canonical_json_bytes(manifest),
    )
    return package_root


def _reject_identity_leak(package_root: Path, identities: Collection[str]) -> None:
    patterns = [
        re.compile(rb"(?<![A-Za-z0-9_])" + re.escape(value.encode("utf-8")) + rb"(?![A-Za-z0-9_])", re.I)
        for value in identities
    ]
    for path in package_root.rglob("*"):
        if not path.is_file():
            continue
        data = path.read_bytes()
        if any(pattern.search(data) for pattern in patterns):
            shutil.rmtree(package_root)
            _fail("evaluation_blinding_violation", path.name)


def _lock_seed(lock: Mapping[str, object]) -> str:
    value = lock.get("randomization_seed")
    if not isinstance(value, str) or not value:
        _fail("evaluation_lock_invalid", "randomization_seed")
    return value


def _execution_roles(block: Mapping[str, object]) -> tuple[str, ...]:
    executions = block.get("treatment_executions")
    if not isinstance(executions, list):
        _fail("evaluation_block_invalid", "treatment_executions")
    roles: list[str] = []
    for execution in executions:
        if not isinstance(execution, Mapping):
            _fail("evaluation_block_invalid", "treatment execution")
        role = execution.get("treatment_id")
        if not isinstance(role, str) or not role or role in roles:
            _fail("evaluation_block_invalid", "treatment_id")
        roles.append(role)
    if len(roles) < 2:
        _fail("evaluation_block_invalid", "at least two treatments required")
    return tuple(roles)
