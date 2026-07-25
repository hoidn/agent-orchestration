"""Closed runtime records for cooperative provider peer groups."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
import hashlib
import math
from types import MappingProxyType
from typing import Any, Mapping, TypeAlias

from ...providers.interactive_terminal import (
    FailedCleanupProof,
    NaturalShutdownProof,
)
from .paths import PeerMemberPathPlan


PEER_PROTOCOL_SCHEMA_VERSION = "provider_peer_protocol.v1"
PEER_TERMINAL_EVIDENCE_SCHEMA_VERSION = (
    "provider_peer_group_terminal_evidence.v1"
)
MAX_PEER_MESSAGE_BYTES = 65_536


def _closed(
    value: Any,
    keys: frozenset[str],
    field: str,
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != keys:
        raise ValueError(
            f"{field} must be a closed object with keys {sorted(keys)}"
        )
    return value


def _nonempty(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field} must be a non-empty string")
    return value


def _positive_integer(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{field} must be a positive integer")
    return value


def _sha256(value: Any, field: str) -> str:
    raw = _nonempty(value, field)
    prefix = "sha256:"
    hexadecimal = raw[len(prefix) :] if raw.startswith(prefix) else ""
    if (
        len(hexadecimal) != 64
        or any(character not in "0123456789abcdef" for character in hexadecimal)
    ):
        raise ValueError(f"{field} must be a canonical sha256 digest")
    return raw


def _aware_timestamp(value: Any, field: str) -> str:
    raw = _nonempty(value, field)
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field} must include a timezone")
    return raw


def _deep_freeze(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Mapping):
        copied: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError("frozen result mappings require string keys")
            copied[key] = _deep_freeze(item)
        return MappingProxyType(copied)
    if isinstance(value, (list, tuple)):
        return tuple(_deep_freeze(item) for item in value)
    raise ValueError("frozen result value must be transportable data")


def _deep_thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _deep_thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_deep_thaw(item) for item in value]
    return value


@dataclass(frozen=True)
class PeerGroupVisitIdentity:
    run_id: str
    step_name: str
    node_id: str
    visit_count: int

    def __post_init__(self) -> None:
        _nonempty(self.run_id, "group_visit.run_id")
        _nonempty(self.step_name, "group_visit.step_name")
        _nonempty(self.node_id, "group_visit.node_id")
        _positive_integer(self.visit_count, "group_visit.visit_count")

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "step_name": self.step_name,
            "node_id": self.node_id,
            "visit_count": self.visit_count,
        }

    @classmethod
    def from_dict(cls, value: Any) -> "PeerGroupVisitIdentity":
        node = _closed(
            value,
            frozenset({"run_id", "step_name", "node_id", "visit_count"}),
            "group_visit",
        )
        return cls(
            run_id=_nonempty(node["run_id"], "group_visit.run_id"),
            step_name=_nonempty(
                node["step_name"],
                "group_visit.step_name",
            ),
            node_id=_nonempty(node["node_id"], "group_visit.node_id"),
            visit_count=_positive_integer(
                node["visit_count"],
                "group_visit.visit_count",
            ),
        )


@dataclass(frozen=True)
class PeerAttemptIdentity:
    member_id: str
    attempt_scope_key: str
    attempt_ordinal: int

    def __post_init__(self) -> None:
        _nonempty(self.member_id, "attempt.member_id")
        _nonempty(self.attempt_scope_key, "attempt.attempt_scope_key")
        _positive_integer(
            self.attempt_ordinal,
            "attempt.attempt_ordinal",
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "member_id": self.member_id,
            "attempt_scope_key": self.attempt_scope_key,
            "attempt_ordinal": self.attempt_ordinal,
        }

    @classmethod
    def from_dict(cls, value: Any) -> "PeerAttemptIdentity":
        node = _closed(
            value,
            frozenset(
                {"member_id", "attempt_scope_key", "attempt_ordinal"}
            ),
            "attempt",
        )
        return cls(
            member_id=_nonempty(node["member_id"], "attempt.member_id"),
            attempt_scope_key=_nonempty(
                node["attempt_scope_key"],
                "attempt.attempt_scope_key",
            ),
            attempt_ordinal=_positive_integer(
                node["attempt_ordinal"],
                "attempt.attempt_ordinal",
            ),
        )


@dataclass(frozen=True)
class PeerEndpointIdentity:
    """Ephemeral endpoint identity; private serialization only."""

    group_visit: PeerGroupVisitIdentity
    endpoint_instance_id: str

    def __post_init__(self) -> None:
        if not isinstance(self.group_visit, PeerGroupVisitIdentity):
            raise ValueError("endpoint.group_visit must be a visit identity")
        _nonempty(
            self.endpoint_instance_id,
            "endpoint.endpoint_instance_id",
        )

    def to_private_dict(self) -> dict[str, Any]:
        return {
            **self.group_visit.to_dict(),
            "endpoint_instance_id": self.endpoint_instance_id,
        }

    @classmethod
    def from_private_dict(cls, value: Any) -> "PeerEndpointIdentity":
        node = _closed(
            value,
            frozenset(
                {
                    "run_id",
                    "step_name",
                    "node_id",
                    "visit_count",
                    "endpoint_instance_id",
                }
            ),
            "endpoint",
        )
        return cls(
            group_visit=PeerGroupVisitIdentity.from_dict(
                {
                    key: node[key]
                    for key in (
                        "run_id",
                        "step_name",
                        "node_id",
                        "visit_count",
                    )
                }
            ),
            endpoint_instance_id=_nonempty(
                node["endpoint_instance_id"],
                "endpoint.endpoint_instance_id",
            ),
        )


@dataclass(frozen=True)
class PeerSenderBinding:
    """Ephemeral opaque sender resolution; private serialization only."""

    opaque_binding: str
    attempt: PeerAttemptIdentity
    endpoint_instance_id: str

    def __post_init__(self) -> None:
        _nonempty(self.opaque_binding, "sender_binding.opaque_binding")
        if not isinstance(self.attempt, PeerAttemptIdentity):
            raise ValueError(
                "sender_binding.attempt must be an attempt identity"
            )
        _nonempty(
            self.endpoint_instance_id,
            "sender_binding.endpoint_instance_id",
        )

    def to_private_dict(self) -> dict[str, Any]:
        return {
            "opaque_binding": self.opaque_binding,
            **self.attempt.to_dict(),
            "endpoint_instance_id": self.endpoint_instance_id,
        }

    @classmethod
    def from_private_dict(cls, value: Any) -> "PeerSenderBinding":
        node = _closed(
            value,
            frozenset(
                {
                    "opaque_binding",
                    "member_id",
                    "attempt_scope_key",
                    "attempt_ordinal",
                    "endpoint_instance_id",
                }
            ),
            "sender_binding",
        )
        return cls(
            opaque_binding=_nonempty(
                node["opaque_binding"],
                "sender_binding.opaque_binding",
            ),
            attempt=PeerAttemptIdentity.from_dict(
                {
                    key: node[key]
                    for key in (
                        "member_id",
                        "attempt_scope_key",
                        "attempt_ordinal",
                    )
                }
            ),
            endpoint_instance_id=_nonempty(
                node["endpoint_instance_id"],
                "sender_binding.endpoint_instance_id",
            ),
        )


class PeerMemberLifecycle(str, Enum):
    ALLOCATED = "ALLOCATED"
    STARTING = "STARTING"
    READY_WAITING = "READY_WAITING"
    ACTIVE = "ACTIVE"
    FINISH_REQUESTED = "FINISH_REQUESTED"
    CLOSING = "CLOSING"
    TERMINAL = "TERMINAL"
    FAILED = "FAILED"

    def can_transition_to(self, target: "PeerMemberLifecycle") -> bool:
        if not isinstance(target, PeerMemberLifecycle):
            return False
        if self in {self.TERMINAL, self.FAILED}:
            return False
        if target is self.FAILED:
            return True
        return {
            self.ALLOCATED: self.STARTING,
            self.STARTING: self.READY_WAITING,
            self.READY_WAITING: self.ACTIVE,
            self.ACTIVE: self.FINISH_REQUESTED,
            self.FINISH_REQUESTED: self.CLOSING,
            self.CLOSING: self.TERMINAL,
        }.get(self) is target


@dataclass(frozen=True)
class PeerMemberRuntimeBinding:
    """One exact member attempt and its precomputed runtime paths."""

    attempt: PeerAttemptIdentity
    timeout_sec: float
    paths: PeerMemberPathPlan

    def __post_init__(self) -> None:
        if not isinstance(self.attempt, PeerAttemptIdentity):
            raise ValueError("member binding attempt is invalid")
        if (
            isinstance(self.timeout_sec, bool)
            or not isinstance(self.timeout_sec, (int, float))
            or self.timeout_sec <= 0
            or not math.isfinite(self.timeout_sec)
        ):
            raise ValueError(
                "member binding timeout_sec must be finite and positive"
            )
        if not isinstance(self.paths, PeerMemberPathPlan):
            raise ValueError("member binding paths are invalid")
        if self.paths.member_id != self.attempt.member_id:
            raise ValueError(
                "member binding paths do not match the attempt member"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "attempt": self.attempt.to_dict(),
            "timeout_sec": self.timeout_sec,
            "paths": self.paths.to_dict(),
        }

    @classmethod
    def from_dict(cls, value: Any) -> "PeerMemberRuntimeBinding":
        node = _closed(
            value,
            frozenset({"attempt", "timeout_sec", "paths"}),
            "member_binding",
        )
        return cls(
            attempt=PeerAttemptIdentity.from_dict(node["attempt"]),
            timeout_sec=node["timeout_sec"],
            paths=PeerMemberPathPlan.from_dict(node["paths"]),
        )


@dataclass(frozen=True)
class PeerGroupRuntimeBinding:
    """Closed authored-order runtime binding, separate from executable IR."""

    visit: PeerGroupVisitIdentity
    members: tuple[PeerMemberRuntimeBinding, ...]
    messaging_policy: str
    max_steers: int

    def __post_init__(self) -> None:
        if not isinstance(self.visit, PeerGroupVisitIdentity):
            raise ValueError("group binding visit is invalid")
        if not isinstance(self.members, tuple):
            raise ValueError(
                "group binding members must be an authored-order tuple"
            )
        if not 2 <= len(self.members) <= 8:
            raise ValueError("group binding requires 2 through 8 members")
        if any(
            not isinstance(member, PeerMemberRuntimeBinding)
            for member in self.members
        ):
            raise ValueError("group binding members are invalid")
        member_ids = tuple(
            member.attempt.member_id for member in self.members
        )
        if len(set(member_ids)) != len(member_ids):
            raise ValueError("group binding member ids must be unique")
        if self.messaging_policy != "all_other_members":
            raise ValueError(
                "group binding messaging_policy is unsupported"
            )
        if (
            isinstance(self.max_steers, bool)
            or not isinstance(self.max_steers, int)
            or self.max_steers != 0
        ):
            raise ValueError("group binding max_steers must be zero")

    def to_dict(self) -> dict[str, Any]:
        return {
            "visit": self.visit.to_dict(),
            "members": [member.to_dict() for member in self.members],
            "messaging_policy": self.messaging_policy,
            "max_steers": self.max_steers,
        }

    @classmethod
    def from_dict(cls, value: Any) -> "PeerGroupRuntimeBinding":
        node = _closed(
            value,
            frozenset(
                {
                    "visit",
                    "members",
                    "messaging_policy",
                    "max_steers",
                }
            ),
            "group_binding",
        )
        raw_members = node["members"]
        if not isinstance(raw_members, list):
            raise ValueError("group binding members must be a list")
        return cls(
            visit=PeerGroupVisitIdentity.from_dict(node["visit"]),
            members=tuple(
                PeerMemberRuntimeBinding.from_dict(member)
                for member in raw_members
            ),
            messaging_policy=node["messaging_policy"],
            max_steers=node["max_steers"],
        )


def _request_header(
    schema_version: Any,
    request_id: Any,
    sender_binding: Any,
) -> tuple[str, str]:
    if schema_version != PEER_PROTOCOL_SCHEMA_VERSION:
        raise ValueError("peer request schema_version is unsupported")
    return (
        _nonempty(request_id, "peer_request.request_id"),
        _nonempty(sender_binding, "peer_request.sender_binding"),
    )


@dataclass(frozen=True)
class PeerReadyRequest:
    request_id: str
    sender_binding: str
    schema_version: str = PEER_PROTOCOL_SCHEMA_VERSION
    kind: str = "ready"

    def __post_init__(self) -> None:
        _request_header(
            self.schema_version,
            self.request_id,
            self.sender_binding,
        )
        if self.kind != "ready":
            raise ValueError("ready request kind is invalid")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "kind": self.kind,
            "request_id": self.request_id,
            "sender_binding": self.sender_binding,
        }


@dataclass(frozen=True)
class PeerSendRequest:
    request_id: str
    sender_binding: str
    target_binding: str
    message: str
    schema_version: str = PEER_PROTOCOL_SCHEMA_VERSION
    kind: str = "send"

    def __post_init__(self) -> None:
        _request_header(
            self.schema_version,
            self.request_id,
            self.sender_binding,
        )
        if self.kind != "send":
            raise ValueError("send request kind is invalid")
        _nonempty(self.target_binding, "peer_request.target_binding")
        message = _nonempty(self.message, "peer_request.message")
        try:
            encoded = message.encode("utf-8", errors="strict")
        except UnicodeEncodeError as exc:
            raise ValueError("peer request message must be valid UTF-8") from exc
        if len(encoded) > MAX_PEER_MESSAGE_BYTES:
            raise ValueError("peer request message exceeds 65,536 bytes")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "kind": self.kind,
            "request_id": self.request_id,
            "sender_binding": self.sender_binding,
            "target_binding": self.target_binding,
            "message": self.message,
        }


@dataclass(frozen=True)
class PeerAcknowledgeRequest:
    request_id: str
    sender_binding: str
    message_id: str
    schema_version: str = PEER_PROTOCOL_SCHEMA_VERSION
    kind: str = "ack"

    def __post_init__(self) -> None:
        _request_header(
            self.schema_version,
            self.request_id,
            self.sender_binding,
        )
        if self.kind != "ack":
            raise ValueError("ack request kind is invalid")
        _nonempty(self.message_id, "peer_request.message_id")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "kind": self.kind,
            "request_id": self.request_id,
            "sender_binding": self.sender_binding,
            "message_id": self.message_id,
        }


@dataclass(frozen=True)
class PeerFinishRequest:
    request_id: str
    sender_binding: str
    schema_version: str = PEER_PROTOCOL_SCHEMA_VERSION
    kind: str = "finish"

    def __post_init__(self) -> None:
        _request_header(
            self.schema_version,
            self.request_id,
            self.sender_binding,
        )
        if self.kind != "finish":
            raise ValueError("finish request kind is invalid")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "kind": self.kind,
            "request_id": self.request_id,
            "sender_binding": self.sender_binding,
        }


PeerRequest: TypeAlias = (
    PeerReadyRequest
    | PeerSendRequest
    | PeerAcknowledgeRequest
    | PeerFinishRequest
)


def peer_request_from_dict(value: Any) -> PeerRequest:
    if not isinstance(value, Mapping):
        raise ValueError("peer request must be an object")
    kind = value.get("kind")
    keys_by_kind = {
        "ready": frozenset(
            {"schema_version", "kind", "request_id", "sender_binding"}
        ),
        "send": frozenset(
            {
                "schema_version",
                "kind",
                "request_id",
                "sender_binding",
                "target_binding",
                "message",
            }
        ),
        "ack": frozenset(
            {
                "schema_version",
                "kind",
                "request_id",
                "sender_binding",
                "message_id",
            }
        ),
        "finish": frozenset(
            {"schema_version", "kind", "request_id", "sender_binding"}
        ),
    }
    if kind not in keys_by_kind:
        raise ValueError("peer request kind is unsupported")
    node = _closed(value, keys_by_kind[kind], "peer_request")
    common = {
        "schema_version": node["schema_version"],
        "request_id": node["request_id"],
        "sender_binding": node["sender_binding"],
        "kind": node["kind"],
    }
    if kind == "ready":
        return PeerReadyRequest(**common)
    if kind == "send":
        return PeerSendRequest(
            **common,
            target_binding=node["target_binding"],
            message=node["message"],
        )
    if kind == "ack":
        return PeerAcknowledgeRequest(
            **common,
            message_id=node["message_id"],
        )
    return PeerFinishRequest(**common)


@dataclass(frozen=True)
class PeerReadyReceipt:
    request_id: str
    schema_version: str = PEER_PROTOCOL_SCHEMA_VERSION
    kind: str = "ready"
    status: str = "active"

    def __post_init__(self) -> None:
        _receipt_header(self.schema_version, self.request_id)
        if (self.kind, self.status) != ("ready", "active"):
            raise ValueError("ready receipt is invalid")

    def to_dict(self) -> dict[str, Any]:
        return _receipt_dict(self, ("message_id", "pending_message_ids"))


@dataclass(frozen=True)
class PeerSendReceipt:
    request_id: str
    message_id: str
    schema_version: str = PEER_PROTOCOL_SCHEMA_VERSION
    kind: str = "send"
    status: str = "offered"

    def __post_init__(self) -> None:
        _receipt_header(self.schema_version, self.request_id)
        _nonempty(self.message_id, "peer_receipt.message_id")
        if (self.kind, self.status) != ("send", "offered"):
            raise ValueError("send receipt is invalid")

    def to_dict(self) -> dict[str, Any]:
        return {
            **_receipt_dict(self, ()),
            "message_id": self.message_id,
        }


@dataclass(frozen=True)
class PeerAcknowledgeReceipt:
    request_id: str
    message_id: str
    schema_version: str = PEER_PROTOCOL_SCHEMA_VERSION
    kind: str = "ack"
    status: str = "receiver_acknowledged"

    def __post_init__(self) -> None:
        _receipt_header(self.schema_version, self.request_id)
        _nonempty(self.message_id, "peer_receipt.message_id")
        if (self.kind, self.status) != (
            "ack",
            "receiver_acknowledged",
        ):
            raise ValueError("ack receipt is invalid")

    def to_dict(self) -> dict[str, Any]:
        return {
            **_receipt_dict(self, ()),
            "message_id": self.message_id,
        }


@dataclass(frozen=True)
class PeerFinishReceipt:
    request_id: str
    status: str
    pending_message_ids: tuple[str, ...] = ()
    schema_version: str = PEER_PROTOCOL_SCHEMA_VERSION
    kind: str = "finish"

    def __post_init__(self) -> None:
        _receipt_header(self.schema_version, self.request_id)
        if self.kind != "finish":
            raise ValueError("finish receipt kind is invalid")
        if not isinstance(self.pending_message_ids, tuple):
            raise ValueError(
                "finish receipt pending_message_ids must be a tuple"
            )
        pending = self.pending_message_ids
        if self.status == "pending_messages":
            if (
                not pending
                or any(
                    not isinstance(message_id, str) or not message_id
                    for message_id in pending
                )
                or len(set(pending)) != len(pending)
            ):
                raise ValueError(
                    "pending finish requires ordered unique message ids"
                )
        elif self.status == "close_offered":
            if pending:
                raise ValueError(
                    "close-offered finish forbids pending message ids"
                )
        else:
            raise ValueError("finish receipt status is invalid")

    @classmethod
    def pending(
        cls,
        request_id: str,
        message_ids: tuple[str, ...],
    ) -> "PeerFinishReceipt":
        return cls(
            request_id=request_id,
            status="pending_messages",
            pending_message_ids=message_ids,
        )

    @classmethod
    def close_offered(cls, request_id: str) -> "PeerFinishReceipt":
        return cls(request_id=request_id, status="close_offered")

    def to_dict(self) -> dict[str, Any]:
        result = _receipt_dict(self, ())
        if self.status == "pending_messages":
            result["pending_message_ids"] = list(self.pending_message_ids)
        return result


@dataclass(frozen=True)
class PeerFailureReceipt:
    request_kind: str
    request_id: str
    error_code: str
    retryable: bool
    schema_version: str = PEER_PROTOCOL_SCHEMA_VERSION
    kind: str = "failure"
    status: str = "rejected"

    def __post_init__(self) -> None:
        _receipt_header(self.schema_version, self.request_id)
        if self.kind != "failure" or self.status != "rejected":
            raise ValueError("failure receipt is invalid")
        if self.request_kind not in {"ready", "send", "ack", "finish"}:
            raise ValueError("failure receipt request_kind is invalid")
        _nonempty(self.error_code, "peer_receipt.error_code")
        if not isinstance(self.retryable, bool):
            raise ValueError("failure receipt retryable must be a boolean")

    def to_dict(self) -> dict[str, Any]:
        return {
            **_receipt_dict(self, ()),
            "request_kind": self.request_kind,
            "error_code": self.error_code,
            "retryable": self.retryable,
        }


PeerReceipt: TypeAlias = (
    PeerReadyReceipt
    | PeerSendReceipt
    | PeerAcknowledgeReceipt
    | PeerFinishReceipt
    | PeerFailureReceipt
)


def _receipt_header(schema_version: Any, request_id: Any) -> str:
    if schema_version != PEER_PROTOCOL_SCHEMA_VERSION:
        raise ValueError("peer receipt schema_version is unsupported")
    return _nonempty(request_id, "peer_receipt.request_id")


def _receipt_dict(value: Any, _ignored: tuple[str, ...]) -> dict[str, Any]:
    return {
        "schema_version": value.schema_version,
        "kind": value.kind,
        "request_id": value.request_id,
        "status": value.status,
    }


def peer_receipt_from_dict(value: Any) -> PeerReceipt:
    if not isinstance(value, Mapping):
        raise ValueError("peer receipt must be an object")
    kind = value.get("kind")
    status = value.get("status")
    base = {"schema_version", "kind", "request_id", "status"}
    if (kind, status) == ("ready", "active"):
        node = _closed(value, frozenset(base), "peer_receipt")
        return PeerReadyReceipt(
            request_id=node["request_id"],
            schema_version=node["schema_version"],
            kind=node["kind"],
            status=node["status"],
        )
    if (kind, status) == ("send", "offered"):
        node = _closed(
            value,
            frozenset(base | {"message_id"}),
            "peer_receipt",
        )
        return PeerSendReceipt(
            request_id=node["request_id"],
            message_id=node["message_id"],
            schema_version=node["schema_version"],
            kind=node["kind"],
            status=node["status"],
        )
    if (kind, status) == ("ack", "receiver_acknowledged"):
        node = _closed(
            value,
            frozenset(base | {"message_id"}),
            "peer_receipt",
        )
        return PeerAcknowledgeReceipt(
            request_id=node["request_id"],
            message_id=node["message_id"],
            schema_version=node["schema_version"],
            kind=node["kind"],
            status=node["status"],
        )
    if kind == "finish" and status in {
        "pending_messages",
        "close_offered",
    }:
        expected = base | (
            {"pending_message_ids"}
            if status == "pending_messages"
            else set()
        )
        node = _closed(value, frozenset(expected), "peer_receipt")
        raw_pending = node.get("pending_message_ids", [])
        if not isinstance(raw_pending, list):
            raise ValueError(
                "finish receipt pending_message_ids must be a list"
            )
        return PeerFinishReceipt(
            request_id=node["request_id"],
            status=node["status"],
            pending_message_ids=tuple(raw_pending),
            schema_version=node["schema_version"],
            kind=node["kind"],
        )
    if kind == "failure" and status == "rejected":
        node = _closed(
            value,
            frozenset(
                base
                | {"request_kind", "error_code", "retryable"}
            ),
            "peer_receipt",
        )
        return PeerFailureReceipt(
            request_kind=node["request_kind"],
            request_id=node["request_id"],
            error_code=node["error_code"],
            retryable=node["retryable"],
            schema_version=node["schema_version"],
            kind=node["kind"],
            status=node["status"],
        )
    raise ValueError("peer receipt variant is unsupported")


@dataclass(frozen=True)
class FrozenPeerMemberResult:
    attempt: PeerAttemptIdentity
    exact_bundle_bytes: bytes
    value: Any
    bundle_sha256: str

    def __post_init__(self) -> None:
        if not isinstance(self.attempt, PeerAttemptIdentity):
            raise ValueError("frozen result attempt is invalid")
        if not isinstance(self.exact_bundle_bytes, (bytes, bytearray)):
            raise ValueError("exact bundle must be bytes")
        copied = bytes(self.exact_bundle_bytes)
        expected_digest = (
            "sha256:" + hashlib.sha256(copied).hexdigest()
        )
        _sha256(self.bundle_sha256, "frozen_result.bundle_sha256")
        if self.bundle_sha256 != expected_digest:
            raise ValueError(
                "frozen result digest does not match exact bundle bytes"
            )
        object.__setattr__(self, "exact_bundle_bytes", copied)
        object.__setattr__(self, "value", _deep_freeze(self.value))

    @classmethod
    def create(
        cls,
        *,
        attempt: PeerAttemptIdentity,
        exact_bundle_bytes: bytes | bytearray,
        value: Any,
    ) -> "FrozenPeerMemberResult":
        if not isinstance(attempt, PeerAttemptIdentity):
            raise ValueError("frozen result attempt is invalid")
        if not isinstance(exact_bundle_bytes, (bytes, bytearray)):
            raise ValueError("exact bundle must be bytes")
        copied = bytes(exact_bundle_bytes)
        return cls(
            attempt=attempt,
            exact_bundle_bytes=copied,
            value=_deep_freeze(value),
            bundle_sha256=(
                "sha256:" + hashlib.sha256(copied).hexdigest()
            ),
        )


@dataclass(frozen=True)
class PeerLedgerCounts:
    recorded: int
    offered: int
    offer_failed: int
    receiver_acknowledged: int

    def __post_init__(self) -> None:
        for field in (
            "recorded",
            "offered",
            "offer_failed",
            "receiver_acknowledged",
        ):
            value = getattr(self, field)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"ledger counts {field} must be non-negative")

    def to_dict(self) -> dict[str, int]:
        return {
            "recorded": self.recorded,
            "offered": self.offered,
            "offer_failed": self.offer_failed,
            "receiver_acknowledged": self.receiver_acknowledged,
        }

    @classmethod
    def from_dict(cls, value: Any) -> "PeerLedgerCounts":
        node = _closed(
            value,
            frozenset(
                {
                    "recorded",
                    "offered",
                    "offer_failed",
                    "receiver_acknowledged",
                }
            ),
            "ledger.counts",
        )
        return cls(**node)


@dataclass(frozen=True)
class PeerLedgerSummary:
    receiver_attempt: PeerAttemptIdentity
    ledger_sha256: str
    row_count: int
    counts: PeerLedgerCounts

    def __post_init__(self) -> None:
        if not isinstance(self.receiver_attempt, PeerAttemptIdentity):
            raise ValueError("ledger summary receiver attempt is invalid")
        _sha256(self.ledger_sha256, "ledger.ledger_sha256")
        _positive_integer(self.row_count, "ledger.row_count")
        if not isinstance(self.counts, PeerLedgerCounts):
            raise ValueError("ledger summary counts are invalid")

    def to_dict(self) -> dict[str, Any]:
        return {
            "receiver_attempt": self.receiver_attempt.to_dict(),
            "ledger_sha256": self.ledger_sha256,
            "row_count": self.row_count,
            "counts": self.counts.to_dict(),
        }

    @classmethod
    def from_dict(cls, value: Any) -> "PeerLedgerSummary":
        node = _closed(
            value,
            frozenset(
                {
                    "receiver_attempt",
                    "ledger_sha256",
                    "row_count",
                    "counts",
                }
            ),
            "ledger",
        )
        return cls(
            receiver_attempt=PeerAttemptIdentity.from_dict(
                node["receiver_attempt"]
            ),
            ledger_sha256=_sha256(
                node["ledger_sha256"],
                "ledger.ledger_sha256",
            ),
            row_count=_positive_integer(
                node["row_count"],
                "ledger.row_count",
            ),
            counts=PeerLedgerCounts.from_dict(node["counts"]),
        )


@dataclass(frozen=True)
class PeerNaturalShutdownEvidence:
    disposition: str
    return_code: int
    pane_absent: bool
    server_absent: bool
    proof_complete: bool

    @classmethod
    def from_proof(
        cls,
        value: NaturalShutdownProof,
    ) -> "PeerNaturalShutdownEvidence":
        if not isinstance(value, NaturalShutdownProof):
            raise ValueError("natural shutdown proof is invalid")
        return cls(
            disposition=value.disposition,
            return_code=value.return_code,
            pane_absent=value.pane_absent,
            server_absent=value.server_absent,
            proof_complete=value.proof_complete,
        )

    def __post_init__(self) -> None:
        if self.disposition != "natural_exit":
            raise ValueError("natural shutdown disposition is invalid")
        if (
            isinstance(self.return_code, bool)
            or not isinstance(self.return_code, int)
        ):
            raise ValueError("natural shutdown return code is invalid")
        for field in ("pane_absent", "server_absent", "proof_complete"):
            if not isinstance(getattr(self, field), bool):
                raise ValueError(f"natural shutdown {field} must be boolean")

    def to_dict(self) -> dict[str, Any]:
        return {
            "disposition": self.disposition,
            "return_code": self.return_code,
            "pane_absent": self.pane_absent,
            "server_absent": self.server_absent,
            "proof_complete": self.proof_complete,
        }

    @classmethod
    def from_dict(cls, value: Any) -> "PeerNaturalShutdownEvidence":
        node = _closed(
            value,
            frozenset(
                {
                    "disposition",
                    "return_code",
                    "pane_absent",
                    "server_absent",
                    "proof_complete",
                }
            ),
            "natural_shutdown",
        )
        return cls(**node)


@dataclass(frozen=True)
class PeerFailedCleanupEvidence:
    disposition: str
    pane_absent: bool
    server_absent: bool
    cleanup_complete: bool
    error_code: str | None

    @classmethod
    def from_proof(
        cls,
        value: FailedCleanupProof,
    ) -> "PeerFailedCleanupEvidence":
        if not isinstance(value, FailedCleanupProof):
            raise ValueError("failed cleanup proof is invalid")
        return cls(
            disposition=value.disposition,
            pane_absent=value.pane_absent,
            server_absent=value.server_absent,
            cleanup_complete=value.cleanup_complete,
            error_code=value.error_code,
        )

    def __post_init__(self) -> None:
        if self.disposition != "failed_cleanup":
            raise ValueError("failed cleanup disposition is invalid")
        for field in ("pane_absent", "server_absent", "cleanup_complete"):
            if not isinstance(getattr(self, field), bool):
                raise ValueError(f"failed cleanup {field} must be boolean")
        if self.error_code is not None:
            _nonempty(self.error_code, "failed_cleanup.error_code")

    def to_dict(self) -> dict[str, Any]:
        return {
            "disposition": self.disposition,
            "pane_absent": self.pane_absent,
            "server_absent": self.server_absent,
            "cleanup_complete": self.cleanup_complete,
            "error_code": self.error_code,
        }

    @classmethod
    def from_dict(cls, value: Any) -> "PeerFailedCleanupEvidence":
        node = _closed(
            value,
            frozenset(
                {
                    "disposition",
                    "pane_absent",
                    "server_absent",
                    "cleanup_complete",
                    "error_code",
                }
            ),
            "failed_cleanup",
        )
        return cls(**node)


@dataclass(frozen=True)
class PeerMemberTerminalEvidence:
    attempt: PeerAttemptIdentity
    lifecycle: PeerMemberLifecycle
    ledger: PeerLedgerSummary | None
    frozen_bundle_sha256: str | None
    natural_shutdown: (
        PeerNaturalShutdownEvidence | NaturalShutdownProof | None
    )
    failed_cleanup: PeerFailedCleanupEvidence | FailedCleanupProof | None

    def __post_init__(self) -> None:
        if not isinstance(self.attempt, PeerAttemptIdentity):
            raise ValueError("member evidence attempt is invalid")
        if not isinstance(self.lifecycle, PeerMemberLifecycle):
            raise ValueError("member evidence lifecycle is invalid")
        if isinstance(self.natural_shutdown, NaturalShutdownProof):
            object.__setattr__(
                self,
                "natural_shutdown",
                PeerNaturalShutdownEvidence.from_proof(
                    self.natural_shutdown
                ),
            )
        if isinstance(self.failed_cleanup, FailedCleanupProof):
            object.__setattr__(
                self,
                "failed_cleanup",
                PeerFailedCleanupEvidence.from_proof(
                    self.failed_cleanup
                ),
            )
        if (
            self.natural_shutdown is not None
            and not isinstance(
                self.natural_shutdown,
                PeerNaturalShutdownEvidence,
            )
        ):
            raise ValueError("member natural-shutdown evidence is invalid")
        if (
            self.failed_cleanup is not None
            and not isinstance(
                self.failed_cleanup,
                PeerFailedCleanupEvidence,
            )
        ):
            raise ValueError("member failed-cleanup evidence is invalid")
        if self.ledger is not None:
            if not isinstance(self.ledger, PeerLedgerSummary):
                raise ValueError("member evidence ledger is invalid")
            if self.ledger.receiver_attempt != self.attempt:
                raise ValueError(
                    "member evidence ledger receiver does not match attempt"
                )
        if self.frozen_bundle_sha256 is not None:
            _sha256(
                self.frozen_bundle_sha256,
                "member_evidence.frozen_bundle_sha256",
            )
        if self.lifecycle is PeerMemberLifecycle.TERMINAL:
            natural = self.natural_shutdown
            if (
                self.ledger is None
                or self.frozen_bundle_sha256 is None
                or not isinstance(
                    natural,
                    PeerNaturalShutdownEvidence,
                )
                or natural.return_code != 0
                or natural.proof_complete is not True
                or natural.pane_absent is not True
                or natural.server_absent is not True
                or self.failed_cleanup is not None
            ):
                raise ValueError(
                    "terminal member evidence requires a complete natural exit"
                )
        elif self.lifecycle is PeerMemberLifecycle.FAILED:
            if self.frozen_bundle_sha256 is not None:
                raise ValueError(
                    "failed member evidence forbids a frozen bundle digest"
                )
        else:
            raise ValueError(
                "terminal evidence member lifecycle must be TERMINAL or FAILED"
            )

    def to_dict(self) -> dict[str, Any]:
        natural = self.natural_shutdown
        cleanup = self.failed_cleanup
        if natural is not None and not isinstance(
            natural,
            PeerNaturalShutdownEvidence,
        ):
            raise RuntimeError("member natural-shutdown evidence is invalid")
        if cleanup is not None and not isinstance(
            cleanup,
            PeerFailedCleanupEvidence,
        ):
            raise RuntimeError("member failed-cleanup evidence is invalid")
        return {
            "attempt": self.attempt.to_dict(),
            "lifecycle": self.lifecycle.value,
            "ledger": None if self.ledger is None else self.ledger.to_dict(),
            "frozen_bundle_sha256": self.frozen_bundle_sha256,
            "natural_shutdown": (
                None if natural is None else natural.to_dict()
            ),
            "failed_cleanup": (
                None if cleanup is None else cleanup.to_dict()
            ),
        }

    @classmethod
    def from_dict(cls, value: Any) -> "PeerMemberTerminalEvidence":
        node = _closed(
            value,
            frozenset(
                {
                    "attempt",
                    "lifecycle",
                    "ledger",
                    "frozen_bundle_sha256",
                    "natural_shutdown",
                    "failed_cleanup",
                }
            ),
            "member_evidence",
        )
        try:
            lifecycle = PeerMemberLifecycle(node["lifecycle"])
        except (TypeError, ValueError) as exc:
            raise ValueError(
                "member evidence lifecycle is invalid"
            ) from exc
        return cls(
            attempt=PeerAttemptIdentity.from_dict(node["attempt"]),
            lifecycle=lifecycle,
            ledger=(
                None
                if node["ledger"] is None
                else PeerLedgerSummary.from_dict(node["ledger"])
            ),
            frozen_bundle_sha256=node["frozen_bundle_sha256"],
            natural_shutdown=(
                None
                if node["natural_shutdown"] is None
                else PeerNaturalShutdownEvidence.from_dict(
                    node["natural_shutdown"]
                )
            ),
            failed_cleanup=(
                None
                if node["failed_cleanup"] is None
                else PeerFailedCleanupEvidence.from_dict(
                    node["failed_cleanup"]
                )
            ),
        )


@dataclass(frozen=True)
class PeerGroupTerminalEvidence:
    outcome: str
    group_visit: PeerGroupVisitIdentity
    members: tuple[PeerMemberTerminalEvidence, ...]
    endpoint_drained: bool
    endpoint_closed: bool
    endpoint_workers_joined: bool
    settlement_sha256: str | None
    failure: Mapping[str, str] | None
    terminal_at: str
    schema_version: str = PEER_TERMINAL_EVIDENCE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != PEER_TERMINAL_EVIDENCE_SCHEMA_VERSION:
            raise ValueError("terminal evidence schema_version is unsupported")
        if self.outcome not in {"completed", "failed"}:
            raise ValueError("terminal evidence outcome is invalid")
        if not isinstance(self.group_visit, PeerGroupVisitIdentity):
            raise ValueError("terminal evidence group_visit is invalid")
        members = tuple(self.members)
        object.__setattr__(self, "members", members)
        if not 2 <= len(members) <= 8:
            raise ValueError("terminal evidence requires 2 through 8 members")
        if (
            any(
                not isinstance(member, PeerMemberTerminalEvidence)
                for member in members
            )
            or len({member.attempt.member_id for member in members})
            != len(members)
        ):
            raise ValueError("terminal evidence members are invalid")
        for field in (
            "endpoint_drained",
            "endpoint_closed",
            "endpoint_workers_joined",
        ):
            if not isinstance(getattr(self, field), bool):
                raise ValueError(f"terminal evidence {field} must be boolean")
        _aware_timestamp(self.terminal_at, "terminal_evidence.terminal_at")

        if self.outcome == "completed":
            if (
                not self.endpoint_drained
                or not self.endpoint_closed
                or not self.endpoint_workers_joined
                or any(
                    member.lifecycle is not PeerMemberLifecycle.TERMINAL
                    for member in members
                )
                or self.failure is not None
                or self.settlement_sha256 is None
            ):
                raise ValueError(
                    "completed terminal evidence is structurally incomplete"
                )
            _sha256(
                self.settlement_sha256,
                "terminal_evidence.settlement_sha256",
            )
        else:
            if self.settlement_sha256 is not None:
                raise ValueError(
                    "failed terminal evidence forbids a settlement digest"
                )
            failure = _closed(
                self.failure,
                frozenset({"code", "message"}),
                "terminal_evidence.failure",
            )
            frozen_failure = MappingProxyType(
                {
                    "code": _nonempty(
                        failure["code"],
                        "terminal_evidence.failure.code",
                    ),
                    "message": _nonempty(
                        failure["message"],
                        "terminal_evidence.failure.message",
                    ),
                }
            )
            object.__setattr__(self, "failure", frozen_failure)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "outcome": self.outcome,
            "group_visit": self.group_visit.to_dict(),
            "members": [member.to_dict() for member in self.members],
            "endpoint_drained": self.endpoint_drained,
            "endpoint_closed": self.endpoint_closed,
            "endpoint_workers_joined": self.endpoint_workers_joined,
            "settlement_sha256": self.settlement_sha256,
            "failure": (
                None if self.failure is None else dict(self.failure)
            ),
            "terminal_at": self.terminal_at,
        }

    @classmethod
    def from_dict(cls, value: Any) -> "PeerGroupTerminalEvidence":
        node = _closed(
            value,
            frozenset(
                {
                    "schema_version",
                    "outcome",
                    "group_visit",
                    "members",
                    "endpoint_drained",
                    "endpoint_closed",
                    "endpoint_workers_joined",
                    "settlement_sha256",
                    "failure",
                    "terminal_at",
                }
            ),
            "terminal_evidence",
        )
        raw_members = node["members"]
        if not isinstance(raw_members, list):
            raise ValueError("terminal evidence members must be a list")
        return cls(
            schema_version=node["schema_version"],
            outcome=node["outcome"],
            group_visit=PeerGroupVisitIdentity.from_dict(
                node["group_visit"]
            ),
            members=tuple(
                PeerMemberTerminalEvidence.from_dict(member)
                for member in raw_members
            ),
            endpoint_drained=node["endpoint_drained"],
            endpoint_closed=node["endpoint_closed"],
            endpoint_workers_joined=node["endpoint_workers_joined"],
            settlement_sha256=node["settlement_sha256"],
            failure=node["failure"],
            terminal_at=node["terminal_at"],
        )
