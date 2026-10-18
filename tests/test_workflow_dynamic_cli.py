"""Actual public dynamic compile/dry-run admission without effect dispatch."""
from argparse import Namespace
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from orchestrator.cli.main import create_parser
from orchestrator.cli.commands.compile import compile_workflow
from orchestrator.cli.commands.run import RunWorkflowResult, run_workflow
from tests.test_workflow_dynamic_source import write_source


def source(tmp_path, body='(defworkflow main () -> Int 1)'):
    return write_source(tmp_path, 'demo/main', '(export main) ' + body)


def args(path, *options, command='run'):
    return create_parser().parse_args([command, str(path), *options])


def forbid_retained(monkeypatch):
    from orchestrator.cli.commands import compile as compiler, run, evaluated
    def forbidden(*a, **kw):
        raise AssertionError('candidate entered retained frontend/runtime')
    monkeypatch.setattr(compiler, 'build_frontend_bundle', forbidden)
    monkeypatch.setattr(compiler, 'build_closed_program_bundle', forbidden)
    monkeypatch.setattr(run, 'StateManager', forbidden)
    monkeypatch.setattr(evaluated, 'run_evaluated_workflow', forbidden)


def test_public_compile_dispatch_export_and_diagnostics(tmp_path, monkeypatch, capsys):
    path = source(tmp_path)
    monkeypatch.chdir(tmp_path)
    forbid_retained(monkeypatch)
    assert compile_workflow(args(path, '--diagnostics-json', '--emit-source-map', command='compile')) == 0
    document = json.loads(capsys.readouterr().out)
    assert document['status'] == 'accepted'
    assert document['program_digest'].startswith('sha256:')
    artifact = next((tmp_path / '.orchestrate/build').glob('*/dynamic_program.json'))
    assert json.loads(artifact.read_text())['target'] == '3.0'
    exported = json.loads((tmp_path / 'source_map.json').read_text())
    assert exported == json.loads(artifact.read_text())['source_map']


@pytest.mark.parametrize('flag', ['--emit-executable-ir', '--emit-core-ast', '--emit-runtime-plan', '--emit-semantic-ir', '--emit-debug-yaml'])
def test_compile_unavailable_exports_refuse_before_writes(tmp_path, monkeypatch, flag):
    path = source(tmp_path)
    monkeypatch.chdir(tmp_path)
    assert compile_workflow(args(path, flag, command='compile')) == 2
    assert not (tmp_path / '.orchestrate').exists()


def test_dryrun_omitted_defaults_no_body_evaluation_or_allocation(tmp_path, monkeypatch):
    path = source(tmp_path, '(define (bad x) (+ x true)) (defworkflow main ((flag Bool :default false)) -> Int (bad flag))')
    monkeypatch.chdir(tmp_path)
    forbid_retained(monkeypatch)
    import orchestrator.workflow.dynamic.evaluator as evaluator
    monkeypatch.setattr(evaluator, 'evaluate', lambda *a, **kw: pytest.fail('dryrun evaluated body'))
    parsed = args(path, '--dry-run')
    assert parsed.max_retries == 1  # retained parser default
    assert 'max_retries' not in parsed._explicit_options
    result = run_workflow(parsed)
    assert result.exit_code == 0
    assert result.run_id is None and result.run_root is None
    assert not (tmp_path / '.orchestrate').exists()


@pytest.mark.parametrize('options', [
    ['--max-retries', '1'], ['--max-retries', '-1'], ['--on-error', 'continue'],
    ['--retry-delay', '1000'], ['--context', 'x=1'], ['--context-file', 'missing.json'],
    ['--run-ref-root', '/tmp'], ['--clean-processed'], ['--archive-processed', 'out'],
    ['--backup-state'], ['--step-summaries'], ['--summary-provider', 'claude_sonnet_summary'],
    ['--summary-timeout-sec', '120'], ['--summary-mode', 'async'], ['--summary-profile', 'basic'],
    ['--live-agent-notes'], ['--live-agent-note-interval-sec', '15'],
])
def test_explicit_legacy_options_refuse_before_build(tmp_path, monkeypatch, caplog, options):
    path = source(tmp_path)
    monkeypatch.chdir(tmp_path)
    assert run_workflow(args(path, '--dry-run', *options)).exit_code == 2
    assert 'dynamic_option_unsupported' in caplog.text
    assert not (tmp_path / '.orchestrate').exists()


