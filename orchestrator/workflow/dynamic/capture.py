"""Read-only lexical reconstruction of checked native run snapshots."""
from __future__ import annotations

from collections.abc import Mapping
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from orchestrator.contracts.output_contract import OutputContractError
from orchestrator.workflow.evaluated.commands import CommandPerformerError, validate_effect_result
from orchestrator.workflow.evaluated.values import EvaluatedValueError, _thaw
from orchestrator.workflow.run_ref.contracts import canonical_json_bytes
from orchestrator.workflow.workspace_files import WorkspaceFiles
from orchestrator.workflow_lisp.dynamic.program import DynamicProgram, _node_children, _pointer
from orchestrator.workflow_lisp.repl_expr import ReplRefusal
from .evaluator import _generated_effect_wrapper, evaluate
from .state import DynamicStateError, load_dynamic_run


@dataclass(frozen=True)
class NativeAuthority:
    header: Mapping
    program: DynamicProgram


@dataclass(frozen=True)
class NativeCapturedRun:
    environment: Mapping[str, Any]
    definition: str
    pointer: str
    position: str
    result: Any
    has_result: bool
    snapshot: Mapping
    authority: NativeAuthority


class _Frontier(Exception):
    pass


def visible_bindings(captured):
    """Omit only compiler operand bindings active at the captured source position."""
    program = captured.authority.program
    node = program.definitions[captured.definition]["body"]
    pointer = _pointer(_pointer("/definitions", captured.definition), "body")
    generated = set()
    while captured.pointer == pointer or captured.pointer.startswith(pointer + "/"):
        if _generated_effect_wrapper(program, node, pointer):
            body_pointer = _pointer(pointer, "body")
            if captured.pointer == body_pointer or captured.pointer.startswith(body_pointer + "/"):
                generated.update(name for name, _value in node["bindings"])
            else:
                for index, (name, _value) in enumerate(node["bindings"]):
                    binding_pointer = _pointer(_pointer(_pointer(pointer, "bindings"), index), 1)
                    if captured.pointer == binding_pointer or captured.pointer.startswith(binding_pointer + "/"):
                        generated.update(row[0] for row in node["bindings"][:index])
                        break
        children = [(child_pointer, child) for child_pointer, child in _node_children(node, pointer)
                    if captured.pointer == child_pointer or captured.pointer.startswith(child_pointer + "/")]
        if not children:
            break
        pointer, node = children[0]
    return {name: value for name, value in captured.environment.items() if name not in generated}


def _error_matches(saved, actual):
    return (saved['code'] == actual.code and saved['location'] == actual.location
            and type(saved['metadata'].get('steps')) is int
            and saved['metadata'].get('steps') == actual.metadata.get('steps'))


def capture_run_environment(run_root: Path, expected_program: DynamicProgram) -> NativeCapturedRun:
    """Consume physical completed results without creating execution authority."""
    with closing(WorkspaceFiles(run_root)) as files:
        header, program, state = load_dynamic_run(run_root, run_files=files)
        if program.semantic_digest != expected_program.semantic_digest:
            raise ReplRefusal('resume_program_changed', 'current program differs from the run header')
        rows = state['effects']
        consumed = 0
        last_boundary = 0
        scope = None
        position = None
        result = None
        halted = False
        failure = None

        def observe(environment, code, pointer, context, steps):
            nonlocal scope
            scope = (environment, code, pointer)

        with closing(WorkspaceFiles(Path(header['workspace']))) as workspace:
            def replay(_program, node, operands, *, pointer, code, context, steps, workspace_files):
                nonlocal consumed, last_boundary, position
                if consumed == len(rows):
                    if state['status'] == 'failed':
                        saved = state['error']
                        if (saved['location'] != pointer or type(saved['metadata'].get('steps')) is not int
                                or saved['metadata'].get('steps') != steps):
                            raise DynamicStateError('failed terminal differs from reached effect frontier')
                    position = f"effect:{consumed + 1}"
                    raise _Frontier
                row = rows[consumed]
                if (row['definition'], row['location'], row['effect_class']) != (code, pointer, node['class']):
                    raise DynamicStateError('recorded effect differs from reached effect')
                consumed += 1
                last_boundary = steps
                if row['status'] != 'completed':
                    if row['status'] == 'failed':
                        saved = row['error']
                        if (type(saved['metadata'].get('steps')) is not int
                                or saved['metadata'].get('steps') != steps or saved['location'] != pointer):
                            raise DynamicStateError('failed effect diagnostic differs from its boundary')
                        if state['status'] == 'failed' and canonical_json_bytes(_thaw(saved)) != canonical_json_bytes(_thaw(state['error'])):
                            raise DynamicStateError('failed row and terminal diagnostics disagree')
                        if state['status'] == 'failed' and state['steps_used'] != steps:
                            raise DynamicStateError('failed terminal steps differ from effect boundary')
                    elif state['status'] == 'failed':
                        raise DynamicStateError('failed terminal has a running effect')
                    position = f"{row['status']}:{row['ordinal']}"
                    raise _Frontier
                try:
                    value, _digest, _artifacts = validate_effect_result(
                        _thaw(node), files.read(row['result_path']),
                        str(files.workspace / row['result_path']), workspace,
                        native_result=True,
                    )
                except (OSError, TypeError, ValueError, RecursionError, OutputContractError, CommandPerformerError) as exc:
                    raise DynamicStateError(f'invalid physical completed result: {exc}') from exc
                return value

            try:
                evaluated = evaluate(program, header['bound_inputs'], workspace_files=workspace,
                                     command_effect=replay, provider_effect=replay, observer=observe)
                result, halted = evaluated.value, True
                position = 'halt' if state['status'] == 'completed' else 'halt-unpublished'
            except _Frontier:
                pass
            except EvaluatedValueError as exc:
                failure = exc
                position = f'failed:{exc.code}'

        if consumed != len(rows):
            raise DynamicStateError('reconstruction leaves unreachable recorded effects')
        if state['status'] == 'running' and state['steps_used'] != last_boundary:
            raise DynamicStateError('saved progress steps differ from the last recorded effect boundary')
        if state['status'] == 'completed':
            if not halted or failure is not None:
                raise DynamicStateError('completed terminal does not reconstruct a halt')
            if evaluated.steps != state['steps_used'] or canonical_json_bytes(_thaw(result)) != canonical_json_bytes(_thaw(state['workflow_outputs'])):
                raise DynamicStateError('completed terminal value or steps disagree')
        elif state['status'] == 'failed':
            if halted:
                raise DynamicStateError('failed terminal reconstructs a halt')
            if failure is not None:
                if not _error_matches(state['error'], failure) or state['steps_used'] != failure.metadata.get('steps'):
                    raise DynamicStateError('failed terminal diagnostic or steps disagree')
            elif not rows or rows[-1]['status'] == 'completed':
                if state['steps_used'] != state['error']['metadata'].get('steps'):
                    raise DynamicStateError('pre-dispatch terminal steps disagree')
        elif failure is not None and rows and rows[-1]['status'] != 'completed':
            raise DynamicStateError('pure failure contradicts unfinished recorded effect')
        if scope is None:
            raise DynamicStateError('reconstruction has no lexical scope')
        environment, definition, pointer = scope
        return NativeCapturedRun(environment, definition, pointer, position, result,
                                 state['status'] == 'completed', state,
                                 NativeAuthority(header, program))
