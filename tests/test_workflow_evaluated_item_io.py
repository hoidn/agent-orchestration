"""Real item performers keep typed paths and results rooted in outer authority.

Parallel public CLI dispatch is qualified after Task 4 installs its workers.
"""

from contextlib import closing
from dataclasses import replace
import json
import os
from pathlib import Path

import pytest

from orchestrator.providers import ProviderExecutor, ProviderRegistry
from orchestrator.workflow.evaluated import runtime
from orchestrator.workflow.evaluated.machine import evaluate_closed_program, site_classes
from orchestrator.workflow.evaluated.values import coerce_evaluated_value
from orchestrator.workflow.run_ref.contracts import canonical_sha256
from orchestrator.workflow.workspace_files import WorkspaceFiles
from orchestrator.workflow_lisp.closed.artifact import build_closed_program_bundle
from orchestrator.workflow_lisp.command_boundaries import ExternalToolBinding, CertifiedAdapterInputField
from orchestrator.workflow_lisp.stdlib_contracts import STDLIB_CERTIFIED_ADAPTER_BINDINGS_BY_NAME
from tests.test_workflow_evaluated_attempt_cwd import STRING
from tests.test_workflow_evaluated_command_lifecycle import _publish
from tests.test_workflow_evaluated_providers import _fixture
from tests.workflow_lisp_closed_program_helpers import build


ADAPTER = 'orchestrator.workflow_lisp.adapters.validate_review_findings_v1'
PATH_DECL = '(defpath Findings :kind relpath :under "artifacts/work" :must-exist true)'
RECORD_DECL = '(defrecord ReviewFindings (schema_version String) (items_path Findings))'


def reached_serial(program, inputs, *, provider_io=None):
    reached = []

    def observe(node, operands, identity, owner, reader):
        reached.append((node, operands, identity, owner, reader))
        value = {'schema_version': 'ReviewFindings.v1', 'items_path': 'artifacts/work/findings.json'}
        return coerce_evaluated_value(value, node['result'])

    evaluate_closed_program(program, inputs, effect_handler=observe, provider_io=provider_io)
    return reached[0]


def prepare_reached(authority, root, files, reached, *, executor=None):
    node, operands, identity, owner, reader = reached
    return runtime.prepare_effect(authority, node, operands, identity, owner=owner,
        workspace=root, run_files=authority.run_files, workspace_files=files,
        site_classes=site_classes(authority.program), reader=reader,
        provider_executor=executor, launch_workspace=coerce_evaluated_value('item', STRING))


def adapter_inputs(root):
    work = root / 'artifacts' / 'work'
    work.mkdir(parents=True)
    carrier = {'schema_version': 'ReviewFindings.v1', 'items_path': 'artifacts/work/findings.json'}
    (work / 'carrier.json').write_text(json.dumps(carrier))
    (work / 'findings.json').write_text('{"items":[]}')
    item = root / 'item'
    (item / 'artifacts' / 'work').mkdir(parents=True)
    (item / 'artifacts' / 'work' / 'carrier.json').write_text('item sentinel invalid carrier')
    (item / 'artifacts' / 'work' / 'findings.json').write_text('item sentinel invalid findings')
    return carrier


@pytest.mark.parametrize('transport', ['carrier', 'inline'])
def test_admitted_review_adapter_uses_logical_paths_from_actual_item_cwd(tmp_path, transport):
    expected = adapter_inputs(tmp_path)
    argv = f':argv ("python" "-m" "{ADAPTER}" items)'
    params = '((items Findings))'
    inputs = {'items': 'artifacts/work/carrier.json'}
    boundaries = {}
    if transport == 'inline':
        argv = ':adapter validate_review_findings_v1 :inputs ((schema_version "ReviewFindings.v1") (items_path items))'
        original = STDLIB_CERTIFIED_ADAPTER_BINDINGS_BY_NAME['validate_review_findings_v1']
        boundaries['validate_review_findings_v1'] = replace(original,
            closure=(str(Path(runtime.__file__).resolve().parents[2]),),
            input_signature=(CertifiedAdapterInputField(name='schema_version', type_name='String', required=True, transport_key='schema_version'),
                CertifiedAdapterInputField(name='items_path', type_name='Findings', required=True, transport_key='items_path')))
        inputs = {'items': 'artifacts/work/findings.json'}
    source = f'''(workflow-lisp (:language "0.1") (:target-dsl "2.37")
        (defmodule review) (export run) {PATH_DECL} {RECORD_DECL}
        (defworkflow run {params} -> ReviewFindings
            (command-result validate_review_findings_v1 {argv} :returns ReviewFindings)))'''
    program = build(tmp_path, source, boundaries=boundaries)
    reached = reached_serial(program, inputs)
    with _publish(tmp_path, program, inputs=inputs) as authority, closing(WorkspaceFiles(tmp_path)) as files:
        attempt = prepare_reached(authority, tmp_path, files, reached)
        assert attempt.resolved[0][1:3] == ['-m', ADAPTER]
        if transport == 'inline':
            assert json.loads(attempt.resolved[0][-1]) == expected
        result = runtime.finish_effect(attempt, runtime.perform_external(attempt))
        assert result.json_value() == expected
        assert json.loads((attempt.attempt_files.workspace / 'result.json').read_text()) == expected


