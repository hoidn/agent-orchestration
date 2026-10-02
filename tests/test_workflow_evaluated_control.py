from __future__ import annotations

from copy import deepcopy
from importlib import import_module
import json
from pathlib import Path
import re

import pytest

from orchestrator.workflow_lisp import syntax
from orchestrator.workflow_lisp.closed.sites import _ast_nodes, assign_sites
from orchestrator.workflow_lisp.closed.program import ClosedProgram
from orchestrator.workflow_lisp.command_boundaries import ExternalToolBinding
from orchestrator.workflow_lisp.workflows import PromptExtern
from tests.test_workflow_lisp_closed_program_corpus import _control_sources
from tests.workflow_lisp_closed_program_helpers import TARGET, build


def _machine_api():
    return import_module("orchestrator.workflow.evaluated.machine")


def test_read_back_machine_instantiates_call_sites_inside_loop(tmp_path: Path) -> None:
    source = (
        Path(__file__).parent
        / "experiments/fixtures/evaluated_execution_spike/arms_in_loop.orc"
    ).read_text(encoding="utf-8")
    source = source.replace(
        '(:target-dsl "2.33")',
        f'(:target-dsl "{syntax.EVALUATED_EXECUTION_MIN_TARGET_DSL_VERSION}")',
    )
    compiled = build(
        tmp_path,
        source,
        boundaries={
            "fetch": ExternalToolBinding(
                name="fetch", stable_command=("python", "probe.py"), closure=()
            )
        },
    )
    program = ClosedProgram.from_artifact(compiled.artifact())
    values = import_module("orchestrator.workflow.evaluated.values")
    dispatched: list[tuple[int, str]] = []

    def perform(node, operands, identity):
        command_argument, argument = operands
        assert command_argument.value == "fetch"
        dispatched.append((argument.value, identity))
        return values.coerce_evaluated_value(
            {"n": argument.value * 10}, node["result"], dependencies={identity}
        )

    result = _machine_api().evaluate_closed_program(
        program, {}, effect_handler=perform
    )

    assert result.value == 100
    assert [argument for argument, _ in dispatched] == [1, 2, 3, 4]
    assert [identity for _, identity in dispatched] == [
        "workflow:spk/arms_in_loop::run / loop:state[1] / got / body / FIRST / "
        "#1=procedure:spk/arms_in_loop::fetch / #1",
        "workflow:spk/arms_in_loop::run / loop:state[2] / got / body / SECOND / "
        "#1=procedure:spk/arms_in_loop::fetch / #1",
        "workflow:spk/arms_in_loop::run / loop:state[3] / got / body / THIRD / "
        "#1=procedure:spk/arms_in_loop::fetch / #1",
        "workflow:spk/arms_in_loop::run / loop:state[4] / got / body / FIRST / "
        "#1=procedure:spk/arms_in_loop::fetch / #1",
    ]
    assert result.dependencies == frozenset(dispatched_identity for _, dispatched_identity in dispatched)


def test_effectful_if_selects_values_without_making_branch_entry_an_effect_input(
    tmp_path: Path,
) -> None:
    sources, entry = _control_sources("effectful_if_branches", "direct")
    source = sources["cp/probe.orc"]
    source = source.replace(
        "(defworkflow run () -> Int", "(defworkflow run ((flag Bool)) -> Int"
    ).replace("(if true", "(if flag")
    program = _build_read_back(tmp_path, {"cp/probe.orc": source}, entry)
    values = import_module("orchestrator.workflow.evaluated.values")
    effects = []

    result = _machine_api().evaluate_closed_program(
        program,
        {"flag": values.EvaluatedValue(True, BOOL, {"input:flag"})},
        effect_handler=_effect_handler(values, effects),
    )

    assert result.value == 13
    assert [row[0] for row in effects] == ["arm-prefix", "arm-value"]
    assert "input:flag" not in effects[0][3]
    assert effects[1][3] == frozenset({effects[0][2]})
    assert result.dependencies == frozenset({"input:flag", effects[0][2], effects[1][2]})


