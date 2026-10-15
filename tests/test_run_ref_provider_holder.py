"""Private Holder integration boundaries; public provider admission stays closed."""
from __future__ import annotations

import socket
from pathlib import Path

import pytest

from orchestrator.workflow.run_ref import holder_scope, holder_spawner


def test_gateway_mount_is_directory_only_with_fixed_relative_alias_and_none_has_neither():
    plain = holder_spawner.holder_argv(workspace_mib=32, runref_dir='/private/scripts', git=False)
    assert '/run/runref-gateway' not in plain and '/run/gateway.sock' not in plain
    model = holder_spawner.holder_argv(workspace_mib=32, runref_dir='/private/scripts', git=False,
                                      gateway_dir='/private/owned-gateway')
    index = model.index('/private/owned-gateway')
    assert model[index-1:index+6] == ['--ro-bind', '/private/owned-gateway', '/run/runref-gateway',
                                    '--symlink', 'runref-gateway/gateway.sock', '/run/gateway.sock', '--remount-ro']
    assert model.index('/run/runref-gateway') < model.index('--remount-ro', model.index('/run/runref'))


def test_host_window_excludes_helpers_without_queue_and_requires_empty_gateway(tmp_path, monkeypatch):
    scope = holder_scope.HolderScope(object(), {}, control_dir=tmp_path)
    if not hasattr(scope, 'begin_transport'):
        pytest.fail('private host transport window is not implemented')
    scope.gateway = holder_scope.GatewayDirectory(tmp_path / 'gateway')
    quiescence = []
    monkeypatch.setattr(scope, 'require_quiescent', lambda: quiescence.append(True))
    calls = []
    monkeypatch.setattr(scope, '_run_host_helper', lambda *a, **kw: calls.append(True))
    try:
        scope.begin_transport()
        with pytest.raises(Exception, match='host_slot_busy'):
            scope.run_host_helper(['/bin/true'], pass_fds=(), timeout_sec=1)
        assert not calls
        scope.end_transport()
        scope.run_host_helper(['/bin/true'], pass_fds=(), timeout_sec=1)
        assert calls == [True]
        (scope.gateway.path / 'foreign').write_bytes(b'preserve')
        with pytest.raises(holder_scope.HolderDeathError):
            scope.begin_transport()
        assert (scope.gateway.path / 'foreign').read_bytes() == b'preserve'
    finally:
        (scope.gateway.path / 'foreign').unlink(missing_ok=True)
        scope.gateway.close()


def test_gated_worker_late_host_placement_after_revoke_never_executes(tmp_path):
    import os
    import subprocess
    import sys
    import time
    if not hasattr(holder_scope, 'HOST_WORKER_TRAMPOLINE'):
        pytest.fail('gated host worker entry is not implemented')
    read_fd, write_fd = os.pipe()
    controller, child_gate = socket.socketpair()
    marker = tmp_path / 'must-not-execute'
    process = None
    try:
        # A full pipe is a concrete blocked placement syscall. The runtime
        # uses its validated host cgroup.procs FD at this exact interface.
        os.set_blocking(write_fd, False)
        while True:
            try:
                os.write(write_fd, b'x')
            except BlockingIOError:
                break
        os.set_blocking(write_fd, True)
        process = subprocess.Popen([sys.executable, '-I', '-S', '-c', holder_scope.HOST_WORKER_TRAMPOLINE,
                                    str(write_fd), str(os.getpid()), str(child_gate.fileno()),
                                    sys.executable, '-I', '-c', f'open({str(marker)!r}, "wb").close()'],
                                   pass_fds=(write_fd, child_gate.fileno()), stdout=subprocess.DEVNULL,
                                   stderr=subprocess.DEVNULL)
        child_gate.close()
        deadline = time.monotonic() + 2
        while 'pipe_write' not in Path(f'/proc/{process.pid}/wchan').read_text():
            assert process.poll() is None and time.monotonic() < deadline
            time.sleep(.005)
        controller.shutdown(socket.SHUT_RDWR)
        controller.close()  # observer revocation before placement completed
        assert process.poll() is None and not marker.exists()
        os.read(read_fd, 4096)  # release the blocked syscall, not the exec gate
        assert process.wait(timeout=2) == 125 and not marker.exists()
    finally:
        controller.close()
        child_gate.close()
        if process is not None and process.poll() is None:
            process.kill()
            process.wait(timeout=2)
        os.close(read_fd)
        os.close(write_fd)