@pytest.mark.parametrize('state_location', ['contained', 'external'])
def test_external_typed_document_and_absolute_result_are_attempt_owned(tmp_path, state_location):
    expected = adapter_inputs(tmp_path)
    script = '''import json, os, sys
from pathlib import Path
p = Path(sys.argv[-1]); assert p.is_absolute()
r = Path(os.environ['ORCHESTRATOR_OUTPUT_BUNDLE_PATH']); assert r.is_absolute()
inputs = json.loads(p.read_text()); logical = Path(os.environ['ORCHESTRATOR_WORKSPACE_ROOT'])
assert (logical / inputs['items_path']).is_file()
r.write_text(json.dumps(inputs))
'''
    (tmp_path / 'tool.py').write_text('raise SystemExit(55)')
    (tmp_path / 'item' / 'tool.py').write_text(script)
    source = f'''(workflow-lisp (:language "0.1") (:target-dsl "2.37")
        (defmodule tool) (export run) {PATH_DECL} {RECORD_DECL}
        (defworkflow run ((items Findings)) -> ReviewFindings
            (command-result fetch :argv ("python" "tool.py")
                :inputs ((schema_version "ReviewFindings.v1") (items_path items)) :returns ReviewFindings)))'''
    binding = ExternalToolBinding(name='fetch', stable_command=('python', 'tool.py'), closure=())
    program = build(tmp_path, source, boundaries={'fetch': binding})
    reached = reached_serial(program, {'items': expected['items_path']})
    state_root = None if state_location == 'contained' else tmp_path.parent / (tmp_path.name + '-state') / 'run-1'
    with _publish(tmp_path, program, inputs={'items': expected['items_path']}, run_root=state_root) as authority, closing(WorkspaceFiles(tmp_path)) as files:
        attempt = prepare_reached(authority, tmp_path, files, reached)
        document = attempt.resolved[1]
        assert json.loads(document) == expected
        result = runtime.finish_effect(attempt, runtime.perform_external(attempt))
        assert result.json_value() == expected
        assert (attempt.attempt_files.workspace / 'inputs.json').read_bytes() == document
        assert attempt.parts['argv'] == canonical_sha256(['python', 'tool.py'])


def test_provider_uses_outer_config_paths_and_returns_outer_relative_artifact(tmp_path, monkeypatch):
    expected = adapter_inputs(tmp_path)
    source = f'''(workflow-lisp (:language "0.1") (:target-dsl "2.37")
        (defmodule main) (export run) {PATH_DECL} {RECORD_DECL}
        (defworkflow run ((message String)) -> ReviewFindings
            (provider-result providers.review :prompt prompts.base :inputs (message) :returns ReviewFindings)))'''
    fixture = _fixture(tmp_path, source)
    built = build_closed_program_bundle(fixture[3])
    binary = tmp_path / 'bin' / 'codex'
    binary.write_text(binary.read_text().split('\n', 1)[0] + '\n' + '''import os, json, sys
from pathlib import Path
prompt = sys.stdin.read()
root = Path(os.environ['ORCHESTRATOR_WORKSPACE_ROOT'])
artifact = root / 'artifacts/work/provider.json'
artifact.write_text('{"items":[]}')
Path('provider-location.json').write_text(json.dumps({'cwd': str(Path.cwd()), 'root': str(root), 'prompt': prompt}))
Path(os.environ['ORCHESTRATOR_OUTPUT_BUNDLE_PATH']).write_text(json.dumps({'schema_version': 'ReviewFindings.v1', 'items_path': 'artifacts/work/provider.json'}))
''')
    monkeypatch.setenv('PATH', str(binary.parent) + os.pathsep + os.environ['PATH'])
    reached = reached_serial(built.program, {'message': 'artifacts/work/findings.json'}, provider_io=built.provider_io)
    with _publish(tmp_path, built.program, inputs={'message': 'artifacts/work/findings.json'}) as authority, closing(WorkspaceFiles(tmp_path)) as files:
        executor = ProviderExecutor(tmp_path, ProviderRegistry(), provider_observation_enabled=False)
        attempt = prepare_reached(authority, tmp_path, files, reached, executor=executor)
        assert executor.workspace == tmp_path
        assert str(tmp_path) not in attempt.resolved.prompt
        inactive = runtime.effect_inputs._resolve_effect_input(authority, reached[0], reached[1], reached[2],
            tmp_path, reached[4], None, None, None, attempt.result_path, owner=reached[3])[0]
        assert inactive.input_parts['prompt'] != attempt.resolved.input_parts['prompt']
        result = runtime.finish_effect(attempt, runtime.perform_external(attempt))
        assert result.json_value()['items_path'] == 'artifacts/work/provider.json'
        observed = json.loads((tmp_path / 'item' / 'provider-location.json').read_text())
        assert observed['cwd'] == str(tmp_path / 'item') and observed['root'] == str(tmp_path)
        assert (tmp_path / 'artifacts' / 'work' / 'provider.json').is_file()
        assert not (tmp_path / 'item' / 'artifacts' / 'work' / 'provider.json').exists()


