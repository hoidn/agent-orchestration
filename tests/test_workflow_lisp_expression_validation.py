"""Tests for Workflow Lisp MVP expression validation."""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest


FIXTURES = Path(__file__).parent / "fixtures" / "workflow_lisp" / "expression_validation"
DEFINITION_FIXTURES = Path(__file__).parent / "fixtures" / "workflow_lisp" / "definitions"


def _fixture_path(name: str) -> Path:
    return FIXTURES / name


def _definition_fixture_path(name: str) -> Path:
    return DEFINITION_FIXTURES / name


def _parser_module():
    return importlib.import_module("orchestrator.workflow_lisp.parser")


def _definition_validation_module():
    return importlib.import_module("orchestrator.workflow_lisp.definition_validation")


def _expression_validation_module():
    return importlib.import_module("orchestrator.workflow_lisp.expression_validation")


def _diagnostic_from_error(error: BaseException):
    diagnostic = getattr(error, "diagnostic", None)
    assert diagnostic is not None
    return diagnostic


def _checked_module_from_fixture(name: str):
    parser = _parser_module()
    definition_validation = _definition_validation_module()
    source_path = _fixture_path(name)
    module = parser.parse_workflow_module_text(
        source_path.read_text(encoding="utf-8"),
        source_path=str(source_path),
    )
    return definition_validation.validate_definition_module(module)


def _checked_module_from_definition_fixture(name: str):
    parser = _parser_module()
    definition_validation = _definition_validation_module()
    source_path = _definition_fixture_path(name)
    module = parser.parse_workflow_module_text(
        source_path.read_text(encoding="utf-8"),
        source_path=str(source_path),
    )
    return definition_validation.validate_definition_module(module)


def test_validate_expression_module_accepts_typed_let_star_and_match() -> None:
    expression_validation = _expression_validation_module()
    checked = _checked_module_from_fixture("valid_typed_expressions.orc")

    result = expression_validation.validate_expression_module(checked)

    assert tuple(workflow.name for workflow in result.workflows) == ("select_report", "read_plan")
    assert result.workflows[0].inferred_return_type == "String"
    assert result.workflows[1].inferred_return_type == "String"


def test_validate_expression_module_accepts_record_expression() -> None:
    expression_validation = _expression_validation_module()
    checked = _checked_module_from_fixture("valid_record_expression.orc")

    result = expression_validation.validate_expression_module(checked)

    assert tuple(workflow.name for workflow in result.workflows) == ("build_plan",)
    assert result.workflows[0].inferred_return_type == "Plan"


def test_validate_expression_module_accepts_typed_call_expression() -> None:
    expression_validation = _expression_validation_module()
    checked = _checked_module_from_fixture("valid_call_expression.orc")

    result = expression_validation.validate_expression_module(checked)

    assert tuple(workflow.name for workflow in result.workflows) == ("build_plan", "run")
    assert result.workflows[1].inferred_return_type == "Plan"


def test_validate_expression_module_accepts_zero_argument_call_expression() -> None:
    expression_validation = _expression_validation_module()
    checked = _checked_module_from_fixture("valid_call_no_arguments.orc")

    result = expression_validation.validate_expression_module(checked)

    assert tuple(workflow.name for workflow in result.workflows) == ("build_plan", "run")
    assert result.workflows[1].inferred_return_type == "Plan"


def test_validate_expression_module_accepts_imported_call_with_explicit_returns() -> None:
    expression_validation = _expression_validation_module()
    checked = _checked_module_from_fixture("valid_call_imported_with_returns.orc")

    result = expression_validation.validate_expression_module(checked)

    assert tuple(workflow.name for workflow in result.workflows) == ("run",)
    assert result.workflows[0].inferred_return_type == "String"


def test_validate_expression_module_accepts_imported_call_with_explicit_returns_and_arguments() -> None:
    expression_validation = _expression_validation_module()
    checked = _checked_module_from_fixture("valid_call_imported_with_returns_and_arguments.orc")

    result = expression_validation.validate_expression_module(checked)

    assert tuple(workflow.name for workflow in result.workflows) == ("run",)
    assert result.workflows[0].inferred_return_type == "String"


