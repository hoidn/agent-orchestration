from __future__ import annotations

from collections import Counter
import json
from pathlib import Path

import pytest

from orchestrator.workflow_lisp import syntax
from orchestrator.workflow_lisp.build import FrontendBuildRequest
from orchestrator.workflow_lisp.closed.artifact import build_closed_program_bundle
from orchestrator.workflow_lisp.closed.build import build_closed_program
from orchestrator.workflow_lisp.closed.frontend import compile_typed_program
from orchestrator.workflow_lisp.closed.program import ClosedProgram, _sites_from_nodes
from orchestrator.workflow_lisp.closed.sites import _ast_nodes
from orchestrator.workflow_lisp.compiler import compile_stage3_entrypoint
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from orchestrator.workflow_lisp.stdlib_contracts import STDLIB_CERTIFIED_ADAPTER_BINDINGS_BY_NAME
from tests.workflow_lisp_closed_program_corpus import (
    Built,
    Gap,
    NotSynthesizable,
    Refused,
    corpus,
    entry_with_target,
    target_dsl_version,
    try_build,
)


TARGET = syntax.EVALUATED_EXECUTION_MIN_TARGET_DSL_VERSION


EXPECTED = {
    "experiments/mlevolve_pair/probes/malformed_result.orc::run": Built(1),
    "experiments/mlevolve_pair/probes/missing_bundle.orc::run": Built(1),
    "experiments/mlevolve_pair/search.orc::run-search": Built(12),
    "experiments/mlevolve_pair/search_compact.orc::run-search": Built(6),
    "experiments/orc_vs_single_call/task/bug_report/reviewed_change.orc::reviewed-change": Built(4),
    "experiments/orc_vs_single_call/workflows/best_of_n.orc::best-of-n": Built(2),
    "experiments/orc_vs_single_call/workflows/best_of_n.orc::select-only": Built(1),
    "experiments/orc_vs_single_call/workflows/reviewed_change.orc::reviewed-change": Built(4),
    "workflows/examples/cycle_guard_demo.orc::cycle-guard-demo": Built(1),
    "workflows/examples/design_plan_impl_review_stack_v2_call.orc::design-plan-impl-review-stack": Built(6),
    "workflows/examples/effectful_let_star_normalization.orc::run-effectful-let-star-normalization": Built(4),
    "workflows/examples/effectful_match_arm_normalization.orc::run-effectful-match-arm-normalization": Built(3),
    "workflows/examples/improve_experiment_proposal.orc::run-experiment": Built(5),
    "workflows/examples/kiss_backlog_item.orc::run-backlog-item": Built(12),
    "workflows/examples/review_revise_design_docs.orc::review-revise-design-docs": Refused("workflow_signature_mismatch"),
    "workflows/examples/review_revise_design_docs_judgment_panel.orc::review-revise-design-docs-judgment-panel": Built(2),
    "workflows/examples/review_revise_parametric_design_docs.orc::review-revise-parametric-design-docs": Refused("macro_arity_error"),
    "workflows/examples/same_file_record_call_binding.orc::run-same-file-record-call-binding": Built(1),
    "workflows/examples/with_phase_composed_binding.orc::run-with-phase-composed-binding": Built(1),
    "workflows/experiments/qa_placement_effectiveness/qa_placement_arms.orc::design-qa": Built(4),
    "workflows/experiments/qa_placement_effectiveness/qa_placement_arms.orc::direct": Built(1),
    "workflows/experiments/qa_placement_effectiveness/qa_placement_arms.orc::product-qa": Built(3),
    "workflows/experiments/qa_placement_effectiveness/qa_placement_arms.orc::rich": Built(6),
    "workflows/experiments/qa_placement_effectiveness/qa_placement_trial.orc::compare": Gap("trial"),
    "workflows/experiments/repository_task_pilot/task_loop.orc::run-task": NotSynthesizable(("command 'pilot_product_manifest' is parameterized by workflow input 'controller_script', whose concrete script path, source bytes, and closure are missing",)),
    "workflows/library/control/direct_task.orc::direct-task": Built(1),
    "workflows/library/design_plan_impl_implementation_phase.orc::design-plan-impl-implementation-phase": Built(2),
    "workflows/library/generic_run_watchdog/watchdog.orc::watchdog": Built(5),
    "workflows/library/lisp_frontend_design_delta/bootstrap.orc::project-work-item-inputs": Built(0),
    "workflows/library/lisp_frontend_design_delta/design_gap_architect.orc::draft-design-gap-architecture": Built(1),
    "workflows/library/lisp_frontend_design_delta/design_gap_architect.orc::draft-design-gap-architecture-stdlib": Built(1),
    "workflows/library/lisp_frontend_design_delta/design_gap_architect.orc::project-design-gap-architecture-targets": Built(0),
    "workflows/library/lisp_frontend_design_delta/design_gap_architect.orc::project-design-gap-architecture-targets-stdlib": Built(0),
    "workflows/library/lisp_frontend_design_delta/design_gap_architect.orc::validate-design-gap-architecture": Gap("materialize-view"),
    "workflows/library/lisp_frontend_design_delta/design_gap_architect.orc::validate-design-gap-architecture-stdlib": Gap("materialize-view"),
    "workflows/library/lisp_frontend_design_delta/drain.orc::drain": Refused("provider_bundle_path_target_invalid"),
    "workflows/library/lisp_frontend_design_delta/implementation_phase.orc::implementation-phase": Gap("materialize-view"),
    "workflows/library/lisp_frontend_design_delta/plan_phase.orc::run-plan-phase": Gap("materialize-view"),
    "workflows/library/lisp_frontend_design_delta/projections.orc::classify-work-item-terminal": Built(0),
    "workflows/library/lisp_frontend_design_delta/projections.orc::project-selector-action": Built(0),
    "workflows/library/lisp_frontend_design_delta/runtime_transition_fixture.orc::run-runtime-transition-fixture": Gap("resource-transition"),
    "workflows/library/lisp_frontend_design_delta/runtime_view_fixture.orc::run-summary-view": Gap("resource-transition"),
    "workflows/library/lisp_frontend_design_delta/selector.orc::select-next-work": Refused("provider_bundle_path_target_invalid"),
    "workflows/library/lisp_frontend_design_delta/stdlib_payloads.orc::project-selected-item-payload": Built(0),
    "workflows/library/lisp_frontend_design_delta/stdlib_payloads.orc::project-selection-result": Built(0),
    "workflows/library/lisp_frontend_design_delta/transitions.orc::apply-drain-status-transition": Gap("resource-transition"),
    "workflows/library/lisp_frontend_design_delta/transitions.orc::emit-drain-status-transition-audit": Gap("resource-transition"),
    "workflows/library/lisp_frontend_design_delta/work_item.orc::classify-blocked-implementation-recovery": Built(1),
    "workflows/library/lisp_frontend_design_delta/work_item.orc::run-work-item": Gap("materialize-view"),
    "workflows/library/tracked_design_phase.orc::tracked-design-phase": Built(2),
    "workflows/library/tracked_plan_phase.orc::tracked-plan-phase": Built(2),
    "workflows/library/verified_iteration_drain/drain.orc::drain": Built(9),
}