def test_selected_select_prefix_uses_the_machine_binding_callback(tmp_path: Path) -> None:
    sources, entry = _control_sources("pure_select_prefixes", "direct")
    sources["cp/probe.orc"] = sources["cp/probe.orc"].replace(
        "(defworkflow run () -> Int", "(defworkflow run ((flag Bool)) -> Int"
    ).replace("(if true", "(if flag")
    compiled = _build_read_back(tmp_path, sources, entry)
    effectful_sources, effectful_entry = _control_sources("effectful_if_branches", "direct")
    effectful = _build_read_back(tmp_path / "effectful", effectful_sources, effectful_entry)
    tree = deepcopy(compiled.tree)
    arm_prefix = next(
        name for name in effectful.tree["definitions"]
        if name.endswith("::arm-prefix")
    )
    tree["definitions"][arm_prefix] = deepcopy(effectful.tree["definitions"][arm_prefix])
    select = next(node for node in _ast_nodes(tree["body"]) if node.get("k") == "select")
    prefix = select["then"]["prefix"][0]
    prefix["value"] = {
        "k": "call",
        "callee": arm_prefix,
        "args": [{"k": "lit", "v": 11, "type": INT}],
        "type": INT,
    }
    tree["sites"] = [list(row) for row in assign_sites(tree)]
    program = ClosedProgram.from_artifact(
        json.dumps(tree, sort_keys=True, separators=(",", ":"))
    )
    values = import_module("orchestrator.workflow.evaluated.values")
    effects = []

    result = _machine_api().evaluate_closed_program(
        program,
        {"flag": values.EvaluatedValue(True, BOOL, {"input:flag"})},
        effect_handler=_effect_handler(values, effects),
    )

    assert result.value == 13
    assert [row[0] for row in effects] == ["arm-prefix"]
    assert effects[0][2] == (
        "workflow:cp/probe::run / chosen / then / left=procedure:cp/probe::arm-prefix / #1"
    )
    assert "input:flag" not in effects[0][3]
    assert result.dependencies == frozenset({"input:flag", effects[0][2]})


def test_case_variant_value_and_nested_block_execute_selected_effects(tmp_path: Path) -> None:
    cases = (
        ("match_nested_in_if", 18, ["arm-value"]),
        ("effectful_block", 35, ["body-val", "after-val"]),
    )
    for index, (case, expected, names) in enumerate(cases):
        sources, entry = _control_sources(case, "direct")
        program = _build_read_back(tmp_path / str(index), sources, entry)
        values = import_module("orchestrator.workflow.evaluated.values")
        effects = []
        result = _machine_api().evaluate_closed_program(
            program, {}, effect_handler=_effect_handler(values, effects)
        )

        assert result.value == expected
        assert [row[0] for row in effects] == names
    block_call = effects[0][2]
    assert "held / block / " in block_call


def test_join_halt_continuation_and_strict_branch_execution(tmp_path: Path) -> None:
    sources, entry = _control_sources("join_body_and_continuation", "direct")
    program = _build_read_back(tmp_path, sources, entry)
    values = import_module("orchestrator.workflow.evaluated.values")
    effects = []

    result = _machine_api().evaluate_closed_program(
        program, {}, effect_handler=_effect_handler(values, effects)
    )

    assert result.value is True
    assert [row[0] for row in effects] == ["check", "check", "check"]
    assert [row[1][-1] for row in effects] == [1, 2, 4]
    assert "check 3" not in [f"check {row[1][-1]}" for row in effects]
    assert result.dependencies == frozenset(row[2] for row in effects)