def test_validate_expression_module_accepts_module_qualified_imported_call_with_explicit_returns() -> None:
    expression_validation = _expression_validation_module()
    checked = _checked_module_from_fixture("valid_call_imported_module_qualified_with_returns.orc")

    result = expression_validation.validate_expression_module(checked)

    assert tuple(workflow.name for workflow in result.workflows) == ("run",)
    assert result.workflows[0].inferred_return_type == "String"


def test_validate_expression_module_accepts_provider_and_command_result_expressions() -> None:
    expression_validation = _expression_validation_module()
    checked = _checked_module_from_fixture("valid_provider_command_result_expressions.orc")

    result = expression_validation.validate_expression_module(checked)

    assert tuple(workflow.name for workflow in result.workflows) == (
        "execute_attempt",
        "run_checks",
    )
    assert result.workflows[0].inferred_return_type == "Attempt"
    assert result.workflows[1].inferred_return_type == "Plan"


def test_validate_expression_module_accepts_with_phase_wrapped_provider_result() -> None:
    expression_validation = _expression_validation_module()
    checked = _checked_module_from_fixture("valid_with_phase_provider_result.orc")

    result = expression_validation.validate_expression_module(checked)

    assert tuple(workflow.name for workflow in result.workflows) == ("execute_attempt",)
    assert result.workflows[0].inferred_return_type == "Attempt"


def test_validate_expression_module_accepts_float_literals_and_types() -> None:
    expression_validation = _expression_validation_module()
    checked = _checked_module_from_fixture("valid_provider_result_float_expression.orc")

    result = expression_validation.validate_expression_module(checked)

    assert tuple(workflow.name for workflow in result.workflows) == ("run_metrics",)
    assert result.workflows[0].inferred_return_type == "Metrics"


def test_validate_expression_module_accepts_partial_non_exhaustive_match() -> None:
    expression_validation = _expression_validation_module()
    checked = _checked_module_from_fixture("valid_match_partial_non_exhaustive.orc")

    result = expression_validation.validate_expression_module(checked)

    assert tuple(workflow.name for workflow in result.workflows) == ("select_completed",)
    assert result.workflows[0].inferred_return_type == "String"


def test_validate_expression_module_accepts_nil_literal_expression() -> None:
    expression_validation = _expression_validation_module()
    checked = _checked_module_from_fixture("valid_nil_literal_expression.orc")

    result = expression_validation.validate_expression_module(checked)

    assert tuple(workflow.name for workflow in result.workflows) == ("emit_null",)
    assert result.workflows[0].inferred_return_type == "Json"


def test_validate_expression_module_accepts_imported_type_references() -> None:
    expression_validation = _expression_validation_module()
    checked = _checked_module_from_definition_fixture("valid_imported_type_references.orc")

    result = expression_validation.validate_expression_module(checked)

    assert tuple(workflow.name for workflow in result.workflows) == ("run_phase",)
    assert result.workflows[0].inferred_return_type == "ImplementationInputs"


def test_validate_expression_module_accepts_calls_to_local_procedures() -> None:
    expression_validation = _expression_validation_module()
    checked = _checked_module_from_definition_fixture("valid_defprocs.orc")

    result = expression_validation.validate_expression_module(checked)

    assert tuple(procedure.name for procedure in result.procedures) == ("build_plan",)
    assert result.procedures[0].inferred_return_type == "PlanResult"
    assert tuple(workflow.name for workflow in result.workflows) == ("run_phase",)
    assert result.workflows[0].inferred_return_type == "PlanResult"


def test_validate_expression_module_accepts_phase_target_expression() -> None:
    parser = _parser_module()
    definition_validation = _definition_validation_module()
    expression_validation = _expression_validation_module()
    source_path = str(_fixture_path("inline_phase_target.orc"))
    module = parser.parse_workflow_module_text(
        """
(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14"))

(defworkflow emit_target ((phase_ctx PathRel)) -> PathRel
  (phase-target phase_ctx progress-report))
""",
        source_path=source_path,
    )
    checked = definition_validation.validate_definition_module(module)

    result = expression_validation.validate_expression_module(checked)

    assert tuple(workflow.name for workflow in result.workflows) == ("emit_target",)
    assert result.workflows[0].inferred_return_type == "PathRel"