EXPECTED_PARTITION = {
    "Built": 37,
    "Gap": 10,
    "Refused": 4,
    "NotSynthesizable": 1,
}


_CONTROL_ROUTES = ("direct", "same_module", "imported_old_source")
_CONTROL_CASES = {
    "effectful_if_branches": (
        "Int",
        """(let* ((chosen (if true
            (let* ((left-prefix (arm-prefix 11))) (arm-value left-prefix))
            (let* ((right-prefix (arm-prefix 22))) (arm-value right-prefix))))) chosen)""",
        "",
    ),
    "pure_select_prefixes": (
        "Int",
        """(let* ((chosen (if true
            (let* ((left (+ 11 1))) (+ left 1))
            (let* ((right (+ 22 1))) (+ right 1))))) chosen)""",
        "",
    ),
    "effectful_block": (
        "Int",
        "(let* ((held (make-block (+ (body-val 31) 1)))) (after-val held))",
        "(defun make-block ((value Int)) -> Int (let* ((inside (+ value 1))) inside))",
    ),
    "join_body_and_continuation": (
        "Bool",
        "(and (if (check 1) (check 2) (check 3)) (check 4))",
        "",
    ),
    "if_nested_in_if": (
        "Bool",
        "(if (check 0) (if (check 1) (check 2) (check 3)) (check 4))",
        "",
    ),
    "match_nested_in_if": (
        "Int",
        """(if true
            (match (variant Route LEFT :value 17)
              ((LEFT left) (arm-value left.value))
              ((RIGHT right) (arm-value right.value)))
            (arm-value 99))""",
        "(defunion Route (LEFT (value Int)) (RIGHT (value Int)))",
    ),
    "loop_nested_in_if": (
        "Int",
        """(if true
            (loop/recur :max 2 :state (loop-state (i Int (seed 0))) :on-exhausted state.i
              (fn (state)
                (let* ((next (next-val state.i)))
                  (if (< next 2)
                    (continue (loop-state :like state :i next))
                    (done (done-val next))))))
            (done-val 9))""",
        "",
    ),
    "loop_budget_before_seed": (
        "Int",
        """(loop/recur :max (budget 3) :state (loop-state (i Int (seed 0)))
            :on-exhausted state.i (fn (state) (done (done-val state.i))))""",
        "",
    ),
    "loop_seed_before_budget": (
        "Int",
        """(loop/recur :state (loop-state (i Int (seed 0))) :max (budget 3)
            :on-exhausted state.i (fn (state) (done (done-val state.i))))""",
        "",
    ),
    "loop_continue_and_done": (
        "Int",
        """(loop/recur :max 3 :state (loop-state (i Int 0)) :on-exhausted state.i
            (fn (state) (if (< state.i 2)
              (continue (loop-state :like state :i (next-val state.i)))
              (done (done-val state.i)))))""",
        "",
    ),
    "nested_loop_in_done": (
        "Bool",
        """(if (loop/recur :max 1 :state (loop-state (i Int 0)) :on-exhausted false
            (fn (outer) (done (loop/recur :state (loop-state (i Int (seed 0)))
              :max (budget 3) :on-exhausted false (fn (inner) (done (check 1))))))) true false)""",
        "",
    ),
    "list_map_value_block": (
        "List[Int]",
        "(list/map ((item (list 1 2))) (let* ((one (+ item 1)) (two (+ one 1))) two))",
        "",
    ),
}

_CONTROL_REFUSALS = {
    "effectful_loop_exhaustion": (
        "Int",
        """(loop/recur :max 0 :state (loop-state (i Int 0))
            :on-exhausted (done-val state.i) (fn (state) (done state.i)))""",
        "",
        "loop_recur_contract_invalid",
    ),
    "effectful_list_map_body": (
        "List[Int]",
        "(list/map ((item (list 1 2))) (body-val item))",
        "",
        "list_map_body_effect_forbidden",
    ),
}

_CONTROL_COMMANDS = (
    "budget", "seed", "done-val", "next-val", "arm-prefix", "arm-value",
    "body-val", "after-val", "check",
)


def _control_procedures() -> str:
    return "\n".join(
        f'''(defproc {name} ((n Int)) -> {"Bool" if name == "check" else "Int"}
          :effects ((uses-command {name})) :lowering inline
          (command-result {name} :argv ("python" "probe.py" n) :returns {"Bool" if name == "check" else "Int"}))'''
        for name in _CONTROL_COMMANDS
    )


