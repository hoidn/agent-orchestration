from pathlib import Path

import pytest

from orchestrator.workflow_lisp.compiler import PRELUDE_TYPE_NAMES, compile_stage1_module
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from orchestrator.workflow_lisp.expressions import (
    FieldAccessExpr,
    LetStarExpr,
    LiteralExpr,
    MatchExpr,
    NameExpr,
    RecordExpr,
    elaborate_expression,
)
from orchestrator.workflow_lisp.reader import read_sexpr_text
from orchestrator.workflow_lisp.reader import read_sexpr_file
from orchestrator.workflow_lisp.syntax import SyntaxNode, build_syntax_module
from orchestrator.workflow_lisp.type_env import (
    FrontendTypeEnvironment,
    PathTypeRef,
    PrimitiveTypeRef,
    RecordTypeRef,
    UnionTypeRef,
    VariantCaseTypeRef,
)
from orchestrator.workflow_lisp.typecheck import typecheck_expression


FIXTURES = Path(__file__).parent / "fixtures" / "workflow_lisp"
TYPE_FIXTURE = FIXTURES / "valid" / "type_definitions.orc"
FORM_PATH = ("workflow-lisp", "expression-test")


def _build_type_env() -> FrontendTypeEnvironment:
    return FrontendTypeEnvironment.from_module(compile_stage1_module(TYPE_FIXTURE))


def _expression_syntax(source: str, *, form_path: tuple[str, ...] = FORM_PATH) -> SyntaxNode:
    parse_tree = read_sexpr_text(source, source_path="inline_expression.orc")
    assert len(parse_tree.items) == 1
    datum = parse_tree.items[0]
    return SyntaxNode(
        datum=datum,
        span=datum.span,
        module_path="inline_expression.orc",
        form_path=form_path,
    )


def _assert_diagnostic_code(excinfo: pytest.ExceptionInfo[LispFrontendCompileError], code: str) -> None:
    assert excinfo.value.diagnostics[0].code == code


def test_frontend_type_environment_resolves_stage1_definitions() -> None:
    type_env = _build_type_env()
    syntax = _expression_syntax('"probe"')

    for prelude_name in PRELUDE_TYPE_NAMES:
        resolved = type_env.resolve_type(prelude_name, span=syntax.span, form_path=syntax.form_path)
        assert isinstance(resolved, PrimitiveTypeRef)
        assert resolved.name == prelude_name

    checks_result = type_env.resolve_type("ChecksResult", span=syntax.span, form_path=syntax.form_path)
    implementation_state = type_env.resolve_type(
        "ImplementationState",
        span=syntax.span,
        form_path=syntax.form_path,
    )
    work_report = type_env.resolve_type("WorkReport", span=syntax.span, form_path=syntax.form_path)

    assert isinstance(checks_result, RecordTypeRef)
    assert isinstance(implementation_state, UnionTypeRef)
    assert isinstance(work_report, PathTypeRef)


def test_frontend_type_environment_exposes_union_variant_payloads() -> None:
    type_env = _build_type_env()
    syntax = _expression_syntax('"probe"')
    implementation_state = type_env.resolve_type(
        "ImplementationState",
        span=syntax.span,
        form_path=syntax.form_path,
    )
    assert isinstance(implementation_state, UnionTypeRef)

    blocked = type_env.union_variant(
        implementation_state,
        "BLOCKED",
        span=syntax.span,
        form_path=syntax.form_path,
    )
    progress_report = type_env.record_field(
        blocked,
        "progress_report",
        span=syntax.span,
        form_path=syntax.form_path,
    )
    blocker_class = type_env.record_field(
        blocked,
        "blocker_class",
        span=syntax.span,
        form_path=syntax.form_path,
    )

    assert isinstance(blocked, VariantCaseTypeRef)
    assert blocked.union_name == "ImplementationState"
    assert blocked.variant_name == "BLOCKED"
    assert [field.name for field in blocked.definition.fields] == [
        "progress_report",
        "blocker_class",
    ]
    assert isinstance(progress_report, PathTypeRef)
    assert progress_report.name == "WorkReport"
    assert isinstance(blocker_class, PrimitiveTypeRef)
    assert blocker_class.name == "BlockerClass"


