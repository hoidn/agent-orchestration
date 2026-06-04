from __future__ import annotations

import json
from pathlib import Path

import pytest

from orchestrator.workflow.executable_ir import workflow_executable_ir_to_json
from orchestrator.workflow.semantic_ir import workflow_semantic_ir_to_json
from orchestrator.workflow_lisp.compiler import compile_stage1_module, compile_stage3_module
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from orchestrator.workflow_lisp.expressions import elaborate_expression
from orchestrator.workflow_lisp.reader import read_sexpr_text
from orchestrator.workflow_lisp.syntax import SyntaxNode
from orchestrator.workflow_lisp.type_env import FrontendTypeEnvironment, TypeParamRef
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


def _compile(path: Path, *, tmp_path: Path, validate_shared: bool = False):
    return compile_stage3_module(
        path,
        provider_externs={"providers.execute": "test-provider"},
        prompt_externs={"prompts.implementation.execute": "prompts/implementation/execute.md"},
        validate_shared=validate_shared,
        workspace_root=tmp_path,
    )


def _assert_diagnostic_code(excinfo: pytest.ExceptionInfo[LispFrontendCompileError], code: str) -> None:
    assert excinfo.value.diagnostics[0].code == code


def _build_type_env(tmp_path: Path, extra_lines: list[str] | None = None) -> FrontendTypeEnvironment:
    path = _write_module(
        tmp_path / "loop_state_types.orc",
        [
            "(workflow-lisp",
            '  (:language "0.1")',
            '  (:target-dsl "2.14")',
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
    expr = elaborate_expression(
        _expression_syntax(
            '(loop-state (status String "ok") (report WorkReport report-path))'
        ),
        bound_names=frozenset({"report-path"}),
    )

    typed = typecheck_expression(
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

    assert type(typed.type_ref).__name__ == "RecordTypeRef"
    assert typed.type_ref.name.startswith("%loop-state.")
    assert typed.type_ref.field_types["status"].name == "String"
    assert typed.type_ref.field_types["report"].name == "WorkReport"


def test_typecheck_loop_state_update_preserves_carrier_type(tmp_path: Path) -> None:
    type_env = _build_type_env(tmp_path)
    expr = elaborate_expression(
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
    expr = elaborate_expression(
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


def test_typecheck_loop_state_rejects_non_projectable_field_type(tmp_path: Path) -> None:
    type_env = _build_type_env(tmp_path)
    expr = elaborate_expression(
        _expression_syntax("(loop-state (history List[String] history))"),
        bound_names=frozenset({"history"}),
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        typecheck_expression(
            expr,
            type_env=type_env,
            value_env={
                "history": type_env.resolve_type(
                    "List[String]",
                    span=expr.span,
                    form_path=expr.form_path,
                )
            },
        )

    _assert_diagnostic_code(excinfo, "loop_state_not_projectable")


def test_lowering_loop_state_seed_can_feed_loop_recur_state(tmp_path: Path) -> None:
    workflow_path = _write_module(
        tmp_path / "loop_state_seed_loop.orc",
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
            "  (defworkflow loop-state-seed-loop",
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
        ],
    )

    result = _compile(workflow_path, tmp_path=tmp_path, validate_shared=True)
    authored = result.lowered_workflows[0].authored_mapping
    repeat_step = next(step for step in authored["steps"] if "repeat_until" in step)

    assert "state__report" in repeat_step["repeat_until"]["outputs"]
    assert "state__done" in repeat_step["repeat_until"]["outputs"]


def test_lowering_loop_state_update_can_feed_continue(tmp_path: Path) -> None:
    workflow_path = _write_module(
        tmp_path / "loop_state_update_continue.orc",
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
            "  (defworkflow loop-state-update-continue",
            "    ((report-path WorkReport))",
            "    -> LoopResult",
            "    (loop/recur",
            "      :max 2",
            "      :state (loop-state",
            "               (report WorkReport report-path)",
            "               (done Bool false))",
            "      (fn (current)",
            "        (if current.done",
            "          (done (record LoopResult :report current.report))",
            "          (continue (loop-state :like current :done true)))))))",
        ],
    )

    result = _compile(workflow_path, tmp_path=tmp_path, validate_shared=True)
    authored = result.lowered_workflows[0].authored_mapping
    repeat_step = next(step for step in authored["steps"] if "repeat_until" in step)

    assert repeat_step["repeat_until"]["max_iterations"] == 2


def test_lowered_loop_state_generated_relpath_origin_tracks_authored_field_span(
    tmp_path: Path,
) -> None:
    workflow_path = _write_module(
        tmp_path / "loop_state_origin_map.orc",
        [
            "(workflow-lisp",
            '  (:language "0.1")',
            '  (:target-dsl "2.14")',
            "  (defpath WorkReport",
            "    :kind relpath",
            '    :under "artifacts/work"',
            "    :must-exist true)",
            "  (defunion LoopResult",
            "    (COMPLETED",
            "      (report WorkReport)))",
            "  (defworkflow loop-state-origin-map",
            "    ((report-path WorkReport))",
            "    -> LoopResult",
            "    (loop/recur",
            "      :max 1",
            "      :state (loop-state",
            "               (report WorkReport report-path)",
            "               (done Bool true))",
            "      (fn (current)",
            "        (done (variant LoopResult COMPLETED :report current.report))))))",
        ],
    )

    result = _compile(workflow_path, tmp_path=tmp_path, validate_shared=True)
    lowered = result.lowered_workflows[0]

    assert lowered.origin_map.generated_path_spans
    assert any(
        origin.span.start.path.endswith("loop_state_origin_map.orc")
        for origin in lowered.origin_map.generated_path_spans.values()
    )


def test_lowered_loop_state_artifacts_contain_no_type_param_or_proc_ref_leaks(
    tmp_path: Path,
) -> None:
    workflow_path = _write_module(
        tmp_path / "loop_state_validated_surface.orc",
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
            "  (defworkflow loop-state-validated-surface",
            "    ((report-path WorkReport))",
            "    -> LoopResult",
            "    (loop/recur",
            "      :max 2",
            "      :state (loop-state",
            "               (report WorkReport report-path)",
            "               (done Bool false))",
            "      (fn (current)",
            "        (if current.done",
            "          (done (record LoopResult :report current.report))",
            "          (continue (loop-state :like current :done true)))))))",
        ],
    )

    result = _compile(workflow_path, tmp_path=tmp_path, validate_shared=True)
    lowered = result.lowered_workflows[0]
    bundle = next(iter(result.validated_bundles.values()))
    serialized_payloads = (
        json.dumps(lowered.authored_mapping, sort_keys=True),
        json.dumps(workflow_executable_ir_to_json(bundle.ir), sort_keys=True),
        json.dumps(workflow_semantic_ir_to_json(bundle.semantic_ir), sort_keys=True),
    )

    for payload in serialized_payloads:
        assert "TypeParamRef" not in payload
        assert "ProcRef[" not in payload
        assert "%loop-state." not in payload
