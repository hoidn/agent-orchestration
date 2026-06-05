import inspect
import importlib
import ast
from pathlib import Path
from typing import get_args

import pytest

from orchestrator.workflow_lisp.compiler import PRELUDE_TYPE_NAMES, compile_stage1_module
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from orchestrator.workflow_lisp.drain_stdlib import BacklogDrainSpec
from orchestrator.workflow_lisp.parametric_constraints import SharedUnionFieldCapability
from orchestrator.workflow_lisp.expressions import (
    BacklogDrainExpr,
    BindProcBinding,
    BindProcExpr,
    CommandResultExpr,
    ContinueExpr,
    FinalizeSelectedItemExpr,
    FieldAccessExpr,
    FunctionCallExpr,
    IfExpr,
    LetProcExpr,
    LetProcBinding,
    LetStarExpr,
    LiteralExpr,
    LoopRecurExpr,
    MatchArm,
    MatchExpr,
    NameExpr,
    ProcedureCallExpr,
    ProduceOneOfExpr,
    ProviderResultExpr,
    RecordExpr,
    DoneExpr,
    ResourceTransitionExpr,
    ResumeOrStartExpr,
    RunProviderPhaseExpr,
    UnionVariantExpr,
    WithPhaseExpr,
    WorkflowRefLiteralExpr,
    ProcRefLiteralExpr,
    PhaseTargetExpr,
    GeneratedRelpathSeedExpr,
    CallExpr,
    elaborate_expression,
)
from orchestrator.workflow_lisp.phase_stdlib import (
    ProduceOneOfCandidateFieldSpec,
    ProduceOneOfCandidateSpec,
    ProduceOneOfProducerSpec,
)
from orchestrator.workflow_lisp.reader import read_sexpr_text
from orchestrator.workflow_lisp.reader import read_sexpr_file
from orchestrator.workflow_lisp.resource_stdlib import FinalizeSelectedItemSpec, ResourceTransitionSpec
from orchestrator.workflow_lisp.spans import SourcePosition, SourceSpan
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


def _test_span(path: str = "expression_traversal_test.orc") -> SourceSpan:
    start = SourcePosition(path=path, line=1, column=1, offset=0)
    end = SourcePosition(path=path, line=1, column=2, offset=1)
    return SourceSpan(start=start, end=end)


