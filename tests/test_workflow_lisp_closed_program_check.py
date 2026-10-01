from __future__ import annotations

import base64
from copy import deepcopy
from hashlib import sha256
import json

import pytest

from orchestrator.workflow_lisp.closed import EVALUATED_EXECUTION_MIN_TARGET_DSL_VERSION
from orchestrator.workflow_lisp.closed.check import CheckedFormError, validate
from orchestrator.workflow_lisp.closed.names import canonical_callee_name_from_key
from orchestrator.workflow_lisp.closed.names import canonical_run_ref_signature
from orchestrator.workflow_lisp.closed.names import key_type_descriptor
from orchestrator.workflow_lisp.closed.names import run_ref_type_dependencies
from orchestrator.workflow_lisp.closed.sites import assign_sites
from orchestrator.workflow.type_descriptor import compiled_boundary_rows
from orchestrator.workflow.pure_expr import canonical_json_for_pure_value
from orchestrator.workflow.run_ref.config import (
    PathProgram,
    ReferenceBinding,
    RunRefInput,
    build_run_ref_static_config,
    encode_run_ref_static_config,
)
from orchestrator.workflow.run_ref.contracts import canonical_sha256
from orchestrator.workflow.run_ref.source import SourceRequest
from orchestrator.workflow.run_ref.result_contract import (
    RUN_REF_RESULT_CONTRACT_SCHEMA,
    _accounting_descriptor,
    _workspace_delta_descriptor,
)


INT = {"kind": "primitive", "name": "Int"}
BOOL = {"kind": "primitive", "name": "Bool"}


def _lit(value, descriptor=INT):
    return {"k": "lit", "v": value, "type": deepcopy(descriptor)}


def _halt(value=None):
    return {"k": "halt", "value": _lit(0) if value is None else value}


def _tree(body=None, *, result=INT):
    return {
        "schema": "workflow-lisp/closed-program/1",
        "representation": "table/1",
        "target": EVALUATED_EXECUTION_MIN_TARGET_DSL_VERSION,
        "entry": "workflow:sample::run",
        "params": [],
        "defaults": {},
        "result": deepcopy(result),
        "body": _halt() if body is None else body,
        "types": {},
        "configuration": {
            "commands": {},
            "providers": {},
            "prompts": {},
            "imports": {},
        },
        "definitions": {},
        "sites": [],
    }


def _rule(tree, rule):
    with pytest.raises(CheckedFormError) as excinfo:
        validate(tree)
    assert excinfo.value.rule == rule


def test_valid_typed_entry_tree_is_checked():
    validate(_tree())


def test_runtime_list_operator_record_and_injection_values_are_checked():
    list_int = {"kind": "list", "item": deepcopy(INT)}
    list_value = {"k": "list", "type": list_int, "items": [_lit(1), _lit(2)]}
    validate(_tree(_halt(list_value), result=list_int))

    add_payload = {
        "pure_expr_schema_version": 2,
        "result_type": deepcopy(INT),
        "bindings": {"a0": {"type": deepcopy(INT)}, "a1": {"type": deepcopy(INT)}},
        "expr": {
            "kind": "op",
            "operator": "+",
            "args": [
                {"kind": "binding", "name": "a0"},
                {"kind": "binding", "name": "a1"},
            ],
        },
    }
    operator = {
        "k": "op",
        "payload": add_payload,
        "args": [_lit(2), _lit(3)],
    }
    validate(_tree(_halt(operator)))

    record = _record("sample::Nested", [("items", list_int)])
    union = {
        "kind": "union",
        "name": "sample::Wrapped",
        "variants": [{"name": "Record", "fields": [{"name": "value", "type": record}]}],
    }
    nested_record = {
        "k": "record",
        "type": deepcopy(record),
        "fields": [["items", deepcopy(list_value)]],
    }
    injection = {
        "k": "inject",
        "type": deepcopy(union),
        "variant": "Record",
        "fields": [["value", nested_record]],
    }
    tree = _tree(_halt(injection), result=union)
    tree["types"] = {record["name"]: record, union["name"]: union}
    validate(tree)


def test_bool_literal_does_not_match_int():
    _rule(_tree(_halt(_lit(True))), "type_mismatch")


def test_unknown_primitives_are_rejected_in_runtime_and_key_types():
    unknown = {"kind": "primitive", "name": "DefinitelyNotAnORCPrimitive"}
    _rule(_tree(_halt(_lit("value", unknown)), result=unknown), "type_mismatch")

    key = ["sample", "procedure", "unknown", [], [], [], [], [], {"params": [unknown], "result": INT}]
    name = canonical_callee_name_from_key(key)
    tree = _tree()
    tree["definitions"] = {
        name: {
            "key": key,
            "params": [["value", deepcopy(unknown)]],
            "result": deepcopy(INT),
            "body": _halt(),
        }
    }
    _rule(tree, "definition_key")


@pytest.mark.parametrize(
    ("descriptor", "value"),
    [
        ({"kind": "primitive", "name": "Value"}, {"k": "perform", "site": "literal data"}),
        (
            {"kind": "list", "item": {"kind": "primitive", "name": "Value"}},
            [{"k": "perform", "site": "list data"}],
        ),
    ],
)
def test_runtime_value_literals_accept_json_objects_without_weakening_scalar_tags(descriptor, value):
    validate(_tree(_halt(_lit(value, descriptor)), result=descriptor))


def test_value_defaults_and_record_fields_use_json_value_coercion():
    value_type = {"kind": "primitive", "name": "Value"}
    record = _record("sample::Payload", [("payload", value_type)])
    tree = _tree(
        _halt({"k": "name", "n": "payload"}),
        result=value_type,
    )
    tree["params"] = [["payload", deepcopy(value_type)]]
    tree["defaults"] = {"payload": {"kind": "run-ref-result", "name": "data"}}
    tree["types"][record["name"]] = record
    validate(tree)

    record_value = {
        "k": "record",
        "type": record,
        "fields": [["payload", _lit({"kind": "run-ref-result", "name": "record data"}, value_type)]],
    }
    record_tree = _tree(_halt(record_value), result=record)
    record_tree["types"][record["name"]] = record
    validate(record_tree)


def test_private_nominal_use_must_match_its_registered_definition():
    registered = {
        "kind": "record",
        "name": "sample::Box",
        "fields": [{"name": "n", "type": INT}],
    }
    forged = {
        "kind": "record",
        "name": "sample::Box",
        "fields": [{"name": "n", "type": {"kind": "primitive", "name": "String"}}],
    }
    tree = _tree(_halt({"k": "record", "type": forged, "fields": [["n", _lit("x", forged["fields"][0]["type"])] ]}), result=forged)
    tree["types"] = {"sample::Box": registered}

    _rule(tree, "nominal_definition")


def test_perform_without_a_persisted_site_is_rejected():
    perform = {
        "k": "perform",
        "class": "command",
        "result": INT,
        "repeat": "rerun",
        "boundary": "missing",
        "command": ["python"],
        "closure": [],
        "contract": {"kind": "output", "payload": {}},
        "argv": [],
    }
    _rule(_tree({"k": "let", "name": "got", "value": perform, "body": _halt({"k": "name", "n": "got"})}), "site_missing")


@pytest.mark.parametrize("binder", ["%1", "same"])
def test_checker_keeps_effect_label_counts_separate_for_each_branch(binder):
    command_tree, command = _command_result_tree()
    leaf = lambda: {"k": "let", "name": binder, "value": deepcopy(command), "body": _halt()}
    tree = _tree(
        {
            "k": "if",
            "cond": _lit(True, BOOL),
            "then": leaf(),
            "else": leaf(),
        }
    )
    tree["configuration"]["commands"] = deepcopy(command_tree["configuration"]["commands"])
    tree["sites"] = [list(row) for row in assign_sites(tree)]

    validate(tree)

    label = "#1" if binder.startswith("%") else binder
    assert tree["sites"] == [
        [tree["entry"], f"then / {label}"],
        [tree["entry"], f"else / {label}"],
    ]


def _effectful_call_tree(*, effectful=True):
    command_tree, command = _command_result_tree()
    callee_key = [
        "sample", "procedure", "worker", [], [], [], [], [],
        {"params": [], "result": deepcopy(INT)},
    ]
    callee = canonical_callee_name_from_key(callee_key)
    call = {"k": "call", "callee": callee, "args": [], "type": deepcopy(INT)}
    entry = _tree({"k": "let", "name": "answer", "value": call, "body": _halt(_name("answer"))})
    definition_body = (
        {"k": "let", "name": "performed", "value": deepcopy(command), "body": _halt()}
        if effectful
        else _halt()
    )
    entry["configuration"]["commands"] = deepcopy(command_tree["configuration"]["commands"])
    entry["definitions"] = {
        callee: {
            "key": callee_key,
            "params": [],
            "result": deepcopy(INT),
            "body": definition_body,
        }
    }
    entry["sites"] = [list(row) for row in assign_sites(entry)]
    return entry, call


def test_effectful_call_frame_and_site_table_are_recomputed_as_bijections():
    tree, call = _effectful_call_tree()
    validate(tree)

    missing_frame, missing_call = _effectful_call_tree()
    del missing_call["frame"]
    _rule(missing_frame, "frame_missing")

    wrong_frame, wrong_call = _effectful_call_tree()
    wrong_call["frame"] += "/forged"
    _rule(wrong_frame, "frame_mismatch")

    missing_site, _ = _effectful_call_tree()
    missing_site["sites"].pop()
    _rule(missing_site, "site_table")

    extra_site, _ = _effectful_call_tree()
    extra_site["sites"].append(["procedure:sample::unreachable", "forged"])
    _rule(extra_site, "site_table")

    wrong_site, _ = _command_result_tree()
    wrong_site["body"]["value"]["site"] = "forged"
    _rule(wrong_site, "site_mismatch")


def test_three_case_arms_inside_a_loop_keep_distinct_frames_and_one_callee_site():
    command_tree, command = _command_result_tree()
    key = _callable_key("arms_in_loop")
    callee = canonical_callee_name_from_key(key)
    choice = {
        "kind": "union",
        "name": "sample::ArmChoice",
        "variants": [{"name": arm, "fields": []} for arm in ("First", "Second", "Third")],
    }
    arms = []
    for variant in ("First", "Second", "Third"):
        call = {"k": "call", "callee": callee, "args": [], "type": deepcopy(INT)}
        arms.append({
            "variant": variant,
            "bind": f"case_{variant.lower()}",
            "body": {
                "k": "let",
                "name": "%1",
                "value": call,
                "body": {"k": "jump", "join": "case_result", "args": [_name("%1")]},
            },
        })
    case_result = {
        "k": "join",
        "name": "case_result",
        "params": [["got", deepcopy(INT)]],
        "result": deepcopy(INT),
        "body": {"k": "case", "subject": _name("choice"), "arms": arms},
        "cont": {"k": "done", "value": _name("got")},
    }
    loop = _loop_body(
        case_result,
        exhausted=_halt(_lit(0)),
    )
    tree = _tree(loop)
    tree["params"] = [["choice", deepcopy(choice)]]
    tree["types"] = {choice["name"]: choice}
    tree["definitions"] = {
        callee: {
            "key": key,
            "params": [],
            "result": deepcopy(INT),
            "body": {"k": "let", "name": "%1", "value": deepcopy(command), "body": _halt(_lit(0))},
        }
    }
    tree["configuration"]["commands"] = deepcopy(command_tree["configuration"]["commands"])
    tree["sites"] = [list(row) for row in assign_sites(tree)]

    validate(tree)

    calls = [arm["body"]["value"] for arm in arms]
    assert tree["sites"] == [[callee, "#1"]]
    assert [call["frame"] for call in calls] == [
        f"loop:state[*] / got / body / {variant} / #1={callee}"
        for variant in ("First", "Second", "Third")
    ]


def test_nested_block_and_join_sites_and_frames_are_checked_as_a_bijection():
    command_tree, command = _command_result_tree()
    key = _callable_key("nested_effect")
    callee = canonical_callee_name_from_key(key)
    call = {"k": "call", "callee": callee, "args": [], "type": deepcopy(INT)}
    join = {
        "k": "join",
        "name": "join_target",
        "params": [["answer", deepcopy(INT)]],
        "result": deepcopy(INT),
        "label": "answer-label",
        "body": {
            "k": "let", "name": "body_value", "label": "same",
            "value": deepcopy(call), "body": _halt(_lit(1)),
        },
        "cont": {
            "k": "let", "name": "continuation_value", "label": "same",
            "value": deepcopy(call), "body": _halt(_name("answer")),
        },
    }
    block = {
        "k": "block",
        "body": {
            "k": "let", "name": "block_value", "label": "same",
            "value": deepcopy(call), "body": _halt(_name("block_value")),
        },
    }
    tree = _tree({
        "k": "let", "name": "boxed", "value": block,
        "body": join,
    })
    tree["definitions"] = {
        callee: {
            "key": key,
            "params": [],
            "result": deepcopy(INT),
            "body": {"k": "let", "name": "performed", "value": deepcopy(command), "body": _halt(_lit(0))},
        }
    }
    tree["configuration"]["commands"] = deepcopy(command_tree["configuration"]["commands"])
    tree["sites"] = [list(row) for row in assign_sites(tree)]

    validate(tree)

    frames = [
        block["body"]["value"]["frame"],
        join["body"]["value"]["frame"],
        join["cont"]["value"]["frame"],
    ]
    assert tree["sites"] == [[callee, "performed"]]
    assert frames == [
        f"boxed / block / same={callee}",
        f"answer-label / body / same={callee}",
        f"same={callee}",
    ]


