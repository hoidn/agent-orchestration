"""Attempt-bound provider materialization submit protocol contracts."""

from __future__ import annotations

from concurrent.futures import (
    Future,
    ThreadPoolExecutor,
    TimeoutError as FutureTimeout,
)
from dataclasses import FrozenInstanceError, replace
import base64
import hashlib
import json
from pathlib import Path
import socket
from threading import Event, Thread
import time

import pytest

from orchestrator.workflow.provider_phased_delivery.diagnostics import (
    DiagnosticSource,
    PhasedDeliveryDiagnostic,
    RejectedValue,
    diagnostic_definition,
)
from orchestrator.workflow.provider_phased_delivery.endpoint import (
    PhasedSubmitEndpoint,
    SubmitEndpointShutdownOutcome,
)
from orchestrator.workflow.provider_phased_delivery.models import SubmitReceipt
from orchestrator.workflow.provider_phased_delivery.protocol import (
    MAX_CLIENT_REQUEST_ID_BYTES,
    PHASED_PROVIDER_BINDING_ENV,
    PhasedSubmitProtocolClosedError,
    SubmitRequest,
    decode_submit_binding,
    derive_submit_binding_and_locator,
    receipt_from_dict,
    receipt_to_dict,
    send_submit_request,
    submit_materialization,
    _read_frame,
)


def _digest(byte: str) -> str:
    return "sha256:" + byte * 64


def _diagnostic(reason: str) -> PhasedDeliveryDiagnostic:
    definition = diagnostic_definition(reason)
    return PhasedDeliveryDiagnostic(
        code=definition.code,
        reason=reason,
        rejected_value=RejectedValue(
            type=definition.value_type,
            canonical_value=None,
            summary=reason,
        ),
        primary_source=DiagnosticSource(
            kind="runtime_attempt",
            owner="submit_endpoint",
            path=None,
            span=None,
        ),
        related_sources=(
            DiagnosticSource(
                kind="runtime_attempt",
                owner="runtime_step",
                path=None,
                span=None,
            ),
            DiagnosticSource(
                kind="runtime_attempt",
                owner="phase_lifecycle",
                path=None,
                span=None,
            ),
        ),
    )


def _receipt(
    request_id: str,
    *,
    ordinal: int = 1,
    status: str = "accepted_closing",
    total: int = 2,
    reason: str | None = None,
) -> SubmitReceipt:
    return SubmitReceipt(
        status=status,
        attempt_scope_sha256=_digest("a"),
        client_request_id=request_id,
        submission_ordinal=ordinal,
        configured_total=total,
        remaining_submissions=total - ordinal,
        diagnostic=None if reason is None else _diagnostic(reason),
    )


def _binding(tmp_path: Path, *, deadline: float | None = None):
    return derive_submit_binding_and_locator(
        attempt_scope_sha256=_digest("a"),
        socket_root=tmp_path,
        nonce="fixed-nonce",
        deadline=time.monotonic() + 10 if deadline is None else deadline,
    )


def _request(binding, request_id: str, *, payload: str = "0") -> SubmitRequest:
    return SubmitRequest(
        attempt_scope_sha256=binding.attempt_scope_sha256,
        endpoint_instance_id=binding.endpoint_instance_id,
        binding_token=binding.binding_token,
        client_request_id=request_id,
        payload_sha256=_digest(payload),
    )


def _open_endpoint(tmp_path: Path, *, total: int = 2):
    binding, locator = _binding(tmp_path)
    endpoint = PhasedSubmitEndpoint(
        binding=binding,
        locator=locator,
        configured_total=total,
    )
    endpoint.start()
    endpoint.open_admission("INITIAL_MATERIALIZATION_QUEUED")
    return binding, locator, endpoint


