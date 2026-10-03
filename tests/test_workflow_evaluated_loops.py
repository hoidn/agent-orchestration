from __future__ import annotations

from importlib import import_module
from pathlib import Path

import pytest

from orchestrator.workflow_lisp.command_boundaries import ExternalToolBinding
from tests.test_workflow_evaluated_control import (
    INT,
    _build_read_back,
    _effect_handler,
    _machine_api,
)
from tests.test_workflow_lisp_closed_program_corpus import _control_sources
from tests.workflow_lisp_closed_program_helpers import TARGET


@pytest.mark.parametrize(
    "decisions, expected", [((True, True), 7), ((True, False), 99), ((False,), 99)]
)
def test_loop_literal_result_retains_choices_without_reading_unused_state(
    tmp_path: Path, decisions: tuple[bool, ...], expected: int,
) -> None:
    source = f'''(workflow-lisp (:language "0.1") (:target-dsl "{TARGET}")
      (defmodule loop_choices) (export run)
      (defproc check ((n Int)) -> Bool
        :effects ((uses-command check)) :lowering inline
        (command-result check :argv ("python" "probe.py" n) :returns Bool))
      (defproc work ((n Int)) -> Int
        :effects ((uses-command work)) :lowering inline
        (command-result work :argv ("python" "probe.py" n) :returns Int))
      (defworkflow run ((budget Int) (seed Int) (unused Int)) -> Int
        (loop/recur :max budget
          :state (loop-state (i Int seed))
          :on-exhausted 7
          (fn (state)
            (if (check 5)
              (let* ((observed (work 5)))
                (continue (loop-state :like state :i observed)))
              (done 99))))))'''
    boundaries = {
        name: ExternalToolBinding(
            name=name, stable_command=("python", "probe.py"), closure=()
        )
        for name in ("check", "work")
    }
    program = _build_read_back(
        tmp_path, {"loop_choices.orc": source}, "loop_choices::run",
        boundaries=boundaries,
    )
    values = import_module("orchestrator.workflow.evaluated.values")
    choices = iter(decisions)
    effects = []

    def perform(node, operands, identity, _owner, _reader):
        dependencies = frozenset(
            dependency for operand in operands for dependency in operand.dependencies
        )
        effects.append((node["boundary"], identity, dependencies))
        value = next(choices) if node["boundary"] == "check" else 42
        return values.coerce_evaluated_value(
            value, node["result"], dependencies={identity, *dependencies}
        )

    result = _machine_api().evaluate_closed_program(
        program, {
            "budget": values.EvaluatedValue(2, INT, {"input:budget"}),
            "seed": values.EvaluatedValue(0, INT, {"input:seed"}),
            "unused": values.EvaluatedValue(123, INT, {"input:unused"}),
        }, effect_handler=perform,
    )

    checks = [identity for boundary, identity, _ in effects if boundary == "check"]
    assert result.value == expected
    assert len(checks) == len(decisions)
    assert len(set(checks)) == len(decisions)
    assert result.dependencies == frozenset({"input:budget", *checks})
    assert all(not dependencies for _, _, dependencies in effects)
    assert [boundary for boundary, _, _ in effects].count("work") == sum(decisions)


def test_loop_continue_done_and_parser_ordered_seed_budget(tmp_path: Path) -> None:
    values = import_module("orchestrator.workflow.evaluated.values")
    sources, entry = _control_sources("loop_continue_and_done", "direct")
    loop_program = _build_read_back(tmp_path / "loop", sources, entry)
    effects = []
    result = _machine_api().evaluate_closed_program(
        loop_program, {}, effect_handler=_effect_handler(values, effects)
    )
    assert result.value == 2
    assert [row[0] for row in effects] == ["next-val", "next-val", "done-val"]
    assert [row[2].split("loop:state[")[1].split("]", 1)[0] for row in effects] == [
        "1", "2", "3"
    ]

    for index, (case, expected) in enumerate((
        ("loop_budget_before_seed", ["budget", "seed"]),
        ("loop_seed_before_budget", ["seed", "budget"]),
    )):
        sources, entry = _control_sources(case, "direct")
        ordered = _build_read_back(tmp_path / f"order-{index}", sources, entry)
        calls = []
        result = _machine_api().evaluate_closed_program(
            ordered, {}, effect_handler=_effect_handler(values, calls)
        )
        assert result.value == 0
        assert [row[0] for row in calls[:2]] == expected
        assert calls[2][0] == "done-val"

    sources, entry = _control_sources("loop_nested_in_if", "direct")
    nested_if = _build_read_back(tmp_path / "nested-if", sources, entry)
    nested_effects = []
    result = _machine_api().evaluate_closed_program(
        nested_if, {}, effect_handler=_effect_handler(values, nested_effects)
    )
    assert result.value == 2
    assert [row[0] for row in nested_effects] == [
        "seed", "next-val", "next-val", "done-val"
    ]

    sources, entry = _control_sources("nested_loop_in_done", "direct")
    nested_done = _build_read_back(tmp_path / "nested-done", sources, entry)
    nested_effects = []
    result = _machine_api().evaluate_closed_program(
        nested_done, {}, effect_handler=_effect_handler(values, nested_effects)
    )
    assert result.value is True
    assert [row[0] for row in nested_effects] == ["seed", "budget", "check"]