def test_explicit_zero_retry_and_stop_supported(tmp_path, monkeypatch):
    path = source(tmp_path)
    monkeypatch.chdir(tmp_path)
    assert run_workflow(args(path, '--dry-run', '--max-retries', '0', '--on-error', 'stop')).exit_code == 0


def test_service_namespace_options_are_explicit_without_parser_marker(tmp_path, monkeypatch, caplog):
    path = source(tmp_path)
    monkeypatch.chdir(tmp_path)
    supplied = Namespace(workflow=str(path), dry_run=True)
    assert run_workflow(supplied).exit_code == 0
    supplied.retry_delay = 1000
    assert run_workflow(supplied).exit_code == 2
    assert 'dynamic_option_unsupported' in caplog.text


def test_json_types_preserved_and_only_cli_overrides_coerced(tmp_path, monkeypatch, caplog):
    path = source(tmp_path, '(defworkflow main ((flag Bool)) -> Bool flag)')
    monkeypatch.chdir(tmp_path)
    inputs = tmp_path / 'inputs.json'
    inputs.write_text('{"flag":"false"}')
    assert run_workflow(args(path, '--dry-run', '--input-file', str(inputs))).exit_code == 2
    assert 'dynamic_boundary_invalid' in caplog.text
    assert run_workflow(args(path, '--dry-run', '--input-file', str(inputs), '--input', 'flag=false')).exit_code == 0
    inputs.write_text('{"flag":false}')
    assert run_workflow(args(path, '--dry-run', '--input-file', str(inputs))).exit_code == 0
    assert not (tmp_path / '.orchestrate').exists()


@pytest.mark.parametrize('document', ['{"flag":false,"flag":true}', '{"flag":NaN}', '[]'])
def test_invalid_input_documents_refuse(tmp_path, monkeypatch, document):
    path = source(tmp_path, '(defworkflow main ((flag Bool)) -> Bool flag)')
    monkeypatch.chdir(tmp_path)
    inputs = tmp_path / 'inputs.json'
    inputs.write_text(document)
    assert run_workflow(args(path, '--dry-run', '--input-file', str(inputs))).exit_code == 2
    assert not (tmp_path / '.orchestrate').exists()


@pytest.mark.parametrize('options', [[], ['--input', 'extra=1'], ['--input', 'flag=oops'], ['--input', 'bad']])
def test_missing_extra_and_invalid_inputs_refuse(tmp_path, monkeypatch, options):
    path = source(tmp_path, '(defworkflow main ((flag Bool)) -> Bool flag)')
    monkeypatch.chdir(tmp_path)
    assert run_workflow(args(path, '--dry-run', *options)).exit_code == 2
    assert not (tmp_path / '.orchestrate').exists()


def test_dryrun_checks_unreachable_malformed_body(tmp_path, monkeypatch):
    path = source(tmp_path, '(define (unused) unknown) (defworkflow main () -> Int 1)')
    monkeypatch.chdir(tmp_path)
    assert run_workflow(args(path, '--dry-run')).exit_code == 2
    assert not (tmp_path / '.orchestrate').exists()


@pytest.mark.parametrize('body,options,value', [
    ('(defworkflow main ((n Int :default 0)) -> Int n)', [], 0),
    ('(defworkflow main ((flag Bool :default false)) -> Bool flag)', [], False),
    ('(defworkflow main ((value Value)) -> Value value)', ['--input', 'value=null'], None),
])
def test_real_fresh_run_native_results(tmp_path, monkeypatch, body, options, value):
    from orchestrator.workflow.dynamic.state import load_dynamic_view
    path = source(tmp_path, body)
    monkeypatch.chdir(tmp_path)
    forbid_retained(monkeypatch)
    if value is None:
        document = tmp_path / 'inputs.json'
        document.write_text('{"value":null}')
        options = ['--input-file', str(document)]
    result = run_workflow(args(path, *options))
    assert result.exit_code == 0
    assert result.workflow_outputs is value
    assert result.run_id and result.run_root
    path.unlink()
    view = load_dynamic_view(result.run_root)
    assert view['status'] == 'completed' and view['workflow_outputs'] is value
    assert not (result.run_root / 'memo.jsonl').exists()


