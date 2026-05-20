"""Tests for Workflow Lisp definition-phase validation."""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest


FIXTURES = Path(__file__).parent / "fixtures" / "workflow_lisp" / "definitions"


def _fixture_path(name: str) -> Path:
    return FIXTURES / name


def _parser_module():
    return importlib.import_module("orchestrator.workflow_lisp.parser")


def _validation_module():
    return importlib.import_module("orchestrator.workflow_lisp.definition_validation")


def _diagnostic_from_error(error: BaseException):
    diagnostic = getattr(error, "diagnostic", None)
    assert diagnostic is not None
    return diagnostic


def test_validate_definition_module_returns_immutable_definition_table() -> None:
    parser = _parser_module()
    validation = _validation_module()
    source_path = _fixture_path("valid_enums.orc")

    module = parser.parse_workflow_module_text(
        source_path.read_text(encoding="utf-8"),
        source_path=str(source_path),
    )
    checked = validation.validate_definition_module(module)

    assert checked.source_path == str(source_path)
    assert checked.language_version == "0.1"
    assert checked.target_dsl == "2.14"
    assert tuple(checked.definition_table) == ("Outcome", "BlockerClass")
    with pytest.raises(TypeError):
        checked.definition_table["New"] = checked.definitions[0]  # type: ignore[index]


def test_validate_definition_module_accepts_local_forward_type_references() -> None:
    parser = _parser_module()
    validation = _validation_module()
    source_path = _fixture_path("valid_records_unions.orc")

    module = parser.parse_workflow_module_text(
        source_path.read_text(encoding="utf-8"),
        source_path=str(source_path),
    )
    checked = validation.validate_definition_module(module)

    assert tuple(checked.definition_table) == (
        "WorkReport",
        "ChecksResult",
        "ImplementationAttempt",
    )


def test_validate_definition_module_accepts_imported_type_references() -> None:
    parser = _parser_module()
    validation = _validation_module()
    source_path = _fixture_path("valid_imported_type_references.orc")

    module = parser.parse_workflow_module_text(
        source_path.read_text(encoding="utf-8"),
        source_path=str(source_path),
    )
    checked = validation.validate_definition_module(module)

    assert tuple(checked.definition_table) == ("LocalInputs",)
    assert tuple(workflow.name for workflow in checked.workflow_definitions) == ("run_phase",)


@pytest.mark.parametrize(
    ("fixture_name", "expected_message"),
    [
        ("invalid_reserved_name.orc", "Reserved prelude name cannot be redefined"),
        ("invalid_duplicate_top_level_name.orc", "Duplicate top-level definition"),
    ],
)
def test_validate_definition_module_rejects_reserved_or_duplicate_names(
    fixture_name: str,
    expected_message: str,
) -> None:
    parser = _parser_module()
    validation = _validation_module()
    source_path = _fixture_path(fixture_name)

    module = parser.parse_workflow_module_text(
        source_path.read_text(encoding="utf-8"),
        source_path=str(source_path),
    )

    with pytest.raises(Exception) as exc_info:
        validation.validate_definition_module(module)

    diagnostic = _diagnostic_from_error(exc_info.value)
    assert diagnostic.code == "frontend_parse_error"
    assert expected_message in diagnostic.message
    assert diagnostic.source_file == str(source_path)


@pytest.mark.parametrize(
    ("fixture_name", "expected_node_id", "expected_form_name"),
    [
        ("invalid_unknown_type_record.orc", "ChecksResult.field.status", "defrecord"),
        ("invalid_unknown_type_union.orc", "Attempt.variant.COMPLETED.field.status", "defunion"),
    ],
)
def test_validate_definition_module_rejects_unknown_type_references(
    fixture_name: str,
    expected_node_id: str,
    expected_form_name: str,
) -> None:
    parser = _parser_module()
    validation = _validation_module()
    source_path = _fixture_path(fixture_name)

    module = parser.parse_workflow_module_text(
        source_path.read_text(encoding="utf-8"),
        source_path=str(source_path),
    )

    with pytest.raises(Exception) as exc_info:
        validation.validate_definition_module(module)

    diagnostic = _diagnostic_from_error(exc_info.value)
    assert diagnostic.code == "type_unknown"
    assert "Unknown type reference" in diagnostic.message
    assert diagnostic.source_file == str(source_path)
    assert diagnostic.generated_core_node_id == expected_node_id
    assert diagnostic.enclosing_form_name == expected_form_name


