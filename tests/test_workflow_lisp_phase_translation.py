from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from orchestrator.state import StateManager
from orchestrator.workflow.executor import WorkflowExecutor
from orchestrator.workflow_lisp.compiler import (
    _definition_only_syntax_module,
    _validate_definition_module,
    compile_stage1_module,
    compile_stage3_module,
)
from orchestrator.workflow_lisp.definitions import elaborate_definition_module
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from orchestrator.workflow_lisp.reader import read_sexpr_file, read_sexpr_text
from orchestrator.workflow_lisp.syntax import SyntaxNode, build_syntax_module
from orchestrator.workflow_lisp.type_env import FrontendTypeEnvironment
from orchestrator.workflow_lisp.workflows import (
    ExternEnvironment,
    PromptExtern,
    ProviderExtern,
    build_workflow_catalog,
    elaborate_workflow_definitions,
    typecheck_workflow_definitions,
)
from orchestrator.providers.executor import ProviderExecutor


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "workflow_lisp"
VALID_FIXTURE = FIXTURES / "valid" / "neurips_implementation_attempt.orc"
INVALID_TARGET_FIXTURE = FIXTURES / "invalid" / "phase_target_outside_with_phase.orc"
INVALID_CONTEXT_FIXTURE = FIXTURES / "invalid" / "phase_context_invalid.orc"


def _build_syntax_module(path: Path):
    return build_syntax_module(read_sexpr_file(path))


def _compile_definition_module(path: Path):
    syntax_module = _build_syntax_module(path)
    module = elaborate_definition_module(_definition_only_syntax_module(syntax_module))
    _validate_definition_module(module)
    return module


def _type_env(path: Path = VALID_FIXTURE) -> FrontendTypeEnvironment:
    return FrontendTypeEnvironment.from_module(_compile_definition_module(path))


def _extern_environment() -> ExternEnvironment:
    return ExternEnvironment(
        bindings_by_name={
            "providers.execute": ProviderExtern(
                name="providers.execute",
                provider_id="fake",
            ),
            "prompts.implementation.execute": PromptExtern(
                name="prompts.implementation.execute",
                asset_file="prompts/implementation/execute.md",
            ),
        }
    )


def _assert_diagnostic_code(excinfo: pytest.ExceptionInfo[LispFrontendCompileError], code: str) -> None:
    assert excinfo.value.diagnostics[0].code == code


def _write_module(path: Path, body: str) -> Path:
    path.write_text(body, encoding="utf-8")
    return path


def _expression_syntax(source: str) -> SyntaxNode:
    parse_tree = read_sexpr_text(source, source_path="inline_phase_translation.orc")
    assert len(parse_tree.items) == 1
    datum = parse_tree.items[0]
    return SyntaxNode(
        datum=datum,
        span=datum.span,
        module_path="inline_phase_translation.orc",
        form_path=("workflow-lisp", "phase-translation-test"),
    )


def _typecheck_fixture(path: Path):
    module = _compile_definition_module(path)
    type_env = FrontendTypeEnvironment.from_module(module)
    syntax_module = _build_syntax_module(path)
    workflow_defs = elaborate_workflow_definitions(syntax_module)
    workflow_catalog = build_workflow_catalog(module, workflow_defs, type_env)
    return typecheck_workflow_definitions(
        workflow_defs,
        type_env=type_env,
        workflow_catalog=workflow_catalog,
        extern_environment=_extern_environment(),
    )


def _runtime_bundle_payload(mode: str) -> dict[str, object]:
    if mode == "completed":
        return {
            "variant": "COMPLETED",
            "implementation_state": "COMPLETED",
            "execution_report_path": "artifacts/work/execution_report.md",
        }
    if mode == "blocked":
        return {
            "variant": "BLOCKED",
            "implementation_state": "BLOCKED",
            "progress_report_path": "artifacts/work/progress_report.md",
            "blocker_class": "missing_resource",
        }
    raise AssertionError(f"unexpected mode: {mode}")


