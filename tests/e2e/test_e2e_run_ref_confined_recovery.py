"""External controller SIGKILL at real confined child boundaries through the public CLI.

Observers pause after genuine durable writes or around real holder/helper operations;
no holder, scope, copier, memo, ledger or CLI implementation is replaced by a fake.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

import pytest

from orchestrator.workflow.run_ref.ledger import load_attempt_ledger
from orchestrator.workflow.run_ref.holder_scope import recover_holder_scopes
from tests.e2e.test_e2e_run_ref_confined_child import (
    refs, _candidate, PARENT, READ, STOP, REPOSITORY, _cli, _settled, _child_memo, _clone_digest, _retained_checkpoint,
)

pytestmark = pytest.mark.e2e

OBSERVER = r'''
import json, os, sys, time
from pathlib import Path
from orchestrator.workflow.run_ref import holder_scope, confined_session, holder
from orchestrator.workflow.run_ref import runtime as lifecycle
from orchestrator.workflow.evaluated import runtime, run_ref
control, gap = Path(os.environ['T7_CONTROL']), os.environ['T7_GAP']
def log(name, row):
    with (control / name).open('ab', buffering=0) as stream:
        stream.write(json.dumps(row, sort_keys=True).encode() + b'\n')
        os.fsync(stream.fileno())
def pause(where):
    (control / 'marker.json').write_text(json.dumps(dict(gap=where, pid=os.getpid())))
    while True: time.sleep(1)
real_release = holder_scope.HolderScope._release
def release(self, sock):
    if gap == 'before_release': pause(gap)
    value = real_release(self, sock)
    if gap == 'after_release': pause(gap)
    return value
holder_scope.HolderScope._release = release
real_launch = holder.Holder.launch
def launch(self):
    log('holders.jsonl', dict(unit=self.unit))
    return real_launch(self)
holder.Holder.launch = launch
real_leaf = holder.Holder.run_leaf
def leaf(self, request):
    log('dispatches.jsonl', dict(leaf=request.leaf_id))
    return real_leaf(self, request)
holder.Holder.run_leaf = leaf
real_checkpoint = confined_session.ConfinedChildSession._checkpoint
checkpoints = 0
def checkpoint(self, leaf):
    global checkpoints
    checkpoints += 1
    if gap == 'rerun_before_checkpoint' and checkpoints == 1: pause(gap)
    result = real_checkpoint(self, leaf)
    if gap == 'checkpoint_commit_gap' and checkpoints == 2: pause(gap)
    return result
confined_session.ConfinedChildSession._checkpoint = checkpoint
if gap == 'checkpoint_intent':
    patch = """
import os, time
real_write = checkpoint.durable_atomic_write
def checkpoint_write(path, data):
    real_write(path, data)
    row = json.loads(data)
    if row.get('state') == 'intent' and row.get('effect_identity') != 'none':
        from pathlib import Path
        # Only the second effect's intent: first checkpoint has already committed.
        control = Path(os.environ['T7_CONTROL'])
        count = len((control / 'dispatches.jsonl').read_text().splitlines())
        if count == 2:
            (control / 'marker.json').write_text(json.dumps(dict(gap='checkpoint_intent', pid=os.getpid())))
            while True: time.sleep(1)
