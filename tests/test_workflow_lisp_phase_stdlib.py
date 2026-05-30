from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from orchestrator.workflow_lisp.adapters import (
    load_canonical_phase_result,
    validate_reusable_phase_state,
)
from orchestrator.workflow_lisp.compiler import (
    _definition_only_syntax_module,
    _augment_resume_command_boundaries,
    _validate_definition_module,
    compile_stage3_module,
)
from orchestrator.workflow_lisp.definitions import elaborate_definition_module
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from orchestrator.workflow_lisp.reader import read_sexpr_file
from orchestrator.workflow_lisp.syntax import build_syntax_module
from orchestrator.workflow_lisp.type_env import FrontendTypeEnvironment
from orchestrator.workflow_lisp.workflows import (
    CertifiedAdapterBinding,
    CommandBoundaryEnvironment,
    ExternEnvironment,
    ExternalToolBinding,
    PromptExtern,
    ProviderExtern,
    build_workflow_catalog,
    elaborate_workflow_definitions,
    typecheck_workflow_definitions,
)


FIXTURES = Path(__file__).parent / "fixtures" / "workflow_lisp"
VALID_RUN_PROVIDER_FIXTURE = FIXTURES / "valid" / "phase_stdlib_run_provider_phase.orc"
VALID_PHASE_SNAPSHOT_EFFECTS_FIXTURE = FIXTURES / "valid" / "phase_snapshot_effects.orc"
VALID_POINTER_MATERIALIZATION_EFFECTS_FIXTURE = FIXTURES / "valid" / "pointer_materialization_effects.orc"
VALID_REVIEW_LOOP_FIXTURE = FIXTURES / "valid" / "phase_stdlib_review_loop.orc"
VALID_RESUME_FIXTURE = FIXTURES / "valid" / "phase_stdlib_resume_or_start.orc"
INVALID_PHASE_CTX_FIXTURE = FIXTURES / "invalid" / "phase_ctx_contract_invalid.orc"
INVALID_LEGACY_BRIDGE_FIXTURE = FIXTURES / "invalid" / "phase_ctx_legacy_bridge_misuse.orc"
INVALID_PHASE_TARGET_FIXTURE = FIXTURES / "invalid" / "phase_target_unknown_generic.orc"
INVALID_REVIEW_LOOP_FIXTURE = FIXTURES / "invalid" / "review_loop_result_contract_invalid.orc"
INVALID_RESUME_FIXTURE = FIXTURES / "invalid" / "resume_or_start_contract_invalid.orc"
INVALID_RESUME_POINTER_FIXTURE = FIXTURES / "invalid" / "resume_or_start_pointer_authority_invalid.orc"
INVALID_RESUME_RECORD_VALID_WHEN_FIXTURE = FIXTURES / "invalid" / "resume_or_start_record_valid_when_invalid.orc"
INVALID_UNCERTIFIED_RESUME_FIXTURE = FIXTURES / "invalid" / "resume_or_start_uncertified_adapter.orc"


def _build_syntax_module(path: Path):
    return build_syntax_module(read_sexpr_file(path))


def _compile_definition_module(path: Path):
    syntax_module = _build_syntax_module(path)
    module = elaborate_definition_module(_definition_only_syntax_module(syntax_module))
    _validate_definition_module(module)
    return module


def _write_module(path: Path, body: str) -> Path:
    path.write_text(body, encoding="utf-8")
    return path


def _rewrite_fixture(path: Path, *, replacements: tuple[tuple[str, str], ...], tmp_path: Path, filename: str) -> Path:
    source = path.read_text(encoding="utf-8")
    for old, new in replacements:
        assert old in source, f"fixture text not found: {old}"
        source = source.replace(old, new, 1)
    return _write_module(tmp_path / filename, source)


def _write_payload_file(tmp_path: Path, filename: str, payload: dict[str, object]) -> str:
    path = tmp_path / filename
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path.as_posix()


def _structured_contract_fingerprint(
    *,
    structured_contract_kind: str,
    structured_contract: dict[str, object],
    return_type_name: str,
) -> str:
    digest = hashlib.sha256(
        json.dumps(structured_contract, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return f"2.14:{return_type_name}:{structured_contract_kind}:{digest}"


def _extern_environment() -> ExternEnvironment:
    return ExternEnvironment(
        bindings_by_name={
            "providers.execute": ProviderExtern(
                name="providers.execute",
                provider_id="fake-execute",
            ),
            "providers.review": ProviderExtern(
                name="providers.review",
                provider_id="fake-review",
            ),
            "providers.fix": ProviderExtern(
                name="providers.fix",
                provider_id="fake-fix",
            ),
            "prompts.implementation.execute": PromptExtern(
                name="prompts.implementation.execute",
                asset_file="prompts/implementation/execute.md",
            ),
            "prompts.implementation.review": PromptExtern(
                name="prompts.implementation.review",
                asset_file="prompts/implementation/review.md",
            ),
            "prompts.implementation.fix": PromptExtern(
                name="prompts.implementation.fix",
                asset_file="prompts/implementation/fix.md",
            ),
        }
    )


def _command_boundary_environment() -> CommandBoundaryEnvironment:
    return CommandBoundaryEnvironment(
        bindings_by_name={
            "run_checks": ExternalToolBinding(
                name="run_checks",
                stable_command=("python", "scripts/run_checks.py"),
            ),
            "resolve_plan_gate": ExternalToolBinding(
                name="resolve_plan_gate",
                stable_command=("python", "scripts/resolve_plan_gate.py"),
            ),
            "load_canonical_phase_result__ChecksResult": ExternalToolBinding(
                name="load_canonical_phase_result__ChecksResult",
                stable_command=(
                    "python",
                    "-m",
                    "orchestrator.workflow_lisp.adapters.load_canonical_phase_result",
                ),
            ),
        }
    )


def _typecheck_fixture(path: Path):
    module = _compile_definition_module(path)
    type_env = FrontendTypeEnvironment.from_module(module)
    syntax_module = _build_syntax_module(path)
    workflow_defs = elaborate_workflow_definitions(syntax_module)
    workflow_catalog = build_workflow_catalog(module, workflow_defs, type_env)
    command_boundary_environment = _augment_resume_command_boundaries(
        _command_boundary_environment(),
        expressions=tuple(workflow.body for workflow in workflow_defs),
    )
    return typecheck_workflow_definitions(
        workflow_defs,
        type_env=type_env,
        workflow_catalog=workflow_catalog,
        extern_environment=_extern_environment(),
        command_boundary_environment=command_boundary_environment,
    )


def _compile(path: Path, *, tmp_path: Path, validate_shared: bool = False):
    return compile_stage3_module(
        path,
        provider_externs={
            "providers.execute": "fake-execute",
            "providers.review": "fake-review",
            "providers.fix": "fake-fix",
        },
        prompt_externs={
            "prompts.implementation.execute": "prompts/implementation/execute.md",
            "prompts.implementation.review": "prompts/implementation/review.md",
            "prompts.implementation.fix": "prompts/implementation/fix.md",
        },
        command_boundaries={
            "run_checks": ExternalToolBinding(
                name="run_checks",
                stable_command=("python", "scripts/run_checks.py"),
            ),
            "resolve_plan_gate": ExternalToolBinding(
                name="resolve_plan_gate",
                stable_command=("python", "scripts/resolve_plan_gate.py"),
            ),
            "load_canonical_phase_result__ChecksResult": ExternalToolBinding(
                name="load_canonical_phase_result__ChecksResult",
                stable_command=(
                    "python",
                    "-m",
                    "orchestrator.workflow_lisp.adapters.load_canonical_phase_result",
                ),
            ),
        },
        validate_shared=validate_shared,
        workspace_root=tmp_path,
    )


def _assert_diagnostic_code(excinfo: pytest.ExceptionInfo[LispFrontendCompileError], code: str) -> None:
    assert excinfo.value.diagnostics[0].code == code


def _iter_nested_steps(steps):
    for step in steps:
        yield step
        match_block = step.get("match")
        if isinstance(match_block, dict):
            cases = match_block.get("cases", {})
            if isinstance(cases, dict):
                for case in cases.values():
                    case_steps = case.get("steps", [])
                    if isinstance(case_steps, list):
                        yield from _iter_nested_steps(case_steps)
        repeat_block = step.get("repeat_until")
        if isinstance(repeat_block, dict):
            nested_steps = repeat_block.get("steps", [])
            if isinstance(nested_steps, list):
                yield from _iter_nested_steps(nested_steps)



def test_typecheck_accepts_generic_phase_ctx_for_phase_target(tmp_path: Path) -> None:
    path = _write_module(
        tmp_path / "generic_phase_target_ok.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defpath WorkReportTarget",
                "    :kind relpath",
                '    :under "artifacts/work"',
                "    :must-exist false)",
                "  (defrecord RunCtx",
                "    (run-id RunId)",
                "    (state-root Path.state-root)",
                "    (artifact-root Path.artifact-root))",
                "  (defrecord PhaseCtx",
                "    (run RunCtx)",
                "    (phase-name Symbol)",
                "    (state-root Path.state-root)",
                "    (artifact-root Path.artifact-root))",
                "  (defrecord ReportTargetOnly",
                "    (report_path WorkReportTarget))",
                "  (defworkflow generic-phase-target",
                "    ((phase-ctx PhaseCtx))",
                "    -> ReportTargetOnly",
                "    (with-phase phase-ctx implementation",
                "      (record ReportTargetOnly",
                "        :report_path (phase-target execution-report)))))",
            ]
        ),
    )

    typed = _typecheck_fixture(path)

    assert [workflow.definition.name for workflow in typed] == ["generic-phase-target"]


