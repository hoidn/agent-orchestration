"""Retained typed command materialization and lexical capture decisions."""


import pytest

from orchestrator.workflow_lisp.expressions import FieldAccessExpr, IfExpr, LiteralExpr, NameExpr
from orchestrator.workflow_lisp.spans import SourcePosition, SourceSpan


SPAN = SourceSpan(
    start=SourcePosition(path="transport.orc", line=1, column=1, offset=0),
    end=SourcePosition(path="transport.orc", line=1, column=2, offset=1),
)


def _literal(value):
    return LiteralExpr(value=value, literal_kind="bool", span=SPAN, form_path=())


def _selection():
    return IfExpr(
        condition_expr=_literal(True), then_expr=_literal(True),
        else_expr=_literal(False), span=SPAN, form_path=(),
    )


@pytest.mark.parametrize(
    "expansion,existing,run_ref,provider,request_input,expected",
    [
        (False, None, False, False, False, "if_projection"),
        (False, None, True, False, False, "if_projection"),
        (False, None, False, True, True, "whole_value"),
        (False, None, False, False, True, "alias"),
        (False, None, True, False, True, "request_projection"),
        (True, None, True, True, True, "expansion_projection"),
    ],
)
def test_wcc_materialization_precedence(expansion, existing, run_ref, provider, request_input, expected):
    from orchestrator.workflow_lisp.closed.command_templates import wcc_binding_materialization

    expr = _selection()
    kind, value = wcc_binding_materialization(
        expr, expansion_owned=expansion, existing_ref=existing,
        resolved_binding=expr.then_expr, run_ref_demand=run_ref,
        provider_context_demand=provider, request_input_demand=request_input,
    )
    assert kind == expected
    assert value is (expr if expansion or run_ref or provider else expr.then_expr)


@pytest.mark.parametrize("existing,expected", [
    ("inputs.actual", "alias"), (_literal(True), "expansion_projection"),
    ({"field": "inputs.actual"}, "expansion_projection"), (None, "expansion_projection"),
])
def test_expansion_alias_requires_an_existing_direct_reference(existing, expected):
    from orchestrator.workflow_lisp.closed.command_templates import wcc_binding_materialization

    expr = NameExpr(name="actual", span=SPAN, form_path=())
    kind, value = wcc_binding_materialization(
        expr, expansion_owned=True, existing_ref=existing, resolved_binding=None,
        run_ref_demand=True, provider_context_demand=True, request_input_demand=True,
    )
    assert kind == expected
    assert value is (existing if expected == "alias" else expr)




def test_surface_binding_inline_and_projection_are_distinct_owners():
    from orchestrator.workflow_lisp.closed.command_templates import is_inline_let_binding_expr, surface_binding_materialization

    literal = _literal(True)
    selection = _selection()
    assert is_inline_let_binding_expr(literal)
    assert not is_inline_let_binding_expr(selection)
    assert surface_binding_materialization(selection, resolved_binding=literal) == ("projection", literal)




@pytest.mark.parametrize("resolved,run_ref,expected", [
    ("inputs.record.field", False, "alias"),
    ({"leaf": "inputs.record.field"}, False, "whole_value"),
    ("inputs.record.field", True, "alias"),
])
def test_provider_context_field_availability_precedes_request_projection(resolved, run_ref, expected):
    from orchestrator.workflow_lisp.closed.command_templates import wcc_binding_materialization

    expr = FieldAccessExpr(
        base=NameExpr(name="record", span=SPAN, form_path=()),
        fields=("field",), span=SPAN, form_path=(),
    )
    kind, value = wcc_binding_materialization(
        expr, expansion_owned=False, existing_ref=None, resolved_binding=resolved,
        run_ref_demand=run_ref, provider_context_demand=True,
        request_input_demand=False,
    )
    assert kind == expected
    assert value is (expr if run_ref or expected == "whole_value" else resolved)


def test_run_ref_resolver_override_alone_does_not_emit_a_projection():
    from orchestrator.workflow_lisp.closed.command_templates import wcc_binding_materialization

    expr = NameExpr(name="value", span=SPAN, form_path=())
    assert wcc_binding_materialization(
        expr, expansion_owned=False, existing_ref=None, resolved_binding=_literal(True),
        run_ref_demand=True, provider_context_demand=False, request_input_demand=False,
    ) == ("alias", expr)








