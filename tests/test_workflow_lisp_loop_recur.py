from __future__ import annotations

import json
from pathlib import Path

import pytest

from orchestrator.workflow_lisp.compiler import (
    compile_stage1_module,
    compile_stage3_entrypoint,
    compile_stage3_module,
)
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from orchestrator.workflow_lisp.loops import ensure_loop_projectable_type
from orchestrator.workflow_lisp.spans import SourcePosition, SourceSpan
from orchestrator.workflow_lisp.type_env import FrontendTypeEnvironment, ListTypeRef


FIXTURES = Path(__file__).parent / "fixtures" / "workflow_lisp"
VALID_MINIMAL_FIXTURE = FIXTURES / "valid" / "loop_recur_minimal.orc"
VALID_UNION_FIXTURE = FIXTURES / "valid" / "loop_recur_union_result.orc"
VALID_ON_EXHAUSTED_RECORD_FIXTURE = FIXTURES / "valid" / "loop_recur_on_exhausted_record.orc"
VALID_ON_EXHAUSTED_UNION_FIXTURE = FIXTURES / "valid" / "loop_recur_on_exhausted_union.orc"
INVALID_MISSING_DONE_FIXTURE = FIXTURES / "invalid" / "loop_recur_missing_done.orc"
INVALID_CONTINUE_FIXTURE = FIXTURES / "invalid" / "loop_recur_continue_type_mismatch.orc"
INVALID_DONE_FIXTURE = FIXTURES / "invalid" / "loop_recur_done_type_mismatch.orc"
INVALID_FN_OUTSIDE_FIXTURE = FIXTURES / "invalid" / "loop_recur_fn_outside_loop.orc"
# Under invalid/ for the evidence that names it; it compiles since effects are admitted in `:on-exhausted`.
ON_EXHAUSTED_EFFECTFUL_FIXTURE = FIXTURES / "invalid" / "loop_recur_on_exhausted_impure.orc"
INVALID_ON_EXHAUSTED_TYPE_MISMATCH_FIXTURE = (
    FIXTURES / "invalid" / "loop_recur_on_exhausted_type_mismatch.orc"
)
INVALID_ON_EXHAUSTED_SCALAR_FRAME_COMPUTED_VALUE_FIXTURE = (
    FIXTURES / "invalid" / "loop_recur_on_exhausted_scalar_frame_computed_value.orc"
)
MODULE_FIXTURES = FIXTURES / "modules"
VALID_IF_LOOP_FIXTURE = FIXTURES / "valid" / "if_conditionals_loop_body.orc"


def _write_module(path: Path, body: str) -> Path:
    path.write_text(body, encoding="utf-8")
    return path


def _compile(path: Path, *, tmp_path: Path, validate_shared: bool = False):
    return compile_stage3_module(
        path,
        provider_externs={"providers.execute": "test-provider"},
        prompt_externs={"prompts.implementation.execute": "prompts/implementation/execute.md"},
        validate_shared=validate_shared,
        workspace_root=tmp_path,
    )


def _compile_entrypoint(path: Path, *, source_root: Path, tmp_path: Path, validate_shared: bool = False):
    return compile_stage3_entrypoint(
        path,
        source_roots=(source_root,),
        provider_externs={"providers.execute": "test-provider"},
        prompt_externs={"prompts.implementation.execute": "prompts/implementation/execute.md"},
        validate_shared=validate_shared,
        workspace_root=tmp_path,
    )


def _assert_diagnostic_code(excinfo: pytest.ExceptionInfo[LispFrontendCompileError], code: str) -> None:
    assert excinfo.value.diagnostics[0].code == code




def test_typecheck_loop_recur_requires_reachable_done(tmp_path: Path) -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile(INVALID_MISSING_DONE_FIXTURE, tmp_path=tmp_path)

    _assert_diagnostic_code(excinfo, "loop_recur_missing_done")


def test_typecheck_loop_recur_rejects_continue_type_mismatch(tmp_path: Path) -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile(INVALID_CONTINUE_FIXTURE, tmp_path=tmp_path)

    _assert_diagnostic_code(excinfo, "loop_recur_continue_type_mismatch")