@pytest.mark.parametrize('point', ['popen_return', 'membership'])
def test_host_start_late_return_or_placement_never_releases_and_reaps_owned_child(tmp_path, monkeypatch, point):
    import os
    import subprocess
    import sys
    import threading
    from orchestrator.workflow.run_ref.provider_control import LeafCancellationObserver, ProviderControlRefused, boottime_ns
    scope = holder_scope.HolderScope(object(), {}, control_dir=tmp_path)
    if not hasattr(scope, 'start_host_worker'):
        pytest.fail('gated host worker startup is not implemented')
    scope._transport_active = True
    scope._transport_thread = threading.get_ident()
    cgroup = tmp_path / 'host'
    cgroup.mkdir()
    (cgroup / 'cgroup.procs').write_bytes(b'')
    spawned = []
    observer = LeafCancellationObserver(deadline_ns=boottime_ns() + 2_000_000_000,
                                         cancelled=threading.Event(), stop_scope=lambda: None)
    class Slot:
        path = cgroup
        def revalidate(self):
            pass
        def members(self):
            if point == 'membership':
                observer.revoke()
            return (spawned[0].pid,)
    scope.slots['host'] = Slot()
    original = subprocess.Popen
    def start(*args, **kwargs):
        child = original(*args, **kwargs)
        spawned.append(child)
        if point == 'popen_return':
            observer.revoke()
        return child
    monkeypatch.setattr(subprocess, 'Popen', start)
    marker = tmp_path / 'must-not-execute'
    observer.start()
    try:
        with pytest.raises(ProviderControlRefused):
            scope.start_host_worker([sys.executable, '-I', '-c', f'open({str(marker)!r}, "wb").close()'],
                                    pass_fds=(), env={'PATH': '/usr/bin:/bin'}, cwd=tmp_path,
                                    observer=observer)
        assert len(spawned) == 1 and spawned[0].poll() is not None and not marker.exists()
    finally:
        observer.finish()
        for child in spawned:
            if child.poll() is None:
                child.kill()
            child.wait(timeout=2)


def test_observer_scope_stop_revalidates_whole_scope_without_host_operation_lock(tmp_path, monkeypatch):
    scope = holder_scope.HolderScope(object(), {}, control_dir=tmp_path)
    if not hasattr(scope, 'abort_transport'):
        pytest.fail('whole-scope observer stop is not implemented')
    calls = []
    class Root:
        def revalidate(self):
            calls.append('validated')
    scope.root, scope.path = Root(), tmp_path/'validated-scope'
    monkeypatch.setattr(holder_scope, 'kill_cgroup', lambda path, timeout: calls.append((path, timeout)) or True)
    scope._host_operation.acquire()
    try:
        scope.abort_transport()
        assert calls == ['validated', (scope.path, holder_scope.SLOT_EMPTY_SECONDS)]
        monkeypatch.setattr(holder_scope, 'kill_cgroup', lambda *a, **kw: False)
        with pytest.raises(holder_scope.HolderDeathError):
            scope.abort_transport()
    finally:
        scope._host_operation.release()


@pytest.mark.parametrize('reason', ['expiry', 'cancel'])
def test_initial_durable_ack_blocked_observer_active_and_zero_worker_start(tmp_path, reason):
    import threading
    from types import SimpleNamespace
    from orchestrator.providers.inference_gateway import qualified_policy
    from orchestrator.workflow.run_ref import provider_transport as m
    from orchestrator.workflow.run_ref.provider_control import boottime_ns, ProviderControlRefused
    from orchestrator.workflow.run_ref.provider_worker import NativeInstallation
    from tests.test_run_ref_provider_allowance import _allocate, _projection
    path = tmp_path/'ledger'
    _allocate(path, tmp_path)
    authority = _projection(path, tmp_path)
    entered, release, stopped, cancelled = (threading.Event() for _ in range(4))
    original = authority._emit
    def emit(kind, event):
        ack = original(kind, event)
        entered.set()
        assert release.wait(2)
        return ack
    authority._emit = emit
    spawned = []
    sandbox = SimpleNamespace(control_dir=tmp_path, abort_transport=stopped.set,
        start_host_worker=lambda *a, **kw: spawned.append(True))
    transport = m.LeafProviderTransport(sandbox, authority=authority, policy=qualified_policy(), identity='leaf',
        attempt=1, installation=NativeInstallation(tmp_path/'codex', tmp_path/'home', tmp_path/'host'),
        deadline_ns=boottime_ns()+(80_000_000 if reason == 'expiry' else 2_000_000_000), cancelled=cancelled)
    checked = []
    def inspect():
        try:
            assert entered.wait(1)
            if reason == 'cancel':
                cancelled.set()
            assert stopped.wait(1) and not release.is_set() and not spawned
            assert b'provider_reservation' in path.read_bytes()
            checked.append(True)
        finally:
            release.set()
    thread = threading.Thread(target=inspect)
    thread.start()
    try:
        with pytest.raises(ProviderControlRefused):
            transport.start()
        assert checked and not spawned and authority.state['consumed'] == 1
    finally:
        release.set()
        thread.join(2)
        transport.observer.finish()


