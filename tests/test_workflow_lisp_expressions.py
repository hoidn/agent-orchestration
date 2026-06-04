import inspect
import importlib
import ast
from pathlib import Path
from typing import get_args

import pytest

from orchestrator.workflow_lisp.compiler import PRELUDE_TYPE_NAMES, compile_stage1_module
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from orchestrator.workflow_lisp.expressions import (
    ContinueExpr,
    FieldAccessExpr,
    LetProcExpr,
    LetStarExpr,
    LiteralExpr,
    LoopRecurExpr,
    MatchExpr,
    NameExpr,
    RecordExpr,
    DoneExpr,
    elaborate_expression,
)
from orchestrator.workflow_lisp.reader import read_sexpr_text
from orchestrator.workflow_lisp.reader import read_sexpr_file
from orchestrator.workflow_lisp.syntax import SyntaxNode, build_syntax_module
from orchestrator.workflow_lisp.type_env import (
    FrontendTypeEnvironment,
    PathTypeRef,
    PRELUDE_PATH_TYPES,
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


def _workflow_lisp_package_dir() -> Path:
    return Path(importlib.import_module("orchestrator.workflow_lisp").__file__).resolve().parent


def _typecheck_top_level_names() -> set[str]:
    source_path = Path(importlib.import_module("orchestrator.workflow_lisp.typecheck").__file__)
    module = ast.parse(source_path.read_text(encoding="utf-8"))
    return {
        node.name
        for node in module.body
        if isinstance(node, (ast.AsyncFunctionDef, ast.ClassDef, ast.FunctionDef))
    }


def test_typecheck_facade_reexports_public_entrypoints_after_owner_split() -> None:
    typecheck_module = importlib.import_module("orchestrator.workflow_lisp.typecheck")
    package_dir = _workflow_lisp_package_dir()
    context_path = package_dir / "typecheck_context.py"
    dispatch_path = package_dir / "typecheck_dispatch.py"
    dispatch_source = dispatch_path.read_text(encoding="utf-8")

    assert typecheck_module.typecheck_expression is typecheck_expression
    assert context_path.is_file()
    assert dispatch_path.is_file()
    assert inspect.getsourcefile(typecheck_module.TypedExpr) == str(context_path)
    assert "_typecheck" not in _typecheck_top_level_names()
    assert "_ACTIVE_FUNCTION_CATALOG" not in dispatch_source
    assert "_ACTIVE_PROC_REF_VALUE_ENV" not in dispatch_source
    assert "_ACTIVE_VALUE_EXPR_ENV" not in dispatch_source
    assert "_ACTIVE_REVIEW_LOOP_LEGACY_BRIDGE_POLICY" not in dispatch_source
    assert "snapshot_session_state" in dispatch_source
    assert "restore_session_state" in dispatch_source


def test_frontend_type_environment_resolves_stage1_definitions() -> None:
    type_env = _build_type_env()
    syntax = _expression_syntax('"probe"')

    for prelude_name in PRELUDE_TYPE_NAMES:
        resolved = type_env.resolve_type(prelude_name, span=syntax.span, form_path=syntax.form_path)
        if prelude_name in PRELUDE_PATH_TYPES:
            assert isinstance(resolved, PathTypeRef)
        else:
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


def test_elaborate_expression_supports_loop_recur() -> None:
    expr = elaborate_expression(
        _expression_syntax(
            "(loop/recur :max 3 :state attempt "
            "(fn (state) (match state "
            "((COMPLETED completed) (done completed.execution_report)) "
            "((BLOCKED blocked) (continue state)))))"
        ),
        bound_names=frozenset({"attempt"}),
    )

    assert isinstance(expr, LoopRecurExpr)
    assert expr.binding_name == "state"
    assert isinstance(expr.body_expr, MatchExpr)
    assert isinstance(expr.body_expr.arms[0].body, DoneExpr)
    assert isinstance(expr.body_expr.arms[1].body, ContinueExpr)


def test_elaborate_expression_supports_if_conditional() -> None:
    expr = elaborate_expression(
        _expression_syntax(
            '(if ready (record ChecksResult :status "ok" :report report-path) '
            '(record ChecksResult :status "fallback" :report fallback-path))'
        ),
        bound_names=frozenset({"ready", "report-path", "fallback-path"}),
    )

    assert type(expr).__name__ == "IfExpr"
    assert isinstance(getattr(expr, "condition_expr"), NameExpr)
    assert getattr(expr, "condition_expr").name == "ready"
    assert isinstance(getattr(expr, "then_expr"), RecordExpr)
    assert isinstance(getattr(expr, "else_expr"), RecordExpr)


def test_elaborate_expression_supports_let_proc() -> None:
    expr = elaborate_expression(
        _expression_syntax(
            "(let-proc (run-local ((input WorkflowInput)) -> WorkflowOutput "
            "           :captures (fixed) "
            "           (command-result run_checks "
            '             :argv ("python" "scripts/run_checks.py" input.report fixed) '
            "             :returns WorkflowOutput)) "
            "  (proc-ref run-local))"
        ),
        bound_names=frozenset({"fixed"}),
    )

    assert isinstance(expr, LetProcExpr)
    assert expr.binding.local_name == "run-local"
    assert expr.binding.capture_names == ("fixed",)


@pytest.mark.parametrize(
    ("bound_names", "procedure_names"),
    [
        (frozenset({"input", "run-local"}), frozenset()),
        (frozenset({"input"}), frozenset({"run-local"})),
    ],
)
def test_elaborate_expression_rejects_let_proc_name_collisions(
    bound_names: frozenset[str],
    procedure_names: frozenset[str],
) -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        elaborate_expression(
            _expression_syntax(
                "(let-proc (run-local ((item WorkflowInput)) -> WorkflowOutput "
                "           :captures () "
                "           item) "
                "  input)"
            ),
            bound_names=bound_names,
            procedure_names=procedure_names,
        )

    assert excinfo.value.diagnostics[0].code == "let_proc_name_collision"


@pytest.mark.parametrize(
    ("source", "code", "bound_names"),
    [
        (
            "(let-proc ((a ((input WorkflowInput)) -> WorkflowOutput :captures () input) "
            "           (b ((input WorkflowInput)) -> WorkflowOutput :captures () input)) "
            "  input)",
            "let_proc_multiple_bindings_unsupported",
            frozenset({"input"}),
        ),
        (
            "(let-proc (local ((input WorkflowInput)) -> WorkflowOutput "
            "           :captures (ctx.field) "
            "           input) "
            "  input)",
            "let_proc_capture_not_identifier",
            frozenset({"ctx", "input"}),
        ),
        (
            "(let-proc (local ((input WorkflowInput)) -> WorkflowOutput "
            "           :captures () "
            "           input) "
            "  (local input))",
            "let_proc_bare_name_invalid",
            frozenset({"input"}),
        ),
        (
            "(let-proc (outer ((input WorkflowInput)) -> WorkflowOutput "
            "           :captures () "
            "           input) "
            "  (let-proc (inner ((input WorkflowInput)) -> WorkflowOutput "
            "              :captures () "
            "              input) "
            "    input))",
            "let_proc_nested_unsupported",
            frozenset({"input"}),
        ),
    ],
)
def test_elaborate_expression_rejects_invalid_let_proc_forms(
    source: str,
    code: str,
    bound_names: frozenset[str],
) -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        elaborate_expression(_expression_syntax(source), bound_names=bound_names)

    assert excinfo.value.diagnostics[0].code == code


def test_elaborate_expression_rejects_if_wrong_arity() -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        elaborate_expression(
            _expression_syntax("(if ready report-path)"),
            bound_names=frozenset({"ready", "report-path"}),
        )

    _assert_diagnostic_code(excinfo, "if_form_invalid")


def test_elaborate_expression_rejects_fn_outside_loop_recur() -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        elaborate_expression(
            _expression_syntax("(fn (state) state)"),
            bound_names=frozenset({"state"}),
        )

    _assert_diagnostic_code(excinfo, "loop_recur_fn_outside_loop")


def test_elaborate_expression_rejects_malformed_loop_recur_fn() -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        elaborate_expression(
            _expression_syntax("(loop/recur :max 3 :state attempt (fn (left right) attempt))"),
            bound_names=frozenset({"attempt"}),
        )

    _assert_diagnostic_code(excinfo, "loop_recur_fn_invalid")


def test_elaborate_expression_rejects_unknown_expression_forms() -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        elaborate_expression(_expression_syntax("(unknown-form 1)"), bound_names=frozenset())

    _assert_diagnostic_code(excinfo, "procedure_call_unknown")


def test_elaborate_expression_rejects_stdlib_extension_without_import_route() -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        elaborate_expression(
            _expression_syntax("(review-revise-loop implementation-review)"),
            bound_names=frozenset(),
        )

    _assert_diagnostic_code(excinfo, "stdlib_extension_missing_import_route")


def test_no_review_loop_expr_in_core_ast_union() -> None:
    expressions = importlib.import_module("orchestrator.workflow_lisp.expressions")

    expr_names = {expr_type.__name__ for expr_type in get_args(expressions.ExprNode)}
    source = inspect.getsource(expressions)

    assert "ReviewReviseLoopExpr" not in expr_names
    assert not hasattr(expressions, "ReviewReviseLoopExpr")
    assert "class ReviewReviseLoopExpr" not in source
    assert "StdlibSpecializationExpr" in expr_names


def test_review_revise_loop_not_elaborated_by_head_name() -> None:
    registry = importlib.import_module("orchestrator.workflow_lisp.form_registry")
    expressions = importlib.import_module("orchestrator.workflow_lisp.expressions")

    review_loop = registry.get_form_spec("review-revise-loop")
    bridge = registry.get_form_spec("__stdlib-specialization__")
    handlers = expressions._elaboration_route_handlers()

    assert review_loop is not None and review_loop.elaboration_route is None
    assert bridge is not None and bridge.elaboration_route == "stdlib_specialization"
    assert "review-revise-loop" not in handlers
    assert "__stdlib-specialization__" not in handlers
    assert "stdlib_specialization" in handlers


def test_elaborate_expression_rejects_top_level_definition_head_in_expression_position() -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        elaborate_expression(
            _expression_syntax('(defworkflow nested () -> String "nope")'),
            bound_names=frozenset(),
        )

    _assert_diagnostic_code(excinfo, "top_level_definition_in_expression_position")


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


def test_elaborate_expression_builds_function_calls_for_visible_helpers() -> None:
    signature = inspect.signature(elaborate_expression)

    assert "function_names" in signature.parameters
    expr = elaborate_expression(
        _expression_syntax("(summarize report-path)"),
        bound_names=frozenset({"report-path"}),
        function_names=frozenset({"summarize"}),
    )

    assert type(expr).__name__ == "FunctionCallExpr"
