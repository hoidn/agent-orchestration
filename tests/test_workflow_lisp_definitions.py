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
    assert len(module.definitions) == 4

    enum_def, path_def, record_def, union_def = module.definitions
    assert isinstance(enum_def, EnumDef)
    assert [value.name for value in enum_def.values] == [
        "missing_resource",
        "roadmap_conflict",
    ]
    assert enum_def.values[0].span.start.line == 5

    assert isinstance(path_def, PathDef)
    assert path_def.kind == "relpath"
    assert path_def.under == "artifacts/work"
    assert path_def.must_exist is True

    assert isinstance(record_def, RecordDef)
    assert [field.name for field in record_def.fields] == ["status", "report"]
    assert record_def.fields[1].type_name == "WorkReport"

    assert isinstance(union_def, UnionDef)
    assert [variant.name for variant in union_def.variants] == ["COMPLETED", "BLOCKED"]
    assert union_def.variants[1].fields[1].name == "blocker_class"
    assert union_def.variants[1].fields[1].type_name == "BlockerClass"


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