def test_single_node_rule_failures_include_source_location_and_duplicate_site():
    unknown = _tree({"k": "halt", "value": {"k": "mystery"}})
    _rule(unknown, "node_kind")

    hidden_effect = {"k": "perform", "class": "command", "result": deepcopy(INT), "repeat": "rerun"}
    _rule(_tree({"k": "halt", "value": hidden_effect}), "effect_in_value")

    invalid_payload = {
        "pure_expr_schema_version": 1,
        "result_type": deepcopy(INT),
        "expr": {"kind": "literal", "type": deepcopy(INT), "value": 1},
    }
    _rule(_tree(_halt({"k": "op", "payload": invalid_payload, "args": []})), "payload_invalid")

    unknown_callee = _tree({
        "k": "let",
        "name": "result",
        "value": {"k": "call", "callee": "procedure:sample::absent", "args": [], "type": deepcopy(INT)},
        "body": _halt(_name("result")),
    })
    _rule(unknown_callee, "callee_unknown")

    bad_record = _record("sample::Expected", [("value", INT)])
    missing_field = _tree(_halt({"k": "record", "type": bad_record, "fields": []}), result=bad_record)
    missing_field["types"] = {bad_record["name"]: bad_record}
    _rule(missing_field, "record_fields")

    loop = _loop_body({"k": "done", "value": _lit(0)})
    del loop["budget"]
    _rule(_tree(loop), "budget_missing")

    outer = _loop_body(
        _loop_body({"k": "continue", "loop": "outer", "args": [_name("state")]})
    )
    outer["name"] = "outer"
    outer["body"]["name"] = "inner"
    _rule(_tree(outer), "continue_target")

    with_location = _tree(_halt({"k": "name", "n": "absent", "@": {"span": "source.orc:12:4", "form": []}}))
    with pytest.raises(CheckedFormError) as excinfo:
        validate(with_location)
    assert (excinfo.value.rule, excinfo.value.location) == ("unbound_name", "source.orc:12:4")

    duplicate, first_effect = _command_result_tree()
    second_effect = deepcopy(first_effect)
    duplicate["body"] = {
        "k": "let", "name": "first", "value": first_effect,
        "body": {"k": "let", "name": "second", "value": second_effect, "body": _halt(_lit(0))},
    }
    duplicate["sites"] = [list(row) for row in assign_sites(duplicate)]
    second_effect["site"] = first_effect["site"]
    _rule(duplicate, "site_duplicate")

    extra_call_row, call = _effectful_call_tree()
    extra_call_row["sites"].append([extra_call_row["entry"], call["frame"]])
    _rule(extra_call_row, "site_table")

    changed_label, _ = _command_result_tree()
    changed_label["body"]["label"] = "renamed-without-site-update"
    _rule(changed_label, "site_mismatch")


@pytest.mark.parametrize("label", ["", None, 7])
def test_binding_labels_must_be_nonempty_strings(label):
    tree = _tree({
        "k": "let", "name": "value", "label": label, "value": _lit(1), "body": _halt(_name("value")),
    })
    _rule(tree, "binding_label")


def test_duplicate_parameter_names_are_rejected_before_scope_overwrite():
    tree = _tree(_halt(_name("value")))
    tree["params"] = [["value", deepcopy(INT)], ["value", deepcopy(INT)]]
    _rule(tree, "call_signature")


def test_non_binding_nodes_cannot_carry_labels_and_two_join_parameters_are_rejected():
    list_map = {
        "k": "list_map", "binder": "item", "source": _name("items"),
        "body": _name("item"), "type": {"kind": "list", "item": deepcopy(INT)}, "label": "bad",
    }
    tree = _tree(_halt(list_map), result=list_map["type"])
    tree["params"] = [["items", deepcopy(list_map["type"])]]
    _rule(tree, "node_shape")

    join = {
        "k": "join", "name": "target", "params": [["a", deepcopy(INT)], ["b", deepcopy(INT)]],
        "result": deepcopy(INT), "body": _halt(_lit(0)), "cont": _halt(_lit(0)),
    }
    _rule(_tree(join), "join_arity")

    transfer = {
        "k": "join", "name": "target", "params": [["answer", deepcopy(INT)]],
        "result": deepcopy(INT),
        "body": {"k": "jump", "join": "target", "args": []},
        "cont": _halt(_name("answer")),
    }
    _rule(_tree(transfer), "jump_arity")

    wrong_jump_type = deepcopy(transfer)
    wrong_jump_type["body"]["args"] = [_lit("wrong", {"kind": "primitive", "name": "String"})]
    _rule(_tree(wrong_jump_type), "type_mismatch")


def test_isolated_entry_default_value_and_control_type_facts_are_checked():
    string = {"kind": "primitive", "name": "String"}
    tree = _tree(_halt(_lit(0)), result=string)
    _rule(tree, "entry_result")

    defaulted = _tree(_halt(_name("count")))
    defaulted["params"] = [["count", deepcopy(INT)]]
    defaulted["defaults"] = {"count": "not an Int"}
    _rule(defaulted, "call_signature")

    source = {"kind": "list", "item": deepcopy(INT)}
    wrong_result = {"kind": "list", "item": deepcopy(string)}
    mapping = {
        "k": "list_map", "binder": "item", "source": _name("items"),
        "body": _name("item"), "type": wrong_result,
    }
    mapped = _tree(_halt(mapping), result=wrong_result)
    mapped["params"] = [["items", source]]
    _rule(mapped, "type_mismatch")

    nested = _record("sample::NestedValue", [("count", INT)])
    outer = _record("sample::OuterValue", [("nested", nested)])
    wrong_nested = {
        "k": "record", "type": deepcopy(nested),
        "fields": [["count", _lit("wrong", string)]],
    }
    nested_value = {
        "k": "record", "type": deepcopy(outer),
        "fields": [["nested", wrong_nested]],
    }
    tree = _tree(_halt(nested_value), result=outer)
    tree["types"] = {nested["name"]: nested, outer["name"]: outer}
    _rule(tree, "type_mismatch")

    union = {
        "kind": "union", "name": "sample::TypedInjection",
        "variants": [{"name": "Value", "fields": [{"name": "count", "type": deepcopy(INT)}]}],
    }
    bad_injection = {"k": "inject", "type": union, "variant": "Value", "fields": []}
    tree = _tree(_halt(bad_injection), result=union)
    tree["types"] = {union["name"]: union}
    _rule(tree, "record_fields")

    conditional = _tree({"k": "if", "cond": _lit(1), "then": _halt(_lit(1)), "else": _halt(_lit(2))})
    _rule(conditional, "type_mismatch")

    select = {
        "k": "select", "cond": _lit(True, BOOL),
        "then": {"prefix": [], "value": _lit(1)},
        "else": {"prefix": [], "value": _lit("one", string)},
    }
    _rule(_tree(_halt(select)), "type_mismatch")

    bad_select_condition = {
        "k": "select", "cond": _lit(1),
        "then": {"prefix": [], "value": _lit(1)},
        "else": {"prefix": [], "value": _lit(1)},
    }
    _rule(_tree(_halt(bad_select_condition)), "type_mismatch")

    block = {"k": "block", "body": _halt(_lit("wrong", string))}
    box = _record("sample::BlockResult", [("payload", INT)])
    boxed = {"k": "record", "type": box, "fields": [["payload", block]]}
    tree = _tree(_halt(boxed), result=box)
    tree["types"] = {box["name"]: box}
    _rule(tree, "type_mismatch")


def test_call_signature_and_loop_transfer_type_facts_are_independently_checked():
    string = {"kind": "primitive", "name": "String"}

    def caller(args, call_result=INT):
        key = [
            "sample", "procedure", "typed", [], [], [], [], [],
            {"params": [deepcopy(INT)], "result": deepcopy(INT)},
        ]
        callee = canonical_callee_name_from_key(key)
        call = {"k": "call", "callee": callee, "args": args, "type": deepcopy(call_result)}
        tree = _tree({"k": "let", "name": "answer", "value": call, "body": _halt(_name("answer"))})
        tree["definitions"] = {
            callee: {
                "key": key, "params": [["arg", deepcopy(INT)]], "result": deepcopy(INT),
                "body": _halt(_name("arg")),
            }
        }
        tree["sites"] = [list(row) for row in assign_sites(tree)]
        return tree

    _rule(caller([]), "call_signature")
    _rule(caller([_lit("wrong", string)]), "call_signature")
    _rule(caller([_lit(1)], string), "call_signature")

    loop = _loop_body(
        {"k": "done", "value": _lit(1)},
        result=string,
        exhausted=_halt(_lit("finished", string)),
    )
    _rule(_tree(loop, result=string), "type_mismatch")

    loop = _loop_body(
        {"k": "continue", "loop": "iteration", "args": [_lit("wrong", string)]},
        exhausted=_halt(_lit(0)),
    )
    _rule(_tree(loop), "type_mismatch")

    wrong_seed = _loop_body({"k": "done", "value": _lit(0)}, exhausted=_halt(_lit(0)))
    wrong_seed["init"] = _lit("not state", string)
    _rule(_tree(wrong_seed), "type_mismatch")

    wrong_state = _loop_body({"k": "done", "value": _lit(0)}, exhausted=_halt(_lit(0)))
    wrong_state["state_type"] = deepcopy(string)
    _rule(_tree(wrong_state), "type_mismatch")

    wrong_budget = _loop_body({"k": "done", "value": _lit(0)}, exhausted=_halt(_lit(0)))
    wrong_budget["budget"] = _lit(True, BOOL)
    _rule(_tree(wrong_budget), "type_mismatch")

    loop = _loop_body({"k": "done", "value": _lit(1)}, exhausted=_halt(_lit("wrong", string)))
    _rule(_tree(loop), "type_mismatch")


def test_pure_call_cannot_carry_an_effect_frame():
    tree, call = _effectful_call_tree(effectful=False)
    call["frame"] = "forged=procedure:sample::worker"
    _rule(tree, "frame_mismatch")


def test_checker_visits_every_call_edge_before_short_circuiting_effect_analysis():
    key = [
        "sample", "procedure", "recursive", [], [], [], [], [],
        {"params": [], "result": deepcopy(INT)},
    ]
    name = canonical_callee_name_from_key(key)
    recursive = {
        "k": "call",
        "callee": name,
        "args": [],
        "type": deepcopy(INT),
    }
    body = {"k": "let", "name": "again", "value": recursive, "body": _halt()}
    tree = _tree()
    tree["definitions"] = {
        name: {"key": key, "params": [], "result": deepcopy(INT), "body": body}
    }
    _rule(tree, "call_cycle")


def test_join_requires_one_result_parameter_before_indexing_its_label():
    tree = _tree(
        {
            "k": "join",
            "name": "join_target",
            "params": [],
            "result": INT,
            "body": _halt(),
            "cont": _halt(),
            "label": "result",
        }
    )

    _rule(tree, "join_arity")


def test_join_result_binder_is_only_in_scope_in_the_continuation():
    join = {
        "k": "join",
        "name": "target",
        "params": [["answer", deepcopy(INT)]],
        "result": deepcopy(INT),
        "body": _halt(_lit(7)),
        "cont": _halt({"k": "name", "n": "answer"}),
    }
    validate(_tree(join))

    join["body"] = _halt({"k": "name", "n": "answer"})
    join["cont"] = _halt(_lit(7))
    _rule(_tree(join), "unbound_name")


def test_loop_state_binder_is_available_in_the_exhaustion_branch():
    tree = _tree(
        {
            "k": "loop",
            "name": "again",
            "param": "state",
            "state_type": deepcopy(INT),
            "result": deepcopy(INT),
            "budget": _lit(1),
            "init": _lit(0),
            "body": {"k": "done", "value": {"k": "name", "n": "state"}},
            "exhausted": _halt({"k": "name", "n": "state"}),
            "code": None,
        }
    )
    validate(tree)


def _loop_body(body, *, result=INT, exhausted=None):
    return {
        "k": "loop",
        "name": "iteration",
        "param": "state",
        "state_type": deepcopy(INT),
        "result": deepcopy(result),
        "budget": _lit(1),
        "init": _lit(0),
        "body": body,
        "exhausted": exhausted,
        "code": None,
    }


def test_done_inside_join_body_targets_enclosing_loop_result():
    join = {
        "k": "join",
        "name": "local_join",
        "params": [["answer", deepcopy(INT)]],
        "result": deepcopy(INT),
        "body": {"k": "done", "value": _lit("done", {"kind": "primitive", "name": "String"})},
        "cont": {"k": "done", "value": _lit("continuation", {"kind": "primitive", "name": "String"})},
    }
    validate(_tree(_loop_body(join, result={"kind": "primitive", "name": "String"}), result={"kind": "primitive", "name": "String"}))


def test_join_local_jump_enters_its_continuation():
    join = {
        "k": "join",
        "name": "local_join",
        "params": [["answer", deepcopy(INT)]],
        "result": deepcopy(INT),
        "body": {"k": "jump", "join": "local_join", "args": [_lit(4)]},
        "cont": _halt(_name("answer")),
    }
    validate(_tree(join))


def test_inner_join_propagates_a_jump_to_its_enclosing_join():
    outer = {
        "k": "join",
        "name": "outer_join",
        "params": [["outer_answer", deepcopy(INT)]],
        "result": deepcopy(INT),
        "body": {
            "k": "join",
            "name": "inner_join",
            "params": [["inner_answer", deepcopy(INT)]],
            "result": deepcopy(INT),
            "body": {"k": "jump", "join": "outer_join", "args": [_lit(5)]},
            "cont": _halt(_name("inner_answer")),
        },
        "cont": _halt(_name("outer_answer")),
    }
    validate(_tree(outer))


def test_join_jump_can_continue_to_a_typed_loop_done():
    string = {"kind": "primitive", "name": "String"}
    join = {
        "k": "join",
        "name": "local_join",
        "params": [["answer", deepcopy(INT)]],
        "result": deepcopy(INT),
        "body": {"k": "jump", "join": "local_join", "args": [_lit(4)]},
        "cont": {"k": "done", "value": _lit("finished", string)},
    }
    validate(_tree(_loop_body(join, result=string), result=string))


