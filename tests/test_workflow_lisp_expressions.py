"""Tests for Workflow Lisp MVP expression shaping."""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest


FIXTURES = Path(__file__).parent / "fixtures" / "workflow_lisp" / "expressions"


def _fixture_path(name: str) -> Path:
    return FIXTURES / name


def _parser_module():
    return importlib.import_module("orchestrator.workflow_lisp.parser")


def _definitions_module():
    return importlib.import_module("orchestrator.workflow_lisp.definitions")


def _expressions_module():
    return importlib.import_module("orchestrator.workflow_lisp.expressions")


def _diagnostic_from_error(error: BaseException):
    diagnostic = getattr(error, "diagnostic", None)
    assert diagnostic is not None
    return diagnostic


def _workflow_body_expression_from_fixture(fixture_name: str):
    parser = _parser_module()
    definitions = _definitions_module()
    source_path = _fixture_path(fixture_name)

    module = parser.parse_workflow_module_text(
        source_path.read_text(encoding="utf-8"),
        source_path=str(source_path),
    )
    workflow_defs = definitions.shape_module_workflow_definitions(module)
    assert len(workflow_defs) == 1
    assert len(workflow_defs[0].body_forms) == 1
    return workflow_defs[0].body_forms[0]


def _workflow_body_expression_from_source(source_text: str, *, source_name: str):
    parser = _parser_module()
    definitions = _definitions_module()
    source_path = str(_fixture_path(source_name))
    module = parser.parse_workflow_module_text(source_text, source_path=source_path)
    workflow_defs = definitions.shape_module_workflow_definitions(module)
    assert len(workflow_defs) == 1
    assert len(workflow_defs[0].body_forms) == 1
    return workflow_defs[0].body_forms[0]


def test_shape_expression_parses_symbol_field_access_chain() -> None:
    expressions = _expressions_module()
    body_node = _workflow_body_expression_from_fixture("valid_field_access_symbol.orc")

    shaped = expressions.shape_expression(body_node)

    assert isinstance(shaped, expressions.FieldAccessExpression)
    assert shaped.field_name == "path"
    mid = shaped.base
    assert isinstance(mid, expressions.FieldAccessExpression)
    assert mid.field_name == "design"
    root = mid.base
    assert isinstance(root, expressions.ReferenceExpression)
    assert root.name == "inputs"


def test_shape_expression_parses_let_star_bindings_and_body() -> None:
    expressions = _expressions_module()
    body_node = _workflow_body_expression_from_fixture("valid_let_star.orc")

    shaped = expressions.shape_expression(body_node)

    assert isinstance(shaped, expressions.LetStarExpression)
    assert tuple(binding.name for binding in shaped.bindings) == ("candidate", "status")
    assert isinstance(shaped.bindings[0].value, expressions.FieldAccessExpression)
    assert isinstance(shaped.bindings[1].value, expressions.LiteralExpression)
    assert shaped.bindings[1].value.value == "ready"
    assert isinstance(shaped.body, expressions.ReferenceExpression)
    assert shaped.body.name == "candidate"


def test_shape_expression_parses_match_expression_arms() -> None:
    expressions = _expressions_module()
    body_node = _workflow_body_expression_from_fixture("valid_match.orc")

    shaped = expressions.shape_expression(body_node)

    assert isinstance(shaped, expressions.MatchExpression)
    assert isinstance(shaped.subject, expressions.ReferenceExpression)
    assert shaped.subject.name == "attempt"
    assert tuple(arm.variant_name for arm in shaped.arms) == ("COMPLETED", "BLOCKED")
    assert shaped.arms[0].binding_name == "done"
    assert isinstance(shaped.arms[0].body, expressions.FieldAccessExpression)
    assert shaped.arms[1].binding_name == "blocked"
    assert isinstance(shaped.arms[1].body, expressions.FieldAccessExpression)


def test_shape_expression_parses_match_expression_partial_flag() -> None:
    expressions = _expressions_module()
    body_node = _workflow_body_expression_from_fixture("valid_match_partial.orc")

    shaped = expressions.shape_expression(body_node)

    assert isinstance(shaped, expressions.MatchExpression)
    assert shaped.partial is True
    assert tuple(arm.variant_name for arm in shaped.arms) == ("COMPLETED", "BLOCKED")


