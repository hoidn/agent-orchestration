"""Regression witnesses for confined authority, cumulative budgets and terminal facts."""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from orchestrator.workflow.run_ref import confined_budget, confined_lifecycle, confined_session, evaluated_child, image_store
from orchestrator.workflow.run_ref.contracts import canonical_json_bytes, canonical_sha256
from orchestrator.workflow.run_ref.runtime import RunRefRuntimeError
from tests import test_workflow_run_ref_confined_child as child
from tests.test_workflow_run_ref_confined_child import _removable_tmp, world  # noqa: F401


def _witness(world, memo):
    workspace, root = child._attempt(child._site(memo))
    authority = child.load_run_authority(root)
    return evaluated_child.validate_confined_child_terminal(
        child_root=root, clone_root=workspace, expected_header=authority.header,
        recipe_bytes=(root / 'child-recipe.json').read_bytes(),
        value_descriptor=authority.program.tree['result'], direct_value=8,
        image_digest=next(iter(authority.header['interpreters'].values()))['image'])


@pytest.mark.parametrize('part', ['argv', 'closure'])
def test_completed_witness_rejects_internally_consistent_forged_effect_inputs(world, part):
    _, (_, memo) = child._run(world)
    _, root = child._attempt(child._site(memo))
    rows = [json.loads(line) for line in (root / 'memo.jsonl').read_bytes().splitlines()]
    for row in rows:
        if row['record'] in ('started', 'committed'):
            row['input_parts'][part] = canonical_sha256(['forged'])
            row['input_digest'] = canonical_sha256(row['input_parts'])
    (root / 'memo.jsonl').write_bytes(b''.join(canonical_json_bytes(row) + b'\n' for row in rows))

    with pytest.raises(Exception, match='input.*diverged|input parts changed'):
        _witness(world, memo)


def test_completed_witness_uses_prior_snapshot_after_clone_script_changes(world, monkeypatch):
    child._defer_cleanup(monkeypatch)
    _, (_, memo) = child._run(world)
    workspace, _ = child._attempt(child._site(memo))
    (workspace / 'first.sh').write_text('changed after the committed effect\n')
    from orchestrator.workflow.evaluated import effect_inputs

    def mutable_clone_forbidden(*_args, **_kwargs):
        raise AssertionError('witness opened mutable clone files')

    monkeypatch.setattr(effect_inputs, 'WorkspaceFiles', mutable_clone_forbidden)
    assert _witness(world, memo)[0] == 8


@pytest.mark.parametrize('entry', ['child', 'run', 'resume'])
def test_empty_pins_confined_authority_never_uses_the_host_route(world, monkeypatch, entry):
    from orchestrator.workflow.evaluated import effect_execution, runtime

    monkeypatch.setattr(child, 'PARENT', child.PARENT.replace('("sh" "second.sh")', '("./second.sh" "second.sh")'))
    boundaries = json.loads((world['parent'] / 'boundaries.json').read_text())
    boundaries['second']['stable_command'] = ['./second.sh', 'second.sh']
    (world['parent'] / 'boundaries.json').write_text(json.dumps(boundaries))
    child._defer_cleanup(monkeypatch)
    _, (parent, memo) = child._run(world, first_exe='./first.sh')
    _, root = child._attempt(child._site(memo))
    authority = child.load_run_authority(root)
    assert authority.header['interpreters'] == {}
    (root / 'memo.jsonl').write_bytes(b'')
    host_calls = []
    monkeypatch.setattr(effect_execution, '_dispatch_command', lambda *_: host_calls.append(True))
    if entry == 'child':
        admission, provisioned = child._rebuilt_child(world, parent, child._site(memo))
        try:
            with pytest.raises(RunRefRuntimeError):
                evaluated_child.execute_confined_child(admission, provisioned, run_ref_root=world['refs'])
        finally:
            admission.close()
    else:
        execute = runtime.execute_pure_run if entry == 'run' else runtime.execute_pure_resume
        status, _ = execute(authority, authority.header['bound_inputs'], run_id=root.name,
                            workspace=child._attempt(child._site(memo))[0])
        assert status != 0
    assert host_calls == []