def test_typecheck_loop_recur_rejects_done_type_mismatch(tmp_path: Path) -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile(INVALID_DONE_FIXTURE, tmp_path=tmp_path)

    _assert_diagnostic_code(excinfo, "loop_recur_done_type_mismatch")


def test_typecheck_loop_recur_admits_effectful_on_exhausted(tmp_path: Path) -> None:
    _compile(ON_EXHAUSTED_EFFECTFUL_FIXTURE, tmp_path=tmp_path)


def test_typecheck_loop_recur_rejects_on_exhausted_type_mismatch(tmp_path: Path) -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile(INVALID_ON_EXHAUSTED_TYPE_MISMATCH_FIXTURE, tmp_path=tmp_path)

    _assert_diagnostic_code(excinfo, "loop_recur_done_type_mismatch")




def test_typecheck_loop_recur_resets_variant_proof_each_iteration(tmp_path: Path) -> None:
    workflow_path = _write_module(
        tmp_path / "loop_recur_proof_reset.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.40")',
                "  (defenum BlockerClass",
                "    missing_resource",
                "    unavailable_hardware",
                "    roadmap_conflict",
                "    external_dependency_outside_authority",
                "    user_decision_required",
                "    unrecoverable_after_fix_attempt)",
                "  (defpath WorkReport",
                "    :kind relpath",
                '    :under "artifacts/work"',
                "    :must-exist true)",
                "  (defunion ImplementationState",
                "    (COMPLETED",
                "      (execution_report WorkReport))",
                "    (BLOCKED",
                "      (progress_report WorkReport)",
                "      (blocker_class BlockerClass)))",
                "  (defrecord ChecksResult",
                "    (status String)",
                "    (report WorkReport))",
                "  (defrecord LoopResult",
                "    (report WorkReport))",
                "  (defworkflow loop-recur-proof-reset",
                "    ((input ChecksResult)",
                "     (report_path WorkReport))",
                "    -> LoopResult",
                "    (let* ((attempt",
                "             (provider-result providers.execute",
                "               :prompt prompts.implementation.execute",
                "               :inputs (input report_path)",
                "               :returns ImplementationState)))",
                "      (match attempt",
                "        ((COMPLETED completed)",
                "         (loop/recur",
                "           :max 2",
                "           :state attempt",
                "           (fn (state)",
                "             (done",
                "               (record LoopResult",
                "                 :report state.execution_report)))))",
                "        ((BLOCKED blocked)",
                "         (record LoopResult",
                "           :report blocked.progress_report))))))",
            ]
        ),
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile(workflow_path, tmp_path=tmp_path)

    _assert_diagnostic_code(excinfo, "variant_ref_unproved")


def test_typecheck_loop_recur_rejects_non_projectable_carried_types(tmp_path: Path) -> None:
    workflow_path = _write_module(
        tmp_path / "loop_recur_non_projectable_state.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.40")',
                "  (defrecord LoopResult",
                "    (status String))",
                "  (defworkflow helper",
                "    ()",
                "    -> LoopResult",
                '    (record LoopResult :status "helper"))',
                "  (defworkflow loop-recur-non-projectable",
                "    ()",
                "    -> LoopResult",
                "    (let* ((payload (workflow-ref helper)))",
                "      (loop/recur",
                "        :max 2",
                "        :state payload",
                "        (fn (state)",
                '          (done (record LoopResult :status "ok")))))))',
            ]
        ),
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile(workflow_path, tmp_path=tmp_path)

    _assert_diagnostic_code(excinfo, "loop_recur_state_type_invalid")


def test_typecheck_loop_recur_rejects_proc_ref_state(tmp_path: Path) -> None:
    workflow_path = _write_module(
        tmp_path / "loop_recur_proc_ref_state.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.40")',
                "  (defrecord WorkflowInput",
                "    (value String))",
                "  (defrecord WorkflowOutput",
                "    (value String))",
                "  (defrecord LoopResult",
                "    (status String))",
                "  (defproc helper",
                "    ((input WorkflowInput))",
                "    -> WorkflowOutput",
                "    (record WorkflowOutput :value input.value))",
                "  (defworkflow loop-recur-proc-ref-state",
                "    ()",
                "    -> LoopResult",
                "    (let* ((payload (proc-ref helper)))",
                "      (loop/recur",
                "        :max 2",
                "        :state payload",
                "        (fn (state)",
                "          (done (record LoopResult :status \"ok\")))))))",
            ]
        ),
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile(workflow_path, tmp_path=tmp_path)

    _assert_diagnostic_code(excinfo, "proc_ref_runtime_transport_forbidden")


