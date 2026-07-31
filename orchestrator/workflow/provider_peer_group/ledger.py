"""Durable append-only message ledgers for provider peer-group receivers."""

from __future__ import annotations

import hashlib
import json
import os
import stat
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..._common.canonical import compact_ascii_json_dumps
from ..._common.validation import nonempty_string, ordinary_integer
from .models import (
    PeerAttemptIdentity,
    PeerGroupVisitIdentity,
    PeerLedgerCounts,
    PeerLedgerSummary,
)


PEER_MESSAGE_LEDGER_SCHEMA_VERSION = "provider_peer_message_ledger.v1"
_DIGEST_PREFIX = "sha256:"
_DIGEST_LENGTH = len(_DIGEST_PREFIX) + 64


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _canonical_row_bytes(row: Mapping[str, Any]) -> bytes:
    return (
        compact_ascii_json_dumps(dict(row)).encode("ascii")
        + b"\n"
    )


def _sha256(payload: bytes) -> str:
    return _DIGEST_PREFIX + hashlib.sha256(payload).hexdigest()


def _validate_digest(value: object, *, field: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != _DIGEST_LENGTH
        or not value.startswith(_DIGEST_PREFIX)
        or any(character not in "0123456789abcdef" for character in value[7:])
    ):
        raise ValueError(f"{field} must be a canonical sha256 digest")
    return value


def _nonempty_string(value: object, *, field: str) -> str:
    return nonempty_string(value, field)


def _positive_int(value: object, *, field: str) -> int:
    try:
        return ordinary_integer(value, field, minimum=1)
    except ValueError:
        raise ValueError(f"{field} must be a positive integer") from None


def _nonnegative_int(value: object, *, field: str) -> int:
    try:
        return ordinary_integer(value, field, minimum=0)
    except ValueError:
        raise ValueError(f"{field} must be a non-negative integer") from None


def _timestamp(clock: Callable[[], datetime]) -> str:
    value = clock()
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise ValueError("ledger clock must return a timezone-aware datetime")
    return value.astimezone(timezone.utc).isoformat()


def _validate_timestamp(value: object, *, field: str) -> str:
    text = _nonempty_string(value, field=field)
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(f"{field} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field} must include a timezone")
    return text


def _write_all(descriptor: int, payload: bytes) -> None:
    offset = 0
    while offset < len(payload):
        written = os.write(descriptor, payload[offset:])
        if isinstance(written, bool) or not isinstance(written, int) or written <= 0:
            raise OSError("ledger append made no progress")
        offset += written


def _pread_all(descriptor: int, size: int) -> bytes:
    chunks: list[bytes] = []
    offset = 0
    while offset < size:
        chunk = os.pread(descriptor, min(1024 * 1024, size - offset), offset)
        if not chunk:
            break
        chunks.append(chunk)
        offset += len(chunk)
    return b"".join(chunks)


def _metadata(metadata: os.stat_result) -> tuple[int, int, int, int, int]:
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_size,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
    )


@dataclass
class _MessageLifecycle:
    request_id: str
    sender_attempt: PeerAttemptIdentity
    content_sha256: str
    byte_count: int
    outcome: str | None = None
    acknowledged: bool = False


