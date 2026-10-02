from copy import deepcopy
import json

import pytest

from orchestrator.workflow_lisp.closed.names import canonical_callee_name_from_key, _normalize_closed_value
from orchestrator.workflow_lisp.closed.program import ClosedProgram, ClosedProgramInvalid, program_digest
from orchestrator.workflow_lisp.closed.sites import assign_sites
from tests.test_workflow_lisp_closed_program_check import _tree, _halt, _lit
from tests.test_workflow_lisp_shared_field_relation import INT, STRING, checker, record, union, case, path


def readback(tree):
    tree["sites"] = [list(row) for row in assign_sites(tree)]
    digest = program_digest(tree)
    result = ClosedProgram.from_artifact(json.dumps(tree))
    assert result.digest == digest
    return result


def field_tree(actual, target, *, path_segments=("selection",), key_domain=False, value=None):
    owner = {"kind": "union", "name": "entry::Outer", "variants": [
        {"name": tag, "fields": [{"name": "selection", "type": actual}]} for tag in ("LEFT", "RIGHT")]}
    tree = _tree(result=target)
    tree["types"] = deepcopy(checker(owner, target).types)
    field = {"k": "field", "base": {"k": "name", "n": "value"},
             "path": list(path_segments), "shared": [deepcopy(target), *[None] * (len(path_segments) - 1)]}
    if not key_domain:
        tree["params"] = [["value", owner]]
        tree["body"] = _halt(field)
    else:
        field["base"] = {"k": "inject", "type": owner, "variant": "LEFT", "fields": [["selection", value]]}
        tree["result"] = INT
        key = ["sample", "procedure", "probe", [], [], [], [["selected", deepcopy(target), _normalize_closed_value(field)]], [], {"params": [], "result": INT}]
        name = canonical_callee_name_from_key(key)
        tree["definitions"] = {name: {"key": key, "params": [], "result": INT, "body": _halt()}}
    return tree, field


def rekey(tree):
    definitions = {}
    for old_name, definition in tree["definitions"].items():
        new_name = canonical_callee_name_from_key(definition["key"])
        definitions[new_name] = definition
        for node in tree["body"].values():
            if isinstance(node, dict) and node.get("callee") == old_name:
                node["callee"] = new_name
    tree["definitions"] = definitions


@pytest.mark.parametrize("key_domain", [False, True])
@pytest.mark.parametrize("shared", [[], [None], [INT, None], "wrong"])
def test_malformed_shared_is_rejected_after_identity_update(key_domain, shared):
    tree, field = field_tree(INT, INT, key_domain=key_domain, value=_lit(7))
    if key_domain:
        field = next(iter(tree["definitions"].values()))["key"][6][0][2]
    field["shared"] = shared
    rekey(tree)
    with pytest.raises(ClosedProgramInvalid) as error:
        readback(tree)
    assert error.value.rule == ("definition_key" if key_domain else "node_shape")


@pytest.mark.parametrize("key_domain", [False, True])
@pytest.mark.parametrize("target,expected", [(path("helper::Other", root="other"), False),
    (path("helper::Required", exists=True), False), (path("helper::OtherName"), True)])
def test_path_targets_require_correct_root_and_no_strengthening(key_domain, target, expected):
    actual = path("entry::Optional")
    tree, _ = field_tree(actual, target, key_domain=key_domain, value=_lit("state/report", actual))
    if expected:
        readback(tree)
    else:
        with pytest.raises(ClosedProgramInvalid) as error:
            readback(tree)
        assert error.value.rule == ("definition_key" if key_domain else "field_path")


@pytest.mark.parametrize("key_domain", [False, True])
@pytest.mark.parametrize("target", [record("helper::Payload", INT), record("helper::Different")])
def test_valid_catalog_target_cannot_hide_recursive_or_basename_mismatch(key_domain, target):
    actual = record("entry::Payload")
    value = {"k": "record", "type": actual, "fields": [["item", _lit("seed", STRING)]]}
    tree, _ = field_tree(actual, target, key_domain=key_domain, value=value)
    with pytest.raises(ClosedProgramInvalid) as error:
        readback(tree)
    assert error.value.rule == ("definition_key" if key_domain else "field_path")


