from __future__ import annotations

import json
import os
import subprocess
import sys

import pytest
from pathlib import Path

from orchestrator.cli.commands.resume import resume_workflow
from tests.test_workflow_evaluated_cli import _build, _run_cli
from orchestrator.workflow.evaluated.memo import read_memo


def _snapshot(root: Path) -> dict[str, bytes | None]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes() if path.is_file() else None
        for path in root.rglob('*')
        if path.relative_to(root).as_posix() not in {'workspace.lock', 'workspace.guard'}
        and not (len(path.relative_to(root).parts) == 3
                 and path.relative_to(root).parts[0] == 'runs'
                 and path.relative_to(root).parts[-1] == 'run.lock')
    }


def _completed(root: Path) -> tuple[Path, Path]:
    source, _ = _build(root)
    result = _run_cli(root, str(source), '--input', 'score=0.75')
    assert result.returncode == 0, result.stderr
    (run_root,) = (root / '.orchestrate' / 'runs').iterdir()
    assert (run_root / 'run.json').is_file()
    terminal = read_memo(run_root / 'memo.jsonl', {}).terminal
    assert terminal is not None and terminal.data['outcome'] == 'completed'
    assert not (run_root / 'state.json').exists()
    return source, run_root


def test_public_completed_resume_uses_authority_without_state_view(tmp_path, monkeypatch):
    _, run_root = _completed(tmp_path)
    monkeypatch.chdir(tmp_path)
    before = _snapshot(tmp_path / '.orchestrate')
    for _ in range(2):
        assert resume_workflow(run_root.name) == 0
        assert _snapshot(tmp_path / '.orchestrate') == before


def _resume_cli(root: Path, run_id: str):
    return subprocess.run(
        [sys.executable, '-m', 'orchestrator', 'resume', run_id], cwd=root,
        env={**os.environ, 'PYTHONPATH': str(Path(__file__).parents[1]),
             'PYTHONDONTWRITEBYTECODE': '1'}, capture_output=True, text=True,
    )


def test_completed_resume_cli_keeps_stale_view_and_torn_tail(tmp_path):
    _, run_root = _completed(tmp_path)
    (run_root / 'state.json').write_text('{"schema_version":"2.1","status":"failed"}')
    with (run_root / 'memo.jsonl').open('ab') as stream:
        stream.write(b'{"partial":')
    before = _snapshot(tmp_path / '.orchestrate')
    for _ in range(2):
        result = _resume_cli(tmp_path, run_root.name)
        assert result.returncode == 0, result.stderr
        assert _snapshot(tmp_path / '.orchestrate') == before


@pytest.mark.parametrize('change,code', [
    ('program', 'resume_program_changed'), ('inputs', 'resume_inputs_changed'),
    ('missing-request', 'resume_request_missing'), ('malformed-request', 'memo_inconsistent'),
    ('schema', 'memo_inconsistent'), ('profile', 'memo_inconsistent'),
    ('missing-header', 'memo_inconsistent'), ('artifact', 'memo_inconsistent'),
])
def test_preflight_refusals_preserve_all_evidence(tmp_path, monkeypatch, caplog, change, code):
    source, run_root = _completed(tmp_path)
    header_path = run_root / 'run.json'
    header = json.loads(header_path.read_text())
    if change == 'program':
        source.write_text(source.read_text().replace('(> score threshold)', '(< score threshold)'))
        (run_root / 'closed_program.json').write_text('corrupt')
    elif change == 'inputs':
        header['resume_request']['input_overrides']['score'] = '0.9'
    elif change == 'missing-request':
        header.pop('resume_request', None)
    elif change in ('malformed-request', 'schema', 'profile'):
        field, value = {'malformed-request': ('resume_request', None),
                        'schema': ('schema_version', 'unknown'),
                        'profile': ('result_persistence_profile', 'unknown')}[change]
        header[field] = value
    elif change == 'artifact':
        (run_root / 'closed_program.json').write_text('corrupt')
    if change == 'missing-header':
        header_path.unlink()
    else:
        header_path.write_text(json.dumps(header))
    monkeypatch.chdir(tmp_path)
    def forbidden(*args, **kwargs):
        pytest.fail('memo was read before preflight finished')
    monkeypatch.setattr('orchestrator.workflow.evaluated.runtime.read_memo', forbidden)
    if change in ('program', 'inputs', 'missing-request'):
        monkeypatch.setattr('orchestrator.cli.commands.evaluated.load_run_authority', forbidden)
    before = _snapshot(tmp_path / '.orchestrate')
    assert resume_workflow(run_root.name, repair=True) == 2
    assert code in caplog.text
    assert _snapshot(tmp_path / '.orchestrate') == before


