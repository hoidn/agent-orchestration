"""Lifecycle-thread driver for one private Holder provider leaf.

Only this thread calls its existing allowance. The independent observer owns
revocation/whole-scope stop; the worker has no journal or lifecycle authority.
"""
from __future__ import annotations

import os
from pathlib import Path
import select
import shutil
import socket
import subprocess
import sys
import tempfile

from orchestrator.providers.inference_gateway import validate_transport_policy
from .holder_scope import CONTAINMENT_ERRORS, LOST, SLOT_EMPTY_SECONDS, HolderDeathError
from .provider_control import LeafCancellationObserver, LifecycleControl, PrivateChannel, ProviderControlRefused

_ROOT = Path(__file__).resolve().parents[3]
_ENTRY = '''
import sys
sys.path.insert(0, sys.argv[1])
from orchestrator.workflow.run_ref.provider_worker import main
raise SystemExit(main(int(sys.argv[2]), int(sys.argv[3])))
'''


class LeafProviderTransport:
    def __init__(self, sandbox, *, authority, policy, identity, attempt, installation,
                 deadline_ns, cancelled):
        self.policy = validate_transport_policy(policy.record)
        self.sandbox, self.authority = sandbox, authority
        self.identity, self.attempt, self.installation = identity, attempt, installation
        self.observer = LeafCancellationObserver(deadline_ns=deadline_ns, cancelled=cancelled,
                                                  stop_scope=sandbox.abort_transport)
        self.channel = self.control = self.process = None
        self.socket_identity = self.private_dir = None
        self._closed, self._close_error = False, None

    def start(self):
        self.observer.start()  # before any emit, persistence, head validation or ACK
        self.check()
        row = self.authority.reserve(self.policy.record, identity=self.identity, attempt=self.attempt)
        self.check()
        self.control = LifecycleControl(row, authority=self.authority, policy=self.policy, observer=self.observer)
        self.private_dir = Path(tempfile.mkdtemp(prefix='provider-', dir=self.sandbox.control_dir))
        host, child = socket.socketpair()
        self.observer.register(host)
        self.channel = PrivateChannel(host, self.observer)
        try:
            self.process, native_fd = self.sandbox.start_host_worker(
                [sys.executable, '-I', '-c', _ENTRY, str(_ROOT), str(child.fileno()),
                 str(self.observer.deadline_ns)], pass_fds=(child.fileno(),),
                env={'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8', 'HOME': str(self.private_dir)},
                cwd=self.private_dir, observer=self.observer)
        finally:
            child.close()
        self.check()
        self.channel.send(dict(reservation=row.record,
            policy=self.policy.record if row.event['policy'] is None else None,
            installation={key: str(getattr(self.installation, key))
                          for key in ('binary', 'native_home', 'host_home')},
            owner_dir=str(self.private_dir/'native'), native_slot_fd=native_fd))
        borrowed = self.channel.receive_listener()
        try:
            self.observer.register(borrowed)
            self.check()
            # Capture even after a bind-time revocation, solely for retirement.
            self.socket_identity = self.sandbox.gateway.bind_socket(borrowed)
        finally:
            borrowed.close()  # no shutdown of the worker's shared description
        self.check()
        self.channel.send({'socket_bound': True})
        while self.control.capability is None:
            self.poll(wait=True)
        self.check()
        return self.control.capability

    def check(self):
        self.observer.check()
        self.installation.check_environment(self.observer)

    def poll(self, *, wait=False):
        self.check()
        if self.process is None or self.process.poll() is not None:
            raise ProviderControlRefused('private_worker_ended')
        if not wait and not select.select([self.channel.socket], [], [], 0)[0]:
            return
        message = self.channel.receive()
        self.check()
        reply = self.control.handle(message)
        self.check()
        self.channel.send(reply)
        self.check()

    def close(self):
        if self._close_error is not None:
            raise self._close_error
        if self._closed:
            return
        try:
            if self.control is not None:
                self.control.capability = None
            if self.channel is not None:
                self.channel.close()
            graceful = self.process is None
            if self.process is not None:
                try:
                    graceful = self.process.wait(timeout=SLOT_EMPTY_SECONDS) == 0
                except subprocess.TimeoutExpired:
                    pass
            host = self.sandbox.slots['host']
            try:
                host.kill()
                host.wait_empty(timeout_seconds=SLOT_EMPTY_SECONDS)
            except CONTAINMENT_ERRORS:
                if not (self.observer.finished.wait(2.25) and self.observer.quiesced.is_set()):
                    raise
            if self.process is not None:
                self.process.wait(timeout=SLOT_EMPTY_SECONDS)
            self.sandbox.gateway.remove_socket(self.socket_identity)
            self.sandbox.gateway.require_empty()
            if self.private_dir is not None:
                shutil.rmtree(self.private_dir)
            self.observer.finish()
            if not graceful and not self.observer.revoked.is_set():
                raise HolderDeathError(LOST, 'provider_transport_close_unconfirmed')
        except Exception as error:
            self.observer.revoke()
            try:
                self.observer.finish()
            except Exception:
                pass
            self._close_error = (error if isinstance(error, HolderDeathError)
                                 else HolderDeathError(LOST, 'provider_transport_close_unconfirmed'))
            raise self._close_error from None
        self._closed = True
