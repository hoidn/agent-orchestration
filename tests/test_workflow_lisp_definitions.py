"""Tests for Workflow Lisp top-level definition shaping."""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest


FIXTURES = Path(__file__).parent / "fixtures" / "workflow_lisp" / "definitions"


def _fixture_path(name: str) -> Path:
    return FIXTURES / name


def _parser_module():
    return importlib.import_module("orchestrator.workflow_lisp.parser")


def _definitions_module():
    return importlib.import_module("orchestrator.workflow_lisp.definitions")


def _diagnostic_from_error(error: BaseException):
    diagnostic = getattr(error, "diagnostic", None)
    assert diagnostic is not None
    return diagnostic


def test_shape_module_definitions_shapes_supported_defenum_forms() -> None:
    parser = _parser_module()
    definitions = _definitions_module()
    source_path = _fixture_path("valid_enums.orc")

    module = parser.parse_workflow_module_text(
        source_path.read_text(encoding="utf-8"),
        source_path=str(source_path),
    )
    shaped = definitions.shape_module_definitions(module)

    assert len(shaped) == 2
    first = shaped[0]
    assert isinstance(first, definitions.EnumDefinition)
    assert first.name == "Outcome"
    assert first.values == ("CONTINUE", "BLOCKED", "DONE")
    assert first.name_span.source_file == str(source_path)
    assert first.form_span.line_start == 5


def test_shape_module_definitions_shapes_supported_defpath_forms() -> None:
    parser = _parser_module()
    definitions = _definitions_module()
    source_path = _fixture_path("valid_paths.orc")

    module = parser.parse_workflow_module_text(
        source_path.read_text(encoding="utf-8"),
        source_path=str(source_path),
    )
    shaped = definitions.shape_module_definitions(module)

    assert len(shaped) == 2
    path_definition = shaped[1]
    assert isinstance(path_definition, definitions.PathDefinition)
    assert path_definition.name == "WorkReport"
    assert path_definition.kind == "relpath"
    assert path_definition.under == "artifacts/work"
    assert path_definition.must_exist is True
    assert path_definition.name_span.source_file == str(source_path)
    assert path_definition.form_span.line_start == 6


def test_shape_module_definitions_shapes_supported_defrecord_and_defunion_forms() -> None:
    parser = _parser_module()
    definitions = _definitions_module()
    source_path = _fixture_path("valid_records_unions.orc")

    module = parser.parse_workflow_module_text(
        source_path.read_text(encoding="utf-8"),
        source_path=str(source_path),
    )
    shaped = definitions.shape_module_definitions(module)

    assert len(shaped) == 3
    record_definition = shaped[1]
    assert isinstance(record_definition, definitions.RecordDefinition)
    assert record_definition.name == "ChecksResult"
    assert tuple(field.name for field in record_definition.fields) == ("checks_report", "status")
    assert tuple(field.type_ref.name for field in record_definition.fields) == ("WorkReport", "String")

    union_definition = shaped[2]
    assert isinstance(union_definition, definitions.UnionDefinition)
    assert union_definition.name == "ImplementationAttempt"
    assert tuple(variant.name for variant in union_definition.variants) == ("COMPLETED", "BLOCKED")
    completed = union_definition.variants[0]
    assert tuple(field.name for field in completed.fields) == ("execution_report",)
    assert completed.fields[0].type_ref.name == "WorkReport"


def test_shape_module_definitions_shapes_supported_defschema_forms() -> None:
    parser = _parser_module()
    definitions = _definitions_module()

    module = parser.parse_workflow_module_text(
        """
(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14"))

(defschema PromptEnvelope
  (provider Provider)
  (prompt Prompt))
""",
        source_path="inline_defschema.orc",
    )
    shaped = definitions.shape_module_definitions(module)

    assert len(shaped) == 1
    schema_definition = shaped[0]
    assert isinstance(schema_definition, definitions.SchemaDefinition)
    assert schema_definition.name == "PromptEnvelope"
    assert tuple(field.name for field in schema_definition.fields) == ("provider", "prompt")
    assert tuple(field.type_ref.name for field in schema_definition.fields) == ("Provider", "Prompt")


