from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest

from orchestrator.state import StateManager
from orchestrator.workflow.core_ast import CoreRepeatUntil, workflow_core_ast_to_json
from orchestrator.workflow.executable_ir import (
    RepeatUntilFrameNode,
    workflow_executable_ir_to_json,
)
from orchestrator.workflow.executor import WorkflowExecutor
from orchestrator.workflow.runtime_step import RuntimeStep
from orchestrator.workflow_lisp import build_artifacts
from orchestrator.workflow_lisp.compiler import compile_stage3_entrypoint, compile_stage3_module
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from orchestrator.workflow_lisp.lowering import control_loops
from orchestrator.workflow_lisp.lowering import core as lowering_core
from orchestrator.workflow_lisp.wcc import defunctionalize
from orchestrator.workflow.validation import (
    WorkflowBoundaryValidationPolicy,
    WorkflowMappingBuildRequest,
    WorkflowMappingValidationOptions,
    _WorkflowMappingValidator,
)


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


def _compile_with_internal_exhaustion_code(
    path: Path,
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    diagnostic_code: str = "bounded_traversal_cap_exceeded",
    validate_shared: bool = False,
):
    original_emit = control_loops._emit_repeat_until_from_emitter_input

    def emit_with_diagnostic(emitter_input, **kwargs):
        return original_emit(
            replace(
                emitter_input,
                exhaustion_diagnostic_code=diagnostic_code,
            ),
            **kwargs,
        )

    monkeypatch.setattr(
        defunctionalize,
        "_emit_repeat_until_from_emitter_input",
        emit_with_diagnostic,
    )
    return _compile(path, tmp_path=tmp_path, validate_shared=validate_shared)


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


def test_loop_recur_on_exhausted_opaque_list_record_field_compiles(
    tmp_path: Path,
) -> None:
    workflow_path = _write_module(
        tmp_path / "loop_recur_on_exhausted_opaque_field.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.26")',
                "  (defrecord Payload",
                "    (flag Bool))",
                "  (defworkflow loop-recur-on-exhausted-opaque-field",
                "    ()",
                "    -> List[Bool]",
                '    (loop/recur :max 1 :state "seed"',
                "      :on-exhausted (let* ((payload (record Payload :flag true)))",
                "                     (list payload.flag))",
                "      (fn (state)",
                "        (continue state))))))",
            ]
        ),
    )

    result = _compile(workflow_path, tmp_path=tmp_path)

    assert [
        workflow.typed_workflow.definition.name
        for workflow in result.lowered_workflows
    ] == ["loop-recur-on-exhausted-opaque-field"]


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