def test_item_run_reference_keeps_outer_parent_authority_and_child_clone(tmp_path):
    from orchestrator.workflow.evaluated.machine import site_nodes
    from orchestrator.workflow_lisp.build import FrontendBuildRequest
    from tests.test_workflow_evaluated_run_ref import _public_fixture
    parent, source, refs = _public_fixture(tmp_path, parent_target='2.37', child_target='2.35')
    (parent / 'item').mkdir()
    built = build_closed_program_bundle(FrontendBuildRequest(source_path=source, workspace_root=parent))
    with _publish(parent, built.program, run_ref_root=str(refs)) as authority, closing(WorkspaceFiles(parent)) as files:
        identity, node = next(iter(site_nodes(built.program).items()))
        attempt = runtime.prepare_effect(authority, node, (), identity,
            owner=built.program.tree['entry'], workspace=parent, run_files=authority.run_files,
            workspace_files=files, site_classes=site_classes(built.program), reader=None,
            provider_executor=None, launch_workspace=coerce_evaluated_value('item', STRING))
        outcome = runtime.perform_external(attempt)
        assert not (attempt.attempt_files.workspace / 'result.json').exists()
        result = runtime.finish_effect(attempt, outcome)
        assert result.json_value()['value'] is True
        from orchestrator.workflow.evaluated.memo import read_memo
        snapshot = read_memo(authority.memo_path, site_classes(built.program))
        row = snapshot.active_commits[identity].data
        clone = Path(row['proof']['settled_result']['workspace_path'])
        assert clone.is_relative_to(refs) and (clone / '.git').is_dir()
        assert clone != parent / 'item'
        request = json.loads((clone.parent / 'child-request.json').read_text())
        assert request['parent_authority'] == {'run_root': str(authority.run_root), 'identity': identity, 'attempt': 1}
        assert (identity, 1) in snapshot.settlements


@pytest.mark.parametrize('target', ['2.35', '2.37'])
def test_public_serial_commands_clear_ambient_root_without_item_protocol(tmp_path, monkeypatch, target):
    from orchestrator.workflow.evaluated.authority import load_run_authority
    from orchestrator.workflow.evaluated.memo import read_memo
    from tests.test_workflow_evaluated_attempt_cwd import command_program, SCRIPT
    from tests.test_workflow_evaluated_cli import _run_cli
    (tmp_path / 'probe.py').write_text(SCRIPT)
    program = command_program(tmp_path)
    source = tmp_path / 'cwd.orc'
    source.write_text(source.read_text().replace('"2.37"', json.dumps(target)))
    manifest = tmp_path / 'commands.json'
    manifest.write_text(json.dumps({'fetch': {'stable_command': ['python', 'probe.py', 'data.txt'], 'closure': []}}))
    monkeypatch.setenv('ORCHESTRATOR_WORKSPACE_ROOT', '/ambient/poison')
    result = _run_cli(tmp_path, str(source), '--command-boundaries-file', str(manifest))
    assert result.returncode == 0, result.stderr
    (root,) = (tmp_path / '.orchestrate/runs').iterdir()
    authority = load_run_authority(root)
    snapshot = read_memo(authority.memo_path, site_classes(authority.program))
    assert snapshot.terminal.data['value']['root'] == ''
    assert 'launch_cwd' not in next(iter(snapshot.active_commits.values())).data['input_parts']


