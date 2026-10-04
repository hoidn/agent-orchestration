"""Source-owned command plans, interfaces and closed artifact certificates."""

from dataclasses import fields, is_dataclass

import pytest

from orchestrator.workflow_lisp.closed.build import Builder, build_closed_program
from orchestrator.workflow_lisp.closed.command_templates import elaborate_command_scopes
from orchestrator.workflow_lisp.closed.frontend import compile_typed_program, workflow_catalog_for
from orchestrator.workflow_lisp.closed.sites import _ast_nodes
from orchestrator.workflow_lisp.command_boundaries import ExternalToolBinding
from orchestrator.workflow_lisp.lowering.command_control_summary import ControlFacts
from orchestrator.workflow_lisp.procedures import ProcedureCatalog
from orchestrator.workflow_lisp.wcc.anf import normalize_wcc_body_to_anf
from orchestrator.workflow_lisp.wcc.elaborate import elaborate_typed_workflow_body
from orchestrator.workflow_lisp.wcc.model import WCC_M4_ROUTE_SCHEMA_VERSION, WccCall, WccPerform, WccRecJoin
from tests.workflow_lisp_closed_program_helpers import install


def _compile(tmp_path, body, *, params="", declarations="", returns="Int"):
    source = (
        '(workflow-lisp (:language "0.1") (:target-dsl "TARGET") '
        '(defmodule cp/transport) (export run) '
        + declarations + f' (defworkflow run ({params}) -> {returns} {body}))'
    )
    path = install(tmp_path, source)
    return compile_typed_program(
        path, entry_workflow="cp/transport::run", source_roots=(tmp_path,),
        workspace_root=tmp_path,
        command_boundaries={"echo": ExternalToolBinding(
            name="echo", stable_command=("python", "probe.py"), closure=("probe.py",))},
    )


def _command(argument):
    return f'(command-result echo :argv ("python" "probe.py" {argument}) :returns Int)'


def _commands(tree):
    bodies = [tree["body"], *(row["body"] for row in tree["definitions"].values())]
    return [node for body in bodies for node in _ast_nodes(body)
        if node.get("k") == "perform" and node.get("class") == "command"]


def _assert_root(value, wire):
    assert set(value) <= {"k", "n", "@"}
    assert (value["k"], value["n"]) == ("name", wire)


def _scope_inputs(program, builder):
    entry = program.entry
    owner = entry.definition.name
    type_env = program.workflow_type_env(owner)
    values = dict(entry.signature.params)
    inputs = dict(owner_name=owner, type_env=type_env, value_env=values,
        workflow_return_types=builder._workflow_return_types_for(program, owner),
        procedure_return_types=builder.procedure_return_types,
        resolved_procedures_by_name=program.procedures,
        procedure_type_envs=program.procedure_type_envs,
        route_schema_version=WCC_M4_ROUTE_SCHEMA_VERSION, closed_program=True)
    facts = ControlFacts(signature=entry.signature, type_env=type_env,
        local_type_bindings=values, typed_procedures=program.procedures,
        workflow_catalog=workflow_catalog_for(program, owner),
        workflows_by_name=program.workflows,
        procedure_catalog=ProcedureCatalog(
            signatures_by_name={name: row.signature for name, row in program.procedures.items()},
            definitions_by_name={name: row.definition for name, row in program.procedures.items()},
            call_graph={}),
        procedure_type_envs=program.procedure_type_envs, workflow_name=owner,
        procedure_owners=builder.procedure_owners,
        base_workflow_return_types=builder.workflow_return_types)
    return inputs, facts


def _declaration_resolver(program, builder):
    from orchestrator.workflow_lisp.closed.names import _callable_header

    def resolve(call):
        if isinstance(call, WccCall):
            selected, source = builder.procedure_owners[call.specialized_callee_name or call.callee_name]
        else:
            _, selected, source = builder._resolve_workflow_target(
                program, program.entry.definition.name, call.target_name)
        return list(_callable_header(selected, typed=source)[:3])

    return resolve


def _walk_wcc(node):
    yield node
    if is_dataclass(node):
        children = (getattr(node, field.name) for field in fields(node))
    elif isinstance(node, dict):
        children = node.values()
    elif isinstance(node, (tuple, list)):
        children = node
    else:
        return
    for child in children:
        yield from _walk_wcc(child)