def test_private_provider_entry_exists_but_public_model_route_still_refuses():
    from orchestrator.workflow.run_ref.holder import Holder
    from orchestrator.workflow.run_ref.leaf import LeafRequest
    from orchestrator.workflow.run_ref.runtime import RunRefRuntimeError
    holder = object.__new__(Holder)
    request = LeafRequest('leaf', ('/bin/true',), {}, '/workspace', 1, 1, 1, {}, 'model-only')
    with pytest.raises(RunRefRuntimeError) as error:
        holder.run_leaf(request)
    assert error.value.code == 'run_ref_provider_transport_unavailable'
    assert hasattr(holder, 'run_provider_leaf')


@pytest.mark.parametrize('point', ['normal', 'callback', 'invalid', 'late_callback', 'active_eof', 'budget', 'budget_close_error', 'budget_missing_leaf', 'budget_missing_leaf_unconfirmed'])
def test_private_holder_closes_leaf_before_observer_and_releases_host_window_before_import(tmp_path, monkeypatch, point):
    import os
    import threading
    from dataclasses import replace
    from types import SimpleNamespace
    from orchestrator.providers.inference_gateway import qualified_policy
    from orchestrator.workflow.run_ref import holder as hm, provider_transport
    from orchestrator.workflow.run_ref.holder_broker import LeafReads
    from orchestrator.workflow.run_ref.leaf import LeafRequest
    from orchestrator.workflow.run_ref.provider_control import ProviderControlRefused, boottime_ns
    roots, events, lock = {}, [], threading.Lock()
    for name in ['tmp', 'dev/shm', 'result']:
        directory = tmp_path/name
        directory.mkdir(parents=True)
        roots[name] = os.open(directory, os.O_RDONLY|os.O_DIRECTORY)
    runref = tmp_path/'scripts'
    runref.mkdir(mode=0o700)
    class Slot:
        populated = False
        def add_pid(self, pid):
            self.populated = True
        def members(self):
            return (123,)
        def kill(self):
            if point.startswith('budget_missing_leaf') and state['scope_stopped']:
                self.populated=False
                raise holder_scope.ProviderIsolationStateError('synthetic_missing_leaf_slot')
            self.populated = False
            events.append('leaf_stopped')
        def wait_empty(self, **kw):
            assert not self.populated
        def remove(self):
            pass
    slot = Slot()
    state = dict(host=False, revoked=False, scope_stopped=False)
    scope_path=tmp_path/'scope';scope_path.mkdir()
    (scope_path/'cgroup.events').write_text('populated 1\n')
    def quiescent():
        if state['scope_stopped']:
            raise holder_scope.HolderDeathError(holder_scope.LOST,'holder-slot membership changed')
        assert not slot.populated and not state['host']
    def begin():
        assert lock.acquire(False)
        sandbox._transport_active=True
    def end():
        holder_scope.HolderScope.end_transport(sandbox)
    def helper(*a, **kw):
        assert lock.acquire(False), 'host_slot_busy'
        lock.release()
        events.append('helper')
    sandbox = SimpleNamespace(roots=roots, runref=runref, root=SimpleNamespace(create_slot=lambda name: slot,revalidate=lambda:None),
        require_quiescent=quiescent, begin_transport=begin, end_transport=end, kill=lambda: None,
        slots={'holder':SimpleNamespace(members=lambda: (1,))}, recorded={1},
        gate_socket=SimpleNamespace(sendall=lambda data: events.append('release')),
        check_spawner=lambda: events.append('spawner_checked'), run_host_helper=helper,
        path=scope_path,_host_operation=lock,_transport_error=None,_transport_active=False,_transport_thread=None,
        gateway=SimpleNamespace(require_empty=lambda:None))
    sandbox._transport_scope_empty=lambda:holder_scope.HolderScope._transport_scope_empty(sandbox)
    from orchestrator.workflow.run_ref import holder_scripts
    parent_id, root_id = holder_scripts.identities(runref)
    sandbox.check_scripts = lambda: None
    sandbox.write_leaf_script = lambda leaf, identity, text: holder_scripts.write_script(
        runref,leaf,text,parent_identity=parent_id,root_identity=root_id,leaf_identity=identity)
    sandbox.retire_leaf_script = lambda leaf, identity: holder_scripts.retire_leaf(
        runref,leaf,parent_identity=parent_id,root_identity=root_id,leaf_identity=identity)
    class Transport:
        def __init__(self, *a, **kw):
            self.observer = SimpleNamespace(deadline_ns=kw['deadline_ns'],revoke=lambda:None,
                finished=SimpleNamespace(wait=lambda timeout:True),
                quiesced=SimpleNamespace(is_set=lambda:point!='budget_missing_leaf_unconfirmed'))
            self.closed = False
        def start(self):
            state['host'] = True
            events.append('binding_ack')
            return 'ephemeral-capability'
        def check(self):
            if state['revoked']:
                raise ProviderControlRefused('transport_revoked')
        def close(self):
            if not self.closed:
                assert not slot.populated, 'observer finished while leaf active'
                state['host'] = False
                events.append('observer_finished')
                self.closed = True
                if point=='budget_close_error':
                    raise holder_scope.HolderDeathError(holder_scope.LOST,'synthetic_independent_close_failure')
    monkeypatch.setattr(provider_transport, 'LeafProviderTransport', Transport)
    holder = object.__new__(hm.Holder)
    holder.sandbox, holder._leaves, holder._death = sandbox, 0, None
    holder._request = lambda leaf: 123
    def status(*a, **kw):
        if point.startswith('budget'):
            state['scope_stopped']=True
            (scope_path/'cgroup.events').write_text('populated 0\n')
            raise hm.RunRefRuntimeError('run_ref_budget_exhausted','provider_request_allowance_exhausted')
        if point == 'active_eof':
            raise ProviderControlRefused('private_channel_eof')
        return 0, False, False
    holder._await_status = status
    def import_result(request):
        quiescent()
        assert not lock.locked()
        assert not (runref/request.leaf_id).exists(), 'capability_script_retained_at_import'
        holder.run_host_helper(['/bin/true'], timeout_sec=1)
        events.append('import')
        return LeafReads(b'', b'', False, False, {})
    holder._import = import_result
    request = LeafRequest('leaf', ('/bin/true',), {}, '/workspace', 1, 1024, 1024, {}, 'model-only')
    def prepare(capability):
        assert events == ['binding_ack']
        if point == 'callback':
            raise ValueError('private-callback-canary')
        if point == 'late_callback':
            state['revoked'] = True
        return replace(request, env={'CAP':capability}, timeout_sec=2 if point=='invalid' else 1)
    try:
        try:
            outcome = holder.run_provider_leaf(request, allowance=object(), policy=qualified_policy(), identity='effect',
                attempt=1, installation=object(), deadline_ns=boottime_ns()+800_000_000,
                cancelled=threading.Event(), prepare_guest=prepare)
        except hm.RunRefRuntimeError as error:
            assert point in {'budget','budget_missing_leaf'} and error.code=='run_ref_budget_exhausted'
            assert not lock.locked() and not slot.populated and not state['host']
            assert not list(runref.iterdir()) and 'import' not in events
            return
        assert point not in {'budget','budget_missing_leaf'}, 'budget_error_was_replaced_by_holder_death'
        if point in {'budget_close_error','budget_missing_leaf_unconfirmed'}:
            expected=('synthetic_independent_close_failure' if point=='budget_close_error' else 'provider_leaf_close_unconfirmed')
            assert outcome.holder_death.detail==expected
            assert lock.locked() and not slot.populated and not state['host'] and 'import' not in events
            lock.release()
            return
        assert not lock.locked() and not slot.populated and not state['host']
        assert not list(runref.iterdir())
        assert events.index('leaf_stopped') < events.index('observer_finished')
        if point == 'normal':
            assert outcome.exit_code == 0 and outcome.holder_death is None
            assert events.index('observer_finished') < events.index('helper') < events.index('import')
        else:
            assert outcome.holder_death is not None and 'import' not in events
            assert ('release' in events) == (point == 'active_eof')
    finally:
        for fd in roots.values():
            os.close(fd)