@pytest.mark.parametrize("active", ["A", "B"])
@pytest.mark.parametrize("key_domain", [False, True])
def test_catalog_valid_case_target_never_fabricates_activity(active, key_domain):
    inner = {"kind": "union", "name": "entry::Inner", "variants": [
        {"name": "A", "fields": [{"name": "a", "type": STRING}]},
        {"name": "B", "fields": [{"name": "b", "type": INT}]}]}
    actual_value = {"k": "inject", "type": inner, "variant": active,
                    "fields": [["a", _lit("safe", STRING)]] if active == "A" else [["b", _lit(7)]]}
    tree, _ = field_tree(inner, case(inner, "B"), path_segments=("selection", "b"), key_domain=key_domain, value=actual_value if key_domain else None)
    tree["result"] = INT
    if key_domain:
        definition = next(iter(tree["definitions"].values()))
        definition["key"][6][0][1] = INT
        rekey(tree)
    else:
        tree["defaults"] = {"value": {"variant": "LEFT", "selection": {"variant": active, "a": "safe"} if active == "A" else {"variant": active, "b": 7}}}
    with pytest.raises(ClosedProgramInvalid) as error:
        readback(tree)
    assert error.value.rule == ("definition_key" if key_domain else "field_path")


def test_removing_redundant_int_proof_keeps_ordinary_wire_valid():
    tree, field = field_tree(INT, INT)
    first = readback(tree)
    del field["shared"]
    second = readback(tree)
    assert first.digest != second.digest


@pytest.mark.parametrize("segment", ["variant", "missing"])
def test_shared_cannot_certify_discriminant_or_missing_field(segment):
    tree, field = field_tree(INT, INT)
    field["path"] = [segment]
    with pytest.raises(ClosedProgramInvalid) as error:
        readback(tree)
    assert error.value.rule == "field_path"


@pytest.mark.parametrize("key_domain", [False, True])
@pytest.mark.parametrize("mutation,rule", [
    ("extra", "node_shape"), ("scalar", "field_path"), ("record", "field_path"),
    ("case", "field_path"), ("missing-variant", "field_path"),
    ("forged", "nominal_definition"), ("suffix", "field_path"), ("absent", "field_path"), ("null", "field_path"),
])
def test_shared_body_and_key_contract_failures_use_updated_identity(key_domain, mutation, rule):
    actual, target = path("entry::Actual", exists=True), path("helper::View")
    tree, field = field_tree(actual, target, key_domain=key_domain, value=_lit("state/item", actual))
    if key_domain:
        field = next(iter(tree["definitions"].values()))["key"][6][0][2]
    owner = tree["types"]["entry::Outer"]
    if mutation == "extra":
        field["unexpected"] = True
    elif mutation in {"scalar", "record", "case"}:
        _replace_field_base(tree, field, actual, owner, mutation, key_domain)
    elif mutation == "missing-variant":
        owner["variants"][1]["fields"] = []
        if key_domain:
            field["base"]["type"] = deepcopy(owner)
        else:
            tree["params"][0][1] = deepcopy(owner)
    elif mutation == "forged":
        field["shared"][0]["under"] = "forged"
    elif mutation == "suffix":
        field["path"].append("missing")
        field["shared"].append(None)
    else:
        other = path("entry::Another", exists=True)
        tree["types"][other["name"]] = other
        owner["variants"][1]["fields"][0]["type"] = other
        if key_domain:
            field["base"]["type"] = deepcopy(owner)
        else:
            tree["params"][0][1] = deepcopy(owner)
        if mutation == "null":
            field["path"] = ["selection", "missing"]
            field["shared"] = [None, INT]
        else:
            del field["shared"]
    rekey(tree)
    with pytest.raises(ClosedProgramInvalid) as error:
        readback(tree)
    assert error.value.rule == ("definition_key" if key_domain else rule)