def test_pure_failure_persists_strict_error_and_steps(tmp_path, monkeypatch):
    from orchestrator.workflow.dynamic.state import load_dynamic_view
    path = source(tmp_path, '(defworkflow main () -> Int (+ true 1))')
    monkeypatch.chdir(tmp_path)
    result = run_workflow(args(path))
    assert result.exit_code == 1 and result.run_root is not None
    path.unlink()
    view = load_dynamic_view(result.run_root)
    assert view['status'] == 'failed' and view['workflow_outputs'] is None
    assert view['steps_used'] > 0
    assert view['error']['code'] == 'dynamic_operand_type'
    assert view['error']['location'] in json.loads((result.run_root / 'closed_program.json').read_text())['source_map']['entries']


@pytest.mark.parametrize('kwargs', [{'run_id': 'reserved'}, {'logical_workflow_path': Path('logical.orc')},
    {'reserved_run_fd': 0}, {'expected_run_identity': (1, 2)}, {'profile_conf_fd': 0},
    {'no_tools_conf_root': 'x'}, {'no_tools_conf_identity': (1, 2)}, {'no_tools_conf_manifest_sha256': 'x'}])
def test_dynamic_child_runtime_arguments_refuse_without_writes(tmp_path, monkeypatch, kwargs):
    path = source(tmp_path)
    monkeypatch.chdir(tmp_path)
    assert run_workflow(args(path), **kwargs).exit_code == 2
    assert not (tmp_path / '.orchestrate').exists()


@pytest.mark.parametrize('value', [3, 0, False, None])
def test_public_result_carrier_preserves_native_scalars(value):
    assert RunWorkflowResult(exit_code=0, workflow_outputs=value).workflow_outputs is value


def test_real_subprocess_compile_and_dryrun(tmp_path):
    path = source(tmp_path, '(defworkflow main ((flag Bool :default false)) -> Bool flag)')
    env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1]), PYTHONDONTWRITEBYTECODE='1')
    compiled = subprocess.run([sys.executable, '-m', 'orchestrator', 'compile', str(path), '--diagnostics-json'], cwd=tmp_path, env=env, capture_output=True, text=True)
    assert compiled.returncode == 0, compiled.stderr
    assert json.loads(compiled.stdout)['status'] == 'accepted'
    dryrun = subprocess.run([sys.executable, '-m', 'orchestrator', 'run', str(path), '--dry-run', '--input', 'flag=false'], cwd=tmp_path, env=env, capture_output=True, text=True)
    assert dryrun.returncode == 0, dryrun.stderr
    assert not (tmp_path / '.orchestrate/runs').exists()


def test_parser_keeps_legacy_defaults_and_tracks_equal_and_abbreviated_flags(tmp_path):
    parsed = args(source(tmp_path), '--dry-run', '--retry-delay=1000', '--max-r', '0')
    assert parsed.retry_delay == 1000 and parsed.max_retries == 0
    assert {'dry_run', 'retry_delay', 'max_retries'} <= parsed._explicit_options
    omitted = args(tmp_path / 'legacy.orc')
    assert omitted.max_retries == 1 and omitted.retry_delay == 1000
    assert omitted._explicit_options == {'workflow'}


@pytest.mark.parametrize('value', ['notes/missing.txt', '../outside.txt'])
def test_initial_path_and_path_default_checks_before_allocation(tmp_path, monkeypatch, value):
    path = source(tmp_path, f'(defpath Note :kind relpath :under "notes" :must-exist true) (defworkflow main ((note Note :default "{value}")) -> Int 1)')
    monkeypatch.chdir(tmp_path)
    assert run_workflow(args(path, '--dry-run')).exit_code == 2
    assert not (tmp_path / '.orchestrate').exists()


def test_path_text_override_uses_pinned_workspace_owner(tmp_path, monkeypatch):
    path = source(tmp_path, '(defpath Note :kind relpath :under "notes" :must-exist true) (defworkflow main ((note Note)) -> Int 1)')
    (tmp_path / 'notes').mkdir()
    (tmp_path / 'notes/ok.txt').write_text('data')
    monkeypatch.chdir(tmp_path)
    assert run_workflow(args(path, '--dry-run', '--input', 'note=notes/ok.txt')).exit_code == 0
    assert not (tmp_path / '.orchestrate').exists()


