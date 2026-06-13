from __future__ import annotations

from pathlib import Path

import pytest

from orchestrator.state import StateManager
from orchestrator.workflow.executor import WorkflowExecutor
from orchestrator.workflow_lisp.compiler import compile_stage3_entrypoint, compile_stage3_module
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError


FIXTURES = Path(__file__).parent / "fixtures" / "workflow_lisp"
VALID_MINIMAL_FIXTURE = FIXTURES / "valid" / "loop_recur_minimal.orc"
VALID_UNION_FIXTURE = FIXTURES / "valid" / "loop_recur_union_result.orc"
VALID_ON_EXHAUSTED_RECORD_FIXTURE = FIXTURES / "valid" / "loop_recur_on_exhausted_record.orc"
VALID_ON_EXHAUSTED_UNION_FIXTURE = FIXTURES / "valid" / "loop_recur_on_exhausted_union.orc"
VALID_ON_EXHAUSTED_SCALAR_FRAME_CARRIAGE_FIXTURE = (
    FIXTURES / "valid" / "loop_recur_on_exhausted_scalar_frame_carriage.orc"
)
INVALID_MISSING_DONE_FIXTURE = FIXTURES / "invalid" / "loop_recur_missing_done.orc"
INVALID_CONTINUE_FIXTURE = FIXTURES / "invalid" / "loop_recur_continue_type_mismatch.orc"
INVALID_DONE_FIXTURE = FIXTURES / "invalid" / "loop_recur_done_type_mismatch.orc"
INVALID_FN_OUTSIDE_FIXTURE = FIXTURES / "invalid" / "loop_recur_fn_outside_loop.orc"
INVALID_ON_EXHAUSTED_IMPURE_FIXTURE = FIXTURES / "invalid" / "loop_recur_on_exhausted_impure.orc"
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


def test_typecheck_loop_recur_rejects_impure_on_exhausted(tmp_path: Path) -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile(INVALID_ON_EXHAUSTED_IMPURE_FIXTURE, tmp_path=tmp_path)

    _assert_diagnostic_code(excinfo, "loop_recur_contract_invalid")


def test_typecheck_loop_recur_rejects_on_exhausted_type_mismatch(tmp_path: Path) -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile(INVALID_ON_EXHAUSTED_TYPE_MISMATCH_FIXTURE, tmp_path=tmp_path)

    _assert_diagnostic_code(excinfo, "loop_recur_done_type_mismatch")


def test_typecheck_loop_recur_rejects_computed_scalar_on_exhausted_value(tmp_path: Path) -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile(INVALID_ON_EXHAUSTED_SCALAR_FRAME_COMPUTED_VALUE_FIXTURE, tmp_path=tmp_path)

    _assert_diagnostic_code(excinfo, "workflow_return_not_exportable")


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


def test_lowering_loop_recur_supports_union_result_fixture(tmp_path: Path) -> None:
    result = _compile(VALID_UNION_FIXTURE, tmp_path=tmp_path)

    assert {
        workflow.typed_workflow.definition.name for workflow in result.lowered_workflows
    } == {"loop-recur-union-result"}

    authored = result.lowered_workflows[0].authored_mapping
    repeat_step = next(step for step in authored["steps"] if "repeat_until" in step)

    assert repeat_step["repeat_until"]["condition"]["compare"]["right"] == "DONE"


def test_compile_stage3_imported_loop_recur_on_exhausted_helper_validates(tmp_path: Path) -> None:
    source_root = MODULE_FIXTURES / "valid" / "imported_loop_recur_on_exhausted"
    result = _compile_entrypoint(source_root / "entry.orc", source_root=source_root, tmp_path=tmp_path)

    assert result.entry_result.typed_workflows[0].definition.name == "entry::orchestrate"
    assert any(
        workflow.typed_workflow.definition.name == "helper::project-exhausted"
        for workflow in result.compiled_results_by_name["helper"].lowered_workflows
    )


