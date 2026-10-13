"""Prepared attempts retain outer authority while dispatch uses an item's cwd."""

import json
from contextlib import closing
from pathlib import Path

import pytest

from orchestrator.workflow.evaluated import runtime
from orchestrator.workflow.evaluated.closure import resolve_command_evidence, ClosureEvidenceError
from orchestrator.workflow.evaluated.closure_evidence import command_evidence_key
from orchestrator.workflow.evaluated.machine import site_classes, site_nodes
from orchestrator.workflow.evaluated.memo import read_memo
from orchestrator.workflow.evaluated.values import coerce_evaluated_value
from orchestrator.workflow.workspace_files import WorkspaceFiles
from orchestrator.workflow_lisp.command_boundaries import ExternalToolBinding
from tests.test_workflow_evaluated_command_lifecycle import _publish
from tests.workflow_lisp_closed_program_helpers import build


STRING = {'kind': 'primitive', 'name': 'String'}
SCRIPT = '''import os, json, sys
from pathlib import Path
Path(os.environ['ORCHESTRATOR_OUTPUT_BUNDLE_PATH']).write_text(json.dumps({'seen': sys.argv[1], 'place': Path.cwd().name, 'root': os.environ.get('ORCHESTRATOR_WORKSPACE_ROOT', '')}))
'''


def command_program(root, *, command=('python', 'probe.py', 'data.txt'), closure=()):
    source = '''(workflow-lisp (:language "0.1") (:target-dsl "2.37")
        (defmodule cwd) (export run)
        (defrecord Seen (seen String) (place String) (root String))
        (defworkflow run () -> Seen (command-result fetch :argv (%s) :returns Seen)))'''
    binding = ExternalToolBinding(name='fetch', stable_command=command, closure=closure)
    return build(root, source % ' '.join(json.dumps(x) for x in command), boundaries={'fetch': binding})


def prepared(authority, root, files, item='item'):
    identity, node = next(iter(site_nodes(authority.program).items()))
    return runtime.prepare_effect(authority, node, (), identity,
        owner=authority.program.tree['entry'], workspace=root, run_files=authority.run_files,
        workspace_files=files, site_classes=site_classes(authority.program), reader=None,
        provider_executor=None, launch_workspace=coerce_evaluated_value(item, STRING))


def test_prepare_perform_finish_keep_tokens_and_delay_commit_until_finish(tmp_path):
    item = tmp_path / 'item'
    item.mkdir()
    (tmp_path / 'probe.py').write_text('raise SystemExit(55)\n')
    (item / 'probe.py').write_text(SCRIPT)
    (tmp_path / 'data.txt').write_text('outer')
    (item / 'data.txt').write_text('item')
    with _publish(tmp_path, command_program(tmp_path)) as authority, closing(WorkspaceFiles(tmp_path)) as files:
        attempt = prepared(authority, tmp_path, files)
        initial = read_memo(authority.memo_path, site_classes(authority.program))
        assert len(initial.pending_starts) == 1 and not initial.active_commits
        outcome = runtime.perform_external(attempt)
        dispatched = read_memo(authority.memo_path, site_classes(authority.program))
        assert not dispatched.active_commits
        result = runtime.finish_effect(attempt, outcome)
        assert result.json_value() == {'seen': 'data.txt', 'place': 'item', 'root': str(tmp_path)}
        final = read_memo(authority.memo_path, site_classes(authority.program))
        row = next(iter(final.active_commits.values())).data
        assert row['input_parts']['launch_cwd']
        assert command_evidence_key('workspace', 'item/probe.py', 1) in row['implementation_files']
        assert command_evidence_key('workspace', 'item/data.txt', 2) in row['implementation_files']
        assert attempt.attempt_files.closed


def test_selected_item_token_prior_disappearance_is_required(tmp_path):
    item = tmp_path / 'item'
    item.mkdir()
    (item / 'data.txt').write_text('item')
    command = ('python', 'data.txt')
    evidence = resolve_command_evidence(command, (), workspace_root=tmp_path, launch_cwd=item)
    assert list(evidence) == [command_evidence_key('workspace', 'item/data.txt', 1)]
    (item / 'data.txt').unlink()
    with pytest.raises(ClosureEvidenceError):
        resolve_command_evidence(command, (), workspace_root=tmp_path, launch_cwd=item, prior=evidence)


