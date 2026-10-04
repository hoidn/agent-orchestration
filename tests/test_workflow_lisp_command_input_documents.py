from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from orchestrator.workflow_lisp.build import _parse_command_boundaries_manifest
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from orchestrator.workflow_lisp.compiler import compile_stage3_module
from orchestrator.workflow_lisp.wcc.defunctionalize import _frontend_expr_from_wcc_loop_binding_value
from orchestrator.workflow_lisp.wcc.model import WccPerform
from tests.test_workflow_lisp_closed_program_elaboration import _compile_and_elaborate, _let_chain, _walk_wcc


def _commands(tmp_path: Path, names=("emit",)):
    path = tmp_path / "commands.json"
    path.write_text(json.dumps({name: {"kind": "external_tool", "stable_command": ["python", f"{name}.py"]} for name in names}))
    return _parse_command_boundaries_manifest(json.loads(path.read_text()), manifest_path=path)


def _source(body: str, *, target="2.35", params="", declarations="", returns="String"):
    return f'''(workflow-lisp (:language "0.1") (:target-dsl "{target}")
      (defmodule cp/closed_elaboration) (export run)
      {declarations}
      (defworkflow run ({params}) -> {returns} {body}))'''


def _perform(body):
    return next(node for node in _walk_wcc(body) if isinstance(node, WccPerform) and node.target_name == "emit")


@pytest.mark.parametrize("inputs,present,fields", [("", False, ()), (":inputs ()", True, ()), (':inputs ((message "hi"))', True, ("message",))])
def test_external_document_presence_survives_source_and_wcc(tmp_path, inputs, present, fields):
    body = _compile_and_elaborate(tmp_path, source=_source(f'(command-result emit :argv ("python" "emit.py") {inputs} :returns String)'), commands=_commands(tmp_path))
    perform = _perform(body)
    expr = _frontend_expr_from_wcc_loop_binding_value(perform)
    assert expr.inputs_present is present
    assert perform.operation_payload.get("inputs_present", False) is present
    assert tuple(name for name, _ in perform.operation_payload["adapter_inputs"]) == fields
    assert tuple(arg.value for arg in perform.positional_args) == ("python", "emit.py")
    assert replace(expr, step_name="copied").inputs_present is present
    from orchestrator.workflow_lisp.build_manifest_io import _json_data
    serialized = _json_data(expr)
    assert serialized.get("inputs_present", False) is present
    assert ("operand_order" in serialized) is present


@pytest.mark.parametrize("first", ["argv", "inputs"])
def test_operand_effects_follow_reordered_sections_once(tmp_path, first):
    declarations = '''(defproc number () -> Int :effects ((uses-command number)) :lowering inline
      (command-result number :argv ("python" "number.py") :returns Int))
      (defproc text () -> String :effects ((uses-command text)) :lowering inline
      (command-result text :argv ("python" "text.py") :returns String))'''
    argv = ':argv ("python" "emit.py" (number))'
    inputs = ':inputs ((message (text)))'
    sections = f'{argv} {inputs}' if first == "argv" else f'{inputs} {argv}'
    body = _compile_and_elaborate(tmp_path, source=_source(f'(command-result emit {sections} :returns String)', declarations=declarations), commands=_commands(tmp_path, ("emit", "number", "text")))
    calls = [let.bound_value for let in _let_chain(body) if hasattr(let.bound_value, "callee_name")]
    expected = ["number", "text"] if first == "argv" else ["text", "number"]
    assert [call.callee_name.rsplit("::", 1)[-1] for call in calls] == expected
    assert len(calls) == 2
    assert _frontend_expr_from_wcc_loop_binding_value(_perform(body)).operand_order == (first, "inputs" if first == "argv" else "argv")


@pytest.mark.parametrize("inputs", ["7", "(message)", '((message "one" "two"))', '((message "one") (message "two"))', '(("" "one"))', '((() "one"))'])
def test_external_document_pairs_are_checked_at_source(tmp_path, inputs):
    with pytest.raises(LispFrontendCompileError) as caught:
        _compile_and_elaborate(tmp_path, source=_source(f'(command-result emit :argv ("python" "emit.py") :inputs {inputs} :returns String)'), commands=_commands(tmp_path))
    diagnostic = caught.value.diagnostics[0]
    assert diagnostic.code == "command_result_inputs_invalid"
    assert diagnostic.form_path == ("workflow-lisp", "defworkflow", "run")
    assert Path(diagnostic.span.start.path).name == "closed_elaboration.orc"


