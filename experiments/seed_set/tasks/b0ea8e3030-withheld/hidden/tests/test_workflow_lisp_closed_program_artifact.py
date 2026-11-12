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
from tests.test_workflow_lisp_closed_program_check import (
    BOOL,
    INT,
    _command_result_tree,
    _effectful_call_tree,
    _halt,
    _lit,
    _name,
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
    ],
)
def test_readback_rejects_non_operator_type_tampering(builder, mutation, rule) -> None:
    tree = builder()
    mutation(tree)

    with pytest.raises(ClosedProgramInvalid) as excinfo:
        ClosedProgram.from_artifact(json.dumps(tree))

    assert (excinfo.value.code, excinfo.value.rule) == ("closed_program_invalid", rule)
