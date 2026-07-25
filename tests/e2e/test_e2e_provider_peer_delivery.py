"""Real Codex proof for recorded natural turn-boundary peer delivery."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shlex
import sys
import tempfile
import time

import pytest

from orchestrator.contracts.output_contract import validate_output_bundle
from orchestrator.providers import ProviderExecutor, ProviderRegistry
from orchestrator.providers.interactive_terminal import (
    InteractiveMemberHandle,
    InteractiveTerminalTurnQueueAdapter,
    NaturalShutdownProof,
)
from orchestrator.workflow.provider_peer_group.bindings import (
    PeerDeliveryFrame,
)
from orchestrator.workflow.provider_peer_group.ledger import (
    PeerMessageLedger,
    inspect_peer_message_ledger,
)
from orchestrator.workflow.provider_peer_group.models import (
    FrozenPeerMemberResult,
    PeerAcknowledgeReceipt,
    PeerAcknowledgeRequest,
    PeerAttemptIdentity,
    PeerEndpointIdentity,
    PeerFinishReceipt,
    PeerFinishRequest,
    PeerGroupVisitIdentity,
    PeerReadyReceipt,
    PeerReadyRequest,
)
from orchestrator.workflow.provider_peer_group.protocol import (
    ACTIVE_PEER_BINDING_ENV,
    PeerEndpointCloseProof,
    PeerProtocolEvent,
    PeerProtocolListener,
    encode_active_peer_binding,
)
from tests.e2e.conftest import skip_if_no_cli, skip_if_no_e2e


_EXPECTED_VALUE = "peer-delivery-ok"
_MESSAGE_ID = "real-adapter-message-1"
_MESSAGE_CONTENT = "Apply the queued peer message protocol now."
_EVENT_TIMEOUT_SEC = 240.0
_NATURAL_JOIN_TIMEOUT_SEC = 90.0
_REPO_ROOT = Path(__file__).parents[2]


def _fixture_path() -> Path:
    return (
        Path(__file__).parents[1]
        / "fixtures"
        / "workflow_lisp"
        / "provider_peer_group"
        / "real_adapter_prompt.md"
    )


def _render_prompt() -> str:
    template_path = _fixture_path()
    assert template_path.is_file(), (
        "real adapter prompt fixture is missing"
    )
    template = template_path.read_text(encoding="utf-8")
    rendered = template.replace(
        "{{PYTHON}}",
        shlex.quote(sys.executable),
    ).replace(
        "{{EXPECTED_VALUE_JSON}}",
        json.dumps(_EXPECTED_VALUE),
    )
    assert "{{" not in rendered and "}}" not in rendered
    return rendered


def _receive(
    listener: PeerProtocolListener,
    request_type: type,
) -> PeerProtocolEvent:
    event = listener.receive_event(timeout_sec=_EVENT_TIMEOUT_SEC)
    assert isinstance(event.request, request_type)
    return event


def _sha256(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


@pytest.mark.e2e
def test_real_one_member_adapter_delivers_at_natural_turn_boundary(
    tmp_path: Path,
) -> None:
    """Record, offer, acknowledge, freeze, and naturally close one turn."""

    skip_if_no_e2e()
    for executable in ("codex", "git", "tmux"):
        skip_if_no_cli(executable)

    prompt = _render_prompt()
    workspace = tmp_path / "provider-peer-real-adapter"
    workspace.mkdir()

    group_visit = PeerGroupVisitIdentity(
        run_id="real-adapter-run",
        step_name="real-adapter-step",
        node_id="real-adapter-node",
        visit_count=1,
    )
    receiver_attempt = PeerAttemptIdentity(
        member_id="receiver",
        attempt_scope_key="real-adapter-receiver-scope",
        attempt_ordinal=1,
    )
    sender_attempt = PeerAttemptIdentity(
        member_id="harness-sender",
        attempt_scope_key="real-adapter-sender-scope",
        attempt_ordinal=1,
    )
    endpoint_identity = PeerEndpointIdentity(
        group_visit=group_visit,
        endpoint_instance_id="real-adapter-endpoint",
    )
    runtime_root = workspace / ".orchestrate" / "provider-peer-real"
    transport_temp = tempfile.TemporaryDirectory(prefix="orc-peer-e2e-")
    transport_root = Path(transport_temp.name)
    socket_path = transport_root / "peer.sock"
    bundle_path = runtime_root / "member-result.json"
    ledger_path = runtime_root / "injected-messages.jsonl"
    runtime_root.mkdir(parents=True)

    listener = PeerProtocolListener(endpoint_identity, socket_path)
    ledger = PeerMessageLedger.create(
        ledger_path,
        group_visit=group_visit,
        receiver_attempt=receiver_attempt,
    )
    registry = ProviderRegistry()
    provider = registry.get("codex")
    assert provider is not None
    assert provider.interactive_session_support is not None
    executor = ProviderExecutor(workspace, registry)
    adapter = InteractiveTerminalTurnQueueAdapter(
        transport_root / "interactive-terminal"
    )
    handle: InteractiveMemberHandle | None = None
    natural_proof: NaturalShutdownProof | None = None
    listener_proof: PeerEndpointCloseProof | None = None

    try:
        listener.start()
        inherited_python_path = os.environ.get("PYTHONPATH")
        python_path = str(_REPO_ROOT)
        if inherited_python_path:
            python_path = os.pathsep.join(
                (python_path, inherited_python_path)
            )
        # Interactive Codex has an exact-project trust chooser for new
        # temporary roots. Launch from the already trusted checkout so that
        # the adapter exercises only declared provider turns; every mutable
        # endpoint, bundle, ledger, and tmux artifact remains under tmp_path.
        invocation, error = executor.prepare_interactive_invocation(
            provider_name="codex",
            params={},
            context={},
            prompt_content=prompt,
            invocation_id="real-adapter-invocation",
            member_id=receiver_attempt.member_id,
            attempt_scope_key=receiver_attempt.attempt_scope_key,
            attempt_ordinal=receiver_attempt.attempt_ordinal,
            cwd=_REPO_ROOT,
            env={
                ACTIVE_PEER_BINDING_ENV: encode_active_peer_binding(
                    socket_path=socket_path,
                    sender_binding="real-adapter-receiver-binding",
                ),
                "ORCHESTRATOR_OUTPUT_BUNDLE_PATH": str(bundle_path),
                "PYTHONPATH": python_path,
            },
        )
        assert error is None
        assert invocation is not None
        assert invocation.support is provider.interactive_session_support
        assert "resume" not in invocation.resolved_command[:-1]
        assert "--ephemeral" not in invocation.resolved_command[:-1]

        handle = adapter.start(invocation)
        ready_event = _receive(listener, PeerReadyRequest)
        assert ready_event.endpoint_identity == endpoint_identity
        assert (
            ready_event.request.sender_binding
            == "real-adapter-receiver-binding"
        )

        # Keep the ready tool active while the runtime durably records and
        # offers the next-turn message. Resolving ready afterward lets the
        # current provider turn finish naturally with the message queued.
        content_sha256 = ledger.append_recorded(
            coordinator_sequence=1,
            request_id="real-adapter-send-request",
            message_id=_MESSAGE_ID,
            sender_attempt=sender_attempt,
            content=_MESSAGE_CONTENT,
        )
        frame = PeerDeliveryFrame(
            message_id=_MESSAGE_ID,
            sender_member_id=sender_attempt.member_id,
            content=_MESSAGE_CONTENT,
        )
        offer_receipt = adapter.offer(handle, frame.render())
        assert offer_receipt.status == "offered"
        assert offer_receipt.handle_id == handle.handle_id
        assert offer_receipt.byte_count == frame.rendered_byte_count
        assert offer_receipt.content_sha256 == frame.rendered_sha256
        ledger.append_offered(
            message_id=_MESSAGE_ID,
            adapter_instance_id=handle.adapter_instance_id,
            handle_id=handle.handle_id,
            byte_count=len(_MESSAGE_CONTENT.encode("utf-8")),
            content_sha256=content_sha256,
        )
        listener.resolve(
            ready_event,
            PeerReadyReceipt(ready_event.request.request_id),
        )

        acknowledge_event = _receive(
            listener,
            PeerAcknowledgeRequest,
        )
        assert isinstance(
            acknowledge_event.request,
            PeerAcknowledgeRequest,
        )
        assert (
            acknowledge_event.request.sender_binding
            == "real-adapter-receiver-binding"
        )
        assert acknowledge_event.request.message_id == _MESSAGE_ID
        ledger.append_receiver_acknowledged(
            request_id=acknowledge_event.request.request_id,
            message_id=_MESSAGE_ID,
            receiver_attempt=receiver_attempt,
        )
        acknowledge_receipt = PeerAcknowledgeReceipt(
            acknowledge_event.request.request_id,
            _MESSAGE_ID,
        )
        listener.resolve(acknowledge_event, acknowledge_receipt)

        finish_event = _receive(listener, PeerFinishRequest)
        assert isinstance(finish_event.request, PeerFinishRequest)
        assert (
            finish_event.request.sender_binding
            == "real-adapter-receiver-binding"
        )
        artifacts = validate_output_bundle(
            {
                "path": bundle_path.relative_to(workspace).as_posix(),
                "fields": [
                    {
                        "name": "__result__",
                        "json_pointer": "",
                        "type": "string",
                        "required": True,
                    }
                ],
            },
            workspace=workspace,
        )
        assert artifacts == {"__result__": _EXPECTED_VALUE}
        exact_bundle_bytes = bundle_path.read_bytes()
        bundle_value = json.loads(exact_bundle_bytes.decode("utf-8"))
        assert bundle_value == _EXPECTED_VALUE
        assert bundle_path.read_bytes() == exact_bundle_bytes
        frozen = FrozenPeerMemberResult.create(
            attempt=receiver_attempt,
            exact_bundle_bytes=exact_bundle_bytes,
            value=bundle_value,
        )
        assert frozen.value == _EXPECTED_VALUE
        assert frozen.exact_bundle_bytes == exact_bundle_bytes
        assert frozen.bundle_sha256 == _sha256(exact_bundle_bytes)

        close_receipt = adapter.offer_close(handle)
        assert close_receipt.status == "close_offered"
        finish_receipt = PeerFinishReceipt.close_offered(
            finish_event.request.request_id
        )
        listener.resolve(finish_event, finish_receipt)
        natural_proof = adapter.join(
            handle,
            deadline=time.monotonic() + _NATURAL_JOIN_TIMEOUT_SEC,
        )
        assert natural_proof == NaturalShutdownProof(
            disposition="natural_exit",
            handle_id=handle.handle_id,
            return_code=0,
            pane_absent=True,
            server_absent=True,
            proof_complete=True,
        )

        ledger_summary = ledger.finalize()
        assert ledger_summary.counts.recorded == 1
        assert ledger_summary.counts.offered == 1
        assert ledger_summary.counts.offer_failed == 0
        assert ledger_summary.counts.receiver_acknowledged == 1
        assert inspect_peer_message_ledger(ledger_path) == ledger_summary
        rows = tuple(
            json.loads(line)
            for line in ledger_path.read_text(encoding="utf-8").splitlines()
        )
        assert tuple(row["row_kind"] for row in rows) == (
            "header",
            "recorded",
            "offered",
            "receiver_acknowledged",
        )

        listener_proof = listener.close()
        assert listener_proof == PeerEndpointCloseProof(
            drained=True,
            closed=True,
            workers_joined=True,
        )
        assert not socket_path.exists()
        for forcing_surface in (
            "cancel_and_reap",
            "resume",
            "steer",
            "directive",
        ):
            assert not hasattr(adapter, forcing_surface)
    finally:
        if listener_proof is None:
            listener.close()
        if handle is not None and natural_proof is None:
            adapter.abort(
                handle,
                deadline=time.monotonic() + 15.0,
            )
        ledger.finalize()
        transport_temp.cleanup()
        assert not transport_root.exists()