@pytest.mark.parametrize(
    ("fixture_name", "expected_code", "expected_message"),
    [
        ("invalid_unknown_reference.orc", "type_unknown", "Unknown reference: missing"),
        ("invalid_unknown_field.orc", "type_mismatch", "Unknown field missing on record type Plan"),
        (
            "invalid_variant_field_unproved.orc",
            "variant_ref_unproved",
            "Field execution_report on union type Attempt requires variant proof",
        ),
        ("invalid_match_non_exhaustive.orc", "union_match_non_exhaustive", "Non-exhaustive match over Attempt"),
        ("invalid_match_unknown_variant.orc", "union_variant_unknown", "Unknown match variant FAILED for union Attempt"),
        ("invalid_match_subject_not_union.orc", "type_mismatch", "match subject must be a union type"),
        ("invalid_workflow_return_mismatch.orc", "return_type_mismatch", "Workflow bad returns Int but declares String"),
        ("invalid_record_unknown_type.orc", "type_unknown", "Unknown record type: Missing"),
        ("invalid_record_missing_field.orc", "type_mismatch", "Record constructor for Plan is missing required field: status"),
        ("invalid_record_field_type_mismatch.orc", "type_mismatch", "Record field Plan.status expects String but got Int"),
        ("invalid_call_unknown_workflow.orc", "type_unknown", "Unknown workflow reference: missing_workflow"),
        (
            "invalid_call_imported_only_workflow_signature_erased.orc",
            "workflow_call_signature_erased",
            "Imported workflow call run_phase requires an explicit :returns type",
        ),
        (
            "invalid_call_imported_alias_workflow_signature_erased.orc",
            "workflow_call_signature_erased",
            "Imported workflow call remote/run_phase requires an explicit :returns type",
        ),
        (
            "invalid_call_imported_alias_only_unknown_workflow.orc",
            "type_unknown",
            "Unknown workflow reference: remote/run_phase",
        ),
        (
            "invalid_call_imported_only_unknown_qualified_workflow.orc",
            "type_unknown",
            "Unknown workflow reference: remote/workflows/other_phase",
        ),
        (
            "invalid_call_missing_argument.orc",
            "workflow_signature_mismatch",
            "Missing call argument for workflow build_plan: attempts",
        ),
        (
            "invalid_call_unknown_argument.orc",
            "workflow_signature_mismatch",
            "Unknown call argument for workflow build_plan: retries",
        ),
        (
            "invalid_call_argument_type_mismatch.orc",
            "type_mismatch",
            "Call argument build_plan.attempts expects Int but got String",
        ),
        (
            "invalid_provider_result_non_structured_return.orc",
            "type_mismatch",
            "provider-result :returns must reference a record or union type",
        ),
        (
            "invalid_command_result_non_structured_return.orc",
            "type_mismatch",
            "command-result :returns must reference a record or union type",
        ),
    ],
)
def test_validate_expression_module_rejects_invalid_expressions(
    fixture_name: str,
    expected_code: str,
    expected_message: str,
) -> None:
    expression_validation = _expression_validation_module()
    checked = _checked_module_from_fixture(fixture_name)
    source_path = _fixture_path(fixture_name)

    with pytest.raises(Exception) as exc_info:
        expression_validation.validate_expression_module(checked)

    diagnostic = _diagnostic_from_error(exc_info.value)
    assert diagnostic.code == expected_code
    assert expected_message in diagnostic.message
    assert diagnostic.source_file == str(source_path)


def test_validate_expression_module_variant_proof_error_includes_form_and_generated_node_id() -> None:
    expression_validation = _expression_validation_module()
    checked = _checked_module_from_fixture("invalid_variant_field_unproved.orc")

    with pytest.raises(Exception) as exc_info:
        expression_validation.validate_expression_module(checked)

    diagnostic = _diagnostic_from_error(exc_info.value)
    assert diagnostic.code == "variant_ref_unproved"
    assert diagnostic.enclosing_form_name == "field.access"
    assert diagnostic.generated_core_node_id == "bad.result"