def _compile_old_target(tmp_path, source, commands):
    path = tmp_path / "cp" / "closed_elaboration.orc"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source)
    return compile_stage3_module(path, command_boundaries=commands, validate_shared=False, workspace_root=tmp_path)


@pytest.mark.parametrize("target,extra", [("2.34", ""), ("2.35", ":adapter emit")])
def test_external_documents_preserve_target_and_mode_refusals(tmp_path, target, extra):
    with pytest.raises(LispFrontendCompileError) as caught:
        _compile_old_target(tmp_path, source=_source(f'(command-result emit :argv ("python" "emit.py") {extra} :inputs () :returns String)', target=target), commands=_commands(tmp_path))
    assert caught.value.diagnostics[0].code == "command_result_adapter_invalid"


def _adapter_commands(tmp_path, type_name="String"):
    from tests.test_workflow_lisp_command_adapters import _typed_adapter_manifest_payload

    payload = _typed_adapter_manifest_payload()["normalize_result"]
    payload.update(output_type_name="String", input_signature=[
        {"name": "payload", "type_name": type_name, "required": True, "transport_key": "body"},
        {"name": "optional", "type_name": "Int", "required": False, "transport_key": "extra"}])
    path = tmp_path / "adapter.json"
    path.write_text(json.dumps({"emit": payload}))
    return _parse_command_boundaries_manifest(json.loads(path.read_text()), manifest_path=path)


def test_certified_name_cannot_select_external_document_transport(tmp_path):
    with pytest.raises(LispFrontendCompileError) as caught:
        _compile_and_elaborate(tmp_path, source=_source('(command-result emit :argv ("python" "scripts/normalize_result.py") :inputs () :returns String)'), commands=_adapter_commands(tmp_path))
    assert caught.value.diagnostics[0].code == "command_result_adapter_invalid"


@pytest.mark.parametrize("type_name", ["String", "List[Int]", "Optional[Int]", "Map[String,Int]", "List[Choice]", "Optional[List[Choice]]", "Map[String,List[Choice]]", "Candidate", "Asset"])
@pytest.mark.parametrize("certified", [False, True])
def test_checked_recursive_inputs_use_existing_transport_types(tmp_path, type_name, certified):
    declarations = '''(defpath Asset :kind relpath :under "artifacts" :must-exist true)
      (defunion Choice (YES (asset Asset)) (NO))
      (defrecord Candidate (choices List[Choice]) (note Optional[String]))'''
    mode = ':adapter emit' if certified else ':argv ("python" "emit.py")'
    commands = _adapter_commands(tmp_path, type_name) if certified else _commands(tmp_path)
    body = _compile_and_elaborate(tmp_path, source=_source(f'(command-result emit {mode} :inputs ((payload value)) :returns String)', params=f'(value {type_name})', declarations=declarations), commands=commands)
    expr = _frontend_expr_from_wcc_loop_binding_value(_perform(body))
    assert tuple(name for name, _ in expr.adapter_inputs) == ("payload",)
    assert expr.adapter_name == ("emit" if certified else None)


@pytest.mark.parametrize("certified", [False, True])
def test_nontransportable_document_input_is_rejected(tmp_path, certified):
    mode = ':adapter emit' if certified else ':argv ("python" "emit.py")'
    commands = _adapter_commands(tmp_path, "ProcRef[Int -> Int]") if certified else _commands(tmp_path)
    with pytest.raises(LispFrontendCompileError) as caught:
        _compile_and_elaborate(tmp_path, source=_source(f'(command-result emit {mode} :inputs ((payload (proc-ref identity))) :returns String)', declarations='(defproc identity ((n Int)) -> Int :effects () :lowering inline n)'), commands=commands)
    expected = "command_adapter_input_not_projectable" if certified else "command_result_inputs_invalid"
    assert caught.value.diagnostics[0].code == expected


def test_certified_recursive_inputs_preserve_nominal_type_check(tmp_path):
    declarations = '(defrecord First (value Int)) (defrecord Second (value Int))'
    with pytest.raises(LispFrontendCompileError) as caught:
        _compile_and_elaborate(tmp_path, source=_source('(command-result emit :adapter emit :inputs ((payload value)) :returns String)', params='(value Second)', declarations=declarations), commands=_adapter_commands(tmp_path, "First"))
    assert caught.value.diagnostics[0].code == "type_mismatch"