def _authorized_field_value(node, field):
    value = getattr(node, field.name)
    if isinstance(node, WccPerform) and field.name == "operation_payload" and isinstance(value, dict):
        return {key: child for key, child in value.items() if key != "argv_transport"}
    return value


def _without_authorized_annotations(node):
    if is_dataclass(node):
        rows = []
        for field in fields(node):
            if field.name == "command_scope":
                continue
            value = _authorized_field_value(node, field)
            rows.append((field.name, _without_authorized_annotations(value)))
        return type(node), tuple(rows)
    if isinstance(node, dict):
        return tuple((key, _without_authorized_annotations(value)) for key, value in node.items())
    if isinstance(node, (tuple, list)):
        return tuple(_without_authorized_annotations(value) for value in node)
    return node


def _planned(program):
    builder = Builder(program)
    inputs, facts = _scope_inputs(program, builder)
    annotated = elaborate_command_scopes(program.entry.typed_body, **inputs,
        incoming_command_facts=facts, producer_lowering_schema=program.producer_lowering_schema,
        include_command_plans=True, source_program=program,
        command_bindings=builder._command_bindings(program,
            builder._module_for_owner(program, program.entry.definition.name))[0])
    return annotated, [node for node in _walk_wcc(annotated)
        if isinstance(node, WccPerform) and node.perform_kind == "command_result"]


def test_actual_closed_command_has_materialization_plans_and_native_whole_root(tmp_path):
    program = _compile(tmp_path, _command(
        'true (let* ((x true)) x) (if true true false) (let* ((s "${inputs.n}")) s)'),
        params="(n Int)")
    closed = build_closed_program(program)
    (command,) = _commands(closed.tree)
    plans = command["argv_transport"]
    assert [row["kind"] for row in plans] == ["template", "template", "value", "template"]
    assert plans[:2] == [{"kind": "template", "parts": [{"kind": "text", "text": "True"}]}] * 2
    native_wire = closed.tree["params"][0][0]
    assert closed.tree["command_params"] == [["n", 0]]
    root = plans[3]["parts"][0]["value"]
    _assert_root(root, native_wire)
    assert plans[3] == {"kind": "template", "parts": [{
        "kind": "slot", "name": ["input", "n", "n"], "path": [], "filters": [],
        "value": root,
    }]}
    assert len(command["argv"]) == len(plans) == 4


def test_native_input_root_survives_a_differently_typed_lexical_shadow(tmp_path):
    program = _compile(tmp_path,
        '(let* ((n "shadow")) ' + _command('"${inputs.n}" n') + ')', params="(n Int)")
    closed = build_closed_program(program)
    (command,) = _commands(closed.tree)
    slot = command["argv_transport"][0]["parts"][0]
    _assert_root(slot["value"], closed.tree["params"][0][0])
    assert command["argv_transport"][1] == {
        "kind": "template", "parts": [{"kind": "text", "text": "shadow"}]}
    assert closed.tree["command_params"] == [["n", 0]]


@pytest.mark.parametrize("argument,expected", [
    ("text", {"kind": "value"}),
    ('"${inputs.absent}"', {"kind": "template", "parts": [{
        "kind": "missing", "expression": "inputs.absent"}]}),
])
def test_runtime_string_and_missing_lookup_do_not_capture_dummy_roots(tmp_path, argument, expected):
    program = _compile(tmp_path, _command(argument), params="(text String)")
    closed = build_closed_program(program)
    (command,) = _commands(closed.tree)
    assert command["argv_transport"] == [expected]
    assert closed.tree.get("command_params", []) == []
    if expected["kind"] == "template":
        assert closed.tree["command_params"] == []


def test_input_union_slot_keeps_whole_root_without_universal_field(tmp_path):
    program = _compile(tmp_path, _command('"${inputs.choice__i}"'),
        params="(choice Choice)", declarations="(defunion Choice (A (i Int)) (B))")
    closed = build_closed_program(program)
    (command,) = _commands(closed.tree)
    slot = command["argv_transport"][0]["parts"][0]
    assert slot["name"] == ["input", "choice", "choice__i"]
    assert slot["path"] == []
    _assert_root(slot["value"], closed.tree["params"][0][0])
    assert closed.tree["params"][0][1]["kind"] == "union"
    assert closed.tree["command_params"] == [["choice", 0]]


