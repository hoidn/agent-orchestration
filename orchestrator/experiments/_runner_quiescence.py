"""Durable process-group quiescence evidence for lean-pilot attempts."""

from __future__ import annotations

import json
import os
import secrets
import stat
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath

from .contracts import (
    PilotContractError,
    canonical_json_bytes,
    canonical_sha256,
    validate_record,
)
from ._runner_types import QuiescenceError


_LEDGER_NAME = "process-groups.json"
_LEDGER_SCHEMA = "lean-pilot-process-groups.v1"
_LEDGER_FIELDS = {
    "schema_version",
    "pilot_lock_digest",
    "block_id",
    "in_flight_spawn_ids",
    "process_group_ids",
}


def _safe_component(value: object) -> str | None:
    if (
        not isinstance(value, str)
        or not value
        or value in {".", ".."}
        or "\x00" in value
        or "/" in value
        or "\\" in value
        or PurePosixPath(value).is_absolute()
    ):
        return None
    return value


def _ledger_value(
    *,
    pilot_lock_digest: str,
    block_id: str,
    in_flight_spawn_ids: Sequence[str],
    process_group_ids: Sequence[int],
) -> dict[str, object]:
    return {
        "schema_version": _LEDGER_SCHEMA,
        "pilot_lock_digest": pilot_lock_digest,
        "block_id": block_id,
        "in_flight_spawn_ids": list(in_flight_spawn_ids),
        "process_group_ids": list(process_group_ids),
    }


def _canonical_parent(path: Path) -> bool:
    try:
        identity = path.lstat()
        return (
            stat.S_ISDIR(identity.st_mode)
            and not path.is_symlink()
            and path.resolve(strict=True) == path
        )
    except OSError:
        return False


def _load_ledger_state(
    path: Path,
    *,
    pilot_lock_digest: str,
    block_id: str,
) -> tuple[tuple[int, ...], tuple[str, ...]] | None:
    if not _canonical_parent(path.parent):
        return None
    try:
        identity = path.lstat()
        if not stat.S_ISREG(identity.st_mode) or path.is_symlink():
            return None
        descriptor = os.open(
            path,
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
        )
        with os.fdopen(descriptor, "rb", closefd=True) as stream:
            data = stream.read()
        value = json.loads(data.decode("utf-8"))
        if (
            not isinstance(value, dict)
            or set(value) != _LEDGER_FIELDS
            or value.get("schema_version") != _LEDGER_SCHEMA
            or value.get("pilot_lock_digest") != pilot_lock_digest
            or value.get("block_id") != block_id
            or canonical_json_bytes(value) != data
        ):
            return None
        raw_ids = value.get("process_group_ids")
        raw_spawn_ids = value.get("in_flight_spawn_ids")
        if (
            not isinstance(raw_ids, list)
            or any(
                isinstance(item, bool) or not isinstance(item, int) or item <= 0
                for item in raw_ids
            )
            or raw_ids != sorted(raw_ids)
            or len(raw_ids) != len(set(raw_ids))
            or not isinstance(raw_spawn_ids, list)
            or any(_safe_component(item) is None for item in raw_spawn_ids)
            or raw_spawn_ids != sorted(raw_spawn_ids)
            or len(raw_spawn_ids) != len(set(raw_spawn_ids))
        ):
            return None
        return tuple(raw_ids), tuple(raw_spawn_ids)
    except (
        OSError,
        UnicodeDecodeError,
        json.JSONDecodeError,
        PilotContractError,
        TypeError,
        ValueError,
    ):
        return None