def _write_module(path: Path, lines: list[str]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def _build_type_env_from_lines(tmp_path: Path, lines: list[str]) -> FrontendTypeEnvironment:
    path = _write_module(tmp_path / "shared_union_fields.orc", lines)
    return FrontendTypeEnvironment.from_module(compile_stage1_module(path))


def _workflow_lisp_package_dir() -> Path:
    return Path(importlib.import_module("orchestrator.workflow_lisp").__file__).resolve().parent


def _traversal_module():
    return importlib.import_module("orchestrator.workflow_lisp.expression_traversal")


def _name(name: str) -> NameExpr:
    return NameExpr(name=name, span=_test_span(name), form_path=FORM_PATH)


def _literal(value: str | int | bool) -> LiteralExpr:
    if isinstance(value, bool):
        literal_kind = "bool"
    elif isinstance(value, int):
        literal_kind = "int"
    else:
        literal_kind = "string"
    return LiteralExpr(
        value=value,
        literal_kind=literal_kind,
        span=_test_span(str(value)),
        form_path=FORM_PATH,
    )


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


def test_elaborate_expression_supports_loop_recur_on_exhausted() -> None:
    expr = elaborate_expression(
        _expression_syntax(
            "(loop/recur :max 3 :state attempt "
            ":on-exhausted (record ChecksResult :status \"exhausted\" :report state.report) "
            "(fn (state) (match state "
            "((COMPLETED completed) (done (record ChecksResult :status \"ok\" :report completed.execution_report))) "
            "((BLOCKED blocked) (continue state)))))"
        ),
        bound_names=frozenset({"attempt"}),
    )

    assert isinstance(expr, LoopRecurExpr)
    assert isinstance(expr.on_exhausted_result_expr, RecordExpr)
    field_map = dict(expr.on_exhausted_result_expr.fields)
    assert isinstance(field_map["report"], FieldAccessExpr)
    assert field_map["report"].base.name == "state"


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


@pytest.mark.parametrize(
    "source",
    [
        "(loop/recur :max 3 :state attempt :on-exhausted (fn (state) (continue state)))",
        "(loop/recur :max 3 :state attempt (fn (state) (continue state)) :on-exhausted attempt)",
    ],
)
def test_elaborate_expression_rejects_malformed_loop_recur_on_exhausted(
    source: str,
) -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        elaborate_expression(
            _expression_syntax(source),
            bound_names=frozenset({"attempt"}),
        )

    _assert_diagnostic_code(excinfo, "loop_recur_contract_invalid")


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
    assert "StdlibSpecializationExpr" not in expr_names
    assert not hasattr(expressions, "StdlibSpecializationExpr")
    assert "class StdlibSpecializationExpr" not in source


def test_review_revise_loop_registry_owns_only_public_macro_surface() -> None:
    registry = importlib.import_module("orchestrator.workflow_lisp.form_registry")
    expressions = importlib.import_module("orchestrator.workflow_lisp.expressions")

    review_loop = registry.get_form_spec("review-revise-loop")
    bridge = registry.get_form_spec("__stdlib-specialization__")
    handlers = expressions._elaboration_route_handlers()

    assert review_loop is not None and review_loop.elaboration_route is None
    assert bridge is None
    assert "review-revise-loop" not in handlers
    assert "__stdlib-specialization__" not in handlers
    assert "stdlib_specialization" not in handlers


def test_expression_traversal_module_exports_locked_surface() -> None:
    traversal = _traversal_module()

    assert callable(traversal.iter_child_exprs)
    assert callable(traversal.walk_expr)


def test_expression_traversal_leaf_classification_matches_exprnode_union() -> None:
    expressions = importlib.import_module("orchestrator.workflow_lisp.expressions")

    leaf_expr_types = {
        NameExpr,
        LiteralExpr,
        FieldAccessExpr,
        PhaseTargetExpr,
        GeneratedRelpathSeedExpr,
        WorkflowRefLiteralExpr,
        ProcRefLiteralExpr,
    }

    assert leaf_expr_types <= set(get_args(expressions.ExprNode))


def test_expression_traversal_direct_child_classification_matches_exprnode_union() -> None:
    expressions = importlib.import_module("orchestrator.workflow_lisp.expressions")

    leaf_expr_types = {
        NameExpr,
        LiteralExpr,
        FieldAccessExpr,
        PhaseTargetExpr,
        GeneratedRelpathSeedExpr,
        WorkflowRefLiteralExpr,
        ProcRefLiteralExpr,
    }
    child_expr_types = {
        RecordExpr,
        UnionVariantExpr,
        LetStarExpr,
        IfExpr,
        MatchExpr,
        CallExpr,
        FunctionCallExpr,
        ProcedureCallExpr,
        WithPhaseExpr,
        BindProcExpr,
        LetProcExpr,
        ProviderResultExpr,
        CommandResultExpr,
        ContinueExpr,
        DoneExpr,
        LoopRecurExpr,
        RunProviderPhaseExpr,
        ProduceOneOfExpr,
        ResumeOrStartExpr,
        ResourceTransitionExpr,
        FinalizeSelectedItemExpr,
        BacklogDrainExpr,
    }

    expr_types = set(get_args(expressions.ExprNode))

    assert leaf_expr_types | child_expr_types == expr_types
    assert leaf_expr_types.isdisjoint(child_expr_types)


@pytest.mark.parametrize(
    ("expr", "expected_children"),
    [
        pytest.param(
            LetProcExpr(
                binding=LetProcBinding(
                    local_name="run-local",
                    params=(),
                    return_type_name="WorkflowOutput",
                    capture_names=(),
                    local_body=FunctionCallExpr(
                        callee_name="helper",
                        args=(_name("report"),),
                        span=_test_span("let-proc-local"),
                        form_path=FORM_PATH,
                    ),
                    span=_test_span("let-proc-binding"),
                    form_path=FORM_PATH,
                ),
                body=ProcedureCallExpr(
                    callee_name="invoke-runner",
                    args=(_name("payload"),),
                    span=_test_span("let-proc-body"),
                    form_path=FORM_PATH,
                ),
                span=_test_span("let-proc"),
                form_path=FORM_PATH,
            ),
            ("local_body", "body"),
            id="let-proc",
        ),
        pytest.param(
            LoopRecurExpr(
                max_iterations_expr=_literal(3),
                initial_state_expr=_name("state"),
                binding_name="current",
                body_expr=ContinueExpr(
                    state_expr=_name("next-state"),
                    span=_test_span("loop-body"),
                    form_path=FORM_PATH,
                ),
                on_exhausted_result_expr=DoneExpr(
                    result_expr=_name("exhausted"),
                    span=_test_span("loop-exhausted"),
                    form_path=FORM_PATH,
                ),
                span=_test_span("loop"),
                form_path=FORM_PATH,
            ),
            (
                "max_iterations_expr",
                "initial_state_expr",
                "body_expr",
                "on_exhausted_result_expr",
            ),
            id="loop-recur",
        ),
        pytest.param(
            ProduceOneOfExpr(
                returns_type_name="SelectionResult",
                ctx_expr=_name("ctx"),
                producer=ProduceOneOfProducerSpec(
                    kind="provider",
                    provider_expr=_name("providers.execute"),
                    prompt_expr=_name("prompts.implementation.execute"),
                    inputs=(_name("producer-input"),),
                ),
                candidates=(
                    ProduceOneOfCandidateSpec(
                        variant_name="APPROVED",
                        fields=(
                            ProduceOneOfCandidateFieldSpec(
                                field_name="result",
                                target_expr=_name("candidate-target"),
                            ),
                            ProduceOneOfCandidateFieldSpec(
                                field_name="sidecar",
                                target_expr=None,
                            ),
                        ),
                    ),
                ),
                span=_test_span("produce-one-of"),
                form_path=FORM_PATH,
            ),
            (
                "ctx_expr",
                "producer.provider_expr",
                "producer.prompt_expr",
                "producer.inputs[0]",
                "candidate.target_expr",
            ),
            id="produce-one-of",
        ),
        pytest.param(
            ResourceTransitionExpr(
                spec=ResourceTransitionSpec(
                    transition_name="complete",
                    ctx_expr=_name("ctx"),
                    when_expr=_name("when-ready"),
                    resource_expr=_name("resource"),
                    from_queue_name="queued",
                    to_queue_name="done",
                    ledger_expr=_name("ledger"),
                    event_name="completed",
                ),
                span=_test_span("resource-transition"),
                form_path=FORM_PATH,
            ),
            ("spec.ctx_expr", "spec.when_expr", "spec.resource_expr", "spec.ledger_expr"),
            id="resource-transition",
        ),
        pytest.param(
            FinalizeSelectedItemExpr(
                spec=FinalizeSelectedItemSpec(
                    ctx_expr=_name("ctx"),
                    selected_expr=_name("selected"),
                    queue_transition_expr=_name("queue-transition"),
                    roadmap_expr=_name("roadmap"),
                    plan_expr=_name("plan"),
                    implementation_expr=_name("implementation"),
                ),
                span=_test_span("finalize-selected-item"),
                form_path=FORM_PATH,
            ),
            (
                "spec.ctx_expr",
                "spec.selected_expr",
                "spec.queue_transition_expr",
                "spec.roadmap_expr",
                "spec.plan_expr",
                "spec.implementation_expr",
            ),
            id="finalize-selected-item",
        ),
        pytest.param(
            BacklogDrainExpr(
                spec=BacklogDrainSpec(
                    drain_name="drain",
                    ctx_expr=_name("ctx"),
                    selector_name="selector",
                    run_item_name="runner",
                    gap_drafter_name="drafter",
                    providers_expr=_name("providers"),
                    max_iterations_expr=_literal(5),
                ),
                span=_test_span("backlog-drain"),
                form_path=FORM_PATH,
            ),
            ("spec.ctx_expr", "spec.providers_expr", "spec.max_iterations_expr"),
            id="backlog-drain",
        ),
    ],
)
def test_expression_traversal_iter_child_exprs_preserves_locked_order(
    expr: object,
    expected_children: tuple[str, ...],
) -> None:
    traversal = _traversal_module()
    labels: list[str] = []
    children = traversal.iter_child_exprs(expr)

    for child in children:
        if child == getattr(getattr(expr, "binding", None), "local_body", object()):
            labels.append("local_body")
        elif child == getattr(expr, "body", object()):
            labels.append("body")
        elif child == getattr(expr, "max_iterations_expr", object()):
            labels.append("max_iterations_expr")
        elif child == getattr(expr, "initial_state_expr", object()):
            labels.append("initial_state_expr")
        elif child == getattr(expr, "body_expr", object()):
            labels.append("body_expr")
        elif child == getattr(expr, "on_exhausted_result_expr", object()):
            labels.append("on_exhausted_result_expr")
        elif child == getattr(expr, "ctx_expr", object()):
            labels.append("ctx_expr")
        elif child == getattr(getattr(expr, "producer", None), "provider_expr", object()):
            labels.append("producer.provider_expr")
        elif child == getattr(getattr(expr, "producer", None), "prompt_expr", object()):
            labels.append("producer.prompt_expr")
        elif child in getattr(getattr(expr, "producer", None), "inputs", ()):
            labels.append("producer.inputs[0]")
        elif (
            isinstance(expr, ProduceOneOfExpr)
            and child == expr.candidates[0].fields[0].target_expr
        ):
            labels.append("candidate.target_expr")
        elif child == getattr(getattr(expr, "spec", None), "ctx_expr", object()):
            labels.append("spec.ctx_expr")
        elif child == getattr(getattr(expr, "spec", None), "when_expr", object()):
            labels.append("spec.when_expr")
        elif child == getattr(getattr(expr, "spec", None), "resource_expr", object()):
            labels.append("spec.resource_expr")
        elif child == getattr(getattr(expr, "spec", None), "ledger_expr", object()):
            labels.append("spec.ledger_expr")
        elif child == getattr(getattr(expr, "spec", None), "selected_expr", object()):
            labels.append("spec.selected_expr")
        elif child == getattr(getattr(expr, "spec", None), "queue_transition_expr", object()):
            labels.append("spec.queue_transition_expr")
        elif child == getattr(getattr(expr, "spec", None), "roadmap_expr", object()):
            labels.append("spec.roadmap_expr")
        elif child == getattr(getattr(expr, "spec", None), "plan_expr", object()):
            labels.append("spec.plan_expr")
        elif child == getattr(getattr(expr, "spec", None), "implementation_expr", object()):
            labels.append("spec.implementation_expr")
        elif child == getattr(getattr(expr, "spec", None), "providers_expr", object()):
            labels.append("spec.providers_expr")
        elif child == getattr(getattr(expr, "spec", None), "max_iterations_expr", object()):
            labels.append("spec.max_iterations_expr")

    assert tuple(labels) == expected_children


def test_expression_traversal_walk_expr_is_preorder() -> None:
    traversal = _traversal_module()
    expr = WithPhaseExpr(
        ctx_expr=_name("ctx"),
        phase_name="implementation",
        body=MatchExpr(
            subject=_name("attempt"),
            arms=(
                MatchArm(
                    variant_name="BLOCKED",
                    binding_name="blocked",
                    body=ContinueExpr(
                        state_expr=FunctionCallExpr(
                            callee_name="next-state",
                            args=(_name("blocked"),),
                            span=_test_span("continue-call"),
                            form_path=FORM_PATH,
                        ),
                        span=_test_span("continue"),
                        form_path=FORM_PATH,
                    ),
                    span=_test_span("blocked-arm"),
                    form_path=FORM_PATH,
                ),
                MatchArm(
                    variant_name="COMPLETED",
                    binding_name="completed",
                    body=DoneExpr(
                        result_expr=ProcedureCallExpr(
                            callee_name="finalize",
                            args=(_name("completed"),),
                            span=_test_span("done-call"),
                            form_path=FORM_PATH,
                        ),
                        span=_test_span("done"),
                        form_path=FORM_PATH,
                    ),
                    span=_test_span("completed-arm"),
                    form_path=FORM_PATH,
                ),
            ),
            span=_test_span("match"),
            form_path=FORM_PATH,
        ),
        span=_test_span("with-phase"),
        form_path=FORM_PATH,
    )

    walked = list(traversal.walk_expr(expr))

    assert [type(node).__name__ for node in walked] == [
        "WithPhaseExpr",
        "NameExpr",
        "MatchExpr",
        "NameExpr",
        "ContinueExpr",
        "FunctionCallExpr",
        "NameExpr",
        "DoneExpr",
        "ProcedureCallExpr",
        "NameExpr",
    ]


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


def test_shared_union_field_capability_allows_branch_free_projection_only_for_validated_field(
    tmp_path: Path,
) -> None:
    type_env = _build_type_env_from_lines(
        tmp_path,
        [
            "(workflow-lisp",
            '  (:language "0.1")',
            '  (:target-dsl "2.14")',
            "  (defpath WorkReport",
            "    :kind relpath",
            '    :under "artifacts/work"',
            "    :must-exist true)",
            "  (defunion ReviewState",
            "    (APPROVED",
            "      (shared_report WorkReport))",
            "    (BLOCKED",
            "      (shared_report WorkReport)",
            "      (blocker_class String))))",
        ],
    )
    review_state = type_env.resolve_type("ReviewState", span=_expression_syntax('"probe"').span, form_path=FORM_PATH)
    shared_report = type_env.resolve_type("WorkReport", span=_expression_syntax('"probe"').span, form_path=FORM_PATH)

    typed = typecheck_expression(
        elaborate_expression(
            _expression_syntax("attempt.shared_report"),
            bound_names=frozenset({"attempt"}),
        ),
        type_env=type_env,
        value_env={"attempt": review_state},
        shared_union_field_capabilities=(
            SharedUnionFieldCapability(
                union_type_name="ReviewState",
                field_name="shared_report",
                field_type_ref=shared_report,
            ),
        ),
    )

    assert isinstance(typed.type_ref, PathTypeRef)
    assert typed.type_ref.name == "WorkReport"


def test_shared_union_field_capability_does_not_allow_variant_specific_field_without_match(
    tmp_path: Path,
) -> None:
    type_env = _build_type_env_from_lines(
        tmp_path,
        [
            "(workflow-lisp",
            '  (:language "0.1")',
            '  (:target-dsl "2.14")',
            "  (defpath WorkReport",
            "    :kind relpath",
            '    :under "artifacts/work"',
            "    :must-exist true)",
            "  (defunion ReviewState",
            "    (APPROVED",
            "      (shared_report WorkReport))",
            "    (BLOCKED",
            "      (shared_report WorkReport)",
            "      (blocker_class String))))",
        ],
    )
    review_state = type_env.resolve_type("ReviewState", span=_expression_syntax('"probe"').span, form_path=FORM_PATH)
    shared_report = type_env.resolve_type("WorkReport", span=_expression_syntax('"probe"').span, form_path=FORM_PATH)

    with pytest.raises(LispFrontendCompileError) as excinfo:
        typecheck_expression(
            elaborate_expression(
                _expression_syntax("attempt.blocker_class"),
                bound_names=frozenset({"attempt"}),
            ),
            type_env=type_env,
            value_env={"attempt": review_state},
            shared_union_field_capabilities=(
                SharedUnionFieldCapability(
                    union_type_name="ReviewState",
                    field_name="shared_report",
                    field_type_ref=shared_report,
                ),
            ),
        )

    _assert_diagnostic_code(excinfo, "variant_ref_unproved")


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