def test_command_relations_visit_argv_then_slots_then_external_document(tmp_path):
    from copy import deepcopy
    from orchestrator.workflow_lisp.closed.check import _Checker
    from orchestrator.workflow_lisp.closed.sites import _effect_value_children

    program = _compile(tmp_path, _command('"${inputs.n}"'), params="(n Int)")
    closed = build_closed_program(program)
    command = deepcopy(_commands(closed.tree)[0])
    slot = command["argv_transport"][0]["parts"][0]["value"]
    # External documents share the ordered value walk with argv and slots.
    # The traversal exposes every lane independently of its binding kind.
    document = deepcopy(command["argv"][0])
    command["document"] = [["value", document]]
    expected = [*command["argv"], slot, document]
    assert _effect_value_children(command) == expected
    assert _Checker(closed.tree)._effect_children(command) == expected


@pytest.mark.parametrize("tamper", ["other-root", "invented-wire", "leaf-root",
    "wrong-root-descriptor", "extra-annotation", "hidden-effect"])
def test_source_free_command_readback_rejects_whole_root_and_projection_tampering(tmp_path, tamper):
    from copy import deepcopy
    from orchestrator.workflow_lisp.closed.program import ClosedProgram, ClosedProgramInvalid, program_digest

    program = _compile(tmp_path, _command('"${inputs.choice__i}"'),
        params="(choice Choice) (other Choice) (leaf Int)",
        declarations="(defunion Choice (A (i Int)) (B))")
    closed = build_closed_program(program)
    assert ClosedProgram.from_artifact(closed.artifact()).tree == closed.tree
    tree = deepcopy(closed.tree)
    command = _commands(tree)[0]
    slot = command["argv_transport"][0]["parts"][0]
    if tamper == "other-root":
        slot["value"]["n"] = tree["params"][1][0]
    elif tamper == "invented-wire":
        slot["name"][2] = "choice__absent"
    elif tamper == "leaf-root":
        slot["value"] = {"k": "field", "base": slot["value"], "path": ["i"]}
    elif tamper == "wrong-root-descriptor":
        slot["value"]["n"] = tree["params"][2][0]
    elif tamper == "extra-annotation":
        slot["annotation"] = "unexpected"
    else:
        slot["value"] = deepcopy(command)
    altered = ClosedProgram(tree=tree, sites=closed.sites, digest=program_digest(tree))
    rule = "effect_in_value" if tamper == "hidden-effect" else "command_transport"
    with pytest.raises(ClosedProgramInvalid, match=rule):
        ClosedProgram.from_artifact(altered.artifact())


def test_plans_checkpoint_preserves_neutral_anf_and_its_cached_owner(tmp_path):
    program = _compile(tmp_path, _command(
        '(if flag "${inputs.n}" "other") (let* ((alias "${inputs.n}")) alias)'),
        params="(n Int) (flag Bool)")
    builder = Builder(program)
    inputs, facts = _scope_inputs(program, builder)
    neutral = builder._workflow_wcc_body(program.entry, program)
    before = _without_authorized_annotations(neutral)
    annotated = elaborate_command_scopes(program.entry.typed_body, **inputs,
        incoming_command_facts=facts, producer_lowering_schema=program.producer_lowering_schema,
        include_command_plans=True, source_program=program,
        command_bindings=builder._command_bindings(program,
            builder._module_for_owner(program, program.entry.definition.name))[0])
    (perform,) = [node for node in _walk_wcc(annotated)
        if isinstance(node, WccPerform) and node.perform_kind == "command_result"]
    assert [row["kind"] for row in perform.operation_payload["argv_transport"]] == ["value", "template"]
    assert _without_authorized_annotations(annotated) == before
    assert normalize_wcc_body_to_anf(annotated) == annotated
    assert builder._workflow_wcc_body(program.entry, program) is neutral
    assert _without_authorized_annotations(neutral) == before
    ordinary = normalize_wcc_body_to_anf(elaborate_typed_workflow_body(program.entry.typed_body, **inputs))
    assert ordinary == neutral


