"""Evaluated command summaries retain nested generic result transport."""

import pytest

from orchestrator.workflow_lisp.closed.program import ClosedProgram
from orchestrator.workflow_lisp.closed.sites import _ast_nodes
from tests.workflow_lisp_closed_program_helpers import build


SOURCE = '''(workflow-lisp
  (:language "0.1") (:target-dsl "2.35")
  (defmodule nested/control)
  (import std/improve :only (Decision))
  (export run)
  (defrecord Notes (notes String))
  (defunion Blocker (STOP (issue String)) (LATER (issue String)))
  (defrecord Box (decision Decision[Notes Blocker]))
  DECLARATION
  (defworkflow run ((draft String)) -> Int
    (loop/recur :max 1 :state (loop-state (n Int 0)) :on-exhausted 0
      (fn (state)
        (let* ((decision BODY)
               (result (command-result fetch :argv ("python" "probe.py" decision) :returns Int)))
          (done result))))))'''


def _source(route, result_type):
    effect = f'''(provider-result provider :prompt prompt :inputs (draft)
                  :returns {result_type})'''
    declaration = ""
    body = effect
    if route != "direct":
        declaration = f'''(defproc review ((draft String)) -> {result_type}
          :effects ((uses-provider provider)) :lowering {route} {effect})'''
        body = "(review draft)"
    return SOURCE.replace("DECLARATION", declaration).replace("BODY", body)


@pytest.mark.parametrize("route", ["direct", "inline", "private-workflow"])
@pytest.mark.parametrize("result_type", ["Decision[Notes Blocker]", "Box"], ids=["union", "record"])
def test_evaluated_summary_preserves_nested_union_result(tmp_path, route, result_type):
    program = build(tmp_path, _source(route, result_type))
    restored = ClosedProgram.from_artifact(program.artifact())
    effects = [node for node in _ast_nodes(restored.tree["body"]) if node.get("k") == "perform"]
    for definition in restored.tree["definitions"].values():
        effects.extend(node for node in _ast_nodes(definition["body"]) if node.get("k") == "perform")
    assert sorted(node["class"] for node in effects) == ["command", "provider"]
    assert restored.digest == program.digest
