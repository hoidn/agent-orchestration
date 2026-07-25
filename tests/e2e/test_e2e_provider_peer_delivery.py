"""Real Codex proof for recorded natural turn-boundary peer delivery."""

from __future__ import annotations

from argparse import Namespace
import hashlib
import json
import os
from pathlib import Path
import shlex
import sys
import tempfile
import time

import pytest

from orchestrator.cli.commands.run import run_workflow
from orchestrator.cli.commands.report import report_workflow
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
    PeerGroupTerminalEvidence,
    PeerGroupVisitIdentity,
    PeerReadyReceipt,
    PeerReadyRequest,
)
from orchestrator.workflow.provider_peer_group.paths import (
    realize_provider_peer_group_paths,
)
from orchestrator.workflow.provider_peer_group.protocol import (
    ACTIVE_PEER_BINDING_ENV,
    PeerEndpointCloseProof,
    PeerProtocolEvent,
    PeerProtocolListener,
    encode_active_peer_binding,
)
from orchestrator.workflow.executable_ir import ExecutableNodeKind
from orchestrator.workflow.pure_expr import canonical_json_for_pure_value
from orchestrator.workflow_lisp.build import (
    FrontendBuildRequest,
    build_frontend_bundle,
)
from tests.e2e.conftest import skip_if_no_cli, skip_if_no_e2e


_EXPECTED_VALUE = "peer-delivery-ok"
_MESSAGE_ID = "real-adapter-message-1"
_MESSAGE_CONTENT = "Apply the queued peer message protocol now."
_EVENT_TIMEOUT_SEC = 240.0
_NATURAL_JOIN_TIMEOUT_SEC = 90.0
_REPO_ROOT = Path(__file__).parents[2]
_COORDINATOR_MESSAGE = (
    "Preserve this exact peer payload 🌍.\nSecond line: Ω"
)
_COORDINATOR_SENDER_VALUE = "peer-send-complete"
_ROLE_PROMPT_FIXTURES = {
    "sender": "real_peer_two_sender.md",
    "receiver": "real_peer_two_receiver.md",
}
_THREE_MEMBER_FIXTURES = {
    "source": "real_peer_group_three.orc",
    "providers": "real_peer_group_three.providers.json",
    "prompts": "real_peer_group_three.prompts.json",
}
_THREE_MEMBER_ROLE_PROMPTS = {
    "sender": "real_peer_group_sender.md",
    "receiver": "real_peer_group_receiver.md",
    "witness": "real_peer_group_witness.md",
}


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


def _render_role_prompt(role: str, *, sync_marker: Path) -> str:
    fixture_name = _ROLE_PROMPT_FIXTURES[role]
    template_path = _fixture_path().with_name(fixture_name)
    assert template_path.is_file(), (
        f"{role} prompt fixture is missing"
    )
    rendered = template_path.read_text(encoding="utf-8")
    replacements = {
        "{{PYTHON}}": shlex.quote(sys.executable),
        "{{MESSAGE_JSON}}": json.dumps(
            _COORDINATOR_MESSAGE,
            ensure_ascii=False,
        ),
        "{{MESSAGE_SHELL}}": shlex.quote(_COORDINATOR_MESSAGE),
        "{{SENDER_VALUE_JSON}}": json.dumps(
            _COORDINATOR_SENDER_VALUE,
        ),
        "{{SYNC_MARKER_SHELL}}": shlex.quote(str(sync_marker)),
    }
    for marker, value in replacements.items():
        rendered = rendered.replace(marker, value)
    assert "{{" not in rendered and "}}" not in rendered
    return rendered