def _control_sources(case: str, route: str) -> tuple[dict[str, str], str]:
    specification = _CONTROL_CASES.get(case) or _CONTROL_REFUSALS[case]
    result_type, body, extra = specification[:3]
    target = syntax.EVALUATED_EXECUTION_MIN_TARGET_DSL_VERSION
    entry_header = f'(workflow-lisp (:language "0.1") (:target-dsl "{target}") (defmodule cp/probe)'
    old_header = '(workflow-lisp (:language "0.1") (:target-dsl "2.34") (defmodule cp/old)'
    if route == "direct":
        text = f'''{entry_header} (export run)
{_control_procedures()}
{extra}
(defworkflow run () -> {result_type} {body}))'''
        return {"cp/probe.orc": text}, "cp/probe::run"
    if route == "same_module":
        text = f'''{entry_header} (export run)
{_control_procedures()}
{extra}
(defworkflow helper () -> {result_type} {body})
(defworkflow run () -> {result_type} (call helper)))'''
        return {"cp/probe.orc": text}, "cp/probe::run"
    if route == "imported_old_source":
        entry = f'''{entry_header} (import cp/old :as old) (export run)
(defworkflow run () -> {result_type} (call old.helper)))'''
        helper = f'''{old_header} (export helper)
{_control_procedures()}
{extra}
(defworkflow helper () -> {result_type} {body}))'''
        return {"cp/probe.orc": entry, "cp/old.orc": helper}, "cp/probe::run"
    raise AssertionError(f"unknown control route {route}")


def _control_chain(node: dict) -> tuple[list[dict], dict]:
    rows = []
    while node.get("k") == "let":
        rows.append(node)
        node = node["body"]
    return rows, node


def _control_nodes(node: dict, kind: str) -> list[dict]:
    return [row for row in _ast_nodes(node) if row.get("k") == kind]


def _control_calls(node: dict) -> list[dict]:
    return _control_nodes(node, "call")


def _control_callee(node: dict, definitions: dict, expected_module: str) -> str:
    declaration = definitions[node["callee"]]["key"]
    assert declaration[:2] == [expected_module, "procedure"]
    return declaration[2]


def _control_argument(node: dict, definitions: dict) -> dict:
    definition = definitions[node["callee"]]
    key = definition["key"]
    assert key[2] in _CONTROL_COMMANDS  # Each authored control procedure has exactly n:Int.
    integer = {"kind": "primitive", "name": "Int"}
    closed = {name: (type_row, value) for name, type_row, value in key[6]}
    if "n" in closed:
        assert set(closed) == {"n"}
        type_row, value = closed["n"]
        assert type_row == integer
        assert key[8]["params"] == definition["params"] == node["args"] == []
        return value
    assert closed == {}
    assert key[8]["params"] == [integer]
    ((wire, type_row),) = definition["params"]
    assert type_row == integer
    arguments = dict(zip((name for name, _ in definition["params"]), node["args"], strict=True))
    return arguments[wire]


