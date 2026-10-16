"""Durable submit ingress ownership across controller death."""

import json
import multiprocessing
import os
from pathlib import Path
import socket
import tempfile
import time

import pytest

from orchestrator.providers.interactive_terminal import InteractiveTerminalTurnQueueAdapter, PhasedFailedCleanupEvidence
from orchestrator.workflow.provider_phased_delivery.endpoint import PhasedSubmitEndpoint
from orchestrator.workflow.provider_phased_delivery.protocol import derive_submit_binding_and_locator
from orchestrator.workflow.workspace_files import WorkspaceFiles


def _endpoint(reservation):
    binding, locator = derive_submit_binding_and_locator(attempt_scope_sha256="sha256:" + "a" * 64,
        socket_root=reservation.path, nonce=reservation.adapter_token, deadline=time.monotonic() + 30)
    return PhasedSubmitEndpoint(binding=binding, locator=locator, configured_total=2, reservation=reservation)


def _dead_controller(reservation, connection):
    endpoint = _endpoint(reservation)
    endpoint.start()
    connection.send(str(endpoint.locator.socket_path))
    connection.recv()


@pytest.fixture
def reservation():
    with tempfile.TemporaryDirectory(prefix="p", dir="/tmp") as root:
        yield InteractiveTerminalTurnQueueAdapter.reserve_recoverable(Path(root))


def test_live_endpoint_durably_binds_and_closes_exact_socket(reservation):
    endpoint = _endpoint(reservation)
    endpoint.start()
    record = json.loads((reservation.path / "submit.json").read_bytes())
    assert record["state"] == "bound"
    assert record["controller_pid"] == os.getpid()
    assert (record["socket_dev"], record["socket_ino"]) == (
        endpoint.locator.socket_path.stat().st_dev, endpoint.locator.socket_path.stat().st_ino)
    with pytest.raises((ValueError, RuntimeError)):
        PhasedSubmitEndpoint.inspect_owned(reservation, deadline=time.monotonic() + 2)
    outcome = endpoint.shutdown()
    assert outcome.endpoint_zero_survivor_proven
    assert json.loads((reservation.path / "submit.json").read_bytes())["state"] == "closed"
    assert not endpoint.locator.socket_path.exists()
    PhasedSubmitEndpoint.inspect_owned(reservation, deadline=time.monotonic() + 2)


def test_endpoint_restart_cleanup_requires_dead_original_controller(reservation):
    context = multiprocessing.get_context("spawn")
    parent, child = context.Pipe()
    process = context.Process(target=_dead_controller, args=(reservation, child))
    process.start()
    try:
        assert parent.poll(5), "endpoint child did not start"
        path = Path(parent.recv())
        with pytest.raises((ValueError, RuntimeError)):
            PhasedSubmitEndpoint.inspect_owned(reservation, deadline=time.monotonic() + 2)
        process.terminate()
        process.join(timeout=3)
        assert not process.is_alive()
        PhasedSubmitEndpoint.inspect_owned(reservation, deadline=time.monotonic() + 2)
        proof = PhasedFailedCleanupEvidence("failed_cleanup", True, True, True, None)
        PhasedSubmitEndpoint.recover_owned(reservation, deadline=time.monotonic() + 2, provider_cleanup=proof)
        assert not path.exists()
        assert json.loads((reservation.path / "submit.json").read_bytes())["state"] == "closed"
    finally:
        if process.is_alive():
            process.terminate()
            process.join(timeout=3)


