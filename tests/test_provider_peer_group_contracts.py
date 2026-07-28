"""Closed contracts, paths, and ledgers for provider peer groups."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import datetime, timezone
import hashlib
import inspect
import json
from pathlib import Path
from types import MappingProxyType

import pytest

from orchestrator.providers.interactive_terminal import (
    FailedCleanupProof,
    NaturalShutdownProof,
)
from orchestrator.workflow.provider_peer_group.bindings import (
    PeerInteractiveAdapter,
)
from orchestrator.workflow.provider_peer_group.ledger import (
    PeerMessageLedger,
    inspect_peer_message_ledger,
)
from orchestrator.workflow.provider_peer_group.models import (
    FrozenPeerMemberResult,
    PeerAcknowledgeReceipt,
    PeerAttemptIdentity,
    PeerEndpointIdentity,
    PeerFailureReceipt,
    PeerFinishReceipt,
    PeerGroupTerminalEvidence,
    PeerGroupRuntimeBinding,
    PeerGroupVisitIdentity,
    PeerMemberLifecycle,
    PeerMemberRuntimeBinding,
    PeerMemberTerminalEvidence,
    PeerReadyReceipt,
    PeerSendReceipt,
    PeerSenderBinding,
    peer_receipt_from_dict,
    peer_request_from_dict,
)
from orchestrator.workflow.provider_peer_group.paths import (
    PeerGroupPathPlan,
    derive_provider_peer_group_paths,
    preflight_provider_peer_group_paths,
    realize_provider_peer_group_paths,
)


def test_peer_interactive_adapter_deadline_contract_is_explicit() -> None:
    for operation in ("start", "offer", "offer_close"):
        deadline = inspect.signature(
            getattr(PeerInteractiveAdapter, operation)
        ).parameters.get("deadline")
        assert deadline is not None
        assert deadline.kind is inspect.Parameter.KEYWORD_ONLY

    for operation in ("join", "abort"):
        deadline = inspect.signature(
            getattr(PeerInteractiveAdapter, operation)
        ).parameters.get("deadline")
        assert deadline is not None
        assert deadline.kind is inspect.Parameter.POSITIONAL_OR_KEYWORD


def _visit() -> PeerGroupVisitIdentity:
    return PeerGroupVisitIdentity(
        run_id="run-1",
        step_name="peer-step",
        node_id="node-1",
        visit_count=1,
    )


def _attempt(
    member_id: str = "writer",
    ordinal: int = 1,
) -> PeerAttemptIdentity:
    return PeerAttemptIdentity(
        member_id=member_id,
        attempt_scope_key=f"scope-{member_id}",
        attempt_ordinal=ordinal,
    )


class _Clock:
    def __init__(self) -> None:
        self.second = 0

    def __call__(self) -> datetime:
        self.second += 1
        return datetime(
            2026,
            7,
            24,
            12,
            0,
            self.second,
            tzinfo=timezone.utc,
        )


def _record_message(
    ledger: PeerMessageLedger,
    *,
    message_id: str = "message-1",
    request_id: str = "request-1",
    content: str = "hello\nλ",
) -> str:
    return ledger.append_recorded(
        coordinator_sequence=1,
        request_id=request_id,
        message_id=message_id,
        sender_attempt=_attempt("reviewer"),
        content=content,
    )


def _complete_ledger(
    tmp_path: Path,
    *,
    receiver: PeerAttemptIdentity | None = None,
) -> tuple[PeerMessageLedger, str]:
    receiver_attempt = receiver or _attempt()
    ledger = PeerMessageLedger.create(
        tmp_path / "injected-messages.jsonl",
        group_visit=_visit(),
        receiver_attempt=receiver_attempt,
        clock=_Clock(),
    )
    digest = _record_message(ledger)
    ledger.append_offered(
        message_id="message-1",
        adapter_instance_id="adapter-1",
        handle_id="handle-1",
        byte_count=len("hello\nλ".encode("utf-8")),
        content_sha256=digest,
    )
    ledger.append_receiver_acknowledged(
        request_id="ack-request-1",
        message_id="message-1",
        receiver_attempt=receiver_attempt,
    )
    return ledger, digest


def test_visit_and_attempt_identities_are_closed_and_immutable() -> None:
    visit = _visit()
    attempt = _attempt()

    assert PeerGroupVisitIdentity.from_dict(visit.to_dict()) == visit
    assert PeerAttemptIdentity.from_dict(attempt.to_dict()) == attempt
    assert set(visit.to_dict()) == {
        "run_id",
        "step_name",
        "node_id",
        "visit_count",
    }
    assert set(attempt.to_dict()) == {
        "member_id",
        "attempt_scope_key",
        "attempt_ordinal",
    }
    with pytest.raises(FrozenInstanceError):
        visit.visit_count = 2  # type: ignore[misc]
    with pytest.raises(ValueError):
        PeerGroupVisitIdentity.from_dict(
            {**visit.to_dict(), "endpoint_instance_id": "not-persistent"}
        )
    with pytest.raises(ValueError):
        PeerAttemptIdentity(
            member_id="writer",
            attempt_scope_key="scope",
            attempt_ordinal=True,  # type: ignore[arg-type]
        )


def test_endpoint_and_sender_bindings_are_explicit_runtime_only_records() -> None:
    endpoint = PeerEndpointIdentity(
        group_visit=_visit(),
        endpoint_instance_id="endpoint-1",
    )
    sender = PeerSenderBinding(
        opaque_binding="opaque-1",
        attempt=_attempt(),
        endpoint_instance_id="endpoint-1",
    )

    assert PeerEndpointIdentity.from_private_dict(
        endpoint.to_private_dict()
    ) == endpoint
    assert PeerSenderBinding.from_private_dict(
        sender.to_private_dict()
    ) == sender
    assert "endpoint_instance_id" in endpoint.to_private_dict()
    assert "opaque_binding" in sender.to_private_dict()


def test_member_lifecycle_uses_only_the_designed_transition_table() -> None:
    assert tuple(state.value for state in PeerMemberLifecycle) == (
        "ALLOCATED",
        "STARTING",
        "READY_WAITING",
        "ACTIVE",
        "FINISH_REQUESTED",
        "CLOSING",
        "TERMINAL",
        "FAILED",
    )
    assert PeerMemberLifecycle.ALLOCATED.can_transition_to(
        PeerMemberLifecycle.STARTING
    )
    assert PeerMemberLifecycle.ACTIVE.can_transition_to(
        PeerMemberLifecycle.FINISH_REQUESTED
    )
    assert PeerMemberLifecycle.ACTIVE.can_transition_to(
        PeerMemberLifecycle.FAILED
    )
    assert not PeerMemberLifecycle.ACTIVE.can_transition_to(
        PeerMemberLifecycle.TERMINAL
    )
    assert not PeerMemberLifecycle.TERMINAL.can_transition_to(
        PeerMemberLifecycle.FAILED
    )


def test_runtime_group_and_member_bindings_are_closed_and_authored_ordered() -> None:
    path_plan = derive_provider_peer_group_paths(
        node_id="node",
        member_ids=("writer", "reviewer"),
    )
    writer = PeerMemberRuntimeBinding(
        attempt=_attempt(),
        timeout_sec=30.0,
        paths=path_plan.members[0],
    )
    reviewer = PeerMemberRuntimeBinding(
        attempt=_attempt("reviewer"),
        timeout_sec=45,
        paths=path_plan.members[1],
    )
    group = PeerGroupRuntimeBinding(
        visit=_visit(),
        members=(writer, reviewer),
        messaging_policy="all_other_members",
        max_steers=0,
    )

    assert PeerGroupRuntimeBinding.from_dict(group.to_dict()) == group
    assert tuple(
        member.attempt.member_id for member in group.members
    ) == ("writer", "reviewer")
    assert set(group.to_dict()) == {
        "visit",
        "members",
        "messaging_policy",
        "max_steers",
    }
    assert set(writer.to_dict()) == {"attempt", "timeout_sec", "paths"}


def test_runtime_bindings_reject_wrong_group_shape() -> None:
    path_plan = derive_provider_peer_group_paths(
        node_id="node",
        member_ids=("writer", "reviewer"),
    )
    writer = PeerMemberRuntimeBinding(
        attempt=_attempt(),
        timeout_sec=30,
        paths=path_plan.members[0],
    )
    with pytest.raises(ValueError):
        PeerGroupRuntimeBinding(
            visit=_visit(),
            members=(writer,),
            messaging_policy="all_other_members",
            max_steers=0,
        )
    with pytest.raises(ValueError):
        PeerGroupRuntimeBinding(
            visit=_visit(),
            members=(writer, writer),
            messaging_policy="all_other_members",
            max_steers=0,
        )
    reviewer = PeerMemberRuntimeBinding(
        attempt=_attempt("reviewer"),
        timeout_sec=30,
        paths=path_plan.members[1],
    )
    with pytest.raises(ValueError):
        PeerGroupRuntimeBinding(
            visit=_visit(),
            members=(writer, reviewer),
            messaging_policy="directed",
            max_steers=0,
        )
    with pytest.raises(ValueError):
        PeerGroupRuntimeBinding(
            visit=_visit(),
            members=(writer, reviewer),
            messaging_policy="all_other_members",
            max_steers=1,
        )


@pytest.mark.parametrize(
    "payload",
    (
        {
            "schema_version": "provider_peer_protocol.v1",
            "kind": "ready",
            "request_id": "request-1",
            "sender_binding": "opaque-1",
        },
        {
            "schema_version": "provider_peer_protocol.v1",
            "kind": "send",
            "request_id": "request-2",
            "sender_binding": "opaque-1",
            "target_binding": "writer",
            "message": "first\nλ",
        },
        {
            "schema_version": "provider_peer_protocol.v1",
            "kind": "ack",
            "request_id": "request-3",
            "sender_binding": "opaque-1",
            "message_id": "message-1",
        },
        {
            "schema_version": "provider_peer_protocol.v1",
            "kind": "finish",
            "request_id": "request-4",
            "sender_binding": "opaque-1",
        },
    ),
)
def test_peer_request_union_round_trips_exact_closed_variants(
    payload: dict[str, object],
) -> None:
    request = peer_request_from_dict(payload)

    assert request.to_dict() == payload
    with pytest.raises(ValueError):
        peer_request_from_dict({**payload, "extra": "rejected"})


def test_send_request_preserves_utf8_boundary_and_rejects_oversize() -> None:
    payload = {
        "schema_version": "provider_peer_protocol.v1",
        "kind": "send",
        "request_id": "request-1",
        "sender_binding": "opaque-1",
        "target_binding": "writer",
        "message": "λ" * 32_768,
    }

    assert peer_request_from_dict(payload).to_dict() == payload
    with pytest.raises(ValueError, match="65,536"):
        peer_request_from_dict(
            {**payload, "message": ("λ" * 32_768) + "x"}
        )
    with pytest.raises(ValueError):
        peer_request_from_dict({**payload, "message": ""})
    with pytest.raises(ValueError):
        peer_request_from_dict({**payload, "message": "\ud800"})


@pytest.mark.parametrize(
    "receipt",
    (
        PeerReadyReceipt("request-1"),
        PeerSendReceipt("request-2", "message-1"),
        PeerAcknowledgeReceipt("request-3", "message-1"),
        PeerFinishReceipt.pending(
            "request-4",
            ("message-1", "message-2"),
        ),
        PeerFinishReceipt.close_offered("request-5"),
        PeerFailureReceipt(
            request_kind="send",
            request_id="request-6",
            error_code="target_not_active",
            retryable=False,
        ),
    ),
)
def test_peer_receipt_union_round_trips_exact_closed_variants(
    receipt: object,
) -> None:
    payload = receipt.to_dict()  # type: ignore[union-attr]

    assert peer_receipt_from_dict(payload).to_dict() == payload
    with pytest.raises(ValueError):
        peer_receipt_from_dict({**payload, "extra": "rejected"})


def test_finish_pending_receipt_requires_ordered_unique_messages() -> None:
    with pytest.raises(ValueError):
        PeerFinishReceipt.pending("request-1", ())
    with pytest.raises(ValueError):
        PeerFinishReceipt.pending(
            "request-1",
            ("message-1", "message-1"),
        )
    with pytest.raises(ValueError):
        PeerFinishReceipt(
            request_id="request-1",
            status="pending_messages",
            pending_message_ids=["message-1"],  # type: ignore[arg-type]
        )
    with pytest.raises(ValueError):
        peer_receipt_from_dict(
            {
                "schema_version": "provider_peer_protocol.v1",
                "kind": "finish",
                "request_id": "request-1",
                "status": "pending_messages",
                "pending_message_ids": "message-1",
            }
        )


def test_frozen_member_result_copies_bytes_and_deeply_freezes_value() -> None:
    mutable = {"items": [{"score": 1}]}
    payload = bytearray(b'{"result":{"items":[{"score":1}]}}')
    result = FrozenPeerMemberResult.create(
        attempt=_attempt(),
        exact_bundle_bytes=payload,
        value=mutable,
    )
    mutable["items"][0]["score"] = 9
    payload[0] = ord("[")

    assert result.exact_bundle_bytes == (
        b'{"result":{"items":[{"score":1}]}}'
    )
    assert result.value == MappingProxyType(
        {"items": (MappingProxyType({"score": 1}),)}
    )
    assert result.bundle_sha256 == (
        "sha256:"
        + hashlib.sha256(result.exact_bundle_bytes).hexdigest()
    )
    direct_value = {"items": [1]}
    direct_bytes = bytearray(b'{"result":{"items":[1]}}')
    direct = FrozenPeerMemberResult(
        attempt=_attempt(),
        exact_bundle_bytes=direct_bytes,  # type: ignore[arg-type]
        value=direct_value,
        bundle_sha256=(
            "sha256:" + hashlib.sha256(direct_bytes).hexdigest()
        ),
    )
    direct_value["items"].append(2)
    direct_bytes[0] = ord("[")
    assert direct.exact_bundle_bytes == b'{"result":{"items":[1]}}'
    assert direct.value == MappingProxyType({"items": (1,)})
    with pytest.raises(ValueError):
        FrozenPeerMemberResult(
            attempt=_attempt(),
            exact_bundle_bytes=b"{}",
            value={},
            bundle_sha256="sha256:" + ("0" * 64),
        )


@pytest.mark.parametrize("member_count", (2, 3, 8))
def test_peer_path_plan_preserves_authored_order_and_is_distinct(
    tmp_path: Path,
    member_count: int,
) -> None:
    members = tuple(f"member-{index}" for index in range(member_count))
    plan = derive_provider_peer_group_paths(
        node_id="node/one",
        member_ids=members,
    )
    realized = realize_provider_peer_group_paths(
        run_root=tmp_path,
        plan=plan,
        visit_count=2,
        attempt_ordinals={
            member: index + 1
            for index, member in enumerate(members)
        },
    )

    assert tuple(member.member_id for member in plan.members) == members
    assert len(realized.leaf_paths()) == 1 + (4 * member_count)
    assert len(set(realized.leaf_paths())) == len(realized.leaf_paths())
    assert all(
        path.is_relative_to(tmp_path.resolve())
        for path in realized.leaf_paths()
    )
    assert "%2F" in plan.visit_root_relpath
    preflight_provider_peer_group_paths(realized)


@pytest.mark.parametrize(
    "members",
    (
        ("only-one",),
        tuple(f"m-{index}" for index in range(9)),
        ("same", "same"),
        (".", "other"),
        ("..", "other"),
    ),
)
def test_peer_path_plan_rejects_invalid_member_sets(
    members: tuple[str, ...],
) -> None:
    with pytest.raises(ValueError):
        derive_provider_peer_group_paths(
            node_id="node",
            member_ids=members,
        )


def test_peer_path_realization_rejects_ordinal_mismatch_and_collision(
    tmp_path: Path,
) -> None:
    plan = derive_provider_peer_group_paths(
        node_id="node",
        member_ids=("writer", "reviewer"),
    )
    with pytest.raises(ValueError):
        realize_provider_peer_group_paths(
            run_root=tmp_path,
            plan=plan,
            visit_count=1,
            attempt_ordinals={"writer": 1},
        )

    payload = plan.to_dict()
    members = payload["members"]
    assert isinstance(members, list)
    first, second = members
    assert isinstance(first, dict)
    assert isinstance(second, dict)
    second["evidence_relpath"] = first["evidence_relpath"]
    with pytest.raises(ValueError):
        PeerGroupPathPlan.from_dict(payload)


def test_peer_path_plan_rejects_absolute_and_parent_templates() -> None:
    plan = derive_provider_peer_group_paths(
        node_id="node",
        member_ids=("writer", "reviewer"),
    )
    absolute = plan.to_dict()
    absolute["visit_root_relpath"] = "/provider-peer-group/node/visits/{visit}"
    with pytest.raises(ValueError):
        PeerGroupPathPlan.from_dict(absolute)

    parent = plan.to_dict()
    members = parent["members"]
    assert isinstance(members, list)
    first = members[0]
    assert isinstance(first, dict)
    first["injected_messages_relpath"] = (
        "../visits/{visit}/attempt-{attempt}/injected-messages.jsonl"
    )
    with pytest.raises(ValueError):
        PeerGroupPathPlan.from_dict(parent)


def test_peer_path_preflight_rejects_existing_leaf_or_nonempty_visit(
    tmp_path: Path,
) -> None:
    plan = derive_provider_peer_group_paths(
        node_id="node",
        member_ids=("writer", "reviewer"),
    )
    realized = realize_provider_peer_group_paths(
        run_root=tmp_path,
        plan=plan,
        visit_count=1,
        attempt_ordinals={"writer": 1, "reviewer": 2},
    )
    leaf = realized.members[0].injected_messages_path
    leaf.parent.mkdir(parents=True)
    leaf.write_text("", encoding="utf-8")
    with pytest.raises(FileExistsError):
        preflight_provider_peer_group_paths(realized)

    leaf.unlink()
    unexpected = realized.visit_root / "unexpected.txt"
    unexpected.write_text("occupied", encoding="utf-8")
    with pytest.raises(FileExistsError):
        preflight_provider_peer_group_paths(realized)


def test_ledger_exclusive_creates_and_fsyncs_canonical_header(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from orchestrator.workflow.provider_peer_group import ledger as module

    calls: list[int] = []
    real_fsync = module.os.fsync

    def tracking_fsync(descriptor: int) -> None:
        calls.append(descriptor)
        real_fsync(descriptor)

    monkeypatch.setattr(module.os, "fsync", tracking_fsync)
    path = tmp_path / "messages.jsonl"
    ledger = PeerMessageLedger.create(
        path,
        group_visit=_visit(),
        receiver_attempt=_attempt(),
        clock=_Clock(),
    )

    raw = path.read_bytes()
    [line] = raw.splitlines()
    header = json.loads(line)
    assert line == json.dumps(
        header,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("ascii")
    assert header["row_kind"] == "header"
    assert header["sequence"] == 0
    assert len(calls) >= 2
    with pytest.raises(FileExistsError):
        PeerMessageLedger.create(
            path,
            group_visit=_visit(),
            receiver_attempt=_attempt(),
            clock=_Clock(),
        )
    ledger.finalize()


def test_ledger_records_ordered_utf8_delivery_and_ack(
    tmp_path: Path,
) -> None:
    ledger, content_digest = _complete_ledger(tmp_path)

    summary = ledger.finalize()
    inspected = inspect_peer_message_ledger(
        tmp_path / "injected-messages.jsonl"
    )
    rows = [
        json.loads(line)
        for line in (
            tmp_path / "injected-messages.jsonl"
        ).read_text(encoding="ascii").splitlines()
    ]

    assert [row["sequence"] for row in rows] == [0, 1, 2, 3]
    assert [row["row_kind"] for row in rows] == [
        "header",
        "recorded",
        "offered",
        "receiver_acknowledged",
    ]
    assert set(rows[0]) == {
        "schema_version",
        "row_kind",
        "sequence",
        "group_visit",
        "receiver_attempt",
        "created_at",
    }
    assert set(rows[1]) == {
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
    }
    assert set(rows[2]) == {
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
    }
    assert set(rows[3]) == {
        "schema_version",
        "row_kind",
        "sequence",
        "request_id",
        "message_id",
        "receiver_attempt",
        "acknowledged_at",
    }
    assert rows[0]["receiver_attempt"] == _attempt().to_dict()
    assert rows[1]["sender_attempt"] == _attempt("reviewer").to_dict()
    assert rows[1]["receiver_attempt"] == _attempt().to_dict()
    assert rows[2]["receiver_attempt"] == _attempt().to_dict()
    assert rows[3]["receiver_attempt"] == _attempt().to_dict()
    assert rows[1]["content"] == "hello\nλ"
    assert rows[1]["content_sha256"] == content_digest
    assert summary == inspected
    assert summary.counts.to_dict() == {
        "recorded": 1,
        "offered": 1,
        "offer_failed": 0,
        "receiver_acknowledged": 1,
    }
    assert summary.ledger_sha256 == (
        "sha256:"
        + hashlib.sha256(
            (tmp_path / "injected-messages.jsonl").read_bytes()
        ).hexdigest()
    )
    assert "content" not in json.dumps(summary.to_dict())


def test_ledger_enforces_record_outcome_ack_state_machine(
    tmp_path: Path,
) -> None:
    ledger = PeerMessageLedger.create(
        tmp_path / "messages.jsonl",
        group_visit=_visit(),
        receiver_attempt=_attempt(),
        clock=_Clock(),
    )
    with pytest.raises(ValueError):
        ledger.append_offered(
            message_id="unknown",
            adapter_instance_id="adapter",
            handle_id="handle",
            byte_count=1,
            content_sha256="sha256:" + ("0" * 64),
        )
    digest = _record_message(ledger)
    with pytest.raises(ValueError):
        _record_message(ledger)
    with pytest.raises(ValueError):
        ledger.append_offered(
            message_id="message-1",
            adapter_instance_id="adapter",
            handle_id="handle",
            byte_count=1,
            content_sha256=digest,
        )
    ledger.append_offer_failed(
        message_id="message-1",
        error_code="offer_failed",
        message="provider pane unavailable",
    )
    rows = [
        json.loads(line)
        for line in (tmp_path / "messages.jsonl")
        .read_text(encoding="ascii")
        .splitlines()
    ]
    assert set(rows[-1]) == {
        "schema_version",
        "row_kind",
        "sequence",
        "message_id",
        "receiver_attempt",
        "content_sha256",
        "error_code",
        "message",
        "failed_at",
    }
    assert rows[-1]["receiver_attempt"] == _attempt().to_dict()
    with pytest.raises(ValueError):
        ledger.append_receiver_acknowledged(
            request_id="ack-1",
            message_id="message-1",
            receiver_attempt=_attempt(),
        )
    with pytest.raises(ValueError):
        ledger.append_receiver_acknowledged(
            request_id="ack-2",
            message_id="message-1",
            receiver_attempt=_attempt("other"),
        )
    ledger.finalize()


def test_ledger_fsyncs_every_lifecycle_row(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from orchestrator.workflow.provider_peer_group import ledger as module

    calls: list[int] = []
    real_fsync = module.os.fsync

    def tracking_fsync(descriptor: int) -> None:
        calls.append(descriptor)
        real_fsync(descriptor)

    monkeypatch.setattr(module.os, "fsync", tracking_fsync)
    ledger = PeerMessageLedger.create(
        tmp_path / "messages.jsonl",
        group_visit=_visit(),
        receiver_attempt=_attempt(),
        clock=_Clock(),
    )
    after_header = len(calls)
    digest = _record_message(ledger)
    assert len(calls) == after_header + 1
    ledger.append_offered(
        message_id="message-1",
        adapter_instance_id="adapter",
        handle_id="handle",
        byte_count=len("hello\nλ".encode("utf-8")),
        content_sha256=digest,
    )
    assert len(calls) == after_header + 2
    ledger.append_receiver_acknowledged(
        request_id="ack-1",
        message_id="message-1",
        receiver_attempt=_attempt(),
    )
    assert len(calls) == after_header + 3
    ledger.finalize()


@pytest.mark.parametrize("tamper", ("append", "replace", "truncate"))
def test_ledger_rejects_external_mutation_before_append_or_finalize(
    tmp_path: Path,
    tamper: str,
) -> None:
    path = tmp_path / "messages.jsonl"
    ledger = PeerMessageLedger.create(
        path,
        group_visit=_visit(),
        receiver_attempt=_attempt(),
        clock=_Clock(),
    )
    if tamper == "append":
        with path.open("ab") as stream:
            stream.write(b'{"partial":')
    elif tamper == "replace":
        replacement = tmp_path / "replacement"
        replacement.write_bytes(path.read_bytes())
        replacement.replace(path)
    else:
        path.write_bytes(b"")

    with pytest.raises(RuntimeError, match="ledger"):
        ledger.finalize()


def test_ledger_inspection_rejects_a_malformed_partial_tail(
    tmp_path: Path,
) -> None:
    path = tmp_path / "messages.jsonl"
    ledger = PeerMessageLedger.create(
        path,
        group_visit=_visit(),
        receiver_attempt=_attempt(),
        clock=_Clock(),
    )
    ledger.finalize()
    with path.open("ab") as stream:
        stream.write(b'{"row_kind":"recorded"')

    with pytest.raises(RuntimeError, match="malformed"):
        inspect_peer_message_ledger(path)


def test_empty_ledger_has_explicit_header_and_zero_summary(
    tmp_path: Path,
) -> None:
    ledger = PeerMessageLedger.create(
        tmp_path / "messages.jsonl",
        group_visit=_visit(),
        receiver_attempt=_attempt(),
        clock=_Clock(),
    )

    summary = ledger.finalize()

    assert summary.row_count == 1
    assert summary.counts.to_dict() == {
        "recorded": 0,
        "offered": 0,
        "offer_failed": 0,
        "receiver_acknowledged": 0,
    }


def test_terminal_evidence_completed_contract_excludes_runtime_handles(
    tmp_path: Path,
) -> None:
    writer_attempt = _attempt()
    reviewer_attempt = _attempt("reviewer")
    writer_ledger = PeerMessageLedger.create(
        tmp_path / "writer.jsonl",
        group_visit=_visit(),
        receiver_attempt=writer_attempt,
        clock=_Clock(),
    )
    reviewer_ledger = PeerMessageLedger.create(
        tmp_path / "reviewer.jsonl",
        group_visit=_visit(),
        receiver_attempt=reviewer_attempt,
        clock=_Clock(),
    )
    natural_shutdown = NaturalShutdownProof(
        disposition="natural_exit",
        handle_id="adapter-handle-not-evidence",
        return_code=0,
        pane_absent=True,
        server_absent=True,
        proof_complete=True,
    )
    writer = PeerMemberTerminalEvidence(
        attempt=writer_attempt,
        lifecycle=PeerMemberLifecycle.TERMINAL,
        ledger=writer_ledger.finalize(),
        frozen_bundle_sha256="sha256:" + ("1" * 64),
        natural_shutdown=natural_shutdown,
        failed_cleanup=None,
    )
    reviewer = PeerMemberTerminalEvidence(
        attempt=reviewer_attempt,
        lifecycle=PeerMemberLifecycle.TERMINAL,
        ledger=reviewer_ledger.finalize(),
        frozen_bundle_sha256="sha256:" + ("3" * 64),
        natural_shutdown=natural_shutdown,
        failed_cleanup=None,
    )
    evidence = PeerGroupTerminalEvidence(
        outcome="completed",
        group_visit=_visit(),
        members=(writer, reviewer),
        endpoint_drained=True,
        endpoint_closed=True,
        endpoint_workers_joined=True,
        settlement_sha256="sha256:" + ("2" * 64),
        failure=None,
        terminal_at="2026-07-24T12:30:00+00:00",
    )

    payload = evidence.to_dict()
    encoded = json.dumps(payload)
    assert PeerGroupTerminalEvidence.from_dict(payload) == evidence
    assert "adapter-handle-not-evidence" not in encoded
    assert "endpoint_instance_id" not in encoded
    assert "opaque_binding" not in encoded
    assert "content" not in encoded


def test_terminal_failure_requires_failure_and_forbids_settlement() -> None:
    cleanup = FailedCleanupProof(
        disposition="failed_cleanup",
        handle_id="private-handle",
        pane_absent=True,
        server_absent=True,
        cleanup_complete=True,
        error_code=None,
    )
    writer = PeerMemberTerminalEvidence(
        attempt=_attempt(),
        lifecycle=PeerMemberLifecycle.FAILED,
        ledger=None,
        frozen_bundle_sha256=None,
        natural_shutdown=None,
        failed_cleanup=cleanup,
    )
    reviewer = PeerMemberTerminalEvidence(
        attempt=_attempt("reviewer"),
        lifecycle=PeerMemberLifecycle.FAILED,
        ledger=None,
        frozen_bundle_sha256=None,
        natural_shutdown=None,
        failed_cleanup=cleanup,
    )
    with pytest.raises(ValueError):
        PeerGroupTerminalEvidence(
            outcome="failed",
            group_visit=_visit(),
            members=(writer, reviewer),
            endpoint_drained=True,
            endpoint_closed=True,
            endpoint_workers_joined=True,
            settlement_sha256="sha256:" + ("2" * 64),
            failure={"code": "member_failed", "message": "failed"},
            terminal_at="2026-07-24T12:30:00+00:00",
        )
    with pytest.raises(ValueError):
        PeerGroupTerminalEvidence(
            outcome="failed",
            group_visit=_visit(),
            members=(writer, reviewer),
            endpoint_drained=True,
            endpoint_closed=True,
            endpoint_workers_joined=True,
            settlement_sha256=None,
            failure=None,
            terminal_at="2026-07-24T12:30:00+00:00",
        )

    evidence = PeerGroupTerminalEvidence(
        outcome="failed",
        group_visit=_visit(),
        members=(writer, reviewer),
        endpoint_drained=True,
        endpoint_closed=True,
        endpoint_workers_joined=True,
        settlement_sha256=None,
        failure={"code": "member_failed", "message": "member failed"},
        terminal_at="2026-07-24T12:30:00+00:00",
    )
    payload = evidence.to_dict()
    encoded = json.dumps(payload)
    assert PeerGroupTerminalEvidence.from_dict(payload) == evidence
    assert set(payload["failure"]) == {"code", "message"}
    assert "private-handle" not in encoded
    assert "endpoint_instance_id" not in encoded
    assert "opaque_binding" not in encoded


@pytest.mark.parametrize(
    "field",
    ("natural_shutdown", "failed_cleanup"),
)
def test_failed_member_evidence_rejects_arbitrary_proof_objects(
    field: str,
) -> None:
    values = {
        "attempt": _attempt(),
        "lifecycle": PeerMemberLifecycle.FAILED,
        "ledger": None,
        "frozen_bundle_sha256": None,
        "natural_shutdown": None,
        "failed_cleanup": None,
    }
    values[field] = object()

    with pytest.raises(ValueError):
        PeerMemberTerminalEvidence(**values)


def test_ledger_poisoned_when_post_append_metadata_probe_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from orchestrator.workflow.provider_peer_group import ledger as module

    ledger = PeerMessageLedger.create(
        tmp_path / "messages.jsonl",
        group_visit=_visit(),
        receiver_attempt=_attempt(),
        clock=_Clock(),
    )
    real_fstat = module.os.fstat
    calls = 0

    def fail_final_metadata_probe(descriptor: int):
        nonlocal calls
        calls += 1
        if calls == 5:
            raise OSError("injected post-append fstat failure")
        return real_fstat(descriptor)

    monkeypatch.setattr(module.os, "fstat", fail_final_metadata_probe)

    with pytest.raises(RuntimeError, match="durability is uncertain"):
        _record_message(ledger)
    with pytest.raises(RuntimeError, match="poisoned"):
        ledger.finalize()