def test_typecheck_rejects_resume_state_adapter_authored_outside_resume_or_start(
    tmp_path: Path,
) -> None:
    path = _write_module(
        tmp_path / "resume_state_adapter_outside_resume_or_start.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defpath StateFile",
                "    :kind relpath",
                '    :under "state"',
                "    :must-exist false)",
                "  (defrecord ChecksResult",
                "    (status String))",
                "  (defworkflow orchestrate",
                "    ((resume_state StateFile))",
                "    -> ChecksResult",
                "    (command-result load_resume_state",
                '      :argv ("python" "scripts/load_resume_state.py" resume_state)',
                "      :returns ChecksResult)))",
            ]
        ),
    )
    module = _compile_definition_module(path)
    type_env = FrontendTypeEnvironment.from_module(module)
    syntax_module = _build_syntax_module(path)
    workflow_defs = elaborate_workflow_definitions(syntax_module)
    workflow_catalog = build_workflow_catalog(module, workflow_defs, type_env)
    command_boundary_environment = CommandBoundaryEnvironment(
        bindings_by_name={
            "load_resume_state": CertifiedAdapterBinding(
                name="load_resume_state",
                stable_command=("python", "scripts/load_resume_state.py"),
                input_contract={"type": "object"},
                output_type_name="ChecksResult",
                effects=("resume_state_reuse", "structured_result"),
                path_safety={"kind": "workspace_relpath"},
                source_map_behavior="step",
                fixture_ids=("resume_state_reuse_ok",),
                negative_fixture_ids=("resume_state_reuse_bad",),
            ),
        }
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        typecheck_workflow_definitions(
            workflow_defs,
            type_env=type_env,
            workflow_catalog=workflow_catalog,
            command_boundary_environment=command_boundary_environment,
        )

    _assert_diagnostic_code(excinfo, "recovery_gate_without_resume_or_start")


def test_run_provider_phase_accepts_generic_ctx_after_typechecking() -> None:
    typed = _typecheck_fixture(VALID_RUN_PROVIDER_FIXTURE)

    assert [workflow.definition.name for workflow in typed] == [
        "run-provider-phase-demo",
        "produce-one-of-demo",
    ]


def test_typecheck_rejects_run_provider_phase_name_mismatch_with_active_phase(tmp_path: Path) -> None:
    path = _rewrite_fixture(
        VALID_RUN_PROVIDER_FIXTURE,
        replacements=(("run-provider-phase implementation", "run-provider-phase wrong-phase"),),
        tmp_path=tmp_path,
        filename="run_provider_phase_name_mismatch.orc",
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _typecheck_fixture(path)

    _assert_diagnostic_code(excinfo, "phase_scope_name_mismatch")


def test_typecheck_rejects_invalid_generic_phase_ctx_contract() -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _typecheck_fixture(INVALID_PHASE_CTX_FIXTURE)

    _assert_diagnostic_code(excinfo, "phase_context_invalid")


def test_generic_stdlib_rejects_legacy_bridge() -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _typecheck_fixture(INVALID_LEGACY_BRIDGE_FIXTURE)

    _assert_diagnostic_code(excinfo, "phase_ctx_legacy_bridge_invalid")


def test_typecheck_rejects_unknown_generic_phase_target() -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _typecheck_fixture(INVALID_PHASE_TARGET_FIXTURE)

    _assert_diagnostic_code(excinfo, "phase_target_contract_unresolved")


def test_lowering_run_provider_phase_derives_phase_bundle_path(tmp_path: Path) -> None:
    result = _compile(VALID_RUN_PROVIDER_FIXTURE, tmp_path=tmp_path)

    authored = next(
        workflow.authored_mapping
        for workflow in result.lowered_workflows
        if workflow.typed_workflow.definition.name == "run-provider-phase-demo"
    )
    provider_step = next(step for step in authored["steps"] if step.get("provider") == "fake-execute")

    assert provider_step["variant_output"]["path"].endswith("/phases/implementation/state.json")
    assert provider_step["variant_output"]["path"].startswith("${inputs.phase-ctx__state-root}")


def test_lowering_run_provider_phase_materializes_and_consumes_authored_inputs(tmp_path: Path) -> None:
    result = _compile(VALID_RUN_PROVIDER_FIXTURE, tmp_path=tmp_path)

    authored = next(
        workflow.authored_mapping
        for workflow in result.lowered_workflows
        if workflow.typed_workflow.definition.name == "run-provider-phase-demo"
    )
    materialize_step = next(step for step in authored["steps"] if "materialize_artifacts" in step)
    provider_step = next(step for step in authored["steps"] if step.get("provider") == "fake-execute")

    assert [value["name"] for value in materialize_step["materialize_artifacts"]["values"]] == [
        "design",
        "plan",
        "execution_report_target",
        "progress_report_target",
    ]
    assert [consume["artifact"] for consume in provider_step["consumes"]] == [
        "design",
        "plan",
        "execution_report_target",
        "progress_report_target",
    ]
    assert provider_step["prompt_consumes"] == [
        "design",
        "plan",
        "execution_report_target",
        "progress_report_target",
    ]


def test_lowering_produce_one_of_uses_pre_snapshot_and_select_variant_output(tmp_path: Path) -> None:
    result = _compile(VALID_RUN_PROVIDER_FIXTURE, tmp_path=tmp_path)

    authored = next(
        workflow.authored_mapping
        for workflow in result.lowered_workflows
        if workflow.typed_workflow.definition.name == "produce-one-of-demo"
    )
    assert any("pre_snapshot" in step for step in authored["steps"])
    assert any("select_variant_output" in step for step in authored["steps"])


def test_lowering_phase_snapshot_effects_fixture_keeps_orchestrate_pre_snapshot(tmp_path: Path) -> None:
    result = _compile(VALID_PHASE_SNAPSHOT_EFFECTS_FIXTURE, tmp_path=tmp_path)
    authored = next(
        workflow.authored_mapping
        for workflow in result.lowered_workflows
        if workflow.typed_workflow.definition.name == "orchestrate"
    )

    assert any("pre_snapshot" in step for step in authored["steps"])


def test_lowering_pointer_materialization_effects_fixture_keeps_orchestrate_pointer_paths(tmp_path: Path) -> None:
    result = _compile(VALID_POINTER_MATERIALIZATION_EFFECTS_FIXTURE, tmp_path=tmp_path)
    authored = next(
        workflow.authored_mapping
        for workflow in result.lowered_workflows
        if workflow.typed_workflow.definition.name == "orchestrate"
    )
    materialize_step = next(step for step in authored["steps"] if "materialize_artifacts" in step)

    assert all(
        "pointer" in value and "path" in value["pointer"]
        for value in materialize_step["materialize_artifacts"]["values"]
    )


def test_lowering_produce_one_of_materializes_and_consumes_authored_inputs(tmp_path: Path) -> None:
    result = _compile(VALID_RUN_PROVIDER_FIXTURE, tmp_path=tmp_path)

    authored = next(
        workflow.authored_mapping
        for workflow in result.lowered_workflows
        if workflow.typed_workflow.definition.name == "produce-one-of-demo"
    )
    materialize_step = next(step for step in authored["steps"] if "materialize_artifacts" in step)
    provider_step = next(step for step in authored["steps"] if step.get("provider") == "fake-execute")

    assert [value["name"] for value in materialize_step["materialize_artifacts"]["values"]] == [
        "design",
        "plan",
        "execution_report_target",
        "progress_report_target",
    ]
    assert [consume["artifact"] for consume in provider_step["consumes"]] == [
        "design",
        "plan",
        "execution_report_target",
        "progress_report_target",
    ]
    assert provider_step["prompt_consumes"] == [
        "design",
        "plan",
        "execution_report_target",
        "progress_report_target",
    ]


def test_shared_validation_accepts_run_provider_phase_and_produce_one_of(tmp_path: Path) -> None:
    result = _compile(
        VALID_RUN_PROVIDER_FIXTURE,
        tmp_path=tmp_path,
        validate_shared=True,
    )

    assert {
        workflow.typed_workflow.definition.name for workflow in result.lowered_workflows
    } >= {"run-provider-phase-demo", "produce-one-of-demo"}


def test_reusable_phase_state_with_composed_with_phase_preserves_generated_write_root_inputs(
    tmp_path: Path,
) -> None:
    path = _write_module(
        tmp_path / "reusable_composed_with_phase_review_loop.orc",
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
                "  (defenum ReviewDecision",
                "    APPROVE",
                "    REVISE",
                "    BLOCKED)",
                "  (defpath WorkReport",
                "    :kind relpath",
                '    :under "artifacts/work"',
                "    :must-exist true)",
                "  (defrecord RunCtx",
                "    (run-id RunId)",
                "    (state-root Path.state-root)",
                "    (artifact-root Path.artifact-root))",
                "  (defrecord PhaseCtx",
                "    (run RunCtx)",
                "    (phase-name Symbol)",
                "    (state-root Path.state-root)",
                "    (artifact-root Path.artifact-root))",
                "  (defrecord CompletedSurface",
                "    (plan_path WorkReport))",
                "  (defrecord ReviewInputs",
                "    (report_path WorkReport))",
                "  (defrecord ReviewSurfaceResult",
                "    (report_path WorkReport))",
                "  (defunion ReviewLoopResult",
                "    (APPROVED",
                "      (checks_report WorkReport)",
                "      (review_report WorkReport)",
                "      (review_decision ReviewDecision))",
                "    (BLOCKED",
                "      (progress_report WorkReport)",
                "      (blocker_class BlockerClass))",
                "    (EXHAUSTED",
                "      (last_review_report WorkReport)",
                "      (reason String)))",
                "  (defproc review-phase-helper",
                "    ((phase-ctx PhaseCtx)",
                "     (completed CompletedSurface)",
                "     (inputs ReviewInputs))",
                "    -> ReviewSurfaceResult",
                "    :effects ()",
                "    :lowering private-workflow",
                "    (let* ((review",
                "             (with-phase phase-ctx implementation-review",
                "               (review-revise-loop implementation-review",
                "                 :ctx phase-ctx",
                "                 :completed completed",
                "                 :inputs inputs",
                "                 :review-provider providers.review",
                "                 :fix-provider providers.fix",
                "                 :review-prompt prompts.implementation.review",
                "                 :fix-prompt prompts.implementation.fix",
                "                 :max 3",
                "                 :returns ReviewLoopResult))))",
                "      (match review",
                "        ((APPROVED approved)",
                "         (record ReviewSurfaceResult",
                "           :report_path approved.review_report))",
                "        ((BLOCKED blocked)",
                "         (record ReviewSurfaceResult",
                "           :report_path blocked.progress_report))",
                "        ((EXHAUSTED exhausted)",
                "         (record ReviewSurfaceResult",
                "           :report_path exhausted.last_review_report)))))",
                "  (defworkflow run-review",
                "    ((phase-ctx PhaseCtx)",
                "     (completed CompletedSurface)",
                "     (inputs ReviewInputs))",
                "    -> ReviewSurfaceResult",
                "    (review-phase-helper phase-ctx completed inputs)))",
            ]
        ),
    )

    result = compile_stage3_module(
        path,
        provider_externs={
            "providers.review": "fake-review",
            "providers.fix": "fake-fix",
        },
        prompt_externs={
            "prompts.implementation.review": "prompts/implementation/review.md",
            "prompts.implementation.fix": "prompts/implementation/fix.md",
        },
        validate_shared=True,
        workspace_root=tmp_path,
    )

    private_workflow = next(
        workflow
        for workflow in result.lowered_workflows
        if workflow.typed_workflow.definition.name.endswith(".review-phase-helper.v1")
    )
    outer_workflow = next(
        workflow.authored_mapping
        for workflow in result.lowered_workflows
        if workflow.typed_workflow.definition.name == "run-review"
    )
    call_step = next(
        step for step in outer_workflow["steps"] if step.get("call") == private_workflow.typed_workflow.definition.name
    )

    assert any(name.startswith("__write_root__") for name in private_workflow.authored_mapping["inputs"])
    assert any(name.startswith("__write_root__") for name in call_step["with"])


