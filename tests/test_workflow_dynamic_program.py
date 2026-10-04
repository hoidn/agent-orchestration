"""Production admission contract for closed dynamic Workflow Lisp programs."""

from __future__ import annotations

import hashlib
import json

import pytest


INT = {"kind": "primitive", "name": "Int"}
BOOL = {"kind": "primitive", "name": "Bool"}


from tests.workflow_dynamic_helpers import _artifact, _invalid, _pointer, _read, _span, _text


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
