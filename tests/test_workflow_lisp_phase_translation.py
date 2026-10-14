from __future__ import annotations

from pathlib import Path

import pytest

from orchestrator.workflow_lisp.compiler import _definition_only_syntax_module, _validate_definition_module
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