def test_loop_exhaustion_returns_the_last_committed_state(tmp_path: Path) -> None:
    source = f'''(workflow-lisp (:language "0.1") (:target-dsl "{TARGET}")
      (defmodule exhaustion_machine) (export run)
      (defworkflow run () -> Int
        (loop/recur :max 2
          :state (loop-state (i Int 0))
          :on-exhausted state.i
          (fn (state)
            (if (= state.i 99)
              (done state.i)
              (continue (loop-state :like state :i (+ state.i 1))))))))'''
    program = _build_read_back(
        tmp_path, {"exhaustion_machine.orc": source}, "exhaustion_machine::run"
    )
    result = _machine_api().evaluate_closed_program(program, {})
    assert result.value == 2



def test_loop_budget_result_dependency_does_not_leak_into_body_effect_inputs(
    tmp_path: Path,
) -> None:
    source = f'''(workflow-lisp (:language "0.1") (:target-dsl "{TARGET}")
      (defmodule loop_budget_dependencies) (export run)
      (defproc get-budget ((n Int)) -> Int
        :effects ((uses-command get-budget)) :lowering inline
        (command-result get-budget :argv ("python" "probe.py" n) :returns Int))
      (defproc work ((n Int)) -> Int
        :effects ((uses-command work)) :lowering inline
        (command-result work :argv ("python" "probe.py" n) :returns Int))
      (defworkflow run ((iterations Int)) -> Int
        (loop/recur :max (get-budget iterations)
          :state (loop-state (i Int 0))
          :on-exhausted 7
          (fn (state)
              (if (< 0 state.i)
                (continue (loop-state :like state :i (+ state.i 1)))
                (let* ((observed (work 5))) (done (+ observed 4))))))))'''
    boundaries = {
        name: ExternalToolBinding(
            name=name, stable_command=("python", "probe.py"), closure=()
        )
        for name in ("get-budget", "work")
    }
    program = _build_read_back(
        tmp_path, {"loop_budget_dependencies.orc": source},
        "loop_budget_dependencies::run", boundaries=boundaries,
    )
    values = import_module("orchestrator.workflow.evaluated.values")

    def evaluate(budget):
        effects = []

        def perform(node, operands, identity, _owner, _reader):
            dependencies = frozenset(
                dependency for operand in operands for dependency in operand.dependencies
            )
            effects.append((node["boundary"], dependencies, identity))
            return values.coerce_evaluated_value(
                operands[-1].value, node["result"], dependencies={identity, *dependencies}
            )

        result = _machine_api().evaluate_closed_program(
            program,
            {"iterations": values.EvaluatedValue(budget, INT, {"input:iterations"})},
            effect_handler=perform,
        )
        return result, effects

    exhausted, exhausted_effects = evaluate(0)
    completed, completed_effects = evaluate(1)

    assert exhausted.value == 7
    assert completed.value == 9
    assert exhausted.dependencies == frozenset({"input:iterations", exhausted_effects[0][2]})
    assert completed.dependencies == frozenset({
        "input:iterations", completed_effects[0][2], completed_effects[1][2]
    })
    assert exhausted_effects[0][0] == "get-budget"
    assert [row[0] for row in completed_effects] == ["get-budget", "work"]
    assert completed_effects[1][1] == frozenset()