def test_plans_checkpoint_uses_selected_binding_fact_and_original_native_root(tmp_path):
    program = _compile(tmp_path,
        '(let* ((n "shadow")) ' + _command(
        'true (let* ((x true)) x) (if true true false) "${inputs.n}" n') + ')',
        params="(n Int)")
    _, (command,) = _planned(program)
    plans = command.operation_payload["argv_transport"]
    assert [row["kind"] for row in plans] == ["template", "template", "value", "template", "template"]
    assert [plans[index]["parts"] for index in (0, 1, 4)] == [
        [{"kind": "text", "text": text}] for text in ("True", "True", "shadow")]
    root = plans[3]["parts"][0]["value"]
    assert root.name == "n"
    assert root.metadata.type_ref == dict(program.entry.signature.params)["n"]


def test_plans_checkpoint_union_row_keeps_whole_checked_root(tmp_path):
    program = _compile(tmp_path, _command('"${inputs.choice__i}"'),
        params="(choice Choice)", declarations="(defunion Choice (A (i Int)) (B))")
    _, (command,) = _planned(program)
    slot = command.operation_payload["argv_transport"][0]["parts"][0]
    assert slot["name"] == ["input", "choice", "choice__i"]
    assert slot["value"].metadata.type_ref == dict(program.entry.signature.params)["choice"]
    assert slot["value"].name == "choice"


def test_plans_checkpoint_loop_index_comes_from_body_owner(tmp_path):
    program = _compile(tmp_path,
        '(loop/recur :max 1 :state 0 (fn (state) '
        '(let* ((result ' + _command('"${loop.index}"') + ')) (done result))))')
    annotated, (command,) = _planned(program)
    slot = command.operation_payload["argv_transport"][0]["parts"][0]
    assert slot["kind"] == "slot"
    assert slot["name"] == ["loop-index"]
    assert slot["value"].metadata.type_ref.name == "Int"
    assert _without_authorized_annotations(annotated) == _without_authorized_annotations(
        normalize_wcc_body_to_anf(elaborate_typed_workflow_body(
            program.entry.typed_body, **_scope_inputs(program, Builder(program))[0])))


def _command_index_names(commands):
    return {command.operation_payload["argv_transport"][0]["parts"][0]["value"].name
        for command in commands}


def test_nested_loop_index_names_survive_actual_state_binder_hygiene(tmp_path):
    from orchestrator.workflow_lisp.closed.command_templates import command_loop_index_name
    from orchestrator.workflow_lisp.wcc.use_site_scope import rename_capturing_binders

    inner = '(loop/recur :max 1 :state 0 (fn (state) (let* ((result ' + _command('"${loop.index}"') + ')) (done result))))'
    program = _compile(tmp_path, '(loop/recur :max 1 :state 0 (fn (state) '
        '(let* ((inner ' + inner + ') (result ' + _command('"${loop.index}"') + ')) (done result))))')
    annotated, commands = _planned(program)
    loops = [node for node in _walk_wcc(annotated) if isinstance(node, WccRecJoin)]
    expected = {command_loop_index_name(loop.loop_name) for loop in loops}
    assert len(expected) == len(loops) == 2
    assert _command_index_names(commands) == expected
    moved, _ = rename_capturing_binders(annotated, live=frozenset({"state"}))
    moved_loops = [node for node in _walk_wcc(moved) if isinstance(node, WccRecJoin)]
    assert all(loop.params[0].name != "state" for loop in moved_loops)
    assert {command_loop_index_name(loop.loop_name) for loop in moved_loops} == expected
    moved_commands = [node for node in _walk_wcc(moved)
        if isinstance(node, WccPerform) and node.perform_kind == "command_result"]
    assert _command_index_names(moved_commands) == expected
    neutral = normalize_wcc_body_to_anf(elaborate_typed_workflow_body(
        program.entry.typed_body, **_scope_inputs(program, Builder(program))[0]))
    moved_neutral, _ = rename_capturing_binders(neutral, live=frozenset({"state"}))
    assert _without_authorized_annotations(moved) == _without_authorized_annotations(moved_neutral)
    assert normalize_wcc_body_to_anf(moved) == moved