def _write_atomic(path: Path, data: bytes, *, create: bool) -> None:
    if not _canonical_parent(path.parent):
        raise QuiescenceError("process-group ledger parent is not canonical")
    temporary: Path | None = None
    descriptor: int | None = None
    try:
        for _attempt in range(16):
            candidate = path.parent / (
                f".{path.name}.tmp-{secrets.token_hex(8)}"
            )
            try:
                descriptor = os.open(
                    candidate,
                    os.O_WRONLY
                    | os.O_CREAT
                    | os.O_EXCL
                    | getattr(os, "O_NOFOLLOW", 0),
                    0o600,
                )
            except FileExistsError:
                continue
            temporary = candidate
            break
        if descriptor is None or temporary is None:
            raise QuiescenceError(
                "cannot allocate process-group ledger temporary"
            )
        with os.fdopen(descriptor, "wb", closefd=True) as stream:
            descriptor = None
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        if create:
            try:
                os.link(temporary, path, follow_symlinks=False)
            except FileExistsError as exc:
                raise QuiescenceError(
                    "process-group ledger already exists"
                ) from exc
            temporary.unlink()
            temporary = None
        else:
            identity = path.lstat()
            if not stat.S_ISREG(identity.st_mode) or path.is_symlink():
                raise QuiescenceError("process-group ledger is not regular")
            os.replace(temporary, path)
            temporary = None
        directory = os.open(
            path.parent,
            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0),
        )
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    except QuiescenceError:
        raise
    except OSError as exc:
        raise QuiescenceError("cannot persist process-group ledger") from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if temporary is not None:
            try:
                temporary.unlink()
            except OSError:
                pass


def initialize_process_group_ledger(
    *,
    path: Path,
    pilot_lock_digest: str,
    block_id: str,
) -> None:
    """Create the canonical empty ledger for a newly persisted STARTED attempt."""

    if _safe_component(block_id) is None:
        raise QuiescenceError("process-group ledger block_id is invalid")
    _write_atomic(
        path,
        canonical_json_bytes(
            _ledger_value(
                pilot_lock_digest=pilot_lock_digest,
                block_id=block_id,
                in_flight_spawn_ids=(),
                process_group_ids=(),
            )
        ),
        create=True,
    )


def replace_process_group_ledger(
    *,
    path: Path,
    pilot_lock_digest: str,
    block_id: str,
    expected_process_group_ids: Sequence[int],
    expected_in_flight_spawn_ids: Sequence[str],
    process_group_ids: Sequence[int],
    in_flight_spawn_ids: Sequence[str],
) -> None:
    """Replace a validated ledger without accepting stale or tampered state."""

    expected = tuple(sorted(expected_process_group_ids))
    desired = tuple(sorted(process_group_ids))
    expected_spawns = tuple(sorted(expected_in_flight_spawn_ids))
    desired_spawns = tuple(sorted(in_flight_spawn_ids))
    if _load_ledger_state(
        path,
        pilot_lock_digest=pilot_lock_digest,
        block_id=block_id,
    ) != (expected, expected_spawns):
        raise QuiescenceError("process-group ledger state is invalid")
    _write_atomic(
        path,
        canonical_json_bytes(
            _ledger_value(
                pilot_lock_digest=pilot_lock_digest,
                block_id=block_id,
                in_flight_spawn_ids=desired_spawns,
                process_group_ids=desired,
            )
        ),
        create=False,
    )


def surviving_started_process_groups_are_quiescent(
    *,
    lock: Mapping[str, object],
    block_id: str,
    evidence_root: Path,
) -> bool:
    """Return whether a surviving STARTED attempt's recorded groups are absent."""

    safe_block_id = _safe_component(block_id)
    if safe_block_id is None:
        return False
    try:
        lock_value = dict(lock)
        validate_record(lock_value)
        root = Path(evidence_root)
        if (
            not root.is_absolute()
            or not _canonical_parent(root)
            or lock_value.get("evidence_root") != root.as_posix()
            or safe_block_id
            not in {
                lock_value.get("smoke_id"),
                *(
                    lock_value.get("live_attempt_ids")
                    if isinstance(lock_value.get("live_attempt_ids"), list)
                    else []
                ),
            }
        ):
            return False
        digest = canonical_sha256(lock_value)
    except (OSError, PilotContractError, TypeError, ValueError):
        return False
    ledger_state = _load_ledger_state(
        root / safe_block_id / _LEDGER_NAME,
        pilot_lock_digest=digest,
        block_id=safe_block_id,
    )
    if ledger_state is None:
        return False
    process_group_ids, in_flight_spawn_ids = ledger_state
    if in_flight_spawn_ids:
        return False
    for process_group_id in process_group_ids:
        try:
            os.killpg(process_group_id, 0)
        except ProcessLookupError:
            continue
        except (PermissionError, OSError):
            return False
        return False
    return True