@pytest.mark.parametrize('failed', ['exit125','forced'])
def test_unconfirmed_worker_close_stays_failed_even_after_host_and_socket_empty(tmp_path, failed):
    import subprocess
    import threading
    from types import SimpleNamespace
    from orchestrator.providers.inference_gateway import qualified_policy
    from orchestrator.workflow.run_ref.provider_control import boottime_ns
    from orchestrator.workflow.run_ref.provider_transport import LeafProviderTransport
    from orchestrator.workflow.run_ref.provider_worker import NativeInstallation
    directory = holder_scope.GatewayDirectory(tmp_path/'gateway')
    actions = []
    class Process:
        calls = 0
        def wait(self, timeout):
            self.calls += 1
            if failed == 'forced' and self.calls == 1:
                raise subprocess.TimeoutExpired('private_worker', timeout)
            return 125 if failed == 'exit125' else -9
    sandbox = SimpleNamespace(gateway=directory, abort_transport=lambda: actions.append('scope_stopped'),
        slots={'host':SimpleNamespace(kill=lambda: actions.append('host_stopped'), wait_empty=lambda **kw: None)})
    transport = LeafProviderTransport(sandbox, authority=object(), policy=qualified_policy(), identity='leaf', attempt=1,
        installation=NativeInstallation(tmp_path/'codex',tmp_path/'home',tmp_path/'host'),
        deadline_ns=boottime_ns()+2_000_000_000, cancelled=threading.Event())
    transport.process = Process()
    transport.observer.start()
    try:
        for _ in range(2):
            with pytest.raises(holder_scope.HolderDeathError, match='provider_transport_close_unconfirmed'):
                transport.close()
        assert actions.count('host_stopped') == 1 and not list(directory.path.iterdir())
    finally:
        transport.observer.finish()
        directory.close()