@pytest.mark.parametrize("call_kind", ("procedure", "workflow"))
def test_call_preparation_consumes_real_alias_facts_after_operand_normalization(tmp_path, call_kind):
    if call_kind == "procedure":
        declaration = '(defproc helper ((flag Bool)) -> Int '
        declaration += ':effects ((uses-command echo)) :lowering inline ' + _command('flag') + ')'
        first, second = '(helper alias)', '(helper materialized)'
    else:
        declaration = '(defworkflow helper ((flag Bool)) -> Int ' + _command('flag') + ')'
        first, second = '(call helper :flag alias)', '(call helper :flag materialized)'
    program = _compile(tmp_path,
        '(let* ((alias true) (first ' + first + ') '
        '(materialized (if true true false))) ' + second + ')', declarations=declaration)
    builder = Builder(program)
    inputs, facts = _scope_inputs(program, builder)
    observed = []

    def prepare(selector, expr, call, context, actual_values):
        operands = call.args if isinstance(call, WccCall) else tuple(value for _, value in call.keyword_args)
        observed.append((getattr(actual_values[0], "value", None), operands[0].name, selector))

    annotated = elaborate_command_scopes(program.entry.typed_body, **inputs,
        incoming_command_facts=facts, producer_lowering_schema=program.producer_lowering_schema,
        include_command_plans=True, source_program=program,
        command_bindings=builder._command_bindings(program, program.entry_module)[0],
        call_preparator=prepare, call_declaration_identity=_declaration_resolver(program, builder))
    assert len(observed) == 2
    did = ["cp/transport", call_kind, "helper"]
    assert observed == [(None, "materialized", (did, 1)), (True, "alias", (did, 0))]
    calls = [node for node in _walk_wcc(annotated)
        if isinstance(node, WccCall)
        or isinstance(node, WccPerform) and node.perform_kind == "workflow_call"]
    assert [(node.args if isinstance(node, WccCall) else tuple(value for _, value in node.keyword_args))[0].name
        for node in calls] == ["alias", "materialized"]
    neutral = normalize_wcc_body_to_anf(elaborate_typed_workflow_body(
        program.entry.typed_body, **inputs))
    assert _without_authorized_annotations(annotated) == _without_authorized_annotations(neutral)
    assert not builder.definitions and not builder.run_ref_producers
    assert not builder.emitted_descriptors and not builder.generated_result_contract_requests
    assert not builder.boundary_requests


def _observe_call_selectors(program):
    from orchestrator.workflow_lisp.closed.command_templates import command_call_occurrences

    builder = Builder(program)
    inputs, facts = _scope_inputs(program, builder)
    observed = []
    resolver = _declaration_resolver(program, builder)

    def prepare(selector, expr, call, context, actual_values):
        observed.append(selector)

    annotated = elaborate_command_scopes(program.entry.typed_body, **inputs,
        incoming_command_facts=facts, producer_lowering_schema=program.producer_lowering_schema,
        call_preparator=prepare, call_declaration_identity=resolver)
    neutral = normalize_wcc_body_to_anf(elaborate_typed_workflow_body(program.entry.typed_body, **inputs))
    inventory = command_call_occurrences(neutral, resolver)
    assert inventory == command_call_occurrences(annotated, resolver)
    assert len(observed) == len(inventory)
    assert sorted(observed) == sorted(inventory.values())
    assert _without_authorized_annotations(annotated) == _without_authorized_annotations(neutral)
    assert normalize_wcc_body_to_anf(annotated) == annotated
    return inventory


def _integer_helper(name="helper"):
    return ('(defproc ' + name + ' ((n Int)) -> Int :effects ((uses-command echo)) '
        ':lowering inline ' + _command('n') + ')')


def test_identical_calls_and_other_declarations_keep_original_occurrences(tmp_path):
    program = _compile(tmp_path,
        '(let* ((first (helper n)) (middle (other n))) (helper n))',
        params="(n Int)", declarations=_integer_helper() + _integer_helper("other"))
    inventory = _observe_call_selectors(program)
    assert list(inventory.values()) == [
        (["cp/transport", "procedure", "helper"], 0),
        (["cp/transport", "procedure", "other"], 0),
        (["cp/transport", "procedure", "helper"], 1)]


