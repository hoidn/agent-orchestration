"""Attempt-bound local transport for cooperative provider peer clients."""

from __future__ import annotations

import base64
import binascii
from concurrent.futures import Future
from dataclasses import dataclass, field
import json
import os
from pathlib import Path
from queue import Empty, Queue
import socket
from threading import Event, Lock, Thread, current_thread
from typing import Any, Mapping

from ..._common.canonical import compact_ascii_json_dumps
from ..._common.validation import nonempty_string
from .models import (
    MAX_PEER_MESSAGE_BYTES,
    PeerAcknowledgeRequest,
    PeerAcknowledgeReceipt,
    PeerEndpointIdentity,
    PeerFailureReceipt,
    PeerFinishRequest,
    PeerFinishReceipt,
    PeerReadyRequest,
    PeerReadyReceipt,
    PeerReceipt,
    PeerRequest,
    PeerSendRequest,
    PeerSendReceipt,
    peer_receipt_from_dict,
    peer_request_from_dict,
)


ACTIVE_PEER_BINDING_ENV = "ORCHESTRATOR_ACTIVE_PEER_BINDING"
_ACTIVE_BINDING_SCHEMA_VERSION = "provider_peer_active_binding.v1"
_MAX_FRAME_BYTES = (4 * MAX_PEER_MESSAGE_BYTES) + 16_384
_ACCEPT_POLL_SECONDS = 0.1
_CONNECT_TIMEOUT_SECONDS = 5.0
_CLOSED_EVENT = object()


class PeerProtocolClosedError(RuntimeError):
    """The exact peer-group endpoint is absent or has closed."""


def _canonical_frame(value: Mapping[str, Any]) -> bytes:
    return (
        compact_ascii_json_dumps(dict(value)).encode("ascii")
        + b"\n"
    )


