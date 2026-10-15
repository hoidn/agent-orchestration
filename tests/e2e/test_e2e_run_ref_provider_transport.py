"""Actual Holder+native owner with fictitious home and disconnected fixture worker."""
from dataclasses import replace
import os
import json
import threading
import time
import socket
import subprocess
import sys
from pathlib import Path
from queue import Empty

import pytest

from orchestrator.providers.inference_gateway import qualified_policy
from orchestrator.workflow.run_ref.confined_budget import boottime_ns
from orchestrator.workflow.run_ref.holder_scope import populated, SLOT_EMPTY_SECONDS
from tests.e2e.run_ref_image_fixture import launch, sealed_image, leaf  # noqa: F401
from tests.e2e.run_ref_provider_fixture import LocalBackend, actual_native_pids, offline_worker, request, synthetic_home
from tests.test_run_ref_provider_allowance import _allocate, _projection

pytestmark = pytest.mark.e2e


@pytest.fixture(autouse=True)
def _scan_all_synthetic_artifacts_after_teardown(tmp_path):
    yield
    from tests.e2e.run_ref_provider_fixture import _jwt, scan_canaries
    if (tmp_path/'native-home').exists():
        account='holder-synthetic-account-A'
        counts=scan_canaries({'all_fixture':tmp_path},
            upstream=(_jwt(account,1).encode(),_jwt(account,2).encode(),b'holder-synthetic-refresh-CANARY'),
            credential_store=tmp_path/'native-home'/'auth.json')
        assert counts['all_fixture']['upstream_outside_store']==0, 'synthetic_upstream_secret_outside_exact_store'
        (tmp_path/'safe-upstream-scan.json').write_text(json.dumps(counts))


def test_private_two_native_generations_with_none_between_close_before_import_and_helper(launch, tmp_path, monkeypatch):
    installation, secrets, table = synthetic_home(tmp_path)
    backend = LocalBackend(tmp_path, table)
    holder = launch(network='model-only')
    offline_worker(monkeypatch, holder.sandbox, tmp_path)
    ledger = tmp_path/'ledger'
    _allocate(ledger, tmp_path)
    authority = _projection(ledger, tmp_path)
    observations = []
    borrowed = []
    original_bind = holder.sandbox.gateway.bind_socket
    def bind(copy):
        borrowed.append(copy)
        return original_bind(copy)
    monkeypatch.setattr(holder.sandbox.gateway,'bind_socket',bind)
    original_import = holder._import
    def import_result(req):
        holder.sandbox.require_quiescent()
        holder.sandbox.gateway.require_empty()
        assert not holder.sandbox._host_operation.locked()
        if req.network == 'model-only':
            assert not (holder.sandbox.runref/req.leaf_id).exists(), 'capability_script_retained_at_import'
        observations.append(req.leaf_id)
        return original_import(req)
    monkeypatch.setattr(holder, '_import', import_result)
    try:
        for name in ['first','second']:
            req = request(name)
            def prepare(cap):
                assert borrowed and all(copy.fileno()==-1 for copy in borrowed)
                return replace(req,env={**req.env,'FIXTURE_CAPABILITY':cap})
            out = holder.run_provider_leaf(req, allowance=authority, policy=qualified_policy(),
                identity=name, attempt=1, installation=installation,
                deadline_ns=boottime_ns()+int(req.timeout_sec*1e9), cancelled=threading.Event(),
                prepare_guest=prepare)
            assert out.holder_death is None and out.exit_code == 0, (out.holder_death, out.stderr)
            assert out.result_files['done.json'] == b'true'
            assert not os.listdir(holder.sandbox.gateway.path) and not os.listdir(holder.sandbox.runref)
            assert holder.run_host_helper(['/bin/true'], timeout_sec=2).returncode == 0
            if name == 'first':
                plain = holder.run_leaf(leaf('between', 'test -L /run/gateway.sock && test ! -e /run/gateway.sock'))
                assert plain.exit_code == 0 and plain.holder_death is None
        assert backend.requests == 2 and backend.crossed == 0
        assert authority.state['consumed'] == 2 and observations == ['first','between','second']
        # The exact fictitious native store is the sole secret exclusion.
        for path in tmp_path.rglob('*'):
            if path.is_file() and not path.is_symlink() and path != installation.native_home/'auth.json':
                raw = path.read_bytes()
                assert not any(needle in raw for needle in secrets), 'synthetic_upstream_secret_outside_store'
    finally:
        backend.close()