def test_valid_value_and_control_forms_preserve_their_typed_scopes():
    string = {"kind": "primitive", "name": "String"}
    validate(_tree(_halt({"k": "context", "field": "run-id"}), result=string))

    selected = {
        "k": "select",
        "cond": _lit(True, BOOL),
        "then": {"prefix": [{"name": "picked", "value": _lit(1)}], "value": _name("picked")},
        "else": {"prefix": [{"name": "picked", "value": _lit(2)}], "value": _name("picked")},
    }
    validate(_tree(_halt(selected)))

    list_int = {"kind": "list", "item": deepcopy(INT)}
    list_map = {
        "k": "list_map",
        "binder": "element",
        "source": _name("values"),
        "body": _name("element"),
        "type": deepcopy(list_int),
    }
    list_tree = _tree(_halt(list_map), result=list_int)
    list_tree["params"] = [["values", deepcopy(list_int)]]
    validate(list_tree)

    local_block = {
        "k": "block",
        "body": {"k": "let", "name": "inside", "value": _lit(7), "body": _halt(_name("inside"))},
    }
    validate(_tree(_halt(local_block)))

    path = {
        "kind": "path",
        "name": "sample::OutputPath",
        "under": ".orchestrate/runs",
        "must_exist_target": False,
    }
    path_tree = _tree(
        _halt({"k": "path_join", "base": _name("root"), "child": _lit("phase", string), "type": path}),
        result=path,
    )
    path_tree["params"] = [["root", deepcopy(path)]]
    path_tree["types"] = {path["name"]: deepcopy(path)}
    validate(path_tree)

    choice = {
        "kind": "union",
        "name": "sample::MaybeValue",
        "variants": [
            {"name": "Some", "fields": [{"name": "value", "type": deepcopy(INT)}]},
            {"name": "None", "fields": []},
        ],
    }
    subject = {
        "k": "inject",
        "type": deepcopy(choice),
        "variant": "Some",
        "fields": [["value", _lit(3)]],
    }
    case = {
        "k": "case",
        "subject": subject,
        "arms": [
            {
                "variant": "Some",
                "bind": "some_case",
                "body": _halt({"k": "field", "base": _name("some_case"), "path": ["value"]}),
            },
            {"variant": "None", "bind": "none_case", "body": _halt(_lit(0))},
        ],
    }
    case_tree = _tree(case)
    case_tree["types"] = {choice["name"]: choice}
    validate(case_tree)

    loop = _loop_body(
        {"k": "continue", "loop": "iteration", "args": [_name("state")]},
        exhausted=_halt(_name("state")),
    )
    validate(_tree(loop))


@pytest.mark.parametrize(
    "loop_body",
    [
        _halt(_lit(1)),
        _loop_body({"k": "done", "value": _lit(1)}),
    ],
    ids=["halt-is-not-loop-control", "nested-loop-value-is-not-loop-control"],
)
def test_loop_body_cannot_implicitly_halt(loop_body):
    _rule(_tree(_loop_body(loop_body)), "loop_control")


def test_block_cannot_transfer_done_to_an_enclosing_loop():
    block = {"k": "block", "body": {"k": "done", "value": _lit(1)}}
    _rule(_tree(_loop_body({"k": "done", "value": block})), "block_control")


def test_loop_cannot_jump_to_a_join_outside_its_control_scope():
    outer = {
        "k": "join",
        "name": "outer_join",
        "params": [["answer", deepcopy(INT)]],
        "result": deepcopy(INT),
        "body": _loop_body({"k": "jump", "join": "outer_join", "args": [_lit(1)]}),
        "cont": _halt(_lit(2)),
    }
    _rule(_tree(outer), "jump_target")


def test_unmatched_union_fields_are_rejected_but_common_fields_remain_accessible():
    common = {
        "kind": "union",
        "name": "sample::Common",
        "variants": [
            {"name": "First", "fields": [{"name": "x", "type": deepcopy(INT)}]},
            {"name": "Second", "fields": [{"name": "x", "type": deepcopy(INT)}]},
        ],
    }
    value = {"k": "field", "base": {"k": "name", "n": "choice"}, "path": ["x"]}
    tree = _tree(_halt(value))
    tree["params"] = [["choice", deepcopy(common)]]
    tree["types"] = {common["name"]: deepcopy(common)}
    validate(tree)

    partial = deepcopy(common)
    partial["name"] = "sample::Partial"
    partial["variants"][1]["fields"] = []
    tree = _tree(_halt(value))
    tree["params"] = [["choice", partial]]
    tree["types"] = {partial["name"]: deepcopy(partial)}
    _rule(tree, "field_path")


def test_closed_union_field_access_requires_a_common_field():
    union = {
        "kind": "union",
        "name": "sample::ClosedPartial",
        "variants": [
            {"name": "First", "fields": [{"name": "x", "type": deepcopy(INT)}]},
            {"name": "Second", "fields": []},
        ],
    }
    literal = {
        "k": "field",
        "base": {
            "k": "inject",
            "type": deepcopy(union),
            "variant": "First",
            "fields": [["x", _lit(3)]],
        },
        "path": ["x"],
    }
    key = ["sample", "procedure", "probe", [], [], [], [["selected", deepcopy(INT), literal]], [], {"params": [], "result": deepcopy(INT)}]
    name = canonical_callee_name_from_key(key)
    tree = _tree()
    tree["types"] = {union["name"]: deepcopy(union)}
    tree["definitions"] = {name: {"key": key, "params": [], "result": deepcopy(INT), "body": _halt()}}
    tree["sites"] = [list(row) for row in assign_sites(tree)]
    _rule(tree, "definition_key")


def test_nonfinite_values_are_rejected_before_type_checking():
    _rule(_tree(_halt(_lit(float("nan")))), "nonfinite_json")


def test_callable_kind_is_always_part_of_the_base_name():
    procedure = ["sample", "procedure", "run", [], [], [], [], [], {"params": [], "result": INT}]
    workflow = ["sample", "workflow", "run", [], [], [], [], [], {"params": [], "result": INT}]

    assert canonical_callee_name_from_key(procedure) == "procedure:sample::run"
    assert canonical_callee_name_from_key(workflow) == "workflow:sample::run"


def test_local_and_specialized_names_hash_the_complete_canonical_key():
    local = [
        "sample",
        "procedure",
        {"owner": ["sample", "workflow", "run"], "name": "helper", "ordinal": 2},
        [],
        [],
        [],
        [],
        [],
        {"params": [], "result": INT},
    ]
    specialized = ["sample", "procedure", "run", [["T", INT]], [], [], [], [], {"params": [], "result": INT}]

    assert canonical_callee_name_from_key(local).startswith("procedure:sample::helper[")
    assert canonical_callee_name_from_key(specialized).startswith("procedure:sample::run[")
    assert canonical_callee_name_from_key(local) != canonical_callee_name_from_key(specialized)


def test_run_ref_signature_rejects_duplicate_input_names():
    result = {
        "schema": RUN_REF_RESULT_CONTRACT_SCHEMA,
        "envelope": {
            "kind": "record",
            "name": "RunRefResult$0000000000000000",
            "fields": [
                {"name": "value", "type": INT},
                {"name": "workspace_delta", "type": _workspace_delta_descriptor()},
                {"name": "accounting", "type": _accounting_descriptor()},
            ],
        },
    }

    with pytest.raises(ValueError, match="input names must be unique"):
        canonical_run_ref_signature(
            [("payload", INT), ("payload", INT)],
            result,
            run_ref_signatures={},
        )


def test_key_projection_preserves_phantom_applied_arguments_as_structural_signatures():
    generated = "RunRefResult$0123456789abcdef"
    signature = {
        "inputs": [],
        "result": {
            "schema": RUN_REF_RESULT_CONTRACT_SCHEMA,
            "envelope": {"kind": "record", "fields": []},
        },
    }
    descriptor = {
        "kind": "record",
        "name": f"entry::Wrapper[{generated}]",
        "fields": [{"name": "count", "type": INT}],
    }
    original = deepcopy(descriptor)

    projected = key_type_descriptor(descriptor, run_ref_signatures={generated: signature})

    assert projected["name"] == {
        "head": "entry::Wrapper",
        "args": [{"kind": "run-ref-result", "signature": signature}],
    }
    assert descriptor == original
    assert run_ref_type_dependencies(descriptor) == (generated,)


def test_runtime_applied_type_arguments_require_nominal_rows_and_run_ref_origins():
    known = _record("sample::Known", [("value", INT)])
    valid = {
        "kind": "union",
        "name": "sample::Wrap[sample::Known]",
        "variants": [{"name": "WRAP", "fields": [{"name": "value", "type": deepcopy(INT)}]}],
    }
    tree = _tree(_halt(_lit(0)))
    tree["params"] = [["wrapped", deepcopy(valid)]]
    tree["types"] = {known["name"]: known, valid["name"]: deepcopy(valid)}
    validate(tree)

    missing = deepcopy(valid)
    missing["name"] = "sample::Wrap[sample::Missing]"
    tree = _tree(_halt(_lit(0)))
    tree["params"] = [["wrapped", missing]]
    tree["types"] = {missing["name"]: deepcopy(missing)}
    _rule(tree, "nominal_definition")

    unproduced = deepcopy(valid)
    unproduced["name"] = "sample::Wrap[RunRefResult$ffffffffffffffff]"
    tree = _tree(_halt(_lit(0)))
    tree["params"] = [["wrapped", unproduced]]
    tree["types"] = {unproduced["name"]: deepcopy(unproduced)}
    _rule(tree, "run_ref_origin")

    generated, _ = _generated_result_pair()
    wrapped_generated = {
        "kind": "union",
        "name": f"sample::Wrap[{generated['name']}]",
        "variants": [{"name": "WRAP", "fields": [{"name": "value", "type": deepcopy(INT)}]}],
    }
    tree, _call, _, _ = _generated_boundary_tree(
        [("wrapped", wrapped_generated)],
        [("wrapped", deepcopy(wrapped_generated))],
        INT,
        INT,
    )
    validate(tree)


def test_runtime_applied_container_arguments_recurse_without_nominal_container_rows():
    known = _record("sample::KnownContainerItem", [("value", INT)])
    arguments = (
        "List[Int]",
        "Optional[Int]",
        "Map[String,Int]",
        "List[sample::KnownContainerItem]",
        "Map[String,List[sample::KnownContainerItem]]",
    )
    for argument in arguments:
        wrapped = {
            "kind": "union",
            "name": f"sample::ContainerWrap[{argument}]",
            "variants": [{"name": "WRAP", "fields": [{"name": "value", "type": deepcopy(INT)}]}],
        }
        tree = _tree(_halt(_lit(0)))
        tree["params"] = [["wrapped", deepcopy(wrapped)]]
        tree["types"] = {known["name"]: deepcopy(known), wrapped["name"]: deepcopy(wrapped)}
        validate(tree)

    missing = {
        "kind": "union",
        "name": "sample::ContainerWrap[List[sample::MissingContainerItem]]",
        "variants": [{"name": "WRAP", "fields": [{"name": "value", "type": deepcopy(INT)}]}],
    }
    tree = _tree(_halt(_lit(0)))
    tree["params"] = [["wrapped", deepcopy(missing)]]
    tree["types"] = {missing["name"]: deepcopy(missing)}
    _rule(tree, "nominal_definition")


def test_applied_union_discriminant_projects_its_owner_and_records_dependencies():
    generated = "RunRefResult$0123456789abcdef"
    signature = {"inputs": [], "result": {"schema": RUN_REF_RESULT_CONTRACT_SCHEMA, "envelope": {"kind": "record", "fields": []}}}
    descriptor = {
        "kind": "enum",
        "name": f"entry::Wrapper[{generated}].variant",
        "allowed": ["WRAP"],
    }

    projected = key_type_descriptor(descriptor, run_ref_signatures={generated: signature})

    assert projected["name"] == {
        "owner": {
            "head": "entry::Wrapper",
            "args": [{"kind": "run-ref-result", "signature": signature}],
        },
        "member": "variant",
    }
    assert run_ref_type_dependencies(descriptor) == (generated,)


def test_union_discriminant_field_uses_the_canonical_applied_owner_suffix():
    union = {
        "kind": "union",
        "name": "sample::Choice[Int]",
        "variants": [{"name": "Ready", "fields": []}],
    }
    discr = {"kind": "enum", "name": "sample::Choice[Int].variant", "allowed": ["Ready"]}
    tree = _tree(
        {
            "k": "halt",
            "value": {
                "k": "field",
                "base": {"k": "name", "n": "choice"},
                "path": ["variant"],
            },
        },
        result=discr,
    )
    tree["params"] = [["choice", union]]
    tree["types"] = {union["name"]: union, discr["name"]: discr}

    validate(tree)


def _captured_reference_tree(enclosing_capture_index=0, *, owner_capture_type=INT):
    target_key = [
        "sample", "procedure", "target", [], [], [], [],
        [{"type": deepcopy(INT), "routes": [["parameter", "captured"]]}],
        {"params": [], "result": deepcopy(INT)},
    ]
    reference = {
        "target": target_key,
        "residual": deepcopy(target_key[8]),
        "bound": [["captured", deepcopy(INT), {"capture": enclosing_capture_index}]],
    }
    owner_captures = [
        {"type": deepcopy(owner_capture_type), "routes": [["reference", ["fetch"], ["parameter", "captured"]]]},
    ]
    owner_params = [["capture0", deepcopy(owner_capture_type)]]
    if enclosing_capture_index:
        owner_captures.append({"type": deepcopy(INT), "routes": [["parameter", "unused"]]})
        owner_params.append(["capture1", deepcopy(INT)])
    owner_key = [
        "sample", "workflow", "owner", [], [["fetch", reference]], [], [],
        owner_captures, {"params": [], "result": deepcopy(INT)},
    ]
    target_name = canonical_callee_name_from_key(target_key)
    owner_name = canonical_callee_name_from_key(owner_key)
    tree = _tree()
    tree["definitions"] = {
        target_name: {
            "key": target_key,
            "params": [["captured", deepcopy(INT)]],
            "result": deepcopy(INT),
            "body": _halt(),
        },
        owner_name: {
            "key": owner_key,
            "params": owner_params,
            "result": deepcopy(INT),
            "body": _halt(),
        },
    }
    tree["sites"] = [list(row) for row in assign_sites(tree)]
    return tree, owner_key


