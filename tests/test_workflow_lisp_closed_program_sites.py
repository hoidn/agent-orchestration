from __future__ import annotations

import pytest

from orchestrator.workflow_lisp.closed.sites import assign_sites
from orchestrator.workflow_lisp.closed.sites import SiteAssignmentError


def _let(name, value, body, *, label=None):
    node = {"k": "let", "name": name, "value": value, "body": body}
    if label is not None:
        node["label"] = label
    return node


def _perform():
    return {"k": "perform", "class": "command"}


def _halt():
    return {"k": "halt", "value": {"k": "lit", "v": None, "type": {"kind": "primitive", "name": "Value"}}}


def _tree(body, definitions=None):
    return {
        "entry": "workflow:sample::run",
        "body": body,
        "definitions": definitions or {},
    }


def test_pure_bindings_do_not_advance_ordinals_and_repeated_labels_count():
    body = _let(
        "%1",
        {"k": "lit", "v": 0, "type": {"kind": "primitive", "name": "Int"}},
        _let("%2", _perform(), _let("x", _perform(), _let("x", _perform(), _halt()))),
    )

    assert assign_sites(_tree(body)) == [
        ("workflow:sample::run", "#1"),
        ("workflow:sample::run", "x"),
        ("workflow:sample::run", "x#2"),
    ]


def test_authored_labels_override_hygienic_names_and_escape_site_separators():
    body = _let(
        "%1",
        _perform(),
        _let("%2", _perform(), _halt(), label="%/=#[]"),
        label="x",
    )

    assert assign_sites(_tree(body)) == [
        ("workflow:sample::run", "x"),
        ("workflow:sample::run", "%25%2F%3D%23%5B%5D"),
    ]


def test_select_prefixes_and_loop_exhaustion_have_distinct_paths():
    callee = "procedure:sample::fetch"
    selected = {
        "k": "select",
        "cond": {"k": "lit", "v": True, "type": {"kind": "primitive", "name": "Bool"}},
        "then": {
            "prefix": [
                {"name": "%1", "label": "then/row", "value": {"k": "call", "callee": callee, "args": []}}
            ],
            "value": {"k": "lit", "v": 1, "type": {"kind": "primitive", "name": "Int"}},
        },
        "else": {
            "prefix": [
                {"name": "%2", "label": "else=row", "value": {"k": "call", "callee": callee, "args": []}}
            ],
            "value": {"k": "lit", "v": 2, "type": {"kind": "primitive", "name": "Int"}},
        },
    }
    loop = {
        "k": "loop",
        "name": "generated_loop_target",
        "param": "%3",
        "init": {"k": "lit", "v": 0, "type": {"kind": "primitive", "name": "Int"}},
        "budget": {"k": "lit", "v": 3, "type": {"kind": "primitive", "name": "Int"}},
        "label": "state",
        "body": _let("inside", _perform(), _halt()),
        "exhausted": _let("exhausted", _perform(), _halt()),
    }
    definitions = {
        callee: {
            "params": [],
            "body": _let("effect", _perform(), _halt()),
        }
    }
    body = _let("outer", selected, loop)

    tree = _tree(body, definitions)
    assert assign_sites(tree) == [
        ("workflow:sample::run", "loop:state[*] / inside"),
        ("workflow:sample::run", "loop:state / exhausted / exhausted"),
        (callee, "effect"),
    ]
    calls = [
        tree["body"]["value"]["then"]["prefix"][0]["value"],
        tree["body"]["value"]["else"]["prefix"][0]["value"],
    ]
    assert [call["frame"] for call in calls] == [
        "outer / then / then%2Frow=procedure:sample::fetch",
        "outer / else / else%3Drow=procedure:sample::fetch",
    ]


def test_effectful_select_prefixes_are_visited_at_a_bound_site():
    selected = {
        "k": "select",
        "cond": {"k": "lit", "v": True, "type": {"kind": "primitive", "name": "Bool"}},
        "then": {
            "prefix": [{"name": "work", "value": _perform()}],
            "value": {"k": "lit", "v": 1, "type": {"kind": "primitive", "name": "Int"}},
        },
        "else": {
            "prefix": [{"name": "work", "value": _perform()}],
            "value": {"k": "lit", "v": 2, "type": {"kind": "primitive", "name": "Int"}},
        },
    }

    tree = _tree(_let("choose", selected, _halt()))

    assert assign_sites(tree) == [
        ("workflow:sample::run", "choose / then / work"),
        ("workflow:sample::run", "choose / else / work"),
    ]


def test_loop_state_override_labels_the_loop_without_exposing_its_target():
    loop = {
        "k": "loop",
        "name": "internal_target",
        "param": "%5",
        "init": {"k": "lit", "v": 0, "type": {"kind": "primitive", "name": "Int"}},
        "budget": {"k": "lit", "v": 3, "type": {"kind": "primitive", "name": "Int"}},
        "label": "state",
        "body": _let("work", _perform(), _halt()),
        "exhausted": None,
    }

    assert assign_sites(_tree(loop)) == [
        ("workflow:sample::run", "loop:state[*] / work")
    ]


def test_effectful_block_hidden_in_a_record_field_is_rejected():
    nested = {
        "k": "record",
        "type": {"kind": "record", "name": "sample::Box", "fields": []},
        "fields": [
            ["value", {"k": "block", "body": _let("hidden", _perform(), _halt())}]
        ],
    }

    with pytest.raises(SiteAssignmentError, match="outside a binding") as error:
        assign_sites(_tree(_let("box", nested, _halt())))

    assert error.value.rule == "effect_in_value"


def test_call_cycle_is_found_after_an_earlier_effect_in_the_definition():
    recursive = "procedure:sample::recursive"
    body = _let(
        "effect",
        _perform(),
        _let("again", {"k": "call", "callee": recursive, "args": []}, _halt()),
    )

    with pytest.raises(SiteAssignmentError, match="recursive call") as error:
        assign_sites(_tree(_halt(), {recursive: {"params": [], "body": body}}))

    assert error.value.rule == "call_cycle"


def test_terminal_values_are_scanned_for_hidden_effects():
    terminal = {
        "k": "halt",
        "value": {"k": "block", "body": _let("hidden", _perform(), _halt())},
    }

    with pytest.raises(SiteAssignmentError, match="outside a binding") as error:
        assign_sites(_tree(terminal))

    assert error.value.rule == "effect_in_value"


def test_site_assignment_never_treats_literal_json_as_ast_or_mutates_it():
    literal_data = {"k": "perform", "site": "authored-data"}
    halt = _halt()
    halt["value"] = {"k": "lit", "v": literal_data, "type": {"kind": "primitive", "name": "Value"}}
    call_lookalike = {"k": "call", "callee": "not-a-definition"}
    body = _let(
        "data",
        {"k": "lit", "v": call_lookalike, "type": {"kind": "primitive", "name": "Value"}},
        halt,
    )

    assert assign_sites(_tree(body)) == []
    assert literal_data == {"k": "perform", "site": "authored-data"}


def test_definition_site_rows_follow_first_call_order_not_mapping_order():
    first = "procedure:sample::first"
    second = "procedure:sample::second"
    definitions = {
        second: {"params": [], "body": _let("done", _perform(), _halt())},
        first: {"params": [], "body": _let("done", _perform(), _halt())},
    }
    body = _let(
        "second_result",
        {"k": "call", "callee": second, "args": []},
        _let("first_result", {"k": "call", "callee": first, "args": []}, _halt()),
    )

    assert assign_sites(_tree(body, definitions)) == [
        (second, "done"),
        (first, "done"),
    ]
