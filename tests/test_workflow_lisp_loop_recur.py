from __future__ import annotations

from pathlib import Path

import pytest

from orchestrator.state import StateManager
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




def test_typecheck_loop_recur_rich_list_root_union_uses_defining_type_env(tmp_path: Path) -> None:
    """The target-2.29 loop check receives the defining union environment."""

    definitions_path = _write_module(
        tmp_path / "rich_list_root_union_types.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.29")',
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


def test_typecheck_loop_recur_rich_list_target_228_reports_descriptor_blocker(
    tmp_path: Path,
) -> None:
    """Target 2.28 retains the pre-rich-loop descriptor refusal."""

    workflow_path = _write_module(
        tmp_path / "rich_list_target_228_blocker.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.28")',
                "  (defrecord Task",
                "    (task_id String))",
                "  (defworkflow carry-tasks ((tasks List[Task])) -> List[Task]",
                "    (loop/recur :max 1 :state tasks",
                "      (fn (state) (done state)))))",
            ]
        ),
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile(workflow_path, tmp_path=tmp_path)

    _assert_diagnostic_code(excinfo, "list_collection_contract_unsupported")






def test_compile_stage3_imported_loop_recur_on_exhausted_helper_validates(tmp_path: Path) -> None:
    source_root = MODULE_FIXTURES / "valid" / "imported_loop_recur_on_exhausted"
    result = _compile_entrypoint(source_root / "entry.orc", source_root=source_root, tmp_path=tmp_path)

    assert result.entry_result.typed_workflows[0].definition.name == "entry::orchestrate"




def test_loop_recur_on_exhausted_scalar_frame_carriage_executes_through_shared_repeat_until(
    tmp_path: Path,
) -> None:
    result = _compile(
        VALID_ON_EXHAUSTED_SCALAR_FRAME_CARRIAGE_FIXTURE,
        tmp_path=tmp_path,
        validate_shared=True,
    )

    assert result.lowering_schema_version == 2

    state_manager = StateManager(workspace=tmp_path, run_id="loop-recur-on-exhausted-scalar-frame-carriage")


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
                '  (:target-dsl "2.18")',
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
    """Target-2.29 admits complete root record-list descriptors."""

    workflow_path = _write_module(
        tmp_path / "rich_list_root_state.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.29")',
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
    assert workflow.definition.name == "carry-tasks"
    state_type = workflow.signature.params[0][1]
    assert isinstance(state_type, ListTypeRef)
    assert state_type.item_type_ref.name == "Task"
    assert workflow.signature.return_type_ref == state_type
    assert workflow.typed_body.type_ref == state_type
    assert tuple(field.name for field in state_type.item_type_ref.definition.fields) == ("task_id",)