def test_validate_definition_module_rejects_unknown_import_alias_type_reference() -> None:
    parser = _parser_module()
    validation = _validation_module()
    source_path = _fixture_path("invalid_unknown_import_alias_type_reference.orc")

    module = parser.parse_workflow_module_text(
        source_path.read_text(encoding="utf-8"),
        source_path=str(source_path),
    )

    with pytest.raises(Exception) as exc_info:
        validation.validate_definition_module(module)

    diagnostic = _diagnostic_from_error(exc_info.value)
    assert diagnostic.code == "type_unknown"
    assert "Unknown type reference: wrong.WorkReport" in diagnostic.message
    assert diagnostic.source_file == str(source_path)


def test_validate_definition_module_rejects_unknown_type_references_in_defschema() -> None:
    parser = _parser_module()
    validation = _validation_module()

    module = parser.parse_workflow_module_text(
        """
(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14"))

(defschema PromptEnvelope
  (provider Provider)
  (status MissingType))
""",
        source_path="inline_invalid_defschema_unknown_type.orc",
    )

    with pytest.raises(Exception) as exc_info:
        validation.validate_definition_module(module)

    diagnostic = _diagnostic_from_error(exc_info.value)
    assert diagnostic.code == "type_unknown"
    assert "Unknown type reference: MissingType" in diagnostic.message
    assert diagnostic.enclosing_form_name == "defschema"
    assert diagnostic.generated_core_node_id == "PromptEnvelope.field.status"


def test_validate_definition_module_rejects_import_alias_type_not_listed_in_only() -> None:
    parser = _parser_module()
    validation = _validation_module()
    source_path = _fixture_path("invalid_import_alias_only_unknown_type_reference.orc")

    module = parser.parse_workflow_module_text(
        source_path.read_text(encoding="utf-8"),
        source_path=str(source_path),
    )

    with pytest.raises(Exception) as exc_info:
        validation.validate_definition_module(module)

    diagnostic = _diagnostic_from_error(exc_info.value)
    assert diagnostic.code == "type_unknown"
    assert "Unknown type reference: nt.ImplementationResult" in diagnostic.message
    assert diagnostic.source_file == str(source_path)


def test_validate_definition_module_shapes_workflow_definitions() -> None:
    parser = _parser_module()
    validation = _validation_module()
    source_path = _fixture_path("valid_workflows.orc")

    module = parser.parse_workflow_module_text(
        source_path.read_text(encoding="utf-8"),
        source_path=str(source_path),
    )
    checked = validation.validate_definition_module(module)

    assert tuple(checked.definition_table) == (
        "ImplementationInputs",
        "ImplementationResult",
    )
    assert tuple(workflow.name for workflow in checked.workflow_definitions) == (
        "run_phase",
        "run_review",
    )


def test_validate_definition_module_shapes_procedure_definitions() -> None:
    parser = _parser_module()
    validation = _validation_module()
    source_path = _fixture_path("valid_defprocs.orc")

    module = parser.parse_workflow_module_text(
        source_path.read_text(encoding="utf-8"),
        source_path=str(source_path),
    )
    checked = validation.validate_definition_module(module)

    assert tuple(procedure.name for procedure in checked.procedure_definitions) == ("build_plan",)
    assert tuple(workflow.name for workflow in checked.workflow_definitions) == ("run_phase",)


