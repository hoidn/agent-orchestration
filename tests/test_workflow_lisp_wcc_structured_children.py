from __future__ import annotations

from pathlib import Path

import pytest

from orchestrator.contracts.closed_program.program import ClosedProgram
from orchestrator.workflow.evaluated.machine import evaluate_closed_program
from orchestrator.workflow.evaluated.values import coerce_evaluated_value
from orchestrator.workflow_lisp.closed import command_templates
from tests.workflow_lisp_closed_program_helpers import build


@pytest.mark.parametrize(("body", "return_type", "params", "inputs", "expected"), [
    ("(loop/recur :max 1 :state (loop-state (n Int (+ 1 2))) :on-exhausted state.n "
     "(fn (state) (if (< state.n 10) "
     "(continue (loop-state :like state :n (let* ((x (+ state.n 1))) x))) (done state.n))))",
     "Int", "", {}, 4),
    ("(let* ((x 10)) (loop/recur :max 1 :state "
     "(loop-state (a Int (let* ((x (+ x 1))) x)) (b Int x)) :on-exhausted 0 "
     "(fn (state) (done (+ state.a state.b)))))", "Int", "", {}, 21),
    ("(path/join-under Report (let* ((suffix child)) suffix))", "Report", "(child String)",
     {"child": "note.md"}, "artifacts/reports/note.md"),
    ("(list/map-effect ((item items)) :max 3 "
     "(command-result inc :argv (\"python\" \"probe.py\" item) :returns Int))",
     "List[Int]", "(items List[Int])", {"items": [1, 2]}, (2, 3)),
], ids=["state-update-local-block", "state-fields-shadowing", "rooted-path-local-block", "serial-map-head"])
def test_structured_children_prepare_without_frontend_reentry(
    tmp_path: Path, monkeypatch, body, return_type, params, inputs, expected,
):
    def forbidden(*args, **kwargs):
        pytest.fail("structured WCC child re-entered the frontend translator")

    monkeypatch.setattr(command_templates, "prepare_frontend_value", forbidden)
    source = f'''(workflow-lisp (:language "0.1") (:target-dsl "TARGET")
      (defmodule cp/prepared_structured) (export run)
      (defpath Report :kind relpath :under "artifacts/reports" :must-exist false)
      (defworkflow run ({params}) -> {return_type} {body}))'''
    program = build(tmp_path, source)
    restored = ClosedProgram.from_artifact(program.artifact())
    supplied = {name: coerce_evaluated_value(inputs[name], descriptor)
        for name, descriptor in restored.tree["params"]}
    effects = []

    def perform(node, operands, identity, _owner, _reader):
        effects.append(operands[-1].value)
        return coerce_evaluated_value(operands[-1].value + 1, node["result"], dependencies={identity})

    result = evaluate_closed_program(restored, supplied, effect_handler=perform)
    assert result.value == expected
    assert effects == ([1, 2] if inputs.get("items") else [])


@pytest.mark.parametrize(("update", "child_kind"), [
    ("(record-update state :n 2)", "block"),
    ("(loop-state :like state :n 2)", "op"),
], ids=["ordinary-record-update", "loop-state-update"])
def test_updates_of_the_same_carrier_keep_their_value_boundaries(tmp_path, update, child_kind):
    source = f'''(workflow-lisp (:language "0.1") (:target-dsl "TARGET")
      (defmodule cp/update_boundary) (export run)
      (defworkflow run () -> Int
        (loop/recur :max 1 :state (loop-state (n Int 0)) :on-exhausted 0
          (fn (state) (done (list/length (list {update})))))))'''
    restored = ClosedProgram.from_artifact(build(tmp_path, source).artifact())

    def nodes(value):
        if isinstance(value, dict):
            yield value
            for child in value.values():
                yield from nodes(child)
        elif isinstance(value, (list, tuple)):
            for child in value:
                yield from nodes(child)

    lists = [node for node in nodes(restored.tree) if node.get("k") == "list"]
    assert len(lists) == 1
    child = lists[0]["items"][0]
    assert child["k"] == child_kind
    if child_kind == "block":
        assert child["body"]["k"] == "let"
        assert child["body"]["body"]["k"] == "halt"
        assert child["body"]["body"]["value"]["n"] == child["body"]["name"]
    assert evaluate_closed_program(restored, {}).value == 1
