"""Production admission contract for closed dynamic Workflow Lisp programs."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy

import pytest


INT = {"kind": "primitive", "name": "Int"}
BOOL = {"kind": "primitive", "name": "Bool"}


from tests.workflow_dynamic_helpers import _artifact, _invalid, _pointer, _read, _span, _text


@pytest.mark.parametrize('case_id', ('A01', 'A05', 'A08', 'A09', 'A11', 'A12', 'A13', 'A14', 'A15', 'A16', 'A17', 'A18'))
def test_original_admission_case(case_id):
    from tests.workflow_dynamic_helpers import _definition

    tree = _artifact({"k": "lit", "v": 1})
    if case_id == 'A01':
        program = _read(tree)
        reordered = _read(json.dumps(tree, indent=2, sort_keys=True))
        assert program.semantic_digest == reordered.semantic_digest
        assert program.provenance_digest == reordered.provenance_digest
        with pytest.raises(TypeError):
            program.definitions[program.entry]['body']['v'] = 2
        return
    if case_id == 'A05':
        _invalid(lambda: _read(_artifact({'k': 'fn', 'code': 'demo::forged', 'captures': []})))
        tree = _artifact(definitions={'demo::bad': _definition({'k': 'lit', 'v': 0})})
        tree['definitions']['demo::bad'] = {}
    elif case_id == 'A08':
        tree['schemas']['unused'] = {'kind': 'list', 'item': {'kind': 'what'}}
    elif case_id == 'A09':
        tree['schemas']['unused'] = {'kind': 'path', 'name': 'Path', 'under': 'root', 'must_exist_target': False}
    elif case_id == 'A11':
        tree = _artifact({'k': 'host_call', 'name': 'x'})
    elif case_id == 'A12':
        tree = _artifact({'k': 'import', 'path': 'x'})
    elif case_id == 'A13':
        for unused in (False, True):
            node = {'k': 'op', 'name': 'unknown', 'args': [{'k': 'lit', 'v': 1}]}
            _invalid(lambda: _read(_artifact(definitions={'demo::unused': _definition(node)}) if unused else _artifact(node)))
        return
    elif case_id == 'A14':
        tree = _artifact(definitions={'demo::duplicate': _definition({'k': 'lit', 'v': 0}, params=('x', 'x'))})
    elif case_id == 'A15':
        _invalid(lambda: _read('{'))
        tree = _artifact({'k': 'lit', 'v': '\ud800'})
        _invalid(lambda: _read(json.dumps(tree, ensure_ascii=True)))
        return
    elif case_id == 'A16':
        tree['definitions'][tree['entry']]['body']['extra'] = True
    elif case_id == 'A17':
        tree['definitions'][tree['entry']]['params'] = []
    elif case_id == 'A18':
        node = {'k': 'record', 'fields': [['x', {'k': 'lit', 'v': 1}], ['x', {'k': 'lit', 'v': 2}]]}
        for unused in (False, True):
            _invalid(lambda: _read(_artifact(definitions={'demo::unused': _definition(node)}) if unused else _artifact(node)))
        return
    _invalid(lambda: _read(tree))


def test_record_update_and_fail_exact_shapes_refuse_even_when_unreachable():
    from tests.workflow_dynamic_helpers import _definition

    base = {'k': 'record', 'fields': [['x', {'k': 'lit', 'v': 1}]]}
    nodes = [
        {'k': 'record-update', 'base': base, 'fields': []},
        {'k': 'record-update', 'base': base, 'fields': [['x', {'k': 'lit', 'v': 2}], ['x', {'k': 'lit', 'v': 3}]]},
        {'k': 'record-update', 'base': base, 'fields': [[1, {'k': 'lit', 'v': 2}]]},
        {'k': 'record-update', 'base': base, 'fields': [['x', {'k': 'lit', 'v': 2}]], 'extra': 1},
        {'k': 'fail', 'reason': ''}, {'k': 'fail', 'reason': 4},
        {'k': 'fail'}, {'k': 'fail', 'reason': 'x', 'payload': {'k': 'lit', 'v': 1}},
    ]
    for node in nodes:
        for unused in (False, True):
            _invalid(lambda: _read(_artifact(definitions={'demo::unused': _definition(node)}) if unused else _artifact(node)))


def test_production_program_round_trips_with_separate_semantic_and_provenance_pins():
    program = _read(_artifact())
    assert program.schema == "workflow-lisp/dynamic-program/1"
    assert program.entry == "demo::main"
    assert program.budget == 100
    assert program.definitions["demo::main"]["boundary"]["defaults"]["n"] == 3
    root_field = program.root_result_contract["payload"]["fields"][0]
    assert program.root_result_contract["kind"] == "output_bundle"
    assert root_field == {
        "name": "__result__",
        "json_pointer": "",
        "type": "integer",
    }
    restored = _read(program.artifact())
    assert restored.semantic_digest == program.semantic_digest
    assert restored.provenance_digest == program.provenance_digest
    with pytest.raises(TypeError):
        program.definitions["demo::other"] = {}


@pytest.mark.parametrize(
    "mutate",
    [
        lambda tree: tree.update(extra=True),
        lambda tree: tree.pop("source_map"),
        lambda tree: tree.update(schema="workflow-lisp/dynamic-spike/3"),
        lambda tree: tree.update(target="3.1"),
        lambda tree: tree.update(entry="missing::entry"),
    ],
)
def test_read_back_rejects_unknown_or_incomplete_production_envelopes(mutate):
    tree = _artifact()
    mutate(tree)
    _invalid(lambda: _read(tree))


def test_read_back_checks_every_body_and_resolves_lexical_code_and_capture_references():
    body = {
        "k": "if",
        "cond": {"k": "lit", "v": True},
        "then": {"k": "call", "callee": {"k": "fn", "code": "demo::helper", "captures": [{"k": "name", "n": "n"}]}, "args": []},
        "else": {"k": "lit", "v": 0},
    }
    helper = {
        "params": [],
        "captures": ["saved"],
        "body": {"k": "name", "n": "saved"},
        "owner": {"module": "demo", "asset_base": "."},
        "boundary": None,
    }
    program = _read(_artifact(body, definitions={"demo::helper": helper}))
    assert set(program.definitions) == {"demo::main", "demo::helper"}

    unreachable = _artifact(
        definitions={
            "demo::unused": {
                **helper,
                "body": {"k": "name", "n": "missing"},
            }
        }
    )
    _invalid(lambda: _read(unreachable))

    wrong_capture_arity = _artifact(
        body={"k": "fn", "code": "demo::helper", "captures": []},
        definitions={"demo::helper": helper},
    )
    _invalid(lambda: _read(wrong_capture_arity))


def test_entry_defaults_use_the_shared_strict_descriptor_kernel():
    assert _read(_artifact(defaults={"n": 9})).definitions["demo::main"]["boundary"]["defaults"]["n"] == 9
    _invalid(lambda: _read(_artifact(defaults={"n": True})))
    _invalid(lambda: _read(_artifact(defaults={"unknown": 9})))
    _invalid(lambda: _read(_artifact(defaults={"n": float("inf")})))


def test_path_and_variant_case_schemas_keep_the_shared_transport_boundary():
    from orchestrator.workflow_lisp.dynamic.program import schema_reference

    path = {
        "kind": "path",
        "name": "demo::InputPath",
        "under": "workspace",
        "must_exist_target": False,
    }
    variant_case = {
        "kind": "variant_case",
        "union_name": "demo::Choice",
        "variant": "ready",
        "fields": [{"name": "value", "type": INT}],
    }
    union = {
        "kind": "union",
        "name": "demo::Choice",
        "variants": [{"name": "ready", "fields": [{"name": "value", "type": INT}]}],
    }
    path_ref = schema_reference(path)
    variant_case_ref = schema_reference(variant_case)
    union_ref = schema_reference(union)
    tree = _artifact()
    tree["schemas"][path_ref] = path
    tree["schemas"][union_ref] = union
    tree["schemas"][variant_case_ref] = variant_case
    program = _read(tree)
    assert program.schemas[path_ref]["kind"] == "path"
    assert program.schemas[variant_case_ref]["kind"] == "variant_case"

    path_boundary = _artifact(defaults={"n": "inputs/source.json"})
    path_boundary["schemas"][path_ref] = path
    path_boundary["definitions"]["demo::main"]["boundary"]["params"][0][1] = path_ref
    path_boundary["definitions"]["demo::main"]["boundary"]["result"] = path_ref
    assert _read(path_boundary).schemas[path_ref]["kind"] == "path"

    bad_path_default = _artifact(defaults={"n": 3})
    bad_path_default["schemas"][path_ref] = path
    bad_path_default["definitions"]["demo::main"]["boundary"]["params"][0][1] = path_ref
    _invalid(lambda: _read(bad_path_default))

    bad_variant_default = _artifact(defaults={"n": {"variant": "missing"}})
    bad_variant_default["schemas"][union_ref] = union
    bad_variant_default["schemas"][variant_case_ref] = variant_case
    bad_variant_default["definitions"]["demo::main"]["boundary"]["params"][0][1] = union_ref
    error = _invalid(lambda: _read(bad_variant_default))
    assert "does not match its declared schema" in str(error)


@pytest.mark.parametrize(
    ("kind", "descriptor"),
    [
        (
            "record",
            {
                "kind": "record",
                "name": "demo::Payload",
                "fields": [{"name": "count", "type": INT}],
            },
        ),
        (
            "union",
            {
                "kind": "union",
                "name": "demo::Outcome",
                "variants": [
                    {"name": "ready", "fields": [{"name": "count", "type": INT}]},
                    {"name": "empty", "fields": []},
                ],
            },
        ),
    ],
)
def test_root_result_contract_uses_the_shared_native_record_and_union_schema(kind, descriptor):
    from orchestrator.workflow_lisp.dynamic.program import schema_reference
    from orchestrator.workflow.evaluated.values import _thaw
    from orchestrator.workflow.type_descriptor import transport_schema_for_descriptor

    reference = schema_reference(descriptor)
    tree = _artifact(schemas={"Int": INT, "Bool": BOOL, reference: descriptor}, result=reference)
    field = _thaw(_read(tree).root_result_contract)["payload"]["fields"][0]
    assert field == {
        "name": "__result__",
        "json_pointer": "",
        **transport_schema_for_descriptor(descriptor, allow_nested_structures=True),
    }


def test_read_back_rejects_conflicting_embedded_nominal_definitions():
    from orchestrator.workflow_lisp.dynamic.program import schema_reference

    registered = {
        "kind": "record",
        "name": "demo::Payload",
        "fields": [{"name": "count", "type": INT}],
    }
    conflicting = {
        "kind": "record",
        "name": "demo::Payload",
        "fields": [{"name": "label", "type": {"kind": "primitive", "name": "String"}}],
    }
    reference = schema_reference(registered)
    holder = {
        "kind": "record",
        "name": "demo::Holder",
        "fields": [{"name": "payload", "type": conflicting}],
    }
    tree = _artifact(
        schemas={"Int": INT, "Bool": BOOL, reference: registered, "demo::Holder": holder},
        result="demo::Holder",
    )
    error = _invalid(lambda: _read(tree))
    assert "differs from its catalog definition" in str(error)


def test_read_back_rejects_variant_case_that_differs_from_its_catalog_union():
    from orchestrator.workflow_lisp.dynamic.program import schema_reference

    union = {
        "kind": "union",
        "name": "demo::Choice",
        "variants": [{"name": "ready", "fields": [{"name": "value", "type": INT}]}],
    }
    conflicting_case = {
        "kind": "variant_case",
        "union_name": "demo::Choice",
        "variant": "ready",
        "fields": [{"name": "value", "type": {"kind": "primitive", "name": "String"}}],
    }
    tree = _artifact()
    tree["schemas"][schema_reference(union)] = union
    tree["schemas"][schema_reference(conflicting_case)] = conflicting_case
    error = _invalid(lambda: _read(tree))
    assert "differs from its registered union variant" in str(error)


def test_read_back_rejects_forged_schema_owner_and_definition_references():
    tree = _artifact()
    tree["definitions"]["demo::main"]["boundary"]["params"][0][1] = "missing::type"
    _invalid(lambda: _read(tree))

    tree = _artifact()
    tree["definitions"]["demo::main"]["boundary"]["result"] = "missing::type"
    _invalid(lambda: _read(tree))

    tree = _artifact()
    tree["definitions"]["demo::main"]["owner"]["module"] = "other"
    _invalid(lambda: _read(tree))

    tree = _artifact()
    tree["definitions"]["demo::main"]["unchecked"] = True
    _invalid(lambda: _read(tree))

    tree = _artifact()
    tree["definitions"]["demo::main"]["body"] = {
        "k": "fn",
        "code": "unknown::callback",
        "captures": [],
    }
    _invalid(lambda: _read(tree))


def test_read_back_requires_complete_source_and_boundary_provenance_coverage():
    tree = _artifact()
    tree["source_map"]["entries"].pop("/definitions/demo::main/body")
    _invalid(lambda: _read(tree))

    tree = _artifact()
    tree["source_map"]["entries"]["/unknown"] = {
        "source": "demo",
        "span": _span(),
        "form_path": ["workflow-lisp"],
    }
    _invalid(lambda: _read(tree))

    tree = _artifact()
    tree["source_map"]["entries"]["/definitions/demo::main/body"]["source"] = "missing"
    _invalid(lambda: _read(tree))

    for subject in (
        "/definitions/demo::main",
        "/definitions/demo::main/boundary/params/0",
        "/definitions/demo::main/boundary/defaults/n",
        "/definitions/demo::main/boundary/result",
    ):
        tree = _artifact()
        tree["source_map"]["entries"].pop(subject)
        _invalid(lambda tree=tree: _read(tree))


@pytest.mark.parametrize(
    ("start", "end"),
    [
        (
            {"path": "demo/main.orc", "line": 1, "column": 10, "offset": 100},
            {"path": "demo/main.orc", "line": 2, "column": 1, "offset": 1},
        ),
        (
            {"path": "demo/main.orc", "line": 2, "column": 4, "offset": 10},
            {"path": "demo/main.orc", "line": 2, "column": 4, "offset": 11},
        ),
    ],
)
def test_read_back_requires_source_spans_to_advance_in_location_and_offset(start, end):
    tree = _artifact()
    span = tree["source_map"]["entries"]["/definitions/demo::main/body"]["span"]
    span["start"] = start
    span["end"] = end
    _invalid(lambda: _read(tree))


def test_read_back_rejects_duplicate_source_root_and_relative_path_even_if_hashes_differ():
    tree = _artifact()
    tree["sources"]["demo-copy"] = {
        **tree["sources"]["demo"],
        "source_sha256": "sha256:" + "1" * 64,
    }
    error = _invalid(lambda: _read(tree))
    assert "duplicate source identity" in str(error)


@pytest.mark.parametrize("module", ["../demo", "/demo", "demo//entry", "demo/./entry"])
def test_read_back_rejects_noncanonical_source_module_ids_even_when_unused(module):
    tree = _artifact()
    tree["sources"][module] = {
        **tree["sources"]["demo"],
        "relative_path": "other/main.orc",
    }
    error = _invalid(lambda: _read(tree))
    assert "canonical relative logical path" in str(error)


@pytest.mark.parametrize("relative_path", ["other//main.orc", "other/./main.orc"])
def test_read_back_rejects_alias_source_relative_paths(relative_path):
    tree = _artifact()
    tree["sources"]["demo"]["relative_path"] = relative_path
    for row in tree["source_map"]["entries"].values():
        row["span"]["start"]["path"] = relative_path
        row["span"]["end"]["path"] = relative_path
    error = _invalid(lambda: _read(tree))
    assert "normalized path relative to its root" in str(error)


def test_read_back_requires_definition_asset_base_to_match_its_canonical_module_directory():
    tree = _artifact()
    tree["definitions"]["demo::main"]["owner"]["asset_base"] = "different/module"
    error = _invalid(lambda: _read(tree))
    assert "canonical module asset base" in str(error)


def test_semantic_identity_ignores_source_locations_but_provenance_identity_does_not():
    original = _read(_artifact())
    moved = _artifact()
    moved["source_map"]["entries"]["/definitions/demo::main/body"]["span"]["start"]["line"] = 7
    moved["source_map"]["entries"]["/definitions/demo::main/body"]["span"]["end"]["line"] = 7
    moved["sources"]["demo"]["source_sha256"] = "sha256:" + "1" * 64
    relocated = _read(moved)
    assert relocated.semantic_digest == original.semantic_digest
    assert relocated.provenance_digest != original.provenance_digest


def test_pure_admission_fails_closed_on_effects_and_unadmitted_bindings():
    _invalid(lambda: _read(_artifact(bindings={"commands": {"tool": {}}})))
    _invalid(lambda: _read(_artifact(body={"k": "effect", "name": "tool", "inputs": {}})))

    from orchestrator.workflow_lisp.dynamic.program import DynamicProgram

    _invalid(lambda: DynamicProgram.from_artifact({"host_callback": lambda: None}))


def test_strict_json_rejects_duplicate_keys_and_non_finite_values():
    duplicate_key = '{"schema":"workflow-lisp/dynamic-program/1","schema":"workflow-lisp/dynamic-program/1"}'
    _invalid(lambda: _read(duplicate_key))
    _invalid(lambda: _read('{"not":"a complete artifact","number":NaN}'))


STRING = {"kind": "primitive", "name": "String"}
VALUE = {"kind": "primitive", "name": "Value"}
INPUT = {"kind": "record", "name": "demo::Input", "fields": [{"name": "payload", "type": INT}]}


def _native_contract(descriptor):
    from orchestrator.workflow.type_descriptor import transport_schema_for_descriptor
    return {"kind": "output_bundle", "payload": {"fields": [
        {"name": "__result__", "json_pointer": "", **transport_schema_for_descriptor(descriptor, allow_nested_structures=True)}
    ]}}


def _binding(module="demo", *, commands=None, providers=None, prompts=None, types=None):
    from orchestrator.workflow_lisp.closed.program import logical_asset_base_for_module
    return {"owner": {"module": module, "asset_base": logical_asset_base_for_module(module)},
            "configuration": {"commands": commands or {}, "providers": providers or {}, "prompts": prompts or {}},
            "types": types or {}}


def _command_fixture(*, certified=False, document=False, result=INT):
    from tests.test_workflow_lisp_closed_program_check import _external_command_row, _certified_command_row
    row = _certified_command_row(signature=[{"name": "payload", "type_name": "Int", "required": True, "transport_key": "payload"}]) if certified else _external_command_row()
    name = row["name"]
    node = {"k": "perform", "class": "command", "result": deepcopy(result), "repeat": "rerun",
            "boundary": name, "command": row["stable_command"], "closure": row["closure"],
            "contract": _native_contract(result), "argv": []}
    schemas = {"Int": INT, "Bool": BOOL, "String": STRING, "Value": VALUE, INPUT["name"]: INPUT}
    if result != INT:
        from orchestrator.workflow_lisp.dynamic.program import schema_reference
        schemas[schema_reference(result)] = result
    if document or certified:
        node["document"] = [["payload", {"k": "name", "n": "n"}]]
    if document and not certified:
        node["input_type"] = INPUT
    tree = _artifact(node, schemas=schemas, bindings={"demo": _binding(commands={name: row}, types={"Int": "Int"} if certified else {})})
    return tree, node, row


def _provider_fixture(*, composed=True, prompt_module="demo"):
    owner = _binding(prompt_module)["owner"]
    prompt = {"template": "{payload}", "fills": [
        {"name": "payload", "kind": "value", "type": VALUE, "value": {"k": "name", "n": "n"},
         "renderer_id": "canonical-json", "output_role": None, "placeholder_ordinals": [0]}
    ]} if composed else {"source_kind": "asset_file", "path": "prompt.md", "asset_base": owner["asset_base"]}
    node = {"k": "perform", "class": "provider", "result": INT, "repeat": "rerun",
            "provider": "provider-id", "prompt_owner": owner, "prompt": prompt,
            "inputs": [], "dependencies": None, "policy": None, "contract": _native_contract(INT)}
    bindings = {"demo": _binding(providers={"providers.run": {"provider_id": "provider-id"}})}
    if prompt_module not in bindings:
        bindings[prompt_module] = _binding(prompt_module)
    if not composed:
        bindings[prompt_module]["configuration"]["prompts"] = {"prompts.run": deepcopy(prompt)}
    return _artifact(node, schemas={"Int": INT, "Bool": BOOL, "String": STRING, "Value": VALUE}, bindings=bindings), node


@pytest.mark.parametrize("kind", ["command", "document", "certified", "composed", "extern"])
def test_static_effect_payloads_round_trip_without_typed_sites_or_host_registry(kind):
    tree, *_ = (_provider_fixture(composed=kind == "composed") if kind in {"composed", "extern"}
                else _command_fixture(certified=kind == "certified", document=kind == "document"))
    program = _read(tree)
    assert _read(program.artifact()).semantic_digest == program.semantic_digest
    assert "site" not in program.definitions[program.entry]["body"]


@pytest.mark.parametrize("mutation", [
    lambda tree, node, row: node.update(site="forged"),
    lambda tree, node, row: node.update(**{"@": {}}),
    lambda tree, node, row: node.update(argv_transport=[]),
    lambda tree, node, row: node.pop("argv"),
    lambda tree, node, row: node.update(**{"class": "run_ref"}),
    lambda tree, node, row: node.update(command=["different"]),
    lambda tree, node, row: node.update(closure=[]),
    lambda tree, node, row: node.update(repeat="never"),
    lambda tree, node, row: node.update(boundary="unknown"),
    lambda tree, node, row: node["contract"]["payload"]["fields"][0].update(type="boolean"),
    lambda tree, node, row: node["contract"]["payload"].update(path="forged.json"),
    lambda tree, node, row: node.update(argv=[7]),
    lambda tree, node, row: node.update(argv=[{"k": "name", "n": "unbound"}]),
])
def test_command_static_tampering_is_rejected_in_unreachable_bodies(mutation):
    from tests.workflow_dynamic_helpers import _definition
    tree, node, row = _command_fixture()
    mutation(tree, node, row)
    tree["definitions"]["demo::unused"] = _definition(node)
    tree["definitions"][tree["entry"]]["body"] = {"k": "lit", "v": 0}
    error = _invalid(lambda: _read(tree))
    assert error.location != "/source_map/entries"


@pytest.mark.parametrize("mutation", [
    lambda tree: tree["bindings"]["demo"].update(extra=True),
    lambda tree: tree["bindings"]["demo"]["owner"].update(module="unknown"),
    lambda tree: tree["bindings"]["demo"]["owner"].update(asset_base="other"),
    lambda tree: tree["bindings"]["demo"]["configuration"].update(imports={}),
    lambda tree: tree["bindings"]["demo"]["configuration"]["commands"]["fetch"].update(extra=True),
    lambda tree: tree["bindings"]["demo"]["configuration"]["commands"]["fetch"].update(stable_command=[]),
    lambda tree: tree["bindings"]["demo"]["configuration"]["commands"]["fetch"].update(closure=[{"base": "workspace", "path": "./probe.py"}]),
    lambda tree: tree["bindings"]["demo"]["types"].update(Int="missing"),
    lambda tree: tree["bindings"]["demo"]["types"].update(Int="Int"),
])
def test_bindings_require_canonical_owners_configuration_and_only_used_type_associations(mutation):
    tree, *_ = _command_fixture()
    mutation(tree)
    _invalid(lambda: _read(tree))


def test_certified_type_associations_are_declared_aliases_and_match_the_result():
    tree, node, row = _command_fixture(certified=True)
    row["input_signature"][0]["type_name"] = "shared.Payload"
    tree["bindings"]["demo"]["types"]["shared.Payload"] = INPUT["name"]
    assert _read(tree).bindings["demo"]["types"]["shared.Payload"] == INPUT["name"]
    missing = deepcopy(tree)
    missing["bindings"]["demo"]["types"].pop("shared.Payload")
    _invalid(lambda: _read(missing))
    node["result"] = BOOL
    node["contract"] = _native_contract(BOOL)
    _invalid(lambda: _read(tree))


def test_certified_type_associations_cannot_rebind_reserved_primitive_names():
    tree, node, _ = _command_fixture(certified=True)
    tree["bindings"]["demo"]["types"]["Int"] = "Bool"
    node["result"] = BOOL
    node["contract"] = _native_contract(BOOL)
    _invalid(lambda: _read(tree))


@pytest.mark.parametrize("mutation", [
    lambda node: node.pop("input_type"),
    lambda node: node.pop("document"),
    lambda node: node.update(input_type=INT),
    lambda node: node.update(document=[]),
    lambda node: node["document"].append(deepcopy(node["document"][0])),
    lambda node: node["document"][0].__setitem__(0, "unknown"),
])
def test_external_document_requires_an_exact_declared_record(mutation):
    tree, node, _ = _command_fixture(document=True)
    mutation(node)
    _invalid(lambda: _read(tree))


def test_certified_document_uses_signature_order_and_forbids_external_input_type():
    tree, node, _ = _command_fixture(certified=True)
    node["document"][0][0] = "other"
    _invalid(lambda: _read(tree))
    tree, node, _ = _command_fixture(certified=True)
    node["input_type"] = INPUT
    _invalid(lambda: _read(tree))


@pytest.mark.parametrize("mutation", [
    lambda node: node.update(inputs=[["data", "canonical-json", {"k": "name", "n": "n"}]]),
    lambda node: node.update(provider="unknown"),
    lambda node: node.update(repeat="never"),
    lambda node: node["prompt"]["fills"][0].update(renderer_id="wrong"),
    lambda node: node["prompt"]["fills"][0].update(placeholder_ordinals=[]),
    lambda node: node["prompt"]["fills"][0].update(value=7),
    lambda node: node["prompt"]["fills"][0].update(type={"kind": "primitive", "name": "Provider"}),
    lambda node: node.update(policy={"timeout_sec": {"k": "lit", "v": True}}),
    lambda node: node.update(policy={"timeout_sec": {"k": "name", "n": "n"}}),
    lambda node: node.update(policy={"delivery": {"k": "lit", "v": "other"}}),
    lambda node: node.update(policy={"materialization_attempts": {"k": "lit", "v": 1}}),
    lambda node: node.update(dependencies={"required": [None], "optional": [], "position": "prepend", "instruction": None}),
])
def test_provider_static_tampering_never_hides_malformed_operands(mutation):
    tree, node = _provider_fixture()
    mutation(node)
    _invalid(lambda: _read(tree))


@pytest.mark.parametrize("composed", [False, True])
def test_imported_prompt_keeps_declaration_and_caller_expression_provenance(composed):
    tree, node = _provider_fixture(composed=composed, prompt_module="library/prompts")
    program = _read(tree)
    entries = program.source_map["entries"]
    root = "/definitions/demo::main/body"
    assert entries[root]["source"] == "demo"
    assert entries[root + "/prompt"]["source"] == "library/prompts"
    assert entries[root + "/result"]["source"] == ("library/prompts" if composed else "demo")
    if composed:
        for subject in ("/prompt/template", "/prompt/fills/0"):
            assert entries[root + subject]["source"] == "library/prompts"
        assert entries[root + "/prompt/fills/0/value"]["source"] == "demo"
    altered = deepcopy(tree)
    altered["source_map"]["entries"][root + "/prompt"]["source"] = "demo"
    _invalid(lambda: _read(altered))
    altered = deepcopy(tree)
    altered["source_map"]["entries"].pop(root + "/result")
    _invalid(lambda: _read(altered))


def test_dynamic_policy_order_and_operand_paths_survive_canonical_read_back():
    from orchestrator.workflow_lisp.closed.sites import effect_value_operands
    tree, node = _provider_fixture()
    node["policy"] = {"model": {"k": "op", "name": "string/concat", "args": [{"k": "lit", "v": "a"}, {"k": "lit", "v": "b"}]},
                      "effort": {"k": "name", "n": "n"}}
    tree = _artifact(node, schemas=tree["schemas"], bindings=tree["bindings"])
    program = _read(tree)
    checked = program.definitions[program.entry]["body"]
    assert list(checked["policy"]) == ["effort", "model"]
    assert list(_read(program.artifact()).definitions[program.entry]["body"]["policy"]) == ["effort", "model"]
    operands = list(effect_value_operands(checked, canonical_policy=True))
    assert [path for path, _ in operands] == [("prompt", "fills", 0, "value"), ("policy", "effort"), ("policy", "model")]
    permuted = deepcopy(tree)
    permuted["definitions"][tree["entry"]]["body"]["policy"] = dict(reversed(list(node["policy"].items())))
    assert _read(permuted).semantic_digest == program.semantic_digest


def test_effect_root_contracts_are_independently_derived_for_records_and_unions():
    union = {"kind": "union", "name": "demo::Outcome", "variants": [
        {"name": "ready", "fields": [{"name": "payload", "type": INT}]}, {"name": "empty", "fields": []}]}
    for descriptor in (INPUT, union):
        tree, node, _ = _command_fixture(result=descriptor)
        assert _read(tree).definitions[tree["entry"]]["body"]["contract"]["payload"]["fields"][0]["json_pointer"] == ""
        node["contract"] = {"kind": "output_bundle", "payload": {"fields": [{"name": "payload", "json_pointer": "/payload", "type": "integer"}]}}
        _invalid(lambda: _read(tree))


def test_certified_raw_argv_lane_and_unused_canonical_rows_remain_admissible():
    from tests.test_workflow_lisp_closed_program_check import _certified_command_row
    tree, node, row = _command_fixture(certified=True)
    node.pop("document")
    node["argv"] = [{"k": "lit", "v": "opaque"}]
    # The established typed raw-argv lane does not invoke the promoted protocol.
    row["invocation_protocol"] = None
    tree["bindings"]["demo"]["configuration"]["commands"]["unused"] = _certified_command_row()
    tree = _artifact(node, schemas=tree["schemas"], bindings=tree["bindings"])
    assert _read(tree).bindings["demo"]["types"] == {"Int": "Int"}
    tree, node, row = _command_fixture(certified=True)
    row["invocation_protocol"] = "unsupported"
    _invalid(lambda: _read(tree))


def test_unreachable_certified_effects_still_require_their_type_associations():
    from tests.workflow_dynamic_helpers import _definition
    tree, node, row = _command_fixture(certified=True)
    row["input_signature"][0]["type_name"] = "String"
    tree["bindings"]["demo"]["types"]["String"] = "String"
    tree = _artifact(definitions={"demo::unused": _definition(node, params=("n",))}, schemas=tree["schemas"], bindings=tree["bindings"])
    assert "String" in _read(tree).bindings["demo"]["types"]
    tree["bindings"]["demo"]["types"].pop("String")
    error = _invalid(lambda: _read(tree))
    assert error.location == "/definitions/demo::unused/body"


def test_unreachable_extern_provider_inputs_refuse_before_provenance_validation():
    from tests.workflow_dynamic_helpers import _definition
    tree, node = _provider_fixture(composed=False)
    node["inputs"] = [["data", "canonical-json", {"k": "name", "n": "n"}]]
    tree["definitions"]["demo::unused"] = _definition(node)
    tree["definitions"][tree["entry"]]["body"] = {"k": "lit", "v": 0}
    error = _invalid(lambda: _read(tree))
    assert error.location == "/definitions/demo::unused/body/inputs"


def test_prompt_refinements_use_catalog_descriptors_without_inferring_expression_types():
    path = {"kind": "path", "name": "demo::Document", "under": "documents", "must_exist_target": True}
    tree, node = _provider_fixture()
    tree["schemas"].update({INPUT["name"]: INPUT, path["name"]: path})
    node["prompt"]["fills"][0]["type"] = INPUT
    node["prompt"]["fills"].append({"name": "document", "kind": "doc", "type": path,
        "value": {"k": "name", "n": "n"}, "renderer_id": None, "output_role": None, "placeholder_ordinals": []})
    tree = _artifact(node, schemas=tree["schemas"], bindings=tree["bindings"])
    # The Int parameter's shape is checked against the declaration at runtime.
    assert _read(tree).definitions[tree["entry"]]["body"]["prompt"]["fills"][0]["type"]["kind"] == "record"
    missing = deepcopy(tree)
    missing["schemas"].pop(path["name"])
    _invalid(lambda: _read(missing))
    node["prompt"]["fills"][1]["type"] = STRING
    tree = _artifact(node, schemas=tree["schemas"], bindings=tree["bindings"])
    _invalid(lambda: _read(tree))


def test_empty_external_document_retains_present_semantics():
    tree, node, _ = _command_fixture(document=True)
    empty = {"kind": "record", "name": "demo::Empty", "fields": []}
    tree["schemas"][empty["name"]] = empty
    node["input_type"] = empty
    node["document"] = []
    tree = _artifact(node, schemas=tree["schemas"], bindings=tree["bindings"])
    assert "document" in _read(tree).definitions[tree["entry"]]["body"]


def test_source_map_uses_real_operand_and_record_array_positions():
    tree, node = _provider_fixture(prompt_module="library/prompts")
    node["prompt"]["fills"][0]["value"] = {"k": "record", "fields": [["a~/b", {"k": "lit", "v": 7}]]}
    node["dependencies"] = {"required": [{"k": "name", "n": "n"}], "optional": [], "position": "prepend", "instruction": None}
    node["policy"] = {"model": {"k": "name", "n": "n"}, "effort": {"k": "lit", "v": "low"}}
    tree = _artifact(node, schemas=tree["schemas"], bindings=tree["bindings"])
    program = _read(tree)
    root = "/definitions/demo::main/body"
    for subject in ("/prompt/fills/0/value/fields/0/1", "/dependencies/required/0", "/policy/model", "/policy/effort"):
        assert program.source_map["entries"][root + subject]["source"] == "demo"
        altered = deepcopy(tree)
        altered["source_map"]["entries"].pop(root + subject)
        _invalid(lambda altered=altered: _read(altered))
