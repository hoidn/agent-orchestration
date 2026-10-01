from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import json

import pytest

from orchestrator.workflow_lisp.closed.program import (
    ClosedProgram,
    ClosedProgramInvalid,
    canonical_configuration,
    canonical_digest,
    logical_asset_base_for_module,
    program_digest,
    strip_provenance,
)
from orchestrator.workflow_lisp.closed.check import validate
from orchestrator.workflow_lisp.closed.names import canonical_callee_name_from_key
from tests.test_workflow_lisp_closed_program_check import (
    BOOL,
    INT,
    _boundary_tree,
    _command_result_tree,
    _effectful_call_tree,
    _halt,
    _lit,
    _name,
    _provider_prompt_fills,
    _provider_prompt_tree,
    _record,
    _run_ref_tree,
    _tree,
)
from orchestrator.workflow_lisp.command_boundaries import ExternalToolBinding
from orchestrator.workflow_lisp.workflows import PromptExtern, ProviderExtern


VALUE = {"kind": "primitive", "name": "Value"}
STRING = {"kind": "primitive", "name": "String"}


def _closed(tree: dict) -> ClosedProgram:
    return ClosedProgram(
        tree=tree,
        sites=tuple(tuple(row) for row in tree["sites"]),
        digest=program_digest(tree),
    )


def _typed_call_tree() -> dict:
    tree, call = _effectful_call_tree(effectful=False)
    old_name = call["callee"]
    definition = tree["definitions"].pop(old_name)
    key = definition["key"]
    key[8]["params"] = [deepcopy(INT)]
    definition["key"] = key
    definition["params"] = [["argument", deepcopy(INT)]]
    callee = canonical_callee_name_from_key(key)
    tree["definitions"][callee] = definition
    call["callee"] = callee
    call["args"] = [_lit(1)]
    return tree


def _list_map_tree() -> dict:
    list_int = {"kind": "list", "item": deepcopy(INT)}
    tree = _tree(
        _halt(
            {
                "k": "list_map",
                "binder": "item",
                "source": _name("items"),
                "body": _name("item"),
                "type": deepcopy(list_int),
            }
        ),
        result=list_int,
    )
    tree["params"] = [["items", deepcopy(list_int)]]
    return tree


def _nested_record_tree() -> dict:
    nested = {
        "kind": "record",
        "name": "sample::Nested",
        "fields": [{"name": "count", "type": deepcopy(INT)}],
    }
    outer = {
        "kind": "record",
        "name": "sample::Outer",
        "fields": [{"name": "nested", "type": deepcopy(nested)}],
    }
    nested_value = {
        "k": "record",
        "type": deepcopy(nested),
        "fields": [["count", _lit(1)]],
    }
    value = {
        "k": "record",
        "type": deepcopy(outer),
        "fields": [["nested", nested_value]],
    }
    tree = _tree(_halt(value), result=outer)
    tree["types"] = {nested["name"]: nested, outer["name"]: outer}
    return tree


def _wref_extern_configuration_tree() -> tuple[dict, str, str, str]:
    producer_module = "cp/workflows/producer"
    asset_base = logical_asset_base_for_module(producer_module)
    configuration = canonical_configuration(
        {},
        origins={},
        externs={
            "reviewer": ProviderExtern(name="reviewer", provider_id="provider:review"),
            "asset-prompt": PromptExtern(
                name="asset-prompt", source_kind="asset_file", path="review.md"
            ),
            "input-prompt": PromptExtern(
                name="input-prompt", source_kind="input_file", path="input.md"
            ),
        },
        asset_base=asset_base,
    )
    configuration_digest = canonical_digest(configuration)
    workflow_key = [
        producer_module,
        "workflow",
        "nested",
        [],
        [],
        [],
        [],
        [],
        {"params": [], "result": deepcopy(INT)},
    ]
    reference = {
        "target": workflow_key,
        "externs": {
            "providers": [
                [name, deepcopy(row)]
                for name, row in configuration["providers"].items()
            ],
            "prompts": [
                [name, deepcopy(row)]
                for name, row in configuration["prompts"].items()
            ],
        },
    }
    producer_key = [
        producer_module,
        "workflow",
        "producer",
        [],
        [],
        [["nested", reference]],
        [],
        [],
        {"params": [], "result": deepcopy(INT)},
    ]
    producer_name = canonical_callee_name_from_key(producer_key)
    tree = _tree(_halt(_lit(0)))
    tree["configuration"]["imports"] = {configuration_digest: configuration}
    tree["definitions"] = {
        producer_name: {
            "key": producer_key,
            "params": [],
            "result": deepcopy(INT),
            "body": _halt(_lit(0)),
            "configuration": configuration_digest,
        }
    }
    return tree, configuration_digest, producer_name, asset_base


