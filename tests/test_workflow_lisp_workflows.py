from pathlib import Path

import pytest

from orchestrator.workflow_lisp.compiler import compile_stage1_module
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from orchestrator.workflow_lisp.expressions import (
    CallExpr,
    CommandResultExpr,
    ProviderResultExpr,
    elaborate_expression,
)
from orchestrator.workflow_lisp.reader import read_sexpr_file
from orchestrator.workflow_lisp.syntax import SyntaxNode, WorkflowLispSyntaxModule, build_syntax_module
from orchestrator.workflow_lisp.type_env import FrontendTypeEnvironment, PrimitiveTypeRef, UnionTypeRef
from orchestrator.workflow_lisp.workflows import (
    WorkflowCatalog,
    WorkflowDef,
    build_workflow_catalog,
    elaborate_workflow_definitions,
    typecheck_workflow_definitions,
)


FIXTURES = Path(__file__).parent / "fixtures" / "workflow_lisp"
TYPE_FIXTURE = FIXTURES / "valid" / "type_definitions.orc"
FORM_PATH = ("workflow-lisp", "workflow-expression-test")


def _build_syntax_module(path: Path) -> WorkflowLispSyntaxModule:
    return build_syntax_module(read_sexpr_file(path))


def _build_type_env() -> FrontendTypeEnvironment:
    return FrontendTypeEnvironment.from_module(compile_stage1_module(TYPE_FIXTURE))


def _expression_syntax(source: str, *, form_path: tuple[str, ...] = FORM_PATH) -> SyntaxNode:
    parse_tree = read_sexpr_file(FIXTURES / "valid" / "minimal_module.orc")
    del parse_tree
    from orchestrator.workflow_lisp.reader import read_sexpr_text

    expr_tree = read_sexpr_text(source, source_path="inline_workflow_expression.orc")
    assert len(expr_tree.items) == 1
    datum = expr_tree.items[0]
    return SyntaxNode(
        datum=datum,
        span=datum.span,
        module_path="inline_workflow_expression.orc",
        form_path=form_path,
    )


def _assert_diagnostic_code(excinfo: pytest.ExceptionInfo[LispFrontendCompileError], code: str) -> None:
    assert excinfo.value.diagnostics[0].code == code


def test_elaborate_workflow_definitions_builds_same_file_catalog() -> None:
    syntax_module = _build_syntax_module(FIXTURES / "valid" / "workflow_definitions.orc")

    workflow_defs = elaborate_workflow_definitions(syntax_module)
    workflow_catalog = build_workflow_catalog(
        compile_stage1_module(TYPE_FIXTURE),
        workflow_defs,
        _build_type_env(),
    )

    assert [workflow_def.name for workflow_def in workflow_defs] == ["entry", "helper"]
    assert all(isinstance(workflow_def, WorkflowDef) for workflow_def in workflow_defs)
    assert isinstance(workflow_catalog, WorkflowCatalog)
    assert tuple(workflow_catalog.signatures_by_name) == ("entry", "helper")

    entry_signature = workflow_catalog.signatures_by_name["entry"]
    helper_signature = workflow_catalog.signatures_by_name["helper"]

    assert [param_name for param_name, _ in entry_signature.params] == [
        "provider",
        "prompt",
        "input",
        "report_path",
    ]
    assert isinstance(entry_signature.params[0][1], PrimitiveTypeRef)
    assert entry_signature.params[0][1].name == "Provider"
    assert isinstance(entry_signature.return_type_ref, UnionTypeRef)
    assert helper_signature.return_type_ref == entry_signature.return_type_ref


def test_build_workflow_catalog_rejects_duplicate_workflow_names() -> None:
    syntax_module = _build_syntax_module(
        FIXTURES / "invalid" / "duplicate_workflow_definition.orc"
    )
    workflow_defs = elaborate_workflow_definitions(syntax_module)

    with pytest.raises(LispFrontendCompileError) as excinfo:
        build_workflow_catalog(
            compile_stage1_module(TYPE_FIXTURE),
            workflow_defs,
            _build_type_env(),
        )

    _assert_diagnostic_code(excinfo, "workflow_definition_duplicate")