def test_pref_bound_rows_match_target_substitutions_and_route_mapped_capture_prefixes():
    tree, _ = _captured_reference_tree()

    validate(tree)

    tree, owner_key = _captured_reference_tree(enclosing_capture_index=1)
    owner_key[4][0][1]["bound"][0][2]["capture"] = 1
    # The second enclosing capture has the same type, but its route does not
    # own the selected target parameter.
    _rule(tree, "definition_key")

    wrong_capture_type, _ = _captured_reference_tree(
        owner_capture_type={"kind": "primitive", "name": "String"}
    )
    _rule(wrong_capture_type, "definition_key")


def _tree_with_key_reference(target_key, reference):
    owner_key = [
        "sample", "workflow", "owner", [], [["fetch", reference]], [], [], [],
        {"params": [], "result": deepcopy(INT)},
    ]
    owner_name = canonical_callee_name_from_key(owner_key)
    tree = _tree()
    tree["definitions"] = {
        owner_name: {
            "key": owner_key,
            "params": [],
            "result": deepcopy(INT),
            "body": _halt(),
        }
    }
    tree["sites"] = [list(row) for row in assign_sites(tree)]
    return tree, owner_key


def test_pref_bound_value_and_nested_reference_rows_match_target_key_facts():
    closed = {"k": "lit", "v": 7, "type": deepcopy(INT)}
    target_key = [
        "sample", "procedure", "target", [], [], [], [["value", deepcopy(INT), closed]], [],
        {"params": [], "result": deepcopy(INT)},
    ]
    reference = {
        "target": target_key,
        "residual": deepcopy(target_key[8]),
        "bound": [["value", deepcopy(INT), {"value": deepcopy(closed)}]],
    }
    tree, _ = _tree_with_key_reference(target_key, reference)
    validate(tree)

    tree, owner_key = _tree_with_key_reference(target_key, reference)
    owner_key[4][0][1]["bound"][0][2]["value"]["v"] = 8
    _rule(tree, "definition_key")

    nested_target = [
        "sample", "procedure", "nested", [], [], [], [], [],
        {"params": [], "result": deepcopy(INT)},
    ]
    nested = {"target": nested_target, "residual": deepcopy(nested_target[8]), "bound": []}
    outer_target = [
        "sample", "procedure", "outer", [], [["callback", nested]], [], [], [],
        {"params": [], "result": deepcopy(INT)},
    ]
    outer_reference = {
        "target": outer_target,
        "residual": deepcopy(outer_target[8]),
        "bound": [[
            "callback",
            {"kind": "procedure-reference", "signature": deepcopy(nested["residual"])},
            {"procedure": deepcopy(nested)},
        ]],
    }
    tree, _ = _tree_with_key_reference(outer_target, outer_reference)
    validate(tree)


def test_pref_bound_workflow_reference_matches_its_nested_wref_target():
    workflow_key = [
        "sample", "workflow", "nested", [], [], [], [], [],
        {"params": [], "result": deepcopy(INT)},
    ]
    nested_wref = {
        "target": workflow_key,
        "externs": {"providers": [], "prompts": []},
    }
    target = [
        "sample", "procedure", "callback_owner", [], [], [["callback", nested_wref]], [], [],
        {"params": [], "result": deepcopy(INT)},
    ]
    pref = {
        "target": target,
        "residual": deepcopy(target[8]),
        "bound": [[
            "callback",
            {"kind": "workflow-reference", "signature": deepcopy(workflow_key[8])},
            {"workflow": deepcopy(nested_wref)},
        ]],
    }
    tree, owner = _tree_with_key_reference(target, deepcopy(pref))
    validate(tree)

    missing_bound, owner = _tree_with_key_reference(target, deepcopy(pref))
    owner[4][0][1]["bound"] = []
    _rule(missing_bound, "definition_key")

    wrong_nested_kind, owner = _tree_with_key_reference(target, deepcopy(pref))
    owner[4][0][1]["bound"][0][2]["workflow"]["target"][1] = "procedure"
    _rule(wrong_nested_kind, "definition_key")


def test_captured_reference_rejects_out_of_range_capture_selector():
    tree, owner = _captured_reference_tree()
    owner[4][0][1]["bound"][0][2]["capture"] = 9
    _rule(tree, "definition_key")


@pytest.mark.parametrize(
    ("reference_kind", "slot", "wrong_kind"),
    [("procedure", 4, "workflow"), ("workflow", 5, "procedure")],
)
def test_reference_category_matches_the_target_key_kind(reference_kind, slot, wrong_kind):
    def check_target(target_kind):
        target = [
            "sample", target_kind, "target", [], [], [], [], [],
            {"params": [], "result": deepcopy(INT)},
        ]
        reference = (
            {"target": target, "residual": deepcopy(target[8]), "bound": []}
            if reference_kind == "procedure"
            else {"target": target, "externs": {"providers": [], "prompts": []}}
        )
        owner = [
            "sample", "workflow", "owner", [], [], [], [], [],
            {"params": [], "result": deepcopy(INT)},
        ]
        owner[slot] = [["reference", reference]]
        name = canonical_callee_name_from_key(owner)
        halt = _halt(_lit(0))
        tree = _tree(deepcopy(halt))
        tree["definitions"] = {
            name: {
                "key": owner,
                "params": [],
                "result": deepcopy(INT),
                "body": deepcopy(halt),
            }
        }
        tree["sites"] = [list(row) for row in assign_sites(tree)]
        return tree

    validate(check_target(reference_kind))
    _rule(check_target(wrong_kind), "definition_key")


@pytest.mark.parametrize(
    ("category", "extern"),
    [
        ("providers", {"provider_id": "provider:test"}),
        ("prompts", {"source_kind": "input_file", "path": "prompt.md"}),
        ("prompts", {"source_kind": "asset_file", "path": "prompt.md", "asset_base": "assets"}),
    ],
)
@pytest.mark.parametrize("formal", ["ordinary", ["local", 0]])
def test_workflow_extern_rows_require_named_formals(category, extern, formal):
    target = [
        "sample", "workflow", "target", [], [], [], [], [],
        {"params": [], "result": deepcopy(INT)},
    ]
    externs = {"providers": [], "prompts": []}
    externs[category] = [[formal, deepcopy(extern)]]
    reference = {"target": target, "externs": externs}
    owner = [
        "sample", "workflow", "owner", [], [], [["reference", reference]], [], [],
        {"params": [], "result": deepcopy(INT)},
    ]
    name = canonical_callee_name_from_key(owner)
    halt = _halt(_lit(0))
    tree = _tree(deepcopy(halt))
    tree["definitions"] = {
        name: {
            "key": owner,
            "params": [],
            "result": deepcopy(INT),
            "body": deepcopy(halt),
        }
    }
    tree["sites"] = [list(row) for row in assign_sites(tree)]

    if isinstance(formal, str):
        validate(tree)
    else:
        _rule(tree, "definition_key")


def test_workflow_extern_rows_reject_malformed_duplicate_and_reordered_facts():
    target = [
        "sample", "workflow", "externs", [], [], [], [], [],
        {"params": [], "result": deepcopy(INT)},
    ]

    def tree_for(provider_rows):
        reference = {
            "target": target,
            "externs": {"providers": deepcopy(provider_rows), "prompts": []},
        }
        owner = [
            "sample", "workflow", "extern_owner", [], [], [["nested", reference]], [], [],
            {"params": [], "result": deepcopy(INT)},
        ]
        name = canonical_callee_name_from_key(owner)
        tree = _tree(_halt(_lit(0)))
        tree["definitions"] = {
            name: {"key": owner, "params": [], "result": deepcopy(INT), "body": _halt(_lit(0))}
        }
        tree["sites"] = [list(row) for row in assign_sites(tree)]
        return tree

    valid_rows = [["alpha", {"provider_id": "provider:alpha"}], ["omega", {"provider_id": "provider:omega"}]]
    validate(tree_for(valid_rows))

    malformed = deepcopy(valid_rows)
    malformed[0][1]["unexpected"] = True
    _rule(tree_for(malformed), "definition_key")

    duplicate = [valid_rows[0], ["alpha", {"provider_id": "provider:other"}]]
    _rule(tree_for(duplicate), "definition_key")

    reordered = [valid_rows[1], valid_rows[0]]
    _rule(tree_for(reordered), "definition_key")


def test_closed_literal_data_is_not_scanned_as_a_run_ref_marker():
    value_type = {"kind": "primitive", "name": "Value"}
    data = {
        "kind": "run-ref-result",
        "signature": "ordinary literal data",
        "name": "RunRefResult$0123456789abcdef",
    }
    closed = {"k": "lit", "type": value_type, "v": data}
    key = [
        "sample", "procedure", "f", [], [], [], [["payload", value_type, closed]], [],
        {"params": [], "result": deepcopy(INT)},
    ]
    name = canonical_callee_name_from_key(key)
    tree = _tree()
    tree["definitions"] = {
        name: {
            "key": key,
            "params": [],
            "result": deepcopy(INT),
            "body": _halt(),
        }
    }
    tree["sites"] = [list(row) for row in assign_sites(tree)]

    validate(tree)

    forged, _, path = _provider_result_path_tree(params=[["\x00provider:x", deepcopy(INT)]])
    forged["body"] = {"k": "halt", "value": {"k": "result_path", "n": "x", "type": path}}
    forged["sites"] = [list(row) for row in assign_sites(forged)]
    _rule(forged, "provider_result_path")


def _closed_enum_operator_tree():
    union = {
        "kind": "union",
        "name": "sample::Choice[Int]",
        "variants": [{"name": "Ready", "fields": []}],
    }
    enum = {"kind": "enum", "name": "sample::Choice[Int].variant", "allowed": ["Ready"]}
    projected = key_type_descriptor(enum, run_ref_signatures={})
    bool_type = deepcopy(BOOL)
    payload = {
        "pure_expr_schema_version": 2,
        "result_type": bool_type,
        "bindings": {"a0": {"type": deepcopy(enum)}, "a1": {"type": deepcopy(enum)}},
        "expr": {
            "kind": "op",
            "operator": "=",
            "args": [
                {"kind": "binding", "name": "a0"},
                {"kind": "binding", "name": "a1"},
            ],
        },
    }
    for row in payload["bindings"].values():
        row["type"] = deepcopy(projected)
    closed = {
        "k": "op",
        "payload": payload,
        "args": [
            {"k": "lit", "type": deepcopy(projected), "v": "Ready"},
            {"k": "lit", "type": deepcopy(projected), "v": "Ready"},
        ],
    }
    key = ["sample", "procedure", "f", [], [], [], [["flag", bool_type, closed]], [], {"params": [], "result": deepcopy(INT)}]
    name = canonical_callee_name_from_key(key)
    body = _halt(_lit(0))
    tree = _tree(body)
    tree["types"] = {union["name"]: union, enum["name"]: enum}
    tree["definitions"] = {
        name: {"key": key, "params": [], "result": deepcopy(INT), "body": deepcopy(body)}
    }
    tree["sites"] = [list(row) for row in assign_sites(tree)]
    return tree, payload, enum


def test_closed_operator_payload_uses_projected_type_slots_and_checks_them():
    tree, _, _ = _closed_enum_operator_tree()
    validate(tree)

    malformed, payload, enum = _closed_enum_operator_tree()
    payload["bindings"]["a0"]["type"] = deepcopy(enum)
    _rule(malformed, "definition_key")

    malformed, payload, _ = _closed_enum_operator_tree()
    payload["pure_expr_schema_version"] = 1
    _rule(malformed, "definition_key")


def test_applied_identity_parser_rejects_noncanonical_container_renderings():
    descriptor = {
        "kind": "record",
        "name": "entry::Wrapper[Map[String, Int]]",
        "fields": [],
    }

    with pytest.raises(ValueError, match="canonical"):
        key_type_descriptor(descriptor, run_ref_signatures={})


def _record(name, fields):
    return {
        "kind": "record",
        "name": name,
        "fields": [{"name": field, "type": deepcopy(type_)} for field, type_ in fields],
    }


def _boundary_tree(caller_roots, native_roots, caller_result, native_result, *, direct=()):
    key = [
        "native", "workflow", "fetch", [], [], [], [], [],
        {"params": [deepcopy(descriptor) for _, descriptor in native_roots], "result": deepcopy(native_result)},
    ]
    callee = canonical_callee_name_from_key(key)
    params = [[name, deepcopy(descriptor)] for name, descriptor in caller_roots]
    native_params = [[name, deepcopy(descriptor)] for name, descriptor in native_roots]
    caller_direct = {left for left, _ in direct}
    native_direct = {right for _, right in direct}
    caller_projected = [row for index, row in enumerate(caller_roots) if index not in caller_direct]
    native_projected = [row for index, row in enumerate(native_roots) if index not in native_direct]
    call = {
        "k": "call",
        "callee": callee,
        "args": [{"k": "name", "n": name} for name, _ in caller_roots],
        "type": deepcopy(caller_result),
        "boundary": {
            "params": params,
            "direct": [list(pair) for pair in direct],
            "inputs": {
                "caller": compiled_boundary_rows(caller_projected),
                "callee": compiled_boundary_rows(native_projected),
            },
            "outputs": {
                "caller": compiled_boundary_rows([("return", caller_result)], output=True),
                "callee": compiled_boundary_rows([("return", native_result)], output=True),
            },
        },
    }
    native_value = _boundary_value(native_result)
    tree = _tree(
        {
            "k": "let",
            "name": "answer",
            "value": call,
            "body": {"k": "halt", "value": {"k": "name", "n": "answer"}},
        },
        result=caller_result,
    )
    tree["params"] = [[name, deepcopy(descriptor)] for name, descriptor in caller_roots]
    tree["types"] = {
        descriptor["name"]: deepcopy(descriptor)
        for _, descriptor in [*caller_roots, *native_roots, ("return", caller_result), ("return", native_result)]
        if descriptor["kind"] in {"record", "union", "enum", "path"}
    }
    tree["definitions"] = {
        callee: {
            "key": key,
            "params": native_params,
            "result": deepcopy(native_result),
            "body": {"k": "halt", "value": native_value},
        }
    }
    tree["sites"] = [list(row) for row in assign_sites(tree)]
    return tree, call


