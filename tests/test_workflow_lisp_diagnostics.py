from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from orchestrator.workflow_lisp.compiler import compile_stage1_module
from orchestrator.workflow_lisp.diagnostics import (
    LispFrontendCompileError,
    LispFrontendDiagnostic,
    render_diagnostic,
    render_diagnostics,
)
from orchestrator.workflow_lisp.reader import read_sexpr_file
from orchestrator.workflow_lisp.spans import SourcePosition, SourceSpan
from orchestrator.workflow_lisp.syntax import build_syntax_module


FIXTURES = Path(__file__).parent / "fixtures" / "workflow_lisp"


def test_render_diagnostic_includes_location_and_form_path() -> None:
    start = SourcePosition(
        path="tests/fixtures/workflow_lisp/invalid/example.orc",
        line=3,
        column=5,
        offset=18,
    )
    end = SourcePosition(
        path="tests/fixtures/workflow_lisp/invalid/example.orc",
        line=3,
        column=14,
        offset=27,
    )
    span = SourceSpan(start=start, end=end)
    diagnostic = LispFrontendDiagnostic(
        code="frontend_parse_error",
        message="unexpected closing parenthesis",
        span=span,
        form_path=("workflow-lisp", "defrecord", "ChecksResult"),
        notes=("while reading field list",),
    )

    rendered = render_diagnostic(diagnostic)

    assert "tests/fixtures/workflow_lisp/invalid/example.orc:3:5" in rendered
    assert "[frontend_parse_error]" in rendered
    assert "unexpected closing parenthesis" in rendered
    assert "workflow-lisp > defrecord > ChecksResult" in rendered
    assert "while reading field list" in rendered
    assert render_diagnostics((diagnostic,)) == rendered

    with pytest.raises(FrozenInstanceError):
        diagnostic.message = "mutated"


def test_frontend_compile_error_exposes_diagnostics_tuple() -> None:
    span = SourceSpan(
        start=SourcePosition(path="module.orc", line=1, column=1, offset=0),
        end=SourcePosition(path="module.orc", line=1, column=6, offset=5),
    )
    diagnostics = (
        LispFrontendDiagnostic(
            code="definition_duplicate",
            message="duplicate definition `Thing`",
            span=span,
        ),
        LispFrontendDiagnostic(
            code="type_unknown",
            message="unknown type `Missing`",
            span=span,
        ),
    )

    error = LispFrontendCompileError(diagnostics)

    assert error.diagnostics == diagnostics
    assert isinstance(error.diagnostics, tuple)
    assert "[definition_duplicate]" in str(error)
    assert "[type_unknown]" in str(error)


def test_compile_stage1_renders_unknown_type_diagnostic_with_field_location() -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage1_module(FIXTURES / "invalid" / "unknown_type.orc")

    rendered = render_diagnostic(excinfo.value.diagnostics[0])

    assert "unknown_type.orc:5:5" in rendered
    assert "[type_unknown]" in rendered
    assert "unknown type `MissingType`" in rendered
    assert "workflow-lisp > defrecord > ChecksResult" in rendered


def test_compile_stage1_renders_unsupported_target_dsl_diagnostic() -> None:
    parse_tree = read_sexpr_file(FIXTURES / "invalid" / "unsupported_target_dsl.orc")

    with pytest.raises(LispFrontendCompileError) as excinfo:
        build_syntax_module(parse_tree)

    rendered = render_diagnostic(excinfo.value.diagnostics[0])

    assert "unsupported_target_dsl.orc:3:16" in rendered
    assert "[target_dsl_unsupported]" in rendered
    assert "unsupported target DSL `2.15`" in rendered


def test_compile_stage1_preserves_diagnostic_order(tmp_path: Path) -> None:
    path = tmp_path / "multiple_errors.orc"
    path.write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defrecord ProblemRecord",
                "    (status MissingA)",
                "    (status MissingB))",
                "  (defrecord ProblemRecord",
                "    (report MissingC)))",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage1_module(path)

    diagnostics = excinfo.value.diagnostics

    assert [diagnostic.code for diagnostic in diagnostics] == [
        "definition_duplicate",
        "record_field_duplicate",
        "type_unknown",
        "type_unknown",
        "type_unknown",
    ]
