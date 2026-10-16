from __future__ import annotations

from pathlib import Path

import pytest

from orchestrator.workflow_lisp.compiler import compile_stage1_module
from orchestrator.workflow_lisp.compiler_session import CompilerSession
from orchestrator.workflow_lisp.loop_state import retain_loop_carrier_families
from orchestrator.workflow_lisp.workflows import WorkflowDef
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from orchestrator.workflow_lisp.expressions import elaborate_expression
from orchestrator.workflow_lisp.reader import read_sexpr_text
from orchestrator.workflow_lisp.syntax import SyntaxNode
from orchestrator.workflow_lisp.type_env import (
    FrontendTypeEnvironment,
    ListTypeRef,
    TypeParamRef,
)
from orchestrator.workflow_lisp.typecheck import typecheck_expression


FORM_PATH = ("workflow-lisp", "loop-state-test")


def _expression_syntax(source: str, *, form_path: tuple[str, ...] = FORM_PATH) -> SyntaxNode:
    parse_tree = read_sexpr_text(source, source_path="inline_loop_state.orc")
    assert len(parse_tree.items) == 1
    datum = parse_tree.items[0]
    return SyntaxNode(
        datum=datum,
        span=datum.span,
        module_path="inline_loop_state.orc",
        form_path=form_path,
    )