def _boundary_value(descriptor):
    kind = descriptor["kind"]
    if kind == "primitive":
        values = {
            "String": "value",
            "Int": 0,
            "Float": 0.0,
            "Bool": False,
            "Value": {},
            "RunId": "run",
            "Symbol": "symbol",
        }
        return _lit(values[descriptor["name"]], descriptor)
    if kind in {"enum", "path", "list", "optional", "map"}:
        value = (
            descriptor["allowed"][0]
            if kind == "enum"
            else f"{descriptor['under']}/result"
            if kind == "path"
            else []
            if kind == "list"
            else None
            if kind == "optional"
            else {}
        )
        return _lit(value, descriptor)
    if kind == "record":
        return {
            "k": "record",
            "type": deepcopy(descriptor),
            "fields": [[field["name"], _boundary_value(field["type"])] for field in descriptor["fields"]],
        }
    if kind == "union":
        variant = descriptor["variants"][0]
        return {
            "k": "inject",
            "type": deepcopy(descriptor),
            "variant": variant["name"],
            "fields": [[field["name"], _boundary_value(field["type"])] for field in variant["fields"]],
        }
    raise AssertionError(f"no boundary value fixture for {kind}")


def _generated_producer(site, input_type, source_name):
    input_rows = (("source", deepcopy(input_type)),)
    placeholder = _build_run_ref_config("0" * 64, input_rows)
    signature = canonical_run_ref_signature(
        [(row.name, row.type_descriptor) for row in placeholder.inputs],
        placeholder.result_descriptor,
        run_ref_signatures={},
    )
    digest = sha256(
        canonical_json_for_pure_value(
            ["workflow-lisp/run-ref-site/1", "workflow:sample::run", site, signature]
        ).encode("utf-8")
    ).hexdigest()
    config = _build_run_ref_config(digest, input_rows)
    effect = {
        "k": "perform",
        "class": "run_ref",
        "result": deepcopy(config.result_descriptor["envelope"]),
        "repeat": "rerun",
        "config": base64.b64encode(encode_run_ref_static_config(config)).decode("ascii"),
        "inputs": [["source", _name(source_name)]],
    }
    return effect, config, signature


def _generated_boundary_tree(
    caller_roots,
    native_roots,
    caller_result,
    native_result,
    *,
    second_input_type=INT,
    direct=(),
    capture_prefix=0,
):
    producer_a, config_a, signature_a = _generated_producer("producer_a", INT, "seed_a")
    producer_b, config_b, signature_b = _generated_producer("producer_b", second_input_type, "seed_b")
    tree, call = _boundary_tree(
        caller_roots, native_roots, caller_result, native_result, direct=direct
    )
    tree["params"].extend([["seed_a", deepcopy(INT)], ["seed_b", deepcopy(second_input_type)]])
    tree["body"] = {
        "k": "let",
        "name": "producer_a",
        "value": producer_a,
        "body": {
            "k": "let",
            "name": "producer_b",
            "value": producer_b,
            "body": tree["body"],
        },
    }
    for config in (config_a, config_b):
        _register_nominal_types(config.result_descriptor["envelope"], tree["types"])
    tree["sites"] = [list(row) for row in assign_sites(tree)]
    assert producer_a["site"] == "producer_a"
    assert producer_b["site"] == "producer_b"

    signatures = {
        config_a.generated_result_type: signature_a,
        config_b.generated_result_type: signature_b,
    }
    previous_name = call["callee"]
    definition = tree["definitions"].pop(previous_name)
    key = definition["key"]
    key[7] = [
        {
            "type": key_type_descriptor(
                native_roots[index][1], run_ref_signatures=signatures
            ),
            "routes": [["parameter", native_roots[index][0]]],
        }
        for index in range(capture_prefix)
    ]
    key[8] = {
        "params": [
            key_type_descriptor(descriptor, run_ref_signatures=signatures)
            for _, descriptor in native_roots[capture_prefix:]
        ],
        "result": key_type_descriptor(native_result, run_ref_signatures=signatures),
    }
    definition["key"] = key
    call["callee"] = canonical_callee_name_from_key(key)
    tree["definitions"][call["callee"]] = definition
    tree["sites"] = [list(row) for row in assign_sites(tree)]
    return tree, call, config_a.result_descriptor["envelope"], config_b.result_descriptor["envelope"]


def _generated_result_pair(second_input_type=INT):
    _, config_a, _ = _generated_producer("producer_a", INT, "seed_a")
    _, config_b, _ = _generated_producer("producer_b", second_input_type, "seed_b")
    return config_a.result_descriptor["envelope"], config_b.result_descriptor["envelope"]


def _phantom_record(generated):
    return {
        "kind": "record",
        "name": f"sample::Phantom[{generated['name']}]",
        "fields": [{"name": "count", "type": deepcopy(INT)}],
    }


def test_generated_boundary_compares_full_signatures_for_scalar_list_and_phantom_units():
    generated_a, generated_b = _generated_result_pair()
    same_signature_cases = [
        ([("value", generated_a)], [("value", generated_b)]),
        (
            [("value", {"kind": "list", "item": deepcopy(generated_a)})],
            [("value", {"kind": "list", "item": deepcopy(generated_b)})],
        ),
        (
            [("value", _phantom_record(generated_a))],
            [("value", _phantom_record(generated_b))],
        ),
    ]
    for caller_roots, native_roots in same_signature_cases:
        tree, _call, _, _ = _generated_boundary_tree(
            caller_roots, native_roots, INT, INT
        )
        validate(tree)

    changed_a, changed_b = _generated_result_pair(BOOL)
    changed_signature_cases = [
        ([("value", changed_a)], [("value", changed_b)]),
        (
            [("value", {"kind": "list", "item": deepcopy(changed_a)})],
            [("value", {"kind": "list", "item": deepcopy(changed_b)})],
        ),
        (
            [("value", _phantom_record(changed_a))],
            [("value", _phantom_record(changed_b))],
        ),
    ]
    for caller_roots, native_roots in changed_signature_cases:
        tree, _call, _, _ = _generated_boundary_tree(
            caller_roots, native_roots, INT, INT, second_input_type=BOOL
        )
        _rule(tree, "call_boundary")


def test_generated_boundary_checks_outputs_and_branch_activation_independently():
    generated_a, generated_b = _generated_result_pair()
    output_tree, _call, _, _ = _generated_boundary_tree(
        [("value", deepcopy(INT))],
        [("value", deepcopy(INT))],
        generated_a,
        generated_b,
    )
    validate(output_tree)

    changed_a, changed_b = _generated_result_pair(BOOL)
    output_tree, _call, _, _ = _generated_boundary_tree(
        [("value", deepcopy(INT))],
        [("value", deepcopy(INT))],
        changed_a,
        changed_b,
        second_input_type=BOOL,
    )
    _rule(output_tree, "call_boundary")

    branch_a, branch_b = _generated_result_pair(BOOL)
    caller_union = {
        "kind": "union",
        "name": "caller::Choice",
        "variants": [
            {"name": "LEFT", "fields": [{"name": "child", "type": deepcopy(branch_a)}]},
            {"name": "RIGHT", "fields": [{"name": "child", "type": deepcopy(branch_b)}]},
        ],
    }
    native_union = deepcopy(caller_union)
    native_union["name"] = "native::Choice"
    tree, _call, _, _ = _generated_boundary_tree(
        [("value", caller_union)],
        [("value", native_union)],
        INT,
        INT,
        second_input_type=BOOL,
    )
    validate(tree)

    native_union["variants"][0]["fields"][0]["type"] = deepcopy(branch_b)
    native_union["variants"][1]["fields"][0]["type"] = deepcopy(branch_a)
    swapped, _call, _, _ = _generated_boundary_tree(
        [("value", caller_union)],
        [("value", native_union)],
        INT,
        INT,
        second_input_type=BOOL,
    )
    _rule(swapped, "call_boundary")


def test_generated_boundary_preserves_capture_prefix_and_composed_one_to_many_rows():
    generated_a, generated_b = _generated_result_pair()
    capture_tree, _call, _, _ = _generated_boundary_tree(
        [("captured", generated_a), ("value", deepcopy(INT))],
        [("captured", generated_b), ("value", deepcopy(INT))],
        INT,
        INT,
        capture_prefix=1,
    )
    validate(capture_tree)

    changed_a, changed_b = _generated_result_pair(BOOL)
    changed_capture, _call, _, _ = _generated_boundary_tree(
        [("captured", changed_a), ("value", deepcopy(INT))],
        [("captured", changed_b), ("value", deepcopy(INT))],
        INT,
        INT,
        second_input_type=BOOL,
        capture_prefix=1,
    )
    _rule(changed_capture, "call_boundary")

    direct_capture, _call, _, _ = _generated_boundary_tree(
        [("captured", generated_a), ("value", generated_a)],
        [("captured", deepcopy(generated_a)), ("value", deepcopy(generated_b))],
        INT,
        INT,
        direct=[(0, 0)],
        capture_prefix=1,
    )
    validate(direct_capture)

    direct_generated_capture, _call, _, _ = _generated_boundary_tree(
        [("captured", generated_a)],
        [("captured", generated_b)],
        INT,
        INT,
        direct=[(0, 0)],
        capture_prefix=1,
    )
    _rule(direct_generated_capture, "call_boundary")

    caller_context = _record("caller::PhaseCtx", [("phase", INT)])
    native_context = _record("native::PhaseCtx", [("phase", INT)])
    caller_pack = _record(
        "caller::Packed",
        [("token", INT), ("child", deepcopy(generated_a))],
    )
    composed, _call, _, _ = _generated_boundary_tree(
        [("ctx", caller_context), ("pack", caller_pack)],
        [
            ("ctx", native_context),
            ("pack__child", deepcopy(generated_b)),
            ("pack__token", deepcopy(INT)),
        ],
        INT,
        INT,
    )
    validate(composed)

    shared = {
        "kind": "union",
        "name": "caller::Shared",
        "variants": [
            {"name": "LEFT", "fields": [{"name": "child", "type": deepcopy(generated_a)}]},
            {"name": "RIGHT", "fields": [{"name": "child", "type": deepcopy(generated_a)}]},
        ],
    }
    discriminator = {
        "kind": "enum",
        "name": "native::Shared.variant",
        "allowed": ["LEFT", "RIGHT"],
    }
    shared_view, _call, _, _ = _generated_boundary_tree(
        [("value", shared)],
        [("value__child", deepcopy(generated_b)), ("value__variant", discriminator)],
        INT,
        INT,
    )
    validate(shared_view)

    conditional = {
        "kind": "union",
        "name": "caller::Conditional",
        "variants": [
            {"name": "LEFT", "fields": [{"name": "child", "type": deepcopy(generated_a)}]},
            {"name": "RIGHT", "fields": [{"name": "dummy", "type": deepcopy(INT)}]},
        ],
    }
    conditional_discriminator = {
        "kind": "enum",
        "name": "native::Conditional.variant",
        "allowed": ["LEFT", "RIGHT"],
    }
    conditional_view, _call, _, _ = _generated_boundary_tree(
        [("value", conditional)],
        [
            ("value__child", deepcopy(generated_b)),
            ("value__dummy", deepcopy(INT)),
            ("value__variant", conditional_discriminator),
        ],
        INT,
        INT,
    )
    _rule(conditional_view, "call_boundary")


def test_annotated_nominal_result_and_one_to_many_input_views_are_checked_by_both_endpoints():
    caller = _record("sample::Pair", [("x", INT), ("y", INT)])
    native = _record("native::Pair", [("x", INT), ("y", INT)])
    tree, _ = _boundary_tree([("a", caller)], [("a", native)], caller, native)

    validate(tree)

    tree, _ = _boundary_tree(
        [("a", caller)], [("a__x", INT), ("a__y", INT)], INT, INT
    )
    validate(tree)


def test_annotated_boundary_rejects_forged_root_paths_and_boolean_direct_indices():
    pair = _record("sample::Pair", [("x", INT), ("y", INT)])
    tree, call = _boundary_tree([("a", pair)], [("a", pair)], INT, INT)
    call["boundary"]["inputs"]["caller"][0]["path"] = ["a", "missing"]
    _rule(tree, "call_boundary")

    tree, _ = _boundary_tree([("a", INT)], [("a", INT)], INT, INT, direct=[(True, 0)])
    _rule(tree, "call_boundary")


_SOURCE_CONTEXT = _record("sample::SourceCtx", [("x", INT)])
_NATIVE_CONTEXT = _record("sample::NativeCtx", [("x", INT)])
_WRAPPER_ID = ["sample", "procedure", "wrapper"]
_TERMINAL_ID = ["sample", "procedure", "terminal"]
_CONTEXT_FIELDS = [[ ["x"], ["x"] ]]


def _name(name):
    return {"k": "name", "n": name}


def _call(callee, arguments):
    return {"k": "call", "callee": callee, "args": [_name(name) for name in arguments], "type": deepcopy(INT)}


def _callable_key(name, *, captures=(), params=()):
    return [
        "sample", "procedure", name, [], [], [], [], list(captures),
        {"params": [deepcopy(type_) for type_ in params], "result": deepcopy(INT)},
    ]


def _context_capture(route):
    return {"type": deepcopy(_SOURCE_CONTEXT), "routes": [route]}


