"""F1 feasibility: a non-exported named workflow builds as a private child entry.

The child-entry seam is the ordinary closed-program builder applied to a typed
program whose entry is the named workflow (no `:program (:workflow ...)`
surface syntax yet; that arrives with the syntax task).
"""

from __future__ import annotations

from dataclasses import replace
from importlib import import_module
from pathlib import Path

import pytest

from orchestrator.contracts.closed_program.program import ClosedProgram
from orchestrator.workflow.evaluated.machine import evaluate_closed_program, site_classes
from orchestrator.workflow.evaluated.values import EvaluatedValueError
from orchestrator.workflow_lisp.closed.build import Builder, build_closed_program
from orchestrator.workflow_lisp.closed.frontend import compile_typed_program
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from orchestrator.workflow_lisp.effects import UsesCommandEffect, UsesProviderEffect
from tests.workflow_lisp_closed_program_helpers import BOUNDARIES, PROMPTS, install

HELPER = '''(workflow-lisp (:language "0.1") (:target-dsl "TARGET")
  (defmodule helper) (export bump fetch Box)
  (defrecord Box (n Int))
  (defproc fetch ((n Int)) -> Box
    :effects ((uses-command fetch)) :lowering inline
    (command-result fetch :argv ("python" "probe.py" "fetch" n) :returns Box))
  (defun bump ((n Int)) -> Int (+ n 1)))'''

PARENT = '''(workflow-lisp (:language "0.1") (:target-dsl "TARGET")
  (defmodule controller) (import helper :only (bump fetch Box)) (export run)
  (defrecord Verdict (ok Bool))
  (defworkflow candidate-body ((seed Int) (task String)) -> Int
    (let* ((verdict (provider-result providers.review :prompt prompts.base
                      :inputs (task) :returns Verdict)))
      (if verdict.ok
        (loop/recur :max 5
          :state (loop-state (i Int seed))
          :on-exhausted -1
          (fn (state)
            (let* ((box (fetch (bump state.i))))
              (if (>= box.n 3) (done box.n)
                (continue (loop-state :like state :i box.n))))))
        0)))
  (defworkflow run ((seed Int)) -> Int PARENT_BODY))'''

CHILD = "controller::candidate-body"


def _typed(root: Path, parent_body: str = "(+ seed 1)"):
    install(root, {"helper.orc": HELPER,
                   "controller.orc": PARENT.replace("PARENT_BODY", parent_body)})
    return compile_typed_program(
        root / "controller.orc", entry_workflow="controller::run", source_roots=(root,),
        command_boundaries=BOUNDARIES, provider_externs={"providers.review": "probe-provider"},
        prompt_externs={"prompts.base": PROMPTS["prompt"]}, workspace_root=root)


def _child_entry(typed, name: str = CHILD) -> ClosedProgram:
    child = replace(typed, entry=typed.workflows[name])
    return build_closed_program(child, builder=Builder(child))


def _perform(effects):
    values = import_module("orchestrator.workflow.evaluated.values")

    def perform(node, operands, identity, _owner, _reader):
        arguments = tuple(operand.value for operand in operands)
        kind = _site_kind(node)
        effects.append((kind, arguments[-1]))
        value = {"ok": True} if kind == "provider" else {"n": arguments[-1]}
        return values.coerce_evaluated_value(value, node["result"], dependencies={identity})

    return perform


def _site_kind(node) -> str:
    return "command" if "boundary" in node else "provider"


def test_private_child_entry_evaluates_declared_inputs_with_imported_helper(tmp_path):
    program = ClosedProgram.from_artifact(_child_entry(_typed(tmp_path)).artifact())
    effects: list[tuple[str, object]] = []

    result = evaluate_closed_program(program, {"seed": 0, "task": "t"},
                                     effect_handler=_perform(effects))

    assert (result.value, effects) == (
        3, [("provider", "t"), ("command", 1), ("command", 2), ("command", 3)])


def test_private_child_entry_has_own_signature_sites_and_summary(tmp_path):
    typed = _typed(tmp_path)
    program = _child_entry(typed)

    assert (
        program.tree["entry"],
        [name for name, _ in program.tree["params"]],
        sorted(site_classes(program).values()),
        typed.workflows[CHILD].effect_summary.transitive_effects,
    ) == (
        f"workflow:{CHILD}",
        ["seed", "task"],
        ["command", "provider"],
        frozenset({UsesCommandEffect(subject=("fetch",)),
                   UsesProviderEffect(subject=("providers", "review"))}),
    )


def test_private_child_entry_keeps_canonical_owners_and_owner_bindings(tmp_path):
    program = _child_entry(_typed(tmp_path))
    owners = {definition["key"][0] for definition in program.tree["definitions"].values()}
    configuration = program.tree["configuration"]

    assert (owners, configuration["providers"], configuration["commands"]["fetch"]["stable_command"]) == (
        {"helper"}, {"providers.review": {"provider_id": "probe-provider"}}, ["python", "probe.py"])


def test_private_child_cannot_resolve_parent_runtime_binding(tmp_path):
    install(tmp_path, {"helper.orc": HELPER, "controller.orc": PARENT.replace(
        "(>= box.n 3)", "(>= box.n limit)").replace(
        "PARENT_BODY", "(let* ((limit 3)) (+ seed limit))")})

    with pytest.raises(LispFrontendCompileError) as refused:
        compile_typed_program(
            tmp_path / "controller.orc", entry_workflow="controller::run",
            source_roots=(tmp_path,), command_boundaries=BOUNDARIES,
            provider_externs={"providers.review": "probe-provider"},
            prompt_externs={"prompts.base": PROMPTS["prompt"]}, workspace_root=tmp_path)

    assert [row.code for row in refused.value.diagnostics] == ["name_unknown"]


def test_private_child_entry_refuses_parent_inputs_at_evaluation(tmp_path):
    program = _child_entry(_typed(tmp_path))

    with pytest.raises(EvaluatedValueError) as refused:
        evaluate_closed_program(program, {"seed": 0, "task": "t", "limit": 3},
                                effect_handler=_perform([]))

    assert refused.value.code == "closed_input_names"


def test_private_child_entry_identity_survives_snapshot_and_rebuild(tmp_path):
    first = _child_entry(_typed(tmp_path / "a"))
    snapshot = ClosedProgram.from_artifact(first.artifact())
    rebuilt = _child_entry(_typed(tmp_path / "b", parent_body="(+ seed 2)"))

    assert {snapshot.digest, rebuilt.digest} == {first.digest}