def test_outside_item_uses_absolute_position_key_but_declared_closure_stays_outer(tmp_path):
    outer, item = tmp_path / 'outer', tmp_path / 'other'
    outer.mkdir(); item.mkdir()
    (outer / 'declared.txt').write_text('outer')
    (item / 'data.txt').write_text('item')
    closure = ({'base': 'workspace', 'path': 'declared.txt'},)
    evidence = resolve_command_evidence(('python', 'data.txt'), closure,
        workspace_root=outer, launch_cwd=item)
    positional = command_evidence_key('absolute', str(item / 'data.txt'), 1)
    assert set(evidence) == {positional, command_evidence_key('workspace', 'declared.txt')}
    assert resolve_command_evidence(('python', 'data.txt'), closure,
        workspace_root=outer, launch_cwd=item, prior=evidence) == evidence
    with pytest.raises(ValueError, match='prior token'):
        resolve_command_evidence(('python', 'data.txt'), closure, workspace_root=outer, prior=evidence)


def test_item_token_symlink_dotdot_lookup_preserves_kernel_component_order(tmp_path):
    item, elsewhere = tmp_path / 'item', tmp_path / 'elsewhere'
    item.mkdir(); elsewhere.mkdir()
    (elsewhere / 'nested').mkdir()
    (item / 'alias').symlink_to(elsewhere / 'nested', target_is_directory=True)
    (elsewhere / 'data.txt').write_text('actual')
    (item / 'data.txt').write_text('wrong')
    evidence = resolve_command_evidence(('python', 'alias/../data.txt'), (),
        workspace_root=tmp_path, launch_cwd=item)
    row = evidence[command_evidence_key('workspace', 'item/alias/../data.txt', 1)]
    assert row['target'] == 'elsewhere/data.txt'


@pytest.mark.parametrize('mutation', ['bound-file', 'new-homonym'])
def test_finish_detects_item_local_c4_change_before_commit(tmp_path, mutation):
    item = tmp_path / 'item'
    item.mkdir()
    (tmp_path / 'probe.py').write_text('# outer\n')
    (item / 'probe.py').write_text(SCRIPT)
    if mutation == 'bound-file':
        (item / 'data.txt').write_text('before')
    with _publish(tmp_path, command_program(tmp_path)) as authority, closing(WorkspaceFiles(tmp_path)) as files:
        attempt = prepared(authority, tmp_path, files)
        outcome = runtime.perform_external(attempt)
        (item / 'data.txt').write_text('after')
        with pytest.raises(runtime.CommandPerformerError, match='command closure changed'):
            runtime.finish_effect(attempt, outcome)
        snapshot = read_memo(authority.memo_path, site_classes(authority.program))
        assert not snapshot.active_commits and not snapshot.pending_starts
        assert snapshot.entries[-1].data['code'] == 'command_closure_written'
        assert attempt.attempt_files.closed


def test_authored_absolute_outer_script_and_explicit_closure_keep_outer_root(tmp_path):
    item = tmp_path / 'item'
    item.mkdir()
    outer_script = tmp_path / 'probe.py'
    outer_script.write_text(SCRIPT)
    (item / 'probe.py').write_text('raise SystemExit(55)')
    (tmp_path / 'declared.txt').write_text('outer')
    (item / 'declared.txt').write_text('item')
    command = ('python', str(outer_script), 'data.txt')
    with _publish(tmp_path, command_program(tmp_path, command=command, closure=('declared.txt',))) as authority, closing(WorkspaceFiles(tmp_path)) as files:
        attempt = prepared(authority, tmp_path, files)
        assert attempt.resolved[0][1] == str(outer_script)
        result = runtime.finish_effect(attempt, runtime.perform_external(attempt))
        assert result.json_value()['place'] == 'item'
        evidence = next(iter(read_memo(authority.memo_path, site_classes(authority.program)).active_commits.values())).data['implementation_files']
        assert command_evidence_key('workspace', 'declared.txt') in evidence
        assert command_evidence_key('workspace', 'item/declared.txt') not in evidence


def test_item_local_destination_overlap_refuses_before_start(tmp_path):
    (tmp_path / 'probe.py').write_text('# outer\n')
    program = command_program(tmp_path, command=('python', 'probe.py', '.'))
    with _publish(tmp_path, program) as authority, closing(WorkspaceFiles(tmp_path)) as files:
        (authority.run_root / 'probe.py').write_text(SCRIPT)
        with pytest.raises(ClosureEvidenceError, match='destination overlaps'):
            prepared(authority, tmp_path, files, str(authority.run_root))
        assert not read_memo(authority.memo_path, site_classes(program)).entries