def _context_route_tree(
    *, outer_occurrence=0, inner_occurrence=1, inner_hop=None,
    forwarded=True, injection_source="captured", alias=False,
    shadow=False, add_pure_let=False, rename_binders=False,
    padding_capture=False, field_pairs=None, wrapper_padding_captures=0,
):
    terminal_id = _TERMINAL_ID if inner_hop is None else inner_hop
    pairs = _CONTEXT_FIELDS if field_pairs is None else field_pairs
    outer_route = [
        "context",
        [[_WRAPPER_ID, outer_occurrence], [_TERMINAL_ID, inner_occurrence]],
        "ctx",
        deepcopy(pairs),
    ]
    inner_route = ["context", [[terminal_id, inner_occurrence]], "ctx", deepcopy(pairs)]
    terminal_key = _callable_key("terminal", params=[_NATIVE_CONTEXT, INT])
    unrelated_key = _callable_key("unrelated")
    wrapper_capture_rows = [
        {"type": deepcopy(INT), "routes": [["parameter", f"padding{index}"]]}
        for index in range(wrapper_padding_captures)
    ] + [_context_capture(inner_route)]
    wrapper_key = _callable_key(
        "wrapper", captures=wrapper_capture_rows,
        params=[_SOURCE_CONTEXT, _NATIVE_CONTEXT, INT],
    )
    outer_captures = [_context_capture(outer_route)]
    outer_params = [INT] * wrapper_padding_captures + [_SOURCE_CONTEXT, _NATIVE_CONTEXT, INT]
    if padding_capture:
        outer_captures.insert(0, {"type": deepcopy(INT), "routes": [["parameter", "padding"]]})
    outer_key = _callable_key("outer", captures=outer_captures, params=outer_params)
    terminal = canonical_callee_name_from_key(terminal_key)
    unrelated = canonical_callee_name_from_key(unrelated_key)
    wrapper = canonical_callee_name_from_key(wrapper_key)
    outer = canonical_callee_name_from_key(outer_key)

    injected_source = "forward_alias" if alias else ("alternate" if shadow else injection_source)
    injected = _call(terminal, [injected_source, "payload"])
    injected["boundary"] = {
        "params": [["ctx", deepcopy(_SOURCE_CONTEXT)], ["payload", deepcopy(INT)]],
        "direct": [],
        "inputs": {
            "caller": compiled_boundary_rows([("ctx", _SOURCE_CONTEXT), ("payload", INT)]),
            "callee": compiled_boundary_rows([("ctx", _NATIVE_CONTEXT), ("payload", INT)]),
        },
        "outputs": {
            "caller": compiled_boundary_rows([("return", INT)], output=True),
            "callee": compiled_boundary_rows([("return", INT)], output=True),
        },
    }
    first, second, third = (
        ("first_result", "noise_result", "selected_result")
        if rename_binders else ("explicit_result", "other_result", "injected_result")
    )
    wrapper_body = {
        "k": "let", "name": first, "value": _call(terminal, ["explicit", "payload"]),
        "body": {
            "k": "let", "name": second, "value": _call(unrelated, []),
            "body": {
                "k": "let", "name": third, "value": injected,
                "body": {"k": "halt", "value": _name(third)},
            },
        },
    }
    if alias:
        wrapper_body = {
            "k": "let", "name": "forward_alias", "value": _name("captured"), "body": wrapper_body,
        }
    if shadow:
        wrapper_body = {
            "k": "let", "name": "captured", "value": _name("alternate"), "body": wrapper_body,
        }
    if add_pure_let:
        wrapper_body = {"k": "let", "name": "unused", "value": _lit(3), "body": wrapper_body}

    wrapper_params = [
        [f"padding{index}", deepcopy(INT)]
        for index in range(wrapper_padding_captures)
    ] + [["captured", deepcopy(_SOURCE_CONTEXT)], ["alternate", deepcopy(_SOURCE_CONTEXT)],
         ["explicit", deepcopy(_NATIVE_CONTEXT)], ["payload", deepcopy(INT)]]

    definitions = {
        terminal: {
            "key": terminal_key,
            "params": [["ctx", deepcopy(_NATIVE_CONTEXT)], ["payload", deepcopy(INT)]],
            "result": deepcopy(INT), "body": _halt(_name("payload")),
        },
        unrelated: {
            "key": unrelated_key, "params": [], "result": deepcopy(INT), "body": _halt(),
        },
        wrapper: {
            "key": wrapper_key,
            "params": wrapper_params,
            "result": deepcopy(INT), "body": wrapper_body,
        },
        outer: {
            "key": outer_key,
            "params": ([ ["padding", deepcopy(INT)] ] if padding_capture else []) +
                      [["captured", deepcopy(_SOURCE_CONTEXT)]] +
                      [[f"padding{index}", deepcopy(INT)] for index in range(wrapper_padding_captures)] +
                      [["alternate", deepcopy(_SOURCE_CONTEXT)], ["explicit", deepcopy(_NATIVE_CONTEXT)],
                       ["payload", deepcopy(INT)]],
            "result": deepcopy(INT),
            "body": {"k": "let", "name": "forwarded", "value": _call(wrapper, (
                [f"padding{index}" for index in range(wrapper_padding_captures)] +
                ["captured" if forwarded else "alternate", "alternate", "explicit", "payload"]
            )), "body": _halt(_name("forwarded"))},
        },
    }
    entry_params = ([ ["padding", deepcopy(INT)] ] if padding_capture else []) + [
        ["source", deepcopy(_SOURCE_CONTEXT)],
    ] + [[f"padding{index}", deepcopy(INT)] for index in range(wrapper_padding_captures)] + [
        ["alternate", deepcopy(_SOURCE_CONTEXT)], ["explicit", deepcopy(_NATIVE_CONTEXT)],
        ["payload", deepcopy(INT)],
    ]
    entry_args = (["padding"] if padding_capture else []) + ["source"] + [
        f"padding{index}" for index in range(wrapper_padding_captures)
    ] + ["alternate", "explicit", "payload"]
    tree = _tree(
        {"k": "let", "name": "answer", "value": _call(outer, entry_args),
         "body": _halt(_name("answer"))},
        result=INT,
    )
    tree["entry"] = "workflow:sample::run"
    tree["params"] = entry_params
    tree["types"] = {
        _SOURCE_CONTEXT["name"]: deepcopy(_SOURCE_CONTEXT),
        _NATIVE_CONTEXT["name"]: deepcopy(_NATIVE_CONTEXT),
    }
    tree["definitions"] = definitions
    tree["sites"] = [list(row) for row in assign_sites(tree)]
    return tree


def test_context_routes_follow_selected_calls_and_exact_capture_forwarding():
    validate(_context_route_tree())
    validate(_context_route_tree(add_pure_let=True, rename_binders=True))
    validate(_context_route_tree(padding_capture=True))
    validate(_context_route_tree(wrapper_padding_captures=2))


@pytest.mark.parametrize(
    "changes",
    [
        {"outer_occurrence": 1},
        {"inner_occurrence": 0},
        {"inner_hop": _WRAPPER_ID},
        {"forwarded": False},
        {"injection_source": "alternate"},
        {"alias": True},
        {"shadow": True},
        {"field_pairs": [[["missing"], ["x"]]]},
    ],
)
def test_context_routes_reject_wrong_hops_and_non_capture_argument_sources(changes):
    _rule(_context_route_tree(**changes), "capture_route")


def _provider_result_path_tree(*, params=None):
    string = {"kind": "primitive", "name": "String"}
    path = {
        "kind": "path",
        "name": "sample::RunOutput",
        "under": ".orchestrate/runs",
        "must_exist_target": False,
    }
    provider = {
        "k": "perform",
        "class": "provider",
        "result": deepcopy(string),
        "repeat": "rerun",
        "provider": "sample-provider",
        "prompt": {"template": "write", "fills": []},
        "inputs": [],
        "dependencies": None,
        "policy": None,
        "contract": {
            "kind": "output_bundle",
            "payload": {"fields": [{"name": "__result__", "json_pointer": "", "type": "string"}]},
        },
    }
    tree = _tree(result=path)
    tree["params"] = [] if params is None else params
    tree["types"] = {path["name"]: path}
    tree["configuration"]["providers"] = {
        "sample-provider": {"provider_id": "sample-provider"}
    }
    tree["sites"] = [list(row) for row in assign_sites(tree)]
    return tree, provider, path


def _provider_prompt_tree(template, fills):
    string = {"kind": "primitive", "name": "String"}
    tree, provider, _path = _provider_result_path_tree()
    tree["result"] = deepcopy(string)
    tree["body"] = {
        "k": "let",
        "name": "answer",
        "value": provider,
        "body": _halt(_name("answer")),
    }
    provider["prompt"] = {"template": template, "fills": fills}
    tree["sites"] = [list(row) for row in assign_sites(tree)]
    return tree, provider


def _provider_prompt_fills():
    string = {"kind": "primitive", "name": "String"}
    document = {
        "kind": "path",
        "name": "sample::PromptDocument",
        "under": "docs",
        "must_exist_target": True,
    }
    output = {
        "kind": "path",
        "name": "sample::PromptOutput",
        "under": "artifacts",
        "must_exist_target": False,
    }
    fills = [
        {
            "name": "document",
            "kind": "doc",
            "type": deepcopy(document),
            "value": _lit("docs/readme.md", document),
            "renderer_id": None,
            "output_role": None,
            "placeholder_ordinals": [],
        },
        {
            "name": "title",
            "kind": "text",
            "type": deepcopy(string),
            "value": _lit("A title", string),
            "renderer_id": "raw-utf8-string",
            "output_role": "none",
            "placeholder_ordinals": [0],
        },
        {
            "name": "score",
            "kind": "value",
            "type": deepcopy(INT),
            "value": _lit(7),
            "renderer_id": "canonical-json",
            "output_role": None,
            "placeholder_ordinals": [1],
        },
        {
            "name": "output",
            "kind": "path",
            "type": deepcopy(output),
            "value": _lit("artifacts/result.txt", output),
            "renderer_id": "posix-path-line",
            "output_role": "required_string_file",
            "placeholder_ordinals": [2],
        },
    ]
    return fills, document, output


def test_provider_template_fills_retain_all_closed_slot_semantics():
    fills, document, output = _provider_prompt_fills()
    tree, _provider = _provider_prompt_tree(
        "Read the document; write {title} with score {score} to {output}",
        fills,
    )
    tree["types"].update(
        {document["name"]: deepcopy(document), output["name"]: deepcopy(output)}
    )

    validate(tree)


@pytest.mark.parametrize(
    "mutation",
    [
        "document_integer",
        "document_not_existing",
        "document_has_renderer",
        "text_integer",
        "text_wrong_renderer",
        "unknown_kind",
        "value_wrong_renderer",
        "path_integer",
        "path_output_requires_existing_path",
        "unknown_output_role",
        "missing_placeholder",
        "wrong_placeholder_ordinal",
        "duplicate_placeholder_ordinal",
        "document_claims_placeholder",
    ],
)
def test_provider_template_fills_reject_semantic_and_placeholder_tampering(mutation):
    fills, document, output = _provider_prompt_fills()
    by_name = {row["name"]: row for row in fills}
    template = "Read the document; write {title} with score {score} to {output}"
    if mutation == "document_integer":
        row = by_name["document"]
        row["type"] = deepcopy(INT)
        row["value"] = _lit(7)
    elif mutation == "document_not_existing":
        missing = {**output, "must_exist_target": False}
        by_name["document"]["type"] = deepcopy(missing)
        by_name["document"]["value"] = _lit("artifacts/result.txt", missing)
        output = missing
    elif mutation == "document_has_renderer":
        by_name["document"]["renderer_id"] = "required-document"
    elif mutation == "text_integer":
        by_name["title"]["type"] = deepcopy(INT)
        by_name["title"]["value"] = _lit(7)
    elif mutation == "text_wrong_renderer":
        by_name["title"]["renderer_id"] = "canonical-json"
    elif mutation == "unknown_kind":
        by_name["score"]["kind"] = "other"
    elif mutation == "value_wrong_renderer":
        by_name["score"]["renderer_id"] = "made-up-renderer"
    elif mutation == "path_integer":
        by_name["output"]["type"] = deepcopy(INT)
        by_name["output"]["value"] = _lit(7)
        by_name["output"]["output_role"] = None
    elif mutation == "path_output_requires_existing_path":
        existing_output = {**output, "must_exist_target": True}
        by_name["output"]["type"] = deepcopy(existing_output)
        by_name["output"]["value"] = _lit("artifacts/result.txt", existing_output)
        output = existing_output
    elif mutation == "unknown_output_role":
        by_name["output"]["output_role"] = "optional_string_file"
    elif mutation == "missing_placeholder":
        by_name["score"]["placeholder_ordinals"] = []
    elif mutation == "wrong_placeholder_ordinal":
        by_name["title"]["placeholder_ordinals"] = [1]
    elif mutation == "duplicate_placeholder_ordinal":
        by_name["score"]["placeholder_ordinals"] = [0]
    elif mutation == "document_claims_placeholder":
        by_name["document"]["placeholder_ordinals"] = [0]

    tree, _provider = _provider_prompt_tree(template, fills)
    for descriptor in (document, output):
        tree["types"][descriptor["name"]] = deepcopy(descriptor)

    _rule(tree, "effect_shape")


@pytest.mark.parametrize(
    ("renderer", "descriptor", "value", "accepted"),
    [
        ("canonical-json", INT, 7, True),
        (
            "canonical-json",
            {"kind": "path", "name": "sample::InputPath", "under": "docs", "must_exist_target": False},
            "docs/input.md",
            True,
        ),
        (
            "posix-path-line",
            {"kind": "path", "name": "sample::InputPath", "under": "docs", "must_exist_target": False},
            "docs/input.md",
            True,
        ),
        ("posix-path-line", {"kind": "primitive", "name": "String"}, "docs/input.md", True),
        (7, INT, 7, False),
        ("unknown-renderer", INT, 7, False),
        ("posix-path-line", INT, 7, False),
        ("posix-path-line", {"kind": "primitive", "name": "String"}, "docs/a\r\nb", False),
    ],
)
def test_provider_input_renderer_is_registered_and_matches_its_value_shape(
    renderer, descriptor, value, accepted
):
    tree, provider, _ = _provider_result_path_tree()
    tree["result"] = {"kind": "primitive", "name": "String"}
    tree["body"] = {
        "k": "let",
        "name": "answer",
        "value": provider,
        "body": _halt(_name("answer")),
    }
    if descriptor["kind"] == "path":
        tree["types"][descriptor["name"]] = deepcopy(descriptor)
    provider["inputs"] = [["input", renderer, _lit(value, descriptor)]]
    tree["sites"] = [list(row) for row in assign_sites(tree)]

    if accepted:
        validate(tree)
    else:
        _rule(tree, "effect_shape")