def _assert_control_edge(
    case: str, body: dict, definitions: dict, expected_module: str
) -> None:
    def callee(node: dict) -> str:
        return _control_callee(node, definitions, expected_module)

    def argument(node: dict) -> dict:
        return _control_argument(node, definitions)

    if case == "effectful_if_branches":
        (branch,) = _control_nodes(body, "if")
        joins = _control_nodes(body, "join")
        for edge, literal in (("then", 11), ("else", 22)):
            rows, tail = _control_chain(branch[edge])
            calls = [row for row in rows if row["value"].get("k") == "call"]
            assert [callee(row["value"]) for row in calls] == ["arm-prefix", "arm-value"]
            assert " / " + edge + " / " in calls[0]["value"]["frame"]
            assert " / " + edge + " / " in calls[1]["value"]["frame"]
            assert argument(calls[0]["value"])["v"] == literal
            assert argument(calls[1]["value"])["n"] == calls[0]["name"]
            assert tail["k"] == "jump"
            assert any(join["name"] == tail["join"] for join in joins)
    elif case == "pure_select_prefixes":
        (selected,) = _control_nodes(body, "select")
        for edge, literal, binder in (("then", 11, "left"), ("else", 22, "right")):
            arm = selected[edge]
            assert len(arm["prefix"]) == 1
            prefix = arm["prefix"][0]
            assert prefix["name"] == binder and prefix["value"]["k"] == "op"
            assert prefix["value"]["args"][0]["v"] == literal
            assert arm["value"]["k"] == "op"
            assert arm["value"]["args"][0]["k"] == "name"
            assert arm["value"]["args"][0]["n"] == binder
            assert not _control_calls(arm["value"])
    elif case == "effectful_block":
        rows, _tail = _control_chain(body)
        held = next(row for row in rows if row.get("label") == "held")
        assert held["value"]["k"] == "block"
        block_rows, block_tail = _control_chain(held["value"]["body"])
        assert len(block_rows) == 4
        first, add_argument, preserve_alias, inside = block_rows
        inside_call = first["value"]
        assert inside_call["k"] == "call" and callee(inside_call) == "body-val"
        assert "held / block / " in inside_call["frame"]
        assert argument(inside_call)["k"] == "lit" and argument(inside_call)["v"] == 31
        assert add_argument["value"]["k"] == "op"
        assert add_argument["value"]["args"][0]["n"] == first["name"]
        assert preserve_alias["value"]["k"] == "name"
        assert preserve_alias["value"]["n"] == add_argument["name"]
        assert inside.get("label") == "inside" and inside["value"]["k"] == "op"
        assert inside["value"]["args"][0]["n"] == preserve_alias["name"]
        assert block_tail["k"] == "halt" and block_tail["value"]["n"] == inside["name"]
        after = [call for call in _control_calls(held["body"]) if callee(call) == "after-val"]
        assert len(after) == 1
        assert argument(after[0])["k"] == "name"
        assert argument(after[0])["n"] == "held"
    elif case == "join_body_and_continuation":
        join = next(
            row for row in _control_nodes(body, "join")
            if [callee(call) for call in _control_calls(row["body"])] == ["check"] * 3
        )
        assert [callee(call) for call in _control_calls(join["body"])] == ["check"] * 3
        assert [callee(call) for call in _control_calls(join["cont"]["then"])] == ["check"]
        assert not _control_calls(join["cont"]["else"])
        assert [argument(call)["v"] for call in _control_calls(join["cont"]["then"])] == [4]
        assert all(jump["join"] == join["name"] for jump in _control_nodes(join["body"], "jump"))
    elif case == "if_nested_in_if":
        calls = [call for call in _control_calls(body) if callee(call) == "check"]
        by_literal = {argument(call)["v"]: call for call in calls}
        assert set(by_literal) == {0, 1, 2, 3, 4}
        assert "then / then / " in by_literal[2]["frame"]
        assert "then / else / " in by_literal[3]["frame"]
        assert "else / " in by_literal[4]["frame"]
    elif case == "match_nested_in_if":
        (match_case,) = _control_nodes(body, "case")
        assert [arm["variant"] for arm in match_case["arms"]] == ["LEFT", "RIGHT"]
        arm_calls = [
            [call for call in _control_calls(arm["body"]) if callee(call) == "arm-value"]
            for arm in match_case["arms"]
        ]
        assert [len(calls) for calls in arm_calls] == [1, 1]
        assert all(
            f"then / {arm['variant']} / " in calls[0]["frame"]
            for arm, calls in zip(match_case["arms"], arm_calls, strict=True)
        )
        assert argument(arm_calls[0][0])["k"] == "field"
        assert argument(arm_calls[0][0])["path"] == ["value"]
        assert argument(arm_calls[0][0])["base"]["n"] != argument(arm_calls[1][0])["base"]["n"]
        assert any(
            argument(call).get("v") == 99
            for call in _control_calls(body)
            if callee(call) == "arm-value"
        )
    elif case == "loop_nested_in_if":
        (loop,) = _control_nodes(body, "loop")
        condition = next(
            node for node in _control_nodes(body, "if")
            if _control_nodes(node["then"], "loop")
        )
        assert _control_nodes(condition["then"], "loop") == [loop]
        assert [
            argument(call)["v"] for call in _control_calls(condition["else"])
        ] == [9]
        calls = _control_calls(loop["body"])
        assert {callee(call) for call in calls} == {"next-val", "done-val"}
        assert all("loop:state[*]" in call["frame"] for call in calls)
        transfer = next(node for node in _control_nodes(loop["body"], "continue"))
        assert transfer["loop"] == loop["name"]
    elif case in {"loop_budget_before_seed", "loop_seed_before_budget"}:
        (loop,) = _control_nodes(body, "loop")
        rows, _tail = _control_chain(body)
        calls = [row["value"] for row in rows if row["value"].get("k") == "call"]
        names = [callee(call) for call in calls]
        expected = ["budget", "seed"] if case == "loop_budget_before_seed" else ["seed", "budget"]
        assert names == expected
        bindings = {row["name"]: row["value"] for row in rows}
        assert callee(bindings[loop["budget"]["n"]]) == "budget"
        state = bindings[loop["init"]["n"]]
        seed_ref = state["fields"][0][1]["n"]
        assert callee(bindings[seed_ref]) == "seed"
        assert [callee(call) for call in _control_calls(loop["body"])] == ["done-val"]
        assert not _control_calls(loop.get("exhausted", {}))
        assert any("loop:state[*]" in call["frame"] for call in _control_calls(loop["body"]))
    elif case == "loop_continue_and_done":
        (loop,) = _control_nodes(body, "loop")
        transfers = [
            node for kind in ("continue", "done") for node in _control_nodes(loop["body"], kind)
        ]
        assert {node["k"] for node in transfers} == {"continue", "done"}
        (continue_node,) = [node for node in transfers if node["k"] == "continue"]
        assert continue_node["loop"] == loop["name"]
        assert {callee(call) for call in _control_calls(loop["body"])} == {"next-val", "done-val"}
        condition = next(node for node in _control_nodes(loop["body"], "if"))
        then_rows, continued = _control_chain(condition["then"])
        else_rows, finished = _control_chain(condition["else"])
        assert continued["k"] == "continue" and finished["k"] == "done"
        assert any(
            row["value"].get("k") == "call" and callee(row["value"]) == "next-val"
            for row in then_rows
        )
        assert any(
            row["value"].get("k") == "call" and callee(row["value"]) == "done-val"
            for row in else_rows
        )
        next_binding = next(
            row for row in then_rows
            if row["value"].get("k") == "call" and callee(row["value"]) == "next-val"
        )
        update_binding = next(
            row for row in then_rows
            if row["value"].get("k") == "op"
            and row["value"].get("payload", {}).get("expr", {}).get("kind") == "record_update"
        )
        assert update_binding["value"]["args"][1]["n"] == next_binding["name"]
        assert continued["args"][0]["n"] == update_binding["name"]
        done_binding = next(
            row for row in else_rows
            if row["value"].get("k") == "call" and callee(row["value"]) == "done-val"
        )
        assert finished["value"]["n"] == done_binding["name"]
    elif case == "nested_loop_in_done":
        loops = _control_nodes(body, "loop")
        assert len(loops) == 2
        outer, inner = loops
        calls = _control_calls(body)
        seeded = [call for call in calls if callee(call) in {"seed", "budget"}]
        checked = [call for call in calls if callee(call) == "check"]
        assert {callee(call) for call in seeded} == {"seed", "budget"}
        assert len(checked) == 1
        assert "loop:outer[*]" in checked[0]["frame"]
        assert "loop:inner[*]" in checked[0]["frame"]
        assert all("loop:inner[*]" not in call["frame"] for call in seeded)
        assert all("loop:outer[*]" in call["frame"] for call in seeded)
        assert outer["name"] != inner["name"]
    elif case == "list_map_value_block":
        (block,) = _control_nodes(body, "block")
        rows, tail = _control_chain(block["body"])
        assert [row.get("label") for row in rows] == ["one", "two"]
        assert rows[0]["value"]["k"] == "op"
        assert rows[0]["value"]["args"][0]["k"] == "name"
        assert rows[0]["value"]["args"][0]["n"] == "item"
        assert rows[1]["value"]["args"][0]["k"] == "name"
        assert rows[1]["value"]["args"][0]["n"] == "one"
        assert tail["k"] == "halt"
        assert tail["value"]["k"] == "name" and tail["value"]["n"] == "two"
        assert not _control_calls(block["body"])
    else:
        raise AssertionError(f"no assertions declared for control case {case}")