def test_certified_old_target_keeps_scalar_projection_restriction(tmp_path):
    with pytest.raises(LispFrontendCompileError) as caught:
        _compile_old_target(tmp_path, source=_source('(command-result emit :adapter emit :inputs ((payload value)) :returns String)', target="2.34", params='(value Box)', declarations='(defrecord Box (value Int))'), commands=_adapter_commands(tmp_path, "Box"))
    assert caught.value.diagnostics[0].code == "command_adapter_input_not_projectable"


def test_pure_operand_is_bound_in_source_order_before_later_effect(tmp_path):
    from orchestrator.workflow_lisp.wcc.model import WccCall, WccPureOp

    declarations = '''(defproc number () -> Int :effects ((uses-command number)) :lowering inline
      (command-result number :argv ("python" "number.py") :returns Int))'''
    body = _compile_and_elaborate(tmp_path, source=_source('(command-result emit :inputs ((quotient (/ 7.0 divisor))) :argv ("python" "emit.py" (number)) :returns String)', declarations=declarations, params='(divisor Float)'), commands=_commands(tmp_path, ("emit", "number")))
    values = [let.bound_value for let in _let_chain(body)]
    assert isinstance(values[0], WccPureOp)
    assert isinstance(values[1], WccCall)
    assert isinstance(values[-1], WccPerform)


def test_legacy_adapter_binding_error_precedes_operand_type_error(tmp_path):
    source = _source('(command-result emit :adapter emit :inputs ((payload (+ "bad" 1))) :returns Int)', target="2.34", returns="Int")
    with pytest.raises(LispFrontendCompileError) as caught:
        _compile_old_target(tmp_path, source, _adapter_commands(tmp_path, "Int"))
    assert caught.value.diagnostics[0].code == "command_result_return_type_invalid"


@pytest.mark.parametrize("first", ["argv", "inputs"])
@pytest.mark.parametrize("fields", [("text", "more"), ("more", "text")])
def test_operand_order_survives_nested_let_if_and_import(tmp_path, first, fields):
    from tests.test_workflow_lisp_closed_program_elaboration import _walk_wcc
    from orchestrator.workflow_lisp.wcc.model import WccCall

    library = tmp_path / "cp" / "library.orc"
    library.parent.mkdir()
    library.write_text('''(workflow-lisp (:language "0.1") (:target-dsl "2.35")
      (defmodule cp/library) (export text)
      (defproc text () -> String :effects ((uses-command text)) :lowering inline
        (command-result text :argv ("python" "text.py") :returns String)))''')
    declarations = '''(defproc number () -> Int :effects ((uses-command number)) :lowering inline
        (command-result number :argv ("python" "number.py") :returns Int))
      (defproc more () -> Int :effects ((uses-command more)) :lowering inline
        (command-result more :argv ("python" "more.py") :returns Int))'''
    argv = ':argv ("python" "emit.py" (let* ((n (number))) n))'
    expressions = {"text": '(if flag (text) "unused")', "more": '(more)'}
    inputs = ':inputs (' + ' '.join(f'({name} {expressions[name]})' for name in fields) + ')'
    sections = f'{argv} {inputs}' if first == "argv" else f'{inputs} {argv}'
    source = _source(f'(command-result emit {sections} :returns String)', declarations=declarations, params='(flag Bool)').replace('(defmodule cp/closed_elaboration)', '(defmodule cp/closed_elaboration) (import cp/library :only (text))')
    body = _compile_and_elaborate(tmp_path, source=source, commands=_commands(tmp_path, ("emit", "number", "text", "more")))
    names = [node.callee_name.rsplit("::", 1)[-1] for node in _walk_wcc(body) if isinstance(node, WccCall)]
    expected = ["number", *fields] if first == "argv" else [*fields, "number"]
    assert names == expected
    assert tuple(name for name, _ in _perform(body).operation_payload["adapter_inputs"]) == fields


def test_certified_pure_operands_are_bound_in_authored_field_order(tmp_path):
    from orchestrator.workflow_lisp.wcc.model import WccPureOp

    source = _source('(command-result emit :adapter emit :inputs ((optional (+ n 1)) (payload (string/concat text "!"))) :returns String)', params='(n Int) (text String)')
    body = _compile_and_elaborate(tmp_path, source=source, commands=_adapter_commands(tmp_path))
    values = [let.bound_value for let in _let_chain(body)]
    assert [value.operator for value in values if isinstance(value, WccPureOp)] == ["+", "string/concat"]
    assert isinstance(values[-1], WccPerform)