def _compile_and_execute_phase_fixture(workspace: Path, *, mode: str) -> tuple[dict, Path]:
    (workspace / "docs" / "design").mkdir(parents=True, exist_ok=True)
    (workspace / "docs" / "plans").mkdir(parents=True, exist_ok=True)
    (workspace / "state").mkdir(parents=True, exist_ok=True)
    (workspace / "docs" / "design" / "workflow_lisp_frontend_specification.md").write_text(
        "# design\n",
        encoding="utf-8",
    )
    (workspace / "docs" / "plans" / "implementation_plan.md").write_text("# plan\n", encoding="utf-8")
    (workspace / "state" / "fake_provider_scenario.json").write_text(
        json.dumps({"mode": mode}, indent=2) + "\n",
        encoding="utf-8",
    )

    compile_result = compile_stage3_module(
        VALID_FIXTURE,
        provider_externs={"providers.execute": "fake"},
        prompt_externs={"prompts.implementation.execute": "prompts/implementation/execute.md"},
        validate_shared=True,
        workspace_root=workspace,
    )
    bundle = compile_result.validated_bundles["run-implementation-attempt"]
    state_manager = StateManager(workspace=workspace, run_id=f"phase-translation-{mode}")
    state_manager.initialize(
        VALID_FIXTURE.as_posix(),
        bound_inputs={
            "phase-ctx__implementation_state_bundle_path": "artifacts/work/implementation_state.json",
            "phase-ctx__execution_report_target": "artifacts/work/execution_report.md",
            "phase-ctx__progress_report_target": "artifacts/work/progress_report.md",
            "inputs__design": "docs/design/workflow_lisp_frontend_specification.md",
            "inputs__plan": "docs/plans/implementation_plan.md",
        },
    )
    executor = WorkflowExecutor(bundle, workspace, state_manager, retry_delay_ms=0)

    def _prepare_invocation(_self, *args, **kwargs):
        return SimpleNamespace(input_mode="stdin", prompt=kwargs.get("prompt_content", "")), None

    def _execute(_self, _invocation, **kwargs):
        subprocess.run(
            [sys.executable, str(ROOT / "tests" / "fixtures" / "bin" / "fake_provider.py")],
            input=b"Primitive implementation outcome oracle\n",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=workspace,
            check=True,
        )
        bundle_path = workspace / "artifacts" / "work" / "implementation_state.json"
        bundle_path.parent.mkdir(parents=True, exist_ok=True)
        bundle_path.write_text(
            json.dumps(_runtime_bundle_payload(mode), indent=2) + "\n",
            encoding="utf-8",
        )
        return SimpleNamespace(
            exit_code=0,
            stdout=b"ok",
            stderr=b"",
            duration_ms=1,
            error=None,
            missing_placeholders=None,
            invalid_prompt_placeholder=False,
            raw_stdout=None,
            normalized_stdout=None,
            provider_session=None,
        )

    with patch.object(ProviderExecutor, "prepare_invocation", _prepare_invocation), patch.object(
        ProviderExecutor, "execute", _execute
    ):
        state = executor.execute()

    return state, workspace / "artifacts" / "work" / "implementation_state.json"


def test_elaborate_phase_translation_fixture_builds_with_phase_and_phase_target_nodes() -> None:
    syntax_module = _build_syntax_module(VALID_FIXTURE)
    workflow_def = elaborate_workflow_definitions(syntax_module)[0]
    from orchestrator.workflow_lisp.expressions import elaborate_expression

    body = elaborate_expression(
        workflow_def.body,
        bound_names=frozenset(param.name for param in workflow_def.params),
    )

    assert type(body).__name__ == "WithPhaseExpr"
    assert body.phase_name == "implementation"
    assert type(body.body).__name__ == "LetStarExpr"
    attempt_expr = body.body.bindings[0][1]
    assert type(attempt_expr).__name__ == "ProviderResultExpr"
    assert [type(expr).__name__ for expr in attempt_expr.inputs] == [
        "FieldAccessExpr",
        "FieldAccessExpr",
        "PhaseTargetExpr",
        "PhaseTargetExpr",
    ]
    assert [expr.target_name for expr in attempt_expr.inputs[2:]] == [
        "execution-report",
        "progress-report",
    ]


def test_compile_stage3_module_keeps_hand_authored_phase_fixture_without_macro_frames(tmp_path: Path) -> None:
    result = compile_stage3_module(
        VALID_FIXTURE,
        provider_externs={"providers.execute": "fake"},
        prompt_externs={"prompts.implementation.execute": "prompts/implementation/execute.md"},
        validate_shared=False,
        workspace_root=tmp_path,
    )

    workflow = result.lowered_workflows[0]
    origin = workflow.origin_map.step_spans["run-implementation-attempt__attempt"]

    assert origin.expansion_stack == ()


def test_typecheck_rejects_phase_target_outside_with_phase() -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _typecheck_fixture(INVALID_TARGET_FIXTURE)

    _assert_diagnostic_code(excinfo, "phase_target_outside_with_phase")


def test_typecheck_rejects_invalid_phase_context_record() -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _typecheck_fixture(INVALID_CONTEXT_FIXTURE)

    _assert_diagnostic_code(excinfo, "phase_context_invalid")