class Clock:
    now = 0.0

    def __call__(self):
        return self.now


def _session(world, monkeypatch):
    child._defer_cleanup(monkeypatch)
    _, (parent, memo) = child._run(world, first_exe='./tool.sh')
    admission, provisioned = child._rebuilt_child(world, parent, child._site(memo))
    clock = Clock()
    session = confined_session.ConfinedChildSession(admission, provisioned, clock=clock)
    session.budget = 1.0
    return session, admission, clock


def test_seed_is_not_started_when_holder_launch_exhausted_wall_budget(world, monkeypatch):
    session, admission, clock = _session(world, monkeypatch)
    calls = []
    launch = child.FakeHolder.launch

    def delayed_launch(holder):
        launch(holder)
        clock.now += 2

    monkeypatch.setattr(child.FakeHolder, 'launch', delayed_launch)
    monkeypatch.setattr(child.FakeHolder, 'run_host_helper', lambda *a, **kw: calls.append(kw['timeout_sec']))
    try:
        with pytest.raises(RunRefRuntimeError) as caught:
            session._ensure_started()
        assert (caught.value.code, calls, session.charged_seconds) == ('run_ref_budget_exhausted', [], 2.0)
    finally:
        session.stop()
        admission.close()


def test_host_helper_timeout_uses_current_remainder_without_double_charging(world, monkeypatch):
    session, admission, clock = _session(world, monkeypatch)
    calls = []
    launch = child.FakeHolder.launch

    def delayed_launch(holder):
        launch(holder)
        clock.now += .25

    def helper(holder, *a, **kw):
        calls.append(kw['timeout_sec'])
        clock.now += .125
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(child.FakeHolder, 'launch', delayed_launch)
    monkeypatch.setattr(child.FakeHolder, 'run_host_helper', helper)
    try:
        session._ensure_started()
        session._checkpoint('effect-attempt-1')
        assert calls == [.75, .625]
        assert (session.charged_seconds, session.remaining) == (.5, .5)
    finally:
        session.stop()
        admission.close()


@pytest.mark.parametrize('pure', [False, True])
def test_admission_rehash_is_charged_before_any_holder_or_leaf(world, monkeypatch, pure):
    if pure:
        monkeypatch.setattr(child, 'PARENT', child.PARENT.replace(
            '(command-result first :argv ("FIRST_EXE" "first.sh") :returns Int)', '3').replace(
            '(command-result second :argv ("sh" "second.sh") :returns Int)', '4'))
    clock = Clock()
    real_rehash = image_store.SealedImage.rehash

    def rehash(image):
        real_rehash(image)
        clock.now += 2

    monkeypatch.setattr(image_store.SealedImage, 'rehash', rehash)
    monkeypatch.setattr(confined_budget, 'boottime_ns', lambda: int(clock() * 1_000_000_000))
    session_init = confined_session.ConfinedChildSession.__init__

    def init(session, *args, **kwargs):
        session_init(session, *args, **kwargs, clock=clock)

    monkeypatch.setattr(confined_session.ConfinedChildSession, '__init__', init)
    status, (_, memo) = child._run(world, wall=1)
    assert (status, memo.terminal.data['outcome'], memo.terminal.data['code'],
            list(memo.active_commits), child.FakeHolder.launched, child.FakeHolder.leaves) == (
        1, 'failed', 'run_ref_budget_exhausted', [], [], [])


def test_checkpoint_failure_stops_scope_before_refreezing(world, monkeypatch):
    session, admission, _clock = _session(world, monkeypatch)
    events = []
    session.holder = SimpleNamespace(stop=lambda: events.append('stop'))
    monkeypatch.setattr(session, '_helper', lambda *_: ('run_ref_environment_escape_rejected', 'copy refused'))
    monkeypatch.setattr(confined_session, 'preflight_checkpoint', lambda *_: events.append('refreeze'))
    try:
        with pytest.raises(Exception) as caught:
            session._checkpoint('effect-attempt-1')
        assert caught.value.code == 'run_ref_environment_escape_rejected'
        assert events == ['stop', 'refreeze']
    finally:
        session.stop()
        admission.close()