ORIGINAL_TARGET_FLAT_OUTCOMES = {
    "workflows/examples/review_revise_design_docs.orc::review-revise-design-docs": Refused("workflow_signature_mismatch"),
    "workflows/examples/review_revise_parametric_design_docs.orc::review-revise-parametric-design-docs": Refused("macro_arity_error"),
    "workflows/library/lisp_frontend_design_delta/drain.orc::drain": "passed",
    "workflows/library/lisp_frontend_design_delta/selector.orc::select-next-work": "passed",
}


def _certified_adapter_source(target: str, invocation: str) -> str:
    command = (
        '(command-result validate_review_findings_v1 '
        ':argv ("python" "-m" "orchestrator.workflow_lisp.adapters.validate_review_findings_v1" items) '
        ':returns ReviewFindings)'
        if invocation == "argv"
        else '(command-result validate_review_findings_v1 '
        ':adapter validate_review_findings_v1 :inputs ((items_path items)) '
        ':returns ReviewFindings)'
    )
    return f'''(workflow-lisp (:language "0.1") (:target-dsl "{target}")
      (defmodule cp/certified_argv) (export run)
      (defpath ReviewFindingsJsonPath :kind relpath :under "artifacts/work" :must-exist true)
      (defrecord ReviewFindings (schema_version String) (items_path ReviewFindingsJsonPath))
      (defworkflow run ((items ReviewFindingsJsonPath)) -> ReviewFindings
        {command}))'''


@pytest.mark.parametrize("invocation", ("argv", "document"))
def test_certified_adapter_preserves_its_authored_invocation_mode(
    tmp_path: Path, invocation: str
) -> None:
    source_root = tmp_path / invocation
    source_root.mkdir()
    boundaries = {"validate_review_findings_v1": STDLIB_CERTIFIED_ADAPTER_BINDINGS_BY_NAME["validate_review_findings_v1"]}

    source = source_root / "cp" / "certified_argv.orc"
    source.parent.mkdir()
    old_source = source
    old_source.write_text(_certified_adapter_source("2.34", invocation), encoding="utf-8")
    old_build = compile_stage3_entrypoint(
        old_source,
        source_roots=(source_root,),
        workspace_root=source_root,
        command_boundaries=boundaries,
        validate_shared=True,
    )
    assert "cp/certified_argv::run" in old_build.validated_bundles_by_name

    source.write_text(_certified_adapter_source(TARGET, invocation), encoding="utf-8")
    typed = compile_typed_program(
        source,
        entry_workflow="cp/certified_argv::run",
        source_roots=(source_root,),
        workspace_root=source_root,
        command_boundaries=boundaries,
    )
    closed = build_closed_program(typed)
    restored = ClosedProgram.from_artifact(closed.artifact())
    assert (restored.tree, restored.sites, restored.digest) == (
        closed.tree,
        closed.sites,
        closed.digest,
    )

    binding = boundaries["validate_review_findings_v1"]
    assert binding.must_not_repeat is False
    assert binding.closure == (".",)
    assert [
        (row.name, row.type_name, row.required, row.transport_key)
        for row in binding.input_signature
    ] == [("items_path", "ReviewFindingsJsonPath", True, "items_path")]
    expected_configuration = {
        "kind": "certified_adapter",
        "name": binding.name,
        "stable_command": list(binding.stable_command),
        "must_not_repeat": binding.must_not_repeat,
        "closure": [{"base": "workspace", "path": path} for path in binding.closure],
        "input_contract": dict(binding.input_contract),
        "output_type_name": binding.output_type_name,
        "effects": list(binding.effects),
        "path_safety": dict(binding.path_safety),
        "source_map_behavior": binding.source_map_behavior,
        "fixture_ids": list(binding.fixture_ids),
        "negative_fixture_ids": list(binding.negative_fixture_ids),
        "behavior_class": binding.behavior_class,
        "input_signature": [
            {
                "name": row.name,
                "type_name": row.type_name,
                "required": row.required,
                "transport_key": row.transport_key,
            }
            for row in binding.input_signature
        ],
        "artifact_contracts": list(binding.artifact_contracts),
        "state_writes": list(binding.state_writes),
        "error_codes": list(binding.error_codes),
        "owner_module": binding.owner_module,
        "replacement_path": binding.replacement_path,
        "invocation_protocol": binding.invocation_protocol,
        "transition_binding": None,
        "view_binding": None,
        "declared_promoted_fields": sorted(binding.declared_promoted_fields),
        "retirement_class": binding.retirement_class,
        "retirement_label": binding.retirement_label,
        "replacement_surface": binding.replacement_surface,
        "bridge_owner": binding.bridge_owner,
        "expiry_condition": binding.expiry_condition,
        "evidence_refs": list(binding.evidence_refs),
        "retirement_status": binding.retirement_status,
    }
    assert closed.tree["configuration"]["commands"][binding.name] == expected_configuration
    (old_lowered,) = old_build.entry_result.lowered_workflows
    (old_step,) = old_lowered.authored_mapping["steps"]
    assert old_step["output_bundle"]["fields"] == [
        {
            "name": "schema_version",
            "json_pointer": "/schema_version",
            "type": "string",
        },
        {
            "name": "items_path",
            "json_pointer": "/items_path",
            "type": "relpath",
            "under": "artifacts/work",
            "must_exist_target": True,
        },
    ]
    if invocation == "argv":
        assert old_step["command"] == [*binding.stable_command, "${inputs.items}"]
    else:
        assert old_step["command"] == [
            *binding.stable_command,
            '{"items_path":${inputs.items|json}}',
        ]

    (effect,) = [
        node
        for node in _ast_nodes(closed.tree["body"])
        if node.get("k") == "perform" and node.get("class") == "command"
    ]
    assert effect["boundary"] == binding.name
    assert effect["command"] == list(binding.stable_command)
    assert effect["closure"] == expected_configuration["closure"]
    assert effect["repeat"] == ("never" if binding.must_not_repeat else "rerun")
    assert effect["contract"]["payload"]["fields"] == old_step["output_bundle"]["fields"]
    if invocation == "argv":
        assert len(effect["argv"]) == 1
        assert (effect["argv"][0]["k"], effect["argv"][0]["n"]) == ("name", "items")
        assert "document" not in effect
    else:
        assert effect["argv"] == []
        assert len(effect["document"]) == 1
        key, value = effect["document"][0]
        assert key == "items_path"
        assert (value["k"], value["n"]) == ("name", "items")