def test_elaborate_expression_handles_literals_names_records_and_letstar() -> None:
    literal = elaborate_expression(_expression_syntax('"ok"'), bound_names=frozenset())
    integer = elaborate_expression(_expression_syntax("7"), bound_names=frozenset())
    boolean = elaborate_expression(_expression_syntax("true"), bound_names=frozenset())
    record = elaborate_expression(
        _expression_syntax('(record ChecksResult :status "ok" :report report-path)'),
        bound_names=frozenset({"report-path"}),
    )
    letstar = elaborate_expression(
        _expression_syntax("(let* ((first report-path) (second first)) second)"),
        bound_names=frozenset({"report-path"}),
    )

    assert isinstance(literal, LiteralExpr)
    assert literal.literal_kind == "string"
    assert isinstance(integer, LiteralExpr)
    assert integer.literal_kind == "int"
    assert isinstance(boolean, LiteralExpr)
    assert boolean.literal_kind == "bool"

    assert isinstance(record, RecordExpr)
    assert record.type_name == "ChecksResult"
    assert [field_name for field_name, _ in record.fields] == ["status", "report"]

    assert isinstance(letstar, LetStarExpr)
    assert [name for name, _ in letstar.bindings] == ["first", "second"]
    assert isinstance(letstar.body, NameExpr)
    assert letstar.body.name == "second"


def test_elaborate_expression_prefers_exact_bound_names_over_field_access() -> None:
    exact_name = elaborate_expression(
        _expression_syntax("attempt.execution_report"),
        bound_names=frozenset({"attempt", "attempt.execution_report"}),
    )
    field_access = elaborate_expression(
        _expression_syntax("attempt.execution_report"),
        bound_names=frozenset({"attempt"}),
    )

    assert isinstance(exact_name, NameExpr)
    assert exact_name.name == "attempt.execution_report"

    assert isinstance(field_access, FieldAccessExpr)
    assert field_access.base.name == "attempt"
    assert field_access.fields == ("execution_report",)


def test_elaborate_expression_builds_match_arms_with_spans_and_form_paths() -> None:
    expr = elaborate_expression(
        _expression_syntax(
            "(match attempt "
            "((COMPLETED completed) completed.execution_report) "
            "((BLOCKED blocked) blocked.progress_report))"
        ),
        bound_names=frozenset({"attempt"}),
    )

    assert isinstance(expr, MatchExpr)
    assert expr.form_path == FORM_PATH
    assert len(expr.arms) == 2
    assert expr.arms[0].variant_name == "COMPLETED"
    assert expr.arms[0].binding_name == "completed"
    assert expr.arms[0].form_path == FORM_PATH
    assert isinstance(expr.arms[0].body, FieldAccessExpr)
    assert expr.arms[0].body.base.name == "completed"


def test_elaborate_expression_rejects_unknown_expression_forms() -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        elaborate_expression(_expression_syntax("(unknown-form 1)"), bound_names=frozenset())

    _assert_diagnostic_code(excinfo, "procedure_call_unknown")


def test_compile_stage3_elaborates_same_file_procedure_call_heads(tmp_path: Path) -> None:
    from orchestrator.workflow_lisp.compiler import compile_stage3_module

    fixture = FIXTURES / "valid" / "defproc_inline.orc"
    result = compile_stage3_module(
        fixture,
        validate_shared=False,
        workspace_root=tmp_path,
    )

    assert type(result.typed_workflows[0].typed_body.expr).__name__ == "ProcedureCallExpr"


def test_typecheck_expression_validates_record_exactness() -> None:
    type_env = _build_type_env()
    value_env = {
        "report-path": type_env.resolve_type(
            "WorkReport",
            span=_expression_syntax('"seed"').span,
            form_path=FORM_PATH,
        ),
        "result": type_env.resolve_type(
            "ChecksResult",
            span=_expression_syntax('"seed"').span,
            form_path=FORM_PATH,
        ),
    }

    valid = typecheck_expression(
        elaborate_expression(
            _expression_syntax('(record ChecksResult :status "ok" :report report-path)'),
            bound_names=frozenset(value_env),
        ),
        type_env=type_env,
        value_env=value_env,
    )
    accessed = typecheck_expression(
        elaborate_expression(
            _expression_syntax("result.report"),
            bound_names=frozenset(value_env),
        ),
        type_env=type_env,
        value_env=value_env,
    )

    assert isinstance(valid.type_ref, RecordTypeRef)
    assert valid.type_ref.name == "ChecksResult"
    assert isinstance(accessed.type_ref, PathTypeRef)
    assert accessed.type_ref.name == "WorkReport"

    with pytest.raises(LispFrontendCompileError) as missing_field:
        typecheck_expression(
            elaborate_expression(
                _expression_syntax('(record ChecksResult :status "ok")'),
                bound_names=frozenset(value_env),
            ),
            type_env=type_env,
            value_env=value_env,
        )
    _assert_diagnostic_code(missing_field, "record_field_missing")

    with pytest.raises(LispFrontendCompileError) as duplicate_field:
        typecheck_expression(
            elaborate_expression(
                _expression_syntax(
                    '(record ChecksResult :status "ok" :report report-path :report report-path)'
                ),
                bound_names=frozenset(value_env),
            ),
            type_env=type_env,
            value_env=value_env,
        )
    _assert_diagnostic_code(duplicate_field, "record_field_duplicate")

    with pytest.raises(LispFrontendCompileError) as unknown_field:
        typecheck_expression(
            elaborate_expression(
                _expression_syntax(
                    '(record ChecksResult :status "ok" :report report-path :extra report-path)'
                ),
                bound_names=frozenset(value_env),
            ),
            type_env=type_env,
            value_env=value_env,
        )
    _assert_diagnostic_code(unknown_field, "record_field_unknown")