def test_typecheck_rejects_invalid_review_loop_result_contract() -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _typecheck_fixture(INVALID_REVIEW_LOOP_FIXTURE)

    _assert_diagnostic_code(excinfo, "review_loop_result_contract_invalid")


def test_typecheck_rejects_review_revise_loop_name_mismatch_with_active_phase(tmp_path: Path) -> None:
    path = _rewrite_fixture(
        VALID_REVIEW_LOOP_FIXTURE,
        replacements=(("review-revise-loop implementation-review", "review-revise-loop wrong-loop"),),
        tmp_path=tmp_path,
        filename="review_revise_loop_name_mismatch.orc",
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _typecheck_fixture(path)

    _assert_diagnostic_code(excinfo, "phase_scope_name_mismatch")


def test_lowering_review_loop_carries_last_review_report_through_loop_outputs(tmp_path: Path) -> None:
    result = _compile(VALID_REVIEW_LOOP_FIXTURE, tmp_path=tmp_path)

    authored = next(
        workflow.authored_mapping
        for workflow in result.lowered_workflows
        if workflow.typed_workflow.definition.name == "review-revise-loop-demo"
    )
    repeat_step = next(step for step in authored["steps"] if "repeat_until" in step)
    loop_outputs = repeat_step["repeat_until"]["outputs"]
    on_exhausted = repeat_step["repeat_until"]["on_exhausted"]["outputs"]

    assert "last_review_report" in loop_outputs
    assert "last_review_report" not in on_exhausted
    assert repeat_step["repeat_until"]["steps"]

    body_steps = list(_iter_nested_steps(repeat_step["repeat_until"]["steps"]))

    assert any(step.get("provider") == "fake-review" for step in body_steps)
    assert any(step.get("provider") == "fake-fix" for step in body_steps)
    assert any("match" in step for step in body_steps)

    normalization_step = next(
        step
        for step in authored["steps"]
        if step.get("match", {}).get("ref")
        == "root.steps.review-revise-loop-demo__result__loop.artifacts.variant"
    )
    assert normalization_step["match"]["ref"] == "root.steps.review-revise-loop-demo__result__loop.artifacts.variant"
    assert set(normalization_step["match"]["cases"]) == {"APPROVED", "BLOCKED", "EXHAUSTED", "REVISE"}
    revise_case = normalization_step["match"]["cases"]["REVISE"]
    assert revise_case["outputs"]["variant"]["from"]["ref"] == "self.steps.NormalizeReviseVariant.artifacts.variant"


def test_lowering_review_loop_materializes_and_consumes_authored_inputs(tmp_path: Path) -> None:
    result = _compile(VALID_REVIEW_LOOP_FIXTURE, tmp_path=tmp_path)

    authored = next(
        workflow.authored_mapping
        for workflow in result.lowered_workflows
        if workflow.typed_workflow.definition.name == "review-revise-loop-demo"
    )
    materialize_step = next(step for step in authored["steps"] if "materialize_artifacts" in step)
    repeat_step = next(step for step in authored["steps"] if "repeat_until" in step)
    body_steps = list(_iter_nested_steps(repeat_step["repeat_until"]["steps"]))
    review_step = next(step for step in body_steps if step.get("name") == "ReviewDecision")
    fix_step = next(step for step in body_steps if step.get("name") == "ApplyFix")

    assert [value["name"] for value in materialize_step["materialize_artifacts"]["values"]] == [
        "completed__execution_report_path",
        "design_review_prompt",
        "fix_plan_prompt",
    ]
    expected_consumes = [
        "completed__execution_report_path",
        "design_review_prompt",
        "fix_plan_prompt",
    ]
    assert [consume["artifact"] for consume in review_step["consumes"]] == expected_consumes
    assert review_step["prompt_consumes"] == expected_consumes
    assert [consume["artifact"] for consume in fix_step["consumes"]] == expected_consumes
    assert fix_step["prompt_consumes"] == expected_consumes


def test_shared_validation_accepts_review_revise_loop(tmp_path: Path) -> None:
    result = _compile(
        VALID_REVIEW_LOOP_FIXTURE,
        tmp_path=tmp_path,
        validate_shared=True,
    )

    assert {
        workflow.typed_workflow.definition.name for workflow in result.lowered_workflows
    } >= {"review-revise-loop-demo"}


def test_review_revise_loop_review_bundle_path_is_generated_write_root(tmp_path: Path) -> None:
    result = _compile(
        VALID_REVIEW_LOOP_FIXTURE,
        tmp_path=tmp_path,
        validate_shared=True,
    )

    lowered = next(
        workflow
        for workflow in result.lowered_workflows
        if workflow.typed_workflow.definition.name == "review-revise-loop-demo"
    )
    authored = lowered.authored_mapping
    repeat_step = next(step for step in authored["steps"] if "repeat_until" in step)
    review_step = next(
        step
        for step in _iter_nested_steps(repeat_step["repeat_until"]["steps"])
        if step.get("name") == "ReviewDecision"
    )

    review_path = review_step["output_bundle"]["path"]
    hidden_input = review_path.removeprefix("${inputs.").removesuffix("}")

    assert review_path.startswith("${inputs.__write_root__")
    assert review_path.endswith("__result_bundle}")
    assert hidden_input in authored["inputs"]
    assert {
        item.generated_name: item.reason
        for item in lowered.boundary_projection.generated_internal_inputs
    }[hidden_input] == "managed_write_root"


def test_lowering_resume_or_start_registers_generated_loader_binding(tmp_path: Path) -> None:
    result = _compile(VALID_RESUME_FIXTURE, tmp_path=tmp_path)

    bindings = result.command_boundary_environment.bindings_by_name

    assert isinstance(bindings["validate_reusable_phase_state"], CertifiedAdapterBinding)
    assert isinstance(bindings["load_canonical_phase_result__ChecksResult"], CertifiedAdapterBinding)
    assert isinstance(bindings["load_canonical_phase_result__PlanGateResult"], CertifiedAdapterBinding)
    assert bindings["validate_reusable_phase_state"].stable_command == (
        "python",
        "-m",
        "orchestrator.workflow_lisp.adapters.validate_reusable_phase_state",
    )
    assert bindings["load_canonical_phase_result__ChecksResult"].stable_command == (
        "python",
        "-m",
        "orchestrator.workflow_lisp.adapters.load_canonical_phase_result",
    )
    assert bindings["load_canonical_phase_result__PlanGateResult"].stable_command == (
        "python",
        "-m",
        "orchestrator.workflow_lisp.adapters.load_canonical_phase_result",
    )


def test_resume_or_start_lowers_contract_fingerprint_and_loader_metadata(
    tmp_path: Path,
) -> None:
    result = _compile(VALID_RESUME_FIXTURE, tmp_path=tmp_path)
    authored_by_name = {
        workflow.typed_workflow.definition.name: workflow.authored_mapping
        for workflow in result.lowered_workflows
        if workflow.typed_workflow.definition.name in {"resume-record-phase", "resume-plan-gate"}
    }

    record_validator_payload = json.loads(authored_by_name["resume-record-phase"]["steps"][0]["command"][3])
    assert record_validator_payload["target_dsl_version"] == "2.14"
    assert record_validator_payload["return_type_name"] == "ChecksResult"
    assert record_validator_payload["structured_contract_kind"] == "record"
    assert record_validator_payload["expected_contract_fingerprint"].startswith("2.14:ChecksResult:record:")
    assert record_validator_payload["artifact_requirements"] == {
        "ChecksResult": [
            {
                "field_path": ["checks_report"],
                "under": "artifacts/work",
            }
        ]
    }
    record_loader_payload = json.loads(
        next(
            step["command"][3]
            for step in authored_by_name["resume-record-phase"]["steps"][1]["match"]["cases"]["REUSE"]["steps"]
            if step.get("command", [])[:3]
            == [
                "python",
                "-m",
                "orchestrator.workflow_lisp.adapters.load_canonical_phase_result",
            ]
        )
    )
    assert record_loader_payload["target_dsl_version"] == "2.14"
    assert record_loader_payload["return_type_name"] == "ChecksResult"
    assert record_loader_payload["expected_contract_fingerprint"].startswith("2.14:ChecksResult:record:")

    union_validator_payload = json.loads(authored_by_name["resume-plan-gate"]["steps"][0]["command"][3])
    assert union_validator_payload["target_dsl_version"] == "2.14"
    assert union_validator_payload["return_type_name"] == "PlanGateResult"
    assert union_validator_payload["structured_contract_kind"] == "union"
    assert union_validator_payload["expected_contract_fingerprint"].startswith("2.14:PlanGateResult:union:")
    assert union_validator_payload["artifact_requirements"] == {
        "APPROVED": [
            {
                "field_path": ["shared_report_path"],
                "under": "artifacts/work",
            },
            {
                "field_path": ["execution_report_path"],
                "under": "artifacts/work",
            }
        ],
    }
    union_loader_payload = json.loads(
        next(
            step["command"][3]
            for step in authored_by_name["resume-plan-gate"]["steps"][1]["match"]["cases"]["REUSE"]["steps"]
            if step.get("command", [])[:3]
            == [
                "python",
                "-m",
                "orchestrator.workflow_lisp.adapters.load_canonical_phase_result",
            ]
        )
    )
    assert union_loader_payload["target_dsl_version"] == "2.14"
    assert union_loader_payload["return_type_name"] == "PlanGateResult"
    assert union_loader_payload["expected_contract_fingerprint"].startswith("2.14:PlanGateResult:union:")


def test_resume_or_start_reserved_adapter_names_cannot_be_shadowed(tmp_path: Path) -> None:
    result = compile_stage3_module(
        VALID_RESUME_FIXTURE,
        provider_externs={
            "providers.execute": "fake-execute",
            "providers.review": "fake-review",
            "providers.fix": "fake-fix",
        },
        prompt_externs={
            "prompts.implementation.execute": "prompts/implementation/execute.md",
            "prompts.implementation.review": "prompts/implementation/review.md",
            "prompts.implementation.fix": "prompts/implementation/fix.md",
        },
        command_boundaries={
            "run_checks": ExternalToolBinding(
                name="run_checks",
                stable_command=("python", "scripts/run_checks.py"),
            ),
            "resolve_plan_gate": ExternalToolBinding(
                name="resolve_plan_gate",
                stable_command=("python", "scripts/resolve_plan_gate.py"),
            ),
            "validate_reusable_phase_state": ExternalToolBinding(
                name="validate_reusable_phase_state",
                stable_command=("python", "scripts/not_certified_validator.py"),
            ),
            "load_canonical_phase_result__ChecksResult": ExternalToolBinding(
                name="load_canonical_phase_result__ChecksResult",
                stable_command=("python", "scripts/not_certified_loader.py"),
            ),
        },
        validate_shared=False,
        workspace_root=tmp_path,
    )

    bindings = result.command_boundary_environment.bindings_by_name

    assert isinstance(bindings["validate_reusable_phase_state"], CertifiedAdapterBinding)
    assert isinstance(bindings["load_canonical_phase_result__ChecksResult"], CertifiedAdapterBinding)
    assert bindings["validate_reusable_phase_state"].stable_command == (
        "python",
        "-m",
        "orchestrator.workflow_lisp.adapters.validate_reusable_phase_state",
    )
    assert bindings["load_canonical_phase_result__ChecksResult"].stable_command == (
        "python",
        "-m",
        "orchestrator.workflow_lisp.adapters.load_canonical_phase_result",
    )


def test_resume_or_start_in_inline_defproc_registers_generated_adapters(tmp_path: Path) -> None:
    path = _write_module(
        tmp_path / "resume_or_start_defproc.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defpath WorkReport",
                "    :kind relpath",
                '    :under "artifacts/work"',
                "    :must-exist true)",
                "  (defpath PhaseStateBundle",
                "    :kind relpath",
                '    :under "state"',
                "    :must-exist false)",
                "  (defrecord RunCtx",
                "    (run-id RunId)",
                "    (state-root Path.state-root)",
                "    (artifact-root Path.artifact-root))",
                "  (defrecord PhaseCtx",
                "    (run RunCtx)",
                "    (phase-name Symbol)",
                "    (state-root Path.state-root)",
                "    (artifact-root Path.artifact-root))",
                "  (defrecord ResumeInputs",
                "    (resume_from PhaseStateBundle)",
                "    (report_path WorkReport))",
                "  (defrecord ChecksResult",
                "    (checks_report WorkReport))",
                "  (defproc resume-checks",
                "    ((phase-ctx PhaseCtx)",
                "     (inputs ResumeInputs))",
                "    -> ChecksResult",
                "    :effects ((uses-command run_checks) (uses-command validate_reusable_phase_state))",
                "    :lowering inline",
                "    (with-phase phase-ctx checks",
                "      (resume-or-start checks",
                "        :ctx phase-ctx",
                "        :resume-from inputs.resume_from",
                "        :start",
                "          (command-result run_checks",
                '            :argv ("python" "scripts/run_checks.py" inputs.report_path)',
                "            :returns ChecksResult)",
                "        :returns ChecksResult)))",
                "  (defworkflow orchestrate",
                "    ((phase-ctx PhaseCtx)",
                "     (inputs ResumeInputs))",
                "    -> ChecksResult",
                "    (resume-checks phase-ctx inputs)))",
            ]
        ),
    )

    result = compile_stage3_module(
        path,
        command_boundaries={
            "run_checks": ExternalToolBinding(
                name="run_checks",
                stable_command=("python", "scripts/run_checks.py"),
            )
        },
        validate_shared=False,
        workspace_root=tmp_path,
    )

    bindings = result.command_boundary_environment.bindings_by_name
    assert isinstance(bindings["validate_reusable_phase_state"], CertifiedAdapterBinding)
    assert isinstance(bindings["load_canonical_phase_result__ChecksResult"], CertifiedAdapterBinding)

    authored = next(
        workflow.authored_mapping
        for workflow in result.lowered_workflows
        if workflow.typed_workflow.definition.name == "orchestrate"
    )
    assert authored["steps"][0]["command"][:3] == [
        "python",
        "-m",
        "orchestrator.workflow_lisp.adapters.validate_reusable_phase_state",
    ]