def test_budget_exhausted_after_launch_settles_failed_without_seed(world, monkeypatch):
    clock = Clock()
    monkeypatch.setattr(confined_budget, 'boottime_ns', lambda: int(clock() * 1_000_000_000))
    session_init = confined_session.ConfinedChildSession.__init__
    launch = child.FakeHolder.launch
    helper_calls = []

    def init(session, *args, **kwargs):
        session_init(session, *args, **kwargs, clock=clock)

    def delayed_launch(holder):
        launch(holder)
        clock.now += 2

    monkeypatch.setattr(confined_session.ConfinedChildSession, '__init__', init)
    monkeypatch.setattr(child.FakeHolder, 'launch', delayed_launch)
    monkeypatch.setattr(child.FakeHolder, 'run_host_helper', lambda *a, **kw: helper_calls.append(kw))
    status, (_, memo) = child._run(world, wall=1)
    value = child._site(memo)['value']
    assert (status, value['variant'], value['code'], value['accounting']['elapsed_ms'],
            helper_calls, child.FakeHolder.leaves, child.FakeHolder.launched[0].stopped) == (
        0, 'FAILED', 'run_ref_budget_exhausted', 2000, [], [], True)


def test_baseline_copy_exhaustion_aborts_before_release(world, monkeypatch):
    clock = Clock()
    baseline = confined_lifecycle._snapshot_baseline
    monkeypatch.setattr(confined_budget, 'boottime_ns', lambda: int(clock() * 1_000_000_000))

    def copy(*args):
        manifest = baseline(*args)
        clock.now += 2
        return manifest

    monkeypatch.setattr(confined_lifecycle, '_snapshot_baseline', copy)
    status, (_, memo) = child._run(world, wall=1)
    assert (status, memo.terminal.data['code'], list(memo.active_commits), child.FakeHolder.launched) == (
        1, 'run_ref_budget_exhausted', [], [])


def test_legacy_host_authority_without_resume_request_stays_host(tmp_path):
    from tests.test_workflow_evaluated_authority import _float_input_program
    from orchestrator.workflow.evaluated.authority import publish_run_authority, load_run_authority
    from orchestrator.workflow.evaluated.runtime import execute_pure_run

    program = _float_input_program(tmp_path)
    root = tmp_path / 'runs' / 'legacy-host'
    with publish_run_authority(root, program, run_id=root.name, workflow_file='source.orc',
            workflow_checksum=program.digest, bound_inputs={'score': 1.0},
            resume_request={'source_roots': [], 'entry_workflow': None, 'provider_externs_path': None,
                'prompt_externs_path': None, 'imported_workflow_bundles_path': None,
                'command_boundaries_path': None, 'input_file': None, 'input_overrides': {}}):
        pass
    header = json.loads((root / 'run.json').read_bytes())
    del header['resume_request']
    (root / 'run.json').write_bytes(canonical_json_bytes(header))
    authority = load_run_authority(root)
    assert authority.confined is False
    assert execute_pure_run(authority, {'score': 1.0}, run_id=root.name, workspace=tmp_path) == (0, 1.0)