@pytest.mark.parametrize("select_optional", (False, True))
def test_certified_adapter_document_keeps_signature_order_for_selected_optional_fields(
    tmp_path: Path, select_optional: bool
) -> None:
    from dataclasses import replace

    from orchestrator.workflow_lisp.command_boundaries import CertifiedAdapterInputField

    name = "validate_review_findings_v1"
    source_root = tmp_path / ("selected" if select_optional else "required-only")
    source = source_root / "cp" / "signature_document.orc"
    source.parent.mkdir(parents=True)
    script = source_root / "scripts" / "task10_certified_fixture.py"
    script.parent.mkdir()
    script.write_text(
        """# Task10 compile-only command stand-in; runtime behavior is not tested.
import json
import sys

request = json.loads(sys.argv[1])
print(json.dumps(request, sort_keys=True))
""",
        encoding="utf-8",
    )
    base = STDLIB_CERTIFIED_ADAPTER_BINDINGS_BY_NAME[name]
    binding = replace(
        base,
        stable_command=("python", "scripts/task10_certified_fixture.py"),
        closure=("scripts/task10_certified_fixture.py",),
        input_signature=(
            CertifiedAdapterInputField(
                "items_path", "ReviewFindingsJsonPath", True, "items_path"
            ),
            CertifiedAdapterInputField("review_note", "String", False, "review_note"),
            CertifiedAdapterInputField("decision", "String", False, "decision"),
        ),
    )
    selected_inputs = (
        "(items_path items) (decision decision)"
        if select_optional
        else "(items_path items)"
    )
    source.write_text(
        f'''(workflow-lisp (:language "0.1") (:target-dsl "2.34")
          (defmodule cp/signature_document) (export run)
          (defpath ReviewFindingsJsonPath :kind relpath :under "artifacts/work" :must-exist true)
          (defrecord ReviewFindings (items_path ReviewFindingsJsonPath))
          (defworkflow run ((items ReviewFindingsJsonPath) (decision String)) -> ReviewFindings
            (command-result {name} :adapter {name} :inputs ({selected_inputs})
              :returns ReviewFindings)))''',
        encoding="utf-8",
    )
    boundaries = {name: binding}
    old = compile_stage3_entrypoint(
        source,
        source_roots=(source_root,),
        workspace_root=source_root,
        command_boundaries=boundaries,
        validate_shared=True,
    )
    assert "cp/signature_document::run" in old.validated_bundles_by_name
    (old_lowered,) = old.entry_result.lowered_workflows
    (old_step,) = old_lowered.authored_mapping["steps"]
    assert old_step["command"][:-1] == list(binding.stable_command)
    flat_payload = old_step["command"][-1]
    replacements = {
        "${inputs.items|json}": json.dumps("items.json"),
        "${inputs.decision|json}": json.dumps("ship"),
    }
    for marker, value in replacements.items():
        flat_payload = flat_payload.replace(marker, value)
    flat_pairs = json.loads(flat_payload, object_pairs_hook=list)
    expected_pairs = [("items_path", "items.json")]
    if select_optional:
        expected_pairs.append(("decision", "ship"))
    assert flat_pairs == expected_pairs

    source.write_text(
        source.read_text(encoding="utf-8").replace('"2.34"', f'"{TARGET}"'),
        encoding="utf-8",
    )
    typed = compile_typed_program(
        source,
        entry_workflow="cp/signature_document::run",
        source_roots=(source_root,),
        workspace_root=source_root,
        command_boundaries=boundaries,
    )
    closed = build_closed_program(typed)
    restored = ClosedProgram.from_artifact(closed.artifact())
    assert (restored.tree, restored.sites, restored.digest) == (
        closed.tree,
        closed.sites,
        closed.digest,
    )
    config = closed.tree["configuration"]["commands"][name]
    assert config["stable_command"] == list(binding.stable_command)
    assert config["closure"] == [
        {"base": "workspace", "path": "scripts/task10_certified_fixture.py"}
    ]
    assert config["invocation_protocol"] == "json_object_positional_arg"
    assert [
        (row["name"], row["type_name"], row["required"], row["transport_key"])
        for row in config["input_signature"]
    ] == [
        ("items_path", "ReviewFindingsJsonPath", True, "items_path"),
        ("review_note", "String", False, "review_note"),
        ("decision", "String", False, "decision"),
    ]
    (effect,) = [
        node
        for node in _ast_nodes(closed.tree["body"])
        if node.get("k") == "perform" and node.get("boundary") == name
    ]
    assert effect["command"] == list(binding.stable_command)
    assert effect["closure"] == config["closure"]
    assert effect["repeat"] == "rerun"
    assert effect["argv"] == []
    assert [key for key, _value in effect["document"]] == [
        key for key, _value in expected_pairs
    ]
    expected_value_names = ["items", *(["decision"] if select_optional else [])]
    assert [value["n"] for _key, value in effect["document"]] == expected_value_names
    assert effect["contract"]["payload"]["fields"] == old_step["output_bundle"]["fields"]