@pytest.mark.parametrize(
    ("fixture_name", "expected_node_id"),
    [
        ("invalid_unknown_type_workflow_parameter.orc", "run_phase.input.inputs"),
        ("invalid_unknown_type_workflow_return.orc", "run_phase.result"),
    ],
)
def test_validate_definition_module_rejects_unknown_workflow_signature_types(
    fixture_name: str,
    expected_node_id: str,
) -> None:
    parser = _parser_module()
    validation = _validation_module()
    source_path = _fixture_path(fixture_name)

    module = parser.parse_workflow_module_text(
        source_path.read_text(encoding="utf-8"),
        source_path=str(source_path),
    )

    with pytest.raises(Exception) as exc_info:
        validation.validate_definition_module(module)

    diagnostic = _diagnostic_from_error(exc_info.value)
    assert diagnostic.code == "type_unknown"
    assert "Unknown type reference" in diagnostic.message
    assert diagnostic.source_file == str(source_path)
    assert diagnostic.generated_core_node_id == expected_node_id
    assert diagnostic.enclosing_form_name == "defworkflow"


def test_validate_definition_module_rejects_duplicate_type_and_workflow_names() -> None:
    parser = _parser_module()
    validation = _validation_module()
    source_path = _fixture_path("invalid_duplicate_top_level_name_workflow.orc")

    module = parser.parse_workflow_module_text(
        source_path.read_text(encoding="utf-8"),
        source_path=str(source_path),
    )

    with pytest.raises(Exception) as exc_info:
        validation.validate_definition_module(module)

    diagnostic = _diagnostic_from_error(exc_info.value)
    assert diagnostic.code == "frontend_parse_error"
    assert "Duplicate top-level definition" in diagnostic.message
    assert diagnostic.source_file == str(source_path)


def test_validate_definition_module_rejects_duplicate_procedure_names() -> None:
    parser = _parser_module()
    validation = _validation_module()
    source_path = _fixture_path("invalid_duplicate_defproc_names.orc")

    module = parser.parse_workflow_module_text(
        source_path.read_text(encoding="utf-8"),
        source_path=str(source_path),
    )

    with pytest.raises(Exception) as exc_info:
        validation.validate_definition_module(module)

    diagnostic = _diagnostic_from_error(exc_info.value)
    assert diagnostic.code == "frontend_parse_error"
    assert "Duplicate top-level definition" in diagnostic.message
    assert diagnostic.source_file == str(source_path)


@pytest.mark.parametrize(
    ("fixture_name", "expected_node_id"),
    [
        ("invalid_unknown_type_defproc_parameter.orc", "build_plan.input.inputs"),
        ("invalid_unknown_type_defproc_return.orc", "build_plan.result"),
    ],
)
def test_validate_definition_module_rejects_unknown_procedure_signature_types(
    fixture_name: str,
    expected_node_id: str,
) -> None:
    parser = _parser_module()
    validation = _validation_module()
    source_path = _fixture_path(fixture_name)

    module = parser.parse_workflow_module_text(
        source_path.read_text(encoding="utf-8"),
        source_path=str(source_path),
    )

    with pytest.raises(Exception) as exc_info:
        validation.validate_definition_module(module)

    diagnostic = _diagnostic_from_error(exc_info.value)
    assert diagnostic.code == "type_unknown"
    assert "Unknown type reference" in diagnostic.message
    assert diagnostic.source_file == str(source_path)
    assert diagnostic.generated_core_node_id == expected_node_id
    assert diagnostic.enclosing_form_name == "defproc"


def test_validate_definition_module_rejects_duplicate_workflow_names() -> None:
    parser = _parser_module()
    validation = _validation_module()
    source_path = _fixture_path("invalid_duplicate_workflow_names.orc")

    module = parser.parse_workflow_module_text(
        source_path.read_text(encoding="utf-8"),
        source_path=str(source_path),
    )

    with pytest.raises(Exception) as exc_info:
        validation.validate_definition_module(module)

    diagnostic = _diagnostic_from_error(exc_info.value)
    assert diagnostic.code == "frontend_parse_error"
    assert "Duplicate top-level definition" in diagnostic.message
    assert diagnostic.source_file == str(source_path)