def test_typecheck_loop_recur_rejects_proc_ref_done_results(tmp_path: Path) -> None:
    workflow_path = _write_module(
        tmp_path / "loop_recur_proc_ref_done.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.40")',
                "  (defrecord LoopResult",
                "    (status String))",
                "  (defrecord WorkflowInput",
                "    (value String))",
                "  (defrecord WorkflowOutput",
                "    (value String))",
                "  (defproc helper",
                "    ((input WorkflowInput))",
                "    -> WorkflowOutput",
                "    (record WorkflowOutput :value input.value))",
                "  (defworkflow loop-recur-proc-ref-result",
                "    ()",
                "    -> LoopResult",
                "    (let* ((result",
                "             (loop/recur :max 1 :state \"seed\"",
                "               (fn (state)",
                "                 (done (proc-ref helper))))))",
                "      (record LoopResult :status \"ok\"))))",
            ]
        ),
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile(workflow_path, tmp_path=tmp_path)

    _assert_diagnostic_code(excinfo, "proc_ref_runtime_transport_forbidden")




def test_typecheck_loop_recur_rich_list_root_union_uses_defining_type_env(tmp_path: Path) -> None:
    """The target-2.35 loop check receives the defining union environment."""

    definitions_path = _write_module(
        tmp_path / "rich_list_root_union_types.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.40")',
                "  (defrecord Task",
                "    (task_id String))",
                "  (defunion TaskOutcome",
                "    (PENDING (task Task))",
                "    (BLOCKED (reason String)))",
                ")",
            ]
        ),
    )
    type_env = FrontendTypeEnvironment.from_module(compile_stage1_module(definitions_path))
    span = SourceSpan(
        start=SourcePosition(path=str(definitions_path), line=1, column=1, offset=0),
        end=SourcePosition(path=str(definitions_path), line=1, column=2, offset=1),
    )
    state_type = type_env.resolve_type(
        "List[TaskOutcome]",
        span=span,
        form_path=("workflow-lisp", "defworkflow", "carry-outcomes"),
    )

    assert isinstance(state_type, ListTypeRef)
    assert state_type.item_type_ref.name == "TaskOutcome"
    ensure_loop_projectable_type(
        state_type,
        code="loop_recur_state_type_invalid",
        span=span,
        form_path=("workflow-lisp", "defworkflow", "carry-outcomes"),
        type_env=type_env,
    )








def test_compile_stage3_imported_loop_recur_on_exhausted_helper_validates(tmp_path: Path) -> None:
    source_root = MODULE_FIXTURES / "valid" / "imported_loop_recur_on_exhausted"
    result = _compile_entrypoint(source_root / "entry.orc", source_root=source_root, tmp_path=tmp_path)

    assert result.entry_result.typed_workflows[0].definition.name == "entry::orchestrate"




    # Exhaustion projects the state after the second committed continue.























def test_loop_recur_list_constructor_seed_retains_native_list_type(
    tmp_path: Path,
) -> None:
    workflow_path = _write_module(
        tmp_path / "loop_recur_list_constructor_seed.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.40")',
                "  (defmodule loop_recur_list_constructor_seed)",
                "  (export orchestrate)",
                "  (defworkflow orchestrate () -> List[String]",
                '    (loop/recur :max 2 :state (list "first" "second")',
                "      (fn (state)",
                "        (if (list/empty? state)",
                "          (done state)",
                "          (continue (list/rest state)))))))",
            ]
        ),
    )

    result = _compile_entrypoint(
        workflow_path,
        source_root=tmp_path,
        tmp_path=tmp_path,
        validate_shared=True,
    )

    list_type_descriptor = {
        "kind": "list",
        "item": {"kind": "primitive", "name": "String"},
    }

    from orchestrator.workflow_lisp.type_env import ListTypeRef, PrimitiveTypeRef
    entry = result.entry_result.typed_program.workflows["loop_recur_list_constructor_seed::orchestrate"]
    assert entry.signature.return_type_ref == ListTypeRef("List[String]", PrimitiveTypeRef("String"))
    assert entry.typed_body.type_ref == entry.signature.return_type_ref


