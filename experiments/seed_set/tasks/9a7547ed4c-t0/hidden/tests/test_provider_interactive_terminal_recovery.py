"""Real transport ownership and restart cleanup, without paid providers."""
from __future__ import annotations

from dataclasses import replace
import json
import fcntl
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import time

import pytest

from orchestrator.providers.interactive_terminal import (
    InteractiveMemberInvocation,
    InteractiveTerminalTurnQueueAdapter,
)
from orchestrator.providers.types import InteractiveSessionSupport

pytestmark = pytest.mark.skipif(shutil.which('tmux') is None, reason='tmux unavailable')


def _wait(predicate, seconds=5):
    deadline = time.monotonic() + seconds
    while not predicate():
        assert time.monotonic() < deadline, 'condition never became true'
        time.sleep(.01)


def _invocation(root, script):
    return InteractiveMemberInvocation(
        invocation_id='restart', member_id='writer', attempt_scope_key='scope',
        attempt_ordinal=0, resolved_command=(sys.executable, '-c', script),
        cwd=root, env=os.environ.copy(), support=InteractiveSessionSupport(
            schema_version='interactive_terminal_turn_queue.v1',
            turn_boundary_messages=True, command=('fake', '${PROMPT}'),
            message_submit_keys=('ENTER',), graceful_close_text='exit',
            graceful_close_submit_keys=('ENTER',)),
    )


def test_reservation_is_closed_private_and_recovers_without_handle():
    with tempfile.TemporaryDirectory(prefix='orc-r-') as path:
        root = Path(path)
        reservation = InteractiveTerminalTurnQueueAdapter.reserve_recoverable(root)
        record = reservation.to_dict()
        assert set(record) == {'schema_version', 'adapter_token', 'namespace',
                              'namespace_dev', 'namespace_ino', 'namespace_uid',
                              'lease_dev', 'lease_ino', 'boot_id'}
        namespace = root / record['namespace']
        assert namespace.stat().st_mode & 0o777 == 0o700
        assert (namespace / 'launch.lock').stat().st_mode & 0o777 == 0o600
        assert len(record['adapter_token']) == 32
        restored = type(reservation).from_dict(root, json.loads(json.dumps(record)))
        adapter = InteractiveTerminalTurnQueueAdapter(root, socket_root=root)
        evidence = adapter.recover_failed(restored, deadline=time.monotonic()+3)
        assert evidence.cleanup_complete
        assert (namespace / 'revoked').read_text() == record['adapter_token']


def test_handle_free_cleanup_stops_hup_term_resistant_group():
    with tempfile.TemporaryDirectory(prefix='orc-r-') as path:
        root = Path(path)
        reservation = InteractiveTerminalTurnQueueAdapter.reserve_recoverable(root)
        adapter = InteractiveTerminalTurnQueueAdapter(root, socket_root=root)
        writes = root / 'writes'
        script = ('import signal,time\nfrom pathlib import Path\n'
                  'signal.signal(signal.SIGHUP,signal.SIG_IGN)\n'
                  'signal.signal(signal.SIGTERM,signal.SIG_IGN)\n'
                  f'p=Path({str(writes)!r})\n'
                  'while True:\n p.open("a").write("x");time.sleep(.01)')
        outcome = adapter.start(_invocation(root, script),
                                deadline=time.monotonic()+8, reservation=reservation)
        assert outcome.status == 'started', outcome
        _wait(writes.exists)
        fresh = InteractiveTerminalTurnQueueAdapter(root, socket_root=root)
        try:
            evidence = fresh.recover_failed(reservation, deadline=time.monotonic()+4)
            assert evidence.cleanup_complete, evidence
            size = writes.stat().st_size
            time.sleep(.08)
            assert writes.stat().st_size == size
            client = json.loads((root/reservation.namespace/'client.json').read_text())
            with pytest.raises(ProcessLookupError):
                os.killpg(client['pgid'], 0)
        finally:
            fresh.recover_failed(reservation, deadline=time.monotonic()+3)


@pytest.mark.parametrize('replacement', ['namespace', 'lease'])
def test_recovery_refuses_replaced_identity(replacement):
    with tempfile.TemporaryDirectory(prefix='orc-r-') as path:
        root = Path(path)
        reservation = InteractiveTerminalTurnQueueAdapter.reserve_recoverable(root)
        namespace = root / reservation.namespace
        if replacement == 'namespace':
            namespace.rename(root/'original')
            namespace.mkdir(mode=0o700)
        else:
            (namespace/'launch.lock').rename(namespace/'original.lock')
            (namespace/'launch.lock').touch(mode=0o600)
        adapter = InteractiveTerminalTurnQueueAdapter(root, socket_root=root)
        evidence = adapter.recover_failed(reservation, deadline=time.monotonic()+2)
        assert not evidence.cleanup_complete
        assert not (namespace/'revoked').exists()


def test_active_creating_helper_and_failed_missing_socket_never_prove_absence():
    with tempfile.TemporaryDirectory(prefix='orc-r-') as path:
        root = Path(path)
        reservation = InteractiveTerminalTurnQueueAdapter.reserve_recoverable(root)
        namespace = root / reservation.namespace
        adapter = InteractiveTerminalTurnQueueAdapter(root, socket_root=root)
        command = {'schema_version':'interactive_terminal_command.v1',
                   'adapter_token':reservation.adapter_token, 'operation_token':'a'*32,
                   'kind':'start_server', 'state':'active'}
        (namespace/'command.json').write_text(json.dumps(command))
        (namespace/'command.json').chmod(0o600)
        assert not adapter.recover_failed(reservation, deadline=time.monotonic()+1).cleanup_complete
        command.update(state='completed', outcome='timed_out')
        (namespace/'command.json').write_text(json.dumps(command))
        assert not adapter.recover_failed(reservation, deadline=time.monotonic()+1).cleanup_complete


