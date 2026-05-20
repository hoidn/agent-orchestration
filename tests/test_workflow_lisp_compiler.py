"""Tests for the Workflow Lisp MVP parse/definition/expression compile entrypoints."""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest


EXPR_FIXTURES = Path(__file__).parent / "fixtures" / "workflow_lisp" / "expression_validation"
DEFINITION_FIXTURES = Path(__file__).parent / "fixtures" / "workflow_lisp" / "definitions"


def _fixture_path(name: str) -> Path:
    return EXPR_FIXTURES / name


def _definition_fixture_path(name: str) -> Path:
    return DEFINITION_FIXTURES / name


def _compiler_module():
    return importlib.import_module("orchestrator.workflow_lisp.compiler")


def _diagnostic_from_error(error: BaseException):
    diagnostic = getattr(error, "diagnostic", None)
    assert diagnostic is not None
    return diagnostic


def test_compile_workflow_module_text_runs_full_mvp_frontend_pipeline() -> None:
    compiler = _compiler_module()
    source_path = _fixture_path("valid_typed_expressions.orc")

    compiled = compiler.compile_workflow_module_text(
        source_path.read_text(encoding="utf-8"),
        source_path=str(source_path),
    )

    assert compiled.parsed_module.source_path == str(source_path)
    assert compiled.definition_module.source_path == str(source_path)
    assert compiled.expression_module.source_path == str(source_path)
    assert tuple(workflow.name for workflow in compiled.expression_module.workflows) == (
        "select_report",
        "read_plan",
    )


def test_compile_workflow_module_file_surfaces_expression_validation_diagnostic() -> None:
    compiler = _compiler_module()
    source_path = _fixture_path("invalid_variant_field_unproved.orc")

    with pytest.raises(Exception) as exc_info:
        compiler.compile_workflow_module_file(source_path)

    diagnostic = _diagnostic_from_error(exc_info.value)
    assert diagnostic.code == "variant_ref_unproved"
    assert "requires variant proof" in diagnostic.message
    assert diagnostic.source_file == str(source_path)
    assert diagnostic.enclosing_form_name == "field.access"
    assert diagnostic.generated_core_node_id == "bad.field.execution_report"


def test_compile_workflow_module_file_accepts_imported_type_references() -> None:
    compiler = _compiler_module()
    source_path = _definition_fixture_path("valid_imported_type_references.orc")

    compiled = compiler.compile_workflow_module_file(source_path)

    assert compiled.expression_module.source_path == str(source_path)
    assert tuple(workflow.name for workflow in compiled.expression_module.workflows) == ("run_phase",)
    assert compiled.expression_module.workflows[0].inferred_return_type == "ImplementationInputs"


def test_compile_workflow_module_file_accepts_local_procedure_calls() -> None:
    compiler = _compiler_module()
    source_path = _definition_fixture_path("valid_defprocs.orc")

    compiled = compiler.compile_workflow_module_file(source_path)

    assert compiled.expression_module.source_path == str(source_path)
    assert tuple(procedure.name for procedure in compiled.expression_module.procedures) == ("build_plan",)
    assert tuple(workflow.name for workflow in compiled.expression_module.workflows) == ("run_phase",)


def test_compile_workflow_module_file_preserves_function_definitions() -> None:
    compiler = _compiler_module()
    source_path = _definition_fixture_path("valid_defuns.orc")

    compiled = compiler.compile_workflow_module_file(source_path)

    assert compiled.expression_module.source_path == str(source_path)
    assert tuple(function.name for function in compiled.definition_module.function_definitions) == (
        "normalize_inputs",
        "normalize_path",
    )
    assert tuple(function.name for function in compiled.expression_module.functions) == (
        "normalize_inputs",
        "normalize_path",
    )
    assert tuple(function.inferred_return_type for function in compiled.expression_module.functions) == (
        "PlanInputs",
        "String",
    )
    assert tuple(workflow.name for workflow in compiled.expression_module.workflows) == ("run_phase",)


def test_compile_and_lower_workflow_module_file_runs_pipeline_through_lowering() -> None:
    compiler = _compiler_module()
    source_path = _fixture_path("valid_provider_command_result_expressions.orc")

    lowered = compiler.compile_and_lower_workflow_module_file(source_path)

    assert lowered.source_path == str(source_path)
    assert set(lowered.workflows) == {"execute_attempt", "run_checks"}
    assert lowered.workflows["run_checks"]["name"] == "run_checks"
    assert "run_checks.result" in lowered.source_map["run_checks"]


def test_compile_and_lower_workflow_module_text_runs_pipeline_through_lowering() -> None:
    compiler = _compiler_module()
    source_path = _fixture_path("valid_pathrel_contracts.orc")

    lowered = compiler.compile_and_lower_workflow_module_text(
        source_path.read_text(encoding="utf-8"),
        source_path=str(source_path),
    )

    assert lowered.source_path == str(source_path)
    assert tuple(lowered.workflows) == ("run_path",)
    assert lowered.workflows["run_path"]["name"] == "run_path"