def _configured_completed(tmp_path, monkeypatch):
    from orchestrator.cli.commands.run import run_workflow
    from orchestrator.cli.commands.prompt_run_service import run_namespace
    source, _ = _build(tmp_path)
    for name in ('providers', 'prompts', 'commands', 'imports'):
        (tmp_path / (name + '.json')).write_text('{}')
    (tmp_path / 'producer.orc').write_text('(workflow-lisp (:language "0.1") (:target-dsl "2.35") (defmodule producer) (export run) (defworkflow run () -> String "unused"))')
    (tmp_path / 'imports.json').write_text(json.dumps({'unused': {'kind': 'compiled', 'path': 'producer.orc'}}))
    library = tmp_path / 'lib' / 'helpers'
    library.mkdir(parents=True)
    (library / 'math.orc').write_text('(workflow-lisp (:language "0.1") (:target-dsl "2.35") (defmodule lib/helpers/math) (export noop) (defproc noop () -> Int :effects () :lowering inline 1))')
    source.write_text(source.read_text().replace('(export run)', '(import lib/helpers/math :only (noop)) (export run)'))
    file = tmp_path / 'inputs.json'
    file.write_text('{"score": 0.1, "threshold": 0.25}')
    args = run_namespace(workflow=str(source), provider_externs_file='providers.json',
                         prompt_externs_file='prompts.json', state_dir=None)
    args.source_root = ['lib', '.', 'evaluated', '.']
    args.entry_workflow = None
    args.imported_workflow_bundles_file = 'imports.json'
    args.command_boundaries_file = 'commands.json'
    args.input_file = 'inputs.json'
    args.input = ['score=0.2', 'score=0.75']
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, 'argv', ['irrelevant', '--input', 'score=bad'])
    result = run_workflow(args)
    assert result.exit_code == 0
    return source, result, file


def test_namespace_recipe_preserves_effective_request_and_file_binding(tmp_path, monkeypatch):
    _, result, file = _configured_completed(tmp_path, monkeypatch)
    header = json.loads((result.run_root / 'run.json').read_text())
    assert header['workflow_file'] == 'evaluated/inputs.orc'
    assert header['resume_request'] == {
        'source_roots': ['lib', '.', 'evaluated', '.'], 'entry_workflow': None,
        'provider_externs_path': 'providers.json', 'prompt_externs_path': 'prompts.json',
        'imported_workflow_bundles_path': 'imports.json', 'command_boundaries_path': 'commands.json',
        'input_file': 'inputs.json', 'input_overrides': {'score': '0.75'},
    }
    assert header['bound_inputs'] == {'score': 0.75, 'threshold': 0.25}
    before = _snapshot(tmp_path / '.orchestrate')
    file.write_text('{"threshold":0.25,"score":0.9}')
    for _ in range(2):
        assert resume_workflow(result.run_id) == 0
        assert _snapshot(tmp_path / '.orchestrate') == before
    file.write_text('{"score":0.9,"threshold":0.5}')
    assert resume_workflow(result.run_id) == 2
    assert _snapshot(tmp_path / '.orchestrate') == before
    file.unlink()
    assert resume_workflow(result.run_id) == 2
    assert _snapshot(tmp_path / '.orchestrate') == before


def test_stored_authority_without_recipe_remains_readable(tmp_path, monkeypatch):
    from orchestrator.workflow.evaluated.authority import load_run_authority
    _, run_root = _completed(tmp_path)
    header_path = run_root / 'run.json'
    header = json.loads(header_path.read_text())
    header.pop('resume_request', None)
    header_path.write_text(json.dumps(header))
    assert load_run_authority(run_root).header == header
    monkeypatch.chdir(tmp_path)
    assert resume_workflow(run_root.name) == 2