def test_typecheck_rejects_phase_context_report_targets_that_are_not_target_paths(tmp_path: Path) -> None:
    path = _write_module(
        tmp_path / "phase_context_target_contract_invalid.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
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
                "    (execution_report_target WorkReport)",
                "    (progress_report_target WorkReport))",
                "  (defworkflow invalid-phase-target-contracts",
                "    ((phase-ctx ImplementationAttemptPhaseCtx)",
                "     (inputs ImplementationAttemptInputs))",
                "    -> ImplementationAttemptInputs",
                "    (with-phase phase-ctx implementation",
                "      inputs)))",
            ]
        ),
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _typecheck_fixture(path)

    _assert_diagnostic_code(excinfo, "phase_context_invalid")


def test_typecheck_rejects_phase_target_unknown(tmp_path: Path) -> None:
    path = _write_module(
        tmp_path / "phase_target_unknown.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
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
                "  (defrecord ImplementationAttemptPhaseCtx",
                "    (implementation_state_bundle_path ImplementationStateBundlePath)",
                "    (execution_report_target WorkReportTarget)",
                "    (progress_report_target WorkReportTarget))",
                "  (defrecord ReportResult",
                "    (report WorkReport))",
                "  (defworkflow invalid-phase-target",
                "    ((phase-ctx ImplementationAttemptPhaseCtx))",
                "    -> ReportResult",
                "    (with-phase phase-ctx implementation",
                "      (record ReportResult",
                "        :report (phase-target archive-report)))))",
            ]
        ),
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _typecheck_fixture(path)

    _assert_diagnostic_code(excinfo, "phase_target_unknown")


@pytest.mark.parametrize(
    "source",
    [
        '(phase-target "execution-report")',
        "(phase-target)",
        "(phase-target execution-report progress-report)",
        "(phase-target (execution-report))",
    ],
)
def test_elaborate_phase_target_rejects_malformed_target_names(source: str) -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        from orchestrator.workflow_lisp.expressions import elaborate_expression

        elaborate_expression(_expression_syntax(source), bound_names=frozenset())

    _assert_diagnostic_code(excinfo, "phase_target_name_invalid")


def test_typecheck_rejects_nested_with_phase(tmp_path: Path) -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _typecheck_fixture(
            _write_module(
                tmp_path / "tmp_nested_with_phase.orc",
                "\n".join(
                    [
                        "(workflow-lisp",
                        '  (:language "0.1")',
                        '  (:target-dsl "2.14")',
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
                        "  (defworkflow nested-phase",
                        "    ((phase-ctx ImplementationAttemptPhaseCtx)",
                        "     (inputs ImplementationAttemptInputs))",
                        "    -> ImplementationAttemptInputs",
                        "    (with-phase phase-ctx implementation",
                        "      (with-phase phase-ctx implementation",
                        "        inputs))))",
                    ]
                ),
            )
        )

    _assert_diagnostic_code(excinfo, "phase_scope_nested_unsupported")


def test_typecheck_rejects_non_implementation_phase_name_for_bounded_slice(tmp_path: Path) -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _typecheck_fixture(
            _write_module(
                tmp_path / "phase_name_invalid.orc",
                "\n".join(
                    [
                        "(workflow-lisp",
                        '  (:language "0.1")',
                        '  (:target-dsl "2.14")',
                        "  (defenum BlockerClass",
                        "    missing_resource)",
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
                        "  (defrecord ImplementationAttemptSurfaceResult",
                        "    (implementation_state ImplementationStateTag)",
                        "    (implementation_state_bundle_path ImplementationStateBundlePath))",
                        "  (defworkflow invalid-phase-name",
                        "    ((phase-ctx ImplementationAttemptPhaseCtx)",
                        "     (inputs ImplementationAttemptInputs))",
                        "    -> ImplementationAttemptSurfaceResult",
                        "    (with-phase phase-ctx review",
                        "      (let* ((attempt",
                        "               (provider-result providers.execute",
                        "                 :prompt prompts.implementation.execute",
                        "                 :inputs (inputs.design",
                        "                          inputs.plan",
                        "                          (phase-target execution-report)",
                        "                          (phase-target progress-report))",
                        "                 :returns ImplementationAttempt)))",
                        "        (match attempt",
                        "          ((COMPLETED completed)",
                        "           (record ImplementationAttemptSurfaceResult",
                        "             :implementation_state completed.implementation_state",
                        "             :implementation_state_bundle_path",
                        "               phase-ctx.implementation_state_bundle_path))",
                        "          ((BLOCKED blocked)",
                        "           (record ImplementationAttemptSurfaceResult",
                        "             :implementation_state blocked.implementation_state",
                        "             :implementation_state_bundle_path",
                        "               phase-ctx.implementation_state_bundle_path)))))))",
                    ]
                ),
            )
        )

    _assert_diagnostic_code(excinfo, "phase_context_invalid")