def test_shape_expression_parses_record_expression() -> None:
    expressions = _expressions_module()
    body_node = _workflow_body_expression_from_fixture("valid_record.orc")

    shaped = expressions.shape_expression(body_node)

    assert isinstance(shaped, expressions.RecordExpression)
    assert shaped.type_name == "Plan"
    assert tuple(field.field_name for field in shaped.fields) == ("path", "status")
    assert isinstance(shaped.fields[0].value, expressions.ReferenceExpression)
    assert shaped.fields[0].value.name == "candidate_path"
    assert isinstance(shaped.fields[1].value, expressions.LiteralExpression)
    assert shaped.fields[1].value.value == "draft"


def test_shape_expression_parses_call_expression() -> None:
    expressions = _expressions_module()
    body_node = _workflow_body_expression_from_fixture("valid_call.orc")

    shaped = expressions.shape_expression(body_node)

    assert isinstance(shaped, expressions.CallExpression)
    assert shaped.callee_name == "build_plan"
    assert tuple(argument.parameter_name for argument in shaped.arguments) == (
        "design_path",
        "attempts",
    )
    assert isinstance(shaped.arguments[0].value, expressions.ReferenceExpression)
    assert shaped.arguments[0].value.name == "design_path"
    assert isinstance(shaped.arguments[1].value, expressions.LiteralExpression)
    assert shaped.arguments[1].value.value == 2


def test_shape_expression_parses_call_expression_without_arguments() -> None:
    expressions = _expressions_module()
    body_node = _workflow_body_expression_from_fixture("valid_call_no_arguments.orc")

    shaped = expressions.shape_expression(body_node)

    assert isinstance(shaped, expressions.CallExpression)
    assert shaped.callee_name == "build_plan"
    assert shaped.arguments == ()


def test_shape_expression_parses_imported_call_expression_with_returns() -> None:
    expressions = _expressions_module()
    body_node = _workflow_body_expression_from_fixture("valid_call_imported_with_returns.orc")

    shaped = expressions.shape_expression(body_node)

    assert isinstance(shaped, expressions.CallExpression)
    assert shaped.callee_name == "remote/run_phase"
    assert shaped.arguments == ()
    assert shaped.returns_type_name == "String"


def test_shape_expression_parses_imported_call_expression_with_returns_and_arguments() -> None:
    expressions = _expressions_module()
    body_node = _workflow_body_expression_from_fixture("valid_call_imported_with_returns_and_arguments.orc")

    shaped = expressions.shape_expression(body_node)

    assert isinstance(shaped, expressions.CallExpression)
    assert shaped.callee_name == "remote/run_phase"
    assert tuple(argument.parameter_name for argument in shaped.arguments) == ("design_path",)
    assert isinstance(shaped.arguments[0].value, expressions.ReferenceExpression)
    assert shaped.arguments[0].value.name == "design_path"
    assert shaped.returns_type_name == "String"


def test_shape_expression_parses_provider_result_expression() -> None:
    expressions = _expressions_module()
    body_node = _workflow_body_expression_from_fixture("valid_provider_result.orc")

    shaped = expressions.shape_expression(body_node)

    assert isinstance(shaped, expressions.ProviderResultExpression)
    assert shaped.provider_reference.name == "execute_provider"
    assert shaped.prompt_reference.name == "execute_prompt"
    assert shaped.returns_type_name == "Attempt"
    assert len(shaped.inputs) == 1
    assert isinstance(shaped.inputs[0], expressions.ReferenceExpression)
    assert shaped.inputs[0].name == "design_path"


def test_shape_expression_parses_command_result_expression() -> None:
    expressions = _expressions_module()
    body_node = _workflow_body_expression_from_fixture("valid_command_result.orc")

    shaped = expressions.shape_expression(body_node)

    assert isinstance(shaped, expressions.CommandResultExpression)
    assert shaped.command_name == "run_checks"
    assert shaped.returns_type_name == "Plan"
    assert len(shaped.argv) == 3
    assert isinstance(shaped.argv[0], expressions.LiteralExpression)
    assert shaped.argv[0].value == "python"
    assert isinstance(shaped.argv[2], expressions.ReferenceExpression)
    assert shaped.argv[2].name == "design_path"