def test_fresh_preparation_uses_stored_instance_and_rebound_carrier(tmp_path, monkeypatch):
    import orchestrator.cli.commands.evaluated as module
    _, run_root = _completed(tmp_path)
    monkeypatch.chdir(tmp_path)
    seen = []
    bindings = []
    from orchestrator.workflow_lisp.closed.frontend import ProviderIOContext
    original_bind = ProviderIOContext.bind
    def bind(carrier, program):
        bindings.append(program)
        return original_bind(carrier, program)
    monkeypatch.setattr(ProviderIOContext, 'bind', bind)
    original_load = module.load_run_authority if hasattr(module, 'load_run_authority') else None
    def load(root, **kwargs):
        authority = original_load(root, **kwargs)
        seen.append(authority.program)
        return authority
    def execute(authority, inputs, **kwargs):
        assert authority.program is seen[0]
        assert kwargs['provider_io'].program_digest == authority.program.digest
        assert bindings[-1] is authority.program
        assert bindings[0] is not authority.program
        return 0, None
    monkeypatch.setattr(module, 'load_run_authority', load, raising=False)
    monkeypatch.setattr(module, 'execute_pure_run', execute)
    def forbidden(*args, **kwargs):
        pytest.fail('resume attempted cache publication')
    monkeypatch.setattr('orchestrator.workflow_lisp.closed.artifact.atomic_write_text', forbidden)
    assert resume_workflow(run_root.name) == 0
    assert len(seen) == 1


@pytest.mark.parametrize('target,mode', [(t, m) for t in ('source', 'providers', 'prompts', 'commands', 'imports', 'producer') for m in ('invalid', 'missing', 'cycle')] + [('root', 'cycle')])
def test_fresh_files_missing_or_invalid_refuse_without_publication(tmp_path, monkeypatch, target, mode):
    source, result, _ = _configured_completed(tmp_path, monkeypatch)
    path = tmp_path / 'lib' if target == 'root' else source if target == 'source' else tmp_path / (target + ('.orc' if target == 'producer' else '.json'))
    if target == 'root':
        path.rename(tmp_path / 'saved-root')
    else:
        path.unlink()
    if mode == 'invalid':
        path.write_text('invalid')
    elif mode == 'cycle':
        peer = path.with_name(path.name + '.loop')
        path.symlink_to(peer.name)
        peer.symlink_to(path.name)
    before = _snapshot(tmp_path / '.orchestrate')
    cli = _resume_cli(tmp_path, result.run_id)
    assert cli.returncode == 2 and 'Traceback' not in cli.stderr, cli.stderr
    assert resume_workflow(result.run_id) == 2
    assert _snapshot(tmp_path / '.orchestrate') == before


@pytest.mark.parametrize('name,payload', [
    ('providers', {'unused': 'codex'}),
    ('prompts', {'unused': {'asset_file': 'unused.txt'}}),
    ('commands', {'unused': {'stable_command': ['python', 'unused.py'], 'closure': ['unused.py']}}),
])
def test_unused_manifest_binding_changes_are_semantic(tmp_path, monkeypatch, caplog, name, payload):
    _, result, _ = _configured_completed(tmp_path, monkeypatch)
    before = _snapshot(tmp_path / '.orchestrate')
    (tmp_path / (name + '.json')).write_text(json.dumps(payload))
    assert resume_workflow(result.run_id) == 2
    assert 'resume_program_changed' in caplog.text
    assert _snapshot(tmp_path / '.orchestrate') == before


def test_formatting_and_relative_workspace_relocation_preserve_identity(tmp_path, monkeypatch):
    import shutil
    original = tmp_path / 'original'
    original.mkdir()
    source, result, _ = _configured_completed(original, monkeypatch)
    source.write_text('; formatting only\n' + source.read_text())
    for name in ('providers', 'prompts', 'commands', 'imports'):
        path = original / (name + '.json')
        path.write_text(json.dumps(json.loads(path.read_text()), indent=3))
    assert resume_workflow(result.run_id) == 0
    moved = tmp_path / 'moved'
    shutil.move(original, moved)
    monkeypatch.chdir(moved)
    before = _snapshot(moved / '.orchestrate')
    assert resume_workflow(result.run_id) == 0
    assert _snapshot(moved / '.orchestrate') == before


