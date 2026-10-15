"""Offline-only synthetic owner fixture, never a production installation input.

The JWT encoder follows the retained native upstream fixture pattern. There is
no credential reader/parser here: only Codex reads the fictitious auth store.
"""
from __future__ import annotations

import base64
import datetime
import http.server
import json
import os
from pathlib import Path
import signal
import socket
import socketserver
import subprocess
import sys
import threading
import time
import traceback
from dataclasses import replace

from orchestrator.providers import inference_gateway as core
from orchestrator.workflow.run_ref.provider_worker import NativeInstallation

NATIVE = Path('/home/ollie/.nvm/versions/node/v20.19.4/lib/node_modules/@openai/codex/node_modules/@openai/codex-linux-x64/vendor/x86_64-unknown-linux-musl/bin/codex')
ROOT = Path(__file__).resolve().parents[2]


def actual_native_pids(members):
    """Pinned mounted executable identity, independent of Rust thread names."""
    expected=NATIVE.stat()
    found=[]
    for pid in members:
        try:
            actual=Path(f'/proc/{pid}/exe').stat()
        except FileNotFoundError:
            continue
        if (actual.st_dev,actual.st_ino)==(expected.st_dev,expected.st_ino):
            found.append(pid)
    return found


def _jwt(account, serial):
    def encode(value):
        return base64.urlsafe_b64encode(json.dumps(value).encode()).rstrip(b'=').decode()
    return encode({'alg':'none','typ':'JWT'})+'.'+encode({
        'exp':4102444800, 'fixture':serial, 'email':'fixture@example.invalid',
        'https://api.openai.com/auth':{'chatgpt_account_id':account,
            'chatgpt_user_id':'fixture-user-'+account, 'chatgpt_plan_type':'pro'}})+'.c2lnbmF0dXJl'


def synthetic_home(base):
    home, host = base/'native-home', base/'host-home'
    home.mkdir(mode=0o700)
    host.mkdir(mode=0o700)
    account = 'holder-synthetic-account-A'
    access, identity, refresh = _jwt(account, 1), _jwt(account, 2), 'holder-synthetic-refresh-CANARY'
    store = home/'auth.json'
    store.write_text(json.dumps({'auth_mode':'chatgpt','OPENAI_API_KEY':None,'tokens':{
        'id_token':identity,'access_token':access,'refresh_token':refresh,'account_id':account},
        'last_refresh':datetime.datetime.now(datetime.timezone.utc).isoformat()}))
    store.chmod(0o600)
    (home/'config.toml').write_text('cli_auth_credentials_store = "file"\n')
    return NativeInstallation(Path('/native/codex'), home, host), (access.encode(), identity.encode(), refresh.encode()), {access:account}


