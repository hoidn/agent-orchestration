from __future__ import annotations

from copy import deepcopy
import json

import pytest

from orchestrator.workflow.type_descriptor import compiled_boundary_rows
from orchestrator.workflow_lisp.closed.program import ClosedProgram, ClosedProgramInvalid
from tests.test_workflow_lisp_closed_program_check import INT, _boundary_tree, _record


STRING = {"kind": "primitive", "name": "String"}


def _choice(name: str) -> dict:
    return {
        "kind": "union",
        "name": name,
        "variants": [
            {"name": "Ready", "fields": [{"name": "x", "type": deepcopy(INT)}]},
            {"name": "Skipped", "fields": [{"name": "reason", "type": deepcopy(STRING)}]},
        ],
    }


def _assert_boundary_rejected(tree: dict) -> None:
    with pytest.raises(ClosedProgramInvalid) as excinfo:
        ClosedProgram.from_artifact(json.dumps(tree))
    assert excinfo.value.rule == "call_boundary"


def test_union_split_into_unconditional_native_slots_is_rejected():
    choice = _choice("CallerChoice")
    selector = {"kind": "enum", "name": "ChoiceTag", "allowed": ["Ready", "Skipped"]}
    tree, _ = _boundary_tree(
        [("a", choice)],
        [("a__variant", selector), ("a__x", INT), ("a__reason", STRING)],
        INT,
        INT,
    )

    _assert_boundary_rejected(tree)


def test_unconditional_caller_slots_cannot_feed_a_native_union():
    choice = _choice("NativeChoice")
    selector = {"kind": "enum", "name": "ChoiceTag", "allowed": ["Ready", "Skipped"]}
    split = _record(
        "caller::SplitChoice",
        [("variant", selector), ("x", INT), ("reason", STRING)],
    )
    tree, _ = _boundary_tree(
        [("a", split)],
        [("a", choice)],
        INT,
        INT,
    )
    tree["types"][selector["name"]] = selector

    _assert_boundary_rejected(tree)


def test_unconditional_native_outputs_cannot_replace_a_caller_union():
    choice = _choice("CallerChoice")
    selector = {"kind": "enum", "name": "CallerChoice.variant", "allowed": ["Ready", "Skipped"]}
    split = _record(
        "native::SplitChoice",
        [("variant", selector), ("x", INT), ("reason", STRING)],
    )
    tree, call = _boundary_tree([], [], choice, split)
    call["boundary"]["outputs"]["caller"] = compiled_boundary_rows(
        [("return", choice)], output=True, relax_inactive_union_paths=True
    )
    tree["types"][selector["name"]] = selector

    _assert_boundary_rejected(tree)


def test_activity_check_preserves_one_to_many_records_and_wrapped_unions():
    pair = _record("caller::Pair", [("x", INT), ("y", INT)])
    tree, _ = _boundary_tree(
        [("a", pair)], [("a__x", INT), ("a__y", INT)], INT, INT
    )
    ClosedProgram.from_artifact(json.dumps(tree))

    caller_choice = _choice("caller::Choice")
    native_choice = _choice("native::Choice")
    caller_box = _record("caller::Box", [("choice", caller_choice)])
    native_box = _record("native::Box", [("choice", native_choice)])
    tree, _ = _boundary_tree([("a", caller_box)], [("a", native_box)], INT, INT)
    tree["types"].update(
        {
            caller_choice["name"]: caller_choice,
            native_choice["name"]: native_choice,
        }
    )

    ClosedProgram.from_artifact(json.dumps(tree))
