from __future__ import annotations

from pathlib import Path

import pytest

from orchestrator.workflow_lisp.compiler import compile_stage3_module
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError


FIXTURES = Path(__file__).parent / "fixtures" / "workflow_lisp"
VALID_MINIMAL_FIXTURE = FIXTURES / "valid" / "loop_recur_minimal.orc"
VALID_UNION_FIXTURE = FIXTURES / "valid" / "loop_recur_union_result.orc"
INVALID_MISSING_DONE_FIXTURE = FIXTURES / "invalid" / "loop_recur_missing_done.orc"
INVALID_CONTINUE_FIXTURE = FIXTURES / "invalid" / "loop_recur_continue_type_mismatch.orc"
INVALID_DONE_FIXTURE = FIXTURES / "invalid" / "loop_recur_done_type_mismatch.orc"
INVALID_FN_OUTSIDE_FIXTURE = FIXTURES / "invalid" / "loop_recur_fn_outside_loop.orc"
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


def test_typecheck_loop_recur_resets_variant_proof_each_iteration(tmp_path: Path) -> None:
    workflow_path = _write_module(
        tmp_path / "loop_recur_proof_reset.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
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
                '  (:target-dsl "2.14")',
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
                '  (:target-dsl "2.14")',
                "  (defrecord WorkflowInput",
                "    (value String))",
                "  (defrecord WorkflowOutput",
                "    (value String))",
                "  (defrecord LoopResult",
                "    (status String))",
                "  (defproc helper",
                "    ((input WorkflowInput))",
                "    -> WorkflowOutput",
                "    :effects ()",
                "    :lowering inline",
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
                '  (:target-dsl "2.14")',
                "  (defrecord LoopResult",
                "    (status String))",
                "  (defrecord WorkflowInput",
                "    (value String))",
                "  (defrecord WorkflowOutput",
                "    (value String))",
                "  (defproc helper",
                "    ((input WorkflowInput))",
                "    -> WorkflowOutput",
                "    :effects ()",
                "    :lowering inline",
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


def test_lowering_loop_recur_supports_union_return_fixture(tmp_path: Path) -> None:
    result = _compile(VALID_UNION_FIXTURE, tmp_path=tmp_path)

    assert {
        workflow.typed_workflow.definition.name for workflow in result.lowered_workflows
    } == {"loop-recur-union-result"}


def test_lowering_loop_recur_supports_literal_initial_state(tmp_path: Path) -> None:
    workflow_path = _write_module(
        tmp_path / "loop_recur_literal_state.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defrecord LoopResult",
                "    (status String))",
                "  (defworkflow loop-recur-literal-state",
                "    ()",
                "    -> LoopResult",
                '    (loop/recur :max 1 :state "seed"',
                "      (fn (state)",
                "        (done (record LoopResult :status state))))))",
            ]
        ),
    )

    result = _compile(workflow_path, tmp_path=tmp_path)

    assert [workflow.typed_workflow.definition.name for workflow in result.lowered_workflows] == [
        "loop-recur-literal-state"
    ]


def test_lowering_loop_recur_supports_relpath_result_projection(tmp_path: Path) -> None:
    workflow_path = _write_module(
        tmp_path / "loop_recur_relpath_result.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defpath WorkReport",
                "    :kind relpath",
                '    :under "artifacts/work"',
                "    :must-exist true)",
                "  (defrecord LoopResult",
                "    (report WorkReport))",
                "  (defworkflow loop-recur-relpath-result",
                "    ((report_path WorkReport))",
                "    -> LoopResult",
                "    (let* ((looped",
                "             (loop/recur :max 1 :state report_path",
                "               (fn (state)",
                "                 (done state)))))",
                "      (record LoopResult :report looped))))",
            ]
        ),
    )

    result = _compile(workflow_path, tmp_path=tmp_path)

    assert [workflow.typed_workflow.definition.name for workflow in result.lowered_workflows] == [
        "loop-recur-relpath-result"
    ]


def test_lowering_loop_recur_allows_letstar_inside_body(tmp_path: Path) -> None:
    workflow_path = _write_module(
        tmp_path / "loop_recur_letstar_body.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defrecord LoopResult",
                "    (status String))",
                "  (defworkflow loop-recur-letstar-body",
                "    ((seed String))",
                "    -> LoopResult",
                "    (loop/recur :max 1 :state seed",
                "      (fn (state)",
                "        (let* ((alias state))",
                "          (done (record LoopResult :status alias)))))))",
            ]
        ),
    )

    result = _compile(workflow_path, tmp_path=tmp_path)

    assert [workflow.typed_workflow.definition.name for workflow in result.lowered_workflows] == [
        "loop-recur-letstar-body"
    ]


def test_invalid_loop_recur_fn_outside_loop_fixture_fails(tmp_path: Path) -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile(INVALID_FN_OUTSIDE_FIXTURE, tmp_path=tmp_path)

    _assert_diagnostic_code(excinfo, "loop_recur_fn_outside_loop")


def test_loop_recur_supports_if_routing_between_continue_and_done(tmp_path: Path) -> None:
    result = _compile(VALID_IF_LOOP_FIXTURE, tmp_path=tmp_path)

    lowered = result.lowered_workflows[0].authored_mapping
    repeat_step = next(step for step in lowered["steps"] if "repeat_until" in step)
    body_if = next(
        step
        for step in repeat_step["repeat_until"]["steps"]
        if "if" in step and step["name"].endswith("__body")
    )

    assert "if" in body_if
    assert "then" in body_if
    assert "else" in body_if
    assert [step["name"] for step in body_if["then"]["steps"]] == [
        "loop-report__body__then__summary",
        "loop-report__body__then",
    ]
    assert body_if["then"]["steps"][0]["provider"] == "test-provider"
    assert body_if["then"]["outputs"]["status"]["from"]["ref"].endswith(".artifacts.status")
    assert body_if["then"]["outputs"]["result__report"]["from"]["ref"].endswith(
        ".artifacts.result__report"
    )
    assert body_if["else"]["outputs"]["status"]["from"]["ref"].endswith(".artifacts.status")