def test_natural_zero_exit_with_residual_group_is_refused_then_cleaned():
    with tempfile.TemporaryDirectory(prefix='orc-r-') as path:
        root = Path(path)
        reservation = InteractiveTerminalTurnQueueAdapter.reserve_recoverable(root)
        adapter = InteractiveTerminalTurnQueueAdapter(root, socket_root=root)
        script = ('import os,signal,time,sys\n'
                  'signal.signal(signal.SIGHUP,signal.SIG_IGN)\n'
                  'sys.stdin.readline()\np=os.fork()\n'
                  'if p == 0:\n signal.signal(signal.SIGTERM,signal.SIG_IGN);time.sleep(30)')
        outcome = adapter.start(_invocation(root, script), deadline=time.monotonic()+8,
                                reservation=reservation)
        assert outcome.status == 'started', outcome
        try:
            adapter.offer_close(outcome.handle, deadline=time.monotonic()+5)
            with pytest.raises(Exception, match='process_group_not_empty'):
                adapter.join(outcome.handle, deadline=time.monotonic()+3)
            assert adapter.abort(outcome.handle, deadline=time.monotonic()+4).cleanup_complete
        finally:
            adapter.recover_failed(reservation, deadline=time.monotonic()+3)


@pytest.mark.parametrize('boundary', ['reserved', 'server_command', 'unrecorded_server',
                                     'recorded_server', 'pane_command', 'preexec', 'registered'])