def test_external_locator_retains_original_absolute_target(tmp_path, monkeypatch):
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    source, _ = _build(workspace)
    external = tmp_path / 'inputs.json'
    external.write_text('{"score": 0.75}')
    result = _run_cli(workspace, str(source), '--input-file', str(external))
    assert result.returncode == 0, result.stderr
    (run_root,) = (workspace / '.orchestrate' / 'runs').iterdir()
    header = json.loads((run_root / 'run.json').read_text())
    assert header['resume_request']['input_file'] == str(external)
    (workspace / 'inputs.json').write_text('{"score": 0.75}')
    external.unlink()
    monkeypatch.chdir(workspace)
    before = _snapshot(workspace / '.orchestrate')
    assert resume_workflow(run_root.name) == 2
    assert _snapshot(workspace / '.orchestrate') == before


def test_requested_input_file_is_required_when_fully_overridden(tmp_path, monkeypatch):
    source, _ = _build(tmp_path)
    path = tmp_path / 'inputs.json'
    path.write_text('{"score":0.1,"threshold":0.2}')
    result = _run_cli(tmp_path, str(source), '--input-file', 'inputs.json',
                      '--input', 'score=0.75', '--input', 'threshold=0.5')
    assert result.returncode == 0, result.stderr
    (run_root,) = (tmp_path / '.orchestrate' / 'runs').iterdir()
    monkeypatch.chdir(tmp_path)
    before = _snapshot(tmp_path / '.orchestrate')
    path.write_text('[')
    assert resume_workflow(run_root.name) == 2
    path.unlink()
    assert resume_workflow(run_root.name) == 2
    assert _snapshot(tmp_path / '.orchestrate') == before


@pytest.mark.parametrize('locator', ['', 'a/../b', '../a', './a', 'a//b', 'a/', '/tmp/../a',
                                      '/proc/self/fd/4/a', '/dev/fd/4/a', 'a\x00b'])
def test_malformed_recipe_locators_refuse_at_publication_before_root(tmp_path, locator):
    from orchestrator.workflow.evaluated.authority import publish_run_authority, RunAuthorityError
    _, program = _build(tmp_path)
    recipe = {'source_roots': [locator], 'entry_workflow': None,
              'provider_externs_path': None, 'prompt_externs_path': None,
              'command_boundaries_path': None, 'imported_workflow_bundles_path': None,
              'input_file': None, 'input_overrides': {}}
    root = tmp_path / 'absent-parent' / 'run'
    with pytest.raises(RunAuthorityError):
        with publish_run_authority(root, program, run_id='run', workflow_file='evaluated/inputs.orc',
                                   workflow_checksum='sha256:' + '0' * 64,
                                   bound_inputs={'score': 0.75, 'threshold': 0.5}, resume_request=recipe):
            pytest.fail('invalid recipe was published')
    assert not root.parent.exists()


@pytest.mark.parametrize('change', ['source-locator', 'unknown', 'missing', 'nonfinite', 'entry', 'roots', 'overrides'])
def test_present_malformed_recipe_is_not_a_historical_header(tmp_path, monkeypatch, change):
    from orchestrator.workflow.evaluated.authority import load_run_authority, RunAuthorityError
    _, run_root = _completed(tmp_path)
    path = run_root / 'run.json'
    header = json.loads(path.read_text())
    recipe = header['resume_request']
    replacements = {'entry': ('entry_workflow', ''), 'roots': ('source_roots', '.'),
                    'overrides': ('input_overrides', []), 'nonfinite': ('input_overrides', {'x': float('inf')})}
    if change == 'source-locator':
        header['workflow_file'] = '../inputs.orc'
    elif change == 'unknown':
        recipe['extra'] = None
    elif change == 'missing':
        del recipe['source_roots']
    else:
        field, value = replacements[change]
        recipe[field] = value
    path.write_text(json.dumps(header))
    with pytest.raises(RunAuthorityError):
        load_run_authority(run_root)
    with pytest.raises(RunAuthorityError):
        load_run_authority(run_root, header=header)
    monkeypatch.chdir(tmp_path)
    before = _snapshot(tmp_path / '.orchestrate')
    assert resume_workflow(run_root.name) == 2
    assert _snapshot(tmp_path / '.orchestrate') == before