checkpoint.durable_atomic_write = checkpoint_write
"""
    confined_session.HELPER = confined_session.HELPER.replace('operation, tmpfs, disk =', patch + '\noperation, tmpfs, disk =')
real_append = runtime.append_record
child_commits = 0
def append(path, row, **kwargs):
    global child_commits
    result = real_append(path, row, **kwargs)
    authority = kwargs.get('checked_authority')
    if authority is not None and authority.confined:
        if row['record'] == 'committed':
            child_commits += 1
            if gap == 'first_commit' and child_commits == 1: pause(gap)
        if row['record'] == 'terminal':
            if gap == 'child_terminal' or (gap == 'failed_terminal' and row['outcome'] == 'failed'): pause(gap)
    elif row['record'] == 'committed' and row.get('effect_class') == 'run_ref' and gap == 'parent_commit':
        pause(gap)
    return result
runtime.append_record = append
real_persist = lifecycle.persist_run_ref_lifecycle_event
def persist(request, event):
    ack = real_persist(request, event)
    if gap == 'failed_row' and event.event_kind == 'failed_terminal': pause(gap)
    if gap == 'pending' and event.stage == 'completed_pending_parent_commit': pause(gap)
    return ack
lifecycle.persist_run_ref_lifecycle_event = persist
real_finalize = run_ref.finalize_run_ref_parent_commit
def finalize(*args, **kwargs):
    if gap == 'before_settlement': pause(gap)
    return real_finalize(*args, **kwargs)
run_ref.finalize_run_ref_parent_commit = finalize
from orchestrator.cli.main import main
raise SystemExit(main(sys.argv[1:]))
'''


def _start(parent, control, args, gap):
    control.mkdir(exist_ok=True)
    runner = control / 'observer.py'
    runner.write_text(OBSERVER)
    number = len(list(control.glob('stdout-*.log')))
    out, err = control / f'stdout-{number}.log', control / f'stderr-{number}.log'
    with out.open('wb') as stdout, err.open('wb') as stderr:
        process = subprocess.Popen([sys.executable, str(runner), *args], cwd=parent,
            env={**os.environ, 'PYTHONPATH': str(REPOSITORY), 'T7_CONTROL': str(control), 'T7_GAP': gap},
            stdout=stdout, stderr=stderr, start_new_session=True)
    return process, out, err


def _wait(process, control, err):
    deadline = time.monotonic() + 180
    while not (control / 'marker.json').exists():
        if process.poll() is not None:
            pytest.fail(f'CLI exited {process.returncode} before boundary: {err.read_text()}')
        if time.monotonic() > deadline:
            pytest.fail(f'CLI did not reach boundary: {err.read_text()}')
        time.sleep(.02)


def _lines(path):
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


@pytest.mark.parametrize('gap', ['before_release', 'after_release', 'first_commit', 'checkpoint_intent',
    'checkpoint_commit_gap', 'rerun_before_checkpoint', 'child_terminal', 'failed_row', 'failed_terminal',
    'pending', 'parent_commit', 'before_settlement'])
def test_external_controller_kill_recovery(tmp_path, refs, gap):
    root, image = refs
    repository, commit = _candidate(tmp_path, STOP if gap in {'failed_row', 'failed_terminal'} else READ)
    parent = tmp_path / 'parent'
    parent.mkdir()
    (parent / 'controller.orc').write_text(PARENT.replace('REPO', repository.as_uri()).replace('IMAGE', image).replace('WALL', '300'))
    (parent / 'boundaries.json').write_text(json.dumps({
        'first': dict(stable_command=['python3', 'write.py'], closure=[]),
        'second': dict(stable_command=['python3', 'read.py'], closure=[])}))
    control = tmp_path / 'control'
    arguments = ['run', 'controller.orc', '--entry-workflow', 'controller::run', '--command-boundaries-file',
        'boundaries.json', '--run-ref-root', str(root), '--input', 'seed=1', '--input', f'revision={commit}']
    process, out, err = _start(parent, control, arguments, 'checkpoint_intent' if gap == 'rerun_before_checkpoint' else gap)
    run_root = None
    try:
        _wait(process, control, err)
        run_root, = (parent / '.orchestrate' / 'runs').iterdir()
        row = load_attempt_ledger(run_root / 'run-ref-attempts.jsonl').rows[-1]
        child_id, clone = row.bindings.child_run_id, row.bindings.workspace_path
        clone_identity = (clone.stat().st_dev, clone.stat().st_ino)
        os.kill(process.pid, signal.SIGKILL)  # only the controller: recovery owns exact scope teardown
        assert process.wait(timeout=30) == -signal.SIGKILL
        resume_args = ['resume', run_root.name, '--run-ref-root', str(root)]
        if gap == 'rerun_before_checkpoint':
            (control / 'marker.json').unlink()
            process, out2, err2 = _start(parent, control, resume_args, gap)
            _wait(process, control, err2)
            os.kill(process.pid, signal.SIGKILL)
            assert process.wait(timeout=30) == -signal.SIGKILL
        before_dispatch = len(_lines(control / 'dispatches.jsonl'))
        resumed, stdout, stderr = _start(parent, control, resume_args, '')
        process = resumed
        assert resumed.wait(timeout=300) == 0, stderr.read_text()
        authority, memo, site, workspace, child_root = _settled(parent)
        final_row = load_attempt_ledger(run_root / 'run-ref-attempts.jsonl').rows[-1]
        retained = gap not in {'before_release', 'after_release'}
        assert (final_row.attempt_ordinal == 1) is retained
        if retained:
            recipe = json.loads((child_root / 'child-recipe.json').read_bytes())
            original = recipe['owned_roots']['clone']
            assert (final_row.bindings.child_run_id, workspace, (original['device'], original['inode'])) == (
                child_id, clone, clone_identity)
        header, final_tree = _retained_checkpoint(workspace, child_root)
        assert header.manifest_digest == final_tree.digest
        assert not workspace.exists() and not (child_root / 'checkpoint.json').exists()
        expected = 'FAILED' if gap in {'failed_row', 'failed_terminal'} else 'COMPLETED'
        assert site['value']['variant'] == expected
        if gap in {'child_terminal', 'failed_row', 'failed_terminal', 'pending', 'parent_commit', 'before_settlement'}:
            assert len(_lines(control / 'dispatches.jsonl')) == before_dispatch
        assert _child_memo(child_root).terminal.data['outcome'] == ('failed' if expected == 'FAILED' else 'completed')
        # Reuse revalidates witnesses without another holder or dispatch.
        holders = _lines(control / 'holders.jsonl')
        final = _cli(parent, *resume_args)
        assert final.returncode == 0, final.stderr
        evidence = dict(gap=gap, run_id=run_root.name, image=image, commit=commit, basetemp=str(tmp_path),
            run_root=str(run_root), clone=str(workspace), clone_identity=clone_identity, child_run_id=child_id,
            final_child_run_id=final_row.bindings.child_run_id, dispatches=_lines(control / 'dispatches.jsonl'),
            holders=holders, stdout=str(stdout), stderr=str(stderr), result=site['value']['variant'])
        (control / 'evidence.json').write_text(json.dumps(evidence, indent=2))
        if os.environ.get('T7_EVIDENCE_DIR'):
            target = Path(os.environ['T7_EVIDENCE_DIR'])
            target.mkdir(parents=True, exist_ok=True)
            (target / f'{gap}.json').write_text(json.dumps(evidence, indent=2))
    finally:
        if process.poll() is None:
            os.kill(process.pid, signal.SIGKILL)
            process.wait(timeout=30)
        if run_root is not None:
            for child in (run_root / 'run-ref-children').glob('*'):
                recover_holder_scopes(child / 'holder')