def test_capture_order_preserves_sequential_shadowing_and_match_binders():
    from orchestrator.workflow_lisp.expressions import LetStarExpr, MatchArm, MatchExpr
    from orchestrator.workflow_lisp.closed.command_templates import helper_capture_names

    def name(value):
        return NameExpr(name=value, span=SPAN, form_path=())

    arm = MatchArm(
        variant_name="A", binding_name="c", body=IfExpr(
            condition_expr=name("flag"), then_expr=name("c"),
            else_expr=FieldAccessExpr(
                base=name("holder"), fields=("value",), span=SPAN, form_path=(),
            ),
            span=SPAN, form_path=(),
        ), span=SPAN, form_path=(),
    )
    expr = LetStarExpr(
        bindings=(("a", name("b")), ("b", name("a"))),
        body=MatchExpr(subject=name("choice"), arms=(arm,), span=SPAN, form_path=()),
        span=SPAN, form_path=(),
    )
    assert helper_capture_names(
        expr, local_type_bindings=dict.fromkeys(("flag", "a", "c", "b", "choice", "holder")),
    ) == ("flag", "b", "choice", "holder")




@pytest.mark.parametrize("workflow,iteration,boundary,body,expected", [
    ("run", True, True, True, True), ("%composition.arm.v1", True, True, True, False),
    ("run", False, True, True, False), ("run", True, False, True, False),
    ("run", True, True, False, False),
])
def test_schema1_private_override_requires_both_private_checks(
    monkeypatch, workflow, iteration, boundary, body, expected,
):
    from types import SimpleNamespace
    from orchestrator.workflow_lisp.procedure_specialization import (
        schema1_iteration_private_override_applies,
    )
    from orchestrator.workflow_lisp.procedures import ProcedureLoweringMode
    import orchestrator.workflow_lisp.procedure_specialization as owner
    import orchestrator.workflow_lisp.procedures as procedure_owner

    monkeypatch.setattr(procedure_owner, "procedure_type_env_for", lambda *a, **k: k["default"])
    checks = []
    monkeypatch.setattr(
        owner, "_procedure_private_boundary_valid",
        lambda *a, **k: checks.append("boundary") or boundary,
    )
    monkeypatch.setattr(
        owner, "_procedure_private_body_valid",
        lambda *a, **k: checks.append("body") or body,
    )
    procedure = SimpleNamespace(
        resolved_lowering_mode=ProcedureLoweringMode.INLINE,
        typed_body=SimpleNamespace(expr=_literal(True)),
    )
    assert schema1_iteration_private_override_applies(
        procedure, iteration_scope=object() if iteration else None,
        workflow_name=workflow, default_type_env=object(), typed_procedures={},
        procedure_type_envs={}, workflow_signatures={},
    ) is expected
    expected_checks = []
    if iteration and not workflow.startswith("%composition."):
        expected_checks.append("boundary")
        if boundary:
            expected_checks.append("body")
    assert checks == expected_checks




def test_inline_binding_merge_keeps_caller_specialization_actual_precedence():
    from types import SimpleNamespace
    from orchestrator.workflow_lisp.procedure_specialization import (inline_procedure_bindings)

    procedure = SimpleNamespace(
        signature=SimpleNamespace(params=(("actual", object()),)),
        specialization=SimpleNamespace(
            workflow_ref_bindings={"same": "workflow", "workflow": "forwarded"},
            proc_ref_bindings={"same": "proc"}, value_bindings={"same": "value", "actual": "bound"},
        ),
    )
    caller = {"same": "caller", "actual": "caller-actual", "untouched": "kept"}
    assert inline_procedure_bindings(procedure, caller_values=caller, actual_values=("resolved",)) == {
        "same": "value", "actual": "resolved", "untouched": "kept", "workflow": "forwarded",
    }
    assert caller == {"same": "caller", "actual": "caller-actual", "untouched": "kept"}