def test_effectful_terminal_and_aggregate_positions(tmp_path: Path) -> None:
    source = f'''(workflow-lisp (:language "0.1") (:target-dsl "{TARGET}")
      (defmodule terminal_machine) (export run)
      (defrecord Box (n Int))
      (defproc fetch ((n Int)) -> Box
        :effects ((uses-command fetch)) :lowering inline
        (command-result fetch :argv ("python" "probe.py" n) :returns Box))
      (defproc arm-value ((n Int)) -> Int
        :effects ((uses-command arm-value)) :lowering inline
        (command-result arm-value :argv ("python" "probe.py" n) :returns Int))
      (defworkflow run ((boxed Bool)) -> Box
        (if boxed
          (let* ((n (if boxed (arm-value 1) (arm-value 2)))) (record Box :n n))
          (fetch 7))))'''
    boundaries = {
        name: ExternalToolBinding(
            name=name, stable_command=("python", "probe.py"), closure=()
        )
        for name in ("fetch", "arm-value")
    }
    program = _build_read_back(
        tmp_path, {"terminal_machine.orc": source}, "terminal_machine::run",
        boundaries=boundaries,
    )
    values = import_module("orchestrator.workflow.evaluated.values")
    aggregate_effects = []
    aggregate = _machine_api().evaluate_closed_program(
        program, {"boxed": True},
        effect_handler=_effect_handler(values, aggregate_effects),
    )
    direct_effects = []
    result = _machine_api().evaluate_closed_program(
        program, {"boxed": False}, effect_handler=_effect_handler(values, direct_effects)
    )
    assert aggregate.value == {"n": 2}
    assert aggregate.dependencies == frozenset({aggregate_effects[0][2]})
    assert result.value == {"n": 70}
    assert [row[0] for row in aggregate_effects] == ["arm-value"]
    assert [row[0] for row in direct_effects] == ["fetch"]


def test_run_context_and_committed_result_path_are_machine_values(tmp_path: Path) -> None:
    context_source = f'''(workflow-lisp (:language "0.1") (:target-dsl "{TARGET}")
      (defmodule context_machine) (import std/context :only (RunCtx)) (export entry)
      (defworkflow entry ((run RunCtx)) -> RunId run.run-id))'''
    context_program = _build_read_back(
        tmp_path / "context", {"context_machine.orc": context_source}, "context_machine::entry",
    )
    context_result = _machine_api().evaluate_closed_program(
        context_program, {}, run_id="machine-run-1"
    )
    assert context_result.value == "machine-run-1"

    result_source = f'''(workflow-lisp (:language "0.1") (:target-dsl "{TARGET}")
      (defmodule result_path_machine) (export run)
      (defpath ResultBundle :kind relpath :under ".orchestrate/runs" :must-exist false)
      (defrecord Result (text String))
      (defrecord Projection (bundle ResultBundle))
      (defworkflow run ((seed String)) -> Projection
        (let* ((r (provider-result provider :prompt prompt :inputs (seed) :returns Result)))
          (record Projection :bundle (provider-bundle-path r :as ResultBundle)))))'''
    prompt = PromptExtern(name="prompt", input_file="inputs/prompt.md")
    result_program = _build_read_back(
        tmp_path / "result-path", {"result_path_machine.orc": result_source},
        "result_path_machine::run",
        provider_externs={"provider": "probe-provider"}, prompt_externs={"prompt": prompt},
    )
    values = import_module("orchestrator.workflow.evaluated.values")
    effects = []

    def provider(node, operands, identity):
        effects.append(identity)
        return values.coerce_evaluated_value(
            {"text": "complete"}, node["result"], dependencies={identity},
            committed_result_path=".orchestrate/runs/machine-run-1/result.json",
        )

    result = _machine_api().evaluate_closed_program(
        result_program,
        {"seed": "input"},
        effect_handler=provider,
        run_id="machine-run-1",
    )
    assert result.value == {"bundle": ".orchestrate/runs/machine-run-1/result.json"}
    assert result.dependencies == frozenset(effects)