def _provider_operand_tree():
    tree, provider, _ = _provider_result_path_tree()
    string = {"kind": "primitive", "name": "String"}
    tree["result"] = deepcopy(string)
    tree["body"] = {
        "k": "let",
        "name": "answer",
        "value": provider,
        "body": _halt(_name("answer")),
    }
    tree["sites"] = [list(row) for row in assign_sites(tree)]
    return tree, provider


def test_provider_dependencies_keep_paths_separate_from_text_metadata():
    path = {
        "kind": "path",
        "name": "sample::PromptDependency",
        "under": "docs",
        "must_exist_target": True,
    }
    for instruction in (None, "Read these documents"):
        tree, provider = _provider_operand_tree()
        tree["types"][path["name"]] = deepcopy(path)
        tree["params"] = [["document", deepcopy(path)]]
        provider["dependencies"] = {
            "required": [_name("document")],
            "optional": [],
            "position": "prepend",
            "instruction": instruction,
        }
        tree["sites"] = [list(row) for row in assign_sites(tree)]

        validate(tree)


@pytest.mark.parametrize(
    "mutation",
    [
        "dependency_non_path",
        "invalid_position",
        "unhashable_position",
        "invalid_instruction_type",
        "instruction_too_long",
        "model_not_string",
        "effort_not_string",
        "timeout_not_integer",
        "timeout_not_positive_literal",
        "invalid_delivery",
        "phased_delivery_unsupported",
        "materialization_attempts_unsupported",
    ],
)
def test_provider_dependencies_and_policy_reject_typed_operand_tampering(mutation):
    string = {"kind": "primitive", "name": "String"}
    path = {
        "kind": "path",
        "name": "sample::PromptDependency",
        "under": "docs",
        "must_exist_target": True,
    }
    tree, provider = _provider_operand_tree()
    tree["types"][path["name"]] = deepcopy(path)
    tree["params"] = [["document", deepcopy(path)]]
    provider["dependencies"] = {
        "required": [_name("document")],
        "optional": [],
        "position": "append",
        "instruction": None,
    }
    provider["policy"] = {
        "model": _lit("model", string),
        "effort": _lit("high", string),
        "timeout_sec": _lit(60),
    }
    if mutation == "dependency_non_path":
        provider["dependencies"]["required"] = [_lit(7)]
    elif mutation == "invalid_position":
        provider["dependencies"]["position"] = "middle"
    elif mutation == "unhashable_position":
        provider["dependencies"]["position"] = ["prepend"]
    elif mutation == "invalid_instruction_type":
        provider["dependencies"]["instruction"] = 7
    elif mutation == "instruction_too_long":
        provider["dependencies"]["instruction"] = "x" * 261631
    elif mutation == "model_not_string":
        provider["policy"]["model"] = _lit(7)
    elif mutation == "effort_not_string":
        provider["policy"]["effort"] = _lit(7)
    elif mutation == "timeout_not_integer":
        provider["policy"]["timeout_sec"] = _lit("60", string)
    elif mutation == "timeout_not_positive_literal":
        provider["policy"]["timeout_sec"] = _name("timeout")
        tree["params"].append(["timeout", deepcopy(INT)])
    elif mutation == "invalid_delivery":
        provider["policy"]["delivery"] = _lit("unknown", string)
    elif mutation == "phased_delivery_unsupported":
        provider["policy"]["delivery"] = _lit("phased", string)
    elif mutation == "materialization_attempts_unsupported":
        provider["policy"]["materialization_attempts"] = _lit(2)
    tree["sites"] = [list(row) for row in assign_sites(tree)]

    _rule(tree, "effect_shape")


def test_provider_composed_policy_accepts_a_literal_composed_delivery():
    string = {"kind": "primitive", "name": "String"}
    tree, provider = _provider_operand_tree()
    provider["policy"] = {
        "delivery": _lit("composed", string),
    }
    tree["sites"] = [list(row) for row in assign_sites(tree)]

    validate(tree)


def test_result_path_requires_a_real_provider_binding_and_accepts_its_binder():
    tree, provider, path = _provider_result_path_tree()
    tree["body"] = {
            "k": "let",
            "name": "artifact",
            "value": provider,
            "body": {"k": "halt", "value": {"k": "result_path", "n": "artifact", "type": path}},
        }
    tree["sites"] = [list(row) for row in assign_sites(tree)]

    validate(tree)


def test_provider_effect_result_must_match_its_output_contract():
    tree, provider, _ = _provider_result_path_tree()
    tree["body"] = {"k": "let", "name": "answer", "value": provider, "body": _halt(_name("answer"))}
    tree["result"] = {"kind": "primitive", "name": "String"}
    tree["sites"] = [list(row) for row in assign_sites(tree)]
    validate(tree)

    tree, provider, _ = _provider_result_path_tree()
    provider["contract"]["payload"]["fields"][0]["type"] = "integer"
    tree["body"] = {"k": "let", "name": "answer", "value": provider, "body": _halt(_name("answer"))}
    tree["result"] = {"kind": "primitive", "name": "String"}
    tree["sites"] = [list(row) for row in assign_sites(tree)]
    _rule(tree, "effect_result")


def _structured_provider_result_tree(result, contract):
    effect = {
        "k": "perform",
        "class": "provider",
        "result": deepcopy(result),
        "repeat": "rerun",
        "provider": "sample-provider",
        "prompt": {"template": "write", "fills": []},
        "inputs": [],
        "dependencies": None,
        "policy": None,
        "contract": deepcopy(contract),
    }
    tree = _tree({"k": "let", "name": "answer", "value": effect, "body": _halt(_name("answer"))})
    tree["result"] = deepcopy(result)
    tree["types"] = {}
    _register_nominal_types(result, tree["types"])
    tree["configuration"]["providers"] = {"sample-provider": {"provider_id": "sample-provider"}}
    tree["sites"] = [list(row) for row in assign_sites(tree)]
    return tree


def test_provider_effect_result_contract_flattens_records_by_structural_path():
    string = {"kind": "primitive", "name": "String"}
    integer = {"kind": "primitive", "name": "Int"}
    nested = {"kind": "record", "name": "sample::Details", "fields": [{"name": "title", "type": string}]}
    result = {
        "kind": "record",
        "name": "sample::Output",
        "fields": [{"name": "count", "type": integer}, {"name": "details", "type": nested}],
    }
    contract = {
        "kind": "output_bundle",
        "payload": {
            "fields": [
                {"name": "count", "json_pointer": "/count", "type": "integer"},
                {"name": "details__title", "json_pointer": "/details/title", "type": "string"},
            ],
        },
    }
    validate(_structured_provider_result_tree(result, contract))

    contract["payload"]["fields"][1]["json_pointer"] = "/title"
    _rule(_structured_provider_result_tree(result, contract), "effect_result")


def test_provider_effect_result_contract_orders_shared_and_variant_union_fields():
    string = {"kind": "primitive", "name": "String"}
    integer = {"kind": "primitive", "name": "Int"}
    boolean = {"kind": "primitive", "name": "Bool"}
    result = {
        "kind": "union",
        "name": "sample::Outcome",
        "variants": [
            {"name": "Ready", "fields": [{"name": "shared", "type": string}, {"name": "count", "type": integer}]},
            {"name": "Missing", "fields": [{"name": "shared", "type": string}, {"name": "note", "type": boolean}]},
        ],
    }
    contract = {
        "kind": "variant_output",
        "payload": {
            "discriminant": {"name": "variant", "json_pointer": "/variant", "type": "enum", "allowed": ["Ready", "Missing"]},
            "shared_fields": [{"name": "shared", "json_pointer": "/shared", "type": "string"}],
            "variants": {
                "Ready": {"fields": [{"name": "count", "json_pointer": "/count", "type": "integer"}]},
                "Missing": {"fields": [{"name": "note", "json_pointer": "/note", "type": "bool"}]},
            },
        },
    }
    validate(_structured_provider_result_tree(result, contract))

    reordered = deepcopy(contract)
    reordered["payload"]["shared_fields"].reverse()
    reordered["payload"]["variants"]["Ready"]["fields"].append(
        {"name": "shared", "json_pointer": "/shared", "type": "string"}
    )
    _rule(_structured_provider_result_tree(result, reordered), "effect_result")


def _command_result_tree():
    integer = {"kind": "primitive", "name": "Int"}
    command = {
        "k": "perform",
        "class": "command",
        "result": deepcopy(integer),
        "repeat": "rerun",
        "boundary": "fetch",
        "command": ["python", "probe.py"],
        "closure": [{"base": "workspace", "path": "probe.py"}],
        "contract": {
            "kind": "output_bundle",
            "payload": {"fields": [{"name": "__result__", "json_pointer": "", "type": "integer"}]},
        },
        "argv": [],
    }
    tree = _tree({"k": "let", "name": "answer", "value": command, "body": _halt(_name("answer"))})
    tree["configuration"]["commands"] = {"fetch": _external_command_row()}
    tree["sites"] = [list(row) for row in assign_sites(tree)]
    return tree, command


def _external_command_row():
    return {
        "kind": "external_tool",
        "name": "fetch",
        "stable_command": ["python", "probe.py"],
        "must_not_repeat": False,
        "closure": [{"base": "workspace", "path": "probe.py"}],
        "retirement_class": None,
        "retirement_label": None,
        "replacement_surface": None,
        "bridge_owner": None,
        "expiry_condition": None,
        "evidence_refs": [],
        "retirement_status": None,
    }


_PROMOTED_FIELDS = [
    "artifact_contracts",
    "behavior_class",
    "error_codes",
    "input_signature",
    "invocation_protocol",
    "owner_module",
    "replacement_path",
    "state_writes",
]


def _certified_command_row(*, signature=None):
    return {
        "kind": "certified_adapter",
        "name": "adapter-fetch",
        "stable_command": ["python", "adapter.py"],
        "must_not_repeat": False,
        "closure": [],
        "retirement_class": None,
        "retirement_label": None,
        "replacement_surface": None,
        "bridge_owner": None,
        "expiry_condition": None,
        "evidence_refs": [],
        "retirement_status": None,
        "input_contract": {"kind": "object"},
        "output_type_name": "Int",
        "effects": ["read"],
        "path_safety": {"safe": True},
        "source_map_behavior": "preserve",
        "fixture_ids": ["valid"],
        "negative_fixture_ids": ["invalid"],
        "behavior_class": "data_transform",
        "input_signature": signature if signature is not None else [
            {"name": "token", "type_name": "String", "required": True, "transport_key": "token_id"},
            {"name": "token", "type_name": "String", "required": False, "transport_key": "token_detail"},
            {"name": "mode", "type_name": "String", "required": False, "transport_key": "mode"},
            {"name": "target", "type_name": "String", "required": True, "transport_key": "target"},
        ],
        "artifact_contracts": ["output"],
        "state_writes": [],
        "error_codes": [],
        "owner_module": "sample.adapters",
        "replacement_path": None,
        "invocation_protocol": "json_object_positional_arg",
        "transition_binding": None,
        "view_binding": None,
        "declared_promoted_fields": list(_PROMOTED_FIELDS),
    }


def _document_command_tree(document_keys):
    command = {
        "k": "perform",
        "class": "command",
        "result": deepcopy(INT),
        "repeat": "rerun",
        "boundary": "adapter-fetch",
        "command": ["python", "adapter.py"],
        "closure": [],
        "contract": {
            "kind": "output_bundle",
            "payload": {"fields": [{"name": "__result__", "json_pointer": "", "type": "integer"}]},
        },
        "argv": [],
        "document": [[key, _lit(index)] for index, key in enumerate(document_keys)],
    }
    tree = _tree({"k": "let", "name": "answer", "value": command, "body": _halt(_name("answer"))})
    tree["configuration"]["commands"] = {"adapter-fetch": _certified_command_row()}
    tree["sites"] = [list(row) for row in assign_sites(tree)]
    return tree, command


def test_command_effect_checks_result_contract_and_complete_used_binding_facts():
    tree, command = _command_result_tree()
    validate(tree)

    wrong_type, command = _command_result_tree()
    command["result"] = {"kind": "primitive", "name": "String"}
    _rule(wrong_type, "effect_result")

    missing_closure, _ = _command_result_tree()
    del missing_closure["configuration"]["commands"]["fetch"]["closure"]
    _rule(missing_closure, "configuration_scope")


@pytest.mark.parametrize(
    "configuration",
    [
        {"commands": {}, "providers": {"provider": {"provider_id": "id", "alias": "forged"}}, "prompts": {}, "imports": {}},
        {"commands": {}, "providers": {}, "prompts": {"prompt": {"source_kind": "asset_file", "path": "p.md"}}, "imports": {}},
    ],
)
def test_resolved_configuration_extern_rows_have_exact_shapes(configuration):
    tree = _tree()
    tree["configuration"] = configuration
    _rule(tree, "configuration_scope")


def test_command_configuration_accepts_both_complete_binding_variants():
    tree = _tree()
    external = _external_command_row()
    certified = _certified_command_row()
    certified["closure"] = [{"base": "package:orchestrator", "path": "."}]
    tree["configuration"]["commands"] = {"fetch": external, "adapter-fetch": certified}
    validate(tree)


def test_document_command_accepts_forward_declared_promoted_metadata():
    tree, _ = _document_command_tree(["token_id", "token_detail", "target"])
    row = tree["configuration"]["commands"]["adapter-fetch"]
    row["declared_promoted_fields"].append("future_presence_token")
    row["declared_promoted_fields"].sort()
    validate(tree)