@pytest.mark.parametrize("damage", ["torn", "foreign", "extra", "missing", "replacement"])
def test_endpoint_ownership_damage_refuses_without_mutation(reservation, damage):
    endpoint = _endpoint(reservation)
    endpoint.start()
    endpoint.shutdown()
    record_path = reservation.path / "submit.json"
    record = json.loads(record_path.read_bytes())
    if damage == "torn":
        record_path.write_bytes(b'{')
    elif damage == "foreign":
        record["adapter_token"] = "0" * 32
        record_path.write_text(json.dumps(record))
    elif damage == "extra":
        record["extra"] = 1
        record_path.write_text(json.dumps(record))
    else:
        if damage == "missing":
            record_path.unlink()
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.bind(str(endpoint.locator.socket_path))
        sock.close()
    before = record_path.read_bytes() if record_path.exists() else None
    with pytest.raises((OSError, ValueError, RuntimeError)):
        PhasedSubmitEndpoint.inspect_owned(reservation, deadline=time.monotonic() + 2)
    assert (record_path.read_bytes() if record_path.exists() else None) == before
    if damage in {"missing", "replacement"}:
        assert endpoint.locator.socket_path.exists()


def test_live_socket_replacement_is_preserved_and_never_marked_closed(reservation):
    endpoint = _endpoint(reservation)
    endpoint.start()
    endpoint.locator.socket_path.unlink()
    replacement = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    replacement.bind(str(endpoint.locator.socket_path))
    try:
        before = endpoint.locator.socket_path.stat().st_ino
        outcome = endpoint.shutdown()
        assert not outcome.endpoint_zero_survivor_proven
        assert endpoint.locator.socket_path.stat().st_ino == before
        assert json.loads((reservation.path / "submit.json").read_bytes())["state"] == "bound"
    finally:
        replacement.close()


def test_incomplete_worker_join_never_publishes_closed(reservation):
    endpoint = _endpoint(reservation)
    endpoint.start()
    class Survivor:
        alive = True
        def join(self, timeout):
            pass
        def is_alive(self):
            return self.alive
    worker = Survivor()
    endpoint._workers.add(worker)
    endpoint._worker_count += 1
    outcome = endpoint.shutdown()
    assert not outcome.endpoint_zero_survivor_proven
    assert json.loads((reservation.path / "submit.json").read_bytes())["state"] == "bound"
    worker.alive = False
    assert endpoint.shutdown().endpoint_zero_survivor_proven


def test_bound_record_publication_failure_retains_live_observation_for_safe_cleanup(reservation, monkeypatch):
    original = WorkspaceFiles.write_atomic
    def fail_bound(self, path, content, **kwargs):
        if path == "submit.json" and json.loads(content)["state"] == "bound":
            raise OSError("simulated record publication failure")
        return original(self, path, content, **kwargs)
    monkeypatch.setattr(WorkspaceFiles, "write_atomic", fail_bound)
    endpoint = _endpoint(reservation)
    with pytest.raises(OSError):
        endpoint.start()
    assert not endpoint.locator.socket_path.exists()
    assert endpoint._socket_identity is not None
    assert endpoint.shutdown().endpoint_zero_survivor_proven
    assert json.loads((reservation.path / "submit.json").read_bytes())["state"] == "closed"


def test_dead_binding_record_can_remove_socket_not_yet_observed_durably(reservation):
    endpoint = _endpoint(reservation)
    endpoint.start()
    record_path = reservation.path / "submit.json"
    endpoint.shutdown()
    record = json.loads(record_path.read_bytes())
    # A dead controller before publication has binding/null identity and a fixed socket child.
    record.update(state="binding", socket_dev=None, socket_ino=None,
        controller_start_ticks=record["controller_start_ticks"] + 1)
    record_path.write_text(json.dumps(record))
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.bind(str(endpoint.locator.socket_path))
    sock.close()
    proof = PhasedFailedCleanupEvidence("failed_cleanup", True, True, True, None)
    admission = PhasedSubmitEndpoint.inspect_owned(reservation, deadline=time.monotonic() + 2)
    PhasedSubmitEndpoint.recover_owned(reservation, deadline=time.monotonic() + 2,
        provider_cleanup=proof, admission=admission)
    assert not endpoint.locator.socket_path.exists()
    assert json.loads(record_path.read_bytes())["state"] == "closed"