@pytest.mark.parametrize('mode', ['stop-startup','stop-initialize','stop-acquisition'])
@pytest.mark.parametrize('reason', ['expiry','cancel'])
def test_actual_native_stopped_during_startup_or_rpc_is_killed_by_absolute_observer(launch, tmp_path, monkeypatch, mode, reason):
    installation, _secrets, table = synthetic_home(tmp_path)
    backend = LocalBackend(tmp_path, table)
    holder = launch(network='model-only')
    offline_worker(monkeypatch, holder.sandbox, tmp_path, mode=mode)
    ledger = tmp_path/'ledger'
    _allocate(ledger, tmp_path)
    authority = _projection(ledger, tmp_path)
    cancelled, checked, failures = threading.Event(), [], []
    req = request('stopped', timeout=8)
    deadline = boottime_ns() + (3_000_000_000 if reason=='expiry' else 8_000_000_000)
    def observe():
        phase='waiting_suspension'
        witness={}
        try:
            until = deadline - (2_000_000_000 if reason=='cancel' else 100_000_000)
            while not (tmp_path/'suspended').exists() and boottime_ns()<until:
                time.sleep(.005)
            witness['suspended']=(tmp_path/'suspended').exists()
            phase='suspension_observed'
            assert witness['suspended']
            native = actual_native_pids(holder.slots['host'].members())
            witness.update(native_executable_matches=len(native),scope_populated=populated(holder.scope))
            phase='native_oracle'
            assert native and witness['scope_populated']
            if reason=='cancel':
                cancelled.set()
            checked.append(True)
        except BaseException as error:
            failures.append(type(error).__name__)
            witness.update(phase=phase,error_category=type(error).__name__)
            (tmp_path/'safe-stop-failure.json').write_text(json.dumps(witness))
            cancelled.set()
    monitor = threading.Thread(target=observe)
    monitor.start()
    try:
        prepared = []
        out = holder.run_provider_leaf(req, allowance=authority, policy=qualified_policy(), identity='stopped',
            attempt=1, installation=installation, deadline_ns=deadline, cancelled=cancelled,
            prepare_guest=lambda cap: prepared.append(True))
        monitor.join(3)
        assert checked and not failures and not monitor.is_alive()
        assert out.holder_death is not None and not populated(holder.scope)
        assert not prepared and backend.requests == 0 and authority.state['consumed'] == 1
        assert b'provider_binding' not in ledger.read_bytes()
        assert not list(holder.sandbox.runref.iterdir()) and not list(holder.sandbox.gateway.path.iterdir())
    finally:
        cancelled.set()
        monitor.join(3)
        backend.close()