def test_elaborate_expression_prefers_resolved_names_from_macro_expansion() -> None:
    import importlib

    macros = importlib.import_module("orchestrator.workflow_lisp.macros")
    syntax_module = build_syntax_module(
        read_sexpr_file(FIXTURES / "valid" / "macro_hygiene_local_binding.orc")
    )
    expanded = macros.expand_module_forms(
        syntax_module,
        catalog=macros.collect_macro_catalog(syntax_module),
    )
    from orchestrator.workflow_lisp.workflows import elaborate_workflow_definitions

    elaborated = elaborate_workflow_definitions(expanded)[0]
    body = elaborate_expression(
        elaborated.body,
        bound_names=frozenset(param.name for param in elaborated.params),
    )

    assert isinstance(body, LetStarExpr)
    assert body.bindings[0][0] == "tmp"
    assert isinstance(body.body, LetStarExpr)
    assert body.body.bindings[0][0] == "%macro__preserve-caller-tmp__m0001__tmp"
    assert isinstance(body.body.bindings[1][1], NameExpr)
    assert body.body.bindings[1][1].name == "%macro__preserve-caller-tmp__m0001__tmp"
    assert isinstance(body.body.body, RecordExpr)
    assert isinstance(body.body.body.fields[0][1], NameExpr)
    assert body.body.body.fields[0][1].name == "tmp"


def test_typecheck_expression_supports_sequential_letstar_bindings() -> None:
    type_env = _build_type_env()
    base_expr = _expression_syntax("report-path")
    value_env = {
        "report-path": type_env.resolve_type(
            "WorkReport",
            span=base_expr.span,
            form_path=base_expr.form_path,
        ),
    }

    typed = typecheck_expression(
        elaborate_expression(
            _expression_syntax("(let* ((first report-path) (second first)) second)"),
            bound_names=frozenset(value_env),
        ),
        type_env=type_env,
        value_env=value_env,
    )

    assert isinstance(typed.type_ref, PathTypeRef)
    assert typed.type_ref.name == "WorkReport"


def test_typecheck_expression_rejects_duplicate_letstar_bindings() -> None:
    type_env = _build_type_env()
    base_expr = _expression_syntax("report-path")
    value_env = {
        "report-path": type_env.resolve_type(
            "WorkReport",
            span=base_expr.span,
            form_path=base_expr.form_path,
        ),
    }

    with pytest.raises(LispFrontendCompileError) as excinfo:
        typecheck_expression(
            elaborate_expression(
                _expression_syntax("(let* ((first report-path) (first report-path)) first)"),
                bound_names=frozenset(value_env),
            ),
            type_env=type_env,
            value_env=value_env,
        )

    _assert_diagnostic_code(excinfo, "binding_duplicate")


def test_typecheck_expression_rejects_record_field_type_mismatches() -> None:
    type_env = _build_type_env()
    base_expr = _expression_syntax("report-path")
    value_env = {
        "report-path": type_env.resolve_type(
            "WorkReport",
            span=base_expr.span,
            form_path=base_expr.form_path,
        ),
    }

    with pytest.raises(LispFrontendCompileError) as excinfo:
        typecheck_expression(
            elaborate_expression(
                _expression_syntax('(record ChecksResult :status report-path :report report-path)'),
                bound_names=frozenset(value_env),
            ),
            type_env=type_env,
            value_env=value_env,
        )

    _assert_diagnostic_code(excinfo, "type_mismatch")
