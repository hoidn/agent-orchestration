"""Attempt-bound transport tests for provider peer-group clients."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from dataclasses import FrozenInstanceError
import json
import socket
from pathlib import Path
from threading import Event, Thread

import pytest

from orchestrator.workflow.provider_peer_group.models import (
    PeerAcknowledgeReceipt,
    PeerEndpointIdentity,
    PeerFinishReceipt,
    PeerGroupVisitIdentity,
    PeerReadyReceipt,
    PeerSendRequest,
    PeerSendReceipt,
)
from orchestrator.workflow.provider_peer_group.protocol import (
    ACTIVE_PEER_BINDING_ENV,
    PeerEndpointCloseProof,
    PeerProtocolClosedError,
    PeerProtocolEvent,
    PeerProtocolListener,
    encode_active_peer_binding,
    peer_ack,
    peer_finish,
    peer_ready,
    peer_send,
)


def _endpoint_identity() -> PeerEndpointIdentity:
    return PeerEndpointIdentity(
        group_visit=PeerGroupVisitIdentity(
            run_id="run-1",
            step_name="peer-step",
            node_id="node-1",
            visit_count=2,
        ),
        endpoint_instance_id="endpoint-1",
    )


def _environment(socket_path: Path) -> dict[str, str]:
    return {
        ACTIVE_PEER_BINDING_ENV: encode_active_peer_binding(
            socket_path=socket_path,
            sender_binding="opaque-member-1",
        )
    }


def _round_trip(
    listener: PeerProtocolListener,
    operation,
    receipt,
):
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(operation)
        event = listener.receive_event(timeout_sec=1)
        listener.resolve(event, receipt)
        return event, future.result(timeout=1)


def test_listener_binds_one_visit_identity_and_removes_its_socket(
    tmp_path: Path,
) -> None:
    socket_path = tmp_path / "peer.sock"
    identity = _endpoint_identity()

    with PeerProtocolListener(identity, socket_path) as listener:
        assert listener.endpoint_identity == identity
        assert listener.socket_path == socket_path
        assert socket_path.exists()

    assert not socket_path.exists()


def test_closing_an_unstarted_listener_does_not_unlink_an_unowned_path(
    tmp_path: Path,
) -> None:
    socket_path = tmp_path / "not-owned"
    socket_path.write_text("owner data", encoding="utf-8")
    listener = PeerProtocolListener(_endpoint_identity(), socket_path)

    listener.close()

    assert socket_path.read_text(encoding="utf-8") == "owner data"


def test_listener_start_failure_releases_its_socket_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from orchestrator.workflow.provider_peer_group import protocol

    socket_path = tmp_path / "peer.sock"
    listener = PeerProtocolListener(_endpoint_identity(), socket_path)

    def fail_start(_thread: Thread) -> None:
        raise RuntimeError("thread start failed")

    monkeypatch.setattr(protocol.Thread, "start", fail_start)

    with pytest.raises(RuntimeError, match="thread start failed"):
        listener.start()
    assert not socket_path.exists()
    listener.close()


def test_listener_close_wakes_a_coordinator_waiting_for_an_event(
    tmp_path: Path,
) -> None:
    listener = PeerProtocolListener(
        _endpoint_identity(),
        tmp_path / "peer.sock",
    )
    listener.start()
    outcomes: list[BaseException] = []

    def receive() -> None:
        try:
            listener.receive_event(timeout_sec=60)
        except BaseException as exc:
            outcomes.append(exc)

    thread = Thread(target=receive, daemon=True)
    thread.start()
    listener.close()
    thread.join(timeout=1)

    assert not thread.is_alive()
    assert len(outcomes) == 1
    assert isinstance(outcomes[0], PeerProtocolClosedError)


def test_listener_close_returns_cached_immutable_proof(
    tmp_path: Path,
) -> None:
    listener = PeerProtocolListener(
        _endpoint_identity(),
        tmp_path / "peer.sock",
    )
    listener.start()

    first = listener.close()
    second = listener.close()

    assert first is second
    assert first == PeerEndpointCloseProof(
        drained=True,
        closed=True,
        workers_joined=True,
    )
    with pytest.raises(FrozenInstanceError):
        first.closed = False  # type: ignore[misc]


def test_listener_close_joins_workers_without_a_silent_timeout(
    tmp_path: Path,
) -> None:
    class BlockingWorker:
        def __init__(self) -> None:
            self.join_timeouts: list[float | None] = []
            self.alive = True

        def join(self, timeout: float | None = None) -> None:
            self.join_timeouts.append(timeout)
            if timeout is None:
                self.alive = False

        def is_alive(self) -> bool:
            return self.alive

    listener = PeerProtocolListener(
        _endpoint_identity(),
        tmp_path / "peer.sock",
    )
    worker = BlockingWorker()
    listener._workers.add(worker)  # type: ignore[arg-type]

    proof = listener.close()

    assert worker.join_timeouts == [None]
    assert worker.is_alive() is False
    assert proof.workers_joined is True


def test_listener_close_serializes_with_event_publication(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    socket_path = tmp_path / "peer.sock"
    listener = PeerProtocolListener(_endpoint_identity(), socket_path)
    listener.start()
    publication_entered = Event()
    allow_publication = Event()
    original_put = listener._events.put

    def controlled_put(item, *args, **kwargs) -> None:
        if isinstance(item, PeerProtocolEvent):
            publication_entered.set()
            assert allow_publication.wait(1)
        original_put(item, *args, **kwargs)

    monkeypatch.setattr(listener._events, "put", controlled_put)
    with ThreadPoolExecutor(max_workers=2) as pool:
        client = pool.submit(
            peer_ready,
            request_id="request-publication-race",
            environ=_environment(socket_path),
        )
        assert publication_entered.wait(1)
        closing = pool.submit(listener.close)
        try:
            with pytest.raises(FutureTimeoutError):
                closing.result(timeout=0.05)
        finally:
            allow_publication.set()
        proof = closing.result(timeout=1)
        with pytest.raises(PeerProtocolClosedError):
            client.result(timeout=1)

    assert proof.drained is True
    assert listener._events.qsize() <= 1


def test_listener_close_serializes_with_worker_start(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    socket_path = tmp_path / "peer.sock"
    listener = PeerProtocolListener(_endpoint_identity(), socket_path)
    listener.start()
    worker_start_entered = Event()
    allow_worker_start = Event()
    original_start = Thread.start

    def controlled_start(thread: Thread) -> None:
        if thread.name == "provider-peer-request":
            worker_start_entered.set()
            assert allow_worker_start.wait(1)
        original_start(thread)

    monkeypatch.setattr(Thread, "start", controlled_start)
    with ThreadPoolExecutor(max_workers=2) as pool:
        client = pool.submit(
            peer_ready,
            request_id="request-worker-start-race",
            environ=_environment(socket_path),
        )
        assert worker_start_entered.wait(1)
        closing = pool.submit(listener.close)
        try:
            with pytest.raises(FutureTimeoutError):
                closing.result(timeout=0.05)
        finally:
            allow_worker_start.set()
        proof = closing.result(timeout=1)
        with pytest.raises(PeerProtocolClosedError):
            client.result(timeout=1)

    assert proof == PeerEndpointCloseProof(
        drained=True,
        closed=True,
        workers_joined=True,
    )


@pytest.mark.parametrize(
    ("operation", "expected_kind", "expected_fields", "receipt"),
    (
        (
            lambda env: peer_ready(request_id="request-ready", environ=env),
            "ready",
            {},
            PeerReadyReceipt("request-ready"),
        ),
        (
            lambda env: peer_send(
                target_binding="reviewer",
                message="hello\nλ",
                request_id="request-send",
                environ=env,
            ),
            "send",
            {"target_binding": "reviewer", "message": "hello\nλ"},
            PeerSendReceipt("request-send", "message-1"),
        ),
        (
            lambda env: peer_ack(
                message_id="message-1",
                request_id="request-ack",
                environ=env,
            ),
            "ack",
            {"message_id": "message-1"},
            PeerAcknowledgeReceipt("request-ack", "message-1"),
        ),
        (
            lambda env: peer_finish(
                request_id="request-finish",
                environ=env,
            ),
            "finish",
            {},
            PeerFinishReceipt.close_offered("request-finish"),
        ),
    ),
)
def test_thin_clients_use_only_the_opaque_environment_binding(
    tmp_path: Path,
    operation,
    expected_kind: str,
    expected_fields: dict[str, str],
    receipt,
) -> None:
    socket_path = tmp_path / "peer.sock"
    with PeerProtocolListener(_endpoint_identity(), socket_path) as listener:
        event, observed_receipt = _round_trip(
            listener,
            lambda: operation(_environment(socket_path)),
            receipt,
        )

    assert event.endpoint_identity == _endpoint_identity()
    assert event.request.kind == expected_kind
    assert event.request.sender_binding == "opaque-member-1"
    assert {
        field: getattr(event.request, field)
        for field in expected_fields
    } == expected_fields
    assert observed_receipt == receipt
    with pytest.raises(FrozenInstanceError):
        event.request = event.request  # type: ignore[misc]


def test_send_preserves_the_exact_65536_byte_utf8_boundary(
    tmp_path: Path,
) -> None:
    socket_path = tmp_path / "peer.sock"
    message = "λ" * 32_768
    with PeerProtocolListener(_endpoint_identity(), socket_path) as listener:
        event, receipt = _round_trip(
            listener,
            lambda: peer_send(
                target_binding="reviewer",
                message=message,
                request_id="request-boundary",
                environ=_environment(socket_path),
            ),
            PeerSendReceipt("request-boundary", "message-boundary"),
        )

    assert isinstance(event.request, PeerSendRequest)
    assert isinstance(receipt, PeerSendReceipt)
    assert event.request.message == message
    assert receipt.message_id == "message-boundary"

    with pytest.raises(ValueError, match="65,536"):
        peer_send(
            target_binding="reviewer",
            message=message + "x",
            request_id="request-oversize",
            environ=_environment(socket_path),
        )


def test_listener_rejects_noncanonical_unknown_and_incomplete_frames(
    tmp_path: Path,
) -> None:
    socket_path = tmp_path / "peer.sock"
    payload = {
        "schema_version": "provider_peer_protocol.v1",
        "kind": "ready",
        "request_id": "request-1",
        "sender_binding": "opaque-member-1",
    }
    bad_frames = (
        json.dumps(payload, indent=2).encode("utf-8") + b"\n",
        json.dumps({**payload, "extra": True}, sort_keys=True).encode("utf-8")
        + b"\n",
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        ),
    )

    with PeerProtocolListener(_endpoint_identity(), socket_path) as listener:
        for frame in bad_frames:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
                client.settimeout(1)
                client.connect(str(socket_path))
                client.sendall(frame)
                client.shutdown(socket.SHUT_WR)
                assert client.recv(1) == b""
        with pytest.raises(TimeoutError):
            listener.receive_event(timeout_sec=0.01)


def test_listener_close_resolves_every_waiting_client(
    tmp_path: Path,
) -> None:
    socket_path = tmp_path / "peer.sock"
    listener = PeerProtocolListener(_endpoint_identity(), socket_path)
    listener.start()
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(
            peer_ready,
            request_id="request-waiting",
            environ=_environment(socket_path),
        )
        listener.receive_event(timeout_sec=1)
        listener.close()
        with pytest.raises(PeerProtocolClosedError):
            future.result(timeout=1)


def test_client_fails_closed_for_missing_malformed_or_closed_binding(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match=ACTIVE_PEER_BINDING_ENV):
        peer_ready(request_id="request-1", environ={})
    with pytest.raises(ValueError, match=ACTIVE_PEER_BINDING_ENV):
        peer_ready(
            request_id="request-1",
            environ={ACTIVE_PEER_BINDING_ENV: "not-an-opaque-binding"},
        )
    closed_path = tmp_path / "closed.sock"
    with pytest.raises(PeerProtocolClosedError):
        peer_ready(
            request_id="request-1",
            environ=_environment(closed_path),
        )


def test_receipt_frame_is_canonical_and_client_rejects_wrong_request_id(
    tmp_path: Path,
) -> None:
    socket_path = tmp_path / "peer.sock"
    with PeerProtocolListener(_endpoint_identity(), socket_path) as listener:
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(
                peer_ready,
                request_id="request-1",
                environ=_environment(socket_path),
            )
            event = listener.receive_event(timeout_sec=1)
            with pytest.raises(ValueError, match="request_id"):
                listener.resolve(event, PeerReadyReceipt("other-request"))
            listener.resolve(event, PeerReadyReceipt("request-1"))
            assert event._response_sent.done()
            assert future.result(timeout=1) == PeerReadyReceipt("request-1")