def test_lowering_resume_or_start_emits_validator_and_branch_normalization(tmp_path: Path) -> None:
    result = _compile(VALID_RESUME_FIXTURE, tmp_path=tmp_path)

    by_name = {
        workflow.typed_workflow.definition.name: workflow.authored_mapping
        for workflow in result.lowered_workflows
        if workflow.typed_workflow.definition.name in {"resume-record-phase", "resume-plan-gate"}
    }

    record_workflow = by_name["resume-record-phase"]
    assert len(record_workflow["steps"]) == 2
    validator_step = record_workflow["steps"][0]
    assert validator_step["command"][:3] == [
        "python",
        "-m",
        "orchestrator.workflow_lisp.adapters.validate_reusable_phase_state",
    ]
    validator_payload = json.loads(validator_step["command"][3])
    assert validator_payload["structured_contract_kind"] == "record"
    assert validator_payload["expected_contract_fingerprint"].startswith("2.14:ChecksResult:record:")
    assert validator_payload["artifact_requirements"] == {
        "ChecksResult": [
            {
                "field_path": ["checks_report"],
                "under": "artifacts/work",
            }
        ]
    }
    assert validator_step["variant_output"]["variants"]["REUSE"]["fields"] == [
        {
            "name": "source_bundle_path",
            "json_pointer": "/source_bundle_path",
            "type": "relpath",
        },
        {
            "name": "source_bundle_sha256",
            "json_pointer": "/source_bundle_sha256",
            "type": "string",
        },
    ]
    branch_step = record_workflow["steps"][1]
    assert set(branch_step["match"]["cases"]) == {"REUSE", "START"}
    reuse_steps = branch_step["match"]["cases"]["REUSE"]["steps"]
    start_steps = branch_step["match"]["cases"]["START"]["steps"]
    assert any(
        step.get("command", [])[:3]
        == [
            "python",
            "-m",
            "orchestrator.workflow_lisp.adapters.load_canonical_phase_result",
        ]
        for step in reuse_steps
    )
    assert any(step.get("command", [])[:2] == ["python", "scripts/run_checks.py"] for step in start_steps)

    plan_gate_workflow = by_name["resume-plan-gate"]
    assert len(plan_gate_workflow["steps"]) == 3
    validator_step = plan_gate_workflow["steps"][0]
    assert validator_step["command"][:3] == [
        "python",
        "-m",
        "orchestrator.workflow_lisp.adapters.validate_reusable_phase_state",
    ]
    validator_payload = json.loads(validator_step["command"][3])
    assert validator_payload["structured_contract_kind"] == "union"
    assert validator_payload["expected_contract_fingerprint"].startswith("2.14:PlanGateResult:union:")
    branch_step = next(
        step
        for step in plan_gate_workflow["steps"]
        if step.get("match", {}).get("ref")
        == f"root.steps.{validator_step['name']}.artifacts.variant"
    )
    assert set(branch_step["match"]["cases"]) == {"REUSE", "START"}
    reuse_steps = branch_step["match"]["cases"]["REUSE"]["steps"]
    start_steps = branch_step["match"]["cases"]["START"]["steps"]
    assert any(
        step.get("command", [])[:3]
        == [
            "python",
            "-m",
            "orchestrator.workflow_lisp.adapters.load_canonical_phase_result",
        ]
        for step in reuse_steps
    )
    assert any(step.get("call") == "plan-run" for step in _iter_nested_steps(start_steps))