def test_effect_identity_survives_pure_binding_insertion_and_escapes_authored_names(
    tmp_path: Path,
) -> None:
    source_path = (
        Path(__file__).parent
        / "experiments/fixtures/evaluated_execution_spike/arms_in_loop.orc"
    )
    source = source_path.read_text(encoding="utf-8").replace(
        '(:target-dsl "2.33")',
        f'(:target-dsl "{syntax.EVALUATED_EXECUTION_MIN_TARGET_DSL_VERSION}")',
    )
    refactored = source.replace(
        "(defworkflow run () -> Int\n    (loop/recur",
        "(defworkflow run () -> Int\n    (let* ((seed (+ 0 0))) (loop/recur",
    ).replace("(i Int 0)", "(i Int seed)").replace(
        "(done (+ state.total got.n))))))))",
        "(done (+ state.total got.n)))))))))",
    )
    boundaries = {
        "fetch": ExternalToolBinding(
            name="fetch", stable_command=("python", "probe.py"), closure=()
        )
    }
    plain = _build_read_back(tmp_path / "plain", {"spk/arms_in_loop.orc": source}, "spk/arms_in_loop::run", boundaries=boundaries)
    changed = _build_read_back(tmp_path / "changed", {"spk/arms_in_loop.orc": refactored}, "spk/arms_in_loop::run", boundaries=boundaries)
    values = import_module("orchestrator.workflow.evaluated.values")
    plain_effects = []
    changed_effects = []
    _machine_api().evaluate_closed_program(plain, {}, effect_handler=_effect_handler(values, plain_effects))
    _machine_api().evaluate_closed_program(changed, {}, effect_handler=_effect_handler(values, changed_effects))
    assert [row[2] for row in plain_effects] == [row[2] for row in changed_effects]

    escaped = source.replace("got", "got/one")
    escaped_program = _build_read_back(
        tmp_path / "escaped", {"spk/arms_in_loop.orc": escaped},
        "spk/arms_in_loop::run", boundaries=boundaries,
    )
    escaped_effects = []
    _machine_api().evaluate_closed_program(
        escaped_program, {}, effect_handler=_effect_handler(values, escaped_effects)
    )
    assert any("got%2Fone" in row[2] for row in escaped_effects)


INT = {"kind": "primitive", "name": "Int"}
BOOL = {"kind": "primitive", "name": "Bool"}


def _build_read_back(
    root: Path,
    sources,
    entry: str,
    *,
    boundaries=None,
    provider_externs=None,
    prompt_externs=None,
) -> ClosedProgram:
    from tests.test_workflow_lisp_closed_program_corpus import _CONTROL_COMMANDS

    command_names = set(_CONTROL_COMMANDS)
    configured = boundaries or {
        name: ExternalToolBinding(
            name=name, stable_command=("python", "probe.py"), closure=()
        )
        for name in command_names
    }
    bundle = build(
        root,
        sources,
        entry_workflow=entry,
        boundaries=configured,
        providers=provider_externs or {"provider": "probe-provider"},
        prompts=prompt_externs or {
            "prompt": PromptExtern(name="prompt", input_file="inputs/prompt.md")
        },
    )
    return ClosedProgram.from_artifact(bundle.artifact())


def _effect_handler(values, effects):
    def perform(node, operands, identity):
        boundary = node["boundary"]
        arguments = tuple(value.value for value in operands)
        dependencies = frozenset(
            dependency for value in operands for dependency in value.dependencies
        )
        effects.append((boundary, arguments, identity, dependencies))
        value = arguments[-1]
        if boundary == "fetch":
            value = {"n": value * 10}
        elif boundary == "check":
            value = value != 3
        elif boundary in {"arm-prefix", "arm-value", "body-val", "after-val", "next-val"}:
            value += 1
        return values.coerce_evaluated_value(
            value, node["result"], dependencies={identity, *dependencies}
        )

    return perform
