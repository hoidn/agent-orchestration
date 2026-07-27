"""Private record, path, attempt-prefix, and readiness validation."""

from __future__ import annotations

import stat
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import Any

from ._reporting_types import ReportingError
from .contracts import (
    PilotContractError,
    canonical_sha256,
    load_record,
    validate_record,
)


def _fail(code: str) -> None:
    raise ReportingError(code)


def _validate_record(value: object, kind: str) -> dict[str, Any]:
    if not isinstance(value, dict) or value.get("record_kind") != kind:
        _fail(f"{kind}_invalid")
    try:
        validate_record(value)
    except PilotContractError as exc:
        raise ReportingError(f"{kind}_invalid: {exc}") from exc
    return value


def _relative_path(value: str) -> bool:
    if not isinstance(value, str) or not value or "\\" in value:
        return False
    path = PurePosixPath(value)
    return (
        not path.is_absolute()
        and bool(path.parts)
        and all(part not in {"", ".", ".."} for part in path.parts)
        and path.as_posix() == value
    )


def _regular_record_path(
    *,
    root: Path,
    path: Path,
    missing_ok: bool,
    code: str,
) -> Path | None:
    try:
        identity = path.lstat()
    except FileNotFoundError:
        if missing_ok:
            return None
        raise ReportingError(code)
    except OSError as exc:
        raise ReportingError(code) from exc
    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise ReportingError(code) from exc
    if (
        not stat.S_ISREG(identity.st_mode)
        or path.is_symlink()
        or resolved != path
        or not resolved.is_relative_to(root)
    ):
        _fail(code)
    return path


def _validate_attempt(
    lock: Mapping[str, object],
    attempt: object,
    *,
    attempt_class: str,
    block_id: str,
    sequence_index: int,
) -> dict[str, Any]:
    record = _validate_record(attempt, "block_attempt.v1")
    if (
        record["pilot_lock_digest"] != canonical_sha256(lock)
        or record["attempt_class"] != attempt_class
        or record["block_id"] != block_id
        or record["sequence_index"] != sequence_index
    ):
        _fail("attempt_binding_mismatch")
    return record


def _validate_attempt_sequence(
    *,
    lock: Mapping[str, object],
    block_attempts: Sequence[Mapping[str, object]],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if not block_attempts:
        _fail("smoke_attempt_missing_or_invalid")
    smoke = _validate_attempt(
        lock,
        block_attempts[0],
        attempt_class="SMOKE",
        block_id=lock["smoke_id"],  # type: ignore[index]
        sequence_index=0,
    )
    live_attempts: list[dict[str, Any]] = []
    valid_count = 0
    for index, attempt in enumerate(block_attempts[1:]):
        if smoke["status"] != "VALID":
            _fail("live_attempt_after_failed_smoke")
        live_ids = lock["live_attempt_ids"]  # type: ignore[index]
        if (
            index >= len(live_ids)
            or valid_count >= lock["valid_block_count"]  # type: ignore[index]
        ):
            _fail("attempt_after_denominator")
        record = _validate_attempt(
            lock,
            attempt,
            attempt_class="LIVE",
            block_id=live_ids[index],
            sequence_index=index,
        )
        live_attempts.append(record)
        if record["status"] == "VALID":
            valid_count += 1
    return smoke, live_attempts


def load_attempt_records(
    *,
    lock: Mapping[str, object],
    evidence_root: Path,
) -> tuple[dict[str, Any], ...]:
    """Load the exact locked smoke and contiguous live-attempt prefix."""

    lock_record = _validate_record(lock, "pilot_lock.v1")
    try:
        root_identity = evidence_root.lstat()
        resolved_root = evidence_root.resolve(strict=True)
    except OSError as exc:
        raise ReportingError("evidence_root_invalid") from exc
    if (
        not evidence_root.is_absolute()
        or resolved_root != evidence_root
        or not stat.S_ISDIR(root_identity.st_mode)
        or evidence_root.is_symlink()
        or evidence_root.as_posix() != lock_record["evidence_root"]
    ):
        _fail("evidence_root_invalid")
    smoke_path = evidence_root / lock_record["smoke_id"] / "block-attempt.json"
    _regular_record_path(
        root=evidence_root,
        path=smoke_path,
        missing_ok=False,
        code="smoke_attempt_missing_or_invalid",
    )
    try:
        smoke = load_record(smoke_path, expected_kind="block_attempt.v1")
    except (OSError, PilotContractError) as exc:
        raise ReportingError("smoke_attempt_missing_or_invalid") from exc
    records = [
        _validate_attempt(
            lock_record,
            smoke,
            attempt_class="SMOKE",
            block_id=lock_record["smoke_id"],
            sequence_index=0,
        )
    ]
    if records[0]["status"] != "VALID":
        for block_id in lock_record["live_attempt_ids"]:
            path = evidence_root / block_id / "block-attempt.json"
            if _regular_record_path(
                root=evidence_root,
                path=path,
                missing_ok=True,
                code="live_attempt_invalid",
            ) is not None:
                _fail("live_attempt_after_failed_smoke")
        return tuple(records)

    valid_count = 0
    gap_seen = False
    for index, block_id in enumerate(lock_record["live_attempt_ids"]):
        path = evidence_root / block_id / "block-attempt.json"
        checked_path = _regular_record_path(
            root=evidence_root,
            path=path,
            missing_ok=True,
            code="live_attempt_invalid",
        )
        if checked_path is None:
            gap_seen = True
            continue
        if gap_seen:
            _fail("attempt_prefix_gap")
        if valid_count >= lock_record["valid_block_count"]:
            _fail("attempt_after_denominator")
        try:
            value = load_record(checked_path, expected_kind="block_attempt.v1")
        except (OSError, PilotContractError) as exc:
            raise ReportingError("live_attempt_invalid") from exc
        record = _validate_attempt(
            lock_record,
            value,
            attempt_class="LIVE",
            block_id=block_id,
            sequence_index=index,
        )
        records.append(record)
        if record["status"] == "VALID":
            valid_count += 1
    if gap_seen and valid_count < lock_record["valid_block_count"]:
        _fail("attempt_prefix_gap")
    return tuple(records)


def assess_readiness(
    *,
    lock: Mapping[str, object],
    block_attempts: Sequence[Mapping[str, object]],
) -> str:
    """Derive only one of the three locked readiness states."""

    lock_record = _validate_record(lock, "pilot_lock.v1")
    smoke, live_attempts = _validate_attempt_sequence(
        lock=lock_record,
        block_attempts=block_attempts,
    )
    if smoke["status"] != "VALID":
        return "STOP_APPARATUS_NOT_VIABLE"
    valid = sum(attempt["status"] == "VALID" for attempt in live_attempts)
    if valid >= lock_record["valid_block_count"]:
        return "EVIDENCE_COMPLETE_OWNER_DECISION_REQUIRED"
    if len(live_attempts) >= lock_record["max_live_attempt_count"]:
        return "STOP_INSUFFICIENT_VALID_BLOCKS"
    _fail("attempt_prefix_incomplete")
