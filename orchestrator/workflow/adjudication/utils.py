"""Private shared helpers for adjudicated-provider runtime modules."""

from __future__ import annotations

import json
import math
import os
import shutil
import tempfile
from dataclasses import asdict
from hashlib import sha256
from pathlib import Path
from typing import Any, Mapping

from .models import ManifestEntry

def _resolve_json_pointer(document: Any, pointer: str) -> tuple[bool, Any]:
    if pointer == "":
        return True, document
    if not pointer.startswith("/"):
        return False, None
    current = document
    for token in pointer[1:].split("/"):
        token = token.replace("~1", "/").replace("~0", "~")
        if isinstance(current, dict) and token in current:
            current = current[token]
            continue
        if isinstance(current, list):
            try:
                index = int(token)
            except ValueError:
                return False, None
            if index < 0 or index >= len(current):
                return False, None
            current = current[index]
            continue
        return False, None
    return True, current

def _matching_exclusion(relpath: str, excluded_by_path: Mapping[str, ManifestEntry]) -> ManifestEntry | None:
    path = Path(relpath)
    candidates = [path.as_posix()]
    parts = path.parts
    for index in range(1, len(parts)):
        candidates.append(Path(*parts[:index]).as_posix())
    for candidate in candidates:
        entry = excluded_by_path.get(candidate)
        if entry is not None:
            return entry
    return None


def _safe_token(value: str, label: str) -> str:
    if not isinstance(value, str) or not value or value.startswith(".") or ".." in value or "/" in value or "\\" in value:
        raise ValueError(f"{label} must be a path-safe token")
    allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-")
    if any(char not in allowed for char in value):
        raise ValueError(f"{label} must be a path-safe token")
    return value


def _safe_visit_count(value: int) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ValueError("visit_count must be a positive integer")
    return value


def _safe_relpath(path: Path | str) -> str:
    path = Path(path)
    if path.is_absolute() or not path.parts or ".." in path.parts:
        raise ValueError(f"path '{path}' escapes workspace")
    return path.as_posix()


def _workspace_file(workspace: Path, relpath: str, *, must_exist: bool = True) -> Path:
    rel = _safe_relpath(Path(relpath))
    workspace = workspace.resolve()
    path = (workspace / rel).resolve()
    if not _is_within(path, workspace):
        raise ValueError(f"path '{relpath}' escapes workspace")
    if must_exist and not path.exists():
        raise FileNotFoundError(path)
    return path


def _relative_posix(path: Path, root: Path) -> str:
    try:
        rel = path.relative_to(root)
    except ValueError:
        return ""
    if rel == Path("."):
        return ""
    return rel.as_posix()


def _join_rel(root: str, leaf: str) -> str:
    return leaf if not root else f"{root}/{leaf}"


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _is_finite_score(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))


def _hash_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _hash_bytes(payload: bytes) -> str:
    return f"sha256:{sha256(payload).hexdigest()}"


def _stable_hash(payload: Any) -> str:
    return _hash_bytes(_canonical_json(_jsonable(payload)).encode("utf-8"))


def _canonical_json(payload: Any) -> str:
    return json.dumps(_jsonable(payload), sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def _jsonable(payload: Any) -> Any:
    if isinstance(payload, Mapping):
        return {str(key): _jsonable(value) for key, value in payload.items()}
    if isinstance(payload, (list, tuple)):
        return [_jsonable(value) for value in payload]
    if isinstance(payload, Path):
        return payload.as_posix()
    if hasattr(payload, "__dict__"):
        return _jsonable(asdict(payload))
    return payload


def _replace_file(source: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(delete=False, dir=str(dest.parent)) as handle:
        temp_path = Path(handle.name)
    try:
        shutil.copy2(source, temp_path)
        os.replace(temp_path, dest)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def _atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, dir=str(path.parent)) as handle:
        handle.write(content)
        temp_path = Path(handle.name)
    try:
        os.replace(temp_path, path)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def _utc_now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
