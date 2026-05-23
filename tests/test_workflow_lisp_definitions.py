from pathlib import Path

import pytest

from orchestrator.workflow_lisp.compiler import compile_stage1_module
from orchestrator.workflow_lisp.definitions import (
    EnumDef,
    PathDef,
    RecordDef,
    UnionDef,
    elaborate_definition_module,
)
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from orchestrator.workflow_lisp.reader import read_sexpr_file
from orchestrator.workflow_lisp.syntax import build_syntax_module


FIXTURES = Path(__file__).parent / "fixtures" / "workflow_lisp"


def test_elaborate_definition_module_supports_stage1_type_forms() -> None:
    syntax_module = build_syntax_module(
        read_sexpr_file(FIXTURES / "valid" / "type_definitions.orc")
    )

    module = elaborate_definition_module(syntax_module)

    assert module.language_version == "0.1"
    assert module.target_dsl_version == "2.14"
    assert len(module.definitions) == 6

    enum_def = module.definitions[0]
    path_def = module.definitions[1]
    checks_result_def = module.definitions[2]
    implementation_summary_def = module.definitions[3]
    nested_summary_def = module.definitions[4]
    union_def = module.definitions[5]
    assert isinstance(enum_def, EnumDef)
    assert [value.name for value in enum_def.values] == [
        "missing_resource",
        "unavailable_hardware",
        "roadmap_conflict",
        "external_dependency_outside_authority",
        "user_decision_required",
        "unrecoverable_after_fix_attempt",
    ]
    assert enum_def.values[0].span.start.line == 5

    assert isinstance(path_def, PathDef)
    assert path_def.kind == "relpath"
    assert path_def.under == "artifacts/work"
    assert path_def.must_exist is True

    assert isinstance(checks_result_def, RecordDef)
    assert [field.name for field in checks_result_def.fields] == ["status", "report"]
    assert checks_result_def.fields[1].type_name == "WorkReport"

    assert isinstance(implementation_summary_def, RecordDef)
    assert [field.name for field in implementation_summary_def.fields] == ["status", "report"]
    assert implementation_summary_def.fields[1].type_name == "WorkReport"

    assert isinstance(nested_summary_def, RecordDef)
    assert [field.name for field in nested_summary_def.fields] == ["summary"]
    assert nested_summary_def.fields[0].type_name == "ImplementationSummary"

    assert isinstance(union_def, UnionDef)
    assert [variant.name for variant in union_def.variants] == ["COMPLETED", "BLOCKED"]
    assert union_def.variants[1].fields[1].name == "blocker_class"
    assert union_def.variants[1].fields[1].type_name == "BlockerClass"


def test_elaborate_definition_module_supports_defschema_and_expands_schema_includes() -> None:
    syntax_module = build_syntax_module(
        read_sexpr_file(FIXTURES / "valid" / "defschema_type_definitions.orc")
    )

    module = elaborate_definition_module(syntax_module)

    assert len(module.definitions) == 4
    assert hasattr(module, "schemas")
    assert [schema.name for schema in module.schemas] == ["ReportTargets", "ReviewTargets"]

    implementation_summary = module.definitions[2]
    implementation_state = module.definitions[3]

    assert isinstance(implementation_summary, RecordDef)
    assert [field.name for field in implementation_summary.fields] == [
        "status",
        "execution_report",
        "review_report",
    ]
    assert [field.type_name for field in implementation_summary.fields] == [
        "String",
        "WorkReport",
        "WorkReport",
    ]

    assert isinstance(implementation_state, UnionDef)
    assert [field.name for field in implementation_state.variants[0].fields] == [
        "execution_report"
    ]
    assert [field.name for field in implementation_state.variants[1].fields] == [
        "status",
        "execution_report",
        "review_report",
        "blocker_class",
    ]