@pytest.mark.parametrize('phase', ['retry', 'committed'])
def test_retry_and_committed_reuse_bind_resolved_alias_before_dispatch(tmp_path, phase):
    from orchestrator.workflow.evaluated import effect_inputs
    for name in ('first', 'second'):
        directory = tmp_path / name
        directory.mkdir()
        (directory / 'probe.py').write_text(SCRIPT)
    alias = tmp_path / 'item'
    alias.symlink_to(tmp_path / 'first', target_is_directory=True)
    (tmp_path / 'probe.py').write_text('# outer\n')
    with _publish(tmp_path, command_program(tmp_path)) as authority, closing(WorkspaceFiles(tmp_path)) as files:
        attempt = prepared(authority, tmp_path, files)
        if phase == 'committed':
            runtime.finish_effect(attempt, runtime.perform_external(attempt))
        else:
            with pytest.raises(runtime.CommandPerformerError):
                runtime.finish_effect(attempt, error=runtime.CommandPerformerError('command_exit_nonzero', 'failed'))
        original = authority.memo_path.read_bytes()
        alias.unlink(); alias.symlink_to(tmp_path / 'second', target_is_directory=True)
        with pytest.raises(effect_inputs._EffectInputDiverged, match='launch_cwd'):
            prepared(authority, tmp_path, files)
        assert authority.memo_path.read_bytes() == original


def test_prepare_zero_operand_effect_binds_workspace_dependencies_through_call(tmp_path):
    from orchestrator.workflow.evaluated.replay import discover_prefix
    from tests.workflow_evaluated_parallel_helpers import replay_case
    (tmp_path / 'seed.py').write_text("import os\nfrom pathlib import Path\nPath(os.environ['ORCHESTRATOR_OUTPUT_BUNDLE_PATH']).write_text('\"item\"')\n")
    (tmp_path / 'item').mkdir()
    (tmp_path / 'item' / 'probe.py').write_text("import os\nfrom pathlib import Path\nPath(os.environ['ORCHESTRATOR_OUTPUT_BUNDLE_PATH']).write_text('7')\n")
    seed = '(command-result fetch :argv ("python" "seed.py") :returns String)'
    leaf = '(defworkflow leaf () -> Int (command-result inc :argv ("python" "probe.py") :returns Int))'
    body = f'(let* ((root {seed})) (list/map-effect ((repo (list "a"))) :max 1 :parallel 1 :workspace root (call leaf)))'
    bindings = {'fetch': ExternalToolBinding(name='fetch', stable_command=('python', 'seed.py'), closure=('seed.py',)),
        'inc': ExternalToolBinding(name='inc', stable_command=('python', 'probe.py'), closure=())}
    with replay_case(tmp_path, body, declarations=leaf, boundaries=bindings) as authority, closing(WorkspaceFiles(tmp_path)) as files:
        identity, node = next(iter(site_nodes(authority.program).items()))
        runtime._execute_effect(authority, node, (), identity, owner=authority.program.tree['entry'],
            workspace=tmp_path, run_files=authority.run_files, workspace_files=files,
            site_classes=site_classes(authority.program), reader=None, provider_executor=None)
        prefix = discover_prefix(authority, read_memo(authority.memo_path, site_classes(authority.program)))
        reached = prefix.frontiers[0]
        assert reached.operands == () and reached.launch_workspace.dependencies == {identity}
        attempt = runtime.prepare_effect(authority, reached.node, reached.operands, reached.identity,
            owner=reached.owner, workspace=tmp_path, run_files=authority.run_files,
            workspace_files=files, site_classes=site_classes(authority.program), reader=None,
            provider_executor=None, launch_workspace=reached.launch_workspace)
        runtime.finish_effect(attempt, runtime.perform_external(attempt))
        snapshot = read_memo(authority.memo_path, site_classes(authority.program))
        assert snapshot.active_commits[reached.identity].data['depends_on'] == [identity]
        assert discover_prefix(authority, snapshot).value == [7]


def test_relocated_workspace_reuses_contained_item_locator_and_implementation(tmp_path):
    from orchestrator.workflow.evaluated.authority import load_run_authority
    original = tmp_path / 'original'
    original.mkdir()
    (original / 'probe.py').write_text('# outer')
    (original / 'item').mkdir()
    (original / 'item' / 'probe.py').write_text(SCRIPT)
    with _publish(original, command_program(original)) as authority, closing(WorkspaceFiles(original)) as files:
        attempt = prepared(authority, original, files)
        runtime.finish_effect(attempt, runtime.perform_external(attempt))
        memo_bytes = authority.memo_path.read_bytes()
    relocated = tmp_path / 'relocated'
    original.rename(relocated)
    authority = load_run_authority(relocated / '.state/runs/run-1')
    with closing(WorkspaceFiles(relocated)) as files:
        value = prepared(authority, relocated, files)
        assert value.json_value()['place'] == 'item'
        assert authority.memo_path.read_bytes() == memo_bytes