def worker_entry(control_fd, deadline_ns, base, mode):
    """Runs behind the verified host trampoline, in a disconnected bwrap."""
    from orchestrator.workflow.run_ref import provider_worker as worker
    assert not Path('/home/ollie/.codex').exists() and not Path('/run/user').exists()
    base = Path(base)
    def event(value):
        with (base/'native-events.jsonl').open('a') as target:
            target.write(json.dumps(value)+'\n')
    event({'phase':'worker_entry'})
    account = 'holder-synthetic-account-A'
    class Discovery(http.server.BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass
        def do_GET(self):
            good = (self.path == '/backend-api/wham/accounts/check'
                    and self.headers.get('Authorization') == 'Bearer '+_jwt(account,1)
                    and self.headers.get('chatgpt-account-id') == account)
            event({'phase':'discovery', 'binding_valid':bool(good)})
            payload = json.dumps({'accounts':[{'id':account,'workspace_backend_origin':'https://chatgpt.com',
                'account_routing_override':'NO_CONSTRAINT'}]} if good else {}).encode()
            self.send_response(200 if good else 401)
            self.send_header('Content-Length',str(len(payload)))
            self.send_header('Connection','close')
            self.end_headers()
            self.wfile.write(payload)
        def do_POST(self):
            event({'phase':'unexpected_native_post'})
            self.send_response(401)
            self.send_header('Content-Length','0')
            self.end_headers()
    discovery = http.server.ThreadingHTTPServer(('127.0.0.1',0), Discovery)
    threading.Thread(target=discovery.serve_forever, daemon=True).start()
    original_prepare = worker.prepare_native_launch
    def prepare(*args, **kwargs):
        launch = original_prepare(*args, **kwargs)
        argv = list(launch.argv)
        index = next(i for i, value in enumerate(argv) if value.startswith('chatgpt_base_url='))
        argv[index] = 'chatgpt_base_url='+json.dumps(f'http://127.0.0.1:{discovery.server_port}/backend-api/')
        return replace(launch, argv=tuple(argv))
    worker.prepare_native_launch = prepare
    original_write = core.NativeAuthOwner._write
    def observed(owner, message):
        method = message.get('method')
        if method in {'initialize','initialized','account/read','getAuthStatus'}:
            event({'phase':method})
        if mode == 'stop-initialize' and method == 'initialize':
            os.kill(owner._process.pid, signal.SIGSTOP)
            (base/'suspended').touch()
        if mode == 'stop-acquisition' and method == 'getAuthStatus':
            os.kill(owner._process.pid, signal.SIGSTOP)
            (base/'suspended').touch()
        return original_write(owner, message)
    core.NativeAuthOwner._write = observed
    if mode == 'close-failure':
        original_close = core.NativeAuthOwner.close
        def close_failed(owner):
            original_close(owner)
            event({'phase':'native_close_unconfirmed'})
            raise core.InferenceTransportRefused('native_close_unconfirmed')
        core.NativeAuthOwner.close = close_failed
    if mode in {'exit-before-loan','exit-after-loan'}:
        from orchestrator.workflow.run_ref.provider_control import PrivateChannel
        original_loan = PrivateChannel.send_listener
        def loan(channel, listener):
            if mode == 'exit-after-loan':
                original_loan(channel, listener)
            os._exit(124)
        PrivateChannel.send_listener = loan
    if mode == 'hold-failure-exit':
        held_serve = worker.serve
        def hold_exit(*args):
            result = held_serve(*args)
            event({'phase':'service_refused', 'graceful':result})
            until = time.monotonic()+5
            while not (base/'allow-worker-exit').exists() and time.monotonic()<until:
                time.sleep(.005)
            return result
        worker.serve = hold_exit
    original_spawn = subprocess.Popen
    def spawn(argv, *args, **kwargs):
        assert set(kwargs['env']) == {'PATH','HOME','CODEX_HOME','LANG','RUST_LOG',
                                    'CODEX_INTERNAL_APP_SERVER_REMOTE_CONTROL_DISABLED'}
        process = original_spawn(argv, *args, **kwargs)
        # Stop the actual pinned executable, never its Python placement shim.
        expected=Path('/native/codex').stat()
        while True:
            actual=Path(f'/proc/{process.pid}/exe').stat()
            if (actual.st_dev,actual.st_ino)==(expected.st_dev,expected.st_ino):
                break
            assert process.poll() is None and core.boottime_ns()<deadline_ns
            time.sleep(.002)
        event({'phase':'native_spawn'})
        if mode == 'stop-startup':
            os.kill(process.pid, signal.SIGSTOP)
            (base/'suspended').touch()
            threading.Event().wait(60)
        return process
    subprocess.Popen = spawn
    class LocalHTTPS(core.FixedHTTPSConnection):
        def request(self, *args, **kwargs):
            event({'phase':'inference_request'})
            return super().request(*args, **kwargs)
        def connect(self):
            self._check_send()
            connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            connection.settimeout(max(.001, (self._gate.deadline_ns-core.boottime_ns())/1e9))
            self.transport = connection
            connection.connect(str(base/'upstream.sock'))
            self.sock = connection
            self._check_send()
    core.FixedHTTPSConnection = LocalHTTPS
    def diagnostic(value):
        with (base/'worker-categories.jsonl').open('a') as target:
            target.write(json.dumps(value)+'\n')
    def observed_method(original, phase):
        def observed(*args, **kwargs):
            diagnostic({'phase':phase+'_begin'})
            try:
                result=original(*args, **kwargs)
                diagnostic({'phase':phase+'_complete'})
                return result
            except Exception as error:
                import re
                category = (str(error) if isinstance(error,core.InferenceTransportRefused)
                            and re.fullmatch('[a-z_]{1,64}',str(error)) else type(error).__name__)
                diagnostic({'phase':phase,'category':category})
                raise
        return observed
    core.InferenceGatewayCore.preflight = observed_method(core.InferenceGatewayCore.preflight,'preflight_refused')
    core.InferenceGatewayCore.dispatch = observed_method(core.InferenceGatewayCore.dispatch,'dispatch_refused')
    core.InferenceGatewayCore.close = observed_method(core.InferenceGatewayCore.close,'close_refused')
    from orchestrator.workflow.run_ref.provider_control import WorkerControlClient
    WorkerControlClient.ready=observed_method(WorkerControlClient.ready,'ready_refused')
    original_serve = worker.serve
    def observed_serve(*args):
        try:
            result=original_serve(*args)
        except Exception as error:
            diagnostic({'phase':'serve_exception','category':type(error).__name__,
                        'thread_creation_failed':isinstance(error,RuntimeError) and str(error)=="can't start new thread"})
            raise
        diagnostic({'phase':'serve_exit','graceful':result})
        return result
    worker.serve = observed_serve
    try:
        return worker.main(control_fd, deadline_ns)
    finally:
        discovery.shutdown()
        discovery.server_close()


def offline_worker(monkeypatch, sandbox, base, *, mode='normal'):
    """Only the worker/native get this fixture wrapper; Holder remains the real runtime."""
    from orchestrator.workflow.run_ref import provider_transport
    assert core._file_digest(NATIVE) == core.NATIVE_BINARY_DIGEST
    entry = '''
import sys
sys.path.insert(0, sys.argv[1])
from tests.e2e.run_ref_provider_fixture import worker_entry
raise SystemExit(worker_entry(int(sys.argv[2]), int(sys.argv[3]), BASE, MODE))
'''.replace('BASE',repr(str(base))).replace('MODE',repr(mode))
    monkeypatch.setattr(provider_transport, '_ENTRY', entry)
    start = sandbox.start_host_worker
    def launch(argv, **kwargs):
        wrapper = ['/usr/bin/bwrap','--unshare-all','--die-with-parent','--cap-drop','ALL',
            '--ro-bind','/usr','/usr','--ro-bind','/bin','/bin','--ro-bind','/lib','/lib',
            '--ro-bind','/lib64','/lib64','--proc','/proc','--dev','/dev','--tmpfs','/tmp',
            '--dir','/etc','--dir','/run','--ro-bind',sys.prefix,sys.prefix,
            '--ro-bind',str(ROOT),str(ROOT),'--ro-bind',str(NATIVE),'/native/codex',
            '--bind',str(base),str(base),'--chdir',str(kwargs['cwd']), '--', *argv]
        return start(wrapper, **kwargs)
    monkeypatch.setattr(sandbox, 'start_host_worker', launch)
    original = provider_transport.LeafProviderTransport.start
    def observed_start(transport):
        try:
            return original(transport)
        except Exception as error:
            # Closed controller category only; never native stderr or payload.
            from orchestrator.workflow.run_ref.provider_control import ProviderControlRefused
            category = str(error) if type(error) is ProviderControlRefused else type(error).__name__
            (base/'controller-category.json').write_text(json.dumps({'category':category,
                'frames':[[Path(frame.filename).name, frame.name, frame.lineno]
                          for frame in traceback.extract_tb(error.__traceback__)]}))
            raise
    monkeypatch.setattr(provider_transport.LeafProviderTransport, 'start', observed_start)
    original_close = provider_transport.LeafProviderTransport.close
    def observed_close(transport):
        try:
            return original_close(transport)
        except Exception as error:
            (base/'close-category.json').write_text(json.dumps(dict(category=type(error).__name__,
                worker_exit=None if transport.process is None else transport.process.poll(),
                pids_max_events=(int((transport.sandbox.path/'pids.events').read_text().split()[1])
                    if (transport.sandbox.path/'pids.events').exists() else None),
                socket_owned=transport.socket_identity is not None,revoked=transport.observer.revoked.is_set(),
                frames=[[Path(frame.filename).name,frame.name,frame.lineno]
                        for frame in traceback.extract_tb(error.__traceback__)])))
            raise
    monkeypatch.setattr(provider_transport.LeafProviderTransport,'close',observed_close)


class LocalBackend(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    daemon_threads = True

    def __init__(self, base, table):
        self.table, self.requests, self.crossed, self.status = table, 0, 0, 200
        self.observed = threading.Event()
        super().__init__(str(base/'upstream.sock'), BackendHandler)
        self.thread = threading.Thread(target=self.serve_forever, daemon=True)
        self.thread.start()

    def close(self):
        self.shutdown()
        self.server_close()
        self.thread.join(2)


class BackendHandler(http.server.BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'

    def log_message(self, *_args):
        pass

    def do_POST(self):
        token = self.headers.get('Authorization','').removeprefix('Bearer ')
        account = self.headers.get('chatgpt-account-id')
        good = account and self.server.table.get(token) == account
        if not good:
            self.server.crossed += 1
        size = int(self.headers.get('Content-Length','0'))
        assert size <= core.REQUEST_BODY_BYTES
        self.rfile.read(size)
        self.server.requests += 1
        self.server.observed.set()
        events = [{'type':'response.created','response':{'id':'synthetic-response'}},
                  {'type':'response.completed','response':{'id':'synthetic-response'}}]
        payload = b''.join(b'data: '+json.dumps(event).encode()+b'\n\n' for event in events)
        self.send_response(self.server.status if good and self.path == '/backend-api/codex/responses' else 401)
        self.send_header('Content-Type','text/event-stream')
        self.send_header('Content-Length',str(len(payload)))
        self.send_header('Connection','close')
        self.end_headers()
        try:
            self.wfile.write(payload)
        except (BrokenPipeError, ConnectionResetError):
            pass


GUEST = '''
import errno,http.client,json,os,socket
assert os.listdir('/run/runref-gateway')==['gateway.sock']
for path in ['/run/gateway.sock','/run/runref-gateway/gateway.sock']:
    try:os.unlink(path)
    except OSError as error:assert error.errno==errno.EROFS
    else:raise AssertionError('guest_mutated_gateway')
body=open('/result/LEAF/request.json','rb').read()
for _ in range(COUNT):
    connection=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
    connection.connect('/run/gateway.sock')
    header=('POST /v1/responses HTTP/1.1\\r\\nHost: fixture\\r\\nContent-Type: application/json\\r\\nAuthorization: Bearer '+os.environ['FIXTURE_CAPABILITY']+'\\r\\nContent-Length: '+str(len(body))+'\\r\\n\\r\\n').encode()
    connection.sendall(header+body)
    response=http.client.HTTPResponse(connection);response.begin()
    assert response.status==200
    data=response.read();assert b'response.completed' in data
    response.close();connection.close()
open('/result/LEAF/done.json','w').write('true')
'''


def request(name, *, count=1, timeout=15):
    from orchestrator.workflow.run_ref.leaf import LeafRequest
    from tests.e2e.run_ref_image_fixture import PYTHON, PATH
    body = json.dumps({'model':'gpt-5.5','stream':True,'reasoning':{'effort':'low'},
                       'tools':json.loads(core.qualified_policy().tools_bytes)}).encode()
    invocation = (PYTHON,'-c',GUEST.replace('LEAF',name).replace('COUNT',str(count)))
    return LeafRequest(name, invocation, PATH, '/workspace', timeout, 1024, 1024,
                       {'request.json':body}, 'model-only')


def lost_controller(base, image_fd, image_record, channel_fd):
    """External synthetic controller for the actual SIGKILL descendant witness."""
    import pytest
    from orchestrator.workflow.run_ref.holder import Holder
    from orchestrator.workflow.run_ref.image_store import SealedImage
    from orchestrator.workflow.run_ref.provider_control import PrivateChannel
    from tests.e2e.run_ref_image_fixture import LIMITS, PYTHON
    from tests.test_run_ref_provider_allowance import _allocate, _projection
    base = Path(base)
    image = SealedImage(image_fd,json.loads(Path(image_record).read_text()))
    installation, _secrets, table = synthetic_home(base)
    backend = LocalBackend(base,table)
    control = base/'control'
    control.mkdir(mode=0o700,exist_ok=True)
    holder = Holder(image,LIMITS,control_dir=control,network='model-only').launch()
    patch = pytest.MonkeyPatch()
    offline_worker(patch,holder.sandbox,base)
    ledger = base/'ledger'
    _allocate(ledger,base)
    authority = _projection(ledger,base)
    deadline = core.boottime_ns()+30_000_000_000
    channel = PrivateChannel(socket.socket(fileno=channel_fd),core.TransportGate(deadline_ns=deadline))
    req = replace(request('loss',timeout=30),argv=(PYTHON,'-c','import time; time.sleep(60)'))
    def prepare(capability):
        members = holder.slots['host'].members()
        native = actual_native_pids(members)
        channel.send(dict(scope=str(holder.scope),unit=holder.unit,host_pids=list(members),native_pids=native,
                          host_slot=str(holder.slots['host'].path),holder_slot=str(holder.slots['holder'].path),
                          script=str(holder.sandbox.runref/'loss'/'leaf.sh'),capability=capability))
        return replace(req,env={**req.env,'FIXTURE_CAPABILITY':capability})
    try:
        holder.run_provider_leaf(req,allowance=authority,policy=core.qualified_policy(),identity='loss',attempt=1,
            installation=installation,deadline_ns=deadline,cancelled=threading.Event(),prepare_guest=prepare)
    finally:
        channel.close()
        holder.stop()
        backend.close()


def scan_canaries(roots, *, upstream, credential_store, capability=None):
    """Test-only full-root scan; return counts, never names, content or tokens.

    All names, link targets and regular-file bytes are inspected. Only the
    exact intended native credential file is exempt for upstream credentials;
    it is still included in the capability oracle.
    """
    import stat
    totals={}
    for label, root in roots.items():
        counts={'upstream_outside_store':0,'capability':0}
        for parent, directories, files in os.walk(root, followlinks=False):
            for name in directories+files:
                path=Path(parent)/name
                try:
                    info=path.lstat()
                    raw=os.fsencode(name)
                    if stat.S_ISLNK(info.st_mode):
                        raw+=os.fsencode(os.readlink(path))
                    elif stat.S_ISREG(info.st_mode):
                        fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
                        with os.fdopen(fd,'rb') as stream:
                            raw+=stream.read()
                except FileNotFoundError:
                    continue  # concurrent native retirement, not an exclusion
                if path != credential_store:
                    counts['upstream_outside_store']+=sum(raw.count(value) for value in upstream)
                if capability is not None:
                    counts['capability']+=raw.count(capability)
        totals[label]=counts
    return totals