def _write_module(path: Path, lines: list[str]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    return path




def _assert_diagnostic_code(excinfo: pytest.ExceptionInfo[LispFrontendCompileError], code: str) -> None:
    assert excinfo.value.diagnostics[0].code == code


def _build_type_env(
    tmp_path: Path,
    extra_lines: list[str] | None = None,
    *,
    target_dsl_version: str = "2.35",
) -> FrontendTypeEnvironment:
    path = _write_module(
        tmp_path / "loop_state_types.orc",
        [
            "(workflow-lisp",
            '  (:language "0.1")',
            f'  (:target-dsl "{target_dsl_version}")',
            "  (defpath WorkReport",
            "    :kind relpath",
            '    :under "artifacts/work"',
            "    :must-exist true)",
            "  (defrecord ReviewFindings",
            "    (items_path WorkReport))",
            "  (defrecord WorkflowInput",
            "    (report WorkReport))",
            "  (defrecord WorkflowOutput",
            "    (report WorkReport))",
            *(extra_lines or []),
            ")",
        ],
    )
    return FrontendTypeEnvironment.from_module(compile_stage1_module(path))



def _owned_expression(syntax: SyntaxNode, *, bound_names: frozenset[str]):
    session = CompilerSession()
    owner = WorkflowDef(
        name="loop-state-test",
        params=(),
        return_type_name="WorkflowOutput",
        body=syntax,
        span=syntax.span,
        form_path=syntax.form_path,
    )
    retain_loop_carrier_families(
        "loop_state_types", workflows=(owner,), session_state=session.typecheck,
    )
    return elaborate_expression(syntax, bound_names=bound_names), session


def test_elaborate_loop_state_seed_expr() -> None:
    expr = elaborate_expression(
        _expression_syntax(
            '(loop-state (status String "ok") (report WorkReport report-path))'
        ),
        bound_names=frozenset({"report-path"}),
    )

    assert type(expr).__name__ == "LoopStateSeedExpr"
    fields = getattr(expr, "fields")
    assert [(field.name, field.type_name) for field in fields] == [
        ("status", "String"),
        ("report", "WorkReport"),
    ]
    assert type(fields[0].value_expr).__name__ == "LiteralExpr"
    assert type(fields[1].value_expr).__name__ == "NameExpr"


def test_elaborate_loop_state_update_expr() -> None:
    expr = elaborate_expression(
        _expression_syntax(
            '(loop-state :like current :status next-status :report report-path)'
        ),
        bound_names=frozenset({"current", "next-status", "report-path"}),
    )

    assert type(expr).__name__ == "LoopStateUpdateExpr"
    assert getattr(getattr(expr, "base_expr"), "name") == "current"
    overrides = getattr(expr, "overrides")
    assert [name for name, _ in overrides] == ["status", "report"]
    assert type(overrides[0][1]).__name__ == "NameExpr"
    assert type(overrides[1][1]).__name__ == "NameExpr"


def test_elaborate_loop_state_rejects_duplicate_seed_fields() -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        elaborate_expression(
            _expression_syntax(
                '(loop-state (status String "ok") (status String "still-ok"))'
            ),
            bound_names=frozenset(),
        )

    _assert_diagnostic_code(excinfo, "loop_state_duplicate_field")


def test_elaborate_loop_state_rejects_missing_like_base() -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        elaborate_expression(
            _expression_syntax('(loop-state :like :status next-status)'),
            bound_names=frozenset({"next-status"}),
        )

    _assert_diagnostic_code(excinfo, "loop_state_requires_typed_fields")


def test_expression_traversal_visits_loop_state_children() -> None:
    traversal = __import__(
        "orchestrator.workflow_lisp.expression_traversal",
        fromlist=["iter_child_exprs"],
    )
    expr = elaborate_expression(
        _expression_syntax(
            '(loop-state :like current :status next-status :report report-path)'
        ),
        bound_names=frozenset({"current", "next-status", "report-path"}),
    )

    children = traversal.iter_child_exprs(expr)

    assert [getattr(child, "name", None) for child in children] == [
        "current",
        "next-status",
        "report-path",
    ]


def test_typecheck_loop_state_seed_builds_local_record_type(tmp_path: Path) -> None:
    type_env = _build_type_env(tmp_path)
    expr, session = _owned_expression(
        _expression_syntax(
            '(loop-state (status String "ok") (report WorkReport report-path))'
        ),
        bound_names=frozenset({"report-path"}),
    )

    typed = typecheck_expression(
        expr,
        type_env=type_env,
        compiler_session=session,
        value_env={
            "report-path": type_env.resolve_type(
                "WorkReport",
                span=expr.span,
                form_path=expr.form_path,
            )
        },
    )

    assert type(typed.type_ref).__name__ == "RecordTypeRef"
    assert typed.type_ref.name.startswith("%loop-state.")
    assert typed.type_ref.field_types["status"].name == "String"
    assert typed.type_ref.field_types["report"].name == "WorkReport"


def test_typecheck_loop_state_update_preserves_carrier_type(tmp_path: Path) -> None:
    type_env = _build_type_env(tmp_path)
    expr, session = _owned_expression(
        _expression_syntax(
            "(let* ((state (loop-state (status String \"ok\") (report WorkReport report-path))) "
            "       (next (loop-state :like state :status \"revised\"))) "
            "  next)"
        ),
        bound_names=frozenset({"report-path"}),
    )

    typed = typecheck_expression(
        expr,
        type_env=type_env,
        compiler_session=session,
        value_env={
            "report-path": type_env.resolve_type(
                "WorkReport",
                span=expr.span,
                form_path=expr.form_path,
            )
        },
    )

    assert type(typed.type_ref).__name__ == "RecordTypeRef"
    assert typed.type_ref.name.startswith("%loop-state.")
    assert typed.type_ref.field_types["status"].name == "String"
    assert typed.type_ref.field_types["report"].name == "WorkReport"


def test_typecheck_loop_state_rejects_unknown_override_field(tmp_path: Path) -> None:
    type_env = _build_type_env(tmp_path)
    expr, session = _owned_expression(
        _expression_syntax(
            "(let* ((state (loop-state (status String \"ok\") (report WorkReport report-path)))) "
            "  (loop-state :like state :missing \"nope\"))"
        ),
        bound_names=frozenset({"report-path"}),
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        typecheck_expression(
            expr,
            type_env=type_env,
            compiler_session=session,
            value_env={
                "report-path": type_env.resolve_type(
                    "WorkReport",
                    span=expr.span,
                    form_path=expr.form_path,
                )
            },
        )

    _assert_diagnostic_code(excinfo, "loop_state_unknown_field")


def test_typecheck_loop_state_rejects_non_loop_state_like_base(tmp_path: Path) -> None:
    type_env = _build_type_env(tmp_path)
    expr = elaborate_expression(
        _expression_syntax('(loop-state :like report-path :status "nope")'),
        bound_names=frozenset({"report-path"}),
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        typecheck_expression(
            expr,
            type_env=type_env,
            value_env={
                "report-path": type_env.resolve_type(
                    "WorkReport",
                    span=expr.span,
                    form_path=expr.form_path,
                )
            },
        )

    _assert_diagnostic_code(excinfo, "loop_state_like_not_loop_state")


def test_typecheck_loop_state_rejects_proc_ref_field(tmp_path: Path) -> None:
    type_env = _build_type_env(tmp_path)
    proc_ref_type = type_env.resolve_type(
        "ProcRef[String -> String]",
        span=_expression_syntax("runner").span,
        form_path=FORM_PATH,
    )
    expr = elaborate_expression(
        _expression_syntax(
            "(loop-state (runner ProcRef[String -> String] runner))"
        ),
        bound_names=frozenset({"runner"}),
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        typecheck_expression(
            expr,
            type_env=type_env,
            value_env={"runner": proc_ref_type},
        )

    _assert_diagnostic_code(excinfo, "loop_state_runtime_transport_forbidden")


def test_typecheck_loop_state_rejects_workflow_ref_field(tmp_path: Path) -> None:
    type_env = _build_type_env(tmp_path)
    workflow_ref_type = type_env.resolve_type(
        "WorkflowRef[WorkflowInput -> WorkflowOutput]",
        span=_expression_syntax("runner").span,
        form_path=FORM_PATH,
    )
    expr = elaborate_expression(
        _expression_syntax(
            "(loop-state (runner WorkflowRef[WorkflowInput -> WorkflowOutput] runner))"
        ),
        bound_names=frozenset({"runner"}),
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        typecheck_expression(
            expr,
            type_env=type_env,
            value_env={"runner": workflow_ref_type},
        )

    _assert_diagnostic_code(excinfo, "loop_state_runtime_transport_forbidden")


@pytest.mark.parametrize(
    ("field_type_name", "value_name"),
    [
        ("Provider", "provider"),
        ("Prompt", "prompt"),
        ("Json", "payload"),
    ],
)
def test_typecheck_loop_state_rejects_provider_prompt_json_runtime_forbidden_fields(
    tmp_path: Path,
    field_type_name: str,
    value_name: str,
) -> None:
    type_env = _build_type_env(tmp_path)
    expr = elaborate_expression(
        _expression_syntax(
            f"(loop-state (value {field_type_name} {value_name}))"
        ),
        bound_names=frozenset({value_name}),
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        typecheck_expression(
            expr,
            type_env=type_env,
            value_env={
                value_name: type_env.resolve_type(
                    field_type_name,
                    span=expr.span,
                    form_path=expr.form_path,
                )
            },
        )

    _assert_diagnostic_code(excinfo, "loop_state_runtime_transport_forbidden")


def test_typecheck_loop_state_rejects_unresolved_type_parameter(tmp_path: Path) -> None:
    type_env = _build_type_env(tmp_path)
    type_env._type_refs["T"] = TypeParamRef(name="T")
    expr = elaborate_expression(
        _expression_syntax("(loop-state (value T payload))"),
        bound_names=frozenset({"payload"}),
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        typecheck_expression(
            expr,
            type_env=type_env,
            value_env={
                "payload": type_env.resolve_type(
                    "String",
                    span=expr.span,
                    form_path=expr.form_path,
                )
            },
        )

    _assert_diagnostic_code(excinfo, "loop_state_unresolved_type_parameter")


def test_typecheck_loop_state_accepts_projectable_list_field(tmp_path: Path) -> None:
    type_env = _build_type_env(tmp_path)
    expr, session = _owned_expression(
        _expression_syntax("(loop-state (history List[String] history))"),
        bound_names=frozenset({"history"}),
    )

    typed = typecheck_expression(
        expr,
        type_env=type_env,
        compiler_session=session,
        value_env={
            "history": type_env.resolve_type(
                "List[String]",
                span=expr.span,
                form_path=expr.form_path,
            )
        },
    )

    history_type = typed.type_ref.field_types["history"]
    assert isinstance(history_type, ListTypeRef)
    assert history_type.item_type_ref.name == "String"


def test_typecheck_loop_state_rich_list_preserves_record_and_union_descriptors(
    tmp_path: Path,
) -> None:
    """Target-2.29 preserves rich list descriptors in loop-state."""

    type_env = _build_type_env(
        tmp_path,
        extra_lines=[
            "  (defrecord Task",
            "    (task_id String))",
            "  (defunion TaskOutcome",
            "    (PENDING (task Task))",
            "    (BLOCKED (reason String)))",
        ],
        target_dsl_version="2.35",
    )
    expr, session = _owned_expression(
        _expression_syntax(
            "(loop-state (tasks List[Task] tasks) (outcomes List[TaskOutcome] outcomes))"
        ),
        bound_names=frozenset({"tasks", "outcomes"}),
    )

    typed = typecheck_expression(
        expr,
        type_env=type_env,
        compiler_session=session,
        value_env={
            "tasks": type_env.resolve_type("List[Task]", span=expr.span, form_path=expr.form_path),
            "outcomes": type_env.resolve_type(
                "List[TaskOutcome]", span=expr.span, form_path=expr.form_path
            ),
        },
    )

    tasks_type = typed.type_ref.field_types["tasks"]
    outcomes_type = typed.type_ref.field_types["outcomes"]
    assert isinstance(tasks_type, ListTypeRef)
    assert tasks_type.item_type_ref.name == "Task"
    assert isinstance(outcomes_type, ListTypeRef)
    assert outcomes_type.item_type_ref.name == "TaskOutcome"
