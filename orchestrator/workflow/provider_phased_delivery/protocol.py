"""Content-free attempt-bound transport for phased materialization submits.

Wire v1 is one bounded canonical-JSON newline frame over an attempt-local
UNIX socket. The inert environment binding contains only future socket
coordinates, attempt/endpoint claims, a secret token, and the single absolute
deadline. Request v1 repeats those claims, adds one bounded request id, and
seals a content-free payload; the CLI always uses the empty-payload seal.
"""

from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import re
import socket
import time
from typing import Any, Mapping

from orchestrator._common.canonical import compact_ascii_json_dumps

from .diagnostics import (
    DiagnosticSource,
    DiagnosticSpan,
    PhasedDeliveryDiagnostic,
    RejectedValue,
)
from .models import SubmitReceipt


PHASED_PROVIDER_BINDING_ENV = "ORCHESTRATOR_PHASED_PROVIDER_BINDING"
MAX_CLIENT_REQUEST_ID_BYTES = 128
_BINDING_SCHEMA = "provider_phased_submit_binding.v1"
_REQUEST_SCHEMA = "provider_phased_submit_request.v1"
_MAX_FRAME_BYTES = 256 * 1024
_MAX_BINDING_BYTES = 4096
_TOKEN_RE = re.compile(r"[0-9a-f]{64}")
_DIGEST_RE = re.compile(r"sha256:[0-9a-f]{64}")
_NONCE_RE = re.compile(r"[A-Za-z0-9_-]{1,64}")
_EMPTY_PAYLOAD_SHA256 = (
    "sha256:" + hashlib.sha256(b"").hexdigest()
)


class PhasedSubmitProtocolClosedError(RuntimeError):
    """The exact attempt endpoint is unavailable or cannot return a receipt."""


def _canonical(value: Mapping[str, Any]) -> bytes:
    return (
        compact_ascii_json_dumps(
            dict(value),
            allow_nan=False,
        ).encode("ascii")
        + b"\n"
    )