def test_binding_and_locator_derivation_is_frozen_and_fully_inert(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden(*_args, **_kwargs):
        raise AssertionError("derivation allocated an endpoint resource")

    monkeypatch.setattr("socket.socket", forbidden)
    monkeypatch.setattr("threading.Thread", forbidden)
    monkeypatch.setattr(Thread, "start", forbidden)
    monkeypatch.setattr(Path, "mkdir", forbidden)

    binding, locator = _binding(tmp_path)
    endpoint = PhasedSubmitEndpoint(
        binding=binding,
        locator=locator,
        configured_total=2,
    )

    assert binding.attempt_scope_sha256 == _digest("a")
    assert endpoint.binding is binding
    assert locator.socket_path == tmp_path / "phased-fixed-nonce.sock"
    assert not locator.socket_path.exists()
    with pytest.raises(FrozenInstanceError):
        binding.binding_token = "changed"  # type: ignore[misc]


def test_endpoint_binds_only_after_explicit_post_start_activation(
    tmp_path: Path,
) -> None:
    binding, locator = _binding(tmp_path)
    endpoint = PhasedSubmitEndpoint(
        binding=binding,
        locator=locator,
        configured_total=2,
    )

    assert not locator.socket_path.exists()
    endpoint.start()
    assert locator.socket_path.exists()

    outcome = endpoint.shutdown()
    assert outcome.endpoint_zero_survivor_proven is True
    assert not locator.socket_path.exists()


def test_endpoint_allocation_loses_an_existing_path_race(
    tmp_path: Path,
) -> None:
    binding, locator = _binding(tmp_path)
    locator.socket_path.write_text("other owner", encoding="utf-8")
    endpoint = PhasedSubmitEndpoint(
        binding=binding,
        locator=locator,
        configured_total=2,
    )

    with pytest.raises(FileExistsError):
        endpoint.start()
    outcome = endpoint.shutdown()

    assert locator.socket_path.read_text(encoding="utf-8") == "other owner"
    assert outcome.listener_closed is True
    assert outcome.endpoint_zero_survivor_proven is True


def test_partial_start_unlink_failure_is_retried_by_shutdown(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    binding, locator = _binding(tmp_path)
    endpoint = PhasedSubmitEndpoint(
        binding=binding,
        locator=locator,
        configured_total=2,
    )
    from orchestrator.workflow.provider_phased_delivery import endpoint as owner

    original_start = owner.Thread.start
    original_unlink = Path.unlink

    def fail_listener_start(thread: Thread) -> None:
        if thread.name.startswith("provider-phased-submit-listener-"):
            raise RuntimeError("listener thread start failed")
        original_start(thread)

    def fail_owned_unlink(path: Path, missing_ok: bool = False) -> None:
        if path == locator.socket_path:
            raise OSError("owned path unlink blocked")
        original_unlink(path, missing_ok=missing_ok)

    monkeypatch.setattr(owner.Thread, "start", fail_listener_start)
    monkeypatch.setattr(Path, "unlink", fail_owned_unlink)

    with pytest.raises(RuntimeError, match="listener thread start failed"):
        endpoint.start()

    assert locator.socket_path.exists()
    first = endpoint.shutdown()
    assert first.listener_closed is True
    assert first.endpoint_zero_survivor_proven is False
    assert locator.socket_path.exists()

    monkeypatch.setattr(Path, "unlink", original_unlink)
    second = endpoint.shutdown()
    assert second.listener_closed is True
    assert second.endpoint_zero_survivor_proven is True
    assert not locator.socket_path.exists()


def test_endpoint_start_requires_preexisting_root_and_leaves_none_on_failure(
    tmp_path: Path,
) -> None:
    missing_root = tmp_path / "not-created"
    binding, locator = derive_submit_binding_and_locator(
        attempt_scope_sha256=_digest("a"),
        socket_root=missing_root,
        nonce="missing-root",
        deadline=time.monotonic() + 10,
    )
    endpoint = PhasedSubmitEndpoint(
        binding=binding,
        locator=locator,
        configured_total=2,
    )

    with pytest.raises(OSError):
        endpoint.start()
    assert not missing_root.exists()


def test_request_worker_start_failure_closes_connection_and_cleans_sets(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    binding, _locator, endpoint = _open_endpoint(tmp_path)
    from orchestrator.workflow.provider_phased_delivery import endpoint as owner

    original_start = owner.Thread.start

    def fail_request_worker(thread: Thread) -> None:
        if thread.name == "provider-phased-submit-request":
            raise RuntimeError("worker start failed")
        original_start(thread)

    monkeypatch.setattr(owner.Thread, "start", fail_request_worker)
    connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    connection.connect(str(binding.socket_path))
    connection.sendall(
        _canonical_wire(
            _request(binding, "request-worker-start-fail").to_dict()
        )
    )
    connection.shutdown(socket.SHUT_WR)
    deadline = time.monotonic() + 1
    while endpoint._connections or endpoint._workers:
        assert time.monotonic() < deadline
        time.sleep(0.001)
    connection.close()

    assert endpoint._connections == set()
    assert endpoint._workers == set()
    endpoint.shutdown()


def test_submit_round_trip_binds_request_and_flushes_exact_receipt(
    tmp_path: Path,
) -> None:
    binding, _locator, endpoint = _open_endpoint(tmp_path)
    request = _request(binding, "request-1")

    with ThreadPoolExecutor(max_workers=1) as pool:
        client = pool.submit(send_submit_request, request, binding=binding)
        event = endpoint.receive_event()
        assert event.request == request
        assert event.submission_ordinal == 1
        receipt = _receipt(request.client_request_id)
        endpoint.resolve(event, receipt)
        assert client.result(timeout=1) == receipt

    endpoint.shutdown()


def test_environment_client_sends_the_constant_content_free_payload(
    tmp_path: Path,
) -> None:
    binding, _locator, endpoint = _open_endpoint(tmp_path)
    with ThreadPoolExecutor(max_workers=1) as pool:
        client = pool.submit(
            submit_materialization,
            request_id="request-environment-only",
            environ={
                PHASED_PROVIDER_BINDING_ENV: binding.opaque_value,
            },
        )
        event = endpoint.receive_event()
        assert event.request.payload_sha256 == (
            "sha256:"
            + hashlib.sha256(b"").hexdigest()
        )
        endpoint.resolve(
            event,
            _receipt(event.request.client_request_id),
        )
        assert client.result(timeout=1).status == "accepted_closing"
    endpoint.shutdown()


def test_exact_replay_returns_cached_receipt_without_new_event(
    tmp_path: Path,
) -> None:
    binding, _locator, endpoint = _open_endpoint(tmp_path)
    request = _request(binding, "request-replay")
    with ThreadPoolExecutor(max_workers=1) as pool:
        first = pool.submit(send_submit_request, request, binding=binding)
        event = endpoint.receive_event()
        receipt = _receipt(request.client_request_id)
        endpoint.resolve(event, receipt)
        assert first.result(timeout=1) == receipt

    assert send_submit_request(request, binding=binding) == receipt
    with pytest.raises(TimeoutError):
        endpoint.receive_event(deadline=time.monotonic() + 0.02)
    endpoint.shutdown()


def test_stopped_admission_wins_over_an_exact_prior_replay(
    tmp_path: Path,
) -> None:
    binding, _locator, endpoint = _open_endpoint(tmp_path)
    request = _request(binding, "request-stopped-replay")
    with ThreadPoolExecutor(max_workers=1) as pool:
        first = pool.submit(send_submit_request, request, binding=binding)
        event = endpoint.receive_event()
        accepted = _receipt(request.client_request_id)
        endpoint.resolve(event, accepted)
        assert first.result(timeout=1) == accepted

    endpoint.stop_admission()
    replay = send_submit_request(request, binding=binding)
    assert replay.status == "failed"
    assert replay.diagnostic is not None
    assert replay.diagnostic.reason == "submit_lifecycle_invalid"
    assert replay.submission_ordinal == 1
    endpoint.shutdown()


def test_changed_payload_replay_is_a_closed_conflict(
    tmp_path: Path,
) -> None:
    binding, _locator, endpoint = _open_endpoint(tmp_path)
    first_request = _request(binding, "request-conflict", payload="1")
    with ThreadPoolExecutor(max_workers=1) as pool:
        first = pool.submit(
            send_submit_request,
            first_request,
            binding=binding,
        )
        event = endpoint.receive_event()
        endpoint.resolve(event, _receipt(first_request.client_request_id))
        first.result(timeout=1)

    conflict = send_submit_request(
        _request(binding, "request-conflict", payload="2"),
        binding=binding,
    )
    assert conflict.status == "failed"
    assert conflict.diagnostic is not None
    assert conflict.diagnostic.reason == "submit_request_conflict"
    endpoint.shutdown()


def test_duplicate_in_flight_is_rejected_without_second_event(
    tmp_path: Path,
) -> None:
    binding, _locator, endpoint = _open_endpoint(tmp_path)
    request = _request(binding, "request-in-flight")
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(send_submit_request, request, binding=binding)
        event = endpoint.receive_event()
        duplicate = pool.submit(
            send_submit_request,
            request,
            binding=binding,
        ).result(timeout=1)
        assert duplicate.status == "failed"
        assert duplicate.diagnostic is not None
        assert duplicate.diagnostic.reason == "submit_duplicate_in_flight"
        endpoint.resolve(event, _receipt(request.client_request_id))
        first.result(timeout=1)

    with pytest.raises(TimeoutError):
        endpoint.receive_event(deadline=time.monotonic() + 0.02)
    endpoint.shutdown()


def test_failed_receipt_uses_active_request_ordinal_during_overlap(
    tmp_path: Path,
) -> None:
    binding, _locator, endpoint = _open_endpoint(tmp_path)
    active_request = _request(binding, "request-active-ordinal")
    with ThreadPoolExecutor(max_workers=2) as pool:
        active = pool.submit(
            send_submit_request,
            active_request,
            binding=binding,
        )
        event = endpoint.receive_event()
        foreign_binding = replace(
            binding,
            binding_token="f" * 64,
        )
        foreign = pool.submit(
            send_submit_request,
            _request(foreign_binding, "request-foreign-overlap"),
            binding=replace(
                foreign_binding,
                socket_path=binding.socket_path,
            ),
        ).result(timeout=1)

        assert event.submission_ordinal == 1
        assert foreign.submission_ordinal == 1
        endpoint.resolve(event, _receipt(active_request.client_request_id))
        active.result(timeout=1)
    endpoint.shutdown()


@pytest.mark.parametrize(
    ("mutation", "reason"),
    (
        (
            lambda binding: replace(
                binding,
                attempt_scope_sha256=_digest("b"),
            ),
            "submit_binding_foreign",
        ),
        (
            lambda binding: replace(
                binding,
                binding_token="f" * 64,
            ),
            "submit_binding_foreign",
        ),
        (
            lambda binding: replace(
                binding,
                endpoint_instance_id="stale-endpoint",
            ),
            "submit_binding_stale",
        ),
    ),
)
def test_binding_diagnostic_precedes_distinct_in_flight_duplicate(
    tmp_path: Path,
    mutation,
    reason: str,
) -> None:
    binding, _locator, endpoint = _open_endpoint(tmp_path)
    active_request = _request(binding, "request-active-precedence")
    with ThreadPoolExecutor(max_workers=2) as pool:
        active = pool.submit(
            send_submit_request,
            active_request,
            binding=binding,
        )
        event = endpoint.receive_event()
        altered = mutation(binding)
        raw = pool.submit(
            _raw_exchange,
            binding,
            (
                _canonical_wire(
                    _request(
                        altered,
                        f"request-{reason}-overlap",
                    ).to_dict()
                ),
            ),
        ).result(timeout=1)
        rejected = json.loads(raw)
        endpoint.resolve(event, _receipt(active_request.client_request_id))
        active.result(timeout=1)
        assert rejected["diagnostic"]["reason"] == reason
        assert rejected["submission_ordinal"] == 1
    endpoint.shutdown()


@pytest.mark.parametrize(
    ("mutation", "reason"),
    (
        (
            lambda binding: replace(
                binding,
                attempt_scope_sha256=_digest("b"),
            ),
            "submit_binding_foreign",
        ),
        (
            lambda binding: replace(
                binding,
                binding_token="f" * 64,
            ),
            "submit_binding_foreign",
        ),
        (
            lambda binding: replace(
                binding,
                endpoint_instance_id="stale-endpoint",
            ),
            "submit_binding_stale",
        ),
    ),
)
def test_binding_diagnostic_precedes_same_id_in_flight_conflict(
    tmp_path: Path,
    mutation,
    reason: str,
) -> None:
    binding, _locator, endpoint = _open_endpoint(tmp_path)
    request_id = "request-same-id-binding"
    active_request = _request(binding, request_id)
    with ThreadPoolExecutor(max_workers=2) as pool:
        active = pool.submit(
            send_submit_request,
            active_request,
            binding=binding,
        )
        event = endpoint.receive_event()
        altered = mutation(binding)
        raw = pool.submit(
            _raw_exchange,
            binding,
            (
                _canonical_wire(
                    _request(altered, request_id).to_dict()
                ),
            ),
        ).result(timeout=1)
        rejected = json.loads(raw)
        endpoint.resolve(event, _receipt(request_id))
        active.result(timeout=1)
        assert rejected["diagnostic"]["reason"] == reason
        assert rejected["submission_ordinal"] == 1
    endpoint.shutdown()


@pytest.mark.parametrize(
    ("mutation", "reason"),
    (
        (
            lambda binding: replace(
                binding,
                endpoint_instance_id="stale-endpoint",
            ),
            "submit_binding_stale",
        ),
        (
            lambda binding: replace(
                binding,
                binding_token="f" * 64,
            ),
            "submit_binding_foreign",
        ),
    ),
)
def test_foreign_and_stale_bindings_fail_closed(
    tmp_path: Path,
    mutation,
    reason: str,
) -> None:
    binding, _locator, endpoint = _open_endpoint(tmp_path)
    altered = mutation(binding)
    request = _request(altered, f"request-{reason}")
    receipt = send_submit_request(
        request,
        binding=replace(altered, socket_path=binding.socket_path),
    )

    assert receipt.status == "failed"
    assert receipt.diagnostic is not None
    assert receipt.diagnostic.reason == reason
    endpoint.shutdown()


def test_foreign_attempt_scope_receipt_is_rejected_by_client(
    tmp_path: Path,
) -> None:
    binding, _locator, endpoint = _open_endpoint(tmp_path)
    altered = replace(
        binding,
        attempt_scope_sha256=_digest("b"),
    )
    with pytest.raises(PhasedSubmitProtocolClosedError):
        send_submit_request(
            _request(altered, "request-foreign-scope"),
            binding=replace(altered, socket_path=binding.socket_path),
        )
    endpoint.shutdown()


def test_distinct_overlap_and_closed_replay_rules_survive_without_retry_rearm(
    tmp_path: Path,
) -> None:
    binding, _locator, endpoint = _open_endpoint(tmp_path)
    first_request = _request(binding, "request-first")
    second_request = _request(binding, "request-second")
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(
            send_submit_request,
            first_request,
            binding=binding,
        )
        first_event = endpoint.receive_event()
        second = pool.submit(
            send_submit_request,
            second_request,
            binding=binding,
        )
        rejected = second.result(timeout=1)
        assert rejected.status == "failed"
        assert rejected.submission_ordinal == 1
        assert rejected.diagnostic is not None
        assert rejected.diagnostic.reason == "submit_duplicate_in_flight"
        endpoint.resolve(
            first_event,
            _receipt(
                "request-first",
                ordinal=1,
                status="retry_queued",
            ),
        )
        assert first.result(timeout=1).client_request_id == "request-first"

    replay = send_submit_request(first_request, binding=binding)
    assert replay.status == "retry_queued"
    conflict = send_submit_request(
        _request(binding, "request-first", payload="1"),
        binding=binding,
    )
    assert conflict.diagnostic is not None
    assert conflict.diagnostic.reason == "submit_request_conflict"
    foreign_while_closed = replace(binding, binding_token="f" * 64)
    transient = send_submit_request(
        _request(foreign_while_closed, "request-transient-closed"),
        binding=replace(
            foreign_while_closed,
            socket_path=binding.socket_path,
        ),
    )
    assert transient.diagnostic is not None
    assert transient.diagnostic.reason == "submit_lifecycle_invalid"
    closed_distinct = send_submit_request(
        second_request,
        binding=binding,
    )
    assert closed_distinct.diagnostic is not None
    assert closed_distinct.diagnostic.reason == "submit_lifecycle_invalid"
    assert closed_distinct.submission_ordinal == 1
    endpoint.shutdown()


def test_retry_receipt_atomically_arms_next_distinct_request(
    tmp_path: Path,
) -> None:
    binding, _locator, endpoint = _open_endpoint(tmp_path)
    first_request = _request(binding, "request-first-retry")
    second_request = _request(binding, "request-second-retry")

    def submit_both() -> tuple[SubmitReceipt, SubmitReceipt]:
        first = send_submit_request(first_request, binding=binding)
        second = send_submit_request(second_request, binding=binding)
        return first, second

    with ThreadPoolExecutor(max_workers=1) as pool:
        client = pool.submit(submit_both)
        first_event = endpoint.receive_event()
        endpoint.resolve(
            first_event,
            _receipt(
                first_request.client_request_id,
                ordinal=1,
                status="retry_queued",
            ),
            rearm_retry=True,
        )

        second_event = endpoint.receive_event()
        assert second_event.request == second_request
        assert second_event.submission_ordinal == 2
        endpoint.resolve(
            second_event,
            _receipt(
                second_request.client_request_id,
                ordinal=2,
            ),
        )
        first_receipt, second_receipt = client.result(timeout=1)

    assert first_receipt.status == "retry_queued"
    assert second_receipt.status == "accepted_closing"
    endpoint.shutdown()


def test_stop_before_retry_visibility_replaces_unsent_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from orchestrator.workflow.provider_phased_delivery import endpoint as owner

    receipt_selected = Event()
    allow_visibility = Event()

    class ReceiptSelectionGate(Future[object]):
        def result(self, timeout: float | None = None) -> object:
            value = super().result(timeout=timeout)
            if isinstance(value, SubmitReceipt):
                receipt_selected.set()
                assert allow_visibility.wait(1)
            return value

    monkeypatch.setattr(owner, "Future", ReceiptSelectionGate)
    binding, _locator, endpoint = _open_endpoint(tmp_path)
    request = _request(binding, "request-stop-before-retry-visible")
    retry_receipt = _receipt(
        request.client_request_id,
        ordinal=1,
        status="retry_queued",
    )

    with ThreadPoolExecutor(max_workers=2) as pool:
        client = pool.submit(send_submit_request, request, binding=binding)
        event = endpoint.receive_event()
        resolving = pool.submit(
            endpoint.resolve,
            event,
            retry_receipt,
            rearm_retry=True,
        )
        try:
            assert receipt_selected.wait(1)
            endpoint.stop_admission()
        finally:
            allow_visibility.set()
        observed = client.result(timeout=1)
        resolving.result(timeout=1)

    assert observed.status == "failed"
    assert observed.diagnostic is not None
    assert observed.diagnostic.reason == "submit_lifecycle_invalid"
    assert endpoint._records[request.client_request_id].receipt == observed
    assert endpoint._admission_open is False
    assert send_submit_request(request, binding=binding) == observed
    later = send_submit_request(
        _request(binding, "request-after-stop-won"),
        binding=binding,
    )
    assert later.diagnostic is not None
    assert later.diagnostic.reason == "submit_lifecycle_invalid"
    endpoint.shutdown()


def test_wrong_lifecycle_and_stopped_admission_return_failed_receipts(
    tmp_path: Path,
) -> None:
    binding, locator = _binding(tmp_path)
    endpoint = PhasedSubmitEndpoint(
        binding=binding,
        locator=locator,
        configured_total=2,
    )
    endpoint.start()
    request = _request(binding, "request-wrong-lifecycle")

    wrong = send_submit_request(request, binding=binding)
    assert wrong.status == "failed"
    assert wrong.diagnostic is not None
    assert wrong.diagnostic.reason == "submit_lifecycle_invalid"

    endpoint.open_admission("INITIAL_MATERIALIZATION_QUEUED")
    endpoint.stop_admission()
    late = send_submit_request(
        _request(binding, "request-late"),
        binding=binding,
    )
    assert late.status == "failed"
    assert late.diagnostic is not None
    assert late.diagnostic.reason == "submit_lifecycle_invalid"
    endpoint.shutdown()


def test_stopped_admission_cannot_be_reopened(
    tmp_path: Path,
) -> None:
    _binding_value, _locator, endpoint = _open_endpoint(tmp_path)
    endpoint.stop_admission()

    with pytest.raises(RuntimeError, match="permanently stopped"):
        endpoint.open_admission("RETRY_QUEUED")
    endpoint.shutdown()


def test_stop_admission_rejects_active_request_and_overlap_is_not_queued(
    tmp_path: Path,
) -> None:
    binding, _locator, endpoint = _open_endpoint(tmp_path)
    with ThreadPoolExecutor(max_workers=2) as pool:
        active = pool.submit(
            send_submit_request,
            _request(binding, "request-active"),
            binding=binding,
        )
        endpoint.receive_event()
        queued = pool.submit(
            send_submit_request,
            _request(binding, "request-queued"),
            binding=binding,
        )
        overlap_receipt = queued.result(timeout=1)
        assert overlap_receipt.diagnostic is not None
        assert overlap_receipt.diagnostic.reason == (
            "submit_duplicate_in_flight"
        )
        endpoint.stop_admission()
        active_receipt = active.result(timeout=1)

    assert active_receipt.diagnostic is not None
    assert active_receipt.diagnostic.reason == "submit_lifecycle_invalid"
    outcome = endpoint.shutdown()
    assert outcome.active_requests_drained == 1
    assert outcome.queued_requests_rejected == 0


def test_stop_admission_rejects_pending_request_before_listener_close(
    tmp_path: Path,
) -> None:
    binding, _locator, endpoint = _open_endpoint(tmp_path)
    with ThreadPoolExecutor(max_workers=1) as pool:
        queued = pool.submit(
            send_submit_request,
            _request(binding, "request-pending"),
            binding=binding,
        )
        deadline = time.monotonic() + 1
        while "request-pending" not in endpoint._records:
            assert time.monotonic() < deadline
            time.sleep(0.001)
        endpoint.stop_admission()
        queued_receipt = queued.result(timeout=1)

    assert queued_receipt.diagnostic is not None
    assert queued_receipt.diagnostic.reason == "submit_lifecycle_invalid"
    late = send_submit_request(
        _request(binding, "request-after-stop"),
        binding=binding,
    )
    assert late.diagnostic is not None
    assert late.diagnostic.reason == "submit_lifecycle_invalid"
    outcome = endpoint.shutdown()
    assert outcome.active_requests_drained == 0
    assert outcome.queued_requests_rejected == 1


def test_receipt_flush_failure_is_a_closed_protocol_error(
    tmp_path: Path,
) -> None:
    binding, _locator, endpoint = _open_endpoint(tmp_path)
    request = _request(binding, "request-disconnected")
    connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    connection.connect(str(binding.socket_path))
    connection.sendall(_canonical_wire(request.to_dict()))
    connection.shutdown(socket.SHUT_WR)
    event = endpoint.receive_event()
    connection.close()

    with pytest.raises(PhasedSubmitProtocolClosedError):
        endpoint.resolve(
            event,
            _receipt(
                request.client_request_id,
                status="retry_queued",
            ),
            rearm_retry=True,
        )
    recorded = endpoint._records[request.client_request_id].receipt
    assert recorded is not None
    assert recorded.status == "retry_queued"
    assert recorded.submission_ordinal == 1
    assert recorded.diagnostic is None
    assert endpoint._records[request.client_request_id].rearm_retry is True
    assert endpoint._admission_open is True
    assert endpoint._lifecycle == "RETRY_QUEUED"
    assert send_submit_request(request, binding=binding) == recorded

    next_request = _request(binding, "request-after-flush-failure")
    with ThreadPoolExecutor(max_workers=1) as pool:
        client = pool.submit(
            send_submit_request,
            next_request,
            binding=binding,
        )
        next_event = endpoint.receive_event()
        assert next_event.request == next_request
        assert next_event.submission_ordinal == 2
        endpoint.resolve(
            next_event,
            _receipt(next_request.client_request_id, ordinal=2),
        )
        assert client.result(timeout=1).status == "accepted_closing"

    endpoint.stop_admission()
    endpoint.shutdown()


def test_write_shutdown_failure_after_send_preserves_visible_retry_arm(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from orchestrator.workflow.provider_phased_delivery import endpoint as owner

    original_shutdown_write = (
        lambda connection: connection.shutdown(socket.SHUT_WR)
    )
    shutdown_calls = 0

    def fail_first_shutdown_write(connection: socket.socket) -> None:
        nonlocal shutdown_calls
        shutdown_calls += 1
        if shutdown_calls == 1:
            raise OSError("write shutdown failed after send")
        original_shutdown_write(connection)

    monkeypatch.setattr(
        owner,
        "_shutdown_write",
        fail_first_shutdown_write,
        raising=False,
    )
    binding, _locator, endpoint = _open_endpoint(tmp_path)
    request = _request(binding, "request-shutdown-write-failure")
    retry_receipt = _receipt(
        request.client_request_id,
        status="retry_queued",
    )

    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            client = pool.submit(
                send_submit_request,
                request,
                binding=binding,
            )
            event = endpoint.receive_event()
            with pytest.raises(PhasedSubmitProtocolClosedError):
                endpoint.resolve(
                    event,
                    retry_receipt,
                    rearm_retry=True,
                )
            assert client.result(timeout=1) == retry_receipt

        record = endpoint._records[request.client_request_id]
        assert record.receipt == retry_receipt
        assert record.rearm_retry is True
        assert endpoint._admission_open is True
        assert endpoint._lifecycle == "RETRY_QUEUED"

        next_request = _request(binding, "request-after-shutdown-failure")
        with ThreadPoolExecutor(max_workers=1) as pool:
            client = pool.submit(
                send_submit_request,
                next_request,
                binding=binding,
            )
            next_event = endpoint.receive_event()
            assert next_event.request == next_request
            assert next_event.submission_ordinal == 2
            endpoint.resolve(
                next_event,
                _receipt(next_request.client_request_id, ordinal=2),
            )
            assert client.result(timeout=1).status == "accepted_closing"
    finally:
        endpoint.stop_admission()
        endpoint.shutdown()


@pytest.mark.parametrize(
    ("status", "reason"),
    (
        ("accepted_closing", None),
        ("failed", "submit_lifecycle_invalid"),
    ),
)
def test_non_retry_receipt_cannot_intentionally_rearm_admission(
    tmp_path: Path,
    status: str,
    reason: str | None,
) -> None:
    binding, _locator, endpoint = _open_endpoint(tmp_path)
    request = _request(binding, f"request-non-retry-{status}")
    receipt = _receipt(
        request.client_request_id,
        status=status,
        reason=reason,
    )
    with ThreadPoolExecutor(max_workers=1) as pool:
        client = pool.submit(send_submit_request, request, binding=binding)
        event = endpoint.receive_event()
        with pytest.raises(ValueError, match="retry_queued"):
            endpoint.resolve(event, receipt, rearm_retry=True)
        endpoint.resolve(event, receipt)
        assert client.result(timeout=1) == receipt

    next_receipt = send_submit_request(
        _request(binding, f"request-after-{status}"),
        binding=binding,
    )
    assert next_receipt.diagnostic is not None
    assert next_receipt.diagnostic.reason == "submit_lifecycle_invalid"
    endpoint.shutdown()


def test_client_rejects_receipt_for_different_attempt_scope(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    binding, _locator, endpoint = _open_endpoint(tmp_path)
    from orchestrator.workflow.provider_phased_delivery import endpoint as owner

    original_projection = owner.receipt_to_dict

    def mismatched_scope(receipt: SubmitReceipt) -> dict[str, object]:
        projected = original_projection(receipt)
        projected["attempt_scope_sha256"] = _digest("b")
        return projected

    monkeypatch.setattr(owner, "receipt_to_dict", mismatched_scope)
    request = _request(binding, "request-scope-mismatch")
    with ThreadPoolExecutor(max_workers=2) as pool:
        client = pool.submit(send_submit_request, request, binding=binding)
        event = endpoint.receive_event()
        resolving = pool.submit(
            endpoint.resolve,
            event,
            _receipt(request.client_request_id),
        )
        with pytest.raises(PhasedSubmitProtocolClosedError):
            client.result(timeout=1)
        resolving.result(timeout=1)
    endpoint.shutdown()


def test_successfully_flushed_accepted_closing_counts_as_active_drained(
    tmp_path: Path,
) -> None:
    binding, _locator, endpoint = _open_endpoint(tmp_path)
    with ThreadPoolExecutor(max_workers=1) as pool:
        client = pool.submit(
            send_submit_request,
            _request(binding, "request-accepted-drain"),
            binding=binding,
        )
        event = endpoint.receive_event()
        endpoint.resolve(
            event,
            _receipt(event.request.client_request_id),
        )
        client.result(timeout=1)

    outcome = endpoint.shutdown()
    assert outcome.active_requests_drained == 1


def test_retry_receipt_does_not_count_as_active_drained(
    tmp_path: Path,
) -> None:
    binding, _locator, endpoint = _open_endpoint(tmp_path)
    with ThreadPoolExecutor(max_workers=1) as pool:
        client = pool.submit(
            send_submit_request,
            _request(binding, "request-retry-not-drained"),
            binding=binding,
        )
        event = endpoint.receive_event()
        endpoint.resolve(
            event,
            _receipt(
                event.request.client_request_id,
                status="retry_queued",
            ),
        )
        client.result(timeout=1)

    outcome = endpoint.shutdown()
    assert outcome.active_requests_drained == 0


def test_shutdown_returns_cached_truthful_complete_outcome(
    tmp_path: Path,
) -> None:
    _binding_value, locator, endpoint = _open_endpoint(tmp_path)

    first = endpoint.shutdown()
    second = endpoint.shutdown()

    assert first is second
    assert first == SubmitEndpointShutdownOutcome(
        queued_requests_rejected=0,
        active_requests_drained=0,
        listener_closed=True,
        workers_joined=0,
        endpoint_zero_survivor_proven=True,
    )
    assert not locator.socket_path.exists()


def test_shutdown_unlink_failure_is_incomplete_and_retried(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _binding_value, locator, endpoint = _open_endpoint(tmp_path)
    original_unlink = Path.unlink

    def fail_owned_unlink(path: Path, missing_ok: bool = False) -> None:
        if path == locator.socket_path:
            raise OSError("owned path unlink blocked")
        original_unlink(path, missing_ok=missing_ok)

    monkeypatch.setattr(Path, "unlink", fail_owned_unlink)

    first = endpoint.shutdown()
    assert first.listener_closed is True
    assert first.endpoint_zero_survivor_proven is False
    assert locator.socket_path.exists()

    monkeypatch.setattr(Path, "unlink", original_unlink)
    second = endpoint.shutdown()
    assert second.listener_closed is True
    assert second.endpoint_zero_survivor_proven is True
    assert not locator.socket_path.exists()


def test_concurrent_shutdown_serializes_one_accounting_pass(
    tmp_path: Path,
) -> None:
    _binding_value, _locator, endpoint = _open_endpoint(tmp_path)
    join_entered = Event()
    allow_join = Event()

    class BarrierWorker:
        alive = True
        join_calls = 0

        def join(self, timeout: float | None = None) -> None:
            assert timeout is not None
            self.join_calls += 1
            join_entered.set()
            assert allow_join.wait(1)
            self.alive = False

        def is_alive(self) -> bool:
            return self.alive

    worker = BarrierWorker()
    endpoint._workers.add(worker)  # type: ignore[arg-type]
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(endpoint.shutdown)
        assert join_entered.wait(1)
        second = pool.submit(endpoint.shutdown)
        with pytest.raises(FutureTimeout):
            second.result(timeout=0.02)
        allow_join.set()
        first_outcome = first.result(timeout=1)
        second_outcome = second.result(timeout=1)

    assert worker.join_calls == 1
    assert first_outcome is second_outcome
    assert first_outcome.endpoint_zero_survivor_proven is True


def test_shutdown_uses_stable_worker_snapshot_for_liveness_accounting(
    tmp_path: Path,
) -> None:
    _binding_value, _locator, endpoint = _open_endpoint(tmp_path)

    class SelfDiscardingWorker:
        joined = False

        def join(self, timeout: float | None = None) -> None:
            assert timeout is not None
            self.joined = True

        def is_alive(self) -> bool:
            endpoint._workers.discard(self)  # type: ignore[arg-type]
            return not self.joined

    worker = SelfDiscardingWorker()
    endpoint._workers.add(worker)  # type: ignore[arg-type]
    endpoint._worker_count = 1

    outcome = endpoint.shutdown()

    assert worker.joined is True
    assert outcome.workers_joined == 1
    assert outcome.listener_closed is True
    assert outcome.endpoint_zero_survivor_proven is True


def test_shutdown_deadline_reports_incomplete_worker_join_truthfully(
    tmp_path: Path,
) -> None:
    _binding_value, _locator, endpoint = _open_endpoint(tmp_path)

    class Survivor:
        def join(self, timeout: float | None = None) -> None:
            assert timeout is not None

        def is_alive(self) -> bool:
            return True

    endpoint._workers.add(Survivor())  # type: ignore[arg-type]
    outcome = endpoint.shutdown(deadline=time.monotonic() + 0.02)

    assert outcome.endpoint_zero_survivor_proven is False
    assert outcome.listener_closed is True
    assert outcome.workers_joined == 0


def test_shutdown_waits_for_active_receipt_flush_and_worker_exit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    binding, _locator, endpoint = _open_endpoint(tmp_path)
    request = _request(binding, "request-flush-barrier")
    send_entered = Event()
    allow_send = Event()
    from orchestrator.workflow.provider_phased_delivery import endpoint as owner

    original_canonical = owner._canonical

    def blocked_receipt_frame(value) -> bytes:
        if (
            value.get("schema_version")
            == "provider_phased_submit_receipt.v1"
            and value.get("client_request_id")
            == request.client_request_id
        ):
            send_entered.set()
            assert allow_send.wait(5)
        return original_canonical(value)

    monkeypatch.setattr(owner, "_canonical", blocked_receipt_frame)
    with ThreadPoolExecutor(max_workers=3) as pool:
        client = pool.submit(send_submit_request, request, binding=binding)
        event = endpoint.receive_event()
        resolving = pool.submit(
            endpoint.resolve,
            event,
            _receipt(request.client_request_id),
        )
        assert send_entered.wait(1)
        overlap = pool.submit(
            send_submit_request,
            _request(binding, "request-during-flush"),
            binding=binding,
        ).result(timeout=1)
        assert overlap.diagnostic is not None
        assert overlap.diagnostic.reason == "submit_duplicate_in_flight"
        closing = pool.submit(endpoint.shutdown)
        with pytest.raises(FutureTimeout):
            closing.result(timeout=0.02)
        allow_send.set()
        resolving.result(timeout=1)
        client.result(timeout=1)
        assert closing.result(timeout=1).endpoint_zero_survivor_proven is True


def test_all_client_and_owner_waits_fail_at_the_shared_attempt_deadline(
    tmp_path: Path,
) -> None:
    expired = time.monotonic() - 1
    binding, locator = _binding(tmp_path, deadline=expired)
    endpoint = PhasedSubmitEndpoint(
        binding=binding,
        locator=locator,
        configured_total=2,
    )

    with pytest.raises(TimeoutError):
        endpoint.start()
    with pytest.raises(PhasedSubmitProtocolClosedError):
        submit_materialization(
            request_id="expired-request",
            environ={
                PHASED_PROVIDER_BINDING_ENV: binding.opaque_value,
            },
        )


def test_fully_decoded_request_at_deadline_gets_before_submit_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    binding, _locator, endpoint = _open_endpoint(tmp_path)
    from orchestrator.workflow.provider_phased_delivery import endpoint as owner

    monkeypatch.setattr(
        owner,
        "_monotonic_now",
        lambda: binding.deadline,
    )
    receipt = send_submit_request(
        _request(binding, "request-before-submit-deadline"),
        binding=binding,
    )

    assert receipt.diagnostic is not None
    assert receipt.diagnostic.reason == "deadline_exhausted_before_submit"
    assert endpoint._records == {}
    assert endpoint._next_ordinal == 1
    endpoint.shutdown()


def test_submit_after_check_crossing_deadline_commits_no_admission(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    binding, _locator, endpoint = _open_endpoint(tmp_path)
    from orchestrator.workflow.provider_phased_delivery import endpoint as owner

    observations = iter(
        (binding.deadline - 1, binding.deadline)
    )
    monkeypatch.setattr(
        owner,
        "_monotonic_now",
        lambda: next(observations),
    )
    receipt = send_submit_request(
        _request(binding, "request-during-submit-deadline"),
        binding=binding,
    )

    assert receipt.diagnostic is not None
    assert receipt.diagnostic.reason == "deadline_exhausted_during_submit"
    assert endpoint._records == {}
    assert endpoint._next_ordinal == 1
    endpoint.shutdown()


def test_open_admission_cannot_reopen_at_shared_deadline(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    binding, locator = _binding(tmp_path)
    endpoint = PhasedSubmitEndpoint(
        binding=binding,
        locator=locator,
        configured_total=2,
    )
    endpoint.start()
    from orchestrator.workflow.provider_phased_delivery import endpoint as owner

    monkeypatch.setattr(
        owner,
        "_monotonic_now",
        lambda: binding.deadline,
    )
    with pytest.raises(TimeoutError):
        endpoint.open_admission("INITIAL_MATERIALIZATION_QUEUED")
    endpoint.shutdown()


def _canonical_wire(value: dict[str, object]) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("ascii")
        + b"\n"
    )


def _raw_exchange(binding, chunks: tuple[bytes, ...]) -> bytes:
    connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    connection.settimeout(1)
    try:
        connection.connect(str(binding.socket_path))
        for chunk in chunks:
            connection.sendall(chunk)
        connection.shutdown(socket.SHUT_WR)
        try:
            return connection.recv(262_144)
        except ConnectionResetError:
            return b""
    finally:
        connection.close()


@pytest.mark.parametrize(
    "mutate",
    (
        lambda value: value.pop("payload_sha256"),
        lambda value: value.__setitem__("extra", None),
        lambda value: value.__setitem__("schema_version", "unknown.v1"),
        lambda value: value.__setitem__("payload_sha256", True),
    ),
)
def test_request_wire_rejects_missing_extra_unknown_and_boolean_fields(
    tmp_path: Path,
    mutate,
) -> None:
    binding, _locator, endpoint = _open_endpoint(tmp_path)
    value = _request(binding, "request-invalid-wire").to_dict()
    mutate(value)

    assert _raw_exchange(binding, (_canonical_wire(value),)) == b""
    endpoint.shutdown()


def test_request_wire_rejects_oversize_and_trailing_frames(
    tmp_path: Path,
) -> None:
    binding, _locator, endpoint = _open_endpoint(tmp_path)

    assert _raw_exchange(binding, (b"x" * 300_000 + b"\n",)) == b""
    request = _canonical_wire(
        _request(binding, "request-trailing-wire").to_dict()
    )
    assert _raw_exchange(binding, (request + request,)) == b""
    endpoint.shutdown()


def test_read_frame_rejects_trailing_frame_arriving_after_first_packet(
    tmp_path: Path,
) -> None:
    del tmp_path
    reader, writer = socket.socketpair()
    deadline = time.monotonic() + 1
    with ThreadPoolExecutor(max_workers=1) as pool:
        result = pool.submit(_read_frame, reader, deadline=deadline)
        writer.sendall(b'{"one":1}\n')
        time.sleep(0.02)
        writer.sendall(b'{"two":2}\n')
        writer.shutdown(socket.SHUT_WR)
        with pytest.raises(ValueError, match="exactly one frame"):
            result.result(timeout=1)
    reader.close()
    writer.close()


def test_fragmented_canonical_request_is_one_normal_submission(
    tmp_path: Path,
) -> None:
    binding, _locator, endpoint = _open_endpoint(tmp_path)
    request = _request(binding, "request-fragmented")
    frame = _canonical_wire(request.to_dict())
    with ThreadPoolExecutor(max_workers=1) as pool:
        client = pool.submit(
            _raw_exchange,
            binding,
            (frame[:3], frame[3:17], frame[17:]),
        )
        event = endpoint.receive_event()
        endpoint.resolve(event, _receipt(request.client_request_id))
        receipt = json.loads(client.result(timeout=1))

    assert receipt["client_request_id"] == request.client_request_id
    endpoint.shutdown()


@pytest.mark.parametrize(
    "mutate",
    (
        lambda value: value.pop("binding_token"),
        lambda value: value.__setitem__("extra", None),
        lambda value: value.__setitem__("schema_version", "unknown.v1"),
        lambda value: value.__setitem__("deadline", True),
    ),
)
def test_environment_binding_is_closed_canonical_and_typed(
    tmp_path: Path,
    mutate,
) -> None:
    binding, _locator = _binding(tmp_path)
    padding = "=" * (-len(binding.opaque_value) % 4)
    value = json.loads(
        base64.urlsafe_b64decode(binding.opaque_value + padding)
    )
    mutate(value)
    encoded = base64.urlsafe_b64encode(
        _canonical_wire(value)[:-1]
    ).decode("ascii").rstrip("=")

    with pytest.raises(ValueError):
        decode_submit_binding(
            {PHASED_PROVIDER_BINDING_ENV: encoded}
        )


def test_environment_binding_rejects_oversized_encoded_input() -> None:
    with pytest.raises(ValueError):
        decode_submit_binding(
            {PHASED_PROVIDER_BINDING_ENV: "a" * 20_000}
        )


def test_environment_binding_rejects_padded_base64_alias(
    tmp_path: Path,
) -> None:
    binding, _locator = _binding(tmp_path)
    padding = "=" * (-len(binding.opaque_value) % 4) or "="

    with pytest.raises(ValueError):
        decode_submit_binding(
            {
                PHASED_PROVIDER_BINDING_ENV: (
                    binding.opaque_value + padding
                )
            }
        )


def test_environment_binding_rejects_standard_alphabet_alias() -> None:
    from orchestrator.workflow.provider_phased_delivery.protocol import (
        PhasedSubmitBinding,
    )

    binding = PhasedSubmitBinding(
        attempt_scope_sha256=_digest("a"),
        endpoint_instance_id="e",
        binding_token="f" * 64,
        socket_path=Path("/tmp/>"),
        deadline=1.0,
    )
    assert "-" in binding.opaque_value
    alias = binding.opaque_value.replace("-", "+")

    with pytest.raises(ValueError):
        decode_submit_binding(
            {PHASED_PROVIDER_BINDING_ENV: alias}
        )


@pytest.mark.parametrize("shape", ("array", "object"))
def test_environment_binding_contains_deep_post_decode_canonical_failure(
    tmp_path: Path,
    shape: str,
) -> None:
    depth = 500
    nested = (
        b"[" * depth + b'"x"' + b"]" * depth
        if shape == "array"
        else b'{"a":' * depth + b'"x"' + b"}" * depth
    )
    binding, _locator = _binding(tmp_path)
    raw = (
        b'{"attempt_scope_sha256":'
        + json.dumps(binding.attempt_scope_sha256).encode("ascii")
        + b',"binding_token":'
        + nested
        + b',"deadline":'
        + repr(binding.deadline).encode("ascii")
        + b',"endpoint_instance_id":'
        + json.dumps(binding.endpoint_instance_id).encode("ascii")
        + b',"schema_version":"provider_phased_submit_binding.v1"'
        + b',"socket_path":'
        + json.dumps(str(binding.socket_path)).encode("ascii")
        + b"}"
    )
    encoded = base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")

    with pytest.raises(ValueError):
        decode_submit_binding(
            {PHASED_PROVIDER_BINDING_ENV: encoded}
        )
@pytest.mark.parametrize(
    "mutate",
    (
        lambda value: value.pop("status"),
        lambda value: value.__setitem__("extra", None),
        lambda value: value.__setitem__("schema_version", "unknown.v1"),
        lambda value: value.__setitem__("submission_ordinal", True),
    ),
)
def test_receipt_wire_projection_is_closed_versioned_and_typed(
    mutate,
) -> None:
    value = receipt_to_dict(_receipt("request-receipt-wire"))
    mutate(value)

    with pytest.raises((TypeError, ValueError)):
        receipt_from_dict(value)


def test_expired_client_deadline_allocates_no_socket(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    binding, _locator = _binding(
        tmp_path,
        deadline=time.monotonic() - 1,
    )
    allocated = False

    def socket_forbidden(*_args, **_kwargs):
        nonlocal allocated
        allocated = True
        raise AssertionError("socket allocated after deadline")

    monkeypatch.setattr(
        "orchestrator.workflow.provider_phased_delivery.protocol.socket.socket",
        socket_forbidden,
    )
    with pytest.raises(PhasedSubmitProtocolClosedError):
        send_submit_request(
            _request(binding, "request-before-expiry"),
            binding=binding,
        )
    assert allocated is False


@pytest.mark.parametrize(
    "request_id",
    (
        "",
        "é",
        "x" * (MAX_CLIENT_REQUEST_ID_BYTES + 1),
    ),
)
def test_client_request_id_is_nonempty_ascii_and_bounded(
    tmp_path: Path,
    request_id: str,
) -> None:
    binding, _locator = _binding(tmp_path)
    with pytest.raises(ValueError):
        _request(binding, request_id)