def test_validate_definition_module_shapes_module_imports_and_exports() -> None:
    parser = _parser_module()
    validation = _validation_module()
    source_path = _fixture_path("valid_module_imports_exports.orc")

    module = parser.parse_workflow_module_text(
        source_path.read_text(encoding="utf-8"),
        source_path=str(source_path),
    )
    checked = validation.validate_definition_module(module)

    assert tuple(import_node.module_ref for import_node in checked.import_definitions) == (
        "std/paths",
        "neurips/types",
    )
    assert checked.import_definitions[0].alias == "path"
    assert checked.import_definitions[1].only_names == ("UpstreamInputs", "UpstreamResult")
    assert checked.exported_names == ("ImplementationInputs", "ImplementationResult", "run_phase")


def test_validate_definition_module_rejects_export_of_unknown_name() -> None:
    parser = _parser_module()
    validation = _validation_module()
    source_path = _fixture_path("invalid_export_unknown_name.orc")

    module = parser.parse_workflow_module_text(
        source_path.read_text(encoding="utf-8"),
        source_path=str(source_path),
    )

    with pytest.raises(Exception) as exc_info:
        validation.validate_definition_module(module)

    diagnostic = _diagnostic_from_error(exc_info.value)
    assert diagnostic.code == "module_export_missing"
    assert "unknown name" in diagnostic.message
    assert diagnostic.source_file == str(source_path)
    assert diagnostic.generated_core_node_id == "module.export.MissingWorkflow"
    assert diagnostic.enclosing_form_name == "export"


@pytest.mark.parametrize(
    ("fixture_name", "expected_conflict_name", "expected_node_id"),
    [
        ("invalid_import_only_conflicts_between_imports.orc", "SharedType", "module.import.only.SharedType"),
        ("invalid_import_only_conflicts_with_reserved_name.orc", "String", "module.import.only.String"),
        (
            "invalid_import_only_conflicts_with_local_definition.orc",
            "ImplementationInputs",
            "module.import.only.ImplementationInputs",
        ),
        ("invalid_import_only_conflicts_with_workflow_name.orc", "run_phase", "module.import.only.run_phase"),
    ],
)
def test_validate_definition_module_rejects_ambiguous_import_only_names(
    fixture_name: str,
    expected_conflict_name: str,
    expected_node_id: str,
) -> None:
    parser = _parser_module()
    validation = _validation_module()
    source_path = _fixture_path(fixture_name)

    module = parser.parse_workflow_module_text(
        source_path.read_text(encoding="utf-8"),
        source_path=str(source_path),
    )

    with pytest.raises(Exception) as exc_info:
        validation.validate_definition_module(module)

    diagnostic = _diagnostic_from_error(exc_info.value)
    assert diagnostic.code == "module_import_ambiguous"
    assert expected_conflict_name in diagnostic.message
    assert diagnostic.source_file == str(source_path)
    assert diagnostic.generated_core_node_id == expected_node_id
    assert diagnostic.enclosing_form_name == "import"


@pytest.mark.parametrize(
    ("fixture_name", "expected_conflict_name", "expected_node_id"),
    [
        ("invalid_import_alias_conflicts_with_reserved_name.orc", "String", "module.import.alias.String"),
        ("invalid_import_alias_conflicts_with_local_definition.orc", "LocalInputs", "module.import.alias.LocalInputs"),
        ("invalid_import_alias_conflicts_with_workflow_name.orc", "run_phase", "module.import.alias.run_phase"),
        (
            "invalid_import_alias_conflicts_with_imported_only_name.orc",
            "SharedType",
            "module.import.alias.SharedType",
        ),
    ],
)
def test_validate_definition_module_rejects_ambiguous_import_alias_names(
    fixture_name: str,
    expected_conflict_name: str,
    expected_node_id: str,
) -> None:
    parser = _parser_module()
    validation = _validation_module()
    source_path = _fixture_path(fixture_name)

    module = parser.parse_workflow_module_text(
        source_path.read_text(encoding="utf-8"),
        source_path=str(source_path),
    )

    with pytest.raises(Exception) as exc_info:
        validation.validate_definition_module(module)

    diagnostic = _diagnostic_from_error(exc_info.value)
    assert diagnostic.code == "module_import_ambiguous"
    assert expected_conflict_name in diagnostic.message
    assert diagnostic.source_file == str(source_path)
    assert diagnostic.generated_core_node_id == expected_node_id
    assert diagnostic.enclosing_form_name == "import"