def test_elaboration_rejects_unknown_top_level_form() -> None:
    syntax_module = build_syntax_module(
        read_sexpr_file(FIXTURES / "invalid" / "unknown_top_level_form.orc")
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        elaborate_definition_module(syntax_module)

    diagnostic = excinfo.value.diagnostics[0]
    assert diagnostic.code == "definition_form_unknown"
    assert "defworkflow" in diagnostic.message


def test_elaboration_rejects_invalid_defpath_shape() -> None:
    syntax_module = build_syntax_module(
        read_sexpr_file(FIXTURES / "invalid" / "path_missing_under.orc")
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        elaborate_definition_module(syntax_module)

    diagnostic = excinfo.value.diagnostics[0]
    assert diagnostic.code == "path_definition_invalid"
    assert "missing required keyword `:under`" in diagnostic.message


def test_compile_stage1_reports_duplicate_definition() -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage1_module(FIXTURES / "invalid" / "duplicate_definition.orc")

    diagnostic = excinfo.value.diagnostics[0]
    assert diagnostic.code == "definition_duplicate"
    assert "WorkReport" in diagnostic.message


def test_compile_stage1_reports_unknown_type_with_field_span() -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage1_module(FIXTURES / "invalid" / "unknown_type.orc")

    diagnostic = excinfo.value.diagnostics[0]
    assert diagnostic.code == "type_unknown"
    assert "MissingType" in diagnostic.message
    assert diagnostic.span.start.line == 5
    assert diagnostic.span.start.column == 5


def test_compile_stage1_reports_unknown_schema_include() -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage1_module(FIXTURES / "invalid" / "defschema_unknown_schema.orc")

    diagnostic = excinfo.value.diagnostics[0]
    assert diagnostic.code == "schema_unknown"
    assert "MissingTargets" in diagnostic.message


def test_compile_stage1_reports_schema_cycles() -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage1_module(FIXTURES / "invalid" / "defschema_cycle.orc")

    diagnostic = excinfo.value.diagnostics[0]
    assert diagnostic.code == "schema_cycle"
    assert "ReportTargets" in diagnostic.message


def test_compile_stage1_reports_duplicate_fields_from_schema_expansion() -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage1_module(FIXTURES / "invalid" / "defschema_duplicate_field.orc")

    diagnostic = excinfo.value.diagnostics[0]
    assert diagnostic.code == "record_field_duplicate"
    assert "report" in diagnostic.message


def test_compile_stage1_reports_schema_used_as_type() -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage1_module(FIXTURES / "invalid" / "defschema_used_as_type.orc")

    diagnostic = excinfo.value.diagnostics[0]
    assert diagnostic.code == "schema_used_as_type"
    assert "ReportTargets" in diagnostic.message


def test_compile_stage1_reports_schema_used_as_nested_collection_type(tmp_path: Path) -> None:
    path = tmp_path / "schema_nested_collection.orc"
    path.write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defpath WorkReport",
                "    :kind relpath",
                '    :under "artifacts/work"',
                "    :must-exist true)",
                "  (defschema ReportTargets",
                "    (execution_report WorkReport))",
                "  (defrecord InvalidCollection",
                "    (reports List[ReportTargets])))",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage1_module(path)

    diagnostic = excinfo.value.diagnostics[0]
    assert diagnostic.code == "schema_used_as_type"
    assert "ReportTargets" in diagnostic.message


def test_compile_stage1_rejects_defworkflow_top_level_forms() -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage1_module(FIXTURES / "valid" / "structured_results.orc")

    diagnostic = excinfo.value.diagnostics[0]
    assert diagnostic.code == "definition_form_unknown"
    assert "defworkflow" in diagnostic.message


def test_compile_stage1_allows_forward_type_references(tmp_path: Path) -> None:
    path = tmp_path / "forward_refs.orc"
    path.write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defrecord ChecksResult",
                "    (report WorkReport))",
                "  (defpath WorkReport",
                "    :kind relpath",
                '    :under "artifacts/work"',
                "    :must-exist true))",
            ]
        ),
        encoding="utf-8",
    )

    module = compile_stage1_module(path)

    assert len(module.definitions) == 2
    assert isinstance(module.definitions[0], RecordDef)
    assert module.definitions[0].fields[0].type_name == "WorkReport"


def test_compile_stage1_rejects_duplicate_record_fields() -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage1_module(FIXTURES / "invalid" / "duplicate_record_field.orc")

    diagnostic = excinfo.value.diagnostics[0]
    assert diagnostic.code == "record_field_duplicate"
    assert "status" in diagnostic.message


def test_compile_stage1_rejects_duplicate_union_variants() -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage1_module(FIXTURES / "invalid" / "duplicate_union_variant.orc")

    diagnostic = excinfo.value.diagnostics[0]
    assert diagnostic.code == "union_variant_duplicate"
    assert "COMPLETED" in diagnostic.message
