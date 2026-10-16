"""Shared checked-program services stay independent of source preparation."""

from pathlib import Path
import json
import subprocess
import sys
import textwrap


def _run_without_frontend(source: str) -> None:
    blocker = """
import importlib.abc
import sys

forbidden = {
    'orchestrator.workflow_lisp.compiler',
    'orchestrator.workflow_lisp.reader',
    'orchestrator.workflow_lisp.syntax',
    'orchestrator.workflow_lisp.type_env',
    'orchestrator.workflow_lisp.closed.frontend',
}
class BlockFrontend(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if any(fullname == name or fullname.startswith(name + '.') for name in forbidden):
            raise AssertionError('source frontend import: ' + fullname)
sys.meta_path.insert(0, BlockFrontend())
"""
    result = subprocess.run(
        [sys.executable, "-c", textwrap.dedent(blocker) + textwrap.dedent(source)],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_prepared_provider_io_routes_without_source_frontend():
    _run_without_frontend("""
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from orchestrator.workflow.evaluated.provider_io import (
    ProviderIOActivation, ProviderIOCall, ProviderIOContext, WorkflowIOReader,
    resolve_io_route,
)

leaf = WorkflowIOReader(Path('/leaf/run.orc'))
child = WorkflowIOReader(Path('/child/run.orc'), imports={'leaf': leaf})
root = WorkflowIOReader(Path('/root/run.orc'), imports={'child': child},
    source_paths={'other': Path('/other/run.orc')})
activation = ProviderIOActivation('main', root, {('hook',): child})
assert resolve_io_route(('reader',), activation) is root
assert resolve_io_route(('slot', ('hook',)), activation) is child
assert resolve_io_route(('workflow', 'child', 'unused'), activation) is child
assert resolve_io_route(('procedure', 'leaf', 'unused', ('slot', ('hook',))), activation) is leaf
assert root.select('local', 'other').workflow_path == Path('/other/run.orc')

key = ['workflow', 'child', [], [], [], []]
program = SimpleNamespace(tree={'entry': 'main',
    'body': {'k': 'let', 'name': 'x',
        'value': {'k': 'call', 'callee': 'child', 'frame': 'f', 'args': []},
        'body': {'k': 'halt', 'value': {'k': 'name', 'name': 'x'}}},
    'definitions': {'child': {'key': key, 'body': {'k': 'halt', 'value': {'k': 'lit', 'v': 1}}}}},
    sites=(('child', 's'),), digest='sha256:checked')
carrier = ProviderIOContext(activation, {('main', 'f'): ProviderIOCall('child', ('workflow', 'child', 'unused'))},
    frozenset(program.sites), program.digest).bind(program)
selected = carrier.call('main', 'f', activation)
assert selected.reader is child
assert carrier.effect('child', 's', selected) is child
try:
    replace(carrier, program_digest='sha256:forged').bind(program)
except ValueError:
    pass
else:
    raise AssertionError('mismatched carrier admitted')
try:
    WorkflowIOReader(Path('/root/run.orc'), imports={'raw': object()}).select('raw', 'unused')
except ValueError:
    pass
else:
    raise AssertionError('unprepared reader admitted')
""")


def test_runtime_package_exports_keep_their_original_identity():
    import orchestrator.workflow as workflow
    import orchestrator.workflow.evaluated as evaluated
    from orchestrator.workflow.executor import WorkflowExecutor
    from orchestrator.workflow.pointers import PointerResolver
    from orchestrator.workflow.evaluated.machine import EffectHandler, evaluate_closed_program
    from orchestrator.workflow.evaluated.provider_io import (
        ProviderIOActivation, ProviderIOCall, ProviderIOContext, WorkflowIOReader,
        resolve_io_route,
    )
    from orchestrator.workflow_lisp.closed import frontend, artifact
    from orchestrator.workflow_lisp.closed import sites as legacy_sites
    from orchestrator.contracts.closed_program import sites

    assert workflow.WorkflowExecutor is WorkflowExecutor
    assert workflow.PointerResolver is PointerResolver
    assert evaluated.EffectHandler is EffectHandler
    assert evaluated.evaluate_closed_program is evaluate_closed_program
    for value in (ProviderIOActivation, ProviderIOCall, ProviderIOContext,
                  WorkflowIOReader, resolve_io_route):
        assert getattr(frontend, value.__name__) is value
    assert artifact.ProviderIOContext is ProviderIOContext
    for name in ('SiteAssignmentError', 'assign_sites', '_ast_nodes',
                 '_definition_order', '_effect_value_children', 'effect_value_operands'):
        assert getattr(legacy_sites, name) is getattr(sites, name)
    for module in (workflow, evaluated):
        try:
            getattr(module, 'unknown_export')
        except AttributeError:
            pass
        else:
            raise AssertionError('unknown package export admitted')


def test_checked_artifact_admission_and_command_performer_without_frontend(tmp_path):
    from orchestrator.workflow_lisp.closed.build import build_closed_program
    from orchestrator.workflow_lisp.closed.frontend import compile_typed_program
    from orchestrator.workflow_lisp.command_boundaries import ExternalToolBinding

    script = "import os; from pathlib import Path; Path(os.environ['ORCHESTRATOR_OUTPUT_BUNDLE_PATH']).write_text('7')"
    argv = (sys.executable, '-c', script)
    source = tmp_path / 'probe.orc'
    source.write_text('''(workflow-lisp (:language "0.1") (:target-dsl "2.35")
      (defmodule probe) (export run) (defworkflow run () -> Int
        (command-result fetch :argv (''' + ' '.join(json.dumps(value) for value in argv) + ''') :returns Int)))''')
    typed = compile_typed_program(source, entry_workflow='run', source_roots=(tmp_path,),
        workspace_root=tmp_path, command_boundaries={
            'fetch': ExternalToolBinding(name='fetch', stable_command=argv, closure=())})
    original = build_closed_program(typed)
    artifact = tmp_path / 'program.json'
    artifact.write_text(original.artifact())
    _run_without_frontend(f"""
from copy import deepcopy
import json
from pathlib import Path
from orchestrator.contracts.closed_program import check, command_check, names, static_effects
from orchestrator.contracts.closed_program.program import ClosedProgram, ClosedProgramInvalid
from orchestrator.contracts.closed_program.sites import _ast_nodes
from orchestrator.workflow.evaluated.commands import perform_command
from orchestrator.workflow.workspace_files import WorkspaceFiles

artifact = Path({str(artifact)!r}).read_text()
program = ClosedProgram.from_artifact(artifact)
assert program.artifact() == artifact
assert program.digest == {original.digest!r}
node, = [row for row in _ast_nodes(program.tree['body']) if row.get('k') == 'perform']
workspace = Path({str(tmp_path)!r})
attempt = workspace / '.orchestrate' / 'effects' / 'e1'
attempt.mkdir(parents=True)
workspace_files, attempt_files = WorkspaceFiles(workspace), WorkspaceFiles(attempt)
try:
    value, digest = perform_command(node, {argv!r},
        attempt_files=attempt_files, workspace_files=workspace_files)
    assert value.json_value() == 7
    assert digest == 'sha256:' + __import__('hashlib').sha256(b'7').hexdigest()
finally:
    attempt_files.close()
    workspace_files.close()
for payload in ('{{"schema":1,"schema":2}}', '{{"n":NaN}}'):
    try:
        ClosedProgram.from_artifact(payload)
    except ClosedProgramInvalid:
        pass
    else:
        raise AssertionError('malformed JSON admitted')
for target in ('2.34', '3.0'):
    tree = deepcopy(program.tree)
    tree['target'] = target
    try:
        ClosedProgram.from_artifact(json.dumps(tree))
    except ClosedProgramInvalid:
        pass
    else:
        raise AssertionError('unsupported evaluated target admitted')
""")


def test_shared_target_facts_preserve_native_dispatch_without_frontend():
    _run_without_frontend("""
from orchestrator.contracts.closed_program.targets import (
    SUPPORTED_TARGET_DSL_VERSIONS, target_dsl_uses_evaluated_execution,
    target_dsl_refuses_non_finite_floats,
)
assert '3.0' in SUPPORTED_TARGET_DSL_VERSIONS
assert {target for target in SUPPORTED_TARGET_DSL_VERSIONS
        if target_dsl_uses_evaluated_execution(target)} == {'2.35', '2.36'}
for target in ('2.34', '3.0', '2.37', 'invalid', None):
    assert not target_dsl_uses_evaluated_execution(target)
assert target_dsl_refuses_non_finite_floats('3.0')
""")


def test_checked_contract_compatibility_imports_keep_owner_identity():
    from orchestrator.contracts.closed_program import (
        check, command_check, names, program, static_effects, targets,
    )
    from orchestrator.workflow_lisp.closed import (
        check as old_check, command_check as old_command_check,
        names as old_names, program as old_program, static_effects as old_static_effects,
    )
    from orchestrator.workflow_lisp import syntax, type_env
    from orchestrator.workflow_lisp.wcc import route
    from orchestrator.workflow import type_descriptor

    for owner, legacy, exports in (
        (program, old_program, ('ClosedProgram', 'ClosedProgramInvalid', 'canonical_digest',
                               'program_digest', 'strip_provenance', '_canonical_json',
                               'logical_asset_base_for_module')),
        (check, old_check, ('CheckedFormError', 'validate', '_Checker')),
        (command_check, old_command_check, ('checked_command_interfaces', '_effect_children')),
        (static_effects, old_static_effects, ('StaticEffectError', '_check_provider_prompt_fill_declarations')),
        (names, old_names, ('canonical_callee_name_from_key', 'canonical_run_ref_signature',
                           'key_type_descriptor', 'run_ref_type_dependencies', '_parse_identity')),
        (targets, syntax, ('SUPPORTED_TARGET_DSL_VERSIONS', 'target_dsl_uses_evaluated_execution',
                           'target_dsl_refuses_non_finite_floats',
                           'target_dsl_supports_nested_structural_transport')),
    ):
        for export in exports:
            assert getattr(legacy, export) is getattr(owner, export)
    assert type_env._named_type_basename is type_descriptor._named_type_basename
    for export in ('LOWERING_SCHEMA_LEGACY', 'LOWERING_SCHEMA_WCC', 'DEFAULT_LOWERING_SCHEMA'):
        assert getattr(route, export) is getattr(targets, export)
