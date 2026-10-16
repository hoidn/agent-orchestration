from __future__ import annotations

from copy import deepcopy

import pytest

from orchestrator.workflow.evaluated.capture import CapturedRun
from orchestrator.workflow.evaluated.values import EvaluatedValue, LexicalEnvironment
from orchestrator.workflow_lisp import repl_expr
from orchestrator.workflow_lisp.closed.names import canonical_type_descriptor
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from orchestrator.workflow_lisp.effects import UsesProviderEffect
from orchestrator.workflow_lisp.type_env import PrimitiveTypeRef, RecordTypeRef
from tests.test_workflow_lisp_repl_introspection import loaded_catalog


def _captured(bindings, parent=None) -> CapturedRun:
    return CapturedRun(
        environment=LexicalEnvironment(bindings, parent),
        position="fixture",
        halted=False,
        result=None,
        snapshot=None,
        authority=None,
    )


def test_type_query_checks_module_only_literals_and_escaped_strings(loaded_catalog):
    module, _forms, _paths = loaded_catalog

    typed, captured_types, values = repl_expr.typecheck_repl_expression("42", module)
    assert typed.type_ref.name == "Int"
    assert captured_types == {}
    assert values["providers.review"].name == "Provider"
    assert values["prompts.external"].name == "Prompt"

    typed, _, _ = repl_expr.typecheck_repl_expression(
        r'"two words, \"quoted\" and \\path"', module
    )
    assert typed.type_ref.name == "String"

    with pytest.raises(repl_expr.ReplRefusal) as error:
        repl_expr.typecheck_repl_expression("1 2", module)
    assert error.value.code == "repl_expression_arity"


def test_type_query_resolves_imported_names_and_nearest_captured_binding(loaded_catalog):
    module, _forms, _paths = loaded_catalog
    plan_ref = next(
        ref
        for ref in module._binding_refs.values()
        if isinstance(ref, RecordTypeRef) and ref.name == "proof/types::Plan"
    )
    string_ref = next(
        ref
        for ref in module._binding_refs.values()
        if isinstance(ref, PrimitiveTypeRef) and ref.name == "String"
    )
    plan = EvaluatedValue(
        {"title": "fixture", "status": "READY"},
        canonical_type_descriptor(plan_ref, typed=module.typed_program),
    )
    shadowed_parent = LexicalEnvironment({
        "plan": EvaluatedValue("parent", canonical_type_descriptor(string_ref, typed=module.typed_program))
    })
    captured = _captured({"plan": plan}, shadowed_parent)

    typed, captured_types, values = repl_expr.typecheck_repl_expression(
        "(types.hidden-fn plan)", module, captured
    )
    assert typed.type_ref.name == "String"
    assert captured_types["plan"].name == "proof/types::Plan"
    assert values["plan"].name == "proof/types::Plan"

    typed, _, _ = repl_expr.typecheck_repl_expression(
        "(types.hidden-proc plan)", module, captured
    )
    assert typed.type_ref.name == "proof/types::Plan"

    typed, _, _ = repl_expr.typecheck_repl_expression("plan", module, captured)
    assert typed.type_ref.name == "proof/types::Plan"

    typed, _, _ = repl_expr.typecheck_repl_expression(
        '(let* ((plan "local")) plan)', module, captured
    )
    assert typed.type_ref.name == "String"

    typed, _, _ = repl_expr.typecheck_repl_expression('(Collision "module-only")', module)
    assert typed.type_ref.name == "String"


def test_type_query_reports_ordinary_name_errors(loaded_catalog):
    module, _forms, _paths = loaded_catalog
    with pytest.raises(LispFrontendCompileError) as error:
        repl_expr.typecheck_repl_expression("missing-name", module)
    assert any(item.code == "name_unknown" for item in error.value.diagnostics)

    with pytest.raises(LispFrontendCompileError) as error:
        repl_expr.typecheck_repl_expression('(+ 1 "not an integer")', module)
    assert error.value.diagnostics
    assert all(item.code != "name_unknown" for item in error.value.diagnostics)


def test_type_query_accepts_effectful_and_undefined_arithmetic_without_execution(
    loaded_catalog, monkeypatch
):
    module, _forms, _paths = loaded_catalog
    plan_ref = next(
        ref
        for ref in module._binding_refs.values()
        if isinstance(ref, RecordTypeRef) and ref.name == "proof/types::Plan"
    )
    plan = EvaluatedValue(
        {"title": "fixture", "status": "READY"},
        canonical_type_descriptor(plan_ref, typed=module.typed_program),
    )
    captured = _captured({"plan": plan})

    def unexpected_boundary(*_args, **_kwargs):
        pytest.fail("type query crossed a lowering or evaluation boundary")

    for name in (
        "_prepare_command_owner",
        "_install_prepared_requests",
        "_prepare_computed_capture_requests",
        "body",
    ):
        monkeypatch.setattr(module.builder, name, unexpected_boundary)
    monkeypatch.setattr(repl_expr, "_require_pure_lowered", unexpected_boundary)
    monkeypatch.setattr(repl_expr, "evaluate_closed_value", unexpected_boundary)

    definitions_before = deepcopy(module.builder.definitions)
    types_before = deepcopy(module.builder.nominal_types)
    type_refs_before = dict(module.type_env._type_refs)
    frame_before = captured.environment
    bindings_before = dict(frame_before.bindings)

    typed, _, _ = repl_expr.typecheck_repl_expression(
        "(effectful-proc plan)", module, captured
    )
    assert typed.type_ref.name == "proof/types::Plan"
    assert typed.effect_summary.transitive_effects == frozenset(
        {UsesProviderEffect(subject=("providers", "review"))}
    )

    typed, _, _ = repl_expr.typecheck_repl_expression(
        '(/ 1.0 (if (= plan.title "fixture") 0.0 1.0))', module, captured
    )
    assert typed.type_ref.name == "Float"

    assert module.builder.definitions == definitions_before
    assert module.builder.nominal_types == types_before
    assert module.type_env._type_refs == type_refs_before
    assert captured.environment is frame_before
    assert dict(captured.environment.bindings) == bindings_before


def test_type_query_without_module_context_keeps_literals_and_refuses_calls(loaded_catalog):
    from dataclasses import replace

    module, _forms, _paths = loaded_catalog
    module.stage3 = replace(module.stage3, expression_context=None)
    for expression in ("42", "(+ 1 2)"):
        typed, captured_types, values = repl_expr.typecheck_repl_expression(expression, module)
        assert typed.type_ref.name == "Int"
        assert captured_types == {}
        assert values["providers.review"].name == "Provider"

    with pytest.raises(repl_expr.ReplRefusal) as error:
        repl_expr.typecheck_repl_expression("(call missing)", module)
    assert error.value.code == "repl_module_context_missing"