@pytest.mark.parametrize('directory', [False, True])
def test_typed_document_path_inputs_remain_witnessable_from_captured_snapshots(world, monkeypatch, directory):
    child._defer_cleanup(monkeypatch)
    from dataclasses import replace

    source = child.PARENT.replace('(export run)', '(export run) (defpath Asset :kind relpath :under "data" :must-exist true)')
    source = source.replace(':argv ("FIRST_EXE" "first.sh") :returns Int', ':argv ("FIRST_EXE" "first.sh") :returns Asset')
    source = source.replace(':argv ("sh" "second.sh") :returns Int', ':argv ("sh" "second.sh") :inputs ((source first)) :returns Int')
    source = source.replace('(+ (+ first second) seed)', '(+ second seed)')
    monkeypatch.setattr(child, 'PARENT', source)
    run_leaf = child.FakeHolder.run_leaf

    def leaf(holder, request):
        return run_leaf(holder, replace(request, argv=request.argv[:2]))

    monkeypatch.setattr(child.FakeHolder, 'run_leaf', leaf)
    path = 'data/empty' if directory else 'data/input.txt'
    setup = 'mkdir -p data/empty' if directory else 'mkdir data; echo payload > data/input.txt'
    first = setup + f"; echo '\"{path}\"' > \"$ORCHESTRATOR_OUTPUT_BUNDLE_PATH\""
    status, (_, memo) = child._run(world, first=first, second='echo 4 > "$ORCHESTRATOR_OUTPUT_BUNDLE_PATH"')
    assert (status, memo.terminal.data['value']) == (0, 'completed')
    workspace, root = child._attempt(child._site(memo))
    assert any(path in name for row in child._child_memo(root).active_commits.values()
               for name in row.data['input_parts'])
    if directory:
        (workspace / path).rmdir()
    else:
        (workspace / path).unlink()
    authority = child.load_run_authority(root)
    assert evaluated_child.validate_confined_child_terminal(
        child_root=root, clone_root=workspace, expected_header=authority.header,
        recipe_bytes=(root / 'child-recipe.json').read_bytes(), value_descriptor=authority.program.tree['result'],
        direct_value=5, image_digest=next(iter(authority.header['interpreters'].values()))['image'])[0] == 5


def test_pure_child_runtime_exhaustion_aborts_before_release(world, monkeypatch):
    from orchestrator.workflow.evaluated import runtime
    clock = Clock()
    monkeypatch.setattr(child, 'PARENT', child.PARENT.replace(
        '(command-result first :argv ("FIRST_EXE" "first.sh") :returns Int)', '3').replace(
        '(command-result second :argv ("sh" "second.sh") :returns Int)', '4'))
    monkeypatch.setattr(confined_budget, 'boottime_ns', lambda: int(clock() * 1_000_000_000))
    session_init = confined_session.ConfinedChildSession.__init__
    evaluate = runtime.evaluate_closed_program

    def init(session, *args, **kwargs):
        session_init(session, *args, **kwargs, clock=clock)

    def slow_pure(program, *args, **kwargs):
        value = evaluate(program, *args, **kwargs)
        if program.tree['entry'].endswith('::candidate-body'):
            clock.now += 2
        return value

    monkeypatch.setattr(confined_session.ConfinedChildSession, '__init__', init)
    monkeypatch.setattr(runtime, 'evaluate_closed_program', slow_pure)
    status, (_, memo) = child._run(world, wall=1)
    assert (status, memo.terminal.data['code'], list(memo.active_commits), child.FakeHolder.launched) == (
        1, 'run_ref_budget_exhausted', [], [])


def test_holder_stop_time_is_charged_before_child_completion(world, monkeypatch):
    clock = Clock()
    monkeypatch.setattr(confined_budget, 'boottime_ns', lambda: int(clock() * 1_000_000_000))
    session_init = confined_session.ConfinedChildSession.__init__
    stop = child.FakeHolder.stop

    def init(session, *args, **kwargs):
        session_init(session, *args, **kwargs, clock=clock)

    def slow_stop(holder):
        if not holder.stopped:
            clock.now += 2
        stop(holder)

    monkeypatch.setattr(confined_session.ConfinedChildSession, '__init__', init)
    monkeypatch.setattr(child.FakeHolder, 'stop', slow_stop)
    status, (_, memo) = child._run(world, wall=1)
    value = child._site(memo)['value']
    assert (status, value['variant'], value.get('code'), value['accounting']['elapsed_ms']) == (
        0, 'FAILED', 'run_ref_budget_exhausted', 2000)