@pytest.mark.parametrize("workflow", corpus(), ids=lambda workflow: workflow.key)
def test_every_shipped_workflow_has_a_pinned_closed_outcome(
    tmp_path: Path, workflow
) -> None:
    result = try_build(workflow, tmp_path)
    actual = result.outcome
    diagnostic = result.diagnostic

    if isinstance(actual, Built):
        assert result.program is not None
        restored = ClosedProgram.from_artifact(result.program.artifact())
        assert result.program.sites == _sites_from_nodes(result.program.tree)
        assert len(set(result.program.sites)) == len(result.program.sites)
        assert (restored.tree, restored.sites, restored.digest) == (
            result.program.tree,
            result.program.sites,
            result.program.digest,
        )
    elif isinstance(actual, Gap):
        assert diagnostic.code == "closed_program_gap"
        assert f"form={actual.form}" in diagnostic.notes
        assert diagnostic.span.start.line > 0
    elif isinstance(actual, Refused):
        assert result.prepared is not None
        assert diagnostic is not None and diagnostic.code == actual.code
    assert actual == EXPECTED[workflow.key], (
        f"pinned outcome mismatch for {workflow.key}: expected {EXPECTED[workflow.key]!r}, "
        f"got {actual!r}; diagnostic={diagnostic!r}"
    )


@pytest.mark.parametrize(
    "workflow",
    [row for row in corpus() if row.key in ORIGINAL_TARGET_FLAT_OUTCOMES],
    ids=lambda workflow: workflow.key,
)
def test_selected_refusals_keep_their_original_target_flat_outcomes(
    tmp_path: Path, workflow
) -> None:
    result = try_build(workflow, tmp_path)
    assert isinstance(result.outcome, Refused)
    assert result.prepared is not None
    original = workflow.source.read_text(encoding="utf-8")
    assert result.prepared.entry.read_text(encoding="utf-8") == entry_with_target(
        workflow.source, TARGET
    )
    assert target_dsl_version(workflow.source) != TARGET
    result.prepared.entry.write_text(original, encoding="utf-8")
    expected_flat = ORIGINAL_TARGET_FLAT_OUTCOMES[workflow.key]
    try:
        flat = compile_stage3_entrypoint(
            result.prepared.entry,
            entry_workflow=workflow.canonical_name,
            source_roots=result.prepared.source_roots,
            command_boundaries=result.prepared.commands,
            provider_externs=result.prepared.providers,
            prompt_externs=result.prepared.prompts,
            workspace_root=result.prepared.workspace_root,
            validate_shared=True,
        )
    except LispFrontendCompileError as flat_error:
        assert isinstance(expected_flat, Refused)
        assert flat_error.diagnostics[0].code == expected_flat.code
    else:
        assert expected_flat == "passed"
        assert workflow.canonical_name in flat.validated_bundles_by_name
        assert flat.entry_result.lowered_workflows
    assert result.outcome.code == EXPECTED[workflow.key].code
    assert result.outcome == EXPECTED[workflow.key]


def _phase_reference_targets(row):
    references = dict(row['key'][4])
    return tuple(references[formal]['target'][2] for formal in ('review', 'fix'))


def test_phase_reference_variants_keep_their_exact_call_owners(tmp_path):
    (workflow,) = [row for row in corpus() if row.key == 'workflows/examples/kiss_backlog_item.orc::run-backlog-item']
    result = try_build(workflow, tmp_path)
    assert result.program is not None
    tree = result.program.tree
    expected = {3: ('review-plan', 'fix-plan'), 5: ('review-implementation', 'fix-implementation')}
    definitions = [row for row in tree['definitions'].values()
        if row['key'][:3] == ['std/phase', 'procedure', 'review-revise-loop-proc']]
    assert len(definitions) == 2
    for row in definitions:
        (limit,) = [value['v'] for formal, _, value in row['key'][6] if formal == 'max_iterations']
        targets = _phase_reference_targets(row)
        assert targets == expected[limit]
        calls = [node for node in _ast_nodes(row['body']) if node['k'] == 'call']
        assert [tree['definitions'][call['callee']]['key'][2] for call in calls] == list(targets)
    assert ClosedProgram.from_artifact(result.program.artifact()).tree == tree


def test_contracts_and_prompt_inputs_equal_the_flat_routes_for_the_real_programs(
    tmp_path: Path,
) -> None:
    from tests.workflow_lisp_closed_program_p3 import assert_p3_carriers

    assert_p3_carriers(corpus(), tmp_path / "p3")


def test_corpus_keys_and_pinned_partition_are_exact() -> None:
    workflows = corpus()
    keys = [workflow.key for workflow in workflows]
    assert len(workflows) == 52
    assert len(set(keys)) == len(keys)
    assert set(keys) == set(EXPECTED)


def test_pinned_corpus_partition_is_exact() -> None:
    counts = Counter(type(outcome).__name__ for outcome in EXPECTED.values())
    assert counts == EXPECTED_PARTITION
    assert sum(counts.values()) == 52