def test_nested_equal_arm_binders_keep_complete_variant_call_coordinates(tmp_path):
    program = _compile(tmp_path,
        '(match choice ((A same) (match other ((A same) (helper same.i)) '
        '((B same) (helper same.i)))) ((B same) (match other '
        '((A same) (helper same.i)) ((B same) (helper same.i)))))',
        params="(choice Choice) (other Choice)", declarations=
            '(defunion Choice (A (i Int)) (B (i Int)))' + _integer_helper())
    inventory = _observe_call_selectors(program)
    assert {coordinate[2] for coordinate in inventory} == {("A", "A"), ("A", "B"), ("B", "A"), ("B", "B")}
    assert len({coordinate[:2] for coordinate in inventory}) < len(inventory) == 4
    assert [selector[1] for selector in inventory.values()] == [0, 1, 2, 3]


def test_call_coordinates_cover_if_loop_and_argument_join_owners(tmp_path):
    program = _compile(tmp_path,
        '(loop/recur :max 1 :state 0 :on-exhausted (+ state 1) (fn (state) '
        '(if flag (let* ((result (helper (match choice ((A same) same.i) '
        '((B same) same.i))))) (done result)) (done (helper state)))))',
        params="(flag Bool) (choice Choice)",
        declarations='(defunion Choice (A (i Int)) (B (i Int)))' + _integer_helper())
    inventory = _observe_call_selectors(program)
    assert len(inventory) == 2
    assert list(inventory.values()) == [
        (["cp/transport", "procedure", "helper"], 0),
        (["cp/transport", "procedure", "helper"], 1)]



def test_command_interface_projects_checked_native_and_missing_lookup_choices(tmp_path):
    from orchestrator.workflow_lisp.closed.command_interfaces import command_interface, command_interface_digest
    from orchestrator.workflow_lisp.closed.names import canonical_type_descriptor
    from orchestrator.workflow_lisp.closed.program import _canonical_json
    import hashlib

    program = _compile(tmp_path, _command('"${inputs.n} ${inputs.absent}"'), params="(n Int)")
    body, _ = _planned(program)
    descriptor = canonical_type_descriptor(dict(program.entry.signature.params)["n"], typed=program)
    native = [["n", 0, descriptor]]
    interface = command_interface(body, native_rows=native, command_capture_rows=[],
        child_interfaces={}, call_declaration_identity=_declaration_resolver(program, Builder(program)))
    assert interface == {"native": native, "captures": [], "decisions": [
        ["arg", 0, 0, ["template", [["input", ["native", "n"], "n"], ["missing"]]]]]}
    assert command_interface_digest(interface) == hashlib.sha256(_canonical_json(interface).encode()).hexdigest()


def test_command_interface_derives_loop_origin_from_its_actual_body_binder(tmp_path):
    from orchestrator.workflow_lisp.closed.command_interfaces import command_interface

    program = _compile(tmp_path,
        '(loop/recur :max 1 :state 0 (fn (state) '
        '(let* ((result ' + _command('"${loop.index}"') + ')) (done result))))')
    body, _ = _planned(program)
    interface = command_interface(body, native_rows=[], command_capture_rows=[],
        child_interfaces={}, call_declaration_identity=_declaration_resolver(program, Builder(program)))
    assert interface["decisions"] == [["arg", 0, 0,
        ["template", [["loop-index", ["loop", 0]]]]]]


def test_command_interface_reads_arm_root_and_stops_enclosing_loop_index(tmp_path):
    from orchestrator.workflow_lisp.closed.command_interfaces import command_interface

    match = '(match choice ((A a) (if flag '
    match += _command('"${inputs.a__i}" a.i "${loop.index}"') + ' 1)) ((B b) 2))'
    program = _compile(tmp_path,
        '(loop/recur :max 1 :state 0 :on-exhausted 0 (fn (state) '
        '(let* ((result ' + match + ')) (done result))))',
        params="(choice Choice) (flag Bool)",
        declarations='(defunion Choice (A (i Int)) (B (i Int)))')
    body, _ = _planned(program)
    interface = command_interface(body, native_rows=[], command_capture_rows=[],
        child_interfaces={}, call_declaration_identity=_declaration_resolver(program, Builder(program)))
    assert interface["decisions"] == [
        ["arm", 0, "A", "reset"],
        ["arg", 0, 0, ["template", [["input", ["arm", 0, "A", "a"], "a__i"]]]],
        ["arg", 0, 1, ["value"]], ["arg", 0, 2, ["template", [["missing"]]]]]