class PeerMessageLedger:
    """Single-writer durable ledger bound to one exact receiver attempt."""

    def __init__(
        self,
        *,
        path: Path,
        descriptor: int,
        group_visit: PeerGroupVisitIdentity,
        receiver_attempt: PeerAttemptIdentity,
        clock: Callable[[], datetime],
        expected_hasher: Any,
        expected_metadata: tuple[int, int, int, int, int],
    ) -> None:
        self._path = path
        self._descriptor = descriptor
        self._group_visit = group_visit
        self._receiver_attempt = receiver_attempt
        self._clock = clock
        self._expected_hasher = expected_hasher
        self._expected_metadata = expected_metadata
        self._row_count = 1
        self._counts = {
            "recorded": 0,
            "offered": 0,
            "offer_failed": 0,
            "receiver_acknowledged": 0,
        }
        self._messages: dict[str, _MessageLifecycle] = {}
        self._request_ids: set[str] = set()
        self._last_coordinator_sequence = 0
        self._poisoned = False
        self._finalized_summary: PeerLedgerSummary | None = None

    @classmethod
    def create(
        cls,
        path: Path,
        *,
        group_visit: PeerGroupVisitIdentity,
        receiver_attempt: PeerAttemptIdentity,
        clock: Callable[[], datetime] = _utc_now,
    ) -> PeerMessageLedger:
        if not isinstance(group_visit, PeerGroupVisitIdentity):
            raise TypeError("group_visit must be a PeerGroupVisitIdentity")
        if not isinstance(receiver_attempt, PeerAttemptIdentity):
            raise TypeError("receiver_attempt must be a PeerAttemptIdentity")
        if not callable(clock):
            raise TypeError("clock must be callable")

        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        header = {
            "schema_version": PEER_MESSAGE_LEDGER_SCHEMA_VERSION,
            "row_kind": "header",
            "sequence": 0,
            "group_visit": group_visit.to_dict(),
            "receiver_attempt": receiver_attempt.to_dict(),
            "created_at": _timestamp(clock),
        }
        header_bytes = _canonical_row_bytes(header)
        flags = (
            os.O_RDWR
            | os.O_CREAT
            | os.O_EXCL
            | os.O_APPEND
            | getattr(os, "O_CLOEXEC", 0)
        )
        descriptor: int | None = None
        parent_descriptor: int | None = None
        try:
            descriptor = os.open(destination, flags, 0o600)
            _write_all(descriptor, header_bytes)
            os.fsync(descriptor)
            parent_descriptor = os.open(
                destination.parent,
                os.O_RDONLY
                | getattr(os, "O_DIRECTORY", 0)
                | getattr(os, "O_CLOEXEC", 0),
            )
            os.fsync(parent_descriptor)
            bound = os.fstat(descriptor)
            if not stat.S_ISREG(bound.st_mode):
                raise RuntimeError("peer message ledger is not a regular file")
            hasher = hashlib.sha256(header_bytes)
            return cls(
                path=destination,
                descriptor=descriptor,
                group_visit=group_visit,
                receiver_attempt=receiver_attempt,
                clock=clock,
                expected_hasher=hasher,
                expected_metadata=_metadata(bound),
            )
        except BaseException:
            if descriptor is not None:
                os.close(descriptor)
            raise
        finally:
            if parent_descriptor is not None:
                os.close(parent_descriptor)

    @property
    def path(self) -> Path:
        return self._path

    @property
    def receiver_attempt(self) -> PeerAttemptIdentity:
        return self._receiver_attempt

    def append_recorded(
        self,
        *,
        coordinator_sequence: int,
        request_id: str,
        message_id: str,
        sender_attempt: PeerAttemptIdentity,
        content: str,
    ) -> str:
        coordinator_sequence = _positive_int(
            coordinator_sequence,
            field="coordinator_sequence",
        )
        request_id = _nonempty_string(request_id, field="request_id")
        message_id = _nonempty_string(message_id, field="message_id")
        if not isinstance(sender_attempt, PeerAttemptIdentity):
            raise TypeError("sender_attempt must be a PeerAttemptIdentity")
        content = _nonempty_string(content, field="content")
        try:
            content_bytes = content.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise ValueError("content must be valid UTF-8") from exc
        if message_id in self._messages:
            raise ValueError("message_id is already recorded in this ledger")
        if request_id in self._request_ids:
            raise ValueError("request_id is already recorded in this ledger")
        if coordinator_sequence <= self._last_coordinator_sequence:
            raise ValueError("coordinator_sequence must increase monotonically")

        content_sha256 = _sha256(content_bytes)
        row = {
            "schema_version": PEER_MESSAGE_LEDGER_SCHEMA_VERSION,
            "row_kind": "recorded",
            "sequence": self._row_count,
            "coordinator_sequence": coordinator_sequence,
            "request_id": request_id,
            "message_id": message_id,
            "sender_attempt": sender_attempt.to_dict(),
            "receiver_attempt": self._receiver_attempt.to_dict(),
            "content": content,
            "content_sha256": content_sha256,
            "recorded_at": _timestamp(self._clock),
        }
        self._append_row(row)
        self._messages[message_id] = _MessageLifecycle(
            request_id=request_id,
            sender_attempt=sender_attempt,
            content_sha256=content_sha256,
            byte_count=len(content_bytes),
        )
        self._request_ids.add(request_id)
        self._last_coordinator_sequence = coordinator_sequence
        self._counts["recorded"] += 1
        return content_sha256

    def append_offered(
        self,
        *,
        message_id: str,
        adapter_instance_id: str,
        handle_id: str,
        byte_count: int,
        content_sha256: str,
    ) -> None:
        message_id = _nonempty_string(message_id, field="message_id")
        adapter_instance_id = _nonempty_string(
            adapter_instance_id,
            field="adapter_instance_id",
        )
        handle_id = _nonempty_string(handle_id, field="handle_id")
        byte_count = _positive_int(byte_count, field="byte_count")
        content_sha256 = _validate_digest(
            content_sha256,
            field="content_sha256",
        )
        message = self._recorded_message(message_id)
        if message.outcome is not None:
            raise ValueError("message already has a delivery outcome")
        if (
            byte_count != message.byte_count
            or content_sha256 != message.content_sha256
        ):
            raise ValueError(
                "offered row must bind the exact recorded content bytes"
            )

        row = {
            "schema_version": PEER_MESSAGE_LEDGER_SCHEMA_VERSION,
            "row_kind": "offered",
            "sequence": self._row_count,
            "message_id": message_id,
            "receiver_attempt": self._receiver_attempt.to_dict(),
            "adapter_instance_id": adapter_instance_id,
            "handle_id": handle_id,
            "byte_count": byte_count,
            "content_sha256": content_sha256,
            "offered_at": _timestamp(self._clock),
        }
        self._append_row(row)
        message.outcome = "offered"
        self._counts["offered"] += 1

    def append_offer_failed(
        self,
        *,
        message_id: str,
        error_code: str,
        message: str,
    ) -> None:
        message_id = _nonempty_string(message_id, field="message_id")
        error_code = _nonempty_string(error_code, field="error_code")
        failure_message = _nonempty_string(message, field="message")
        lifecycle = self._recorded_message(message_id)
        if lifecycle.outcome is not None:
            raise ValueError("message already has a delivery outcome")

        row = {
            "schema_version": PEER_MESSAGE_LEDGER_SCHEMA_VERSION,
            "row_kind": "offer_failed",
            "sequence": self._row_count,
            "message_id": message_id,
            "receiver_attempt": self._receiver_attempt.to_dict(),
            "content_sha256": lifecycle.content_sha256,
            "error_code": error_code,
            "message": failure_message,
            "failed_at": _timestamp(self._clock),
        }
        self._append_row(row)
        lifecycle.outcome = "offer_failed"
        self._counts["offer_failed"] += 1

    def append_receiver_acknowledged(
        self,
        *,
        request_id: str,
        message_id: str,
        receiver_attempt: PeerAttemptIdentity,
    ) -> None:
        request_id = _nonempty_string(request_id, field="request_id")
        message_id = _nonempty_string(message_id, field="message_id")
        if not isinstance(receiver_attempt, PeerAttemptIdentity):
            raise TypeError("receiver_attempt must be a PeerAttemptIdentity")
        if receiver_attempt != self._receiver_attempt:
            raise ValueError("acknowledgement receiver attempt does not match ledger")
        if request_id in self._request_ids:
            raise ValueError("request_id is already recorded in this ledger")
        lifecycle = self._recorded_message(message_id)
        if lifecycle.outcome != "offered":
            raise ValueError(
                "only a durably offered message may be acknowledged"
            )
        if lifecycle.acknowledged:
            raise ValueError("message is already acknowledged")

        row = {
            "schema_version": PEER_MESSAGE_LEDGER_SCHEMA_VERSION,
            "row_kind": "receiver_acknowledged",
            "sequence": self._row_count,
            "request_id": request_id,
            "message_id": message_id,
            "receiver_attempt": receiver_attempt.to_dict(),
            "acknowledged_at": _timestamp(self._clock),
        }
        self._append_row(row)
        lifecycle.acknowledged = True
        self._request_ids.add(request_id)
        self._counts["receiver_acknowledged"] += 1

    def finalize(self) -> PeerLedgerSummary:
        if self._finalized_summary is not None:
            return self._finalized_summary
        self._ensure_writable()
        self._assert_integrity()
        try:
            os.fsync(self._descriptor)
        except BaseException as exc:
            self._poisoned = True
            raise RuntimeError(
                "peer message ledger finalization durability is uncertain"
            ) from exc
        summary = PeerLedgerSummary(
            receiver_attempt=self._receiver_attempt,
            ledger_sha256=_DIGEST_PREFIX + self._expected_hasher.hexdigest(),
            row_count=self._row_count,
            counts=PeerLedgerCounts(**self._counts),
        )
        os.close(self._descriptor)
        self._descriptor = -1
        self._finalized_summary = summary
        return summary

    def _recorded_message(self, message_id: str) -> _MessageLifecycle:
        try:
            return self._messages[message_id]
        except KeyError as exc:
            raise ValueError("message_id is not recorded in this ledger") from exc

    def _append_row(self, row: Mapping[str, Any]) -> None:
        self._ensure_writable()
        self._assert_integrity()
        payload = _canonical_row_bytes(row)
        expected_hasher = self._expected_hasher.copy()
        expected_hasher.update(payload)
        expected_size = self._expected_metadata[2] + len(payload)
        try:
            _write_all(self._descriptor, payload)
            os.fsync(self._descriptor)
            self._verify_post_append(
                expected_size=expected_size,
                expected_digest=expected_hasher.digest(),
            )
            updated_metadata = _metadata(os.fstat(self._descriptor))
        except BaseException as exc:
            self._poisoned = True
            raise RuntimeError(
                "peer message ledger append durability is uncertain; "
                "writer is poisoned"
            ) from exc
        self._expected_hasher = expected_hasher
        self._expected_metadata = updated_metadata
        self._row_count += 1

    def _ensure_writable(self) -> None:
        if self._poisoned:
            raise RuntimeError("peer message ledger writer is poisoned")
        if self._finalized_summary is not None or self._descriptor < 0:
            raise RuntimeError("peer message ledger is finalized")

    def _assert_integrity(self) -> None:
        try:
            descriptor_metadata = os.fstat(self._descriptor)
            path_metadata = os.stat(self._path, follow_symlinks=False)
            if (
                not stat.S_ISREG(descriptor_metadata.st_mode)
                or not stat.S_ISREG(path_metadata.st_mode)
                or _metadata(descriptor_metadata) != self._expected_metadata
                or _metadata(path_metadata) != self._expected_metadata
            ):
                raise RuntimeError("peer message ledger binding changed")
            payload = _pread_all(
                self._descriptor,
                self._expected_metadata[2],
            )
            after = os.fstat(self._descriptor)
            if (
                _metadata(after) != self._expected_metadata
                or len(payload) != self._expected_metadata[2]
                or hashlib.sha256(payload).digest()
                != self._expected_hasher.digest()
            ):
                raise RuntimeError("peer message ledger content changed")
        except BaseException as exc:
            self._poisoned = True
            if isinstance(exc, RuntimeError) and "ledger" in str(exc):
                raise
            raise RuntimeError(
                "peer message ledger integrity could not be established"
            ) from exc

    def _verify_post_append(
        self,
        *,
        expected_size: int,
        expected_digest: bytes,
    ) -> None:
        descriptor_metadata = os.fstat(self._descriptor)
        path_metadata = os.stat(self._path, follow_symlinks=False)
        if (
            not stat.S_ISREG(descriptor_metadata.st_mode)
            or not stat.S_ISREG(path_metadata.st_mode)
            or descriptor_metadata.st_dev != self._expected_metadata[0]
            or descriptor_metadata.st_ino != self._expected_metadata[1]
            or path_metadata.st_dev != descriptor_metadata.st_dev
            or path_metadata.st_ino != descriptor_metadata.st_ino
            or descriptor_metadata.st_size != expected_size
            or path_metadata.st_size != expected_size
        ):
            raise RuntimeError("peer message ledger binding changed during append")
        payload = _pread_all(self._descriptor, expected_size)
        after = os.fstat(self._descriptor)
        if (
            len(payload) != expected_size
            or after.st_size != expected_size
            or hashlib.sha256(payload).digest() != expected_digest
        ):
            raise RuntimeError("peer message ledger content changed during append")

    def __del__(self) -> None:
        descriptor = getattr(self, "_descriptor", -1)
        if isinstance(descriptor, int) and descriptor >= 0:
            try:
                os.close(descriptor)
            except OSError:
                pass
            self._descriptor = -1