def test_session_private_deadline_uses_existing_integer_visit_balance_without_reset(monkeypatch):
    import threading
    from types import SimpleNamespace
    from orchestrator.workflow.run_ref import confined_session as m
    from orchestrator.workflow.run_ref.confined_budget import boot_id
    from orchestrator.workflow.run_ref.leaf import LeafRequest
    session = object.__new__(m.ConfinedChildSession)
    session.failure, session.network, session.provider_allowance = None, 'model-only', object()
    session._clock, session._ensure_started, session._require_wall_budget = lambda:7, lambda:None, lambda:None
    session.budget_context = SimpleNamespace(state=dict(charged_ns=100,limit_ns=500000100,
        active=dict(boot_id=boot_id(),since_ns=900000000,opening_sequence=1)))
    calls = []
    session.holder = SimpleNamespace(run_provider_leaf=lambda req, **kw: calls.append(kw) or 'outcome')
    session._after_leaf = lambda req,outcome,started: outcome
    monkeypatch.setattr(m,'boottime_ns',lambda:1000000000)
    req = LeafRequest('leaf',('/bin/true',),{},'/workspace',1,1,1,{},'model-only')
    assert session.run_provider_leaf(req,policy=object(),identity='effect',attempt=1,installation=object(),
        cancelled=threading.Event(),prepare_guest=object()) == 'outcome'
    assert calls[0]['deadline_ns'] == 1400000000 and calls[0]['allowance'] is session.provider_allowance
    session.network = 'none'
    with pytest.raises(Exception):
        session.run_provider_leaf(req,policy=object(),identity='effect',attempt=1,installation=object(),
            cancelled=threading.Event(),prepare_guest=object())
    assert len(calls) == 1