def test_shape_expression_parses_nil_literal_expression() -> None:
    expressions = _expressions_module()
    body_node = _workflow_body_expression_from_fixture("valid_nil_literal.orc")

    shaped = expressions.shape_expression(body_node)

    assert isinstance(shaped, expressions.LiteralExpression)
    assert shaped.kind is expressions.AtomKind.NIL
    assert shaped.value is None


def test_shape_expression_parses_with_phase_expression() -> None:
    expressions = _expressions_module()
    body_node = _workflow_body_expression_from_fixture("valid_with_phase.orc")

    shaped = expressions.shape_expression(body_node)

    assert isinstance(shaped, expressions.WithPhaseExpression)
    assert isinstance(shaped.context, expressions.ReferenceExpression)
    assert shaped.context.name == "phase_ctx"
    assert shaped.phase_name == "implementation"
    assert isinstance(shaped.body, expressions.ProviderResultExpression)


def test_shape_expression_parses_phase_target_expression() -> None:
    expressions = _expressions_module()
    body_node = _workflow_body_expression_from_source(
        """
(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14"))

(defworkflow emit_target ((phase_ctx PathRel)) -> PathRel
  (phase-target phase_ctx progress-report))
""",
        source_name="inline_valid_phase_target.orc",
    )

    shaped = expressions.shape_expression(body_node)

    assert isinstance(shaped, expressions.PhaseTargetExpression)
    assert isinstance(shaped.context, expressions.ReferenceExpression)
    assert shaped.context.name == "phase_ctx"
    assert shaped.target_name == "progress-report"


@pytest.mark.parametrize(
    ("fixture_name", "expected_message"),
    [
        ("invalid_let_star_duplicate_binding.orc", "Duplicate let* binding name"),
        ("invalid_let_star_bad_binding_shape.orc", "let* bindings must be (name expression) pairs"),
        ("invalid_match_duplicate_variant.orc", "Duplicate match arm variant"),
        ("invalid_match_bad_arm_shape.orc", "match arms must have shape ((VARIANT binding) expression)"),
        ("invalid_match_partial_non_bool.orc", "match :partial value must be a boolean"),
        ("invalid_record_duplicate_field.orc", "Duplicate record field"),
        ("invalid_record_bad_clause_shape.orc", "record fields must be keyword/expression pairs"),
        ("invalid_call_duplicate_argument.orc", "Duplicate call argument"),
        ("invalid_call_bad_clause_shape.orc", "call arguments must be keyword/expression pairs"),
        (
            "invalid_provider_result_bad_clause_shape.orc",
            "provider-result :inputs value must be an expression list",
        ),
        (
            "invalid_command_result_bad_argv_shape.orc",
            "command-result :argv value must be an expression list",
        ),
        (
            "invalid_with_phase_bad_phase_name.orc",
            "with-phase phase name must be a symbol",
        ),
        (
            "inline_invalid_phase_target_bad_target.orc",
            "phase-target target name must be a symbol",
        ),
        ("invalid_unsupported_expression_form.orc", "Unsupported expression form: if"),
    ],
)
def test_shape_expression_rejects_invalid_let_star_or_unsupported_forms(
    fixture_name: str,
    expected_message: str,
) -> None:
    expressions = _expressions_module()
    if fixture_name.startswith("inline_invalid_phase_target"):
        body_node = _workflow_body_expression_from_source(
            """
(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14"))

(defworkflow bad_target ((phase_ctx PathRel)) -> PathRel
  (phase-target phase_ctx "progress-report"))
""",
            source_name=fixture_name,
        )
        source_path = _fixture_path(fixture_name)
    else:
        body_node = _workflow_body_expression_from_fixture(fixture_name)
        source_path = _fixture_path(fixture_name)

    with pytest.raises(Exception) as exc_info:
        expressions.shape_expression(body_node)

    diagnostic = _diagnostic_from_error(exc_info.value)
    assert diagnostic.code == "frontend_parse_error"
    assert expected_message in diagnostic.message
    assert diagnostic.source_file == str(source_path)