@pytest.mark.parametrize('boundary', ['initial', 'binding', 'reservation'])
@pytest.mark.parametrize('reason', ['expiry', 'cancel'])
def test_native_owner_and_leaf_stop_while_common_durable_ack_remains_held(launch, tmp_path, monkeypatch, boundary, reason):
    installation, secrets, table = synthetic_home(tmp_path)
    backend = LocalBackend(tmp_path, table)
    holder = launch(network='model-only')
    offline_worker(monkeypatch, holder.sandbox, tmp_path)
    ledger = tmp_path/'ledger'
    _allocate(ledger, tmp_path)
    authority = _projection(ledger, tmp_path)
    entered, release, cancelled = (threading.Event() for _ in range(3))
    original = authority._emit
    def emit(kind, event):
        ack = original(kind, event)
        if ((boundary == 'initial' and kind == 'provider_reservation' and event['request']==1) or
                (boundary == 'binding' and kind == 'provider_binding') or
                (boundary == 'reservation' and kind == 'provider_reservation' and event['request'] == 2)):
            entered.set()
            assert release.wait(10)
        return ack
    authority._emit = emit
    req = request('held', count=2, timeout=8)
    deadline = boottime_ns() + (3_000_000_000 if reason == 'expiry' else 8_000_000_000)
    prepared, failures, witness, capabilities = [], [], {}, []
    def observe():
        try:
            assert entered.wait(5)
            assert populated(holder.scope)
            members = holder.slots['host'].members()
            native = actual_native_pids(members)
            assert bool(native) == (boundary!='initial'), 'actual_native_presence_disagrees'
            leaf_active = any(populated(path) for path in holder.scope.iterdir()
                if path.is_dir() and path not in {holder.slots['host'].path, holder.slots['holder'].path})
            assert leaf_active == (boundary == 'reservation')
            events = tmp_path/'native-events.jsonl'
            before = events.read_bytes() if events.exists() else b''
            posts = backend.requests
            from tests.e2e.run_ref_provider_fixture import scan_canaries
            def scan():
                roots={'all_fixture':tmp_path,'control':holder.sandbox.control_dir,
                    'workspace':Path(f'/proc/self/fd/{holder.root_fd("workspace")}'),
                    'result':Path(f'/proc/self/fd/{holder.root_fd("result")}')}
                return scan_canaries(roots,upstream=secrets,
                    credential_store=installation.native_home/'auth.json',
                    capability=capabilities[0] if capabilities else None)
            active_counts=scan()
            assert all(row['upstream_outside_store']==0 for row in active_counts.values())
            assert active_counts['control']['capability']==int(boundary=='reservation')
            if reason == 'cancel':
                cancelled.set()
                target = boottime_ns()
            else:
                target = deadline
            until = target + int((SLOT_EMPTY_SECONDS+.3)*1e9)
            while populated(holder.scope) and boottime_ns() < until:
                time.sleep(.005)
            assert not populated(holder.scope) and not release.is_set()
            assert (events.read_bytes() if events.exists() else b'') == before and backend.requests == posts
            revoked_counts=scan()
            assert revoked_counts==active_counts
            witness.update(active_scan=active_counts,revoked_pending_scan=revoked_counts)
            witness.update(native_present=bool(native), native_count=len(native), leaf_active=leaf_active,
                scope_empty_while_ack_held=True, new_auth_after_stop=0, new_posts_after_stop=0,
                scope_unit=holder.unit, script_pending_lifecycle_close=(holder.sandbox.runref/'held'/'leaf.sh').exists())
        except BaseException as error:
            failures.append(type(error).__name__)
        finally:
            release.set()
    monitor = threading.Thread(target=observe)
    monitor.start()
    try:
        out = holder.run_provider_leaf(req, allowance=authority, policy=qualified_policy(), identity='held', attempt=1,
            installation=installation, deadline_ns=deadline, cancelled=cancelled,
            prepare_guest=lambda cap: (prepared.append(True) or capabilities.append(cap.encode()) or replace(req,env={**req.env,'FIXTURE_CAPABILITY':cap})))
        monitor.join(3)
        assert not failures and witness.get('scope_empty_while_ack_held') and not monitor.is_alive()
        assert out.holder_death is not None and not populated(holder.scope)
        assert len(prepared) == (1 if boundary == 'reservation' else 0)
        assert authority.state['consumed'] == (2 if boundary == 'reservation' else 1)
        assert backend.requests == (1 if boundary == 'reservation' else 0) and backend.crossed == 0
        assert not list(holder.sandbox.runref.iterdir()) and not list(holder.sandbox.gateway.path.iterdir())
        from tests.e2e.run_ref_provider_fixture import scan_canaries
        retired=scan_canaries({'all_fixture':tmp_path},upstream=secrets,
            credential_store=installation.native_home/'auth.json',
            capability=capabilities[0] if capabilities else None)
        assert retired['all_fixture']=={'upstream_outside_store':0,'capability':0}
        witness.update(retired_scan=retired)
        (tmp_path/'safe-witness.json').write_text(json.dumps(witness))
    finally:
        release.set()
        monitor.join(5)
        backend.close()


def test_inhibited_observer_negative_control_leaves_scope_live_while_binding_ack_is_held(launch, tmp_path, monkeypatch):
    from orchestrator.workflow.run_ref.provider_control import LeafCancellationObserver
    installation, _secrets, table = synthetic_home(tmp_path)
    backend = LocalBackend(tmp_path,table)
    holder = launch(network='model-only')
    offline_worker(monkeypatch,holder.sandbox,tmp_path)
    monkeypatch.setattr(LeafCancellationObserver,'start',lambda self:None)  # test-only omission, no runtime option
    ledger = tmp_path/'ledger'
    _allocate(ledger,tmp_path)
    authority = _projection(ledger,tmp_path)
    entered, release = threading.Event(), threading.Event()
    original = authority._emit
    def emit(kind,payload):
        ack = original(kind,payload)
        if kind=='provider_binding':
            entered.set()
            assert release.wait(6)
        return ack
    authority._emit = emit
    req = request('negative',timeout=5)
    deadline = boottime_ns()+2_000_000_000
    checked,failures = [],[]
    def observe():
        try:
            assert entered.wait(1.5)
            assert actual_native_pids(holder.slots['host'].members())
            while boottime_ns()<deadline+150_000_000:
                time.sleep(.005)
            assert populated(holder.scope) and not release.is_set()
            checked.append(True)  # no claim that native's own timeout keeps its process alive
        except BaseException as error:
            failures.append(type(error).__name__)
        finally:
            release.set()
    monitor = threading.Thread(target=observe)
    monitor.start()
    try:
        out = holder.run_provider_leaf(req,allowance=authority,policy=qualified_policy(),identity='negative',attempt=1,
            installation=installation,deadline_ns=deadline,cancelled=threading.Event(),
            prepare_guest=lambda cap: (_ for _ in ()).throw(AssertionError('late_activation')))
        monitor.join(3)
        assert checked and not failures and out.holder_death is not None
        assert not populated(holder.scope) and backend.requests==0
    finally:
        release.set()
        monitor.join(3)
        backend.close()