@pytest.mark.parametrize('executable', ['missing-tool', './missing-tool', './nonexec'])
def test_static_command_launchability_in_unreachable_body_checked(tmp_path, monkeypatch, caplog, executable):
    path = source(tmp_path, f'(define (unused) (command-result tool :argv ("{executable}") :returns Int)) (defworkflow main () -> Int 1)')
    (tmp_path / 'nonexec').write_text('data')
    manifest = tmp_path / 'commands.json'
    manifest.write_text(json.dumps({'tool': {'kind': 'external_tool', 'stable_command': [executable], 'closure': []}}))
    monkeypatch.chdir(tmp_path)
    assert run_workflow(args(path, '--dry-run', '--command-boundaries-file', str(manifest))).exit_code == 2
    assert 'command_interpreter_missing' in caplog.text
    assert not (tmp_path / '.orchestrate').exists()


def test_unused_manifest_binding_is_not_new_launchability_requirement(tmp_path, monkeypatch):
    path = source(tmp_path)
    manifest = tmp_path / 'commands.json'
    manifest.write_text(json.dumps({'unused': {'kind': 'external_tool', 'stable_command': ['missing-tool'], 'closure': []}}))
    monkeypatch.chdir(tmp_path)
    assert run_workflow(args(path, '--dry-run', '--command-boundaries-file', str(manifest))).exit_code == 0


def test_command_preflight_observes_closure_but_never_dispatches(tmp_path, monkeypatch):
    path = source(tmp_path, '(define (unused) (command-result tool :argv ("python") :returns Int)) (defworkflow main () -> Int 1)')
    manifest = tmp_path / 'commands.json'
    manifest.write_text(json.dumps({'tool': {'kind': 'external_tool', 'stable_command': ['python'], 'closure': ['missing.txt']}}))
    monkeypatch.chdir(tmp_path)
    assert run_workflow(args(path, '--dry-run', '--command-boundaries-file', str(manifest))).exit_code == 2
    (tmp_path / 'missing.txt').write_text('data')
    assert run_workflow(args(path, '--dry-run', '--command-boundaries-file', str(manifest))).exit_code == 0
    assert not (tmp_path / '.orchestrate').exists()