def test_typecheck_workflow_definitions_rejects_duplicate_parameter_names() -> None:
    syntax_module = _build_syntax_module(FIXTURES / "invalid" / "duplicate_workflow_param.orc")
    workflow_defs = elaborate_workflow_definitions(syntax_module)

    with pytest.raises(LispFrontendCompileError) as excinfo:
        typecheck_workflow_definitions(
            workflow_defs,
            type_env=_build_type_env(),
            workflow_catalog=build_workflow_catalog(
                compile_stage1_module(TYPE_FIXTURE),
                workflow_defs,
                _build_type_env(),
            ),
        )

    _assert_diagnostic_code(excinfo, "workflow_param_duplicate")


def test_typecheck_workflow_definitions_requires_record_or_union_return_type() -> None:
    syntax_module = _build_syntax_module(FIXTURES / "invalid" / "workflow_return_type_invalid.orc")
    workflow_defs = elaborate_workflow_definitions(syntax_module)

    with pytest.raises(LispFrontendCompileError) as excinfo:
        build_workflow_catalog(
            compile_stage1_module(TYPE_FIXTURE),
            workflow_defs,
            _build_type_env(),
        )

    _assert_diagnostic_code(excinfo, "workflow_return_type_invalid")


def test_elaborate_expression_supports_call_provider_result_and_command_result() -> None:
    call_expr = elaborate_expression(
        _expression_syntax(
            "(call helper :provider provider :prompt prompt :input input :report_path report_path)"
        ),
        bound_names=frozenset({"provider", "prompt", "input", "report_path"}),
    )
    provider_expr = elaborate_expression(
        _expression_syntax(
            "(provider-result provider "
            ":prompt prompt "
            ":inputs (input report_path) "
            ":returns ImplementationState)"
        ),
        bound_names=frozenset({"provider", "prompt", "input", "report_path"}),
    )
    command_expr = elaborate_expression(
        _expression_syntax(
            '(command-result run_checks :argv ("python" "scripts/run_checks.py" report_path) :returns ChecksResult)'
        ),
        bound_names=frozenset({"report_path"}),
    )

    assert isinstance(call_expr, CallExpr)
    assert call_expr.callee_name == "helper"
    assert [binding_name for binding_name, _ in call_expr.bindings] == [
        "provider",
        "prompt",
        "input",
        "report_path",
    ]

    assert isinstance(provider_expr, ProviderResultExpr)
    assert provider_expr.returns_type_name == "ImplementationState"
    assert len(provider_expr.inputs) == 2

    assert isinstance(command_expr, CommandResultExpr)
    assert command_expr.step_name == "run_checks"
    assert command_expr.returns_type_name == "ChecksResult"
    assert len(command_expr.argv) == 3


def test_elaborate_expression_rejects_malformed_effectful_forms() -> None:
    with pytest.raises(LispFrontendCompileError) as malformed_call:
        elaborate_expression(
            _expression_syntax("(call helper provider)"),
            bound_names=frozenset({"provider"}),
        )
    _assert_diagnostic_code(malformed_call, "frontend_parse_error")

    with pytest.raises(LispFrontendCompileError) as malformed_provider:
        elaborate_expression(
            _expression_syntax("(provider-result provider :inputs input :returns ImplementationState)"),
            bound_names=frozenset({"provider", "input"}),
        )
    _assert_diagnostic_code(malformed_provider, "frontend_parse_error")

    with pytest.raises(LispFrontendCompileError) as malformed_command:
        elaborate_expression(
            _expression_syntax("(command-result run_checks :argv report_path :returns ChecksResult)"),
            bound_names=frozenset({"report_path"}),
        )
    _assert_diagnostic_code(malformed_command, "frontend_parse_error")