def inspect_peer_message_ledger(path: Path) -> PeerLedgerSummary:
    """Validate and summarize one complete or partial receiver ledger."""

    ledger_path = Path(path)
    descriptor: int | None = None
    try:
        descriptor = os.open(
            ledger_path,
            os.O_RDONLY | getattr(os, "O_CLOEXEC", 0),
        )
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise RuntimeError("peer message ledger is not a regular file")
        payload = _pread_all(descriptor, before.st_size)
        after = os.fstat(descriptor)
        current = os.stat(ledger_path, follow_symlinks=False)
        if (
            _metadata(before) != _metadata(after)
            or _metadata(after) != _metadata(current)
            or len(payload) != before.st_size
        ):
            raise RuntimeError(
                "peer message ledger changed during inspection"
            )
    except BaseException as exc:
        if isinstance(exc, RuntimeError) and "ledger" in str(exc):
            raise
        raise RuntimeError("peer message ledger could not be inspected") from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)

    try:
        receiver_attempt, counts, row_count = _validate_ledger_payload(payload)
    except (TypeError, ValueError, UnicodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("peer message ledger is malformed") from exc
    return PeerLedgerSummary(
        receiver_attempt=receiver_attempt,
        ledger_sha256=_sha256(payload),
        row_count=row_count,
        counts=PeerLedgerCounts(**counts),
    )


def _validate_ledger_payload(
    payload: bytes,
) -> tuple[PeerAttemptIdentity, dict[str, int], int]:
    if not payload or not payload.endswith(b"\n"):
        raise ValueError("ledger must contain complete newline-terminated rows")
    encoded_lines = payload.splitlines(keepends=True)
    rows: list[dict[str, Any]] = []
    for encoded_line in encoded_lines:
        if not encoded_line.endswith(b"\n"):
            raise ValueError("ledger contains an incomplete tail")
        text = encoded_line[:-1].decode("ascii")
        row = json.loads(text)
        if not isinstance(row, dict):
            raise ValueError("ledger rows must be JSON objects")
        if _canonical_row_bytes(row) != encoded_line:
            raise ValueError("ledger row is not canonical JSON")
        rows.append(row)

    header = rows[0]
    _require_exact_keys(
        header,
        {
            "schema_version",
            "row_kind",
            "sequence",
            "group_visit",
            "receiver_attempt",
            "created_at",
        },
    )
    if (
        header["schema_version"] != PEER_MESSAGE_LEDGER_SCHEMA_VERSION
        or header["row_kind"] != "header"
        or header["sequence"] != 0
    ):
        raise ValueError("ledger header is invalid")
    PeerGroupVisitIdentity.from_dict(_mapping(header["group_visit"]))
    receiver_attempt = PeerAttemptIdentity.from_dict(
        _mapping(header["receiver_attempt"])
    )
    _validate_timestamp(header["created_at"], field="created_at")

    counts = {
        "recorded": 0,
        "offered": 0,
        "offer_failed": 0,
        "receiver_acknowledged": 0,
    }
    messages: dict[str, _MessageLifecycle] = {}
    request_ids: set[str] = set()
    last_coordinator_sequence = 0
    for expected_sequence, row in enumerate(rows[1:], start=1):
        if (
            row.get("schema_version")
            != PEER_MESSAGE_LEDGER_SCHEMA_VERSION
            or row.get("sequence") != expected_sequence
        ):
            raise ValueError("ledger sequence is invalid")
        kind = row.get("row_kind")
        if kind == "recorded":
            _require_exact_keys(
                row,
                {
                    "schema_version",
                    "row_kind",
                    "sequence",
                    "coordinator_sequence",
                    "request_id",
                    "message_id",
                    "sender_attempt",
                    "receiver_attempt",
                    "content",
                    "content_sha256",
                    "recorded_at",
                },
            )
            coordinator_sequence = _positive_int(
                row["coordinator_sequence"],
                field="coordinator_sequence",
            )
            if coordinator_sequence <= last_coordinator_sequence:
                raise ValueError("coordinator sequence is not monotonic")
            last_coordinator_sequence = coordinator_sequence
            request_id = _unique_id(
                row["request_id"],
                request_ids,
                field="request_id",
            )
            message_id = _nonempty_string(
                row["message_id"],
                field="message_id",
            )
            if message_id in messages:
                raise ValueError("duplicate message_id")
            sender_attempt = PeerAttemptIdentity.from_dict(
                _mapping(row["sender_attempt"])
            )
            _require_receiver(row["receiver_attempt"], receiver_attempt)
            content = _nonempty_string(row["content"], field="content")
            content_bytes = content.encode("utf-8")
            content_sha256 = _validate_digest(
                row["content_sha256"],
                field="content_sha256",
            )
            if content_sha256 != _sha256(content_bytes):
                raise ValueError("recorded content digest is invalid")
            _validate_timestamp(row["recorded_at"], field="recorded_at")
            messages[message_id] = _MessageLifecycle(
                request_id=request_id,
                sender_attempt=sender_attempt,
                content_sha256=content_sha256,
                byte_count=len(content_bytes),
            )
            counts["recorded"] += 1
            continue

        message_id = _nonempty_string(
            row.get("message_id"),
            field="message_id",
        )
        if message_id not in messages:
            raise ValueError("ledger outcome references an unknown message")
        message = messages[message_id]
        if kind == "offered":
            _require_exact_keys(
                row,
                {
                    "schema_version",
                    "row_kind",
                    "sequence",
                    "message_id",
                    "receiver_attempt",
                    "adapter_instance_id",
                    "handle_id",
                    "byte_count",
                    "content_sha256",
                    "offered_at",
                },
            )
            if message.outcome is not None:
                raise ValueError("message has duplicate delivery outcomes")
            _require_receiver(row["receiver_attempt"], receiver_attempt)
            _nonempty_string(
                row["adapter_instance_id"],
                field="adapter_instance_id",
            )
            _nonempty_string(row["handle_id"], field="handle_id")
            if (
                _positive_int(row["byte_count"], field="byte_count")
                != message.byte_count
                or _validate_digest(
                    row["content_sha256"],
                    field="content_sha256",
                )
                != message.content_sha256
            ):
                raise ValueError("offered row content binding is invalid")
            _validate_timestamp(row["offered_at"], field="offered_at")
            message.outcome = "offered"
            counts["offered"] += 1
        elif kind == "offer_failed":
            _require_exact_keys(
                row,
                {
                    "schema_version",
                    "row_kind",
                    "sequence",
                    "message_id",
                    "receiver_attempt",
                    "content_sha256",
                    "error_code",
                    "message",
                    "failed_at",
                },
            )
            if message.outcome is not None:
                raise ValueError("message has duplicate delivery outcomes")
            _require_receiver(row["receiver_attempt"], receiver_attempt)
            if (
                _validate_digest(
                    row["content_sha256"],
                    field="content_sha256",
                )
                != message.content_sha256
            ):
                raise ValueError("offer failure content binding is invalid")
            _nonempty_string(row["error_code"], field="error_code")
            _nonempty_string(row["message"], field="message")
            _validate_timestamp(row["failed_at"], field="failed_at")
            message.outcome = "offer_failed"
            counts["offer_failed"] += 1
        elif kind == "receiver_acknowledged":
            _require_exact_keys(
                row,
                {
                    "schema_version",
                    "row_kind",
                    "sequence",
                    "request_id",
                    "message_id",
                    "receiver_attempt",
                    "acknowledged_at",
                },
            )
            if message.outcome != "offered" or message.acknowledged:
                raise ValueError("acknowledgement lifecycle is invalid")
            _unique_id(row["request_id"], request_ids, field="request_id")
            _require_receiver(row["receiver_attempt"], receiver_attempt)
            _validate_timestamp(
                row["acknowledged_at"],
                field="acknowledged_at",
            )
            message.acknowledged = True
            counts["receiver_acknowledged"] += 1
        else:
            raise ValueError("ledger row kind is unknown")

    return receiver_attempt, counts, len(rows)


def _mapping(value: object) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("ledger identity must be an object")
    return value


def _require_exact_keys(
    value: Mapping[str, Any],
    expected: set[str],
) -> None:
    if set(value) != expected:
        raise ValueError("ledger row fields are not closed")


def _require_receiver(
    value: object,
    expected: PeerAttemptIdentity,
) -> None:
    observed = PeerAttemptIdentity.from_dict(_mapping(value))
    if observed != expected:
        raise ValueError("ledger row receiver attempt does not match header")


def _unique_id(
    value: object,
    seen: set[str],
    *,
    field: str,
) -> str:
    identifier = _nonempty_string(value, field=field)
    if identifier in seen:
        raise ValueError(f"duplicate {field}")
    seen.add(identifier)
    return identifier


__all__ = [
    "PEER_MESSAGE_LEDGER_SCHEMA_VERSION",
    "PeerMessageLedger",
    "inspect_peer_message_ledger",
]