def test_provider_registry_binding_and_interpreter_preflight_without_dispatch(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from orchestrator.cli.commands import dynamic
    path = source(tmp_path, '(defprompt review (:fills (value :value)) -> Int "{value}") (define (unused) (provider-result p :prompt (review :value 1))) (defworkflow main () -> Int 1)')
    providers = tmp_path / 'providers.json'
    providers.write_text('{"p":"local"}')
    observations = []
    class Registry:
        def get(self, name):
            observations.append(name)
            return SimpleNamespace(command=['python']) if name == 'local' else None
    monkeypatch.setattr(dynamic, 'ProviderRegistry', Registry)
    monkeypatch.chdir(tmp_path)
    assert run_workflow(args(path, '--dry-run', '--provider-externs-file', str(providers))).exit_code == 0
    assert observations == ['local']
    providers.write_text('{"p":"absent"}')
    assert run_workflow(args(path, '--dry-run', '--provider-externs-file', str(providers))).exit_code == 2
    assert not (tmp_path / '.orchestrate').exists()


def test_service_debug_yaml_and_compiled_imports_refuse_before_publication(tmp_path, monkeypatch):
    path = source(tmp_path)
    monkeypatch.chdir(tmp_path)
    assert run_workflow(Namespace(workflow=str(path), dry_run=True, emit_debug_yaml=True)).exit_code == 2
    bundles = tmp_path / 'bundles.json'
    bundles.write_text('{}')
    assert run_workflow(args(path, '--dry-run', '--imported-workflow-bundles-file', str(bundles))).exit_code == 2
    assert compile_workflow(args(path, '--imported-workflow-bundles-file', str(bundles), command='compile')) == 2
    assert not (tmp_path / '.orchestrate').exists()


def test_service_unknown_option_refuses_instead_of_silent_ignore(tmp_path, monkeypatch):
    path = source(tmp_path)
    monkeypatch.chdir(tmp_path)
    assert run_workflow(Namespace(workflow=str(path), dry_run=True, future_feature=True)).exit_code == 2
    assert not (tmp_path / '.orchestrate').exists()


def test_compile_service_namespace_and_source_map_custom_export(tmp_path, monkeypatch, capsys):
    path = source(tmp_path)
    monkeypatch.chdir(tmp_path)
    destination = tmp_path / 'exports/map.json'
    assert compile_workflow(Namespace(workflow=str(path), emit_source_map=[str(destination)])) == 0
    assert json.loads(capsys.readouterr().out)['entry_workflow'] == 'demo/main::main'
    assert json.loads(destination.read_text())['schema'] == 'workflow-lisp/dynamic-source-map/1'


def test_compile_multiple_source_map_exports_refuse_before_build(tmp_path, monkeypatch):
    path = source(tmp_path)
    monkeypatch.chdir(tmp_path)
    assert compile_workflow(args(path, '--emit-source-map', '--emit-source-map', command='compile')) == 2
    assert not (tmp_path / '.orchestrate').exists()


def test_compile_machine_rejection_has_real_source_span(tmp_path, monkeypatch, capsys):
    path = source(tmp_path, '(define (unused) unknown) (defworkflow main () -> Int 1)')
    monkeypatch.chdir(tmp_path)
    assert compile_workflow(args(path, '--diagnostics-json', command='compile')) == 2
    document = json.loads(capsys.readouterr().out)
    assert document['status'] == 'rejected'
    assert document['diagnostics']
    assert str(path) in json.dumps(document)
    assert not (tmp_path / '.orchestrate').exists()


@pytest.mark.parametrize('damage', ['duplicate-budget', 'unclosed-form', 'bad-language'])
def test_malformed_candidate_headers_never_fall_through(tmp_path, monkeypatch, damage):
    path = source(tmp_path)
    original = path.read_text()
    if damage == 'duplicate-budget':
        path.write_text(original.replace('(:budget 1000)', '(:budget 1000) (:budget 2)'))
    elif damage == 'unclosed-form':
        path.write_text(original[:-1])
    else:
        path.write_text(original.replace('(:language "0.1")', '(:language "9.9")'))
    monkeypatch.chdir(tmp_path)
    forbid_retained(monkeypatch)
    assert compile_workflow(args(path, command='compile')) == 2
    assert run_workflow(args(path)).exit_code == 2
    assert not (tmp_path / '.orchestrate').exists()


@pytest.mark.parametrize('command', ['compile', 'run'])
def test_public_deep_source_refuses_before_dynamic_build_or_run(
    tmp_path, monkeypatch, caplog, capsys, command
):
    nested = '(list ' * 2000 + '0' + ')' * 2000
    path = source(tmp_path, f'(defworkflow main () -> Int {nested})')
    monkeypatch.chdir(tmp_path)

    from orchestrator.cli.commands import dynamic
    from orchestrator.workflow.dynamic import runtime
    def forbidden(*args, **kwargs):
        pytest.fail('excessively nested source reached dynamic publication or execution')
    monkeypatch.setattr(dynamic, 'build_dynamic_program_bundle', forbidden)
    monkeypatch.setattr(dynamic, 'prepare_dynamic_program_bundle', forbidden)
    monkeypatch.setattr(runtime, 'execute_dynamic_run', forbidden)

    if command == 'compile':
        result = compile_workflow(args(path, '--diagnostics-json', command='compile'))
        document = json.loads(capsys.readouterr().out)
        assert document['diagnostics'][0]['code'] == 'frontend_parse_error'
    else:
        result = run_workflow(args(path)).exit_code
        assert 'frontend_parse_error' in caplog.text

    assert result == 2
    assert not (tmp_path / '.orchestrate').exists()


def test_readonly_export_normalization_and_retained_default_publication(tmp_path):
    from orchestrator.workflow_lisp.build import normalize_frontend_artifact_exports
    destination = tmp_path / 'exports/map.json'
    request = {'source_map': [str(destination)]}
    normalized = normalize_frontend_artifact_exports(request, cwd=tmp_path, source_path=tmp_path / 'main.orc', create_parents=False)
    assert normalized['source_map'].destination == destination
    assert not destination.parent.exists()
    normalize_frontend_artifact_exports(request, cwd=tmp_path, source_path=tmp_path / 'main.orc')
    assert destination.parent.is_dir()


def test_failed_candidate_compile_does_not_create_export_directories(tmp_path, monkeypatch):
    path = source(tmp_path, '(define (unused) unknown) (defworkflow main () -> Int 1)')
    monkeypatch.chdir(tmp_path)
    destination = tmp_path / 'exports/map.json'
    assert compile_workflow(args(path, '--emit-source-map', str(destination), command='compile')) == 2
    assert not destination.parent.exists()
    path.write_text(path.read_text().replace('(:budget 1000)', '(:budget 1000) (:budget 2)'))
    assert compile_workflow(args(path, '--emit-source-map', str(destination), command='compile')) == 2
    assert not destination.parent.exists()


def test_malformed_header_keeps_export_destination_diagnostic_without_writes(tmp_path, monkeypatch, capsys):
    path = source(tmp_path)
    path.write_text(path.read_text().replace('(:budget 1000)', '(:budget 1000) (:budget 2)'))
    monkeypatch.chdir(tmp_path)
    assert compile_workflow(args(path, '--emit-source-map', str(tmp_path), '--diagnostics-json', command='compile')) == 2
    assert json.loads(capsys.readouterr().out)['diagnostics'][0]['code'] == 'artifact_export_destination_is_directory'
    assert not (tmp_path / '.orchestrate').exists()


@pytest.mark.parametrize('option,value', [('lowering_route', 'wcc'), ('boundary_admission_profile', 'public-default'), ('future_feature', True)])
def test_compile_service_unsupported_attributes_refuse_before_publication(tmp_path, monkeypatch, caplog, option, value):
    path = source(tmp_path)
    monkeypatch.chdir(tmp_path)
    destination = tmp_path / 'exports/map.json'
    supplied = Namespace(workflow=str(path), emit_source_map=[str(destination)])
    setattr(supplied, option, value)
    assert compile_workflow(supplied) == 2
    assert 'dynamic_option_unsupported' in caplog.text
    assert not (tmp_path / '.orchestrate').exists()
    assert not destination.parent.exists()


def test_actual_public_subprocess_fresh_run(tmp_path):
    path = source(tmp_path, '(defworkflow main () -> Int 0)')
    env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1]), PYTHONDONTWRITEBYTECODE='1')
    completed = subprocess.run([sys.executable, '-m', 'orchestrator', 'run', str(path)], cwd=tmp_path,
                               env=env, capture_output=True, text=True)
    assert completed.returncode == 0, completed.stderr
    roots = list((tmp_path / '.orchestrate/runs').iterdir())
    assert len(roots) == 1
    state = json.loads((roots[0] / 'state.json').read_text())
    assert state['status'] == 'completed' and state['workflow_outputs'] == 0