def test_shared_validation_accepts_resume_or_start(tmp_path: Path) -> None:
    result = _compile(
        VALID_RESUME_FIXTURE,
        tmp_path=tmp_path,
        validate_shared=True,
    )

    assert {
        workflow.typed_workflow.definition.name for workflow in result.lowered_workflows
    } >= {"resume-record-phase", "resume-plan-gate"}


def test_resume_or_start_supports_union_start_workflow_call(tmp_path: Path) -> None:
    result = _compile(VALID_RESUME_FIXTURE, tmp_path=tmp_path, validate_shared=True)
    authored = next(
        workflow.authored_mapping
        for workflow in result.lowered_workflows
        if workflow.typed_workflow.definition.name == "resume-plan-gate"
    )
    validator_step = authored["steps"][0]
    branch_step = next(
        step
        for step in authored["steps"]
        if step.get("match", {}).get("ref")
        == f"root.steps.{validator_step['name']}.artifacts.variant"
    )
    start_steps = branch_step["match"]["cases"]["START"]["steps"]

    assert any(step.get("call") == "plan-run" for step in _iter_nested_steps(start_steps))


def test_typecheck_rejects_resume_or_start_contract_invalid() -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _typecheck_fixture(INVALID_RESUME_FIXTURE)

    _assert_diagnostic_code(excinfo, "resume_or_start_contract_invalid")


def test_typecheck_rejects_resume_or_start_valid_when_for_record_return() -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _typecheck_fixture(INVALID_RESUME_RECORD_VALID_WHEN_FIXTURE)

    _assert_diagnostic_code(excinfo, "resume_or_start_record_valid_when_invalid")


def test_typecheck_rejects_pointer_backed_resume_from() -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _typecheck_fixture(INVALID_RESUME_POINTER_FIXTURE)

    _assert_diagnostic_code(excinfo, "resume_or_start_resume_path_invalid")