@pytest.mark.parametrize('kind', ['directory', 'file', 'symlink', 'absent'])
def test_document_directory_marker_is_only_emitted_for_a_real_directory(tmp_path, kind):
    from orchestrator.workflow.evaluated import confined_dispatch as cd
    from orchestrator.workflow.workspace_files import WorkspaceFiles

    clone = tmp_path / 'clone'
    clone.mkdir()
    selected = clone / 'selected'
    if kind == 'directory':
        selected.mkdir()
    elif kind == 'file':
        selected.write_bytes(b'content')
    elif kind == 'symlink':
        selected.symlink_to('missing')
    files = WorkspaceFiles(clone)
    try:
        rows = [('document-0', 'selected')]
        binding = cd.bind_clone_inputs(rows, files, max_bytes=1024, directory_rows=rows)
        markers = {name: digest for name, digest in binding.parts.items() if name.startswith('clone-directory:')}
        assert bool(markers) is (kind == 'directory')
        if markers:
            assert list(markers.values()) == [canonical_sha256({'directory': True})]
    finally:
        files.close()


def test_many_empty_directories_hit_the_existing_snapshot_entry_cap(tmp_path, monkeypatch):
    from orchestrator.workflow.evaluated import confined_dispatch as cd
    from orchestrator.workflow.workspace_files import WorkspaceFiles

    clone = tmp_path / 'clone'
    clone.mkdir()
    for index in range(4):
        (clone / str(index)).mkdir()
    monkeypatch.setattr(cd, 'MAX_CHECKPOINT_ENTRIES', 3)
    files = WorkspaceFiles(clone)
    try:
        with pytest.raises(cd.ConfinedDispatchRefusal) as caught:
            cd.bind_clone_inputs([('document-0', '.')], files, max_bytes=1024,
                                 directory_rows=[('document-0', '.')])
        assert caught.value.code == 'run_ref_environment_escape_rejected'
    finally:
        files.close()


@pytest.mark.parametrize('damage', ['missing', 'tampered', 'forged-marker'])
def test_directory_snapshot_marker_must_be_exact_and_present(tmp_path, damage):
    from orchestrator.workflow.evaluated import confined_dispatch as cd
    from orchestrator.workflow.workspace_files import WorkspaceFiles

    store = WorkspaceFiles(tmp_path)
    marker = canonical_json_bytes({'directory': True})
    digest = canonical_sha256({'directory': True})
    if damage == 'forged-marker':
        marker = b'{"directory":false}'
        digest = canonical_sha256({'directory': False})
    if damage != 'missing':
        store.create(digest.removeprefix('sha256:'), marker if damage != 'tampered' else b'damaged')
    try:
        with pytest.raises(cd.ConfinedDispatchRefusal) as caught:
            cd.verify_attempt_snapshot(store, {'clone-directory:document-0:selected': digest})
        assert caught.value.code == 'run_ref_evidence_invalid'
    finally:
        store.close()


def test_snapshot_directory_existence_does_not_invent_descendants_or_cross_files(tmp_path):
    from orchestrator.workflow.evaluated.confined_dispatch import SnapshotPaths

    digest = canonical_sha256({'directory': True})
    files = SnapshotPaths(tmp_path, {'clone-directory:document-0:parent/empty': digest,
        'clone-file:1:regular': canonical_sha256('file'),
        'clone-file:2:regular/forged': canonical_sha256('forged')})
    assert files.exists('parent') and files.exists('parent/empty')
    assert not files.exists('parent/empty/absent')
    with pytest.raises(OSError):
        files.exists('regular/forged')


def test_checkpoint_refreeze_failure_preserves_the_original_code_and_repair_detail(world, monkeypatch):
    session, admission, _ = _session(world, monkeypatch)
    session.holder = SimpleNamespace(stop=lambda: None)
    monkeypatch.setattr(session, '_helper', lambda *_: ('run_ref_environment_escape_rejected', 'copy refused'))

    def refuse_repair(*_):
        raise OSError('repair unavailable')

    monkeypatch.setattr(confined_session, 'preflight_checkpoint', refuse_repair)
    try:
        with pytest.raises(Exception) as caught:
            session._checkpoint('effect-attempt-1')
        assert caught.value.code == 'run_ref_environment_escape_rejected'
        assert 'repair unavailable' in str(caught.value)
    finally:
        session.stop()
        admission.close()