def test_loop_recur_on_exhausted_fixture_validates_through_shared_repeat_until(
    tmp_path: Path,
) -> None:
    result = _compile(VALID_ON_EXHAUSTED_RECORD_FIXTURE, tmp_path=tmp_path, validate_shared=True)

    assert [workflow.typed_workflow.definition.name for workflow in result.lowered_workflows] == [
        "loop-recur-on-exhausted-record"
    ]


def test_loop_recur_on_exhausted_scalar_frame_carriage_executes_through_shared_repeat_until(
    tmp_path: Path,
) -> None:
    result = _compile(
        VALID_ON_EXHAUSTED_SCALAR_FRAME_CARRIAGE_FIXTURE,
        tmp_path=tmp_path,
        validate_shared=True,
    )

    assert result.lowering_schema_version == 2

    bundle = result.validated_bundles["loop-recur-on-exhausted-scalar-frame-carriage"]
    state_manager = StateManager(workspace=tmp_path, run_id="loop-recur-on-exhausted-scalar-frame-carriage")
    state_manager.initialize(VALID_ON_EXHAUSTED_SCALAR_FRAME_CARRIAGE_FIXTURE.as_posix())

    state = WorkflowExecutor(bundle, tmp_path, state_manager, retry_delay_ms=0).execute(on_error="stop")
    loop_step = state["steps"]["loop-recur-on-exhausted-scalar-frame-carriage__loop"]

    assert state["status"] == "completed"
    assert loop_step["artifacts"]["result__attempt_count"] == {
        "ref": "root.steps.loop-recur-on-exhausted-scalar-frame-carriage__loop.artifacts.state__attempt_count"
    }
    assert loop_step["artifacts"]["result__reason"] == {
        "ref": "root.steps.loop-recur-on-exhausted-scalar-frame-carriage__loop.artifacts.state__exhaustion_reason"
    }
    assert state["workflow_outputs"] == {
        "return__variant": "EXHAUSTED",
        "return__attempt_count": 1,
        "return__reason": "retrying",
    }


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


def test_lowering_loop_recur_supports_authored_loop_state_seed(tmp_path: Path) -> None:
    workflow_path = _write_module(
        tmp_path / "loop_recur_loop_state_seed.orc",
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
                "  (defworkflow loop-recur-loop-state-seed",
                "    ((report-path WorkReport))",
                "    -> LoopResult",
                "    (loop/recur",
                "      :max 1",
                "      :state (loop-state",
                "               (report WorkReport report-path)",
                "               (done Bool true))",
                "      (fn (current)",
                "        (if current.done",
                "          (done (record LoopResult :report current.report))",
                "          (continue current))))))",
            ]
        ),
    )

    result = _compile(workflow_path, tmp_path=tmp_path, validate_shared=True)
    authored = result.lowered_workflows[0].authored_mapping
    repeat_step = next(step for step in authored["steps"] if "repeat_until" in step)

    assert "state__report" in repeat_step["repeat_until"]["outputs"]


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