def test_parent_sigkill_around_every_launch_boundary_is_recoverable(boundary):
    with tempfile.TemporaryDirectory(prefix='orc-k-') as path:
        root = Path(path)
        marker, release = root/'boundary', root/'release'
        wrapper = root/'tmux-client'
        wrapper.write_text(
            '#!'+sys.executable+'\nimport os,sys,time\nfrom pathlib import Path\n'
            f'kind={boundary!r}\nmarker=Path({str(marker)!r})\nrelease=Path({str(release)!r})\n'
            'if (kind == "server_command" and "new-session" in sys.argv) or '
            '(kind == "pane_command" and "new-window" in sys.argv):\n'
            ' marker.touch()\n while not release.exists(): time.sleep(.01)\n'
            f'os.execv({shutil.which("tmux")!r}, ["tmux", *sys.argv[1:]])\n')
        wrapper.chmod(0o700)
        delay = root/'delay.py'
        delay.write_text('import os,sys,time\nfrom pathlib import Path\n'
                         f'Path({str(marker)!r}).touch()\n'
                         f'while not Path({str(release)!r}).exists(): time.sleep(.01)\n'
                         'os.execv(sys.argv[1], sys.argv[1:])\n')
        script = '''import json,os,sys,time
from pathlib import Path
from orchestrator.providers import interactive_terminal as m
from orchestrator.providers import _interactive_terminal_lifecycle as life
from tests.test_provider_interactive_terminal_recovery import _invocation
root=Path(sys.argv[1]);boundary=sys.argv[2]
reservation=m.InteractiveTerminalTurnQueueAdapter.reserve_recoverable(root)
(root/'reservation.json').write_text(json.dumps(reservation.to_dict()))
def pause():
 (root/'boundary').touch()
 while not (root/'release').exists():time.sleep(.01)
class Backend(m._TmuxInteractiveTerminalBackend):
 def observe_server(self,*args,**kwargs):
  if boundary=='unrecorded_server':pause()
  super().observe_server(*args,**kwargs)
 def start_pane(self,*args,**kwargs):
  if boundary=='recorded_server':pause()
  return super().start_pane(*args,**kwargs)
original=life.helper_argv
def helper(*args):
 argv=original(*args)
 return [sys.executable,str(root/'delay.py'),*argv] if args[1]=='pane' and boundary=='preexec' else argv
life.helper_argv=helper
adapter=m.InteractiveTerminalTurnQueueAdapter(root,socket_root=root,backend=Backend(str(root/'tmux-client')))
if boundary=='reserved':pause()
outcome=adapter.start(_invocation(root,'import time;time.sleep(30)'),deadline=time.monotonic()+10,reservation=reservation)
if boundary=='registered':pause()
assert outcome.status=='started',outcome
'''
        parent = subprocess.Popen([sys.executable, '-c', script, str(root), boundary],
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        reservation = None
        try:
            _wait(lambda: marker.exists() or parent.poll() is not None)
            assert parent.poll() is None, parent.communicate()
            from orchestrator.providers.interactive_terminal import InteractiveTerminalReservation
            reservation = InteractiveTerminalReservation.from_dict(root, json.loads((root/'reservation.json').read_text()))
            parent.kill()
            parent.communicate(timeout=2)
            if boundary in {'server_command', 'pane_command'}:
                fd = os.open(reservation.path/'launch.lock', os.O_RDWR | os.O_NOFOLLOW)
                try:
                    with pytest.raises(BlockingIOError):
                        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                finally:
                    os.close(fd)
            release.touch()
            fresh = InteractiveTerminalTurnQueueAdapter(root, socket_root=root)
            result = fresh.recover_failed(reservation, deadline=time.monotonic()+5)
            assert result.cleanup_complete, (boundary, result)
            assert not (reservation.path/'tmux.sock').exists()
        finally:
            release.touch()
            if parent.poll() is None:
                parent.kill()
                parent.communicate(timeout=2)
            if reservation is not None:
                InteractiveTerminalTurnQueueAdapter(root, socket_root=root).recover_failed(
                    reservation, deadline=time.monotonic()+3)


def test_delayed_preexec_cannot_execute_after_revocation_or_expired_deadline():
    from orchestrator.providers import _interactive_terminal_lifecycle as life
    for expired in (False, True):
        with tempfile.TemporaryDirectory(prefix='orc-p-') as path:
            root = Path(path)
            reservation = InteractiveTerminalTurnQueueAdapter.reserve_recoverable(root)
            marker = root/'provider-executed'
            with life.opened(reservation) as files:
                lease = life.acquire(reservation, files, time.monotonic()+2)
                child = subprocess.Popen(life.helper_argv(reservation, 'pane', time.monotonic()+(.15 if expired else 3))
                    + [sys.executable, '-c', f'from pathlib import Path;Path({str(marker)!r}).touch()'],
                    start_new_session=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                if expired:
                    time.sleep(.25)
                else:
                    life.write(reservation, files, 'revoked', reservation.adapter_token)
                os.close(lease)
            child.communicate(timeout=3)
            assert child.returncode != 0
            assert not marker.exists()


def test_creating_timeout_reaps_child_before_lease_release():
    from orchestrator.providers import _interactive_terminal_lifecycle as life
    with tempfile.TemporaryDirectory(prefix='orc-c-') as path:
        root = Path(path)
        reservation = InteractiveTerminalTurnQueueAdapter.reserve_recoverable(root)
        pid_path = root/'child.pid'
        command = [sys.executable, '-c', 'import os,time;from pathlib import Path;'
                   f'Path({str(pid_path)!r}).write_text(str(os.getpid()));time.sleep(30)']
        deadline = time.monotonic()+1.5
        with pytest.raises(TimeoutError):
            life.run_creating(reservation, 'start_server', command, None, deadline)
        assert time.monotonic() <= deadline+.2
        pid = int(pid_path.read_text())
        assert not Path(f'/proc/{pid}').exists()
        with life.opened(reservation) as files:
            lease = life.acquire(reservation, files, time.monotonic()+.5)
            try:
                result = life.record(reservation, files, 'command.json')
                assert result['state'] == 'completed'
                assert result['outcome'] == 'timed_out'
            finally:
                os.close(lease)


def test_abnormally_killed_helper_preserves_active_refusal():
    from orchestrator.providers import _interactive_terminal_lifecycle as life
    with tempfile.TemporaryDirectory(prefix='orc-c-') as path:
        root = Path(path)
        reservation = InteractiveTerminalTurnQueueAdapter.reserve_recoverable(root)
        acted = root/'child-acted'
        command = [sys.executable, '-c', 'import os,signal,time;from pathlib import Path;'
                   f'os.kill(os.getppid(),signal.SIGKILL);time.sleep(.15);Path({str(acted)!r}).touch()']
        with pytest.raises(life.OwnershipError):
            life.run_creating(reservation, 'start_server', command, None, time.monotonic()+3)
        _wait(acted.exists)
        result = InteractiveTerminalTurnQueueAdapter(root, socket_root=root).recover_failed(
            reservation, deadline=time.monotonic()+1)
        assert not result.cleanup_complete
        assert json.loads((reservation.path/'command.json').read_text())['state'] == 'active'


@pytest.mark.parametrize('damage', ['foreign_session', 'foreign_pid', 'server_pid', 'socket', 'symlink_record'])
def test_foreign_server_socket_or_client_record_is_preserved(damage):
    with tempfile.TemporaryDirectory(prefix='orc-f-') as path:
        root = Path(path)
        reservation = InteractiveTerminalTurnQueueAdapter.reserve_recoverable(root)
        adapter = InteractiveTerminalTurnQueueAdapter(root, socket_root=root)
        outcome = adapter.start(_invocation(root, 'import time;time.sleep(30)'),
                                reservation=reservation, deadline=time.monotonic()+8)
        assert outcome.status == 'started', outcome
        client_path, server_path = reservation.path/'client.json', reservation.path/'server.json'
        client_bytes, server_bytes = client_path.read_bytes(), server_path.read_bytes()
        socket_path = reservation.path/'tmux.sock'
        socket_original = reservation.path/'saved.sock'
        tmux = [shutil.which('tmux'), '-S', str(socket_path)]
        try:
            if damage == 'foreign_session':
                subprocess.run(tmux+['rename-session','-t',reservation.session,'foreign'],check=True)
                server_path.unlink()  # exercise the pre-observation, full-token rule too
            elif damage == 'foreign_pid':
                client = json.loads(client_bytes)
                client['leader_start_ticks'] += 1
                client_path.write_text(json.dumps(client))
            elif damage == 'server_pid':
                server = json.loads(server_bytes)
                server['server_start_ticks'] += 1
                server_path.write_text(json.dumps(server))
            elif damage == 'socket':
                socket_path.rename(socket_original)
                socket_path.touch(mode=0o600)
            else:
                client_path.unlink()
                client_path.symlink_to(root/'untrusted-client')
            result = adapter.recover_failed(reservation, deadline=time.monotonic()+2)
            assert not result.cleanup_complete
            assert socket_path.exists()
            os.killpg(json.loads(client_bytes)['pgid'], 0)
        finally:
            if damage == 'foreign_session':
                subprocess.run(tmux+['rename-session','-t','foreign',reservation.session],check=True)
            elif damage == 'socket':
                socket_path.unlink()
                socket_original.rename(socket_path)
            if client_path.is_symlink():
                client_path.unlink()
            client_path.write_bytes(client_bytes)
            client_path.chmod(0o600)
            server_path.write_bytes(server_bytes)
            server_path.chmod(0o600)
            assert adapter.recover_failed(reservation, deadline=time.monotonic()+4).cleanup_complete


def test_explicit_reservation_start_and_recovery_allocate_no_extra_namespace():
    with tempfile.TemporaryDirectory(prefix='orc-l-') as path:
        root = Path(path)
        reservation = InteractiveTerminalTurnQueueAdapter.reserve_recoverable(root)
        adapter = InteractiveTerminalTurnQueueAdapter(root, socket_root=root, reservation=reservation)
        assert {p.name for p in root.iterdir()} == {reservation.namespace}
        outcome = adapter.start(_invocation(root, 'import time;time.sleep(30)'),
                                deadline=time.monotonic()+8)
        assert outcome.status == 'started', outcome
        try:
            assert {p.name for p in root.iterdir()} == {reservation.namespace}
        finally:
            fresh = InteractiveTerminalTurnQueueAdapter(root, socket_root=root)
            assert fresh.recover_failed(reservation, deadline=time.monotonic()+4).cleanup_complete
        assert {p.name for p in root.iterdir()} == {reservation.namespace}


def test_preexec_rechecks_deadline_after_last_revocation_read():
    with tempfile.TemporaryDirectory(prefix='orc-d-') as path:
        root = Path(path)
        reservation = InteractiveTerminalTurnQueueAdapter.reserve_recoverable(root)
        marker = root/'provider-executed'
        script = '''import json,sys,time
from pathlib import Path
from orchestrator.providers import _interactive_terminal_lifecycle as life
r=life.InteractiveTerminalReservation.from_dict(sys.argv[1],json.loads(sys.argv[2]))
original=life.record
count=0
def record(*args):
 global count
 result=original(*args)
 if args[-1]=='revoked':
  count+=1
  if count==2:time.sleep(.25)
 return result
life.record=record
life._pane(r,time.monotonic()+.15,[sys.executable,'-c',sys.argv[3]])
'''
        child = subprocess.run([sys.executable,'-c',script,str(root),json.dumps(reservation.to_dict()),
                                f'from pathlib import Path;Path({str(marker)!r}).touch()'],
                               start_new_session=True,capture_output=True,timeout=3)
        assert child.returncode != 0
        assert not marker.exists()


def test_command_rechecks_deadline_after_durable_active_write():
    from orchestrator.providers import _interactive_terminal_lifecycle as life
    with tempfile.TemporaryDirectory(prefix='orc-d-') as path:
        root=Path(path)
        reservation=InteractiveTerminalTurnQueueAdapter.reserve_recoverable(root)
        marker=root/'child-executed'
        script='''import json,sys,time
from orchestrator.providers import _interactive_terminal_lifecycle as life
r=life.InteractiveTerminalReservation.from_dict(sys.argv[1],json.loads(sys.argv[2]))
original=life.write
def write(*args):
 original(*args)
 if args[-2]=='command.json':time.sleep(.25)
life.write=write
life._command(r,time.monotonic()+.15,int(sys.argv[3]),'start_server',[sys.executable,'-c',sys.argv[4]])
'''
        with life.opened(reservation) as files:
            lease=life.acquire(reservation,files,time.monotonic()+1)
            try:
                child=subprocess.run([sys.executable,'-c',script,str(root),json.dumps(reservation.to_dict()),str(lease),
                                      f'from pathlib import Path;Path({str(marker)!r}).touch()'],
                                     pass_fds=(lease,),capture_output=True,timeout=3)
            finally:
                os.close(lease)
        assert child.returncode != 0
        assert not marker.exists()


def test_recovery_refuses_missing_command_with_recorded_resources():
    with tempfile.TemporaryDirectory(prefix='orc-d-') as path:
        root=Path(path)
        reservation=InteractiveTerminalTurnQueueAdapter.reserve_recoverable(root)
        adapter=InteractiveTerminalTurnQueueAdapter(root,socket_root=root,reservation=reservation)
        outcome=adapter.start(_invocation(root,'import time;time.sleep(30)'),deadline=time.monotonic()+5)
        assert outcome.status=='started',outcome
        command_path=reservation.path/'command.json'
        content=command_path.read_bytes()
        command_path.unlink()
        try:
            assert not adapter.recover_failed(reservation,deadline=time.monotonic()+2).cleanup_complete
        finally:
            command_path.write_bytes(content)
            command_path.chmod(0o600)
            assert adapter.recover_failed(reservation,deadline=time.monotonic()+3).cleanup_complete


def test_helper_output_settlement_cannot_outlive_original_deadline():
    from orchestrator.providers import _interactive_terminal_lifecycle as life
    with tempfile.TemporaryDirectory(prefix='orc-o-') as path:
        root=Path(path)
        reservation=InteractiveTerminalTurnQueueAdapter.reserve_recoverable(root)
        with life.opened(reservation) as files:
            lease=life.acquire(reservation,files,time.monotonic()+1)
            helper=subprocess.Popen(life.helper_argv(reservation,'command',time.monotonic()+.5)
                +[str(lease),'start_server',json.dumps([sys.executable,'-c',
                    'import sys;sys.stdout.write("x"*1048576)'])],
                pass_fds=(lease,),stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            os.close(lease)
            try:
                time.sleep(.8)  # deliberately leave helper's output pipe undrained
                assert helper.poll() is not None
                assert life.record(reservation,files,'command.json')['state']=='active'
            finally:
                if helper.poll() is None:
                    helper.kill()
                helper.communicate(timeout=2)


def test_failed_creation_with_delayed_socket_stays_unresolved_until_bound_server_found():
    from orchestrator.providers import _interactive_terminal_lifecycle as life
    with tempfile.TemporaryDirectory(prefix='orc-s-') as path:
        root=Path(path)
        reservation=InteractiveTerminalTurnQueueAdapter.reserve_recoverable(root)
        socket=reservation.path/'tmux.sock'
        delayed=[shutil.which('tmux'),'-f','/dev/null','-S',str(socket),'new-session','-d',
                 '-s',reservation.session,'-n','anchor','sleep 30']
        script='import subprocess,sys;subprocess.Popen([sys.executable,"-c",sys.argv[1]],'
        script+='stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True);sys.exit(1)'
        detached='import subprocess,time;time.sleep(.5);subprocess.run('+repr(delayed)+',check=True)'
        result=life.run_creating(reservation,'start_server',[sys.executable,'-c',script,detached],
                                 None,time.monotonic()+3)
        assert result.returncode==1
        adapter=InteractiveTerminalTurnQueueAdapter(root,socket_root=root)
        assert not adapter.recover_failed(reservation,deadline=time.monotonic()+.2).cleanup_complete
        try:
            _wait(socket.exists)
            assert adapter.recover_failed(reservation,deadline=time.monotonic()+3).cleanup_complete
        finally:
            adapter.recover_failed(reservation,deadline=time.monotonic()+2)


def test_live_lease_wait_never_gets_a_new_cleanup_deadline():
    from orchestrator.providers import _interactive_terminal_lifecycle as life
    with tempfile.TemporaryDirectory(prefix='orc-w-') as path:
        root=Path(path)
        reservation=InteractiveTerminalTurnQueueAdapter.reserve_recoverable(root)
        adapter=InteractiveTerminalTurnQueueAdapter(root,socket_root=root,reservation=reservation)
        with life.opened(reservation) as files:
            lease=life.acquire(reservation,files,time.monotonic()+1)
            try:
                start=time.monotonic()
                outcome=adapter.start(_invocation(root,'import time;time.sleep(30)'),deadline=start+.15)
                assert time.monotonic()-start < .4
                assert outcome.status=='failed'
                assert outcome.cleanup_status=='incomplete'
                assert not (reservation.path/'command.json').exists()
            finally:
                os.close(lease)
        assert adapter.recover_failed(reservation,deadline=time.monotonic()+1).cleanup_complete


def test_operational_json_duplicate_keys_are_refused():
    with tempfile.TemporaryDirectory(prefix='orc-j-') as path:
        root=Path(path)
        reservation=InteractiveTerminalTurnQueueAdapter.reserve_recoverable(root)
        command={'schema_version':'interactive_terminal_command.v1',
                 'adapter_token':reservation.adapter_token,'operation_token':'a'*32,
                 'kind':'start_server','state':'completed','outcome':'success'}
        raw=json.dumps(command)
        (reservation.path/'command.json').write_text(raw[:-1]+',"state":"completed"}')
        (reservation.path/'command.json').chmod(0o600)
        from orchestrator.providers import _interactive_terminal_lifecycle as life
        with life.opened(reservation) as files:
            with pytest.raises(life.OwnershipError):
                life.record(reservation,files,'command.json')


def test_natural_completion_uses_guarded_server_cleanup_without_unguarded_pane_kill(monkeypatch):
    from orchestrator.providers import interactive_terminal as module
    with tempfile.TemporaryDirectory(prefix='orc-n-') as path:
        root=Path(path)
        backend=module._TmuxInteractiveTerminalBackend()
        adapter=InteractiveTerminalTurnQueueAdapter(root,socket_root=root,backend=backend)
        outcome=adapter.start(_invocation(root,'import sys;sys.stdin.readline()'),deadline=time.monotonic()+6)
        assert outcome.status=='started',outcome
        def unguarded(*args,**kwargs):
            raise AssertionError('natural close must use guarded owned server cleanup')
        monkeypatch.setattr(backend,'close_pane',unguarded)
        try:
            adapter.offer_close(outcome.handle,deadline=time.monotonic()+4)
            proof=adapter.join(outcome.handle,deadline=time.monotonic()+3)
            assert proof.proof_complete
            assert proof.return_code==0
            assert not outcome.handle.socket_path.exists()
        finally:
            adapter.recover_failed(adapter._reservation,deadline=time.monotonic()+3)


def test_exit_status_cannot_follow_symlink(monkeypatch):
    from orchestrator.providers import interactive_terminal as module
    with tempfile.TemporaryDirectory(prefix='orc-e-') as path:
        root=Path(path)
        reservation=InteractiveTerminalTurnQueueAdapter.reserve_recoverable(root)
        external=root/'untrusted-status'
        external.write_text('0\n')
        status=reservation.path/'provider.exit-status'
        status.symlink_to(external)
        backend=module._TmuxInteractiveTerminalBackend()
        backend.bind_recoverable(reservation,time.monotonic()+3)
        socket=reservation.path/'tmux.sock'
        backend._exit_status_paths[(socket,'%1')]=status
        monkeypatch.setattr(backend,'_run',lambda *args,**kwargs: subprocess.CompletedProcess([],0,b'1|',b''))
        with pytest.raises(module.InteractiveTerminalError,match='recorded_exit_status_unreadable'):
            backend.pane_process_status(socket,'%1',timeout_sec=1)


@pytest.mark.parametrize('startup', ['shell', 'python'])
def test_private_server_and_preexec_do_not_run_user_shell_startup(startup):
    with tempfile.TemporaryDirectory(prefix='orc-b-') as path:
        root=Path(path)
        reservation=InteractiveTerminalTurnQueueAdapter.reserve_recoverable(root)
        marker=root/'unregistered-shell-executed'
        shell=root/'custom-shell'
        shell.write_text('#!/bin/sh\nif [ ! -f '+str(reservation.path/'client.json')+' ]; then '
                         'touch '+str(marker)+'; fi\nexec /bin/sh "$@"\n')
        shell.chmod(0o700)
        (root/'sitecustomize.py').write_text('from pathlib import Path\n'
            f'if not Path({str(reservation.path / "client.json")!r}).exists():\n'
            f' Path({str(marker)!r}).touch()\n')
        environment = {**os.environ, 'SHELL':str(shell)} if startup == 'shell' else {**os.environ, 'PYTHONPATH':str(root)}
        invocation=replace(_invocation(root,'import time;time.sleep(30)'),env=environment)
        adapter=InteractiveTerminalTurnQueueAdapter(root,socket_root=root,reservation=reservation)
        outcome=adapter.start(invocation,deadline=time.monotonic()+6)
        assert outcome.status=='started',outcome
        try:
            assert not marker.exists()
        finally:
            assert adapter.recover_failed(reservation,deadline=time.monotonic()+3).cleanup_complete


def test_namespace_is_private_from_initial_mkdir_even_with_permissive_umask(monkeypatch):
    from orchestrator.providers import _interactive_terminal_lifecycle as life
    with tempfile.TemporaryDirectory(prefix='orc-mode-') as path:
        root = Path(path)
        modes = []
        original = os.mkdir
        def mkdir(name, mode=0o777, *, dir_fd=None):
            original(name, mode, dir_fd=dir_fd)
            if str(name).startswith('orc-peer-'):
                modes.append(os.stat(name, dir_fd=dir_fd, follow_symlinks=False).st_mode & 0o777)
        monkeypatch.setattr(life.os, 'mkdir', mkdir)
        previous_umask = os.umask(0)
        try:
            reservation = InteractiveTerminalTurnQueueAdapter.reserve_recoverable(root)
        finally:
            os.umask(previous_umask)
        assert modes == [0o700]
        assert reservation.path.stat().st_mode & 0o777 == 0o700


@pytest.mark.parametrize('interruption', ['repeat', 'sigkill_after_guarded_kill'])
def test_unobserved_server_recovery_is_durable_and_repeatable(monkeypatch, interruption):
    from orchestrator.providers import interactive_terminal as module
    with tempfile.TemporaryDirectory(prefix='orc-repeat-') as path:
        root = Path(path)
        reservation = InteractiveTerminalTurnQueueAdapter.reserve_recoverable(root)
        backend = module._TmuxInteractiveTerminalBackend()
        backend.bind_recoverable(reservation, time.monotonic()+5)
        def interrupted_observation(*args, **kwargs):
            raise RuntimeError('interrupted before server record')
        monkeypatch.setattr(backend, 'observe_server', interrupted_observation)
        with pytest.raises(RuntimeError, match='interrupted before server record'):
            backend.start_server(reservation.path/'tmux.sock', reservation.session,
                                 env=os.environ.copy(), timeout_sec=5)
        assert not (reservation.path/'server.json').exists()
        adapter = InteractiveTerminalTurnQueueAdapter(root, socket_root=root)
        refusals = []
        validate_server = adapter._backend.validate_reserved_server
        def capture_refusal(*args, **kwargs):
            try:
                return validate_server(*args, **kwargs)
            except Exception as exc:
                from orchestrator.providers import _interactive_terminal_lifecycle as life
                state = {'error': repr(exc)}
                server = life.record(args[0], args[1], 'server.json')
                state['server'] = server
                state['current_start_ticks'] = None if server is None else life.start_token(server['server_pid'])
                try:
                    info = args[1].stat('tmux.sock')
                    state['socket'] = (info.st_dev, info.st_ino)
                except FileNotFoundError:
                    state['socket'] = None
                refusals.append(state)
                raise
        monkeypatch.setattr(adapter._backend, 'validate_reserved_server', capture_refusal)
        recovery = None
        try:
            if interruption == 'repeat':
                assert adapter.recover_failed(reservation, deadline=time.monotonic()+3).cleanup_complete
            else:
                marker = root/'server-killed'
                script = '''import json,sys,time
from pathlib import Path
from orchestrator.providers import interactive_terminal as m
root=Path(sys.argv[1])
r=m.InteractiveTerminalReservation.from_dict(root,json.loads(sys.argv[2]))
class Backend(m._TmuxInteractiveTerminalBackend):
 def _run(self,socket,*args,**kwargs):
  result=super()._run(socket,*args,**kwargs)
  if args[0]=='if-shell' and 'kill-server' in args and result.returncode==0:
   (root/'server-killed').touch()
   while True:time.sleep(.01)
  return result
adapter=m.InteractiveTerminalTurnQueueAdapter(root,socket_root=root,backend=Backend())
result=adapter.recover_failed(r,deadline=time.monotonic()+5)
raise SystemExit(0 if result.cleanup_complete else 1)
'''
                recovery = subprocess.Popen([sys.executable, '-c', script, str(root),
                                             json.dumps(reservation.to_dict())],
                                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                _wait(lambda: marker.exists() or recovery.poll() is not None)
                assert recovery.poll() is None, recovery.communicate()
                recovery.kill()
                recovery.communicate(timeout=2)
            result = adapter.recover_failed(reservation, deadline=time.monotonic()+3)
            assert result.cleanup_complete, refusals
            server = json.loads((reservation.path/'server.json').read_text())
            assert server['adapter_token'] == reservation.adapter_token
            assert server['server_pid'] > 0
            assert server['server_start_ticks'] > 0
            assert not (reservation.path/'tmux.sock').exists()
        finally:
            if recovery is not None and recovery.poll() is None:
                recovery.kill()
                recovery.communicate(timeout=2)
            adapter.recover_failed(reservation, deadline=time.monotonic()+3)


@pytest.mark.parametrize('operation', ['start_server', 'start_pane'])
def test_real_creation_methods_preserve_operation_timeout_cap(operation):
    from orchestrator.providers import interactive_terminal as module
    with tempfile.TemporaryDirectory(prefix='orc-cap-') as path:
        root = Path(path)
        reservation = InteractiveTerminalTurnQueueAdapter.reserve_recoverable(root)
        marker = root/'delayed-client.pid'
        wrapper = root/'tmux-client'
        delayed_command = 'new-session' if operation == 'start_server' else 'new-window'
        wrapper.write_text('#!/bin/sh\ncase " $* " in *" '+delayed_command+' "*) '
                           'echo $$ > '+str(marker)+'; sleep .4;; esac\n'
                           'exec '+shutil.which('tmux')+' "$@"\n')
        wrapper.chmod(0o700)
        backend = module._TmuxInteractiveTerminalBackend(str(wrapper))
        attempt_deadline = time.monotonic()+4
        backend.bind_recoverable(reservation, attempt_deadline)
        socket = reservation.path/'tmux.sock'
        adapter = InteractiveTerminalTurnQueueAdapter(root, socket_root=root)
        try:
            if operation == 'start_pane':
                backend.start_server(socket, reservation.session, env=os.environ.copy(), timeout_sec=2)
            started = time.monotonic()
            with pytest.raises(module.InteractiveTerminalError, match='backend_operation_timeout'):
                if operation == 'start_server':
                    backend.start_server(socket, reservation.session, env=os.environ.copy(), timeout_sec=.05)
                else:
                    backend.start_pane(socket, reservation.session,
                        (sys.executable, '-c', 'import time;time.sleep(30)'), cwd=root,
                        exit_status_path=reservation.path/'provider.exit-status', timeout_sec=.05)
            assert time.monotonic()-started < .25
            assert time.monotonic() < attempt_deadline
        finally:
            adapter.recover_failed(reservation, deadline=time.monotonic()+3)


@pytest.mark.parametrize('guard_boundary', ['preflight', 'kill'])
def test_recovery_rechecks_server_exit_when_guard_connection_loses_shutdown_race(monkeypatch, guard_boundary):
    from orchestrator.providers import interactive_terminal as module
    from orchestrator.providers import _interactive_terminal_lifecycle as life
    with tempfile.TemporaryDirectory(prefix='orc-shut-') as path:
        root = Path(path)
        reservation = InteractiveTerminalTurnQueueAdapter.reserve_recoverable(root)
        backend = module._TmuxInteractiveTerminalBackend()
        backend.bind_recoverable(reservation, time.monotonic()+5)
        backend.start_server(reservation.path/'tmux.sock', reservation.session,
                             env=os.environ.copy(), timeout_sec=3)
        server = json.loads((reservation.path/'server.json').read_text())
        run = backend._run
        injected_shutdown = False
        def stop_before_guard_connection(socket, *args, **kwargs):
            nonlocal injected_shutdown
            if (args[0] == 'if-shell' and not injected_shutdown
                    and ('kill-server' in args) == (guard_boundary == 'kill')):
                injected_shutdown = True
                pid = server['server_pid']
                assert life.start_token(pid) == str(server['server_start_ticks'])
                condition = '#{&&:#{==:#{session_name},'+reservation.session+'},#{==:#{pid},'+str(pid)+'}}'
                subprocess.run([shutil.which('tmux'), '-S', str(socket),
                                'if-shell', '-F', '-t', reservation.session+':anchor', condition,
                                'kill-server', 'display-message -p OWNERSHIP_MISMATCH'],
                               check=True, capture_output=True, timeout=2)
                _wait(lambda: life.start_token(pid) is None)
            return run(socket, *args, **kwargs)
        monkeypatch.setattr(backend, '_run', stop_before_guard_connection)
        adapter = InteractiveTerminalTurnQueueAdapter(root, socket_root=root, backend=backend)
        try:
            assert adapter.recover_failed(reservation, deadline=time.monotonic()+3).cleanup_complete
            assert injected_shutdown
            assert not (reservation.path/'tmux.sock').exists()
        finally:
            adapter.recover_failed(reservation, deadline=time.monotonic()+3)


def test_natural_join_requests_owned_server_reap_without_group_signals(monkeypatch):
    from orchestrator.providers import _interactive_terminal_lifecycle as life
    with tempfile.TemporaryDirectory(prefix='orc-reap-') as path:
        root = Path(path)
        reservation = InteractiveTerminalTurnQueueAdapter.reserve_recoverable(root)
        adapter = InteractiveTerminalTurnQueueAdapter(root, socket_root=root, reservation=reservation)
        outcome = adapter.start(_invocation(root, 'import sys;sys.stdin.readline()'), deadline=time.monotonic()+6)
        assert outcome.status == 'started'
        signals = []
        original_empty, original_kill, original_killpg = life.group_empty, os.kill, os.killpg
        reaped = False
        def group_empty(client):
            return reaped and original_empty(client)
        def kill(pid, sig):
            nonlocal reaped
            signals.append(('server', sig))
            result = original_kill(pid, sig)
            if sig == signal.SIGCHLD:
                reaped = True
            return result
        def killpg(pid, sig):
            if sig:
                signals.append(('group', sig))
            return original_killpg(pid, sig)
        try:
            adapter.offer_close(outcome.handle, deadline=time.monotonic()+4)
            with monkeypatch.context() as patch:
                patch.setattr(life, 'group_empty', group_empty)
                patch.setattr(os, 'kill', kill)
                patch.setattr(os, 'killpg', killpg)
                proof = adapter.join(outcome.handle, deadline=time.monotonic()+3)
            assert proof.return_code == 0 and proof.proof_complete
            assert ('server', signal.SIGCHLD) in signals
            assert not [row for row in signals if row[0] == 'group']
        finally:
            assert adapter.recover_failed(reservation, deadline=time.monotonic()+4).cleanup_complete


def test_recovery_reaps_only_after_resistant_group_escalation_then_is_idempotent(monkeypatch):
    from orchestrator.providers import _interactive_terminal_lifecycle as life
    with tempfile.TemporaryDirectory(prefix='orc-reap-') as path:
        root = Path(path)
        reservation = InteractiveTerminalTurnQueueAdapter.reserve_recoverable(root)
        adapter = InteractiveTerminalTurnQueueAdapter(root, socket_root=root, reservation=reservation)
        ready = root / 'ready'
        script = ('import signal,time;from pathlib import Path;'
            'signal.signal(signal.SIGHUP,signal.SIG_IGN);signal.signal(signal.SIGTERM,signal.SIG_IGN);'
            f'Path({str(ready)!r}).touch();time.sleep(30)')
        outcome = adapter.start(_invocation(root, script), deadline=time.monotonic()+6)
        assert outcome.status == 'started'
        _wait(ready.exists)
        events = []
        original_empty, original_kill, original_killpg = life.group_empty, os.kill, os.killpg
        reaped = False
        def group_empty(client):
            return reaped and original_empty(client)
        def killpg(pid, sig):
            if sig:
                events.append(sig)
            return original_killpg(pid, sig)
        def kill(pid, sig):
            nonlocal reaped
            if sig == signal.SIGCHLD:
                assert signal.SIGKILL in events
                events.append(sig)
                reaped = True
            return original_kill(pid, sig)
        try:
            with monkeypatch.context() as patch:
                patch.setattr(life, 'group_empty', group_empty)
                patch.setattr(os, 'killpg', killpg)
                patch.setattr(os, 'kill', kill)
                assert adapter.recover_failed(reservation, deadline=time.monotonic()+3).cleanup_complete
            assert events.index(signal.SIGTERM) < events.index(signal.SIGKILL) < events.index(signal.SIGCHLD)
            assert adapter.recover_failed(reservation, deadline=time.monotonic()+3).cleanup_complete
        finally:
            assert adapter.recover_failed(reservation, deadline=time.monotonic()+4).cleanup_complete


@pytest.mark.parametrize('damage', ['foreign-token', 'absent-token', 'token-drift-after-preflight', 'signal-error'])
def test_server_reap_refuses_unmatched_identity_or_failed_signal_without_other_signals(monkeypatch, damage):
    from orchestrator.providers import _interactive_terminal_lifecycle as life
    with tempfile.TemporaryDirectory(prefix='orc-reap-') as path:
        root = Path(path)
        reservation = InteractiveTerminalTurnQueueAdapter.reserve_recoverable(root)
        adapter = InteractiveTerminalTurnQueueAdapter(root, socket_root=root, reservation=reservation)
        outcome = adapter.start(_invocation(root, 'import time;time.sleep(30)'), deadline=time.monotonic()+6)
        assert outcome.status == 'started'
        try:
            with life.opened(reservation) as files:
                lease = life.acquire(reservation, files, time.monotonic()+3)
                try:
                    command = life.record(reservation, files, 'command.json')
                    server = life.record(reservation, files, 'server.json')
                    original_token, original_kill = life.start_token, os.kill
                    signals = []
                    validated = False
                    validate = adapter._backend.validate_reserved_server
                    def validate_then_drift(*args, **kwargs):
                        nonlocal validated
                        value = validate(*args, **kwargs)
                        validated = True
                        return value
                    def token(pid):
                        if pid == server['server_pid'] and (damage != 'token-drift-after-preflight' or validated):
                            return None if damage == 'absent-token' else str(server['server_start_ticks'] + 1)
                        return original_token(pid)
                    def kill(pid, sig):
                        signals.append((pid, sig))
                        if damage == 'signal-error':
                            raise PermissionError('reap denied')
                        return original_kill(pid, sig)
                    with monkeypatch.context() as patch:
                        patch.setattr(os, 'kill', kill)
                        if damage != 'signal-error':
                            patch.setattr(life, 'start_token', token)
                        if damage == 'token-drift-after-preflight':
                            patch.setattr(adapter._backend, 'validate_reserved_server', validate_then_drift)
                        with pytest.raises((life.OwnershipError, OSError, TimeoutError)):
                            adapter._backend.request_server_reap(reservation, files, command, deadline=time.monotonic()+.3)
                    if damage == 'signal-error':
                        assert signals == [(server['server_pid'], signal.SIGCHLD)]
                    else:
                        assert not signals
                finally:
                    os.close(lease)
        finally:
            assert adapter.recover_failed(reservation, deadline=time.monotonic()+4).cleanup_complete


def test_recovery_interrupted_after_reap_notification_remains_retryable(monkeypatch):
    from orchestrator.providers import _interactive_terminal_lifecycle as life
    with tempfile.TemporaryDirectory(prefix='orc-reap-') as path:
        root = Path(path)
        reservation = InteractiveTerminalTurnQueueAdapter.reserve_recoverable(root)
        adapter = InteractiveTerminalTurnQueueAdapter(root, socket_root=root, reservation=reservation)
        outcome = adapter.start(_invocation(root, 'import time;time.sleep(30)'), deadline=time.monotonic()+6)
        assert outcome.status == 'started'
        original_empty, original_kill = life.group_empty, os.kill
        notified = False
        def group_empty(client):
            return notified and original_empty(client)
        def kill(pid, sig):
            nonlocal notified
            result = original_kill(pid, sig)
            if sig == signal.SIGCHLD:
                notified = True
                raise RuntimeError('controller stopped after notification')
            return result
        try:
            with monkeypatch.context() as patch:
                patch.setattr(life, 'group_empty', group_empty)
                patch.setattr(os, 'kill', kill)
                assert not adapter.recover_failed(reservation, deadline=time.monotonic()+1).cleanup_complete
                assert notified
            assert adapter.recover_failed(reservation, deadline=time.monotonic()+4).cleanup_complete
            assert adapter.recover_failed(reservation, deadline=time.monotonic()+2).cleanup_complete
        finally:
            assert adapter.recover_failed(reservation, deadline=time.monotonic()+4).cleanup_complete


@pytest.mark.parametrize('mode', ['natural', 'failed'])
def test_subreaper_controller_reaps_only_its_exact_owned_server(tmp_path, mode):
    script = r'''
import ctypes,json,os,subprocess,sys,tempfile,time
from pathlib import Path
from orchestrator.providers import _interactive_terminal_lifecycle as life
from orchestrator.providers.interactive_terminal import InteractiveTerminalTurnQueueAdapter
from tests.test_provider_interactive_terminal_recovery import _invocation
assert ctypes.CDLL(None).prctl(36,1,0,0,0)==0
mode=sys.argv[1]
unrelated=subprocess.Popen([sys.executable,'-c','raise SystemExit(0)'])
with tempfile.TemporaryDirectory(prefix='orc-subreap-') as path:
 root=Path(path)
 reservation=InteractiveTerminalTurnQueueAdapter.reserve_recoverable(root)
 adapter=InteractiveTerminalTurnQueueAdapter(root,socket_root=root,reservation=reservation)
 outcome=adapter.start(_invocation(root,'import sys;sys.stdin.readline()' + ('' if mode=='natural' else ';raise SystemExit(7)')),deadline=time.monotonic()+8)
 assert outcome.status=='started'
 print('test-owned server',json.loads((reservation.path/'server.json').read_text()),flush=True)
 try:
  if mode=='natural':
   adapter.offer_close(outcome.handle,deadline=time.monotonic()+5)
   proof=adapter.join(outcome.handle,deadline=time.monotonic()+5)
   assert proof.return_code==0 and proof.proof_complete
  else:
   adapter.offer_close(outcome.handle,deadline=time.monotonic()+5)
   client=json.loads((reservation.path/'client.json').read_text())
   exited=time.monotonic()+3
   leader=Path('/proc')/str(client['leader_pid'])/'stat'
   while leader.exists():
    try:state=leader.read_text().rsplit(') ',1)[1].split()[0]
    except FileNotFoundError:break
    if state=='Z':break
    assert time.monotonic()<exited
    time.sleep(.01)
   assert (reservation.path/'provider.exit-status').read_text().strip()=='7'
   assert adapter.recover_failed(reservation,deadline=time.monotonic()+5).cleanup_complete
  server=json.loads((reservation.path/'server.json').read_text())
  assert life.start_token(server['server_pid']) is None
  assert not (reservation.path/'tmux.sock').exists()
  assert adapter.recover_failed(reservation,deadline=time.monotonic()+2).cleanup_complete
  assert adapter.recover_failed(reservation,deadline=time.monotonic()+2).cleanup_complete
  limit=time.monotonic()+2
  stat_path=Path('/proc')/str(unrelated.pid)/'stat'
  while stat_path.read_text().rsplit(') ',1)[1].split()[0]!='Z':
   assert time.monotonic()<limit
   time.sleep(.01)
  pid,status=os.waitpid(unrelated.pid,os.WNOHANG)
  assert pid==unrelated.pid and os.waitstatus_to_exitcode(status)==0
  unrelated.returncode=0
 finally:
  server_path=reservation.path/'server.json'
  if server_path.exists():
   server=json.loads(server_path.read_text())
   if life.start_token(server['server_pid'])==str(server['server_start_ticks']):
    try:os.waitpid(server['server_pid'],os.WNOHANG)
    except ChildProcessError:pass
  cleanup=adapter.recover_failed(reservation,deadline=time.monotonic()+3)
  print('final exact-reservation cleanup',cleanup,flush=True)
  unrelated.wait(timeout=2)
  assert cleanup.cleanup_complete
'''
    result = subprocess.run([sys.executable, '-c', script, mode], capture_output=True, text=True,
        cwd=Path(__file__).resolve().parents[1], timeout=30,
        env={**os.environ, 'PYTHONPATH': str(Path(__file__).resolve().parents[1])})
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize('identity', ['absent', 'mismatched', 'unreadable', 'expired', 'live-child', 'non-child', 'wait-error'])
def test_server_exit_wait_reaps_only_matching_children_and_never_assumes_absence(monkeypatch, identity):
    from orchestrator.providers import interactive_terminal as terminal
    from orchestrator.providers import _interactive_terminal_lifecycle as life
    backend = terminal._TmuxInteractiveTerminalBackend()
    server = {'server_pid': 12345, 'server_start_ticks': 100}
    calls = []
    def token(pid):
        assert pid == server['server_pid']
        if identity == 'unreadable':
            raise life.OwnershipError('cannot read server token')
        return None if identity == 'absent' else '101' if identity == 'mismatched' else '100'
    def waitpid(pid, flags):
        calls.append((pid, flags))
        if identity == 'wait-error':
            raise PermissionError('cannot reap')
        if identity == 'live-child':
            return 0, 0
        raise ChildProcessError('not a child')
    with monkeypatch.context() as patch:
        patch.setattr(life, 'start_token', token)
        patch.setattr(os, 'waitpid', waitpid)
        if identity == 'absent':
            backend._wait_server_exit(server, deadline=time.monotonic()+.04)
        else:
            expected = PermissionError if identity == 'wait-error' else (life.OwnershipError, terminal.InteractiveTerminalError)
            with pytest.raises(expected):
                backend._wait_server_exit(server, deadline=time.monotonic()+(-.01 if identity == 'expired' else .04))
    if identity in {'absent', 'mismatched', 'unreadable', 'expired'}:
        assert not calls
    else:
        assert calls and set(calls) == {(server['server_pid'], os.WNOHANG)}