def test_typecheck_rejects_non_implementation_attempt_provider_result_inside_with_phase(tmp_path: Path) -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _typecheck_fixture(
            _write_module(
                tmp_path / "phase_provider_result_scope_leak.orc",
                "\n".join(
                    [
                        "(workflow-lisp",
                        '  (:language "0.1")',
                        '  (:target-dsl "2.14")',
                        "  (defpath DesignDocPath",
                        "    :kind relpath",
                        '    :under "docs/design"',
                        "    :must-exist true)",
                        "  (defpath PlanDocPath",
                        "    :kind relpath",
                        '    :under "docs/plans"',
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
                        "  (defunion OtherAttempt",
                        "    (COMPLETED",
                        "      (execution_report_path WorkReportTarget))",
                        "    (BLOCKED",
                        "      (progress_report_path WorkReportTarget)))",
                        "  (defworkflow invalid-phase-provider-result",
                        "    ((phase-ctx ImplementationAttemptPhaseCtx)",
                        "     (inputs ImplementationAttemptInputs))",
                        "    -> ImplementationAttemptInputs",
                        "    (with-phase phase-ctx implementation",
                        "      (let* ((attempt",
                        "               (provider-result providers.execute",
                        "                 :prompt prompts.implementation.execute",
                        "                 :inputs (inputs.design",
                        "                          inputs.plan",
                        "                          (phase-target execution-report)",
                        "                          (phase-target progress-report))",
                        "                 :returns OtherAttempt)))",
                        "        inputs))))",
                    ]
                ),
            )
        )

    _assert_diagnostic_code(excinfo, "provider_result_return_type_invalid")


def test_typecheck_phase_translation_fixture_keeps_internal_union_and_externs() -> None:
    typed_workflow = _typecheck_fixture(VALID_FIXTURE)[0]

    assert typed_workflow.definition.name == "run-implementation-attempt"
    assert [param_name for param_name, _ in typed_workflow.signature.params] == ["phase-ctx", "inputs"]
    assert typed_workflow.signature.return_type_ref.name == "ImplementationAttemptSurfaceResult"
    assert typed_workflow.typed_body.type_ref == typed_workflow.signature.return_type_ref


def test_runtime_completed_phase_translation_matches_oracle_shape(tmp_path: Path) -> None:
    state, bundle_path = _compile_and_execute_phase_fixture(tmp_path, mode="completed")

    assert state["status"] == "completed"
    assert state["workflow_outputs"]["return__implementation_state"] == "COMPLETED"
    assert state["workflow_outputs"]["return__implementation_state_bundle_path"] == (
        "artifacts/work/implementation_state.json"
    )
    assert bundle_path.is_file()

    actual_bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    expected_bundle = json.loads(
        (ROOT / "tests" / "fixtures" / "v214_primitives" / "implementation_oracle" / "expected" / "completed.json")
        .read_text(encoding="utf-8")
    )["files"]["state/oracle/implementation_state.json"]["json"]
    assert actual_bundle["implementation_state"] == "COMPLETED"
    assert actual_bundle["execution_report_path"] == "artifacts/work/execution_report.md"
    assert "blocker_class" not in actual_bundle
    assert {key: actual_bundle[key] for key in expected_bundle} == expected_bundle


def test_runtime_blocked_phase_translation_matches_oracle_shape(tmp_path: Path) -> None:
    state, bundle_path = _compile_and_execute_phase_fixture(tmp_path, mode="blocked")

    assert state["status"] == "completed"
    assert state["workflow_outputs"]["return__implementation_state"] == "BLOCKED"
    assert state["workflow_outputs"]["return__implementation_state_bundle_path"] == (
        "artifacts/work/implementation_state.json"
    )
    assert bundle_path.is_file()

    actual_bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    expected_bundle = json.loads(
        (ROOT / "tests" / "fixtures" / "v214_primitives" / "implementation_oracle" / "expected" / "blocked.json")
        .read_text(encoding="utf-8")
    )["files"]["state/oracle/implementation_state.json"]["json"]
    assert actual_bundle["implementation_state"] == "BLOCKED"
    assert actual_bundle["progress_report_path"] == "artifacts/work/progress_report.md"
    assert actual_bundle["blocker_class"] == "missing_resource"
    assert {key: actual_bundle[key] for key in expected_bundle} == expected_bundle