def test_shape_module_definitions_rejects_duplicate_enum_values() -> None:
    parser = _parser_module()
    definitions = _definitions_module()
    source_path = _fixture_path("invalid_defenum_duplicate_value.orc")

    module = parser.parse_workflow_module_text(
        source_path.read_text(encoding="utf-8"),
        source_path=str(source_path),
    )

    with pytest.raises(Exception) as exc_info:
        definitions.shape_module_definitions(module)

    diagnostic = _diagnostic_from_error(exc_info.value)
    assert diagnostic.code == "frontend_parse_error"
    assert "Duplicate defenum value" in diagnostic.message
    assert diagnostic.enclosing_form_name == "defenum"
    assert diagnostic.source_file == str(source_path)


@pytest.mark.parametrize(
    ("fixture_name", "expected_message"),
    [
        ("invalid_defpath_missing_under.orc", "defpath requires :under"),
        ("invalid_defpath_bad_must_exist.orc", "defpath :must-exist value must be a boolean literal"),
    ],
)
def test_shape_module_definitions_rejects_invalid_defpath_clauses(
    fixture_name: str,
    expected_message: str,
) -> None:
    parser = _parser_module()
    definitions = _definitions_module()
    source_path = _fixture_path(fixture_name)

    module = parser.parse_workflow_module_text(
        source_path.read_text(encoding="utf-8"),
        source_path=str(source_path),
    )

    with pytest.raises(Exception) as exc_info:
        definitions.shape_module_definitions(module)

    diagnostic = _diagnostic_from_error(exc_info.value)
    assert diagnostic.code == "frontend_parse_error"
    assert expected_message in diagnostic.message
    assert diagnostic.enclosing_form_name == "defpath"
    assert diagnostic.source_file == str(source_path)


@pytest.mark.parametrize(
    ("fixture_name", "expected_message", "expected_form"),
    [
        ("invalid_defrecord_duplicate_field.orc", "Duplicate defrecord field name", "defrecord"),
        ("invalid_defunion_duplicate_variant.orc", "Duplicate defunion variant name", "defunion"),
        ("invalid_defunion_duplicate_variant_field.orc", "Duplicate field name in defunion variant", "defunion"),
    ],
)
def test_shape_module_definitions_rejects_duplicate_record_or_union_names(
    fixture_name: str,
    expected_message: str,
    expected_form: str,
) -> None:
    parser = _parser_module()
    definitions = _definitions_module()
    source_path = _fixture_path(fixture_name)

    module = parser.parse_workflow_module_text(
        source_path.read_text(encoding="utf-8"),
        source_path=str(source_path),
    )

    with pytest.raises(Exception) as exc_info:
        definitions.shape_module_definitions(module)

    diagnostic = _diagnostic_from_error(exc_info.value)
    assert diagnostic.code == "frontend_parse_error"
    assert expected_message in diagnostic.message
    assert diagnostic.enclosing_form_name == expected_form
    assert diagnostic.source_file == str(source_path)


def test_shape_module_workflow_definitions_shapes_defworkflow_signatures() -> None:
    parser = _parser_module()
    definitions = _definitions_module()
    source_path = _fixture_path("valid_workflows.orc")

    module = parser.parse_workflow_module_text(
        source_path.read_text(encoding="utf-8"),
        source_path=str(source_path),
    )
    shaped = definitions.shape_module_workflow_definitions(module)

    assert len(shaped) == 2
    run = shaped[0]
    assert isinstance(run, definitions.WorkflowDefinition)
    assert run.name == "run_phase"
    assert tuple(parameter.name for parameter in run.parameters) == ("inputs", "provider")
    assert tuple(parameter.type_ref.name for parameter in run.parameters) == ("ImplementationInputs", "Provider")
    assert run.return_type.name == "ImplementationResult"
    assert len(run.body_forms) == 1
    assert run.body_forms[0].value == "inputs"