def test_program_comparison_precedes_invalid_file_inputs_and_artifact(tmp_path, monkeypatch, caplog):
    source, result, file = _configured_completed(tmp_path, monkeypatch)
    source.write_text(source.read_text().replace('(threshold Float :default 0.5)', '(threshold Float :default 0.6)'))
    file.unlink()
    (result.run_root / 'closed_program.json').write_text('corrupt')
    (result.run_root / 'memo.jsonl').write_text('corrupt')
    def forbidden(*args, **kwargs):
        pytest.fail('artifact loaded before program comparison')
    monkeypatch.setattr('orchestrator.cli.commands.evaluated.load_run_authority', forbidden)
    before = _snapshot(tmp_path / '.orchestrate')
    assert resume_workflow(result.run_id) == 2
    assert 'resume_program_changed' in caplog.text
    assert _snapshot(tmp_path / '.orchestrate') == before


def test_c3_checks_all_emitted_interpreters_before_memo(tmp_path, monkeypatch, caplog):
    source = tmp_path / 'c3.orc'
    source.write_text('''(workflow-lisp (:language "0.1") (:target-dsl "2.35")
        (defmodule c3) (export run) (defworkflow run () -> Int
        (if false (command-result unused :argv ("resume-tool" "probe.py") :returns Int) 3)))''')
    tools = tmp_path / 'bin'
    tools.mkdir()
    interpreter = tools / 'resume-tool'
    interpreter.write_text('#!/bin/sh\nexit 0\n')
    interpreter.chmod(0o755)
    monkeypatch.setenv('PATH', str(tools) + os.pathsep + os.environ['PATH'])
    (tmp_path / 'commands.json').write_text(json.dumps({'unused': {
        'stable_command': ['resume-tool', 'probe.py'], 'closure': ['probe.py']}}))
    result = _run_cli(tmp_path, str(source), '--command-boundaries-file', 'commands.json')
    assert result.returncode == 0, result.stderr
    (run_root,) = (tmp_path / '.orchestrate' / 'runs').iterdir()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('PATH', '/missing-alternate-path')
    before = _snapshot(tmp_path / '.orchestrate')
    assert resume_workflow(run_root.name) == 0
    interpreter.write_text('#!/bin/sh\nexit 1\n')
    assert resume_workflow(run_root.name) == 0
    assert 'interpreter_changed' in caplog.text
    def forbidden(*args, **kwargs):
        pytest.fail('memo read before C3')
    monkeypatch.setattr('orchestrator.workflow.evaluated.runtime.read_memo', forbidden)
    interpreter.chmod(0o644)
    assert resume_workflow(run_root.name) == 2
    interpreter.unlink()
    assert resume_workflow(run_root.name) == 2
    assert 'resume_interpreter_missing' in caplog.text
    assert _snapshot(tmp_path / '.orchestrate') == before


def test_force_restart_evaluated_is_an_explicit_refusal(tmp_path, monkeypatch, caplog):
    _, run_root = _completed(tmp_path)
    monkeypatch.chdir(tmp_path)
    before = _snapshot(tmp_path / '.orchestrate')
    assert resume_workflow(run_root.name, force_restart=True) == 2
    assert 'evaluated_execution_unavailable' in caplog.text
    assert _snapshot(tmp_path / '.orchestrate') == before


@pytest.mark.parametrize('selector', [
    '{"schema_version":"3.0","schema_version":"2.1"}',
    '{"schema_version":"2.1","result_persistence_profile":null,"x":NaN}',
    '{"schema_version":"2.1","result_persistence_profile":null,"x":1e999}',
])
def test_malformed_selector_cannot_fall_back_to_legacy(tmp_path, monkeypatch, selector):
    _, run_root = _completed(tmp_path)
    (run_root / 'run.json').write_text(selector)
    monkeypatch.chdir(tmp_path)
    def forbidden(*args, **kwargs):
        pytest.fail('invalid selector reached legacy state')
    monkeypatch.setattr('orchestrator.cli.commands.resume.StateManager', forbidden)
    before = _snapshot(tmp_path / '.orchestrate')
    assert resume_workflow(run_root.name) == 2
    assert _snapshot(tmp_path / '.orchestrate') == before