def _reject_duplicate_keys(
    pairs: list[tuple[str, Any]],
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON object key: {key}")
        result[key] = value
    return result


def _decode_canonical_frame(
    frame: bytes,
    *,
    field: str,
) -> Mapping[str, Any]:
    if not frame.endswith(b"\n") or frame.count(b"\n") != 1:
        raise ValueError(f"{field} must be one complete newline frame")
    if len(frame) > _MAX_FRAME_BYTES:
        raise ValueError(f"{field} exceeds the bounded frame size")
    try:
        value = json.loads(
            frame[:-1].decode("ascii"),
            object_pairs_hook=_reject_duplicate_keys,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{field} must be canonical JSON") from exc
    if not isinstance(value, Mapping):
        raise ValueError(f"{field} must contain a JSON object")
    if _canonical_frame(value) != frame:
        raise ValueError(f"{field} must use canonical JSON framing")
    return value


def _read_frame(connection: socket.socket) -> bytes:
    chunks: list[bytes] = []
    size = 0
    while True:
        chunk = connection.recv(min(65_536, _MAX_FRAME_BYTES + 1 - size))
        if not chunk:
            raise ValueError("peer protocol frame closed before newline")
        chunks.append(chunk)
        size += len(chunk)
        if size > _MAX_FRAME_BYTES:
            raise ValueError("peer protocol frame exceeds the bounded size")
        combined = b"".join(chunks)
        newline = combined.find(b"\n")
        if newline < 0:
            continue
        if newline != len(combined) - 1:
            raise ValueError("peer protocol accepts exactly one frame")
        return combined


def _nonempty(value: object, *, field: str) -> str:
    return nonempty_string(value, field)


def encode_active_peer_binding(
    *,
    socket_path: Path,
    sender_binding: str,
) -> str:
    """Encode the one opaque environment value consumed by peer clients."""

    if not isinstance(socket_path, Path) or not socket_path.is_absolute():
        raise ValueError("active peer socket_path must be an absolute Path")
    sender = _nonempty(
        sender_binding,
        field="active peer sender_binding",
    )
    payload = _canonical_frame(
        {
            "schema_version": _ACTIVE_BINDING_SCHEMA_VERSION,
            "socket_path": str(socket_path),
            "sender_binding": sender,
        }
    )[:-1]
    return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")


def _decode_active_peer_binding(
    environ: Mapping[str, str],
) -> tuple[Path, str]:
    encoded = environ.get(ACTIVE_PEER_BINDING_ENV)
    if not isinstance(encoded, str) or not encoded:
        raise ValueError(
            f"{ACTIVE_PEER_BINDING_ENV} must contain an active peer binding"
        )
    try:
        padding = "=" * (-len(encoded) % 4)
        raw = base64.b64decode(
            encoded + padding,
            altchars=b"-_",
            validate=True,
        )
        value = json.loads(
            raw.decode("ascii"),
            object_pairs_hook=_reject_duplicate_keys,
        )
    except (
        UnicodeDecodeError,
        ValueError,
        binascii.Error,
        json.JSONDecodeError,
    ) as exc:
        raise ValueError(
            f"{ACTIVE_PEER_BINDING_ENV} is not a valid active peer binding"
        ) from exc
    if (
        not isinstance(value, Mapping)
        or set(value)
        != {"schema_version", "socket_path", "sender_binding"}
        or value.get("schema_version") != _ACTIVE_BINDING_SCHEMA_VERSION
        or _canonical_frame(value)[:-1] != raw
    ):
        raise ValueError(
            f"{ACTIVE_PEER_BINDING_ENV} is not a valid active peer binding"
        )
    path_text = _nonempty(
        value.get("socket_path"),
        field=f"{ACTIVE_PEER_BINDING_ENV}.socket_path",
    )
    socket_path = Path(path_text)
    if not socket_path.is_absolute():
        raise ValueError(
            f"{ACTIVE_PEER_BINDING_ENV}.socket_path must be absolute"
        )
    return (
        socket_path,
        _nonempty(
            value.get("sender_binding"),
            field=f"{ACTIVE_PEER_BINDING_ENV}.sender_binding",
        ),
    )


@dataclass(frozen=True, slots=True)
class PeerEndpointCloseProof:
    """Proof that endpoint ingress and all owned workers are closed."""

    drained: bool
    closed: bool
    workers_joined: bool


@dataclass(frozen=True, slots=True)
class PeerProtocolEvent:
    """One immutable request handed from a listener to the coordinator."""

    endpoint_identity: PeerEndpointIdentity
    request: PeerRequest
    _waiter: Future[PeerReceipt] = field(
        repr=False,
        compare=False,
    )
    _response_sent: Future[None] = field(
        default_factory=Future,
        repr=False,
        compare=False,
    )


class PeerProtocolListener:
    """One local endpoint whose workers only enqueue and await receipts."""

    def __init__(
        self,
        endpoint_identity: PeerEndpointIdentity,
        socket_path: Path,
    ) -> None:
        if not isinstance(endpoint_identity, PeerEndpointIdentity):
            raise ValueError(
                "endpoint_identity must be a PeerEndpointIdentity"
            )
        if not isinstance(socket_path, Path) or not socket_path.is_absolute():
            raise ValueError("socket_path must be an absolute Path")
        self._endpoint_identity = endpoint_identity
        self._socket_path = socket_path
        self._events: Queue[PeerProtocolEvent | object] = Queue()
        self._lock = Lock()
        self._listener: socket.socket | None = None
        self._accept_thread: Thread | None = None
        self._workers: set[Thread] = set()
        self._connections: set[socket.socket] = set()
        self._waiters: dict[int, Future[PeerReceipt]] = {}
        self._started = False
        self._closed = False
        self._owns_socket_path = False
        self._close_proof: PeerEndpointCloseProof | None = None
        self._close_complete = Event()

    @property
    def endpoint_identity(self) -> PeerEndpointIdentity:
        return self._endpoint_identity

    @property
    def socket_path(self) -> Path:
        return self._socket_path

    def __enter__(self) -> "PeerProtocolListener":
        self.start()
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def start(self) -> None:
        with self._lock:
            if self._started:
                raise RuntimeError("peer protocol listener already started")
            if self._closed:
                raise PeerProtocolClosedError(
                    "peer protocol listener is closed"
                )
            if self._socket_path.exists():
                raise FileExistsError(self._socket_path)
            self._socket_path.parent.mkdir(parents=True, exist_ok=True)
            listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            bound = False
            try:
                listener.bind(str(self._socket_path))
                bound = True
                listener.listen(8)
                listener.settimeout(_ACCEPT_POLL_SECONDS)
                thread = Thread(
                    target=self._accept_loop,
                    name=(
                        "provider-peer-listener-"
                        + self._endpoint_identity.endpoint_instance_id
                    ),
                    daemon=True,
                )
                self._listener = listener
                self._accept_thread = thread
                self._owns_socket_path = True
                self._started = True
                thread.start()
            except BaseException:
                self._listener = None
                self._accept_thread = None
                self._owns_socket_path = False
                self._started = False
                listener.close()
                if bound:
                    try:
                        self._socket_path.unlink()
                    except FileNotFoundError:
                        pass
                raise

    def receive_event(self, *, timeout_sec: float) -> PeerProtocolEvent:
        if (
            isinstance(timeout_sec, bool)
            or not isinstance(timeout_sec, (int, float))
            or timeout_sec <= 0
        ):
            raise ValueError("timeout_sec must be positive")
        with self._lock:
            if self._closed:
                raise PeerProtocolClosedError(
                    "peer protocol listener is closed"
                )
        try:
            event = self._events.get(timeout=float(timeout_sec))
        except Empty as exc:
            if self._closed:
                raise PeerProtocolClosedError(
                    "peer protocol listener is closed"
                ) from exc
            raise TimeoutError("timed out waiting for a peer request") from exc
        with self._lock:
            if self._closed or event is _CLOSED_EVENT:
                raise PeerProtocolClosedError(
                    "peer protocol listener is closed"
                )
        if not isinstance(event, PeerProtocolEvent):
            raise RuntimeError("peer protocol event queue is invalid")
        return event

    def resolve(
        self,
        event: PeerProtocolEvent,
        receipt: PeerReceipt,
    ) -> None:
        if not isinstance(event, PeerProtocolEvent):
            raise ValueError("event must be a PeerProtocolEvent")
        if not isinstance(
            receipt,
            (
                PeerReadyReceipt,
                PeerSendReceipt,
                PeerAcknowledgeReceipt,
                PeerFinishReceipt,
                PeerFailureReceipt,
            ),
        ):
            raise ValueError("receipt must be a peer receipt")
        with self._lock:
            waiter = self._waiters.get(id(event))
            if waiter is None or waiter is not event._waiter:
                raise ValueError(
                    "peer protocol event is not pending on this listener"
                )
            if receipt.request_id != event.request.request_id:
                raise ValueError(
                    "peer receipt request_id does not match its request"
                )
            if isinstance(receipt, PeerFailureReceipt):
                matches_kind = (
                    receipt.request_kind == event.request.kind
                )
            else:
                matches_kind = receipt.kind == event.request.kind
            if not matches_kind:
                raise ValueError(
                    "peer receipt kind does not match its request"
                )
            if waiter.done():
                raise ValueError("peer protocol event is already resolved")
            waiter.set_result(receipt)
        try:
            event._response_sent.result()
        except PeerProtocolClosedError:
            raise
        except Exception as exc:
            raise PeerProtocolClosedError(
                "peer receipt could not be sent to its waiting client"
            ) from exc

    def close(self) -> PeerEndpointCloseProof:
        listener: socket.socket | None = None
        owns_socket_path = False
        connections: tuple[socket.socket, ...] = ()
        with self._lock:
            if self._close_proof is not None:
                return self._close_proof
            close_in_progress = self._closed
            if not close_in_progress:
                self._closed = True
                listener = self._listener
                self._listener = None
                owns_socket_path = self._owns_socket_path
                self._owns_socket_path = False
                connections = tuple(self._connections)
                for waiter in self._waiters.values():
                    if not waiter.done():
                        waiter.set_exception(
                            PeerProtocolClosedError(
                                "peer protocol endpoint closed before receipt"
                            )
                        )
                while True:
                    try:
                        self._events.get_nowait()
                    except Empty:
                        break
                self._events.put(_CLOSED_EVENT)
        if close_in_progress:
            self._close_complete.wait()
            with self._lock:
                if self._close_proof is None:
                    raise RuntimeError(
                        "peer protocol listener close did not complete"
                    )
                return self._close_proof
        try:
            if listener is not None:
                try:
                    listener.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                listener.close()
            for connection in connections:
                try:
                    connection.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                connection.close()
            accept_thread = self._accept_thread
            if (
                accept_thread is not None
                and accept_thread is not current_thread()
            ):
                accept_thread.join()
            with self._lock:
                workers = tuple(self._workers)
            for worker in workers:
                if worker is not current_thread():
                    worker.join()
            if owns_socket_path:
                try:
                    self._socket_path.unlink()
                except FileNotFoundError:
                    pass
            owned_threads = tuple(
                thread
                for thread in (accept_thread, *workers)
                if thread is not None
            )
            residual_events: list[PeerProtocolEvent | object] = []
            while True:
                try:
                    residual_events.append(self._events.get_nowait())
                except Empty:
                    break
            drained = all(
                event is _CLOSED_EVENT for event in residual_events
            )
            self._events.put(_CLOSED_EVENT)
            proof = PeerEndpointCloseProof(
                drained=drained,
                closed=True,
                workers_joined=all(
                    not thread.is_alive() for thread in owned_threads
                ),
            )
            with self._lock:
                self._close_proof = proof
            return proof
        finally:
            self._close_complete.set()

    def _accept_loop(self) -> None:
        while True:
            with self._lock:
                listener = self._listener
                closed = self._closed
            if closed or listener is None:
                return
            try:
                connection, _address = listener.accept()
            except socket.timeout:
                continue
            except OSError:
                return
            worker = Thread(
                target=self._handle_connection,
                args=(connection,),
                name="provider-peer-request",
                daemon=True,
            )
            with self._lock:
                if self._closed:
                    connection.close()
                    return
                self._connections.add(connection)
                self._workers.add(worker)
                try:
                    worker.start()
                except BaseException:
                    self._workers.discard(worker)
                    self._connections.discard(connection)
                    connection.close()
                    raise

    def _handle_connection(self, connection: socket.socket) -> None:
        event: PeerProtocolEvent | None = None
        try:
            with connection:
                try:
                    frame = _read_frame(connection)
                    request = peer_request_from_dict(
                        _decode_canonical_frame(
                            frame,
                            field="peer request",
                        )
                    )
                except (OSError, ValueError):
                    return
                waiter: Future[PeerReceipt] = Future()
                event = PeerProtocolEvent(
                    endpoint_identity=self._endpoint_identity,
                    request=request,
                    _waiter=waiter,
                )
                with self._lock:
                    if self._closed:
                        return
                    self._waiters[id(event)] = waiter
                    self._events.put(event)
                try:
                    receipt = waiter.result()
                except PeerProtocolClosedError:
                    return
                try:
                    connection.sendall(_canonical_frame(receipt.to_dict()))
                except OSError as exc:
                    event._response_sent.set_exception(
                        PeerProtocolClosedError(
                            "peer client closed before receipt delivery"
                        )
                    )
                    return
                event._response_sent.set_result(None)
        finally:
            with self._lock:
                if event is not None:
                    self._waiters.pop(id(event), None)
                self._connections.discard(connection)


def _send_request(
    request: PeerRequest,
    *,
    socket_path: Path,
) -> PeerReceipt:
    connection: socket.socket | None = None
    try:
        connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        connection.settimeout(_CONNECT_TIMEOUT_SECONDS)
        connection.connect(str(socket_path))
        connection.settimeout(None)
    except OSError as exc:
        if connection is not None:
            connection.close()
        raise PeerProtocolClosedError(
            "active peer endpoint is unavailable"
        ) from exc
    assert connection is not None
    with connection:
        try:
            connection.sendall(_canonical_frame(request.to_dict()))
            frame = _read_frame(connection)
            receipt = peer_receipt_from_dict(
                _decode_canonical_frame(
                    frame,
                    field="peer receipt",
                )
            )
        except (OSError, ValueError) as exc:
            raise PeerProtocolClosedError(
                "active peer endpoint closed without a valid receipt"
            ) from exc
    if receipt.request_id != request.request_id:
        raise PeerProtocolClosedError(
            "active peer endpoint returned a mismatched receipt"
        )
    return receipt


def _binding_and_environment(
    environ: Mapping[str, str] | None,
) -> tuple[Path, str]:
    return _decode_active_peer_binding(
        os.environ if environ is None else environ
    )


def peer_ready(
    *,
    request_id: str,
    environ: Mapping[str, str] | None = None,
) -> PeerReceipt:
    socket_path, sender_binding = _binding_and_environment(environ)
    return _send_request(
        PeerReadyRequest(
            request_id=request_id,
            sender_binding=sender_binding,
        ),
        socket_path=socket_path,
    )


def peer_send(
    *,
    target_binding: str,
    message: str,
    request_id: str,
    environ: Mapping[str, str] | None = None,
) -> PeerReceipt:
    socket_path, sender_binding = _binding_and_environment(environ)
    return _send_request(
        PeerSendRequest(
            request_id=request_id,
            sender_binding=sender_binding,
            target_binding=target_binding,
            message=message,
        ),
        socket_path=socket_path,
    )


def peer_ack(
    *,
    message_id: str,
    request_id: str,
    environ: Mapping[str, str] | None = None,
) -> PeerReceipt:
    socket_path, sender_binding = _binding_and_environment(environ)
    return _send_request(
        PeerAcknowledgeRequest(
            request_id=request_id,
            sender_binding=sender_binding,
            message_id=message_id,
        ),
        socket_path=socket_path,
    )


def peer_finish(
    *,
    request_id: str,
    environ: Mapping[str, str] | None = None,
) -> PeerReceipt:
    socket_path, sender_binding = _binding_and_environment(environ)
    return _send_request(
        PeerFinishRequest(
            request_id=request_id,
            sender_binding=sender_binding,
        ),
        socket_path=socket_path,
    )