@pytest.mark.parametrize(
    "mutation",
    [
        "missing_field",
        "extra_field",
        "bool_int",
        "noncanonical_closure",
        "wrong_closure_origin",
        "malformed_input_signature",
        "bool_renderer_version",
        "unsorted_promoted_fields",
        "non_string_promoted_field",
        "unhashable_kind",
        "unhashable_closure_base",
    ],
)
def test_command_configuration_rejects_row_shape_and_closure_tampering(mutation):
    tree = _tree()
    row = _certified_command_row()
    if mutation == "missing_field":
        del row["must_not_repeat"]
    elif mutation == "extra_field":
        row["origin"] = "injected"
    elif mutation == "bool_int":
        row["must_not_repeat"] = 0
    elif mutation == "noncanonical_closure":
        row["closure"] = [{"base": "workspace", "path": "a/./b"}]
    elif mutation == "wrong_closure_origin":
        row["closure"] = [{"base": "workspace", "path": "/tmp/input"}]
    elif mutation == "malformed_input_signature":
        row["input_signature"][0]["required"] = 1
    elif mutation == "bool_renderer_version":
        row["view_binding"] = {
            "view_name": "review",
            "renderer_id": "renderer",
            "renderer_version": True,
            "contract_role": "replacement_candidate",
        }
    elif mutation == "unsorted_promoted_fields":
        row["declared_promoted_fields"].reverse()
    elif mutation == "non_string_promoted_field":
        row["declared_promoted_fields"].append(3)
        row["declared_promoted_fields"].sort(key=str)
    elif mutation == "unhashable_kind":
        row["kind"] = []
    else:
        row["closure"] = [{"base": [], "path": "probe.py"}]
    tree["configuration"]["commands"] = {"adapter-fetch": row}
    _rule(tree, "configuration_scope")


@pytest.mark.parametrize(
    "keys",
    [
        ["token_id", "token_detail", "target"],
        ["token_id", "token_detail", "mode", "target"],
    ],
)
def test_document_command_uses_required_and_selected_optional_signature_rows(keys):
    tree, _ = _document_command_tree(keys)
    validate(tree)


@pytest.mark.parametrize(
    "keys",
    [
        ["token_detail", "token_id", "target"],
        ["token_id", "token_detail"],
        ["token_id", "token_detail", "unknown", "target"],
    ],
)
def test_document_command_rejects_wrong_signature_projection(keys):
    tree, _ = _document_command_tree(keys)
    _rule(tree, "configuration_scope")


def test_document_mode_requires_promoted_certified_metadata_and_empty_argv():
    tree, command = _document_command_tree(["token_id", "token_detail", "target"])
    row = tree["configuration"]["commands"]["adapter-fetch"]
    row["declared_promoted_fields"].remove("behavior_class")
    _rule(tree, "configuration_scope")

    tree, command = _document_command_tree(["token_id", "token_detail", "target"])
    command["argv"] = ["unexpected"]
    _rule(tree, "effect_shape")

    tree, command = _document_command_tree(["token_id", "token_detail", "target"])
    row = _external_command_row()
    row["stable_command"] = ["python", "adapter.py"]
    row["closure"] = []
    tree["configuration"]["commands"] = {"adapter-fetch": row}
    _rule(tree, "configuration_scope")


def test_result_path_origin_does_not_survive_shadowing_or_an_alias():
    tree, provider, path = _provider_result_path_tree()
    tree["body"] = {
            "k": "let",
            "name": "artifact",
            "value": provider,
            "body": {
                "k": "let",
                "name": "artifact",
                "value": _lit("ordinary", {"kind": "primitive", "name": "String"}),
                "body": {"k": "halt", "value": {"k": "result_path", "n": "artifact", "type": path}},
            },
        }
    tree["sites"] = [list(row) for row in assign_sites(tree)]
    _rule(tree, "provider_result_path")

    tree, provider, path = _provider_result_path_tree()
    tree["body"] = {
        "k": "let",
        "name": "artifact",
        "value": provider,
        "body": {
            "k": "let",
            "name": "alias",
            "value": {"k": "name", "n": "artifact"},
            "body": {"k": "halt", "value": {"k": "result_path", "n": "alias", "type": path}},
        },
    }
    tree["sites"] = [list(row) for row in assign_sites(tree)]
    _rule(tree, "provider_result_path")


def _register_nominal_types(descriptor, rows):
    if not isinstance(descriptor, dict):
        return
    kind = descriptor.get("kind")
    if kind in {"record", "union", "enum", "path"}:
        rows[descriptor["name"]] = deepcopy(descriptor)
    if kind in {"record", "variant_case"}:
        children = [field["type"] for field in descriptor.get("fields", [])]
    elif kind == "union":
        children = [
            field["type"]
            for variant in descriptor.get("variants", [])
            for field in variant.get("fields", [])
        ]
    elif kind in {"optional", "list"}:
        children = [descriptor["item"]]
    elif kind == "map":
        children = [descriptor["key"], descriptor["value"]]
    else:
        children = []
    for child in children:
        _register_nominal_types(child, rows)


def _run_ref_result_descriptor(generated_name, value_type=INT):
    return {
        "schema": RUN_REF_RESULT_CONTRACT_SCHEMA,
        "envelope": {
            "kind": "record",
            "name": generated_name,
            "fields": [
                {"name": "value", "type": deepcopy(value_type)},
                {"name": "workspace_delta", "type": _workspace_delta_descriptor()},
                {"name": "accounting", "type": _accounting_descriptor()},
            ],
        },
    }


def _build_run_ref_config(site_digest, input_rows=(), *, value_type=INT, bindings=None):
    input_rows = tuple(input_rows)
    inputs = tuple(
        RunRefInput(
            name=name,
            type_descriptor=descriptor,
            binding=ReferenceBinding((bindings or {}).get(name, f"inputs.{name}")),
            allow_nested_structures=True,
        )
        for name, descriptor in input_rows
    )
    result = _run_ref_result_descriptor(f"RunRefResult${site_digest[:16]}", value_type)
    program = PathProgram(
        path="child.orc",
        entry_name="run",
        return_refinement=deepcopy(value_type),
        allow_nested_structures=True,
    )
    config = build_run_ref_static_config(
        compiler_runtime_identity_digest="sha256:" + "a" * 64,
        site_digest=site_digest,
        source=SourceRequest(
            locator="file:///repo",
            commit="0123456789abcdef0123456789abcdef01234567",
        ),
        program=program,
        inputs=inputs,
        result_descriptor=result,
        result_digest=canonical_sha256(result),
        target_dsl_version=EVALUATED_EXECUTION_MIN_TARGET_DSL_VERSION,
    )
    return config


def _run_ref_tree(input_rows=(("source", INT),), *, value_type=INT, bindings=None, types=None):
    placeholder = _build_run_ref_config("0" * 64, input_rows, value_type=value_type, bindings=bindings)
    effect = {
        "k": "perform",
        "class": "run_ref",
        "result": placeholder.result_descriptor["envelope"],
        "repeat": "rerun",
        "config": base64.b64encode(encode_run_ref_static_config(placeholder)).decode("ascii"),
        "inputs": [[name, {"k": "name", "n": name}] for name, _ in input_rows],
    }
    body = {
        "k": "let",
        "name": "artifact",
        "value": effect,
        "body": _halt({"k": "name", "n": "artifact"}),
    }
    tree = _tree(body, result=placeholder.result_descriptor["envelope"])
    tree["params"] = [[name, deepcopy(descriptor)] for name, descriptor in input_rows]
    _register_nominal_types(placeholder.result_descriptor["envelope"], tree["types"])
    for descriptor in (types or {}).values():
        _register_nominal_types(descriptor, tree["types"])
    tree["types"].update(deepcopy(types or {}))
    assign_sites(tree)
    signature = canonical_run_ref_signature(
        [(row.name, row.type_descriptor) for row in placeholder.inputs],
        placeholder.result_descriptor,
        run_ref_signatures={},
    )
    site = effect["site"]
    digest = sha256(
        canonical_json_for_pure_value(
            ["workflow-lisp/run-ref-site/1", tree["entry"], site, signature]
        ).encode("utf-8")
    ).hexdigest()
    config = _build_run_ref_config(digest, input_rows, value_type=value_type, bindings=bindings)
    effect["config"] = base64.b64encode(encode_run_ref_static_config(config)).decode("ascii")
    effect["result"] = deepcopy(config.result_descriptor["envelope"])
    tree["result"] = deepcopy(config.result_descriptor["envelope"])
    tree["types"].pop(placeholder.generated_result_type, None)
    _register_nominal_types(config.result_descriptor["envelope"], tree["types"])
    tree["sites"] = [list(row) for row in assign_sites(tree)]
    return tree, effect, config


def test_run_ref_origin_signature_digest_inputs_and_fixed_types_are_checked():
    tree, effect, config = _run_ref_tree()
    validate(tree)

    wrong_digest = deepcopy(config.record)
    wrong_digest["site_digest"] = wrong_digest["site_digest"][:16] + "f" * 48
    effect["config"] = base64.b64encode(
        json.dumps(wrong_digest, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).decode("ascii")
    _rule(tree, "run_ref_digest")

    tree, effect, _ = _run_ref_tree((("first", INT), ("second", BOOL)))
    effect["inputs"].reverse()
    _rule(tree, "run_ref_config")

    tree, effect, _ = _run_ref_tree((("first", INT),), bindings={"first": "inputs.other"})
    _rule(tree, "run_ref_config")

    tree, effect, _ = _run_ref_tree()
    effect["inputs"][0][1] = _lit("not an Int", {"kind": "primitive", "name": "String"})
    _rule(tree, "type_mismatch")

    tree, effect, _ = _run_ref_tree()
    effect["inputs"][0][0] = "other"
    _rule(tree, "run_ref_config")


def _nested_run_ref_tree(*, tamper_nested_signature=False):
    first, config_a, signature_a = _generated_producer("producer_a", INT, "seed_a")
    generated_a = deepcopy(config_a.result_descriptor["envelope"])
    input_rows = (("source", generated_a),)
    placeholder_b = _build_run_ref_config("0" * 64, input_rows)
    signature_for_b = deepcopy(signature_a)
    if tamper_nested_signature:
        signature_for_b["inputs"] = [["forged_nested_argument", deepcopy(INT)]]
    signature_b = canonical_run_ref_signature(
        [(row.name, row.type_descriptor) for row in placeholder_b.inputs],
        placeholder_b.result_descriptor,
        run_ref_signatures={config_a.generated_result_type: signature_for_b},
    )
    digest_b = sha256(
        canonical_json_for_pure_value(
            ["workflow-lisp/run-ref-site/1", "workflow:sample::run", "producer_b", signature_b]
        ).encode("utf-8")
    ).hexdigest()
    config_b = _build_run_ref_config(digest_b, input_rows)
    second = {
        "k": "perform",
        "class": "run_ref",
        "result": deepcopy(config_b.result_descriptor["envelope"]),
        "repeat": "rerun",
        "config": base64.b64encode(encode_run_ref_static_config(config_b)).decode("ascii"),
        "inputs": [["source", _name("producer_a")]],
    }
    tree = _tree(
        {
            "k": "let", "name": "producer_a", "value": first,
            "body": {
                "k": "let", "name": "producer_b", "value": second,
                "body": _halt(_name("producer_b")),
            },
        },
        result=config_b.result_descriptor["envelope"],
    )
    tree["params"] = [["seed_a", deepcopy(INT)]]
    _register_nominal_types(config_a.result_descriptor["envelope"], tree["types"])
    _register_nominal_types(config_b.result_descriptor["envelope"], tree["types"])
    tree["sites"] = [list(row) for row in assign_sites(tree)]
    return tree, second


def test_nested_run_ref_input_uses_the_producer_signature_and_rejects_a_changed_s():
    tree, _ = _nested_run_ref_tree()
    validate(tree)

    changed, _ = _nested_run_ref_tree(tamper_nested_signature=True)
    with pytest.raises(CheckedFormError) as excinfo:
        validate(changed)
    assert excinfo.value.rule == "run_ref_digest"


def test_run_ref_type_table_matches_the_checked_fixed_result_records():
    tree, _, _ = _run_ref_tree()
    tree["types"]["WorkspaceDelta"]["fields"][0]["name"] = "forged"
    _rule(tree, "nominal_definition")


def test_run_ref_origin_rejects_missing_and_duplicate_generated_producers():
    tree, effect, config = _run_ref_tree()
    tree["body"] = _halt(_lit(0))
    tree["result"] = deepcopy(INT)
    tree["sites"] = [list(row) for row in assign_sites(tree)]
    _rule(tree, "run_ref_origin")

    tree, effect, _ = _run_ref_tree()
    duplicate = deepcopy(effect)
    tree["body"] = {
        "k": "let",
        "name": "artifact",
        "value": effect,
        "body": {"k": "let", "name": "again", "value": duplicate, "body": _halt(_lit(0))},
    }
    tree["result"] = deepcopy(INT)
    tree["sites"] = [list(row) for row in assign_sites(tree)]
    _rule(tree, "run_ref_origin")


def test_run_ref_origin_cycles_include_phantom_applied_identity_dependencies():
    digest_a = "a" * 64
    digest_b = "b" * 64
    generated_a = f"RunRefResult${digest_a[:16]}"
    generated_b = f"RunRefResult${digest_b[:16]}"
    wrapper_a = {"kind": "record", "name": f"sample::Wrapper[{generated_a}]", "fields": []}
    wrapper_b = {"kind": "record", "name": f"sample::Wrapper[{generated_b}]", "fields": []}
    config_a = _build_run_ref_config(digest_a, (("from_b", wrapper_b),))
    config_b = _build_run_ref_config(digest_b, (("from_a", wrapper_a),))

    def effect(config, input_name):
        return {
            "k": "perform",
            "class": "run_ref",
            "result": deepcopy(config.result_descriptor["envelope"]),
            "repeat": "rerun",
            "config": base64.b64encode(encode_run_ref_static_config(config)).decode("ascii"),
            "inputs": [[input_name, {"k": "name", "n": input_name}]],
        }

    body = {
        "k": "let",
        "name": "first",
        "value": effect(config_a, "from_b"),
        "body": {
            "k": "let",
            "name": "second",
            "value": effect(config_b, "from_a"),
            "body": _halt(_lit(0)),
        },
    }
    tree = _tree(body)
    tree["params"] = [["from_b", wrapper_b], ["from_a", wrapper_a]]
    _register_nominal_types(wrapper_a, tree["types"])
    _register_nominal_types(wrapper_b, tree["types"])
    _register_nominal_types(config_a.result_descriptor["envelope"], tree["types"])
    _register_nominal_types(config_b.result_descriptor["envelope"], tree["types"])
    tree["sites"] = [list(row) for row in assign_sites(tree)]

    _rule(tree, "run_ref_cycle")