def test_generic_specialization_preserves_document_presence_and_order(tmp_path):
    from orchestrator.workflow_lisp.closed.frontend import compile_typed_program
    from orchestrator.workflow_lisp.expression_traversal import map_expr, walk_expr
    from orchestrator.workflow_lisp.expressions import CommandResultExpr

    declarations = '''(defproc send :forall (T) ((value T)) -> String
      :effects ((uses-command emit)) :lowering inline
      (command-result emit :inputs ((payload "hi")) :argv ("python" "emit.py" value) :returns String))'''
    path = tmp_path / "cp" / "closed_elaboration.orc"
    path.parent.mkdir()
    path.write_text(_source('(send value)', params='(value Int)', declarations=declarations))
    typed = compile_typed_program(path, entry_workflow="run", source_roots=(tmp_path,), command_boundaries=_commands(tmp_path), workspace_root=tmp_path)
    specialized = [proc for proc in typed.procedures.values() if proc.specialization is not None]
    commands = [node for proc in specialized for node in walk_expr(proc.typed_body.expr) if isinstance(node, CommandResultExpr)]
    assert commands
    assert all(node.inputs_present and node.operand_order == ("inputs", "argv") for node in commands)
    rebuilt = map_expr(commands[0], lambda node: node)
    assert rebuilt.inputs_present and rebuilt.operand_order == ("inputs", "argv")


@pytest.mark.parametrize("source,expected", [
    ('(command-result emit :argv ("python" "emit.py") :returns String)', "19e8617fd9d5d4522c20e2b7e92e062bb09285e5191134d4a8437b597f2abcaa"),
    ('(command-result emit :adapter emit :inputs ((payload "hi")) :returns String)', "7074c9ecd4a5b6647e4fd9ddd170ca0c9946c740a2e34bbe1021ba0f96862986"),
])
@pytest.mark.parametrize("target", ["2.34", "2.35"])
def test_legacy_node_serialization_matches_frozen_source_bytes(source, expected, target):
    import hashlib
    from orchestrator.workflow_lisp.build_manifest_io import _json_data
    from orchestrator.workflow_lisp.expressions import elaborate_expression
    from tests.test_workflow_lisp_command_adapters import _expression_syntax

    expr = elaborate_expression(_expression_syntax(source), bound_names=frozenset(), target_dsl_version=target)
    payload = _json_data(expr)
    assert "inputs_present" not in payload and "operand_order" not in payload
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    assert hashlib.sha256(raw).hexdigest() == expected


def test_empty_expanded_document_field_is_rejected():
    from orchestrator.workflow_lisp.expressions import elaborate_expression
    from tests.test_workflow_lisp_command_adapters import _expression_syntax

    node = _expression_syntax('(command-result emit :argv ("python" "emit.py") :inputs ((field "hi")) :returns String)')
    pairs = node.datum.items[5]
    pair = pairs.items[0]
    empty_pair = replace(pair, items=(replace(pair.items[0], value=""), pair.items[1]))
    empty_pairs = replace(pairs, items=(empty_pair,))
    datum = replace(node.datum, items=(*node.datum.items[:5], empty_pairs, *node.datum.items[6:]))
    with pytest.raises(LispFrontendCompileError) as caught:
        elaborate_expression(replace(node, datum=datum), bound_names=frozenset(), target_dsl_version="2.35")
    assert caught.value.diagnostics[0].code == "command_result_inputs_invalid"


def test_legacy_command_semantic_identity_keeps_its_frozen_fields():
    from orchestrator.workflow_lisp.expressions import elaborate_expression
    from orchestrator.workflow_lisp.procedure_typecheck import _semantic_identity
    from tests.test_workflow_lisp_command_adapters import _expression_syntax

    source = '(command-result emit :argv ("python" "emit.py") :returns String)'
    expr = elaborate_expression(_expression_syntax(source), bound_names=frozenset(), target_dsl_version="2.34")
    expected = "CommandResultExpr(step_name='emit',argv=(LiteralExpr(value='python',literal_kind='string'),LiteralExpr(value='emit.py',literal_kind='string')),adapter_name=None,adapter_inputs=(),return_spec=ReturnSpec(type_name='String',guidance=None))"
    assert _semantic_identity(expr) == expected
    empty = elaborate_expression(_expression_syntax(source.replace(':returns', ':inputs () :returns')), bound_names=frozenset(), target_dsl_version="2.35")
    assert _semantic_identity(empty) != expected
    reordered = replace(empty, operand_order=("inputs", "argv"))
    assert _semantic_identity(reordered) != _semantic_identity(empty)