def test_lowering_loop_recur_with_composed_with_phase_binding_exports_step_backed_outputs(
    tmp_path: Path,
) -> None:
    workflow_path = _write_module(
        tmp_path / "loop_recur_with_phase_binding.orc",
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
                "  (defenum ImplementationStateTag",
                "    COMPLETED",
                "    BLOCKED)",
                "  (defpath DesignDocPath",
                "    :kind relpath",
                '    :under "docs/design"',
                "    :must-exist true)",
                "  (defpath PlanDocPath",
                "    :kind relpath",
                '    :under "docs/plans"',
                "    :must-exist true)",
                "  (defpath WorkReport",
                "    :kind relpath",
                '    :under "artifacts/work"',
                "    :must-exist true)",
                "  (defpath WorkReportTarget",
                "    :kind relpath",
                '    :under "artifacts/work"',
                "    :must-exist false)",
                "  (defpath ImplementationStateBundlePath",
                "    :kind relpath",
                '    :under "artifacts/work"',
                "    :must-exist false)",
                "  (defrecord ImplementationAttemptInputs",
                "    (design DesignDocPath)",
                "    (plan PlanDocPath))",
                "  (defrecord ImplementationAttemptPhaseCtx",
                "    (implementation_state_bundle_path ImplementationStateBundlePath)",
                "    (execution_report_target WorkReportTarget)",
                "    (progress_report_target WorkReportTarget))",
                "  (defunion ImplementationAttempt",
                "    (COMPLETED",
                "      (implementation_state ImplementationStateTag)",
                "      (execution_report_path WorkReport))",
                "    (BLOCKED",
                "      (implementation_state ImplementationStateTag)",
                "      (progress_report_path WorkReport)",
                "      (blocker_class BlockerClass)))",
                "  (defrecord AttemptLoopResult",
                "    (report_path WorkReport))",
                "  (defworkflow loop-recur-phase-binding",
                "    ((phase-ctx ImplementationAttemptPhaseCtx)",
                "     (inputs ImplementationAttemptInputs))",
                "    -> AttemptLoopResult",
                "    (let* ((attempt",
                "             (provider-result providers.execute",
                "               :prompt prompts.implementation.execute",
                "               :inputs (inputs.design inputs.plan)",
                "               :returns ImplementationAttempt)))",
                "      (loop/recur :max 2 :state attempt",
                "        (fn (state)",
                "          (let* ((phase-result",
                "                   (with-phase phase-ctx implementation",
                "                     (provider-result providers.execute",
                "                       :prompt prompts.implementation.execute",
                "                       :inputs (inputs.design",
                "                                inputs.plan",
                "                                (phase-target execution-report)",
                "                                (phase-target progress-report))",
                "                       :returns ImplementationAttempt))))",
                "            (match phase-result",
                "              ((COMPLETED completed)",
                "               (done",
                "                 (record AttemptLoopResult",
                "                   :report_path completed.execution_report_path)))",
                "              ((BLOCKED blocked)",
                "               (continue state)))))))))",
            ]
        ),
    )

    result = _compile(workflow_path, tmp_path=tmp_path)

    lowered = result.lowered_workflows[0].authored_mapping
    repeat_step = next(step for step in lowered["steps"] if "repeat_until" in step)
    nested_names = [step["name"] for step in repeat_step["repeat_until"]["steps"]]

    assert any(
        name == "loop-recur-phase-binding__body__phase-result"
        or name.startswith("loop-recur-phase-binding__body____wcc_effect_result_")
        for name in nested_names
    )
    assert "loop-recur-phase-binding__body" in nested_names


def test_loop_recur_review_phase_binding_exports_step_backed_outputs(tmp_path: Path) -> None:
    test_lowering_loop_recur_with_composed_with_phase_binding_exports_step_backed_outputs(tmp_path)