def test_typecheck_rejects_resume_or_start_name_mismatch_with_active_phase(tmp_path: Path) -> None:
    path = _rewrite_fixture(
        VALID_RESUME_FIXTURE,
        replacements=(("(resume-or-start checks", "(resume-or-start wrong-name"),),
        tmp_path=tmp_path,
        filename="resume_or_start_name_mismatch.orc",
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _typecheck_fixture(path)

    _assert_diagnostic_code(excinfo, "phase_scope_name_mismatch")


def test_typecheck_rejects_resume_or_start_without_certified_adapter() -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _typecheck_fixture(INVALID_UNCERTIFIED_RESUME_FIXTURE)

    _assert_diagnostic_code(excinfo, "resume_or_start_contract_invalid")


def test_validate_reusable_phase_state_reuses_record_bundle_without_variant(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    report_path = tmp_path / "artifacts" / "work" / "checks-report.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("checks", encoding="utf-8")
    bundle_path = tmp_path / "checks-state.json"
    bundle_path.write_text(
        json.dumps({"checks_report": "artifacts/work/checks-report.md"}),
        encoding="utf-8",
    )
    expected_sha256 = hashlib.sha256(bundle_path.read_bytes()).hexdigest()
    structured_contract = {
        "fields": [
            {
                "name": "checks_report",
                "json_pointer": "/checks_report",
                "type": "relpath",
                "under": "artifacts/work",
                "must_exist_target": True,
            }
        ]
    }
    payload_path = _write_payload_file(
        tmp_path,
        "validate_ok.json",
        {
            "resume_from": "checks-state.json",
            "target_dsl_version": "2.14",
            "return_type_name": "ChecksResult",
            "structured_contract_kind": "record",
            "expected_contract_fingerprint": _structured_contract_fingerprint(
                structured_contract_kind="record",
                structured_contract=structured_contract,
                return_type_name="ChecksResult",
            ),
            "structured_contract": structured_contract,
            "reusable_variants": [],
            "artifact_requirements": {
                "ChecksResult": [
                    {"field_path": ["checks_report"], "under": "artifacts/work"}
                ]
            },
        },
    )

    exit_code = validate_reusable_phase_state.main(
        [
            "validate_reusable_phase_state",
            payload_path,
        ]
    )

    captured = capsys.readouterr()

    assert exit_code == 0
    assert json.loads(captured.out) == {
        "variant": "REUSE",
        "source_bundle_path": "checks-state.json",
        "source_bundle_sha256": expected_sha256,
    }


def test_validate_reusable_phase_state_rejects_contract_fingerprint_mismatch(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    report_path = tmp_path / "artifacts" / "work" / "checks-report.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("checks", encoding="utf-8")
    bundle_path = tmp_path / "checks-state.json"
    bundle_path.write_text(
        json.dumps({"checks_report": "artifacts/work/checks-report.md"}),
        encoding="utf-8",
    )
    structured_contract = {
        "fields": [
            {
                "name": "checks_report",
                "json_pointer": "/checks_report",
                "type": "relpath",
                "under": "artifacts/work",
                "must_exist_target": True,
            }
        ]
    }
    payload_path = _write_payload_file(
        tmp_path,
        "validate_mismatch.json",
        {
            "resume_from": "checks-state.json",
            "target_dsl_version": "2.14",
            "return_type_name": "ChecksResult",
            "structured_contract_kind": "record",
            "expected_contract_fingerprint": "2.14:ChecksResult:record:expected",
            "structured_contract": structured_contract,
            "reusable_variants": [],
            "artifact_requirements": {
                "ChecksResult": [
                    {"field_path": ["checks_report"], "under": "artifacts/work"}
                ]
            },
        },
    )

    exit_code = validate_reusable_phase_state.main(
        [
            "validate_reusable_phase_state",
            payload_path,
        ]
    )

    captured = capsys.readouterr()

    assert exit_code == 1
    assert json.loads(captured.out) == {
        "error": {"type": "resume_state_contract_fingerprint_mismatch"}
    }


def test_validate_reusable_phase_state_rejects_contract_fingerprint_dsl_version_mismatch(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    report_path = tmp_path / "artifacts" / "work" / "checks-report.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("checks", encoding="utf-8")
    bundle_path = tmp_path / "checks-state.json"
    bundle_path.write_text(
        json.dumps({"checks_report": "artifacts/work/checks-report.md"}),
        encoding="utf-8",
    )
    structured_contract = {
        "fields": [
            {
                "name": "checks_report",
                "json_pointer": "/checks_report",
                "type": "relpath",
                "under": "artifacts/work",
                "must_exist_target": True,
            }
        ]
    }
    payload_path = _write_payload_file(
        tmp_path,
        "validate_version_mismatch.json",
        {
            "resume_from": "checks-state.json",
            "target_dsl_version": "2.14",
            "return_type_name": "ChecksResult",
            "structured_contract_kind": "record",
            "expected_contract_fingerprint": _structured_contract_fingerprint(
                structured_contract_kind="record",
                structured_contract=structured_contract,
                return_type_name="ChecksResult",
            ).replace("2.14:", "999.99:", 1),
            "structured_contract": structured_contract,
            "reusable_variants": [],
            "artifact_requirements": {
                "ChecksResult": [
                    {"field_path": ["checks_report"], "under": "artifacts/work"}
                ]
            },
        },
    )

    exit_code = validate_reusable_phase_state.main(
        [
            "validate_reusable_phase_state",
            payload_path,
        ]
    )

    captured = capsys.readouterr()

    assert exit_code == 1
    assert json.loads(captured.out) == {
        "error": {"type": "resume_state_contract_fingerprint_mismatch"}
    }


def test_validate_reusable_phase_state_rejects_contract_fingerprint_return_type_mismatch(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    report_path = tmp_path / "artifacts" / "work" / "checks-report.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("checks", encoding="utf-8")
    bundle_path = tmp_path / "checks-state.json"
    bundle_path.write_text(
        json.dumps({"checks_report": "artifacts/work/checks-report.md"}),
        encoding="utf-8",
    )
    structured_contract = {
        "fields": [
            {
                "name": "checks_report",
                "json_pointer": "/checks_report",
                "type": "relpath",
                "under": "artifacts/work",
                "must_exist_target": True,
            }
        ]
    }
    payload_path = _write_payload_file(
        tmp_path,
        "validate_return_type_mismatch.json",
        {
            "resume_from": "checks-state.json",
            "target_dsl_version": "2.14",
            "return_type_name": "ChecksResult",
            "structured_contract_kind": "record",
            "expected_contract_fingerprint": _structured_contract_fingerprint(
                structured_contract_kind="record",
                structured_contract=structured_contract,
                return_type_name="ChecksResult",
            ).replace(":ChecksResult:", ":WrongType:", 1),
            "structured_contract": structured_contract,
            "reusable_variants": [],
            "artifact_requirements": {
                "ChecksResult": [
                    {"field_path": ["checks_report"], "under": "artifacts/work"}
                ]
            },
        },
    )

    exit_code = validate_reusable_phase_state.main(
        [
            "validate_reusable_phase_state",
            payload_path,
        ]
    )

    captured = capsys.readouterr()

    assert exit_code == 1
    assert json.loads(captured.out) == {
        "error": {"type": "resume_state_contract_fingerprint_mismatch"}
    }


def test_validate_reusable_phase_state_rejects_pointer_file_authority(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    pointer_path = tmp_path / "pointer.txt"
    pointer_path.write_text("state/phase.json\n", encoding="utf-8")
    structured_contract = {
        "fields": [
            {
                "name": "checks_report",
                "json_pointer": "/checks_report",
                "type": "relpath",
                "under": "artifacts/work",
                "must_exist_target": True,
            }
        ]
    }
    payload_path = _write_payload_file(
        tmp_path,
        "validate_pointer.json",
        {
            "resume_from": "pointer.txt",
            "target_dsl_version": "2.14",
            "return_type_name": "ChecksResult",
            "structured_contract_kind": "record",
            "expected_contract_fingerprint": _structured_contract_fingerprint(
                structured_contract_kind="record",
                structured_contract=structured_contract,
                return_type_name="ChecksResult",
            ),
            "structured_contract": structured_contract,
            "reusable_variants": [],
            "artifact_requirements": {
                "ChecksResult": [
                    {"field_path": ["checks_report"], "under": "artifacts/work"}
                ]
            },
        },
    )

    exit_code = validate_reusable_phase_state.main(
        [
            "validate_reusable_phase_state",
            payload_path,
        ]
    )

    captured = capsys.readouterr()

    assert exit_code == 1
    assert json.loads(captured.out) == {
        "error": {"type": "resume_state_pointer_authority_forbidden"}
    }


def test_validate_reusable_phase_state_rejects_unsafe_required_artifact_path(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    bundle_path = tmp_path / "checks-state.json"
    bundle_path.write_text(
        json.dumps(
            {
                "checks_report": "artifacts/../checks-report.md",
            }
        ),
        encoding="utf-8",
    )
    structured_contract = {
        "fields": [
            {
                "name": "checks_report",
                "json_pointer": "/checks_report",
                "type": "relpath",
                "under": "artifacts/work",
                "must_exist_target": True,
            }
        ]
    }
    payload_path = _write_payload_file(
        tmp_path,
        "validate_unsafe.json",
        {
            "resume_from": "checks-state.json",
            "target_dsl_version": "2.14",
            "return_type_name": "ChecksResult",
            "structured_contract_kind": "record",
            "expected_contract_fingerprint": _structured_contract_fingerprint(
                structured_contract_kind="record",
                structured_contract=structured_contract,
                return_type_name="ChecksResult",
            ),
            "structured_contract": structured_contract,
            "reusable_variants": [],
            "artifact_requirements": {
                "ChecksResult": [
                    {"field_path": ["checks_report"], "under": "artifacts/work"}
                ]
            },
        },
    )

    exit_code = validate_reusable_phase_state.main(
        [
            "validate_reusable_phase_state",
            payload_path,
        ]
    )

    captured = capsys.readouterr()

    assert exit_code == 1
    assert json.loads(captured.out) == {"error": {"type": "resume_state_path_unsafe"}}


def test_validate_reusable_phase_state_rejects_missing_required_artifact_for_reusable_union_variant(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    bundle_path = tmp_path / "plan-gate-state.json"
    bundle_path.write_text(
        json.dumps(
            {
                "variant": "APPROVED",
                "execution_report_path": "artifacts/work/missing-execution.md",
            }
        ),
        encoding="utf-8",
    )
    structured_contract = {
        "discriminant": {
            "name": "variant",
            "json_pointer": "/variant",
            "type": "enum",
            "allowed": ["APPROVED", "BLOCKED"],
        },
        "shared_fields": [],
        "variants": {
            "APPROVED": {
                "fields": [
                    {
                        "name": "execution_report_path",
                        "json_pointer": "/execution_report_path",
                        "type": "relpath",
                        "under": "artifacts/work",
                        "must_exist_target": True,
                    }
                ]
            },
            "BLOCKED": {
                "fields": [
                    {
                        "name": "progress_report_path",
                        "json_pointer": "/progress_report_path",
                        "type": "relpath",
                        "under": "artifacts/work",
                        "must_exist_target": True,
                    },
                    {
                        "name": "blocker_class",
                        "json_pointer": "/blocker_class",
                        "type": "string",
                    },
                ]
            },
        },
    }
    payload_path = _write_payload_file(
        tmp_path,
        "validate_union_missing_artifact.json",
        {
            "resume_from": "plan-gate-state.json",
            "target_dsl_version": "2.14",
            "return_type_name": "PlanGateResult",
            "structured_contract_kind": "union",
            "expected_contract_fingerprint": _structured_contract_fingerprint(
                structured_contract_kind="union",
                structured_contract=structured_contract,
                return_type_name="PlanGateResult",
            ),
            "structured_contract": structured_contract,
            "reusable_variants": ["APPROVED"],
            "artifact_requirements": {
                "APPROVED": [
                    {
                        "field_path": ["execution_report_path"],
                        "under": "artifacts/work",
                    }
                ]
            },
        },
    )

    exit_code = validate_reusable_phase_state.main(
        [
            "validate_reusable_phase_state",
            payload_path,
        ]
    )

    captured = capsys.readouterr()

    assert exit_code == 1
    assert json.loads(captured.out) == {
        "error": {"type": "resume_state_required_artifact_missing"}
    }


def test_validate_reusable_phase_state_rejects_symlinked_external_bundle_path(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    external_root = tmp_path.parent / f"{tmp_path.name}_external"
    external_root.mkdir()
    bundle = {"checks_report": "artifacts/work/checks-report.md"}
    external_bundle_path = external_root / "checks-state.json"
    external_bundle_path.write_text(json.dumps(bundle), encoding="utf-8")
    bundle_link = tmp_path / "checks-state-link.json"
    bundle_link.symlink_to(external_bundle_path)
    structured_contract = {
        "fields": [
            {
                "name": "checks_report",
                "json_pointer": "/checks_report",
                "type": "relpath",
                "under": "artifacts/work",
                "must_exist_target": True,
            }
        ]
    }
    payload_path = _write_payload_file(
        tmp_path,
        "validate_symlinked_external_bundle.json",
        {
            "resume_from": "checks-state-link.json",
            "target_dsl_version": "2.14",
            "return_type_name": "ChecksResult",
            "structured_contract_kind": "record",
            "expected_contract_fingerprint": _structured_contract_fingerprint(
                structured_contract_kind="record",
                structured_contract=structured_contract,
                return_type_name="ChecksResult",
            ),
            "structured_contract": structured_contract,
            "reusable_variants": [],
            "artifact_requirements": {
                "ChecksResult": [
                    {"field_path": ["checks_report"], "under": "artifacts/work"}
                ]
            },
        },
    )

    exit_code = validate_reusable_phase_state.main(
        [
            "validate_reusable_phase_state",
            payload_path,
        ]
    )

    captured = capsys.readouterr()

    assert exit_code == 1
    assert json.loads(captured.out) == {"error": {"type": "resume_state_path_unsafe"}}


def test_load_canonical_phase_result_accepts_bundle_path_contract(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    report_path = tmp_path / "artifacts" / "work" / "checks-report.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("checks", encoding="utf-8")
    bundle_path = tmp_path / "checks-state.json"
    bundle = {"checks_report": "artifacts/work/checks-report.md"}
    bundle_path.write_text(json.dumps(bundle), encoding="utf-8")
    bundle_sha256 = hashlib.sha256(bundle_path.read_bytes()).hexdigest()
    structured_contract = {
        "fields": [
            {
                "name": "checks_report",
                "json_pointer": "/checks_report",
                "type": "relpath",
                "under": "artifacts/work",
                "must_exist_target": True,
            }
        ]
    }

    exit_code = load_canonical_phase_result.main(
        [
            "load_canonical_phase_result",
            json.dumps(
                {
                    "bundle_path": "checks-state.json",
                    "target_dsl_version": "2.14",
                    "return_type_name": "ChecksResult",
                    "expected_contract_fingerprint": _structured_contract_fingerprint(
                        structured_contract_kind="record",
                        structured_contract=structured_contract,
                        return_type_name="ChecksResult",
                    ),
                    "structured_contract_kind": "record",
                    "structured_contract": structured_contract,
                    "source_bundle_sha256": bundle_sha256,
                }
            ),
        ]
    )

    captured = capsys.readouterr()

    assert exit_code == 0
    assert json.loads(captured.out) == bundle


def test_load_canonical_phase_result_rejects_digest_mismatch_before_emit(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    bundle_path = tmp_path / "checks-state.json"
    bundle_path.write_text(
        json.dumps({"checks_report": "artifacts/checks-report.md"}),
        encoding="utf-8",
    )
    structured_contract = {
        "fields": [
            {
                "name": "checks_report",
                "json_pointer": "/checks_report",
                "type": "relpath",
                "under": "artifacts/work",
                "must_exist_target": True,
            }
        ]
    }

    exit_code = load_canonical_phase_result.main(
        [
            "load_canonical_phase_result",
            json.dumps(
                {
                    "bundle_path": "checks-state.json",
                    "target_dsl_version": "2.14",
                    "return_type_name": "ChecksResult",
                    "expected_contract_fingerprint": _structured_contract_fingerprint(
                        structured_contract_kind="record",
                        structured_contract=structured_contract,
                        return_type_name="ChecksResult",
                    ),
                    "structured_contract_kind": "record",
                    "structured_contract": structured_contract,
                    "source_bundle_sha256": "not-the-current-digest",
                }
            ),
        ]
    )

    captured = capsys.readouterr()

    assert exit_code == 1
    assert json.loads(captured.out) == {
        "error": {"type": "resume_state_bundle_mutated_before_load"}
    }


def test_load_canonical_phase_result_rejects_contract_fingerprint_dsl_version_mismatch(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    report_path = tmp_path / "artifacts" / "work" / "checks-report.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("checks", encoding="utf-8")
    bundle_path = tmp_path / "checks-state.json"
    bundle = {"checks_report": "artifacts/work/checks-report.md"}
    bundle_path.write_text(json.dumps(bundle), encoding="utf-8")
    bundle_sha256 = hashlib.sha256(bundle_path.read_bytes()).hexdigest()
    structured_contract = {
        "fields": [
            {
                "name": "checks_report",
                "json_pointer": "/checks_report",
                "type": "relpath",
                "under": "artifacts/work",
                "must_exist_target": True,
            }
        ]
    }

    exit_code = load_canonical_phase_result.main(
        [
            "load_canonical_phase_result",
            json.dumps(
                {
                    "bundle_path": "checks-state.json",
                    "target_dsl_version": "2.14",
                    "return_type_name": "ChecksResult",
                    "expected_contract_fingerprint": _structured_contract_fingerprint(
                        structured_contract_kind="record",
                        structured_contract=structured_contract,
                        return_type_name="ChecksResult",
                    ).replace("2.14:", "999.99:", 1),
                    "structured_contract_kind": "record",
                    "structured_contract": structured_contract,
                    "source_bundle_sha256": bundle_sha256,
                }
            ),
        ]
    )

    captured = capsys.readouterr()

    assert exit_code == 1
    assert json.loads(captured.out) == {
        "error": {"type": "resume_state_contract_fingerprint_mismatch"}
    }


def test_load_canonical_phase_result_rejects_contract_fingerprint_return_type_mismatch(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    report_path = tmp_path / "artifacts" / "work" / "checks-report.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("checks", encoding="utf-8")
    bundle_path = tmp_path / "checks-state.json"
    bundle = {"checks_report": "artifacts/work/checks-report.md"}
    bundle_path.write_text(json.dumps(bundle), encoding="utf-8")
    bundle_sha256 = hashlib.sha256(bundle_path.read_bytes()).hexdigest()
    structured_contract = {
        "fields": [
            {
                "name": "checks_report",
                "json_pointer": "/checks_report",
                "type": "relpath",
                "under": "artifacts/work",
                "must_exist_target": True,
            }
        ]
    }

    exit_code = load_canonical_phase_result.main(
        [
            "load_canonical_phase_result",
            json.dumps(
                {
                    "bundle_path": "checks-state.json",
                    "target_dsl_version": "2.14",
                    "return_type_name": "ChecksResult",
                    "expected_contract_fingerprint": _structured_contract_fingerprint(
                        structured_contract_kind="record",
                        structured_contract=structured_contract,
                        return_type_name="ChecksResult",
                    ).replace(":ChecksResult:", ":WrongType:", 1),
                    "structured_contract_kind": "record",
                    "structured_contract": structured_contract,
                    "source_bundle_sha256": bundle_sha256,
                }
            ),
        ]
    )

    captured = capsys.readouterr()

    assert exit_code == 1
    assert json.loads(captured.out) == {
        "error": {"type": "resume_state_contract_fingerprint_mismatch"}
    }


def test_load_canonical_phase_result_rejects_unsafe_bundle_path_with_stable_error_code(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    exit_code = load_canonical_phase_result.main(
        [
            "load_canonical_phase_result",
            json.dumps(
                {
                    "bundle_path": "../unsafe.json",
                    "target_dsl_version": "2.14",
                    "return_type_name": "ChecksResult",
                    "expected_contract_fingerprint": _structured_contract_fingerprint(
                        structured_contract_kind="record",
                        structured_contract={
                            "fields": [
                                {
                                    "name": "checks_report",
                                    "json_pointer": "/checks_report",
                                    "type": "relpath",
                                    "under": "artifacts/work",
                                    "must_exist_target": True,
                                }
                            ]
                        },
                        return_type_name="ChecksResult",
                    ),
                    "structured_contract_kind": "record",
                    "structured_contract": {
                        "fields": [
                            {
                                "name": "checks_report",
                                "json_pointer": "/checks_report",
                                "type": "relpath",
                                "under": "artifacts/work",
                                "must_exist_target": True,
                            }
                        ]
                    },
                    "source_bundle_sha256": "unused",
                }
            ),
        ]
    )

    captured = capsys.readouterr()

    assert exit_code == 1
    assert json.loads(captured.out) == {"error": {"type": "resume_state_path_unsafe"}}


def test_load_canonical_phase_result_rejects_malformed_bundle_with_stable_error_code(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    bundle_path = tmp_path / "checks-state.json"
    bundle_path.write_text("{bad", encoding="utf-8")
    actual_digest = hashlib.sha256(bundle_path.read_bytes()).hexdigest()

    exit_code = load_canonical_phase_result.main(
        [
            "load_canonical_phase_result",
            json.dumps(
                {
                    "bundle_path": "checks-state.json",
                    "target_dsl_version": "2.14",
                    "return_type_name": "ChecksResult",
                    "expected_contract_fingerprint": _structured_contract_fingerprint(
                        structured_contract_kind="record",
                        structured_contract={
                            "fields": [
                                {
                                    "name": "checks_report",
                                    "json_pointer": "/checks_report",
                                    "type": "relpath",
                                    "under": "artifacts/work",
                                    "must_exist_target": True,
                                }
                            ]
                        },
                        return_type_name="ChecksResult",
                    ),
                    "structured_contract_kind": "record",
                    "structured_contract": {
                        "fields": [
                            {
                                "name": "checks_report",
                                "json_pointer": "/checks_report",
                                "type": "relpath",
                                "under": "artifacts/work",
                                "must_exist_target": True,
                            }
                        ]
                    },
                    "source_bundle_sha256": actual_digest,
                }
            ),
        ]
    )

    captured = capsys.readouterr()

    assert exit_code == 1
    assert json.loads(captured.out) == {
        "error": {"type": "resume_state_loader_schema_invalid"}
    }


def test_load_canonical_phase_result_rejects_symlinked_external_bundle_path(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    external_root = tmp_path.parent / f"{tmp_path.name}_external"
    external_root.mkdir()
    bundle = {"checks_report": "artifacts/work/checks-report.md"}
    external_bundle_path = external_root / "checks-state.json"
    external_bundle_path.write_text(json.dumps(bundle), encoding="utf-8")
    bundle_link = tmp_path / "checks-state-link.json"
    bundle_link.symlink_to(external_bundle_path)

    exit_code = load_canonical_phase_result.main(
        [
            "load_canonical_phase_result",
            json.dumps(
                {
                    "bundle_path": "checks-state-link.json",
                    "target_dsl_version": "2.14",
                    "return_type_name": "ChecksResult",
                    "expected_contract_fingerprint": _structured_contract_fingerprint(
                        structured_contract_kind="record",
                        structured_contract={
                            "fields": [
                                {
                                    "name": "checks_report",
                                    "json_pointer": "/checks_report",
                                    "type": "relpath",
                                    "under": "artifacts/work",
                                    "must_exist_target": True,
                                }
                            ]
                        },
                        return_type_name="ChecksResult",
                    ),
                    "structured_contract_kind": "record",
                    "structured_contract": {
                        "fields": [
                            {
                                "name": "checks_report",
                                "json_pointer": "/checks_report",
                                "type": "relpath",
                                "under": "artifacts/work",
                                "must_exist_target": True,
                            }
                        ]
                    },
                    "source_bundle_sha256": hashlib.sha256(
                        bundle_link.read_bytes()
                    ).hexdigest(),
                }
            ),
        ]
    )

    captured = capsys.readouterr()

    assert exit_code == 1
    assert json.loads(captured.out) == {"error": {"type": "resume_state_path_unsafe"}}