@pytest.mark.parametrize('point', ['exit-before-loan','exit-after-loan','kill-before-ack','cancel-after-bind'])
def test_worker_crash_loan_bind_ack_has_known_cleanup_and_no_auth_or_release(launch, tmp_path, monkeypatch, point):
    installation, _secrets, _table = synthetic_home(tmp_path)
    holder = launch(network='model-only')
    offline_worker(monkeypatch, holder.sandbox, tmp_path, mode=point)
    ledger = tmp_path/'ledger'
    _allocate(ledger, tmp_path)
    authority = _projection(ledger, tmp_path)
    cancelled, prepared = threading.Event(), []
    bind = holder.sandbox.gateway.bind_socket
    def bound(borrowed):
        identity = bind(borrowed)
        if point == 'kill-before-ack':
            holder.slots['host'].kill()
        if point == 'cancel-after-bind':
            cancelled.set()
        return identity
    monkeypatch.setattr(holder.sandbox.gateway, 'bind_socket', bound)
    req = request('loan', timeout=5)
    out = holder.run_provider_leaf(req, allowance=authority, policy=qualified_policy(), identity='loan', attempt=1,
        installation=installation, deadline_ns=boottime_ns()+5_000_000_000, cancelled=cancelled,
        prepare_guest=lambda cap: prepared.append(True))
    assert out.holder_death is not None and not prepared and not populated(holder.scope)
    assert not list(holder.sandbox.gateway.path.iterdir()) and not list(holder.sandbox.runref.iterdir())
    events = (tmp_path/'native-events.jsonl').read_text()
    assert 'native_spawn' not in events and 'initialize' not in events
    assert authority.state['consumed'] == 1 and b'provider_binding' not in ledger.read_bytes()


@pytest.mark.parametrize('mode', ['close-failure','hold-failure-exit'])
def test_guest_status_zero_cannot_hide_worker_transport_or_native_close_failure(launch, tmp_path, monkeypatch, mode):
    installation, _secrets, table = synthetic_home(tmp_path)
    backend = LocalBackend(tmp_path, table)
    if mode == 'hold-failure-exit':
        backend.status = 401
    holder = launch(network='model-only')
    offline_worker(monkeypatch, holder.sandbox, tmp_path, mode=mode)
    ledger = tmp_path/'ledger'
    _allocate(ledger, tmp_path)
    authority = _projection(ledger, tmp_path)
    statuses, imported = [], []
    original_status = holder._await_status
    def status(*args, **kwargs):
        result = original_status(*args, **kwargs)
        statuses.append(result[0])
        (tmp_path/'allow-worker-exit').touch()
        return result
    monkeypatch.setattr(holder,'_await_status',status)
    monkeypatch.setattr(holder,'_import',lambda req: imported.append(True))
    req = request('failed',timeout=8)
    if mode == 'hold-failure-exit':
        # A malicious/buggy guest can ignore transport failure and exit 0.
        original = req.argv[2]
        guarded = 'try:\n'+''.join('    '+line+'\n' for line in original.splitlines())+'except Exception:\n    pass\n'
        req = replace(req,argv=(*req.argv[:2],guarded))
    try:
        out = holder.run_provider_leaf(req,allowance=authority,policy=qualified_policy(),identity='failed',attempt=1,
            installation=installation,deadline_ns=boottime_ns()+8_000_000_000,cancelled=threading.Event(),
            prepare_guest=lambda cap: replace(req,env={**req.env,'FIXTURE_CAPABILITY':cap}))
        assert statuses == [0] and out.holder_death is not None and not imported
        assert not populated(holder.scope) and not list(holder.sandbox.gateway.path.iterdir())
        assert backend.requests == 1 and backend.crossed == 0 and authority.state['consumed'] == 1
    finally:
        (tmp_path/'allow-worker-exit').touch()
        backend.close()