def test_nested_public_orchestrator_clears_parent_coordinate_in_own_serial_launch(tmp_path):
    from tests.test_workflow_evaluated_attempt_cwd import command_program, prepared
    item = tmp_path / 'item'
    item.mkdir()
    (tmp_path / 'probe.py').write_text('# outer')
    (item / 'inner.py').write_text("import os\nfrom pathlib import Path\nassert 'ORCHESTRATOR_WORKSPACE_ROOT' not in os.environ\nPath(os.environ['ORCHESTRATOR_OUTPUT_BUNDLE_PATH']).write_text('1')\n")
    (item / 'nested.orc').write_text('''(workflow-lisp (:language "0.1") (:target-dsl "2.35")
        (defmodule nested) (export run) (defworkflow run () -> Int
        (command-result inner :argv ("python" "inner.py") :returns Int)))''')
    (item / 'commands.json').write_text(json.dumps({'inner': {'stable_command': ['python', 'inner.py'], 'closure': ['inner.py']}}))
    (item / 'probe.py').write_text('''import json, os, subprocess, sys
from pathlib import Path
child = subprocess.run([sys.executable, '-m', 'orchestrator', 'run', 'nested.orc', '--command-boundaries-file', 'commands.json'], capture_output=True, text=True)
assert child.returncode == 0, child.stderr
Path(os.environ['ORCHESTRATOR_OUTPUT_BUNDLE_PATH']).write_text(json.dumps({'seen': 'nested', 'place': Path.cwd().name, 'root': os.environ['ORCHESTRATOR_WORKSPACE_ROOT']}))
''')
    with _publish(tmp_path, command_program(tmp_path)) as authority, closing(WorkspaceFiles(tmp_path)) as files:
        attempt = prepared(authority, tmp_path, files)
        result = runtime.finish_effect(attempt, runtime.perform_external(attempt))
        assert result.json_value() == {'seen': 'nested', 'place': 'item', 'root': str(tmp_path)}
        assert len(list((item / '.orchestrate/runs').glob('*/memo.jsonl'))) == 1


def test_package_origin_checks_actual_item_cwd_before_dispatch(tmp_path):
    adapter_inputs(tmp_path)
    shadow = tmp_path / 'item' / 'orchestrator'
    shadow.mkdir()
    (shadow / '__init__.py').write_text('# shadow\n')
    source = f'''(workflow-lisp (:language "0.1") (:target-dsl "2.37")
        (defmodule review) (export run) {PATH_DECL} {RECORD_DECL}
        (defworkflow run ((items Findings)) -> ReviewFindings
            (command-result validate_review_findings_v1
                :argv ("python" "-m" "{ADAPTER}" items) :returns ReviewFindings)))'''
    program = build(tmp_path, source, boundaries={})
    inputs = {'items': 'artifacts/work/carrier.json'}
    reached = reached_serial(program, inputs)
    with _publish(tmp_path, program, inputs=inputs) as authority, closing(WorkspaceFiles(tmp_path)) as files:
        attempt = prepare_reached(authority, tmp_path, files, reached)
        with pytest.raises(runtime.CommandPerformerError) as failure:
            runtime.perform_external(attempt)
        assert failure.value.code == 'command_module_origin_mismatch'
        with pytest.raises(runtime.CommandPerformerError):
            runtime.finish_effect(attempt, error=failure.value)
        assert not (attempt.attempt_files.workspace / 'stdout.txt').exists()
        assert attempt.attempt_files.closed


@pytest.mark.parametrize('unsafe', ['absolute', 'dotdot', 'symlink'])
def test_typed_document_paths_keep_outer_containment_before_item_dispatch(tmp_path, unsafe):
    from orchestrator.workflow.evaluated.inputs import DocumentInputError
    adapter_inputs(tmp_path)
    outside = tmp_path.parent / (tmp_path.name + '-outside.json')
    outside.write_text('{}')
    spelling = str(outside)
    if unsafe == 'dotdot':
        spelling = 'artifacts/work/../../escape.json'
    if unsafe == 'symlink':
        (tmp_path / 'artifacts/work/escape.json').symlink_to(outside)
        spelling = 'artifacts/work/escape.json'
    (tmp_path / 'tool.py').write_text('# outer')
    source = f'''(workflow-lisp (:language "0.1") (:target-dsl "2.37")
        (defmodule tool) (export run) {PATH_DECL} {RECORD_DECL}
        (defworkflow run ((items Findings)) -> ReviewFindings
            (command-result fetch :argv ("python" "tool.py")
                :inputs ((schema_version "ReviewFindings.v1") (items_path items)) :returns ReviewFindings)))'''
    binding = ExternalToolBinding(name='fetch', stable_command=('python', 'tool.py'), closure=())
    program = build(tmp_path, source, boundaries={'fetch': binding})
    inputs = {'items': spelling}
    if unsafe != 'symlink':
        from orchestrator.workflow.pure_expr import PureExprEvaluationError
        with pytest.raises(PureExprEvaluationError, match='normalized relative paths'):
            reached_serial(program, inputs)
        assert not (tmp_path / '.state').exists()
        return
    reached = reached_serial(program, inputs)
    with _publish(tmp_path, program, inputs=inputs) as authority, closing(WorkspaceFiles(tmp_path)) as files:
        with pytest.raises(DocumentInputError):
            prepare_reached(authority, tmp_path, files, reached)
        assert not authority.memo_path.read_bytes()