def test_shape_module_procedure_definitions_shapes_defproc_signatures() -> None:
    parser = _parser_module()
    definitions = _definitions_module()
    source_path = _fixture_path("valid_defprocs.orc")

    module = parser.parse_workflow_module_text(
        source_path.read_text(encoding="utf-8"),
        source_path=str(source_path),
    )
    shaped = definitions.shape_module_procedure_definitions(module)

    assert len(shaped) == 1
    build_plan = shaped[0]
    assert isinstance(build_plan, definitions.ProcedureDefinition)
    assert build_plan.name == "build_plan"
    assert tuple(parameter.name for parameter in build_plan.parameters) == ("inputs", "provider")
    assert tuple(parameter.type_ref.name for parameter in build_plan.parameters) == ("PlanInputs", "Provider")
    assert build_plan.return_type.name == "PlanResult"
    assert len(build_plan.body_forms) == 1


def test_shape_module_function_definitions_shapes_defun_signatures() -> None:
    parser = _parser_module()
    definitions = _definitions_module()
    source_path = _fixture_path("valid_defuns.orc")

    module = parser.parse_workflow_module_text(
        source_path.read_text(encoding="utf-8"),
        source_path=str(source_path),
    )
    shaped = definitions.shape_module_function_definitions(module)

    assert len(shaped) == 2
    normalize_inputs = shaped[0]
    assert isinstance(normalize_inputs, definitions.FunctionDefinition)
    assert normalize_inputs.name == "normalize_inputs"
    assert tuple(parameter.name for parameter in normalize_inputs.parameters) == ("inputs",)
    assert tuple(parameter.type_ref.name for parameter in normalize_inputs.parameters) == ("PlanInputs",)
    assert normalize_inputs.return_type.name == "PlanInputs"
    assert len(normalize_inputs.body_forms) == 1

def test_shape_module_definitions_allows_import_export_module_forms() -> None:
    parser = _parser_module()
    definitions = _definitions_module()
    source_path = _fixture_path("valid_module_imports_exports.orc")

    module = parser.parse_workflow_module_text(
        source_path.read_text(encoding="utf-8"),
        source_path=str(source_path),
    )
    shaped = definitions.shape_module_definitions(module)
    workflows = definitions.shape_module_workflow_definitions(module)

    assert tuple(definition.name for definition in shaped) == (
        "ImplementationInputs",
        "ImplementationResult",
    )
    assert tuple(workflow.name for workflow in workflows) == ("run_phase",)


@pytest.mark.parametrize(
    ("fixture_name", "expected_message", "expected_generated_core_node_id"),
    [
        ("invalid_defworkflow_missing_arrow.orc", "defworkflow requires -> before return type", "run_phase.result"),
        ("invalid_defworkflow_duplicate_parameter.orc", "Duplicate defworkflow parameter name", "run_phase.input.inputs"),
    ],
)
def test_shape_module_workflow_definitions_rejects_invalid_defworkflow_signature(
    fixture_name: str,
    expected_message: str,
    expected_generated_core_node_id: str,
) -> None:
    parser = _parser_module()
    definitions = _definitions_module()
    source_path = _fixture_path(fixture_name)

    module = parser.parse_workflow_module_text(
        source_path.read_text(encoding="utf-8"),
        source_path=str(source_path),
    )

    with pytest.raises(Exception) as exc_info:
        definitions.shape_module_workflow_definitions(module)

    diagnostic = _diagnostic_from_error(exc_info.value)
    assert diagnostic.code == "frontend_parse_error"
    assert expected_message in diagnostic.message
    assert diagnostic.enclosing_form_name == "defworkflow"
    assert diagnostic.source_file == str(source_path)
    assert diagnostic.generated_core_node_id == expected_generated_core_node_id


def test_shape_module_procedure_definitions_rejects_duplicate_defproc_parameter_with_generated_node_id() -> None:
    parser = _parser_module()
    definitions = _definitions_module()

    module = parser.parse_workflow_module_text(
        """
(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14"))

(defproc build_plan ((inputs PlanInputs) (inputs PlanInputs)) -> PlanResult
  inputs)
""",
        source_path="inline_invalid_defproc_duplicate_parameter.orc",
    )

    with pytest.raises(Exception) as exc_info:
        definitions.shape_module_procedure_definitions(module)

    diagnostic = _diagnostic_from_error(exc_info.value)
    assert diagnostic.code == "frontend_parse_error"
    assert "Duplicate defproc parameter name" in diagnostic.message
    assert diagnostic.enclosing_form_name == "defproc"
    assert diagnostic.generated_core_node_id == "build_plan.input.inputs"