@pytest.mark.parametrize("type_name,template", [("Int", "T"), ("List[Int]", "List[T]"), ("Map[String,List[Choice]]", "Map[String,List[T]]")])
def test_generic_document_contract_is_checked_after_instantiation(tmp_path, type_name, template):
    declarations = f'''(defunion Choice (YES (value Int)) (NO))
      (defproc send :forall (T) ((value {template})) -> String
        :effects ((uses-command emit)) :lowering inline
        (command-result emit :inputs ((payload value)) :argv ("python" "emit.py") :returns String))'''
    body = _compile_and_elaborate(tmp_path, source=_source('(send value)', params=f'(value {type_name})', declarations=declarations), commands=_commands(tmp_path))
    from orchestrator.workflow_lisp.wcc.model import WccCall
    assert any(isinstance(let.bound_value, WccCall) for let in _let_chain(body))


def test_generic_document_contract_rejects_nontransportable_instantiation(tmp_path):
    declarations = '''(defproc identity ((n Int)) -> Int :effects () :lowering inline n)
      (defproc send :forall (T) ((value T)) -> String
        :effects ((uses-command emit)) :lowering inline
        (command-result emit :inputs ((payload value)) :argv ("python" "emit.py") :returns String))'''
    with pytest.raises(LispFrontendCompileError) as caught:
        _compile_and_elaborate(tmp_path, source=_source('(send (proc-ref identity))', declarations=declarations), commands=_commands(tmp_path))
    assert caught.value.diagnostics[0].code == "command_result_inputs_invalid"
    assert "send" in caught.value.diagnostics[0].form_path


@pytest.mark.parametrize("type_name", ["String", "Int"])
def test_certified_generic_document_checks_signature_after_instantiation(tmp_path, type_name):
    declarations = '''(defproc send :forall (T) ((value T)) -> String
      :effects ((uses-command emit)) :lowering inline
      (command-result emit :adapter emit :inputs ((payload value)) :returns String))'''
    source = _source('(send value)', params=f'(value {type_name})', declarations=declarations)
    if type_name == "Int":
        with pytest.raises(LispFrontendCompileError) as caught:
            _compile_and_elaborate(tmp_path, source=source, commands=_adapter_commands(tmp_path))
        assert caught.value.diagnostics[0].code == "type_mismatch"
    else:
        body = _compile_and_elaborate(tmp_path, source=source, commands=_adapter_commands(tmp_path))
        assert _let_chain(body)


def test_recursive_document_keeps_existing_proc_ref_storage_refusal(tmp_path):
    declarations = '''(defrecord Bad (hook ProcRef[Int -> Int]))
      (defproc identity ((n Int)) -> Int :effects () :lowering inline n)'''
    source = _source('(command-result emit :argv ("python" "emit.py") :inputs ((payload (record Bad :hook (proc-ref identity)))) :returns String)', declarations=declarations)
    with pytest.raises(LispFrontendCompileError) as caught:
        _compile_and_elaborate(tmp_path, source=source, commands=_commands(tmp_path))
    assert caught.value.diagnostics[0].code == "proc_ref_runtime_transport_forbidden"


def _colliding_input_commands(tmp_path, certified):
    if not certified:
        return _commands(tmp_path, ("emit", "one", "two"))
    from tests.test_workflow_lisp_command_adapters import _typed_adapter_manifest_payload

    payload = _typed_adapter_manifest_payload()["normalize_result"]
    payload.update(output_type_name="String", input_signature=[
        {"name": name, "type_name": "Int", "required": True, "transport_key": name}
        for name in ("a-b", "a_b")])
    path = tmp_path / "collision-adapter.json"
    path.write_text(json.dumps({"emit": payload}))
    return _parse_command_boundaries_manifest(json.loads(path.read_text()), manifest_path=path) | _commands(tmp_path, ("one", "two"))