def test_invalid_loop_recur_fn_outside_loop_fixture_fails(tmp_path: Path) -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile(INVALID_FN_OUTSIDE_FIXTURE, tmp_path=tmp_path)

    _assert_diagnostic_code(excinfo, "loop_recur_fn_outside_loop")


def test_typecheck_loop_recur_rich_list_root_record_state_preserves_descriptors(
    tmp_path: Path,
) -> None:
    """Target-2.35 admits complete root record-list descriptors."""

    workflow_path = _write_module(
        tmp_path / "rich_list_root_state.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.40")',
                "  (defrecord Task",
                "    (task_id String))",
                "  (defworkflow carry-tasks ((tasks List[Task])) -> List[Task]",
                "    (loop/recur :max 1 :state tasks",
                "      (fn (state) (done state)))))",
            ]
        ),
    )

    result = _compile(workflow_path, tmp_path=tmp_path)

    [workflow] = result.typed_workflows
    assert workflow.definition.name == 'entry::carry-tasks'
    state_type = workflow.signature.params[0][1]
    assert isinstance(state_type, ListTypeRef)
    assert state_type.item_type_ref.name == "Task"
    assert workflow.signature.return_type_ref == state_type
    assert workflow.typed_body.type_ref == state_type
    assert tuple(field.name for field in state_type.item_type_ref.definition.fields) == ("task_id",)


# A `match` as a loop's `:max` or `:state`, and a `continue` value whose branch is an `if` holding an
# effect, through the public `run` (defect backlog plan, Task TD1).
from tests.workflow_lisp_cli_run_helpers import cli_run, command_log, run_workflow  # noqa: E402

MATCH_MAX = "(match u ((A a) a.n) ((B b) 1))"
A_3 = 'u={"variant":"A","n":3}'
B_X = 'u={"variant":"B","why":"x"}'
COUNT_TO_EXHAUSTION = ":on-exhausted s (if (> s 10) (done s) (continue (+ s 1)))"
M = '(command-result c :argv ("python" "c.py" "m" "1") :returns Int)'


@pytest.mark.parametrize(("run", "inputs", "wanted"), [
    (f"((u U)) -> Int (loop/recur ((s 0)) :max {MATCH_MAX} {COUNT_TO_EXHAUSTION})", (A_3,), (3, [])),
    (f"((u U)) -> Int (loop/recur ((s 0)) :max {MATCH_MAX} {COUNT_TO_EXHAUSTION})", (B_X,), (1, [])),
    (f"((u U)) -> Int (loop/recur :max {MATCH_MAX} :state 0 :on-exhausted s "
     "(fn (s) (if (> s 10) (done s) (continue (+ s 1)))))", (A_3,), (3, [])),
    (f"((u U)) -> Int (loop/recur ((s {MATCH_MAX})) :max 2 :on-exhausted 9 (done s))", (A_3,), (3, [])),
    (f"((u U)) -> List[Int] (list/map-effect ((x (list 1 2 3))) :max {MATCH_MAX} {M})", (A_3,), ([1, 1, 1], ["m"] * 3)),
    (f"((u U)) -> Int (let* ((ys (list/map-effect ((x (list 1 2))) :max {MATCH_MAX} {M}))) (list/length ys))",
     (A_3,), (2, ["m", "m"])),
], ids=["loop-max-A", "loop-max-B", "fn-form-max", "loop-state", "serial-map-value", "serial-map-bound"])
def test_match_as_a_loop_budget_or_seed_runs(tmp_path: Path, run: str, inputs: tuple[str, ...], wanted) -> None:
    assert run_workflow(tmp_path, run, *inputs) == wanted


@pytest.mark.parametrize("budget", ["(if (> n 0) 3 1)", "(cond ((> n 5) 1) (true 3))"], ids=["if", "cond"])
def test_conditional_as_a_loop_budget_runs(tmp_path: Path, budget: str) -> None:
    run = f"((n Int)) -> Int (loop/recur ((s 0)) :max {budget} {COUNT_TO_EXHAUSTION})"

    assert run_workflow(tmp_path, run, "n=1") == (3, [])