@pytest.mark.parametrize('error_type', ['guest','syscall'])
def test_result_refusal_and_syscall_text_never_enter_holder_diagnostic(monkeypatch, error_type):
    from types import SimpleNamespace
    from orchestrator.workflow.run_ref import holder as m
    needle = 'fictional-capability-in-a-guest-filename'
    instance = object.__new__(m.Holder)
    instance.sandbox = SimpleNamespace(roots={'result':0},process=None,kill=lambda:None)
    def refuse(*args, **kwargs):
        raise (m.GuestRefusal if error_type=='guest' else OSError)(needle)
    monkeypatch.setattr(m,'read_leaf_results',refuse)
    with pytest.raises(m.HolderDeathError) as caught:
        instance._import(SimpleNamespace(leaf_id='leaf',stdout_limit=10,stderr_limit=10))
    assert needle not in caught.value.death.detail
    assert caught.value.__cause__.args == (needle,)  # retained in memory only
    assert needle not in instance._die(OSError(needle)).detail


@pytest.mark.parametrize('source', ['copier','stderr','runtime','malformed'])
def test_session_copier_boundary_retains_code_without_guest_text(source):
    import json
    from types import SimpleNamespace
    from orchestrator.workflow.run_ref import confined_session as m
    needle = 'fictional-capability-in-workspace-name'
    code = 'run_ref_environment_escape_rejected'
    session = object.__new__(m.ConfinedChildSession)
    session.budget,session._clock,session._wall_started,session._finished_at,session.budget_context = 100,lambda:0,0,None,None
    session._clone_fd = 1
    def helper(*args, **kwargs):
        if source == 'runtime':
            raise m.RunRefRuntimeError(code,needle)
        return SimpleNamespace(returncode=3 if source in {'copier','malformed'} else 1,
            stdout=json.dumps({'code':code,'detail':needle}) if source == 'copier' else needle,
            stderr=needle)
    session.holder=SimpleNamespace(root_fd=lambda _:0,run_host_helper=helper)
    result=session._helper('checkpoint','unused')
    assert result[0] == (code if source in {'copier','runtime'} else m.LOST)
    assert needle not in repr(result)


def test_session_stop_and_refreeze_diagnostics_do_not_project_guest_exception_text(monkeypatch):
    from types import SimpleNamespace
    from orchestrator.workflow.run_ref import confined_session as m
    needle = 'fictional-capability-in-workspace-name'
    code = 'run_ref_environment_escape_rejected'
    session = object.__new__(m.ConfinedChildSession)
    session._stop_error,session.failure = None,None
    def stop():
        raise OSError(needle)
    session.holder=SimpleNamespace(stop=stop)
    with pytest.raises(m.RunRefRuntimeError) as caught:
        session._stop_holder()
    assert needle not in str(caught.value)
    session._stop_error,session.failure,session._clone_fd,session.header_path = None,None,0,None
    session.holder=SimpleNamespace(stop=lambda:None)
    session.limits={'workspace-mib':1}
    session._helper=lambda *a:(code,'checkpoint_refused')
    def refreeze(*a):
        raise OSError(needle)
    monkeypatch.setattr(m,'preflight_checkpoint',refreeze)
    with pytest.raises(Exception) as caught:
        session._checkpoint('effect-attempt-1')
    assert caught.value.code == code and needle not in str(caught.value)


def test_transport_host_close_error_preserved_while_scope_cleanup_retires_known_socket(tmp_path):
    import threading
    from types import SimpleNamespace
    from orchestrator.providers.inference_gateway import qualified_policy
    from orchestrator.workflow.run_ref.provider_control import boottime_ns
    from orchestrator.workflow.run_ref.provider_transport import LeafProviderTransport
    from orchestrator.workflow.run_ref.provider_worker import NativeInstallation
    directory=holder_scope.GatewayDirectory(tmp_path/'gateway')
    original=socket.socket(socket.AF_UNIX)
    owned=directory.bind_socket(original)
    def fail_host_close():
        raise OSError('synthetic_host_close_unconfirmed')
    sandbox=SimpleNamespace(gateway=directory,abort_transport=lambda:None,
        slots={'host':SimpleNamespace(kill=fail_host_close,wait_empty=lambda **kw:None)})
    transport=LeafProviderTransport(sandbox,authority=object(),policy=qualified_policy(),identity='leaf',attempt=1,
        installation=NativeInstallation(tmp_path/'codex',tmp_path/'home',tmp_path/'host'),
        deadline_ns=boottime_ns()+5_000_000_000,cancelled=threading.Event())
    transport.socket_identity=owned
    try:
        with pytest.raises(holder_scope.HolderDeathError) as first:
            transport.close()
        assert (directory.path/'gateway.sock').exists()
        # The caller has now independently established whole-scope emptiness.
        original.close()
        directory.close()
        assert not directory.path.exists()
        with pytest.raises(holder_scope.HolderDeathError) as second:
            transport.close()
        assert second.value is first.value and not transport._closed
    finally:
        original.close()
        transport.observer.finish()
        if directory.fd is not None:
            directory.remove_socket(owned)
            directory.close()