@pytest.mark.parametrize("certified", [False, True])
@pytest.mark.parametrize("fields", [("a-b", "a_b"), ("a_b", "a-b")])
def test_colliding_input_names_keep_distinct_ordered_binders(tmp_path, certified, fields):
    from orchestrator.workflow_lisp.wcc.model import WccNameAtom, WccPureOp

    offsets = {"a-b": 1, "a_b": 2}
    inputs = ' '.join(f'({name} (+ n {offsets[name]}))' for name in fields)
    mode = ':adapter emit' if certified else ':argv ("python" "emit.py")'
    source = _source(f'(command-result emit {mode} :inputs ({inputs}) :returns String)', params='(n Int)')
    body = _compile_and_elaborate(tmp_path, source=source, commands=_colliding_input_commands(tmp_path, certified))
    bindings = _let_chain(body)[:-1]
    assert len(bindings) == 2
    assert all(isinstance(binding.bound_value, WccPureOp) for binding in bindings)
    assert [binding.bound_value.args[-1].value for binding in bindings] == [offsets[name] for name in fields]
    assert len({binding.bound_name for binding in bindings}) == 2
    inputs = _perform(body).operation_payload["adapter_inputs"]
    assert tuple(name for name, _ in inputs) == fields
    assert all(isinstance(value, WccNameAtom) for _, value in inputs)
    assert [value.name for _, value in inputs] == [binding.bound_name for binding in bindings]


def _assert_effect_document_references(body, bindings, calls, aliases, fields):
    assert len(calls) == len(aliases) == 2
    assert len({binding.bound_name for binding in bindings}) == 4
    assert [alias.bound_value.name for alias in aliases] == [call.bound_name for call in calls]
    inputs = _perform(body).operation_payload["adapter_inputs"]
    assert tuple(name for name, _ in inputs) == fields
    assert [value.name for _, value in inputs] == [alias.bound_name for alias in aliases]


@pytest.mark.parametrize("certified", [False, True])
@pytest.mark.parametrize("fields", [("a-b", "a_b"), ("a_b", "a-b")])
def test_colliding_effect_inputs_keep_each_producer_once(tmp_path, certified, fields):
    from orchestrator.workflow_lisp.wcc.model import WccCall, WccNameAtom

    producers = {"a-b": "one", "a_b": "two"}
    declarations = '''(defproc one () -> Int :effects ((uses-command one)) :lowering inline
      (command-result one :argv ("python" "one.py") :returns Int))
      (defproc two () -> Int :effects ((uses-command two)) :lowering inline
      (command-result two :argv ("python" "two.py") :returns Int))'''
    inputs = ' '.join(f'({name} ({producers[name]}))' for name in fields)
    mode = ':adapter emit' if certified else ':argv ("python" "emit.py")'
    source = _source(f'(command-result emit {mode} :inputs ({inputs}) :returns String)', declarations=declarations)
    body = _compile_and_elaborate(tmp_path, source=source, commands=_colliding_input_commands(tmp_path, certified))
    bindings = _let_chain(body)[:-1]
    calls = [binding for binding in bindings if isinstance(binding.bound_value, WccCall)]
    aliases = [binding for binding in bindings if isinstance(binding.bound_value, WccNameAtom)]
    assert [binding.bound_value.callee_name.rsplit("::", 1)[-1] for binding in calls] == [producers[name] for name in fields]
    _assert_effect_document_references(body, bindings, calls, aliases, fields)


@pytest.mark.parametrize("certified", [False, True])
def test_noncolliding_input_binder_identities_are_preserved(tmp_path, certified):
    mode = ':adapter emit' if certified else ':argv ("python" "emit.py")'
    commands = _adapter_commands(tmp_path, "Int") if certified else _commands(tmp_path)
    source = _source(f'(command-result emit {mode} :inputs ((optional (+ n 1)) (payload (+ n 2))) :returns String)', params='(n Int)')
    body = _compile_and_elaborate(tmp_path, source=source, commands=commands)
    names = [binding.bound_name for binding in _let_chain(body)[:-1]]
    assert names == [
        "__wcc_effect_command_adapter_input_optional_3ebbb70c6972c95e",
        "__wcc_effect_command_adapter_input_payload_3ebbb70c6972c95e",
    ]
    assert [value.name for _, value in _perform(body).operation_payload["adapter_inputs"]] == names