def test_digest_omits_ast_provenance_but_keeps_it_in_the_artifact() -> None:
    opaque = {"@": {"span": "semantic data"}, "k": "perform", "site": "literal"}
    tree = _tree(_halt(_lit(opaque, VALUE)), result=VALUE)
    tree["body"]["@"]= {"span": "/first/main.orc:1:1", "form": ["halt"]}
    tree["body"]["value"]["@"]= {"span": "/first/main.orc:1:2", "form": ["lit"]}
    validate(tree)

    moved = deepcopy(tree)
    moved["body"]["@"]["span"] = "/elsewhere/main.orc:8:2"
    moved["body"]["value"]["@"]["span"] = "/elsewhere/main.orc:8:3"

    assert program_digest(tree) == program_digest(moved)
    assert _closed(tree).artifact() != _closed(moved).artifact()
    assert strip_provenance(tree)["body"]["value"]["v"] == opaque
    assert "/first/main.orc" in _closed(tree).artifact()

    changed_data = deepcopy(tree)
    changed_data["body"]["value"]["v"]["@"]["span"] = "changed semantic data"
    assert program_digest(changed_data) != program_digest(tree)


def test_digest_strips_provenance_from_case_select_and_prefix_rows_only() -> None:
    selected = {
        "k": "select",
        "cond": _lit(True, BOOL),
        "then": {
            "prefix": [{"name": "picked", "value": _lit(1)}],
            "value": _lit({"@": {"semantic": True}}, VALUE),
        },
        "else": {"prefix": [], "value": _lit({"@": {"semantic": False}}, VALUE)},
    }
    select_tree = _tree(_halt(selected), result=VALUE)
    validate(select_tree)
    select_tree["body"]["@"] = {"span": "halt"}
    select_tree["body"]["value"]["@"] = {"span": "select"}
    select_tree["body"]["value"]["then"]["@"] = {"span": "then"}
    select_tree["body"]["value"]["then"]["prefix"][0]["@"] = {"span": "prefix"}
    select_before = program_digest(select_tree)
    stripped_select = strip_provenance(select_tree)

    assert program_digest(stripped_select) == select_before
    assert "@" not in stripped_select["body"]
    assert "@" not in stripped_select["body"]["value"]["then"]
    assert "@" not in stripped_select["body"]["value"]["then"]["prefix"][0]
    assert stripped_select["body"]["value"]["then"]["value"]["v"]["@"] == {
        "semantic": True
    }

    choice = {
        "kind": "union",
        "name": "sample::Choice",
        "variants": [
            {"name": "Some", "fields": [{"name": "value", "type": deepcopy(INT)}]},
            {"name": "None", "fields": []},
        ],
    }
    case = {
        "k": "case",
        "subject": {
            "k": "inject",
            "type": deepcopy(choice),
            "variant": "Some",
            "fields": [["value", _lit(3)]],
        },
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
    case_tree["types"] = {choice["name"]: deepcopy(choice)}
    validate(case_tree)
    case_tree["body"]["@"] = {"span": "case"}
    case_tree["body"]["arms"][0]["@"] = {"span": "case-arm"}
    case_before = program_digest(case_tree)
    stripped_case = strip_provenance(case_tree)

    assert program_digest(stripped_case) == case_before
    assert "@" not in stripped_case["body"]
    assert "@" not in stripped_case["body"]["arms"][0]


def test_artifact_round_trip_checks_the_tree_and_rebuilds_sites() -> None:
    tree, _ = _command_result_tree()
    before = deepcopy(tree)
    program = _closed(tree)

    expected = json.dumps(
        tree,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ) + "\n"
    assert program.artifact() == expected

    readback = ClosedProgram.from_artifact(program.artifact())
    assert readback.tree == tree
    assert readback.sites == program.sites
    assert readback.digest == program.digest
    assert tree == before
    assert canonical_digest({"unicode": "áλ"}).startswith("sha256:")


def test_task5_boundary_fixtures_round_trip_through_artifact_readback() -> None:
    fills, document, output = _provider_prompt_fills()
    provider_tree, _provider = _provider_prompt_tree(
        "Read the document; write {title} with score {score} to {output}", fills
    )
    provider_tree["types"].update(
        {document["name"]: deepcopy(document), output["name"]: deepcopy(output)}
    )

    caller = _record("sample::Pair", [("x", INT), ("y", INT)])
    boundary_tree, _call = _boundary_tree(
        [("pair", caller)], [("pair__x", INT), ("pair__y", INT)], INT, INT
    )
    run_ref_tree, _effect, _config = _run_ref_tree()

    for tree in (provider_tree, run_ref_tree, boundary_tree):
        validate(tree)
        program = _closed(tree)
        readback = ClosedProgram.from_artifact(program.artifact())
        assert readback.tree == tree
        assert readback.sites == program.sites
        assert readback.digest == program.digest


def test_wref_extern_artifact_round_trip_matches_its_selected_producer_configuration() -> None:
    tree, configuration_digest, producer_name, asset_base = (
        _wref_extern_configuration_tree()
    )
    physical_sources = (
        "/checkout-a/cp/workflows/producer.orc",
        "/tmp/relocated/cp/workflows/producer.orc",
    )
    digests = []

    for physical_source in physical_sources:
        candidate = deepcopy(tree)
        candidate["body"]["@"] = {
            "span": f"{physical_source}:1:1",
            "form": ["halt"],
        }
        validate(candidate)
        program = _closed(candidate)
        readback = ClosedProgram.from_artifact(program.artifact())
        definition = readback.tree["definitions"][producer_name]
        selected = readback.tree["configuration"]["imports"][
            definition["configuration"]
        ]
        reference = definition["key"][5][0][1]

        assert definition["configuration"] == configuration_digest
        assert {
            name: row for name, row in reference["externs"]["providers"]
        } == selected["providers"]
        assert {name: row for name, row in reference["externs"]["prompts"]} == selected[
            "prompts"
        ]
        assert selected["providers"]["reviewer"] == {
            "provider_id": "provider:review"
        }
        assert selected["prompts"]["asset-prompt"] == {
            "source_kind": "asset_file",
            "path": "review.md",
            "asset_base": asset_base,
        }
        assert selected["prompts"]["input-prompt"] == {
            "source_kind": "input_file",
            "path": "input.md",
        }
        assert physical_source not in json.dumps(selected)
        digests.append(readback.digest)

    assert digests[0] == digests[1]


@pytest.mark.parametrize(
    ("surface", "category", "formal", "change", "rule"),
    [
        ("wref", "providers", "reviewer", "missing_provider_id", "definition_key"),
        ("wref", "providers", "reviewer", "extra_provider_key", "definition_key"),
        ("wref", "prompts", "asset-prompt", "missing_prompt_path", "definition_key"),
        ("wref", "prompts", "asset-prompt", "missing_asset_base", "definition_key"),
        ("wref", "prompts", "input-prompt", "input_has_asset_base", "definition_key"),
        ("wref", "prompts", "input-prompt", "extra_prompt_key", "definition_key"),
        ("wref", "prompts", "input-prompt", "invalid_prompt_source", "definition_key"),
        (
            "configuration",
            "providers",
            "reviewer",
            "missing_provider_id",
            "configuration_scope",
        ),
        (
            "configuration",
            "providers",
            "reviewer",
            "extra_provider_key",
            "configuration_scope",
        ),
        (
            "configuration",
            "prompts",
            "asset-prompt",
            "missing_prompt_path",
            "configuration_scope",
        ),
        (
            "configuration",
            "prompts",
            "asset-prompt",
            "missing_asset_base",
            "configuration_scope",
        ),
        (
            "configuration",
            "prompts",
            "input-prompt",
            "input_has_asset_base",
            "configuration_scope",
        ),
        (
            "configuration",
            "prompts",
            "input-prompt",
            "extra_prompt_key",
            "configuration_scope",
        ),
        (
            "configuration",
            "prompts",
            "input-prompt",
            "invalid_prompt_source",
            "configuration_scope",
        ),
    ],
    ids=[
        "wref-provider-missing-id",
        "wref-provider-extra-key",
        "wref-asset-prompt-missing-path",
        "wref-asset-prompt-missing-base",
        "wref-input-prompt-rejects-base",
        "wref-prompt-extra-key",
        "wref-prompt-invalid-source",
        "config-provider-missing-id",
        "config-provider-extra-key",
        "config-asset-prompt-missing-path",
        "config-asset-prompt-missing-base",
        "config-input-prompt-rejects-base",
        "config-prompt-extra-key",
        "config-prompt-invalid-source",
    ],
)
def test_readback_rejects_malformed_wref_and_configuration_extern_rows(
    surface, category, formal, change, rule
) -> None:
    tree, configuration_digest, producer_name, _asset_base = (
        _wref_extern_configuration_tree()
    )
    validate(tree)
    if surface == "wref":
        producer_key = tree["definitions"][producer_name]["key"]
        reference = producer_key[5][0][1]
        row = next(row for name, row in reference["externs"][category] if name == formal)
    else:
        selected = tree["configuration"]["imports"][configuration_digest]
        row = selected[category][formal]

    if change == "missing_provider_id":
        row.pop("provider_id")
    elif change == "extra_provider_key":
        row["alias"] = "unexpected"
    elif change == "missing_prompt_path":
        row.pop("path")
    elif change == "missing_asset_base":
        row.pop("asset_base")
    elif change == "input_has_asset_base":
        row["asset_base"] = "pkg/workflows"
    elif change == "extra_prompt_key":
        row["template"] = "unexpected"
    else:
        assert change == "invalid_prompt_source"
        row["source_kind"] = "remote_file"

    if surface == "wref":
        definition = tree["definitions"].pop(producer_name)
        producer_name = canonical_callee_name_from_key(definition["key"])
        tree["definitions"][producer_name] = definition
    else:
        imports = tree["configuration"]["imports"]
        selected = imports.pop(configuration_digest)
        configuration_digest = canonical_digest(selected)
        imports[configuration_digest] = selected
        tree["definitions"][producer_name]["configuration"] = configuration_digest

    with pytest.raises(ClosedProgramInvalid) as excinfo:
        ClosedProgram.from_artifact(_closed(tree).artifact())

    assert (excinfo.value.code, excinfo.value.rule) == ("closed_program_invalid", rule)


def test_artifact_round_trips_unequal_producer_scopes_and_deduplicates_equal_rows() -> None:
    _command_tree, command = _command_result_tree()
    binding = ExternalToolBinding(
        name="fetch",
        stable_command=tuple(command["command"]),
        closure=("probe.py",),
    )
    first = canonical_configuration(
        {"fetch": binding, "unused": ExternalToolBinding(
            name="unused", stable_command=("python", "unused.py"), closure=("unused.py",)
        )},
        origins={"fetch": "workspace", "unused": "workspace"},
        externs={
            "providers.review": ProviderExtern(name="providers.review", provider_id="provider-a"),
            "prompts.review": PromptExtern(
                name="prompts.review", source_kind="asset_file", path="review.md"
            ),
        },
        asset_base=logical_asset_base_for_module("cp/producer"),
    )
    unequal = canonical_configuration(
        {
            "fetch": replace(binding, stable_command=("python", "other-fetch.py")),
            "unused": ExternalToolBinding(
                name="unused", stable_command=("python", "unused.py"), closure=("unused.py",)
            ),
        },
        origins={"fetch": "workspace", "unused": "workspace"},
        externs={
            "providers.review": ProviderExtern(name="providers.review", provider_id="provider-b"),
            "prompts.review": PromptExtern(
                name="prompts.review", source_kind="asset_file", path="other-review.md"
            ),
        },
        asset_base=logical_asset_base_for_module("cp/other_producer"),
    )
    first_digest = canonical_digest(first)
    unequal_digest = canonical_digest(unequal)
    imports = {canonical_digest(config): config for config in (first, first, unequal)}
    assert len(imports) == 2

    tree, _call = _effectful_call_tree()
    tree["configuration"]["commands"] = {}
    tree["configuration"]["imports"] = imports
    worker = next(iter(tree["definitions"].values()))
    worker["configuration"] = first_digest
    validate(tree)
    artifact = _closed(tree).artifact()
    readback = ClosedProgram.from_artifact(artifact)

    assert readback.tree["configuration"]["imports"] == imports
    assert readback.digest == program_digest(tree)

    wrong_scope = deepcopy(tree)
    wrong_scope["definitions"][next(iter(wrong_scope["definitions"]))]["configuration"] = (
        unequal_digest
    )
    with pytest.raises(ClosedProgramInvalid) as scope_error:
        ClosedProgram.from_artifact(_closed(wrong_scope).artifact())
    assert scope_error.value.rule == "configuration_scope"

    changed_key_row = deepcopy(tree)
    changed_key_row["configuration"]["imports"][first_digest]["providers"][
        "providers.unused"
    ] = {"provider_id": "tampered-without-rekeying"}
    with pytest.raises(ClosedProgramInvalid) as key_error:
        ClosedProgram.from_artifact(json.dumps(changed_key_row))
    assert key_error.value.rule == "configuration_scope"

    changed_unused = deepcopy(first)
    changed_unused["commands"]["unused"]["stable_command"] = ["python", "changed-unused.py"]
    changed_digest = canonical_digest(changed_unused)
    assert changed_digest != first_digest
    changed_tree = deepcopy(tree)
    changed_tree["configuration"]["imports"].pop(first_digest)
    changed_tree["configuration"]["imports"][changed_digest] = changed_unused
    changed_tree["definitions"][next(iter(changed_tree["definitions"]))]["configuration"] = (
        changed_digest
    )
    validate(changed_tree)
    changed_readback = ClosedProgram.from_artifact(_closed(changed_tree).artifact())
    assert changed_readback.digest != readback.digest


def test_readback_refuses_invalid_operator_payload_before_digesting() -> None:
    tree = _tree(
        _halt(
            {
                "k": "op",
                "payload": {
                    "pure_expr_schema_version": 2,
                    "result_type": deepcopy(INT),
                    "bindings": {
                        "a0": {"type": deepcopy(INT)},
                        "a1": {"type": deepcopy(INT)},
                    },
                    "expr": {
                        "kind": "op",
                        "operator": "+",
                        "args": [
                            {"kind": "binding", "name": "a0"},
                            {"kind": "binding", "name": "a1"},
                        ],
                    },
                },
                "args": [_lit(1), _lit(2)],
            }
        )
    )
    validate(tree)
    tree["body"]["value"]["payload"]["result_type"] = deepcopy(STRING)

    with pytest.raises(ClosedProgramInvalid) as excinfo:
        ClosedProgram.from_artifact(json.dumps(tree))

    assert (excinfo.value.code, excinfo.value.rule) == (
        "closed_program_invalid",
        "payload_invalid",
    )


@pytest.mark.parametrize(
    ("field", "value", "rule"),
    [
        ("schema", "workflow-lisp/closed-program/0", "representation"),
        ("representation", "other/1", "representation"),
        ("sites", [], "sites"),
    ],
)
def test_readback_refuses_schema_representation_and_site_table_changes(field, value, rule) -> None:
    tree, _ = _command_result_tree()
    tree[field] = value

    with pytest.raises(ClosedProgramInvalid) as excinfo:
        ClosedProgram.from_artifact(json.dumps(tree))

    assert (excinfo.value.code, excinfo.value.rule) == ("closed_program_invalid", rule)


def test_readback_rejects_duplicate_json_keys() -> None:
    tree, _ = _command_result_tree()
    text = json.dumps(tree, separators=(",", ":"))
    text = text.replace('"target":"2.35"', '"target":"2.34","target":"2.35"')

    with pytest.raises(ClosedProgramInvalid) as excinfo:
        ClosedProgram.from_artifact(text)

    assert excinfo.value.code == "closed_program_invalid"


def test_readback_rejects_duplicate_keys_inside_opaque_literal_data() -> None:
    tree = _tree(_halt(_lit({"key": 1}, VALUE)), result=VALUE)
    text = json.dumps(tree)
    tampered = text.replace('"v": {"key": 1}', '"v": {"key": 1, "key": 2}')
    assert tampered != text

    with pytest.raises(ClosedProgramInvalid) as excinfo:
        ClosedProgram.from_artifact(tampered)

    assert excinfo.value.code == "closed_program_invalid"


def test_readback_refuses_unencodable_unicode_instead_of_leaking_encode_errors() -> None:
    tree = _tree(_halt(_lit("\ud800", VALUE)), result=VALUE)

    with pytest.raises(ClosedProgramInvalid) as excinfo:
        ClosedProgram.from_artifact(json.dumps(tree))

    assert excinfo.value.code == "closed_program_invalid"


@pytest.mark.parametrize(
    ("builder", "mutation", "rule"),
    [
        (
            lambda: _command_result_tree()[0],
            lambda tree: tree["body"]["value"].__setitem__("result", deepcopy(STRING)),
            "effect_result",
        ),
        (
            lambda: _tree(_halt(_lit(1))),
            lambda tree: tree.__setitem__("result", deepcopy(STRING)),
            "entry_result",
        ),
        (
            _list_map_tree,
            lambda tree: tree["body"]["value"]["type"].__setitem__(
                "item", deepcopy(STRING)
            ),
            "type_mismatch",
        ),
        (
            _nested_record_tree,
            lambda tree: tree["body"]["value"]["fields"][0][1]["fields"][0].__setitem__(
                1, _lit("wrong type", STRING)
            ),
            "type_mismatch",
        ),
        (
            _typed_call_tree,
            lambda tree: tree["body"]["value"].__setitem__("type", deepcopy(STRING)),
            "call_signature",
        ),
        (
            _typed_call_tree,
            lambda tree: tree["body"]["value"]["args"].__setitem__(
                0, _lit("wrong type", STRING)
            ),
            "call_signature",
        ),
    ],
)
def test_readback_rejects_non_operator_type_tampering(builder, mutation, rule) -> None:
    tree = builder()
    validate(tree)
    mutation(tree)
    artifact = _closed(tree).artifact()

    with pytest.raises(ClosedProgramInvalid) as excinfo:
        ClosedProgram.from_artifact(artifact)

    assert (excinfo.value.code, excinfo.value.rule) == ("closed_program_invalid", rule)