@pytest.mark.parametrize("value", [f"(if (> n 0) {MATCH_MAX} 4)", "(let* ((k 1)) (match u ((A a) (+ k a.n)) ((B b) 1)))",
                                   f"(cond ((> n 5) 1) ((> n 0) {MATCH_MAX}) (else 4))"],
                         ids=["if", "let", "cond"])
@pytest.mark.parametrize("position", ["max", "state"])
def test_pure_value_holding_a_match_as_a_loop_budget_or_seed_runs(tmp_path: Path, value: str, position: str) -> None:
    run = (f"((u U) (n Int)) -> Int (loop/recur ((s 0)) :max {value} {COUNT_TO_EXHAUSTION})" if position == "max"
           else f"((u U) (n Int)) -> Int (loop/recur ((s {value})) :max 2 :on-exhausted 9 (done s))")

    assert run_workflow(tmp_path, run, A_3, "n=1") == ((4 if value.startswith("(let*") else 3), [])


def test_match_as_a_serial_map_cap_bounds_the_map(tmp_path: Path) -> None:
    done = cli_run(tmp_path, f"((u U)) -> List[Int] (list/map-effect ((x (list 1 2 3))) :max {MATCH_MAX} {M})", B_X)

    assert (done.returncode, "[list_map_effect_cap_exceeded]" in done.stderr, command_log(tmp_path)) == (1, True, ["m"])


E = '(command-result c :argv ("python" "c.py" "e" "1") :returns Int)'
INNER_IF_VALUES = {
    "then": f"(if (> n 0) (if (> n 0) {E} 0) 0)",
    "else": f"(if (> n 0) 0 (if (> n 0) {E} 0))",
    "cond": f"(cond ((> n 5) 2) ((> n 0) {E}) (else 0))",
    "let": f"(if (> n 0) (if (> n 0) (let* ((y {E})) y) 0) 0)",
}


@pytest.mark.parametrize("form", ["binder", "fn"])
@pytest.mark.parametrize("value", INNER_IF_VALUES)
def test_continue_value_whose_branch_is_an_if_holding_an_effect_is_refused(tmp_path: Path, value: str, form: str) -> None:
    step = f"(if (> s 0) (done s) (continue {INNER_IF_VALUES[value]}))"
    loop = (f"(loop/recur ((s 0)) :max 2 :on-exhausted 0 {step})" if form == "binder"
            else f"(loop/recur :max 2 :state 0 :on-exhausted 0 (fn (s) {step}))")

    done = cli_run(tmp_path, f"((n Int)) -> Int {loop}", "n=1")

    assert (done.returncode, "[effect_not_permitted]" in done.stderr, command_log(tmp_path)) == (2, True, []), done.stderr


EFFECTFUL_CALLEES = (f"(defworkflow w ((n Int)) -> Int {E})", f"(defproc pe ((n Int)) -> Int {E})",
                     "(defproc pw ((n Int)) -> Int (call w :n n))")
CALLEE_VALUES = {
    "workflow": "(if (> n 0) (if (> n 0) (call w :n n) 0) 0)",
    "procedure": "(cond ((> n 5) 2) ((> n 0) (pe n)) (else 0))",
    "procedure-calling-a-workflow": "(if (> n 0) 0 (if (> n 0) (pw n) 0))",
}


@pytest.mark.parametrize("form", ["binder", "fn"])
@pytest.mark.parametrize("value", CALLEE_VALUES)
def test_continue_value_whose_branch_is_an_if_calling_an_effectful_callee_is_refused(
    tmp_path: Path, value: str, form: str
) -> None:
    step = f"(if (> s 0) (done s) (continue {CALLEE_VALUES[value]}))"
    loop = (f"(loop/recur ((s 0)) :max 2 :on-exhausted 0 {step})" if form == "binder"
            else f"(loop/recur :max 2 :state 0 :on-exhausted 0 (fn (s) {step}))")

    done = cli_run(tmp_path, f"((n Int)) -> Int {loop}", "n=1", definitions=EFFECTFUL_CALLEES)

    assert (done.returncode, "[effect_not_permitted]" in done.stderr, command_log(tmp_path)) == (2, True, []), done.stderr