@pytest.mark.parametrize(
    ("case", "route"),
    [(case, route) for case in _CONTROL_CASES for route in _CONTROL_ROUTES],
    ids=lambda value: value,
)
def test_admitted_control_edges_build_and_read_back_across_source_owners(
    tmp_path: Path, case: str, route: str
) -> None:
    files, entry_workflow = _control_sources(case, route)
    source_root = tmp_path / "src"
    for relative, text in files.items():
        destination = source_root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(text, encoding="utf-8")
    (tmp_path / "probe.py").write_text(
        "raise RuntimeError('Task10 compile-only command; runtime is not tested')\n",
        encoding="utf-8",
    )
    command_manifest = tmp_path / "commands.json"
    command_manifest.write_text(
        json.dumps(
            {
                name: {
                    "kind": "external_tool",
                    "stable_command": ["python", "probe.py"],
                    "closure": ["probe.py"],
                }
                for name in _CONTROL_COMMANDS
            }
        ),
        encoding="utf-8",
    )
    result = build_closed_program_bundle(
        FrontendBuildRequest(
            source_path=source_root / "cp/probe.orc",
            source_roots=(source_root,),
            entry_workflow=entry_workflow,
            command_boundaries_path=command_manifest,
            workspace_root=tmp_path,
        )
    )
    program = result.program
    restored = ClosedProgram.from_artifact(result.artifact_path.read_text(encoding="utf-8"))
    assert program.sites == _sites_from_nodes(program.tree)
    assert len(set(program.sites)) == len(program.sites)
    assert (restored.tree, restored.sites, restored.digest) == (
        program.tree,
        program.sites,
        program.digest,
    )

    definitions = program.tree["definitions"]
    helper_module = "cp/old" if route == "imported_old_source" else "cp/probe"
    if route == "direct":
        body = program.tree["body"]
    else:
        declaration = [helper_module, "workflow", "helper"]
        helper_calls = [
            call
            for call in _control_calls(program.tree["body"])
            if call["callee"] in definitions
            and definitions[call["callee"]]["key"][:3] == declaration
        ]
        assert len(helper_calls) == 1
        helper = definitions[helper_calls[0]["callee"]]
        assert helper["key"][:3] == declaration
        body = helper["body"]
    _assert_control_edge(case, body, definitions, helper_module)


@pytest.mark.parametrize(
    ("case", "route"),
    [(case, route) for case in _CONTROL_REFUSALS for route in _CONTROL_ROUTES],
    ids=lambda value: value,
)
def test_unsupported_control_placements_remain_source_refusals(
    tmp_path: Path, case: str, route: str
) -> None:
    files, entry_workflow = _control_sources(case, route)
    source_root = tmp_path / "src"
    for relative, text in files.items():
        destination = source_root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(text, encoding="utf-8")
    (tmp_path / "probe.py").write_text(
        "raise RuntimeError('Task10 compile-only command; runtime is not tested')\n",
        encoding="utf-8",
    )
    command_manifest = tmp_path / "commands.json"
    command_manifest.write_text(
        json.dumps(
            {
                name: {
                    "kind": "external_tool",
                    "stable_command": ["python", "probe.py"],
                    "closure": ["probe.py"],
                }
                for name in _CONTROL_COMMANDS
            }
        ),
        encoding="utf-8",
    )
    expected_code = _CONTROL_REFUSALS[case][3]
    with pytest.raises(LispFrontendCompileError) as exc_info:
        build_closed_program_bundle(
            FrontendBuildRequest(
                source_path=source_root / "cp/probe.orc",
                source_roots=(source_root,),
                entry_workflow=entry_workflow,
                command_boundaries_path=command_manifest,
                workspace_root=tmp_path,
            )
        )
    assert exc_info.value.diagnostics[0].code == expected_code


@pytest.mark.parametrize("producer_target", ("2.34", TARGET))
def test_prepared_import_manifest_uses_shared_old_and_evaluated_producer_routing(
    tmp_path: Path, producer_target: str
) -> None:
    from tests.workflow_lisp_closed_program_corpus import Workflow, compile, prepare

    source_root = tmp_path / "checked-source"
    source_root.mkdir()
    producer = source_root / "producer.orc"
    producer.write_text(
        f'''(workflow-lisp (:language "0.1") (:target-dsl "{producer_target}")
          (defmodule producer) (export get)
          (defworkflow get ((value Int)) -> Int (+ value 1)))''',
        encoding="utf-8",
    )
    entry = source_root / "consumer.orc"
    entry.write_text(
        '''(workflow-lisp (:language "0.1") (:target-dsl "2.34")
      (defmodule consumer) (export run)
      (defworkflow run ((value Int)) -> Int (call dep :value value)))''',
        encoding="utf-8",
    )
    manifest_path = source_root / "imported_workflow_bundles.json"
    manifest = {
        "dep": {
            "kind": "compiled",
            "path": "producer.orc",
            "entry_workflow": "producer::get",
        }
    }
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    workflow = Workflow(
        source=entry,
        source_root=source_root,
        module="consumer",
        name="run",
    )

    prepared = prepare(workflow, tmp_path / "prepared")
    assert prepared.imported_workflow_manifest == (
        prepared.workspace_root / "imported_workflow_bundles.json"
    )
    assert json.loads(prepared.imported_workflow_manifest.read_text()) == manifest
    assert target_dsl_version(prepared.entry) == TARGET
    assert target_dsl_version(prepared.workspace_root / "producer.orc") == producer_target

    typed = compile(prepared)
    assert typed.target == TARGET
    producer_snapshot = typed.imported_programs["dep"]
    assert producer_snapshot.target == producer_target
    assert producer_snapshot.source_file_digests
    closed = build_closed_program(typed)
    restored = ClosedProgram.from_artifact(closed.artifact())
    assert (restored.tree, restored.sites, restored.digest) == (
        closed.tree,
        closed.sites,
        closed.digest,
    )
    imported = closed.tree["definitions"]["workflow:producer::get"]
    body = imported["body"]
    assert body["k"] == "let"
    assert body["value"]["k"] == "op"
    assert body["value"]["payload"]["expr"]["operator"] == "+"
    assert body["body"]["k"] == "halt"
    assert body["body"]["value"]["n"] == body["name"]
