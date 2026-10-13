"""One-datum native REPL expressions using ordinary lowering and admission."""
from __future__ import annotations

from copy import copy, deepcopy
from contextlib import closing
from dataclasses import dataclass
import hashlib
from pathlib import Path

from orchestrator.workflow.dynamic.capture import NativeCapturedRun, visible_bindings
from orchestrator.workflow.dynamic.evaluator import _Closure, _evaluate_body, _kind
from orchestrator.workflow.evaluated.values import EvaluatedValueError, _thaw
from orchestrator.workflow.run_ref.contracts import canonical_json_bytes
from orchestrator.workflow.workspace_files import WorkspaceFiles
from ..reader import read_sexpr_text
from ..syntax import ensure_syntax_datum
from ..repl_expr import ReplRefusal
from .program import _node_children, _pointer


@dataclass
class NativeLoadedModule:
    build: object
    source_path: Path
    frontend_argv: tuple[str, ...] = ()

    def __post_init__(self):
        if self.build.lowerer is None:
            raise ReplRefusal('repl_module_context_missing', 'load requires retained native compiler context')


def runtime_kind(value):
    return 'Function' if isinstance(value, _Closure) else _kind(value)


def printable_value(value):
    if isinstance(value, _Closure):
        return '<function>'
    try:
        return canonical_json_bytes(_thaw(value)).decode('utf-8')
    except (TypeError, ValueError, RecursionError):
        raise ReplRefusal('repl_value_not_printable', 'native value contains a function or another non-JSON value') from None


def evaluate_repl_expression(line: str, module: NativeLoadedModule, captured: NativeCapturedRun):
    parsed = read_sexpr_text(line, source_path='<repl>')
    if len(parsed.items) != 1:
        raise ReplRefusal('repl_expression_arity', 'enter exactly one expression')
    datum = ensure_syntax_datum(parsed.items[0], module_path="<repl>", form_path=("repl",))
    original = module.build.lowerer
    lowerer = copy(original)
    for name in ('definitions', 'schemas', 'bindings', 'locations', 'definition_locations',
                 'boundary_locations', 'effect_subjects', 'expression_paths'):
        setattr(lowerer, name, dict(getattr(original, name)))
    virtual = 'repl/session'
    while virtual in module.build.program.sources:
        virtual += '/query'
    lowerer.bindings = deepcopy(original.bindings)
    lowerer.emitted_module = virtual

    def index(node, path):
        lowerer.expression_paths[id(node)] = path
        for i, child in enumerate(getattr(node, 'items', ())):
            index(child, (*path, str(i)))

    index(datum, ('body',))
    env = visible_bindings(captured)
    resolution_module = module.build.program.definitions[captured.definition]['owner']['module']
    body, _free = lowerer.lower(datum, set(env), resolution_module, 'expression')
    code = f'{virtual}::expression'
    lowerer.definitions[code] = {'params': list(env), 'captures': [], 'body': body,
                                 'owner': lowerer.owner(virtual), 'boundary': None}
    lowerer.definition_locations[code] = (datum.span, virtual, ('repl',))
    for new_code in set(lowerer.definitions) - set(original.definitions):
        pending = [lowerer.definitions[new_code]['body']]
        while pending:
            node = pending.pop()
            if node['k'] == 'perform':
                raise ReplRefusal('repl_effect_refused', 'entered expressions cannot perform effects')
            pending.extend(child for _pointer_, child in _node_children(node, ''))
    sources = _thaw(module.build.program.sources)
    sources[virtual] = {'root_role': 'source', 'relative_path': '<repl>',
                        'source_sha256': 'sha256:' + hashlib.sha256(line.encode('utf-8')).hexdigest()}
    program = lowerer.assemble(module.build.program.entry, sources)
    try:
        with closing(WorkspaceFiles(Path(captured.authority.header['workspace']))) as workspace:
            result = _evaluate_body(program, program.definitions[code]['body'], env, code=code,
                                    pointer=_pointer(_pointer('/definitions', code), 'body'),
                                    workspace_files=workspace, refuse_effects=True)
    except EvaluatedValueError as exc:
        if exc.code == 'dynamic_effect_unsupported':
            raise ReplRefusal('repl_effect_refused', 'entered expressions cannot perform effects') from None
        raise
    return result.value