def test_initial_script_identity_rejects_shared_control_before_spawn_as_unavailable(tmp_path,monkeypatch):
    from types import SimpleNamespace
    scope=holder_scope.HolderScope(SimpleNamespace(rehash=lambda:None),{},control_dir=tmp_path)
    tmp_path.chmod(0o755)
    spawned=[]
    monkeypatch.setattr(holder_scope.subprocess,'Popen',lambda *a,**kw:spawned.append(True))
    monkeypatch.setattr(scope,'_stop',lambda:None)  # no cosmetic systemctl reset-failed subprocess
    with pytest.raises(holder_scope.RunRefRuntimeError) as caught:
        scope.launch()
    assert caught.value.code==holder_scope.UNAVAILABLE and not spawned and not scope._released


@pytest.mark.parametrize('authority', ['owned_empty','absent','replaced_empty','permission','populated'])
def test_end_transport_empty_scope_requires_original_authority_and_keeps_failure_sticky(tmp_path,monkeypatch,authority):
    from types import SimpleNamespace
    scope=holder_scope.HolderScope(object(),{},control_dir=tmp_path)
    scope.gateway=holder_scope.GatewayDirectory(tmp_path/'gateway')
    scope.path=tmp_path/'scope'
    if authority!='absent':
        scope.path.mkdir();(scope.path/'cgroup.events').write_text('populated '+str(int(authority=='populated'))+'\n')
    checked=[]
    def revalidate():
        checked.append(True)
        if authority=='replaced_empty':
            raise holder_scope.ProviderIsolationStateError('synthetic_scope_identity_changed')
        if authority=='permission':
            raise PermissionError('synthetic_permission_denied')
    scope.root=SimpleNamespace(revalidate=revalidate)
    scope._host_operation.acquire();scope._transport_active=True
    def live_quiescent():
        raise holder_scope.HolderDeathError(holder_scope.LOST,'synthetic_membership_lost')
    monkeypatch.setattr(scope,'require_quiescent',live_quiescent)
    try:
        if authority in {'owned_empty','absent'}:
            scope.end_transport()
            assert not scope._host_operation.locked() and not scope._transport_active
            assert bool(checked)==(authority=='owned_empty')
        else:
            with pytest.raises(Exception) as first:scope.end_transport()
            with pytest.raises(Exception) as second:scope.end_transport()
            assert first.value is second.value and scope._host_operation.locked() and checked
    finally:
        if scope._host_operation.locked():scope._host_operation.release()
        scope.gateway.close()


def test_command_holder_syscall_error_is_closed_before_runtime_diagnostics(monkeypatch):
    from types import SimpleNamespace
    from orchestrator.workflow.run_ref import holder as m
    from orchestrator.workflow.run_ref.leaf import LeafRequest
    instance=object.__new__(m.Holder)
    instance.sandbox=SimpleNamespace(process=None,kill=lambda:None)
    instance._death=None
    def failed(*args):raise OSError('fictional-old-capability-as-guest-name')
    instance._run=failed
    request=LeafRequest('command',('/bin/true',),{},'/workspace',1,1,1,{},'none')
    result=instance.run_leaf(request)
    assert result.holder_death.code==holder_scope.LOST
    assert result.holder_death.detail=='holder_operation_failed'


@pytest.mark.parametrize('field',['input','environment'])
def test_leaf_shape_error_never_projects_guest_derived_name(field):
    from orchestrator.workflow.run_ref.leaf import LeafRequest
    needle='fictional-old-capability-as-invalid-name-'
    request=LeafRequest('command',('/bin/true',),{needle:'x'} if field=='environment' else {},
        '/workspace',1,1,1,{needle+'/':b'x'} if field=='input' else {},'none')
    with pytest.raises(ValueError) as caught:holder_spawner.validate_leaf_request(request)
    if needle in str(caught.value):pytest.fail('guest_derived_name_in_shape_diagnostic',pytrace=False)