def test_loop_recur_supports_match_binding_followed_by_effectful_binding(tmp_path: Path) -> None:
    workflow_path = _write_module(
        tmp_path / "loop_recur_match_binding.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defenum BlockerClass",
                "    missing_resource",
                "    unavailable_hardware)",
                "  (defpath WorkReport",
                "    :kind relpath",
                '    :under "artifacts/work"',
                "    :must-exist true)",
                "  (defrecord AttemptReport",
                "    (report WorkReport))",
                "  (defrecord FinalReport",
                "    (report WorkReport))",
                "  (defunion ImplementationState",
                "    (COMPLETED",
                "      (execution_report WorkReport))",
                "    (BLOCKED",
                "      (progress_report WorkReport)",
                "      (blocker_class BlockerClass)))",
                "  (defworkflow loop-recur-match-binding",
                "    ((report_path WorkReport))",
                "    -> FinalReport",
                "    (let* ((attempt",
                "             (provider-result providers.execute",
                "               :prompt prompts.implementation.execute",
                "               :inputs (report_path)",
                "               :returns ImplementationState)))",
                "      (loop/recur :max 2 :state attempt",
                "        (fn (state)",
                "          (let* ((alias state)",
                "                 (attempt-report",
                "                  (match alias",
                "                    ((COMPLETED completed)",
                "                     (provider-result providers.execute",
                "                       :prompt prompts.implementation.execute",
                "                       :inputs (completed.execution_report)",
                "                       :returns AttemptReport))",
                "                    ((BLOCKED blocked)",
                "                     (provider-result providers.execute",
                "                       :prompt prompts.implementation.execute",
                "                       :inputs (blocked.progress_report)",
                "                       :returns AttemptReport))))",
                "                 (final-report",
                "                  (provider-result providers.execute",
                "                    :prompt prompts.implementation.execute",
                "                    :inputs (attempt-report.report)",
                "                    :returns FinalReport)))",
                "            (done final-report)))))))",
            ]
        ),
    )

    result = _compile(workflow_path, tmp_path=tmp_path)

    lowered = result.lowered_workflows[0].authored_mapping
    repeat_step = next(step for step in lowered["steps"] if "repeat_until" in step)
    nested_steps = repeat_step["repeat_until"]["steps"]

    match_step = next(step for step in nested_steps if "match" in step)
    final_provider_step = next(
        step for step in nested_steps if step.get("provider") == "test-provider" and step["name"].endswith("__final-report")
    )

    assert match_step["match"]["cases"]["COMPLETED"]["steps"][0]["provider"] == "test-provider"
    assert match_step["match"]["cases"]["BLOCKED"]["steps"][0]["provider"] == "test-provider"
    assert final_provider_step["output_bundle"]["fields"][0]["name"] == "report"


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


def test_loop_recur_exhaustion_preserves_authored_max_iterations(tmp_path: Path) -> None:
    result = _compile(VALID_UNION_FIXTURE, tmp_path=tmp_path)

    lowered = result.lowered_workflows[0].authored_mapping
    repeat_step = next(step for step in lowered["steps"] if "repeat_until" in step)

    assert repeat_step["repeat_until"]["max_iterations"] == 2


def test_loop_recur_union_result_lowers_seed_state_router_for_first_iteration(tmp_path: Path) -> None:
    workflow_path = _write_module(
        tmp_path / "loop_recur_seed_state_runtime.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defenum BlockerClass",
                "    missing_resource",
                "    unavailable_hardware)",
                "  (defpath WorkReport",
                "    :kind relpath",
                '    :under "artifacts/work"',
                "    :must-exist true)",
                "  (defrecord ChecksResult",
                "    (status String)",
                "    (report WorkReport))",
                "  (defunion ImplementationState",
                "    (COMPLETED",
                "      (execution_report WorkReport))",
                "    (BLOCKED",
                "      (progress_report WorkReport)",
                "      (blocker_class BlockerClass)))",
                "  (defrecord LoopResult",
                "    (report WorkReport))",
                "  (defworkflow loop-recur-seed-state-runtime",
                "    ((input ChecksResult)",
                "     (report_path WorkReport))",
                "    -> LoopResult",
                "    (let* ((attempt",
                "             (provider-result providers.execute",
                "               :prompt prompts.implementation.execute",
                "               :inputs (input report_path)",
                "               :returns ImplementationState)))",
                "      (loop/recur",
                "        :max 2",
                "        :state attempt",
                "        (fn (state)",
                "          (match state",
                "            ((COMPLETED completed)",
                "             (done",
                "               (record LoopResult",
                "                 :report completed.execution_report)))",
                "            ((BLOCKED blocked)",
                "             (continue state))))))))",
            ]
        ),
    )

    result = _compile(workflow_path, tmp_path=tmp_path, validate_shared=True)
    authored = result.lowered_workflows[0].authored_mapping
    repeat_step = next(step for step in authored["steps"] if "repeat_until" in step)
    seed_marker = next(
        step
        for step in repeat_step["repeat_until"]["steps"]
        if step.get("name") == "loop-recur-seed-state-runtime__body__state__seed_marker"
    )
    body_state = next(
        step
        for step in repeat_step["repeat_until"]["steps"]
        if step.get("name") == "loop-recur-seed-state-runtime__body__state"
    )

    assert seed_marker["when"]["equals"] == {
        "left": "${loop.index}",
        "right": "0",
    }
    assert body_state["if"]["compare"] == {
        "left": {"ref": "self.steps.loop-recur-seed-state-runtime__body__state__seed_marker.outcome.class"},
        "op": "eq",
        "right": "skipped",
    }
    assert body_state["then"]["steps"][0]["materialize_artifacts"]["values"][0]["source"] == {
        "ref": "root.steps.loop-recur-seed-state-runtime__loop.artifacts.state__variant"
    }
    assert body_state["else"]["steps"][0]["materialize_artifacts"]["values"][0]["source"] == {
        "ref": "root.steps.loop-recur-seed-state-runtime__seed.artifacts.state__variant"
    }