def test_ordinary_case_binding_can_feed_shared_proved_case_then_forget_proof():
    inner = union("entry::Inner")
    proven = case(inner, "A")
    outer = union("entry::Outer", proven)
    tree = _tree(result=inner)
    tree["types"] = deepcopy(checker(inner, outer).types)
    tree["params"] = [["source", inner]]
    projection = {"k": "field", "base": {"k": "inject", "type": outer, "variant": "B",
        "fields": [["item", {"k": "name", "n": "proved"}]]}, "path": ["item"], "shared": [inner]}
    tree["body"] = {"k": "case", "subject": {"k": "name", "n": "source"}, "arms": [
        {"variant": "A", "bind": "proved", "body": _halt(projection)},
        {"variant": "B", "bind": "other", "body": _halt({"k": "name", "n": "source"})}]}
    program = readback(tree)
    from orchestrator.workflow.evaluated.machine import evaluate_closed_program
    result = evaluate_closed_program(program, {"source": {"variant": "A", "item": "safe"}})
    from orchestrator.workflow.pure_expr import canonical_json_for_pure_value
    assert canonical_json_for_pure_value(result.descriptor) == canonical_json_for_pure_value(inner)
    assert result.value == {"variant": "A", "item": "safe"}


@pytest.mark.parametrize("key_domain", [False, True])
@pytest.mark.parametrize("wrapper", [lambda x: record("entry::Box", x),
    lambda x: {"kind": "list", "item": x}, lambda x: {"kind": "optional", "item": x},
    lambda x: {"kind": "map", "key": STRING, "value": x}])
def test_recursive_union_to_case_cannot_hide_in_checked_field(key_domain, wrapper):
    inner = union("entry::Inner")
    actual, target = wrapper(inner), wrapper(case(inner))
    if target["kind"] == "record":
        target["name"] = "helper::Box"
    raw = {"variant": "A", "item": "safe"}
    kind = actual["kind"]
    value = {"item": raw} if kind == "record" else [raw] if kind == "list" else {"key": raw} if kind == "map" else raw
    tree, _ = field_tree(actual, target, key_domain=key_domain, value=_lit(value, actual))
    with pytest.raises(ClosedProgramInvalid) as error:
        readback(tree)
    assert error.value.rule == ("definition_key" if key_domain else "field_path")


@pytest.mark.parametrize("tamper", [False, True])
def test_shared_closed_substitution_and_bound_reference_key_survive_alpha_projection(tamper):
    from tests.test_workflow_lisp_closed_program_check import _tree_with_key_reference
    actual, target = record("entry::Payload"), record("helper::Payload")
    _, expression = field_tree(actual, target, key_domain=True, value=_lit({"item": "safe"}, actual))
    closed = _normalize_closed_value(expression)
    assert closed["shared"] == [target]
    if tamper:
        closed["shared"] = [None]
    target_key = ["sample", "procedure", "target", [], [], [], [["value", target, closed]], [],
                  {"params": [], "result": INT}]
    reference = {"target": target_key, "residual": deepcopy(target_key[8]),
                 "bound": [["value", target, {"value": deepcopy(closed)}]]}
    tree, _ = _tree_with_key_reference(target_key, reference)
    tree["types"] = deepcopy(checker(expression["base"]["type"], target).types)
    if tamper:
        with pytest.raises(ClosedProgramInvalid) as error:
            readback(tree)
        assert error.value.rule == "definition_key"
    else:
        readback(tree)


def _replace_field_base(tree, field, actual, owner, mutation, key_domain):
    base_type = INT if mutation == "scalar" else record("entry::Container", actual) if mutation == "record" else case(owner, "LEFT")
    tree["types"].update(checker(owner, base_type).types)
    if key_domain:
        raw = {"scalar": 7, "record": {"item": "state/item"}, "case": {"variant": "LEFT", "selection": "state/item"}}[mutation]
        field["base"] = _lit(raw, base_type)
    else:
        tree["params"][0][1] = base_type