def test_explicit_entry_and_prebinding_typed_override_are_preserved(tmp_path):
    from orchestrator.workflow.evaluated.authority import publish_run_authority
    source, program = _build(tmp_path)
    result = _run_cli(tmp_path, str(source), '--entry-workflow', 'evaluated/inputs::run', '--input', 'score=0.75')
    assert result.returncode == 0, result.stderr
    (run_root,) = (tmp_path / '.orchestrate' / 'runs').iterdir()
    recipe = json.loads((run_root / 'run.json').read_text())['resume_request']
    assert recipe['entry_workflow'] == 'evaluated/inputs::run'
    recipe['input_overrides'] = {'score': 0.75}
    with publish_run_authority(tmp_path / 'typed', program, run_id='typed', workflow_file='evaluated/inputs.orc',
                               workflow_checksum='sha256:' + '0' * 64,
                               bound_inputs={'score': 0.75, 'threshold': 0.5}, resume_request=recipe) as authority:
        assert authority.header['resume_request']['input_overrides'] == {'score': 0.75}
        assert 'threshold' not in authority.header['resume_request']['input_overrides']


def test_omitted_entry_is_not_recovered_from_historical_selected_entry(tmp_path, monkeypatch):
    source, run_root = _completed(tmp_path)
    text = source.read_text().replace('(export run)', '(export run alternate)')
    source.write_text(text.replace('(defrecord Result', '(defworkflow alternate () -> String "other") (defrecord Result'))
    monkeypatch.chdir(tmp_path)
    before = _snapshot(tmp_path / '.orchestrate')
    assert resume_workflow(run_root.name) == 2
    assert _snapshot(tmp_path / '.orchestrate') == before


def test_fresh_defaults_and_overrides_are_not_seeded_from_stored_bound_inputs(tmp_path, monkeypatch, caplog):
    from orchestrator.workflow.run_ref.contracts import canonical_sha256
    _, run_root = _completed(tmp_path)
    path = run_root / 'run.json'
    header = json.loads(path.read_text())
    header['bound_inputs']['threshold'] = 0.9
    header['input_digest'] = canonical_sha256(header['bound_inputs'])
    path.write_text(json.dumps(header))
    monkeypatch.chdir(tmp_path)
    before = _snapshot(tmp_path / '.orchestrate')
    assert resume_workflow(run_root.name) == 2
    assert 'resume_inputs_changed' in caplog.text
    assert _snapshot(tmp_path / '.orchestrate') == before


def test_input_file_locator_retains_resolved_target_of_initial_symlink(tmp_path, monkeypatch):
    source, _ = _build(tmp_path)
    target = tmp_path / 'initial.json'
    target.write_text('{"score":0.75}')
    alias = tmp_path / 'alias.json'
    alias.symlink_to(target.name)
    result = _run_cli(tmp_path, str(source), '--input-file', 'alias.json')
    assert result.returncode == 0, result.stderr
    (run_root,) = (tmp_path / '.orchestrate' / 'runs').iterdir()
    assert json.loads((run_root / 'run.json').read_text())['resume_request']['input_file'] == 'initial.json'
    other = tmp_path / 'other.json'
    other.write_text('{"score":0.9}')
    alias.unlink()
    alias.symlink_to(other.name)
    monkeypatch.chdir(tmp_path)
    before = _snapshot(tmp_path / '.orchestrate')
    assert resume_workflow(run_root.name) == 0
    assert _snapshot(tmp_path / '.orchestrate') == before


def test_explicit_invalid_run_ref_root_is_still_validated(tmp_path, monkeypatch):
    _, run_root = _completed(tmp_path)
    monkeypatch.chdir(tmp_path)
    before = _snapshot(tmp_path / '.orchestrate')
    assert resume_workflow(run_root.name, run_ref_root='relative') == 2
    assert _snapshot(tmp_path / '.orchestrate') == before


def test_nontransportable_override_refuses_before_creating_any_run_directory(tmp_path):
    from orchestrator.workflow.evaluated.authority import publish_run_authority, RunAuthorityError
    _, program = _build(tmp_path)
    recipe = {'source_roots': [], 'entry_workflow': None, 'provider_externs_path': None,
              'prompt_externs_path': None, 'command_boundaries_path': None,
              'imported_workflow_bundles_path': None, 'input_file': None,
              'input_overrides': {'unused': '\ud800'}}
    root = tmp_path / 'absent-parent' / 'run'
    with pytest.raises(RunAuthorityError):
        with publish_run_authority(root, program, run_id='run', workflow_file='evaluated/inputs.orc',
                                   workflow_checksum='sha256:' + '0' * 64,
                                   bound_inputs={'score': 0.75, 'threshold': 0.5}, resume_request=recipe):
            pytest.fail('invalid UTF-8 JSON was published')
    assert not root.parent.exists()