LOCAL_VALUES = {"if": "(if (> n 0) (if (> n 0) (g n) 0) 0)", "cond": "(cond ((> n 5) 0) ((> n 0) (g n)) (else 0))"}


@pytest.mark.parametrize("value", LOCAL_VALUES)
def test_continue_value_whose_branch_calls_an_effectful_local_is_refused(tmp_path: Path, value: str) -> None:
    step = f"(let-proc ((g ((k Int)) -> Int {E})) (continue {LOCAL_VALUES[value]}))"

    done = cli_run(tmp_path, f"((n Int)) -> Int (loop/recur ((s 0)) :max 2 :on-exhausted 0 (if (> s 0) (done s) {step}))", "n=1")

    assert (done.returncode, "[effect_not_permitted]" in done.stderr, command_log(tmp_path)) == (2, True, []), done.stderr


def test_continue_value_whose_branch_calls_a_pure_local_runs(tmp_path: Path) -> None:
    step = f"(let-proc ((g ((k Int)) -> Int (+ k 1))) (continue {LOCAL_VALUES['if']}))"

    assert run_workflow(tmp_path, f"((n Int)) -> Int (loop/recur ((s 0)) :max 2 :on-exhausted 0 (if (> s 0) (done s) {step}))",
                        "n=1") == (2, [])


def test_continue_value_whose_branch_is_an_if_calling_a_pure_workflow_runs(tmp_path: Path) -> None:
    run = ("((n Int)) -> Int (loop/recur ((s 0)) :max 2 :on-exhausted 0 "
           "(if (> s 0) (done s) (continue (if (> n 0) (if (> n 0) (call wp :n n) 0) 0))))")

    assert run_workflow(tmp_path, run, "n=1", definitions=("(defworkflow wp ((n Int)) -> Int (+ n 0))",)) == (1, [])


@pytest.mark.parametrize("step", [f"(done {INNER_IF_VALUES['then']})",
                                  f"(let* ((next {INNER_IF_VALUES['then']})) (continue next))"], ids=["done", "bound"])
def test_the_same_value_as_done_or_bound_first_runs(tmp_path: Path, step: str) -> None:
    run = f"((n Int)) -> Int (loop/recur ((s 0)) :max 2 :on-exhausted 0 (if (> s 0) (done s) {step}))"

    assert run_workflow(tmp_path, run, "n=1") == (1, ["e"])


# A `done` or `continue` as the value of a `let*` binding in a loop body (frontend specification 13.1).
LOOP_EXIT_BINDINGS = {
    "done": "(let* ((x (done 1))) x)",
    "continue": "(let* ((x (continue (+ s 1))) (y E)) (done y))".replace("E", E),
    "nested-let": "(let* ((x (let* ((y 1)) (done y)))) x)",
    "if": "(let* ((x (if (> n 0) (done 1) (continue (+ s 1))))) (done 2))",
    "cond": "(let* ((x (cond ((> n 5) (done 1)) (else (continue (+ s 1)))))) (done 2))",
    "match": "(let* ((x (match (variant U A :n n) ((A a) (done a.n)) ((B b) (continue (+ s 1)))))) (done 2))",
}


@pytest.mark.parametrize("form", ["binder", "fn"])
@pytest.mark.parametrize("body", LOOP_EXIT_BINDINGS)
def test_loop_exit_as_a_let_binding_value_is_refused(tmp_path: Path, body: str, form: str) -> None:
    text = LOOP_EXIT_BINDINGS[body]
    loop = (f"(loop/recur ((s 0)) :max 2 :on-exhausted s {text})" if form == "binder"
            else f"(loop/recur :max 2 :state 0 :on-exhausted s (fn (s) {text}))")

    done = cli_run(tmp_path, f"((n Int)) -> Int {loop}", "n=1")

    assert (done.returncode, "[loop_recur_contract_invalid]" in done.stderr, command_log(tmp_path)) == (2, True, []), \
        done.stderr


