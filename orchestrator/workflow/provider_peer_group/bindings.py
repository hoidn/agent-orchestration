"""Immutable workflow bindings for the provider peer-group coordinator."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
from typing import Any, Mapping, Protocol, runtime_checkable

from ...providers.interactive_terminal import (
    CloseOfferReceipt,
    FailedCleanupProof,
    InteractiveMemberHandle,
    InteractiveMemberInvocation,
    NaturalShutdownProof,
    OfferReceipt,
)
from .models import (
    MAX_PEER_MESSAGE_BYTES,
    FrozenPeerMemberResult,
    PeerEndpointIdentity,
    PeerGroupRuntimeBinding,
    PeerGroupTerminalEvidence,
    PeerMemberRuntimeBinding,
    PeerSenderBinding,
)
from .paths import (
    RealizedPeerGroupPaths,
    RealizedPeerMemberPaths,
    derive_provider_peer_group_paths,
    realize_provider_peer_group_paths,
)


PEER_DELIVERY_FRAME_HEADER = "ORCHESTRATOR_PROVIDER_PEER_MESSAGE_V1"


def _nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field} must be a non-empty string")
    return value


def _header_value(value: object, *, field: str) -> str:
    text = _nonempty(value, field=field)
    if "\r" in text or "\n" in text:
        raise ValueError(f"{field} must fit on one header line")
    return text


def _sha256(value: object, *, field: str) -> str:
    text = _nonempty(value, field=field)
    hexadecimal = text[7:] if text.startswith("sha256:") else ""
    if (
        len(hexadecimal) != 64
        or any(character not in "0123456789abcdef" for character in hexadecimal)
    ):
        raise ValueError(f"{field} must be a canonical sha256 digest")
    return text


@dataclass(frozen=True, slots=True)
class PeerDeliveryFrame:
    """Compiler-owned framing around one otherwise-verbatim peer message."""

    message_id: str
    sender_member_id: str
    content: str

    def __post_init__(self) -> None:
        _header_value(self.message_id, field="delivery_frame.message_id")
        _header_value(
            self.sender_member_id,
            field="delivery_frame.sender_member_id",
        )
        content = _nonempty(self.content, field="delivery_frame.content")
        try:
            encoded = content.encode("utf-8", errors="strict")
        except UnicodeEncodeError as exc:
            raise ValueError(
                "delivery_frame.content must be valid UTF-8"
            ) from exc
        if len(encoded) > MAX_PEER_MESSAGE_BYTES:
            raise ValueError(
                "delivery_frame.content exceeds 65,536 bytes"
            )

    def render(self) -> str:
        return (
            f"{PEER_DELIVERY_FRAME_HEADER}\n"
            f"message_id: {self.message_id}\n"
            f"sender_member_id: {self.sender_member_id}\n\n"
            f"{self.content}"
        )

    def render_bytes(self) -> bytes:
        return self.render().encode("utf-8", errors="strict")

    @property
    def rendered_byte_count(self) -> int:
        return len(self.render_bytes())

    @property
    def rendered_sha256(self) -> str:
        return "sha256:" + hashlib.sha256(self.render_bytes()).hexdigest()


@dataclass(frozen=True, slots=True)
class PeerMemberAllocation:
    """One fully allocated member without mutable adapter resources."""

    runtime: PeerMemberRuntimeBinding
    realized_paths: RealizedPeerMemberPaths
    sender: PeerSenderBinding
    prompt_snapshot_sha256: str
    invocation: InteractiveMemberInvocation

    def __post_init__(self) -> None:
        if not isinstance(self.runtime, PeerMemberRuntimeBinding):
            raise TypeError("member allocation runtime binding is invalid")
        if not isinstance(self.realized_paths, RealizedPeerMemberPaths):
            raise TypeError("member allocation realized paths are invalid")
        if not isinstance(self.sender, PeerSenderBinding):
            raise TypeError("member allocation sender binding is invalid")
        if not isinstance(self.invocation, InteractiveMemberInvocation):
            raise TypeError("member allocation invocation is invalid")
        _sha256(
            self.prompt_snapshot_sha256,
            field="member_allocation.prompt_snapshot_sha256",
        )

        attempt = self.runtime.attempt
        if self.sender.attempt != attempt:
            raise ValueError("member allocation sender attempt does not match")
        if (
            self.realized_paths.member_id != attempt.member_id
            or self.realized_paths.attempt_ordinal
            != attempt.attempt_ordinal
        ):
            raise ValueError("member allocation realized paths do not match")
        if (
            self.invocation.member_id != attempt.member_id
            or self.invocation.attempt_scope_key
            != attempt.attempt_scope_key
            or self.invocation.attempt_ordinal
            != attempt.attempt_ordinal
        ):
            raise ValueError("member allocation invocation does not match")


@dataclass(frozen=True, slots=True)
class PeerGroupAllocation:
    """Closed authored-order allocation for one exact group visit."""

    runtime: PeerGroupRuntimeBinding
    realized_paths: RealizedPeerGroupPaths
    endpoint: PeerEndpointIdentity
    endpoint_socket_path: Path
    members: tuple[PeerMemberAllocation, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.runtime, PeerGroupRuntimeBinding):
            raise TypeError("group allocation runtime binding is invalid")
        if not isinstance(self.realized_paths, RealizedPeerGroupPaths):
            raise TypeError("group allocation realized paths are invalid")
        if not isinstance(self.endpoint, PeerEndpointIdentity):
            raise TypeError("group allocation endpoint identity is invalid")
        if (
            not isinstance(self.endpoint_socket_path, Path)
            or not self.endpoint_socket_path.is_absolute()
            or ".." in self.endpoint_socket_path.parts
        ):
            raise ValueError(
                "group allocation endpoint_socket_path must be absolute"
            )
        if not isinstance(self.members, tuple) or any(
            not isinstance(member, PeerMemberAllocation)
            for member in self.members
        ):
            raise TypeError(
                "group allocation members must be an authored-order tuple"
            )
        if self.endpoint.group_visit != self.runtime.visit:
            raise ValueError("group allocation endpoint visit does not match")
        if len(self.members) != len(self.runtime.members):
            raise ValueError("group allocation member count does not match")

        runtime_ids = tuple(
            member.attempt.member_id for member in self.runtime.members
        )
        expected_plan = derive_provider_peer_group_paths(
            node_id=self.runtime.visit.node_id,
            member_ids=runtime_ids,
        )
        if tuple(member.paths for member in self.runtime.members) != (
            expected_plan.members
        ):
            raise ValueError("group allocation runtime paths do not match")
        expected_paths = realize_provider_peer_group_paths(
            run_root=self.realized_paths.visit_root.parents[3],
            plan=expected_plan,
            visit_count=self.runtime.visit.visit_count,
            attempt_ordinals={
                member.attempt.member_id: member.attempt.attempt_ordinal
                for member in self.runtime.members
            },
        )
        if self.realized_paths != expected_paths:
            raise ValueError("group allocation realized path set does not match")
        if tuple(member.runtime for member in self.members) != (
            self.runtime.members
        ) or tuple(member.realized_paths for member in self.members) != (
            self.realized_paths.members
        ):
            raise ValueError(
                "group allocation members do not preserve authored order"
            )
        if any(
            member.sender.endpoint_instance_id
            != self.endpoint.endpoint_instance_id
            for member in self.members
        ):
            raise ValueError("group allocation sender endpoint does not match")
        for values, field in (
            (
                tuple(member.sender.opaque_binding for member in self.members),
                "sender bindings",
            ),
            (
                tuple(member.invocation.invocation_id for member in self.members),
                "invocation ids",
            ),
            (
                tuple(
                    member.runtime.attempt.attempt_scope_key
                    for member in self.members
                ),
                "attempt scope keys",
            ),
        ):
            if len(set(values)) != len(values):
                raise ValueError(f"group allocation {field} must be unique")
        if self.endpoint_socket_path in self.realized_paths.leaf_paths():
            raise ValueError("group allocation endpoint collides with a leaf")


@runtime_checkable
class PeerInteractiveAdapter(Protocol):
    """The exact provider-neutral interactive operations used by a group."""

    def start(
        self, invocation: InteractiveMemberInvocation
    ) -> InteractiveMemberHandle: ...

    def offer(
        self, handle: InteractiveMemberHandle, literal_message: str
    ) -> OfferReceipt: ...

    def offer_close(
        self, handle: InteractiveMemberHandle
    ) -> CloseOfferReceipt: ...

    def join(
        self, handle: InteractiveMemberHandle, deadline: float
    ) -> NaturalShutdownProof: ...

    def abort(
        self, handle: InteractiveMemberHandle, deadline: float
    ) -> FailedCleanupProof: ...


class ProviderPeerGroupCoordinatorBindings(Protocol):
    """Workflow-owned operations invoked only by the serial coordinator."""

    def assert_current_step(self) -> None: ...

    def allocate_group(self) -> PeerGroupAllocation: ...

    def create_adapter(
        self, member: PeerMemberAllocation
    ) -> PeerInteractiveAdapter: ...

    def validate_member_bundle(
        self, member: PeerMemberAllocation
    ) -> FrozenPeerMemberResult: ...

    def evaluate_settlement(
        self, *, resolved_bindings: Mapping[str, Any]
    ) -> Any: ...

    def validate_settlement(self, *, value: Any) -> Any: ...

    def finalize_success(
        self,
        *,
        settlement_value: Any,
        evidence: PeerGroupTerminalEvidence,
    ) -> dict[str, Any]: ...

    def finalize_failure(
        self,
        *,
        evidence: PeerGroupTerminalEvidence,
    ) -> dict[str, Any]: ...


__all__ = [
    "PEER_DELIVERY_FRAME_HEADER",
    "PeerDeliveryFrame",
    "PeerGroupAllocation",
    "PeerInteractiveAdapter",
    "PeerMemberAllocation",
    "ProviderPeerGroupCoordinatorBindings",
]
