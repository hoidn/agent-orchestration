"""Shared checked-program services stay independent of source preparation."""

from pathlib import Path
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