def _without_duplicates(
    pairs: list[tuple[str, Any]],
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _decode_frame(frame: bytes, *, field: str) -> Mapping[str, Any]:
    if (
        not frame.endswith(b"\n")
        or frame.count(b"\n") != 1
        or len(frame) > _MAX_FRAME_BYTES
    ):
        raise ValueError(f"{field} must be one bounded newline frame")
    try:
        value = json.loads(
            frame[:-1].decode("ascii"),
            object_pairs_hook=_without_duplicates,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ValueError(f"{field} must be canonical JSON") from exc
    try:
        canonical = _canonical(value) if isinstance(value, Mapping) else None
    except (RecursionError, TypeError, ValueError):
        canonical = None
    if not isinstance(value, Mapping) or canonical != frame:
        raise ValueError(f"{field} must be a canonical JSON object")
    return value


def _remaining(deadline: float) -> float:
    if (
        isinstance(deadline, bool)
        or not isinstance(deadline, (int, float))
        or not math.isfinite(deadline)
    ):
        raise ValueError("deadline must be one finite absolute timestamp")
    remaining = float(deadline) - time.monotonic()
    if remaining <= 0:
        raise TimeoutError("whole-attempt deadline exhausted")
    return remaining


def _require_digest(value: object, *, field: str) -> str:
    if not isinstance(value, str) or _DIGEST_RE.fullmatch(value) is None:
        raise ValueError(f"{field} must be a canonical SHA-256 digest")
    return value


def _require_request_id(value: object) -> str:
    if (
        not isinstance(value, str)
        or not value
        or not value.isascii()
        or len(value.encode("ascii")) > MAX_CLIENT_REQUEST_ID_BYTES
    ):
        raise ValueError(
            "client_request_id must be nonempty bounded ASCII text"
        )
    return value


@dataclass(frozen=True, slots=True)
class SubmitEndpointLocator:
    """An inert future endpoint coordinate; construction reserves nothing."""

    endpoint_instance_id: str
    socket_path: Path

    def __post_init__(self) -> None:
        if (
            not isinstance(self.endpoint_instance_id, str)
            or not self.endpoint_instance_id
            or not self.endpoint_instance_id.isascii()
        ):
            raise ValueError("endpoint_instance_id must be nonempty ASCII")
        if (
            not isinstance(self.socket_path, Path)
            or not self.socket_path.is_absolute()
        ):
            raise ValueError("socket_path must be an absolute Path")


@dataclass(frozen=True, slots=True)
class PhasedSubmitBinding:
    """Opaque provider binding derived before endpoint allocation."""

    attempt_scope_sha256: str
    endpoint_instance_id: str
    binding_token: str
    socket_path: Path
    deadline: float

    def __post_init__(self) -> None:
        _require_digest(
            self.attempt_scope_sha256,
            field="attempt_scope_sha256",
        )
        if (
            not isinstance(self.endpoint_instance_id, str)
            or not self.endpoint_instance_id
            or not self.endpoint_instance_id.isascii()
        ):
            raise ValueError("endpoint_instance_id must be nonempty ASCII")
        if (
            not isinstance(self.binding_token, str)
            or _TOKEN_RE.fullmatch(self.binding_token) is None
        ):
            raise ValueError("binding_token must be 64 lowercase hex digits")
        if (
            not isinstance(self.socket_path, Path)
            or not self.socket_path.is_absolute()
        ):
            raise ValueError("socket_path must be an absolute Path")
        if (
            isinstance(self.deadline, bool)
            or not isinstance(self.deadline, (int, float))
            or not math.isfinite(self.deadline)
        ):
            raise ValueError("deadline must be finite")

    @property
    def opaque_value(self) -> str:
        raw = _canonical(
            {
                "schema_version": _BINDING_SCHEMA,
                "attempt_scope_sha256": self.attempt_scope_sha256,
                "endpoint_instance_id": self.endpoint_instance_id,
                "binding_token": self.binding_token,
                "socket_path": str(self.socket_path),
                "deadline": self.deadline,
            }
        )[:-1]
        return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def derive_submit_binding_and_locator(
    *,
    attempt_scope_sha256: str,
    socket_root: Path,
    nonce: str,
    deadline: float,
) -> tuple[PhasedSubmitBinding, SubmitEndpointLocator]:
    """Purely derive inert binding data and an unallocated locator."""

    scope = _require_digest(
        attempt_scope_sha256,
        field="attempt_scope_sha256",
    )
    if not isinstance(socket_root, Path) or not socket_root.is_absolute():
        raise ValueError("socket_root must be an absolute Path")
    if not isinstance(nonce, str) or _NONCE_RE.fullmatch(nonce) is None:
        raise ValueError("nonce must be bounded endpoint-safe text")
    endpoint_id = hashlib.sha256(
        f"{scope}\0{nonce}\0endpoint".encode("ascii")
    ).hexdigest()
    token = hashlib.sha256(
        f"{scope}\0{nonce}\0binding".encode("ascii")
    ).hexdigest()
    socket_path = socket_root / f"phased-{nonce}.sock"
    locator = SubmitEndpointLocator(
        endpoint_instance_id=endpoint_id,
        socket_path=socket_path,
    )
    return (
        PhasedSubmitBinding(
            attempt_scope_sha256=scope,
            endpoint_instance_id=endpoint_id,
            binding_token=token,
            socket_path=socket_path,
            deadline=deadline,
        ),
        locator,
    )


def decode_submit_binding(
    environ: Mapping[str, str] | None = None,
) -> PhasedSubmitBinding:
    source = os.environ if environ is None else environ
    encoded = source.get(PHASED_PROVIDER_BINDING_ENV)
    if not isinstance(encoded, str) or not encoded:
        raise ValueError(
            f"{PHASED_PROVIDER_BINDING_ENV} must contain an active binding"
        )
    if len(encoded.encode("utf-8")) > (2 * _MAX_BINDING_BYTES):
        raise ValueError(f"{PHASED_PROVIDER_BINDING_ENV} is invalid")
    try:
        padding = "=" * (-len(encoded) % 4)
        raw = base64.b64decode(
            encoded + padding,
            altchars=b"-_",
            validate=True,
        )
        if (
            base64.urlsafe_b64encode(raw)
            .decode("ascii")
            .rstrip("=")
            != encoded
        ):
            raise ValueError("binding encoding is not canonical")
        value = json.loads(
            raw.decode("ascii"),
            object_pairs_hook=_without_duplicates,
        )
        if len(raw) > _MAX_BINDING_BYTES:
            raise ValueError("binding exceeds bounded size")
    except (
        UnicodeDecodeError,
        ValueError,
        binascii.Error,
        json.JSONDecodeError,
        RecursionError,
    ) as exc:
        raise ValueError(
            f"{PHASED_PROVIDER_BINDING_ENV} is invalid"
        ) from exc
    expected = {
        "schema_version",
        "attempt_scope_sha256",
        "endpoint_instance_id",
        "binding_token",
        "socket_path",
        "deadline",
    }
    try:
        binding_is_canonical = (
            isinstance(value, Mapping)
            and set(value) == expected
            and value.get("schema_version") == _BINDING_SCHEMA
            and _canonical(value)[:-1] == raw
        )
    except (RecursionError, TypeError, ValueError) as exc:
        raise ValueError(
            f"{PHASED_PROVIDER_BINDING_ENV} is invalid"
        ) from exc
    if not binding_is_canonical:
        raise ValueError(f"{PHASED_PROVIDER_BINDING_ENV} is invalid")
    try:
        return PhasedSubmitBinding(
            attempt_scope_sha256=value["attempt_scope_sha256"],
            endpoint_instance_id=value["endpoint_instance_id"],
            binding_token=value["binding_token"],
            socket_path=Path(value["socket_path"]),
            deadline=value["deadline"],
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(
            f"{PHASED_PROVIDER_BINDING_ENV} is invalid"
        ) from exc


@dataclass(frozen=True, slots=True)
class SubmitRequest:
    attempt_scope_sha256: str
    endpoint_instance_id: str
    binding_token: str
    client_request_id: str
    payload_sha256: str

    schema_version = _REQUEST_SCHEMA

    def __post_init__(self) -> None:
        _require_digest(
            self.attempt_scope_sha256,
            field="attempt_scope_sha256",
        )
        if (
            not isinstance(self.endpoint_instance_id, str)
            or not self.endpoint_instance_id
            or not self.endpoint_instance_id.isascii()
        ):
            raise ValueError("endpoint_instance_id must be nonempty ASCII")
        if (
            not isinstance(self.binding_token, str)
            or _TOKEN_RE.fullmatch(self.binding_token) is None
        ):
            raise ValueError("binding_token must be 64 lowercase hex digits")
        _require_request_id(self.client_request_id)
        _require_digest(self.payload_sha256, field="payload_sha256")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "attempt_scope_sha256": self.attempt_scope_sha256,
            "endpoint_instance_id": self.endpoint_instance_id,
            "binding_token": self.binding_token,
            "client_request_id": self.client_request_id,
            "payload_sha256": self.payload_sha256,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "SubmitRequest":
        if set(value) != {
            "schema_version",
            "attempt_scope_sha256",
            "endpoint_instance_id",
            "binding_token",
            "client_request_id",
            "payload_sha256",
        } or value.get("schema_version") != _REQUEST_SCHEMA:
            raise ValueError("submit request shape is invalid")
        return cls(
            attempt_scope_sha256=value["attempt_scope_sha256"],
            endpoint_instance_id=value["endpoint_instance_id"],
            binding_token=value["binding_token"],
            client_request_id=value["client_request_id"],
            payload_sha256=value["payload_sha256"],
        )


def _span_to_dict(value: DiagnosticSpan | None) -> object:
    if value is None:
        return None
    return {
        "start_line": value.start_line,
        "start_column": value.start_column,
        "end_line": value.end_line,
        "end_column": value.end_column,
    }


def _source_to_dict(value: DiagnosticSource) -> dict[str, object]:
    return {
        "kind": value.kind,
        "owner": value.owner,
        "path": value.path,
        "span": _span_to_dict(value.span),
    }


def diagnostic_to_dict(
    value: PhasedDeliveryDiagnostic,
) -> dict[str, object]:
    if type(value) is not PhasedDeliveryDiagnostic:
        raise TypeError("diagnostic must be exact")
    return {
        "schema_version": value.schema_version,
        "code": value.code,
        "reason": value.reason,
        "rejected_value": {
            "type": value.rejected_value.type,
            "canonical_value": value.rejected_value.canonical_value,
            "summary": value.rejected_value.summary,
        },
        "primary_source": _source_to_dict(value.primary_source),
        "related_sources": [
            _source_to_dict(source) for source in value.related_sources
        ],
    }


def _span_from_dict(value: object) -> DiagnosticSpan | None:
    if value is None:
        return None
    if not isinstance(value, Mapping) or set(value) != {
        "start_line",
        "start_column",
        "end_line",
        "end_column",
    }:
        raise ValueError("diagnostic span shape is invalid")
    return DiagnosticSpan(**value)


def _source_from_dict(value: object) -> DiagnosticSource:
    if not isinstance(value, Mapping) or set(value) != {
        "kind",
        "owner",
        "path",
        "span",
    }:
        raise ValueError("diagnostic source shape is invalid")
    return DiagnosticSource(
        kind=value["kind"],
        owner=value["owner"],
        path=value["path"],
        span=_span_from_dict(value["span"]),
    )


def diagnostic_from_dict(value: object) -> PhasedDeliveryDiagnostic:
    if not isinstance(value, Mapping) or set(value) != {
        "schema_version",
        "code",
        "reason",
        "rejected_value",
        "primary_source",
        "related_sources",
    } or value.get("schema_version") != PhasedDeliveryDiagnostic.schema_version:
        raise ValueError("diagnostic shape is invalid")
    rejected = value["rejected_value"]
    related = value["related_sources"]
    if not isinstance(rejected, Mapping) or set(rejected) != {
        "type",
        "canonical_value",
        "summary",
    } or not isinstance(related, list):
        raise ValueError("diagnostic shape is invalid")
    return PhasedDeliveryDiagnostic(
        code=value["code"],
        reason=value["reason"],
        rejected_value=RejectedValue(
            type=rejected["type"],
            canonical_value=rejected["canonical_value"],
            summary=rejected["summary"],
        ),
        primary_source=_source_from_dict(value["primary_source"]),
        related_sources=tuple(_source_from_dict(item) for item in related),
    )


def receipt_to_dict(value: SubmitReceipt) -> dict[str, object]:
    if type(value) is not SubmitReceipt:
        raise TypeError("receipt must be an exact SubmitReceipt")
    return {
        "schema_version": value.schema_version,
        "status": value.status,
        "attempt_scope_sha256": value.attempt_scope_sha256,
        "client_request_id": value.client_request_id,
        "submission_ordinal": value.submission_ordinal,
        "configured_total": value.configured_total,
        "remaining_submissions": value.remaining_submissions,
        "diagnostic": (
            None
            if value.diagnostic is None
            else diagnostic_to_dict(value.diagnostic)
        ),
    }


def receipt_from_dict(value: Mapping[str, Any]) -> SubmitReceipt:
    if set(value) != {
        "schema_version",
        "status",
        "attempt_scope_sha256",
        "client_request_id",
        "submission_ordinal",
        "configured_total",
        "remaining_submissions",
        "diagnostic",
    } or value.get("schema_version") != SubmitReceipt.schema_version:
        raise ValueError("submit receipt shape is invalid")
    diagnostic = value["diagnostic"]
    return SubmitReceipt(
        status=value["status"],
        attempt_scope_sha256=value["attempt_scope_sha256"],
        client_request_id=value["client_request_id"],
        submission_ordinal=value["submission_ordinal"],
        configured_total=value["configured_total"],
        remaining_submissions=value["remaining_submissions"],
        diagnostic=(
            None if diagnostic is None else diagnostic_from_dict(diagnostic)
        ),
    )


def _read_frame(connection: socket.socket, *, deadline: float) -> bytes:
    chunks: list[bytes] = []
    size = 0
    while True:
        connection.settimeout(_remaining(deadline))
        chunk = connection.recv(min(65_536, _MAX_FRAME_BYTES + 1 - size))
        if not chunk:
            break
        chunks.append(chunk)
        size += len(chunk)
        if size > _MAX_FRAME_BYTES:
            raise ValueError("submit frame exceeds bounded size")
    combined = b"".join(chunks)
    if not combined.endswith(b"\n"):
        raise ValueError("submit frame closed before newline")
    if combined.count(b"\n") != 1:
        raise ValueError("submit protocol accepts exactly one frame")
    return combined


def send_submit_request(
    request: SubmitRequest,
    *,
    binding: PhasedSubmitBinding,
) -> SubmitReceipt:
    if type(request) is not SubmitRequest:
        raise TypeError("request must be an exact SubmitRequest")
    if type(binding) is not PhasedSubmitBinding:
        raise TypeError("binding must be an exact PhasedSubmitBinding")
    try:
        timeout = _remaining(binding.deadline)
    except TimeoutError as exc:
        raise PhasedSubmitProtocolClosedError(
            "whole-attempt deadline exhausted before submit"
        ) from exc
    connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        connection.settimeout(timeout)
        connection.connect(str(binding.socket_path))
        connection.settimeout(_remaining(binding.deadline))
        connection.sendall(_canonical(request.to_dict()))
        connection.shutdown(socket.SHUT_WR)
        receipt = receipt_from_dict(
            _decode_frame(
                _read_frame(connection, deadline=binding.deadline),
                field="submit receipt",
            )
        )
    except (OSError, RecursionError, TimeoutError, TypeError, ValueError) as exc:
        raise PhasedSubmitProtocolClosedError(
            "phased submit endpoint closed without a valid receipt"
        ) from exc
    finally:
        connection.close()
    if receipt.client_request_id != request.client_request_id:
        raise PhasedSubmitProtocolClosedError(
            "submit endpoint returned a mismatched request id"
        )
    if (
        receipt.attempt_scope_sha256 != request.attempt_scope_sha256
        or receipt.attempt_scope_sha256 != binding.attempt_scope_sha256
    ):
        raise PhasedSubmitProtocolClosedError(
            "submit endpoint returned a mismatched attempt scope"
        )
    return receipt


def submit_materialization(
    *,
    request_id: str,
    environ: Mapping[str, str] | None = None,
) -> SubmitReceipt:
    binding = decode_submit_binding(environ)
    return send_submit_request(
        SubmitRequest(
            attempt_scope_sha256=binding.attempt_scope_sha256,
            endpoint_instance_id=binding.endpoint_instance_id,
            binding_token=binding.binding_token,
            client_request_id=request_id,
            payload_sha256=_EMPTY_PAYLOAD_SHA256,
        ),
        binding=binding,
    )