def test_external_controller_sigkill_stops_actual_worker_native_and_leaf_then_recovery_retires_script(
        launch, sealed_image, tmp_path, monkeypatch):
    from orchestrator.workflow.run_ref.holder_scope import recover_holder_scopes
    from orchestrator.providers.inference_gateway import TransportGate
    from orchestrator.workflow.run_ref.provider_control import PrivateChannel
    from tests.e2e.run_ref_provider_fixture import ROOT, NativeInstallation
    record = tmp_path/'image-record.json'
    record.write_text(json.dumps(sealed_image.record))
    host, child = socket.socketpair()
    code = ('from tests.e2e.run_ref_provider_fixture import lost_controller;'
            'import sys;lost_controller(sys.argv[1],int(sys.argv[2]),sys.argv[3],int(sys.argv[4]))')
    process = subprocess.Popen([sys.executable,'-c',code,str(tmp_path),str(sealed_image.root_fd),str(record),str(child.fileno())],
        cwd=ROOT,env={key:value for key,value in os.environ.items() if key in {'PATH','HOME','XDG_RUNTIME_DIR','DBUS_SESSION_BUS_ADDRESS'}},
        pass_fds=(child.fileno(),sealed_image.root_fd),stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    child.close()
    channel = PrivateChannel(host,TransportGate(deadline_ns=boottime_ns()+12_000_000_000))
    scope = None
    try:
        message = channel.receive()  # capability only across this private in-memory fixture pipe
        scope, script, capability = Path(message['scope']), Path(message['script']), message['capability']
        assert message['native_pids'] and message['host_pids']
        until = boottime_ns()+2_000_000_000
        leaf_active = False
        while boottime_ns()<until:
            leaf_active = any(populated(path) for path in scope.iterdir() if path.is_dir()
                              and str(path) not in {message['host_slot'],message['holder_slot']})
            if script.exists() and leaf_active:
                break
            time.sleep(.005)
        assert leaf_active and script.exists() and capability.encode() in script.read_bytes()
        assert populated(scope)
        process.kill()
        process.wait(timeout=2)
        until = boottime_ns()+int((SLOT_EMPTY_SECONDS+.3)*1e9)
        while populated(scope) and boottime_ns()<until:
            time.sleep(.005)
        assert not populated(scope)
        for pid in message['host_pids']:
            status = Path(f'/proc/{pid}/stat')
            assert not status.exists() or status.read_text().split(') ',1)[1].startswith('Z')
        assert script.exists()  # pending revoked residue, not a cleanup claim
        control = tmp_path/'control'
        assert recover_holder_scopes(control,readonly=True) is True and script.exists()
        before = (tmp_path/'ledger').read_bytes()
        assert recover_holder_scopes(control) is True and not script.parent.parent.exists()
        assert (tmp_path/'ledger').read_bytes() == before  # recovery has no refund/append
        # A new incarnation must use a new directory/owner. Presenting the old
        # capability is rejected before any request auth, permit or POST.
        holder = launch(network='model-only')
        offline_worker(monkeypatch,holder.sandbox,tmp_path)
        authority = _projection(tmp_path/'ledger',tmp_path)
        installation = NativeInstallation(Path('/native/codex'),tmp_path/'native-home',tmp_path/'host-home')
        req = request('stale',timeout=8)
        prepared = []
        def prepare(_new_capability):
            assert not script.parent.parent.exists()
            prepared.append((tmp_path/'native-events.jsonl').read_bytes())
            return replace(req,env={**req.env,'FIXTURE_CAPABILITY':capability})
        out = holder.run_provider_leaf(req,allowance=authority,policy=qualified_policy(),identity='stale',attempt=1,
            installation=installation,deadline_ns=boottime_ns()+8_000_000_000,cancelled=threading.Event(),prepare_guest=prepare)
        assert out.holder_death is not None and len(prepared)==1
        assert (tmp_path/'native-events.jsonl').read_bytes() == prepared[0]
        assert authority.state['consumed']==2 and not populated(holder.scope)
        assert not list(holder.sandbox.runref.iterdir())
        (tmp_path/'safe-loss-witness.json').write_text(json.dumps(dict(controller_sigkill=True,scope_empty=True,
            actual_native_count=len(message['native_pids']),script_pending_after_loss=True,
            script_absent_after_recovery=True,old_capability_additional_auth=0,old_capability_additional_posts=0,
            old_capability_additional_reservations=0,new_directory=True)))
    finally:
        channel.close()
        if process.poll() is None:
            process.kill()
        process.wait(timeout=2)
        if scope is not None and populated(scope):
            recover_holder_scopes(tmp_path/'control')


@pytest.mark.parametrize('blocked', ['head','persist'])
@pytest.mark.parametrize('reason', ['expiry','cancel'])
def test_existing_parallel_future_writer_chain_cannot_delay_scope_revocation(launch, tmp_path, monkeypatch, blocked, reason):
    from orchestrator.workflow.evaluated import parallel, run_ref as adapter
    from orchestrator.workflow.run_ref import ledger, runtime
    from orchestrator.workflow.run_ref.confined_provider import VisitProviderAllowance
    from orchestrator.workflow.run_ref.confined_lifecycle import _layout
    from tests.test_workflow_run_ref_runtime import _runtime_request
    from tests.test_workflow_run_ref_ledger import _allocated_bindings
    from tests.workflow_evaluated_parallel_helpers import replay_case
    installation, _secrets, table = synthetic_home(tmp_path)
    backend = LocalBackend(tmp_path,table)
    holder = launch(network='model-only')
    offline_worker(monkeypatch,holder.sandbox,tmp_path)
    geometry = tmp_path/'geometry'
    geometry.mkdir()
    request_context = _runtime_request(geometry)
    initial = ledger.allocate_attempt(request_context.ledger_path,visit=request_context.visit,
        bindings=_allocated_bindings(tmp_path),confined_opening=dict(limit_ns=1000000,boot_id='boot',since_ns=100))
    layout = _layout(request_context,1)
    layout.workspace.parent.mkdir(parents=True)
    layout.child_root.mkdir(parents=True)
    allocation = runtime.RunRefLifecycleAllocation(1,request_context.parent_run_root,initial.bindings,
        expected_ledger_sequence=2,expected_previous_row_digest=initial.row_digest,retained=initial)
    entered, release, cancelled, done = (threading.Event() for _ in range(4))
    failures, results, writers, allowance = [], [], [], []
    active = dict(target=False,held=False)
    old_adapter, old_load, old_persist = adapter.persist_parallel_run_ref_event, ledger.load_attempt_ledger, runtime.persist_run_ref_lifecycle_event
    def hold():
        active['held'] = True
        entered.set()
        assert release.wait(10)
    def persistence(lifecycle,event,sequence,previous):
        active['target'] = event.event_kind == 'provider_binding'
        try:
            return old_adapter(lifecycle,event,sequence,previous)
        finally:
            active['target'] = False
    def load(*args,**kwargs):
        if blocked=='head' and active['target'] and not active['held']:
            hold()
        return old_load(*args,**kwargs)
    def persist(request_context,event):
        if blocked=='persist' and active['target'] and not active['held']:
            hold()
        writers.append(threading.get_ident())
        return old_persist(request_context,event)
    monkeypatch.setattr(adapter,'persist_parallel_run_ref_event',persistence)
    monkeypatch.setattr(ledger,'load_attempt_ledger',load)
    monkeypatch.setattr(runtime,'persist_run_ref_lifecycle_event',persist)
    with replay_case(tmp_path/'coordinator') as parent_authority:
        coordinator = parallel.ParallelCoordinator(None,parent_authority,{})
        token = object()
        coordinator.e1_owner,coordinator.e1_lifecycle = token,(request_context,allocation,None)
        deadline = boottime_ns()+(3_000_000_000 if reason=='expiry' else 8_000_000_000)
        def child_lifecycle():
            sequence = 0
            def emit(kind,payload):
                nonlocal sequence
                sequence += 1
                event = runtime.RunRefLifecycleEvent.build(sequence=sequence,event_kind=kind,stage='allocated',
                    visit=request_context.visit,attempt_ordinal=1,effect_instance_root=request_context.parent_run_root,
                    payload={'event':payload})
                return coordinator.request('event',token,request_context,event)
            try:
                authority = VisitProviderAllowance(None,request_context.visit,1,emit)
                allowance.append(authority)
                req = request('future',timeout=8)
                results.append(holder.run_provider_leaf(req,allowance=authority,policy=qualified_policy(),
                    identity='future',attempt=1,installation=installation,deadline_ns=deadline,cancelled=cancelled,
                    prepare_guest=lambda cap: (_ for _ in ()).throw(AssertionError('late_activation'))))
            except BaseException as error:
                failures.append(type(error).__name__)
            finally:
                done.set()
        child = threading.Thread(target=child_lifecycle)
        child.start()
        checked = []
        def observe():
            try:
                assert entered.wait(5)
                assert child.is_alive() and not done.is_set() and populated(holder.scope)
                if reason=='cancel':
                    cancelled.set()
                target = deadline if reason=='expiry' else boottime_ns()
                until = target+int((SLOT_EMPTY_SECONDS+.3)*1e9)
                while populated(holder.scope) and boottime_ns()<until:
                    time.sleep(.005)
                assert not populated(holder.scope) and not release.is_set() and not done.is_set()
                checked.append(True)
            except BaseException as error:
                failures.append(type(error).__name__)
            finally:
                release.set()
        monitor = threading.Thread(target=observe)
        monitor.start()
        try:
            until = time.monotonic()+12
            while not done.is_set() and time.monotonic()<until:
                try:
                    item = coordinator.queue.get(timeout=.05)
                except Empty:
                    continue
                coordinator._service(item)  # real _event → scope/head → persist → durable reread → Future
            child.join(3)
            monitor.join(3)
            assert not failures and checked and done.is_set() and len(results)==1
            assert results[0].holder_death is not None and not populated(holder.scope)
            assert writers and set(writers)=={threading.get_ident()}
            assert allowance[0].state['consumed']==1 and backend.requests==0
            assert not list(holder.sandbox.runref.iterdir())
        finally:
            cancelled.set()
            release.set()
            coordinator._stop(RuntimeError('synthetic_fixture_cleanup'))
            until = time.monotonic()+5
            while child.is_alive() and time.monotonic()<until:
                try:
                    coordinator._service(coordinator.queue.get(timeout=.05))
                except Empty:
                    pass
                child.join(.01)
            monitor.join(5)
            backend.close()


def test_guest_raw_encoded_and_named_capability_copies_preserve_bytes_but_not_runtime_diagnostics(
        launch,tmp_path,monkeypatch):
    import base64
    from orchestrator.workflow.run_ref.checkpoint import checkpoint_workspace
    from tests.e2e.run_ref_image_fixture import PYTHON
    from tests.e2e.run_ref_provider_fixture import scan_canaries
    installation,secrets,table=synthetic_home(tmp_path)
    backend=LocalBackend(tmp_path,table)
    holder=launch(network='model-only')
    offline_worker(monkeypatch,holder.sandbox,tmp_path)
    ledger=tmp_path/'ledger';_allocate(ledger,tmp_path);authority=_projection(ledger,tmp_path)
    req=request('copies')
    extra="""
import base64,sys
cap=os.environ['FIXTURE_CAPABILITY'];encoded=base64.b64encode(cap.encode())
sys.stdout.write(cap);sys.stderr.buffer.write(encoded)
open('/result/copies/raw','wb').write(cap.encode())
open('/result/copies/encoded','wb').write(encoded)
open('/workspace/raw','wb').write(cap.encode())
open('/workspace/encoded','wb').write(encoded)
open('/workspace/'+cap,'wb').write(b'guest-named-file')
"""
    req=replace(req,argv=(*req.argv[:-1],req.argv[-1]+extra))
    memory=[];events=[]
    original_import=holder._import
    def importing(value):
        holder.sandbox.require_quiescent();holder.sandbox.gateway.require_empty()
        assert not list(holder.sandbox.runref.iterdir())
        events.append('closed_before_import')
        return original_import(value)
    monkeypatch.setattr(holder,'_import',importing)
    try:
        out=holder.run_provider_leaf(req,allowance=authority,policy=qualified_policy(),identity='copies',attempt=1,
            installation=installation,deadline_ns=boottime_ns()+15_000_000_000,cancelled=threading.Event(),
            prepare_guest=lambda cap:(memory.append(cap.encode()) or replace(req,env={**req.env,'FIXTURE_CAPABILITY':cap})))
        assert out.holder_death is None and out.exit_code==0
        cap=memory[0];encoded=base64.b64encode(cap)
        assert out.stdout==cap and out.stderr==encoded
        assert out.result_files['raw']==cap and out.result_files['encoded']==encoded
        clone=tmp_path/'guest-checkpoint';clone.mkdir()
        disk=os.open(clone,os.O_RDONLY|os.O_DIRECTORY)
        try:
            holder.sandbox.require_quiescent();holder.sandbox.gateway.require_empty()
            assert events==['closed_before_import'] and not list(holder.sandbox.runref.iterdir())
            checkpoint_workspace(holder.root_fd('workspace'),disk,tmp_path/'header',
                effect_identity='copies',ordinal=1,max_bytes=1<<20)
        finally:
            os.close(disk)
        assert (clone/'raw').read_bytes()==cap and (clone/'encoded').read_bytes()==encoded
        assert (clone/cap.decode()).read_bytes()==b'guest-named-file'
        roots={'all_fixture':tmp_path,'control':holder.sandbox.control_dir,
            'workspace':Path(f'/proc/self/fd/{holder.root_fd("workspace")}'),
            'result':Path(f'/proc/self/fd/{holder.root_fd("result")}')}
        counts=scan_canaries(roots,upstream=secrets,credential_store=installation.native_home/'auth.json',capability=cap)
        assert all(row['upstream_outside_store']==0 for row in counts.values())
        assert counts['control']['capability']==0 and counts['result']['capability']==0
        assert counts['workspace']['capability']==2 and counts['all_fixture']['capability']==2
        # A subsequent command copies the retained old capability into an
        # invalid result name. It must not become a diagnostic field.
        script="import os; cap=open('/workspace/raw').read(); os.mkfifo('/result/poison/'+cap)"
        refused=holder.run_leaf(replace(leaf('poison','true'),argv=(PYTHON,'-c',script)))
        assert refused.holder_death is not None
        assert cap not in refused.holder_death.detail.encode()
        assert refused.holder_death.detail=='result_read_refused'
        # Present the value recovered from the preserved guest checkpoint to a
        # fresh incarnation. Its native preflight is independent; the bad
        # request itself causes no acquisition, reservation or upstream POST.
        next_holder=launch(network='model-only')
        offline_worker(monkeypatch,next_holder.sandbox,tmp_path)
        stale=request('stale-copy',timeout=8)
        before=[];posts=backend.requests
        def prepare_stale(_new_capability):
            before.append((tmp_path/'native-events.jsonl').read_bytes())
            return replace(stale,env={**stale.env,'FIXTURE_CAPABILITY':(clone/'raw').read_text()})
        denied=next_holder.run_provider_leaf(stale,allowance=authority,policy=qualified_policy(),
            identity='stale-copy',attempt=1,installation=installation,
            deadline_ns=boottime_ns()+8_000_000_000,cancelled=threading.Event(),prepare_guest=prepare_stale)
        assert denied.holder_death is not None and len(before)==1
        assert (tmp_path/'native-events.jsonl').read_bytes()==before[0]
        assert authority.state['consumed']==2 and backend.requests==posts
        (tmp_path/'safe-copy-witness.json').write_text(json.dumps(dict(guest_copy_counts=counts,
            exact_raw_encoded_preserved=True,closed_before_import_and_checkpoint=True,
            old_capability_name_diagnostic_absent=True,old_copy_additional_auth=0,
            old_copy_additional_posts=0,old_copy_additional_reservations=0)))
    finally:
        backend.close()


def test_last_permit_then_nplus1_keeps_budget_error_after_actual_scope_stop_without_extra_auth_or_post(
        launch,tmp_path,monkeypatch):
    from orchestrator.workflow.run_ref.runtime import RunRefRuntimeError
    installation,_secrets,table=synthetic_home(tmp_path)
    backend=LocalBackend(tmp_path,table)
    holder=launch(network='model-only')
    offline_worker(monkeypatch,holder.sandbox,tmp_path)
    ledger=tmp_path/'ledger';_allocate(ledger,tmp_path);authority=_projection(ledger,tmp_path)
    for _ in range(31):
        authority.reserve(qualified_policy().record,identity='limit',attempt=1)
    req=request('limit',count=2,timeout=15)
    imported=[]
    monkeypatch.setattr(holder,'_import',lambda value:imported.append(True))
    try:
        with pytest.raises(RunRefRuntimeError) as caught:
            holder.run_provider_leaf(req,allowance=authority,policy=qualified_policy(),identity='limit',attempt=1,
                installation=installation,deadline_ns=boottime_ns()+15_000_000_000,cancelled=threading.Event(),
                prepare_guest=lambda cap:replace(req,env={**req.env,'FIXTURE_CAPABILITY':cap}))
        assert caught.value.code=='run_ref_budget_exhausted'
        events=[json.loads(line) for line in (tmp_path/'native-events.jsonl').read_text().splitlines()]
        assert sum(event['phase']=='getAuthStatus' for event in events)==2
        assert sum(event['phase']=='inference_request' for event in events)==1
        assert authority.state['consumed']==32 and backend.requests==1 and not imported
        assert not populated(holder.scope) and not holder.sandbox._host_operation.locked()
        assert not list(holder.sandbox.runref.iterdir()) and not list(holder.sandbox.gateway.path.iterdir())
    finally:
        backend.close()