@pytest.mark.parametrize(('extra', 'streamed'), [((), True), (('--quiet',), False), (('--stream-output',), True)],
                         ids=['default', 'quiet', 'stream-output'])
def test_public_subprocess_streams_provider_output_unless_quiet(tmp_path, monkeypatch, extra, streamed):
    from tests.test_workflow_dynamic_providers import _manifests, _source, _stage_tools, _values
    path = _source(tmp_path)
    (tmp_path / 'notes').mkdir()
    (tmp_path / 'notes/input.md').write_text('document', encoding='utf-8')
    (tmp_path / 'reports').mkdir()
    providers, commands = _manifests(tmp_path)
    _stage_tools(tmp_path, monkeypatch)
    inputs = tmp_path / 'inputs.json'
    inputs.write_text(json.dumps(_values()), encoding='utf-8')
    env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1]), PYTHONDONTWRITEBYTECODE='1')
    completed = subprocess.run(
        [sys.executable, '-m', 'orchestrator', 'run', str(path), '--source-root', str(tmp_path),
         '--provider-externs-file', str(providers), '--command-boundaries-file', str(commands),
         '--input-file', str(inputs), *extra],
        cwd=tmp_path, env=env, capture_output=True, text=True)
    assert completed.returncode == 0, completed.stderr
    (root,) = (tmp_path / '.orchestrate/runs').iterdir()
    assert json.loads((root / 'state.json').read_text())['status'] == 'completed'
    assert ('private-provider-stdout' in completed.stdout) == streamed
    assert ('private-provider-stderr' in completed.stderr) == streamed
    assert any(b'private-provider-stdout' in out.read_bytes() for out in root.glob('effects/*/attempt-1/stdout.txt'))
    assert any(b'private-provider-stderr' in err.read_bytes() for err in root.glob('effects/*/attempt-1/stderr.txt'))