def test_clone_binding_syscall_preserves_os_family_without_guest_filename(tmp_path):
    from types import SimpleNamespace
    from orchestrator.workflow.run_ref import confined_session as m
    from orchestrator.workflow.workspace_files import WorkspaceFiles
    clone=tmp_path/'clone';clone.mkdir()
    child=clone/'fictional-old-capability-as-directory';child.mkdir();child.chmod(0)
    files=WorkspaceFiles(clone)
    session=object.__new__(m.ConfinedChildSession)
    session.layout,session.clone_files,session.snapshots=SimpleNamespace(workspace=clone),files,object()
    session._require_wall_budget=lambda:None
    session.check_evidence=lambda:0
    try:
        with pytest.raises(PermissionError) as caught:
            session.clone_input_parts({'command':['/bin/true',child.name]},None)
        import errno,traceback
        assert caught.value.errno==errno.EACCES and caught.value.filename is None and caught.value.filename2 is None
        assert caught.value.strerror=='clone_input_binding_failed' and caught.value.__suppress_context__
        if child.name in ''.join(traceback.format_exception(caught.value)):
            pytest.fail('guest_name_in_projected_exception',pytrace=False)
    finally:
        child.chmod(0o700);files.close()


@pytest.mark.parametrize('boundary',['evidence','snapshot'])
@pytest.mark.parametrize('number',[5,13])
def test_session_binding_redaction_preserves_errno_family_and_no_failure_publication(tmp_path,monkeypatch,boundary,number):
    import traceback
    from types import SimpleNamespace
    from orchestrator.workflow.run_ref import confined_session as m
    from orchestrator.workflow.evaluated import confined_dispatch as dispatch
    needle='fictional-old-capability-in-os-fields'
    fault=OSError(number,needle,needle);fault.filename2=needle
    session=object.__new__(m.ConfinedChildSession)
    session.layout,session.clone_files,session.snapshots=SimpleNamespace(workspace=tmp_path),object(),object()
    session._require_wall_budget=lambda:None
    session.failure=None
    published=[];session.failure_callback=lambda *a:published.append(True)
    def fail(*a,**kw):raise fault
    session.check_evidence=fail if boundary=='evidence' else lambda:0
    monkeypatch.setattr(dispatch,'bind_clone_inputs',lambda *a,**kw:SimpleNamespace(blobs={},parts={}))
    monkeypatch.setattr(dispatch,'store_attempt_snapshot',fail)
    with pytest.raises(type(fault)) as caught:
        session.clone_input_parts({'command':['/bin/true']},None)
    assert caught.value.errno==number and caught.value.filename is None and caught.value.filename2 is None
    assert caught.value.strerror=='clone_input_binding_failed' and caught.value.__suppress_context__
    if needle in ''.join(traceback.format_exception(caught.value)):
        pytest.fail('guest_os_fields_in_runtime_projection',pytrace=False)
    assert session.failure is None and not published


@pytest.mark.parametrize('kind',['evidence','ledger','refusal'])
def test_binding_typed_authority_errors_keep_identity_without_failed_publication(tmp_path,kind):
    from types import SimpleNamespace
    from orchestrator.workflow.run_ref import confined_session as m,ledger
    from orchestrator.workflow.evaluated.confined_dispatch import ConfinedDispatchRefusal,EVIDENCE_INVALID
    fault=({'evidence':lambda:m.RunRefRuntimeError('run_ref_evidence_invalid','synthetic_evidence_invalid'),
            'ledger':lambda:ledger.RunRefLedgerError('synthetic_ledger_invalid'),
            'refusal':lambda:ConfinedDispatchRefusal(EVIDENCE_INVALID)})[kind]()
    session=object.__new__(m.ConfinedChildSession)
    session.layout=SimpleNamespace(workspace=tmp_path);session._require_wall_budget=lambda:None
    session.failure=None;published=[];session.failure_callback=lambda *a:published.append(True)
    def fail():raise fault
    session.check_evidence=fail
    with pytest.raises(type(fault)) as caught:session.clone_input_parts({'command':['/bin/true']},None)
    assert caught.value is fault and session.failure is None and not published