def test_pre_218_scalar_loop_authored_mapping_remains_byte_identical(
    tmp_path: Path,
) -> None:
    workflow_path = _write_module(
        tmp_path / "scalar_loop.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.15")',
                "  (defmodule scalar_loop)",
                "  (export orchestrate)",
                "  (defworkflow orchestrate () -> Int",
                "    (loop/recur :max 2 :state 0",
                "      (fn (state)",
                "        (if (< state 1)",
                "          (continue (+ state 1))",
                "          (done state))))))",
            ]
        )
        + "\n",
    )

    result = _compile_entrypoint(
        workflow_path,
        source_root=tmp_path,
        tmp_path=tmp_path,
        validate_shared=True,
    )
    authored = result.entry_result.lowered_workflows[0].authored_mapping
    canonical_bytes = json.dumps(
        authored,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")

    assert len(canonical_bytes) == 6649
    assert hashlib.sha256(canonical_bytes).hexdigest() == (
        "57905acdc66527abdd6e021ebc97c27cfac20675bd335ae6de4ce1d16b75c479"
    )


def test_ordinary_repeat_core_executable_and_runtime_plan_bytes_remain_frozen(
    tmp_path: Path,
) -> None:
    result = _compile(
        Path(
            "tests/fixtures/workflow_lisp/valid/loop_recur_minimal.orc"
        ),
        tmp_path=tmp_path,
        validate_shared=True,
    )
    bundle = result.validated_bundles["loop-recur-minimal"]
    payloads = {
        "core": workflow_core_ast_to_json(bundle.core_workflow_ast),
        "executable": workflow_executable_ir_to_json(bundle.ir),
        "runtime_plan": build_artifacts._public_runtime_plan_payload(
            bundle.runtime_plan
        ),
    }
    expected = {
        "core": (
            48044,
            "3850f236d54e352adc154930f57d23e62784d6875ce0c1842af632a0b9226a60",
        ),
        "executable": (
            66099,
            "9ca9c4cc3bfc2360e9bbace8597684273d6a22be20f8d81af88863c3e70f4325",
        ),
        "runtime_plan": (
            50784,
            "f5e9bbb6042fb78af825f7595b08eb775d24a8dd586eed1e54bae964ceac2379",
        ),
    }

    for artifact_name, payload in payloads.items():
        canonical_bytes = json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        assert b"exhaustion_diagnostic_code" not in canonical_bytes
        assert (len(canonical_bytes), hashlib.sha256(canonical_bytes).hexdigest()) == (
            expected[artifact_name]
        )


def test_internal_repeat_emitter_carries_exhaustion_diagnostic_code_through_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    diagnostic_code = "bounded_traversal_cap_exceeded"
    result = _compile_with_internal_exhaustion_code(
        VALID_MINIMAL_FIXTURE,
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        diagnostic_code=diagnostic_code,
        validate_shared=True,
    )
    lowered = result.lowered_workflows[0]
    repeat_mapping = next(
        step["repeat_until"]
        for step in lowered.authored_mapping["steps"]
        if "repeat_until" in step
    )
    bundle = result.validated_bundles["loop-recur-minimal"]
    surface_repeat = next(
        step.repeat_until
        for step in bundle.surface.steps
        if step.repeat_until is not None
    )
    core_repeat = next(
        statement
        for statement in bundle.core_workflow_ast.body
        if isinstance(statement, CoreRepeatUntil)
    )
    executable_repeat = next(
        node
        for node in bundle.ir.nodes.values()
        if isinstance(node, RepeatUntilFrameNode)
    )
    runtime_repeat = RuntimeStep(
        executable_repeat,
        executable_repeat.presentation_name,
        executable_repeat.step_id,
    )
    runtime_plan_repeat = bundle.runtime_plan.nodes[executable_repeat.node_id]

    assert repeat_mapping["exhaustion_diagnostic_code"] == diagnostic_code
    assert surface_repeat.exhaustion_diagnostic_code == diagnostic_code
    assert core_repeat.exhaustion_diagnostic_code == diagnostic_code
    assert executable_repeat.execution_config.exhaustion_diagnostic_code == diagnostic_code
    assert executable_repeat.exhaustion_diagnostic_code == diagnostic_code
    assert runtime_repeat["repeat_until"]["exhaustion_diagnostic_code"] == diagnostic_code
    assert runtime_plan_repeat.exhaustion_diagnostic_code == diagnostic_code

    executable_payload = workflow_executable_ir_to_json(bundle.ir)
    runtime_plan_payload = build_artifacts._public_runtime_plan_payload(
        bundle.runtime_plan
    )
    core_payload = workflow_core_ast_to_json(bundle.core_workflow_ast)
    assert diagnostic_code in json.dumps(core_payload, sort_keys=True)
    assert diagnostic_code in json.dumps(executable_payload, sort_keys=True)
    assert diagnostic_code in json.dumps(runtime_plan_payload, sort_keys=True)

    coded_executable_bytes = json.dumps(
        executable_payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    coded_runtime_plan_bytes = json.dumps(
        runtime_plan_payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    monkeypatch.undo()
    ordinary_result = _compile(
        VALID_MINIMAL_FIXTURE,
        tmp_path=tmp_path,
        validate_shared=True,
    )
    ordinary_bundle = ordinary_result.validated_bundles["loop-recur-minimal"]
    ordinary_executable_bytes = json.dumps(
        workflow_executable_ir_to_json(ordinary_bundle.ir),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    ordinary_runtime_plan_bytes = json.dumps(
        build_artifacts._public_runtime_plan_payload(
            ordinary_bundle.runtime_plan
        ),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")

    assert hashlib.sha256(coded_executable_bytes).digest() != hashlib.sha256(
        ordinary_executable_bytes
    ).digest()
    assert hashlib.sha256(coded_runtime_plan_bytes).digest() != hashlib.sha256(
        ordinary_runtime_plan_bytes
    ).digest()


def test_shared_validation_rejects_undeclared_or_invalid_repeat_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = _compile_with_internal_exhaustion_code(
        VALID_MINIMAL_FIXTURE,
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )
    lowered = result.lowered_workflows[0]
    undeclared = replace(
        lowered,
        compiler_owned_repeat_until_metadata={},
    )

    with pytest.raises(LispFrontendCompileError) as undeclared_exc:
        lowering_core._validate_one_lowered_workflow(
            undeclared,
            workspace_root=tmp_path,
            imported_bundles={},
            workflow_is_imported=False,
            boundary_validation_policy=(
                WorkflowBoundaryValidationPolicy.PUBLIC_CALLABLE
            ),
        )

    assert "undeclared" in undeclared_exc.value.diagnostics[0].message

    invalid_mapping = json.loads(json.dumps(lowered.authored_mapping))
    invalid_repeat = next(
        step["repeat_until"]
        for step in invalid_mapping["steps"]
        if "repeat_until" in step
    )
    invalid_repeat["exhaustion_diagnostic_code"] = "Not A Diagnostic Code"
    invalid = replace(
        lowered,
        authored_mapping=invalid_mapping,
        compiler_owned_repeat_until_metadata=(
            lowering_core._capture_compiler_owned_repeat_until_metadata(
                invalid_mapping
            )
        ),
    )

    with pytest.raises(LispFrontendCompileError) as invalid_exc:
        lowering_core._validate_one_lowered_workflow(
            invalid,
            workspace_root=tmp_path,
            imported_bundles={},
            workflow_is_imported=False,
            boundary_validation_policy=(
                WorkflowBoundaryValidationPolicy.PUBLIC_CALLABLE
            ),
        )

    assert "lowercase ASCII diagnostic identifier" in (
        invalid_exc.value.diagnostics[0].message
    )


def test_compiler_owned_repeat_metadata_declaration_walks_nested_structured_steps() -> None:
    assert lowering_core._capture_compiler_owned_repeat_until_metadata(
        {
            "steps": [
                {
                    "name": "Branch",
                    "id": "branch",
                    "if": {"compare": {}},
                    "then": {
                        "steps": [
                            {
                                "name": "NestedLoop",
                                "id": "nested_loop",
                                "repeat_until": {
                                    "exhaustion_diagnostic_code": (
                                        "bounded_traversal_cap_exceeded"
                                    )
                                },
                            }
                        ]
                    },
                }
            ]
        }
    ) == {
        "nested_loop": {
            "exhaustion_diagnostic_code": "bounded_traversal_cap_exceeded"
        }
    }


def test_shared_validator_matches_nested_repeat_metadata_to_exact_declaration(
    tmp_path: Path,
) -> None:
    metadata = {
        "exhaustion_diagnostic_code": "bounded_traversal_cap_exceeded"
    }
    mapping = {
        "version": "2.18",
        "name": "nested-metadata-probe",
        "steps": [
            {
                "name": "Branch",
                "id": "branch",
                "if": {"compare": {}},
                "then": {
                    "steps": [
                        {
                            "name": "NestedLoop",
                            "id": "nested_loop",
                            "repeat_until": dict(metadata),
                        }
                    ]
                },
            }
        ],
    }
    request = WorkflowMappingBuildRequest(
        authored_mapping=mapping,
        workflow_path=tmp_path / "nested-metadata-probe.orc",
        frontend_kind="workflow_lisp",
        compiler_owned_repeat_until_metadata={"nested_loop": metadata},
    )
    validator = _WorkflowMappingValidator(
        request,
        WorkflowMappingValidationOptions(
            workspace_root=tmp_path,
            boundary_validation_policy=(
                WorkflowBoundaryValidationPolicy.PUBLIC_CALLABLE
            ),
        ),
    )

    validator._validate_compiler_owned_repeat_until_metadata(mapping)

    assert validator.errors == []


def test_repeat_exhaustion_code_is_emitted_only_on_failed_exhaustion(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def compile_scalar_loop(
        workflow_name: str,
        *,
        max_iterations: int,
        continue_below: int,
    ):
        workflow_path = _write_module(
            tmp_path / f"{workflow_name}.orc",
            "\n".join(
                [
                    "(workflow-lisp",
                    '  (:language "0.1")',
                    '  (:target-dsl "2.18")',
                    f"  (defworkflow {workflow_name} () -> Int",
                    (
                        "    (loop/recur "
                        f":max {max_iterations} :state 0"
                    ),
                    "      (fn (state)",
                    f"        (if (< state {continue_below})",
                    "          (continue (+ state 1))",
                    "          (done state))))))",
                ]
            )
            + "\n",
        )
        return _compile_with_internal_exhaustion_code(
            workflow_path,
            tmp_path=tmp_path,
            monkeypatch=monkeypatch,
            validate_shared=True,
        )

    failed_result = compile_scalar_loop(
        "diagnostic-loop-failed",
        max_iterations=1,
        continue_below=2,
    )
    failed_bundle = failed_result.validated_bundles["diagnostic-loop-failed"]
    failed_state_manager = StateManager(
        workspace=tmp_path,
        run_id="diagnostic-loop-failed",
    )
    failed_state_manager.initialize(
        (tmp_path / "diagnostic-loop-failed.orc").as_posix()
    )

    failed_state = WorkflowExecutor(
        failed_bundle,
        tmp_path,
        failed_state_manager,
        retry_delay_ms=0,
    ).execute(on_error="stop")

    failed_loop = failed_state["steps"]["diagnostic-loop-failed__loop"]
    assert failed_loop["error"]["type"] == "repeat_until_iterations_exhausted"
    assert failed_loop["error"]["code"] == "bounded_traversal_cap_exceeded"

    completed_result = compile_scalar_loop(
        "diagnostic-loop-completed",
        max_iterations=2,
        continue_below=1,
    )
    completed_bundle = completed_result.validated_bundles[
        "diagnostic-loop-completed"
    ]
    completed_state_manager = StateManager(
        workspace=tmp_path,
        run_id="diagnostic-loop-completed",
    )
    completed_state_manager.initialize(
        (tmp_path / "diagnostic-loop-completed.orc").as_posix()
    )

    completed_state = WorkflowExecutor(
        completed_bundle,
        tmp_path,
        completed_state_manager,
        retry_delay_ms=0,
    ).execute(on_error="stop")

    completed_loop = completed_state["steps"]["diagnostic-loop-completed__loop"]
    assert completed_loop["status"] == "completed"
    assert "error" not in completed_loop

    on_exhausted_result = _compile_with_internal_exhaustion_code(
        VALID_ON_EXHAUSTED_SCALAR_FRAME_CARRIAGE_FIXTURE,
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        validate_shared=True,
    )
    on_exhausted_bundle = on_exhausted_result.validated_bundles[
        "loop-recur-on-exhausted-scalar-frame-carriage"
    ]
    on_exhausted_state_manager = StateManager(
        workspace=tmp_path,
        run_id="diagnostic-loop-on-exhausted",
    )
    on_exhausted_state_manager.initialize(
        VALID_ON_EXHAUSTED_SCALAR_FRAME_CARRIAGE_FIXTURE.as_posix()
    )

    on_exhausted_state = WorkflowExecutor(
        on_exhausted_bundle,
        tmp_path,
        on_exhausted_state_manager,
        retry_delay_ms=0,
    ).execute(on_error="stop")

    on_exhausted_loop = on_exhausted_state["steps"][
        "loop-recur-on-exhausted-scalar-frame-carriage__loop"
    ]
    assert on_exhausted_loop["status"] == "completed"
    assert "error" not in on_exhausted_loop


def test_lowering_loop_recur_uses_pure_projection_for_list_constructor_seed(
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
    bundle = result.validated_bundles_by_name[
        "loop_recur_list_constructor_seed::orchestrate"
    ]
    seed_step = next(
        step
        for step in bundle.surface.steps
        if step.name.endswith("__seed")
    )
    authored = result.entry_result.lowered_workflows[0].authored_mapping
    authored_repeat_step = next(
        step for step in authored["steps"] if "repeat_until" in step
    )

    assert seed_step.pure_projection is not None
    assert seed_step.pure_projection["output_contracts"] == {
        "state": {
            "kind": "collection",
            "type": "list",
            "items": {"type": "string"},
        }
    }
    list_type_descriptor = {
        "kind": "list",
        "item": {"kind": "primitive", "name": "String"},
    }
    assert seed_step.pure_projection["payload"]["result_type"] == list_type_descriptor
    assert [
        name
        for name, contract in authored_repeat_step["repeat_until"]["outputs"].items()
        if contract.get("kind") == "collection"
    ] == ["state", "result"]
    rest_projection = next(
        child["pure_projection"]
        for router in authored_repeat_step["repeat_until"]["steps"]
        if "else" in router
        for child in router["else"]["steps"]
        if child.get("pure_projection", {})
        .get("payload", {})
        .get("expr", {})
        .get("operator")
        == "list/rest"
    )
    assert rest_projection["payload"]["result_type"] == list_type_descriptor

    materialized_values: list[dict[str, object]] = []

    def collect_values(value: object) -> None:
        if isinstance(value, dict):
            materialize = value.get("materialize_artifacts")
            if isinstance(materialize, dict):
                values = materialize.get("values")
                if isinstance(values, list):
                    materialized_values.extend(
                        item for item in values if isinstance(item, dict)
                    )
            for child in value.values():
                collect_values(child)
        elif isinstance(value, list):
            for child in value:
                collect_values(child)

    collect_values(authored_repeat_step["repeat_until"])
    assert {
        "name": "result",
        "source": {"literal": []},
        "contract": {
            "kind": "collection",
            "type": "list",
            "items": {"type": "string"},
        },
    } in materialized_values


def test_lowering_loop_recur_projects_mixed_list_and_generated_relpath_seed(
    tmp_path: Path,
) -> None:
    workflow_path = _write_module(
        tmp_path / "loop_recur_mixed_list_relpath_seed.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.18")',
                "  (defmodule loop_recur_mixed_list_relpath_seed)",
                "  (export orchestrate)",
                "  (defpath WorkReport",
                "    :kind relpath",
                '    :under "artifacts/work"',
                "    :must-exist true)",
                "  (defworkflow orchestrate () -> List[String]",
                "    (loop/recur",
                "      :max 1",
                "      :state (loop-state",
                '               (items List[String] (list "first" "second"))',
                "               (report WorkReport",
                "                 (__generated-relpath-seed__",
                "                   WorkReport",
                '                   "artifacts/work/mixed-list-seed.md"',
                '                   "mixed-list-seed")))',
                "      (fn (state)",
                "        (done state.items)))))",
            ]
        ),
    )

    result = _compile_entrypoint(
        workflow_path,
        source_root=tmp_path,
        tmp_path=tmp_path,
        validate_shared=True,
    )
    bundle = result.validated_bundles_by_name[
        "loop_recur_mixed_list_relpath_seed::orchestrate"
    ]
    seed_step = next(
        step
        for step in bundle.surface.steps
        if step.name.endswith("__seed")
    )
    list_component_step = next(
        step
        for step in bundle.surface.steps
        if step.name == f"{seed_step.name}__state__items"
    )

    assert list_component_step.pure_projection is not None
    assert list_component_step.pure_projection["payload"]["expr"]["kind"] == "list"
    assert list_component_step.pure_projection["output_contracts"]["__result__"] == {
        "kind": "collection",
        "type": "list",
        "items": {"type": "string"},
    }
    assert not seed_step.pure_projection
    assert seed_step.materialize_artifacts
    seed_values = {
        value["name"]: value
        for value in seed_step.materialize_artifacts["values"]
    }
    assert seed_values["state__items"] == {
        "name": "state__items",
        "source": {
            "ref": (
                f"root.steps.{list_component_step.name}."
                "artifacts.__result__"
            )
        },
        "contract": {
            "kind": "collection",
            "type": "list",
            "items": {"type": "string"},
        },
    }
    assert seed_values["state__report"] == {
        "name": "state__report",
        "source": {"literal": "artifacts/work/mixed-list-seed.md"},
        "contract": {
            "kind": "relpath",
            "type": "relpath",
            "under": "artifacts/work",
            "must_exist_target": False,
        },
    }
    assert (
        "artifacts/work/mixed-list-seed.md"
        in result.entry_result.lowered_workflows[0].origin_map.generated_path_spans
    )


@pytest.mark.parametrize(
    "item_type",
    (
        "Optional[String]",
        "Map[String,Int]",
    ),
)
def test_lowering_loop_recur_carries_nested_transportable_list_elements(
    tmp_path: Path,
    item_type: str,
) -> None:
    workflow_path = _write_module(
        tmp_path / "loop_recur_nested_list_state.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.18")',
                "  (defmodule loop_recur_nested_list_state)",
                "  (export orchestrate)",
                f"  (defworkflow orchestrate () -> List[{item_type}]",
                "    (let* ((item",
                "             (provider-result providers.execute",
                "               :prompt prompts.implementation.execute",
                "               :inputs ()",
                f"               :returns {item_type})))",
                "      (loop/recur :max 1 :state (list item)",
                "        (fn (state)",
                "          (done state))))))",
            ]
        ),
    )

    result = _compile_entrypoint(
        workflow_path,
        source_root=tmp_path,
        tmp_path=tmp_path,
        validate_shared=True,
    )
    bundle = result.validated_bundles_by_name[
        "loop_recur_nested_list_state::orchestrate"
    ]
    repeat_step = next(
        step for step in bundle.surface.steps if step.repeat_until is not None
    )

    state_contract = repeat_step.repeat_until.outputs["state"]
    assert state_contract.kind == "collection"
    assert state_contract.value_type == "list"
    assert state_contract.definition["items"]["type"] in {"optional", "map"}


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
    nested_provider = next(
        step
        for step in repeat_step["repeat_until"]["steps"]
        if step.get("provider") == "test-provider"
    )
    typed_by_name = {
        row["binding_name"]: row
        for row in nested_provider["typed_prompt_inputs"]
    }
    assert typed_by_name["execution_report_target"]["value_source"] == {
        "kind": "typed_binding_ref",
        "binding": {"ref": "inputs.phase-ctx__execution_report_target"},
    }
    assert typed_by_name["progress_report_target"]["value_source"] == {
        "kind": "typed_binding_ref",
        "binding": {"ref": "inputs.phase-ctx__progress_report_target"},
    }


def test_wcc_lifted_phase_provider_rejects_partial_implicit_input_carriage(
    tmp_path: Path,
) -> None:
    source = """
(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.18")
  (defmodule wcc_phase_mixed)
  (import std/phase :only (with-phase))
  (defpath WorkTarget
    :kind relpath
    :under "artifacts/work"
    :must-exist false)
  (defrecord RunCtx
    (run-id RunId)
    (state-root Path.state-root)
    (artifact-root Path.artifact-root))
  (defrecord PhaseCtx
    (run RunCtx)
    (phase-name Symbol)
    (state-root Path.state-root)
    (artifact-root Path.artifact-root)
    (execution_report_target WorkTarget)
    (progress_report_target WorkTarget))
  (defworkflow run
    ((phase-ctx PhaseCtx)
     (count Int)
     (items List[RunId]))
    -> Bool
    (loop/recur :max 1 :state false
      (fn (state)
        (let* ((result
                 (with-phase phase-ctx implementation
                   (provider-result providers.execute
                     :prompt prompts.execute
                     :inputs (count items
                              (phase-target execution-report)
                              (phase-target progress-report))
                     :returns Bool))))
          (done result))))))
""".lstrip()
    workflow_path = _write_module(
        tmp_path / "wcc_phase_mixed.orc",
        source,
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage3_module(
            workflow_path,
            provider_externs={"providers.execute": "test-provider"},
            prompt_externs={"prompts.execute": "prompt.md"},
            validate_shared=False,
            workspace_root=tmp_path,
            lowering_route="wcc_m4",
        )

    assert [
        diagnostic.code for diagnostic in excinfo.value.diagnostics
    ] == ["typed_prompt_input_renderer_default_missing"]
    items_line = source.splitlines().index(
        "                     :inputs (count items"
    ) + 1
    assert excinfo.value.diagnostics[0].span.start.line == items_line


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