def _write_coordinator_fixture(
    workspace: Path,
    *,
    sync_marker: Path,
) -> dict[str, Path]:
    files = {
        "source": workspace / "real_peer_delivery.orc",
        "providers": workspace / "providers.json",
        "prompts": workspace / "prompts.json",
        "sender": workspace / "sender.md",
        "receiver": workspace / "receiver.md",
    }
    files["source"].write_text(
        "\n".join(
            (
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.17")',
                "  (defmodule real_peer_delivery)",
                "  (export orchestrate)",
                "  (defrecord DeliveryResult",
                "    (sender String)",
                "    (receiver String))",
                "  (defworkflow orchestrate () -> DeliveryResult",
                "    (with-live-provider-peers",
                "      ((sender",
                "         (provider-result providers.sender",
                "           :prompt prompts.sender",
                "           :inputs ()",
                "           :timeout-sec 300",
                "           :returns String))",
                "       (receiver",
                "         (provider-result providers.receiver",
                "           :prompt prompts.receiver",
                "           :inputs ()",
                "           :timeout-sec 300",
                "           :returns String)))",
                "      (record DeliveryResult",
                "        :sender sender",
                "        :receiver receiver))))",
                "",
            )
        ),
        encoding="utf-8",
    )
    files["providers"].write_text(
        json.dumps(
            {
                "providers.receiver": "codex",
                "providers.sender": "codex",
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    files["prompts"].write_text(
        json.dumps(
            {
                "prompts.receiver": "receiver.md",
                "prompts.sender": "sender.md",
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    files["sender"].write_text(
        _render_role_prompt("sender", sync_marker=sync_marker),
        encoding="utf-8",
    )
    files["receiver"].write_text(
        _render_role_prompt("receiver", sync_marker=sync_marker),
        encoding="utf-8",
    )
    return files


def _write_three_member_fixture(
    workspace: Path,
    *,
    sync_marker: Path,
) -> dict[str, Path]:
    fixture_root = _fixture_path().parent
    files: dict[str, Path] = {}
    for key, filename in _THREE_MEMBER_FIXTURES.items():
        destination = workspace / filename
        destination.write_bytes((fixture_root / filename).read_bytes())
        files[key] = destination

    replacements = {
        "{{PYTHON}}": shlex.quote(sys.executable),
        "{{MESSAGE_SHELL}}": shlex.quote(_COORDINATOR_MESSAGE),
        "{{SYNC_MARKER_SHELL}}": shlex.quote(str(sync_marker)),
    }
    for role, filename in _THREE_MEMBER_ROLE_PROMPTS.items():
        rendered = (fixture_root / filename).read_text(encoding="utf-8")
        for marker, value in replacements.items():
            rendered = rendered.replace(marker, value)
        assert "{{" not in rendered and "}}" not in rendered
        destination = workspace / filename
        destination.write_text(rendered, encoding="utf-8")
        files[role] = destination
    return files


def _coordinator_build_request(
    workspace: Path,
    files: dict[str, Path],
) -> FrontendBuildRequest:
    return FrontendBuildRequest(
        source_path=files["source"],
        source_roots=(workspace,),
        entry_workflow="orchestrate",
        provider_externs_path=files["providers"],
        prompt_externs_path=files["prompts"],
        imported_workflow_bundles_path=None,
        command_boundaries_path=None,
        emit_debug_yaml=False,
        workspace_root=workspace,
    )


def _coordinator_run_args(
    files: dict[str, Path],
    *,
    state_dir: Path,
) -> Namespace:
    return Namespace(
        workflow=str(files["source"]),
        context=None,
        context_file=None,
        input=None,
        input_file=None,
        clean_processed=False,
        archive_processed=None,
        debug=False,
        stream_output=False,
        dry_run=False,
        backup_state=False,
        state_dir=str(state_dir),
        on_error="stop",
        max_retries=0,
        retry_delay=0,
        quiet=True,
        verbose=False,
        log_level="error",
        step_summaries=False,
        summary_mode=None,
        summary_provider="claude_sonnet_summary",
        summary_timeout_sec=120,
        summary_max_input_chars=12000,
        summary_profile=None,
        live_agent_notes=False,
        live_agent_note_provider=None,
        live_agent_note_interval_sec=15.0,
        live_agent_note_timeout_sec=30,
        live_agent_note_max_tail_chars=6000,
        entry_workflow="orchestrate",
        source_root=[str(files["source"].parent)],
        provider_externs_file=str(files["providers"]),
        prompt_externs_file=str(files["prompts"]),
        imported_workflow_bundles_file=None,
        command_boundaries_file=None,
        emit_debug_yaml=False,
    )


def _peer_socket_paths() -> set[Path]:
    roots = [Path(tempfile.gettempdir())]
    if os.name == "posix" and Path("/tmp") not in roots:
        roots.append(Path("/tmp"))
    return {
        path
        for root in roots
        if root.is_dir()
        for pattern in (
            "orchestrator-peer-*.sock",
            "orc-peer-*.sock",
        )
        for path in root.glob(pattern)
    }


def test_peer_socket_snapshot_covers_endpoint_and_adapter_names(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        tempfile,
        "gettempdir",
        lambda: str(tmp_path),
    )
    endpoint = tmp_path / "orchestrator-peer-endpoint.sock"
    adapter = tmp_path / "orc-peer-adapter.sock"
    unrelated = tmp_path / "other.sock"
    for path in (endpoint, adapter, unrelated):
        path.touch()

    snapshot = _peer_socket_paths()

    assert endpoint in snapshot
    assert adapter in snapshot
    assert unrelated not in snapshot


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


@pytest.mark.e2e
def test_real_two_member_coordinator_records_peer_send_and_settles_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Run the production coordinator through one natural peer exchange."""

    skip_if_no_e2e()
    for executable in ("codex", "git", "tmux"):
        skip_if_no_cli(executable)

    fixture_root = tmp_path / "provider-peer-real-coordinator"
    fixture_root.mkdir()
    state_dir = tmp_path / "provider-peer-real-runs"
    sync_marker = (
        tmp_path
        / "provider-peer-turn-boundary"
        / "peer-send-succeeded"
    )
    sync_marker.parent.mkdir()
    assert not sync_marker.exists()
    files = _write_coordinator_fixture(
        fixture_root,
        sync_marker=sync_marker,
    )
    built = build_frontend_bundle(
        _coordinator_build_request(fixture_root, files)
    )
    [node] = built.validated_bundle.ir.nodes.values()
    assert node.kind is ExecutableNodeKind.PROVIDER_PEER_GROUP
    config = node.execution_config
    assert tuple(
        member.member_id for member in config.members
    ) == ("sender", "receiver")

    inherited_python_path = os.environ.get("PYTHONPATH")
    python_path = str(_REPO_ROOT)
    if inherited_python_path:
        python_path = os.pathsep.join(
            (python_path, inherited_python_path)
        )
    monkeypatch.setenv("PYTHONPATH", python_path)
    monkeypatch.chdir(_REPO_ROOT)
    sockets_before = _peer_socket_paths()

    assert run_workflow(
        _coordinator_run_args(files, state_dir=state_dir)
    ) == 0

    assert sync_marker.is_file()
    assert _peer_socket_paths() == sockets_before
    [run_root] = state_dir.iterdir()
    state = json.loads(
        (run_root / "state.json").read_text(encoding="utf-8")
    )
    expected_settlement = {
        "sender": _COORDINATOR_SENDER_VALUE,
        "receiver": _COORDINATOR_MESSAGE,
    }
    assert state["status"] == "completed"
    assert state["workflow_outputs"] == {
        "return__sender": _COORDINATOR_SENDER_VALUE,
        "return__receiver": _COORDINATOR_MESSAGE,
    }
    assert len(state["provider_attempt_allocations"]) == 2
    [step] = state["steps"].values()
    assert step["status"] == "completed"
    assert step["artifacts"] == expected_settlement

    terminal_path = (
        run_root
        / step["debug"]["provider_peer_group"][
            "terminal_evidence_path"
        ]
    )
    terminal = PeerGroupTerminalEvidence.from_dict(
        json.loads(terminal_path.read_text(encoding="ascii"))
    )
    assert terminal.outcome == "completed"
    assert terminal.failure is None
    assert (
        terminal.endpoint_drained,
        terminal.endpoint_closed,
        terminal.endpoint_workers_joined,
    ) == (True, True, True)
    assert terminal.settlement_sha256 == _sha256(
        canonical_json_for_pure_value(expected_settlement).encode("utf-8")
    )
    assert tuple(
        member.attempt.member_id for member in terminal.members
    ) == ("sender", "receiver")

    realized = realize_provider_peer_group_paths(
        run_root=run_root,
        plan=config.paths,
        visit_count=terminal.group_visit.visit_count,
        attempt_ordinals={
            member.attempt.member_id: member.attempt.attempt_ordinal
            for member in terminal.members
        },
    )
    assert realized.terminal_evidence_path == terminal_path
    terminal_by_member = {
        member.attempt.member_id: member
        for member in terminal.members
    }
    realized_by_member = {
        member.member_id: member for member in realized.members
    }
    expected_values = {
        "sender": _COORDINATOR_SENDER_VALUE,
        "receiver": _COORDINATOR_MESSAGE,
    }
    for member_id, value in expected_values.items():
        paths = realized_by_member[member_id]
        evidence = terminal_by_member[member_id]
        expected_bytes = json.dumps(
            value,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        assert paths.provisional_bundle_path.read_bytes() == expected_bytes
        frozen = FrozenPeerMemberResult.create(
            attempt=evidence.attempt,
            exact_bundle_bytes=expected_bytes,
            value=value,
        )
        assert frozen.bundle_sha256 == evidence.frozen_bundle_sha256
        assert json.loads(
            paths.evidence_path.read_text(encoding="ascii")
        ) == evidence.to_dict()
        assert evidence.natural_shutdown is not None
        assert evidence.natural_shutdown.to_dict() == {
            "disposition": "natural_exit",
            "return_code": 0,
            "pane_absent": True,
            "server_absent": True,
            "proof_complete": True,
        }
        assert evidence.failed_cleanup is None

    sender_paths = realized_by_member["sender"]
    sender_summary = inspect_peer_message_ledger(
        sender_paths.injected_messages_path
    )
    assert sender_summary == terminal_by_member["sender"].ledger
    assert sender_summary.row_count == 1
    assert sender_summary.counts.to_dict() == {
        "recorded": 0,
        "offered": 0,
        "offer_failed": 0,
        "receiver_acknowledged": 0,
    }
    sender_rows = tuple(
        json.loads(line)
        for line in sender_paths.injected_messages_path.read_text(
            encoding="ascii"
        ).splitlines()
    )
    assert tuple(row["row_kind"] for row in sender_rows) == ("header",)
    assert sender_rows[0]["group_visit"] == terminal.group_visit.to_dict()
    assert sender_rows[0]["receiver_attempt"] == (
        terminal_by_member["sender"].attempt.to_dict()
    )

    receiver_paths = realized_by_member["receiver"]
    receiver_summary = inspect_peer_message_ledger(
        receiver_paths.injected_messages_path
    )
    assert receiver_summary == terminal_by_member["receiver"].ledger
    assert receiver_summary.row_count == 4
    assert receiver_summary.counts.to_dict() == {
        "recorded": 1,
        "offered": 1,
        "offer_failed": 0,
        "receiver_acknowledged": 1,
    }
    receiver_rows = tuple(
        json.loads(line)
        for line in receiver_paths.injected_messages_path.read_text(
            encoding="ascii"
        ).splitlines()
    )
    assert tuple(row["row_kind"] for row in receiver_rows) == (
        "header",
        "recorded",
        "offered",
        "receiver_acknowledged",
    )
    header, recorded, offered, acknowledged = receiver_rows
    receiver_attempt = terminal_by_member["receiver"].attempt.to_dict()
    sender_attempt = terminal_by_member["sender"].attempt.to_dict()
    assert header["group_visit"] == terminal.group_visit.to_dict()
    assert header["receiver_attempt"] == receiver_attempt
    assert recorded["coordinator_sequence"] == 1
    assert recorded["sender_attempt"] == sender_attempt
    assert recorded["receiver_attempt"] == receiver_attempt
    assert recorded["content"] == _COORDINATOR_MESSAGE
    assert recorded["content_sha256"] == _sha256(
        _COORDINATOR_MESSAGE.encode("utf-8")
    )
    assert offered["message_id"] == recorded["message_id"]
    assert offered["receiver_attempt"] == receiver_attempt
    assert offered["byte_count"] == len(
        _COORDINATOR_MESSAGE.encode("utf-8")
    )
    assert offered["content_sha256"] == recorded["content_sha256"]
    assert acknowledged["message_id"] == recorded["message_id"]
    assert acknowledged["receiver_attempt"] == receiver_attempt
    assert not list(run_root.rglob("*.sock"))


@pytest.mark.e2e
def test_real_three_member_workflow_runs_through_public_surface(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Compile and run a three-member peer group through the public surface."""

    skip_if_no_e2e()
    for executable in ("codex", "git", "tmux"):
        skip_if_no_cli(executable)

    fixture_root = tmp_path / "provider-peer-real-three"
    fixture_root.mkdir()
    state_dir = tmp_path / "provider-peer-real-three-runs"
    sync_marker = tmp_path / "provider-peer-real-three-sync" / "sent"
    sync_marker.parent.mkdir()
    assert not sync_marker.exists()
    files = _write_three_member_fixture(
        fixture_root,
        sync_marker=sync_marker,
    )
    built = build_frontend_bundle(
        _coordinator_build_request(fixture_root, files)
    )
    [node] = built.validated_bundle.ir.nodes.values()
    assert node.kind is ExecutableNodeKind.PROVIDER_PEER_GROUP
    config = node.execution_config
    assert tuple(member.member_id for member in config.members) == (
        "sender",
        "receiver",
        "witness",
    )

    inherited_python_path = os.environ.get("PYTHONPATH")
    python_path = str(_REPO_ROOT)
    if inherited_python_path:
        python_path = os.pathsep.join(
            (python_path, inherited_python_path)
        )
    monkeypatch.setenv("PYTHONPATH", python_path)
    monkeypatch.chdir(_REPO_ROOT)
    sockets_before = _peer_socket_paths()

    assert run_workflow(
        _coordinator_run_args(files, state_dir=state_dir)
    ) == 0

    assert sync_marker.is_file()
    assert _peer_socket_paths() == sockets_before
    [run_root] = state_dir.iterdir()
    state = json.loads(
        (run_root / "state.json").read_text(encoding="utf-8")
    )
    expected_settlement = {
        "sender": "sender-complete",
        "received": _COORDINATOR_MESSAGE,
        "witness": True,
    }
    assert state["status"] == "completed"
    assert state["workflow_outputs"] == {
        f"return__{name}": value
        for name, value in expected_settlement.items()
    }
    assert len(state["provider_attempt_allocations"]) == 3
    [step] = state["steps"].values()
    assert step["status"] == "completed"
    assert step["artifacts"] == expected_settlement

    terminal_path = (
        run_root
        / step["debug"]["provider_peer_group"][
            "terminal_evidence_path"
        ]
    )
    terminal = PeerGroupTerminalEvidence.from_dict(
        json.loads(terminal_path.read_text(encoding="ascii"))
    )
    assert terminal.outcome == "completed"
    assert terminal.failure is None
    assert tuple(
        member.attempt.member_id for member in terminal.members
    ) == ("sender", "receiver", "witness")
    assert (
        terminal.endpoint_drained,
        terminal.endpoint_closed,
        terminal.endpoint_workers_joined,
    ) == (True, True, True)
    assert terminal.settlement_sha256 == _sha256(
        canonical_json_for_pure_value(expected_settlement).encode("utf-8")
    )
    assert all(
        member.natural_shutdown is not None
        and member.natural_shutdown.return_code == 0
        and member.natural_shutdown.pane_absent
        and member.natural_shutdown.server_absent
        and member.natural_shutdown.proof_complete
        and member.failed_cleanup is None
        for member in terminal.members
    )

    realized = realize_provider_peer_group_paths(
        run_root=run_root,
        plan=config.paths,
        visit_count=terminal.group_visit.visit_count,
        attempt_ordinals={
            member.attempt.member_id: member.attempt.attempt_ordinal
            for member in terminal.members
        },
    )
    terminal_by_member = {
        member.attempt.member_id: member
        for member in terminal.members
    }
    realized_by_member = {
        member.member_id: member for member in realized.members
    }
    expected_values = {
        "sender": "sender-complete",
        "receiver": _COORDINATOR_MESSAGE,
        "witness": True,
    }
    for member_id, value in expected_values.items():
        paths = realized_by_member[member_id]
        evidence = terminal_by_member[member_id]
        exact_bytes = json.dumps(
            value,
            ensure_ascii=False,
        ).encode("utf-8")
        assert paths.provisional_bundle_path.read_bytes() == exact_bytes
        assert evidence.frozen_bundle_sha256 == _sha256(exact_bytes)
        assert json.loads(
            paths.evidence_path.read_text(encoding="ascii")
        ) == evidence.to_dict()

    for member_id in ("sender", "witness"):
        paths = realized_by_member[member_id]
        rows = tuple(
            json.loads(line)
            for line in paths.injected_messages_path.read_text(
                encoding="ascii"
            ).splitlines()
        )
        assert tuple(row["row_kind"] for row in rows) == ("header",)
        assert inspect_peer_message_ledger(
            paths.injected_messages_path
        ) == terminal_by_member[member_id].ledger

    receiver_paths = realized_by_member["receiver"]
    receiver_rows = tuple(
        json.loads(line)
        for line in receiver_paths.injected_messages_path.read_text(
            encoding="ascii"
        ).splitlines()
    )
    assert tuple(row["row_kind"] for row in receiver_rows) == (
        "header",
        "recorded",
        "offered",
        "receiver_acknowledged",
    )
    _, recorded, offered, acknowledged = receiver_rows
    assert recorded["sender_attempt"] == (
        terminal_by_member["sender"].attempt.to_dict()
    )
    assert recorded["receiver_attempt"] == (
        terminal_by_member["receiver"].attempt.to_dict()
    )
    assert recorded["content"] == _COORDINATOR_MESSAGE
    assert offered["message_id"] == recorded["message_id"]
    assert acknowledged["message_id"] == recorded["message_id"]
    assert inspect_peer_message_ledger(
        receiver_paths.injected_messages_path
    ) == terminal_by_member["receiver"].ledger
    assert not list(run_root.rglob("*.sock"))

    capsys.readouterr()
    assert report_workflow(
        run_id=run_root.name,
        runs_root=str(state_dir),
        format="json",
    ) == 0
    report = json.loads(capsys.readouterr().out)
    [reported_step] = report["steps"]
    assert reported_step["kind"] == "provider_peer_group"
    assert (
        reported_step["output"]["debug"]["provider_peer_group"]
        == step["debug"]["provider_peer_group"]
    )