@pytest.mark.parametrize(("body", "wanted"), [
    ("(let* ((x 1)) (done x))", ("value", 1)),
    ("(let* ((x (if (> n 0) (done 1) 5))) (done x))", ("refused", "type_mismatch")),
], ids=["tail-position", "exit-in-one-branch"])
def test_loop_exit_in_tail_position_runs_and_in_one_branch_of_a_binding_is_a_type_mismatch(
        tmp_path: Path, body: str, wanted: tuple) -> None:
    done = cli_run(tmp_path, f"((n Int)) -> Int (loop/recur ((s 0)) :max 2 :on-exhausted s {body})", "n=1")

    observed = (("value", json.loads(done.stdout.splitlines()[-1])) if done.returncode == 0
                else ("refused", "type_mismatch") if "[type_mismatch]" in done.stderr else ("exit", done.returncode))
    assert observed == wanted, done.stderr


# A `done` or `continue` where a value is expected: a `list` element, a `list/map` or `list/map-effect` body
# (frontend specification 13.1). Each crashed on `main` at c24fb97d (defect D22).
LOOP_EXIT_VALUES = {
    "list": "(list (done 1))",
    "list-both": "(done (list/length (list (continue (+ s 1)) (continue (+ s 1)))))",
    "typed-list": "(done (list/length (list :of Int (if (> n 0) (done 1) (continue (+ s 1))))))",
    "map-body": "(list/map ((x (list 1))) (done 1))",
    "map-body-let": "(done (list/length (list/map ((x (list 1))) (let* ((y x)) (continue (+ s y))))))",
    "map-effect-body": "(done (list/length (list/map-effect ((x (list 1))) :max 2 (cond ((> n 0) (done 1)) (else (continue 2))))))",
    "map-effect-parallel-body": ('(done (list/length (list/map-effect ((x (list "a"))) :max 2 :parallel 1 :workspace x '
                                 "(match (variant U A :n n) ((A a) (done a.n)) ((B b) (continue (+ s 1)))))))"),
    "map-body-in-a-source": "(done (list/length (list/map ((y (list/map ((x (list 1))) (done 1)))) y)))",
}


@pytest.mark.parametrize("form", ["binder", "fn"])
@pytest.mark.parametrize("body", LOOP_EXIT_VALUES)
def test_loop_exit_as_a_list_element_or_map_body_is_refused(tmp_path: Path, body: str, form: str) -> None:
    text = LOOP_EXIT_VALUES[body]
    loop = (f"(loop/recur ((s 0)) :max 2 :on-exhausted 0 {text})" if form == "binder"
            else f"(loop/recur :max 2 :state 0 :on-exhausted 0 (fn (s) {text}))")

    done = cli_run(tmp_path, f"((n Int)) -> Int {loop}", "n=1")

    assert (done.returncode, "[loop_recur_contract_invalid]" in done.stderr, command_log(tmp_path)) == (2, True, []), \
        done.stderr


# Exits in tail position, and values with lists and maps inside an exit: they build and run as on `main` (their
# digests are pinned by `tests/test_workflow_lisp_d22_differential.py`).
TAIL_EXITS = {
    "if": ("(if (> s 0) (done s) (continue (+ s 1)))", 1),
    "cond": ("(cond ((> s 0) (done s)) (else (continue (+ s 1))))", 1),
    "match": ("(match (variant U A :n n) ((A a) (if (> s 0) (done a.n) (continue (+ s 1)))) ((B b) (done 0)))", 1),
    "let": ("(let* ((y (+ s 1))) (if (> s 0) (done y) (continue y)))", 2),
    "if-let": ("(if (> s 0) (let* ((y s)) (done y)) (let* ((z (+ s 1))) (continue z)))", 1),
    "list-in-done": ("(done (list/length (list s 1)))", 2),
    "map-in-continue": ("(if (> s 0) (done s) (continue (list/length (list/map ((x (list 1 2))) (+ x s)))))", 2),
}


@pytest.mark.parametrize("body", TAIL_EXITS)
def test_loop_exit_in_tail_position_runs(tmp_path: Path, body: str) -> None:
    text, wanted = TAIL_EXITS[body]

    assert run_workflow(tmp_path, f"((n Int)) -> Int (loop/recur ((s 0)) :max 3 :on-exhausted 0 {text})", "n=1") \
        == (wanted, [])