def test_loop_recur_exhaustion_projection_relaxes_variant_relpath_at_result_boundary(
    tmp_path: Path,
) -> None:
    workflow_path = _write_module(
        tmp_path / "loop_recur_exhaustion_missing_projection.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defenum BlockerClass",
                "    missing_resource",
                "    unavailable_hardware)",
                "  (defpath WorkReport",
                "    :kind relpath",
                '    :under "artifacts/work"',
                "    :must-exist true)",
                "  (defrecord ChecksResult",
                '    (status String)',
                "    (report WorkReport))",
                "  (defunion LoopResult",
                "    (COMPLETED",
                "      (execution_report WorkReport))",
                "    (BLOCKED",
                "      (progress_report WorkReport)",
                "      (blocker_class BlockerClass))",
                "    (EXHAUSTED",
                "      (last_report WorkReport)",
                "      (reason String)))",
                "  (defworkflow loop-recur-exhaustion-missing-projection",
                "    ((input ChecksResult)",
                "     (report_path WorkReport))",
                "    -> LoopResult",
                "    (let* ((attempt",
                "             (provider-result providers.execute",
                "               :prompt prompts.implementation.execute",
                "               :inputs (input report_path)",
                "               :returns LoopResult)))",
                "      (loop/recur",
                "        :max 2",
                "        :state attempt",
                "        (fn (state)",
                "          (match state",
                "            ((COMPLETED completed)",
                "             (done state))",
                "            ((BLOCKED blocked)",
                "             (continue state))",
                "            ((EXHAUSTED exhausted)",
                "             (done state))))))))",
            ]
        ),
    )

    result = _compile(workflow_path, tmp_path=tmp_path, validate_shared=True)
    authored = result.lowered_workflows[0].authored_mapping
    repeat_step = next(step for step in authored["steps"] if "repeat_until" in step)
    repeat_step["repeat_until"]["max_iterations"] = 1
    repeat_step["repeat_until"]["on_exhausted"] = {
        "outputs": {
            "result__variant": "EXHAUSTED",
            "result__reason": "max_iterations_reached",
        }
    }
    result_step = next(step for step in authored["steps"] if step.get("name") == "loop-recur-exhaustion-missing-projection__result")
    exhausted_case = result_step["match"]["cases"]["EXHAUSTED"]

    assert repeat_step["repeat_until"]["on_exhausted"]["outputs"] == {
        "result__variant": "EXHAUSTED",
        "result__reason": "max_iterations_reached",
    }
    assert "result__last_report" not in repeat_step["repeat_until"]["on_exhausted"]["outputs"]
    assert exhausted_case["outputs"]["return__last_report"]["must_exist_target"] is False
    assert exhausted_case["outputs"]["return__last_report"]["from"] == {
        "ref": "root.steps.loop-recur-exhaustion-missing-projection__loop.artifacts.result__last_report"
    }
    assert authored["outputs"]["return__last_report"]["must_exist_target"] is False