def test_runtime_uses_captured_source_after_preflight_deletion(tmp_path, monkeypatch):
    from orchestrator.cli.commands import dynamic
    from orchestrator.workflow.dynamic.state import load_dynamic_view
    path = source(tmp_path, '(defworkflow main ((n Int :default 0)) -> Int n)')
    original = path.read_bytes()
    prepare = dynamic.prepare_dynamic_run
    def delete_after_preflight(*a, **kw):
        built, inputs = prepare(*a, **kw)
        path.unlink()
        return built, inputs
    monkeypatch.setattr(dynamic, 'prepare_dynamic_run', delete_after_preflight)
    monkeypatch.chdir(tmp_path)
    result = run_workflow(args(path))
    assert result.exit_code == 0 and result.workflow_outputs == 0
    assert load_dynamic_view(result.run_root)['status'] == 'completed'
    import hashlib
    assert json.loads((result.run_root / 'run.json').read_text())['workflow_checksum'] == 'sha256:' + hashlib.sha256(original).hexdigest()


@pytest.mark.parametrize('phase', ['initial', 'terminal'])
def test_runtime_publication_failure_stops_and_never_reexecutes(tmp_path, monkeypatch, phase):
    from orchestrator.workflow.dynamic import runtime
    from orchestrator.workflow.workspace_files import WorkspaceFiles
    path = source(tmp_path)
    monkeypatch.chdir(tmp_path)
    evaluate = runtime.evaluate
    executions = []
    def observed(*a, **kw):
        executions.append(1)
        return evaluate(*a, **kw)
    monkeypatch.setattr(runtime, 'evaluate', observed)
    write = WorkspaceFiles.write_atomic
    def fail(self, path, content, **kw):
        state = json.loads(content) if str(path) == 'state.json' else None
        if state and ((phase == 'initial' and state['status'] == 'running') or
                      (phase == 'terminal' and state['status'] == 'completed')):
            raise OSError('injected atomic state failure')
        return write(self, path, content, **kw)
    monkeypatch.setattr(WorkspaceFiles, 'write_atomic', fail)
    result = run_workflow(args(path))
    assert result.exit_code == 1
    assert len(executions) == (0 if phase == 'initial' else 1)
    assert not (result.run_root / 'memo.jsonl').exists()
    if phase == 'initial': assert not (result.run_root / 'state.json').exists()
    else: assert json.loads((result.run_root / 'state.json').read_text())['status'] == 'running'


def test_run_id_collision_is_not_adopted(tmp_path, monkeypatch):
    from orchestrator.state import StateManager
    path = source(tmp_path)
    root = tmp_path / '.orchestrate/runs/collision'
    root.mkdir(parents=True)
    (root / 'existing').write_text('preserved')
    monkeypatch.setattr(StateManager, 'new_run_id', lambda: 'collision')
    monkeypatch.chdir(tmp_path)
    result = run_workflow(args(path))
    assert result.exit_code == 1
    assert list(root.iterdir()) == [root / 'existing']
    assert (root / 'existing').read_text() == 'preserved'


def test_explicit_local_entry_with_imported_helper_keeps_source_pin(tmp_path, monkeypatch):
    from tests.test_workflow_dynamic_source import write_source
    from orchestrator.workflow.dynamic.state import load_dynamic_view
    write_source(tmp_path, 'demo/lib', '(export helper) (defworkflow helper () -> Int 0)', budget=None)
    path = write_source(tmp_path, 'demo/main', '(import demo/lib :only (helper)) (export main) (defworkflow main () -> Int (helper))')
    monkeypatch.chdir(tmp_path)
    result = run_workflow(args(path, '--entry-workflow', 'main'))
    assert result.exit_code == 0 and result.workflow_outputs == 0
    for authored in tmp_path.rglob('*.orc'): authored.unlink()
    assert load_dynamic_view(result.run_root)['status'] == 'completed'
