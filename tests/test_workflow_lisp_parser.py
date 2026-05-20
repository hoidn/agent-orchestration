"""Tests for Workflow Lisp tokenization and raw syntax reading."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
import importlib
from pathlib import Path

import pytest


FIXTURES = Path(__file__).parent / "fixtures" / "workflow_lisp" / "parser"


def _fixture_path(name: str) -> Path:
    return FIXTURES / name


def _fixture_text(name: str) -> str:
    return _fixture_path(name).read_text(encoding="utf-8")


def _parser_module():
    return importlib.import_module("orchestrator.workflow_lisp.parser")


def _syntax_module():
    return importlib.import_module("orchestrator.workflow_lisp.syntax")


def _diagnostic_from_error(error: BaseException):
    diagnostic = getattr(error, "diagnostic", None)
    assert diagnostic is not None
    return diagnostic


def test_tokenize_workflow_lisp_skips_comments_and_tracks_token_spans() -> None:
    parser = _parser_module()

    tokens = parser.tokenize_workflow_lisp(
        _fixture_text("comments_and_literals.orc"),
        source_path=str(_fixture_path("comments_and_literals.orc")),
    )

    assert [token.kind for token in tokens[:8]] == [
        "lparen",
        "symbol",
        "lparen",
        "keyword",
        "string",
        "rparen",
        "lparen",
        "keyword",
    ]
    assert [token.value for token in tokens[-8:]] == [
        ":values",
        "line\ntext",
        12,
        True,
        False,
        ":keyword",
        "symbol-name",
        ")",
    ]
    first_token = tokens[0]
    assert first_token.span.line_start == 2
    assert first_token.span.column_start == 1
    assert all(token.span.source_file.endswith(".orc") for token in tokens)


def test_read_syntax_forms_preserves_nested_structure_and_frozen_nodes() -> None:
    parser = _parser_module()
    syntax = _syntax_module()

    forms = parser.read_syntax_forms(
        _fixture_text("nested_forms.orc"),
        source_path=str(_fixture_path("nested_forms.orc")),
    )

    assert len(forms) == 2
    header_form, record_form = forms
    assert isinstance(header_form, syntax.SyntaxList)
    assert isinstance(record_form, syntax.SyntaxList)
    assert record_form.items[0].value == "defrecord"
    assert record_form.items[1].value == "Example"
    field_form = record_form.items[2]
    assert isinstance(field_form, syntax.SyntaxList)
    assert field_form.items[0].value == "field"
    assert field_form.items[1].value == "String"
    assert record_form.context.source_path == str(_fixture_path("nested_forms.orc"))
    assert record_form.context.module_name is None
    assert record_form.context.hygiene_marks == ()
    assert record_form.context.expansion_stack == ()
    with pytest.raises(FrozenInstanceError):
        record_form.items = ()


def test_read_syntax_forms_decodes_string_escapes_without_losing_source_coordinates() -> None:
    parser = _parser_module()
    syntax = _syntax_module()

    forms = parser.read_syntax_forms(
        _fixture_text("comments_and_literals.orc"),
        source_path=str(_fixture_path("comments_and_literals.orc")),
    )

    values_form = forms[1]
    assert isinstance(values_form, syntax.SyntaxList)
    string_atom = values_form.items[1]
    assert isinstance(string_atom, syntax.SyntaxAtom)
    assert string_atom.value == "line\ntext"
    assert string_atom.span.line_start == 6
    assert string_atom.span.column_start == 10
    assert string_atom.span.line_end == 6
    assert string_atom.span.column_end > string_atom.span.column_start


def test_tokenize_workflow_lisp_supports_float_literals() -> None:
    parser = _parser_module()

    tokens = parser.tokenize_workflow_lisp(
        "(values -1.25 0.5 2)",
        source_path=str(_fixture_path("nested_forms.orc")),
    )

    assert [token.kind for token in tokens] == [
        "lparen",
        "symbol",
        "float",
        "float",
        "int",
        "rparen",
    ]
    assert tokens[2].value == pytest.approx(-1.25)
    assert tokens[3].value == pytest.approx(0.5)


def test_tokenize_workflow_lisp_supports_nil_literals() -> None:
    parser = _parser_module()
    syntax = _syntax_module()

    tokens = parser.tokenize_workflow_lisp(
        "(values nil)",
        source_path=str(_fixture_path("nested_forms.orc")),
    )

    assert [token.kind for token in tokens] == [
        "lparen",
        "symbol",
        "nil",
        "rparen",
    ]
    assert tokens[2].value is None

    forms = parser.read_syntax_forms(
        "(values nil)",
        source_path=str(_fixture_path("nested_forms.orc")),
    )
    values_form = forms[0]
    nil_atom = values_form.items[1]
    assert nil_atom.kind is syntax.AtomKind.NIL
    assert nil_atom.value is None


def test_tokenize_workflow_lisp_supports_quoted_symbol_literals() -> None:
    parser = _parser_module()
    syntax = _syntax_module()

    tokens = parser.tokenize_workflow_lisp(
        "(values 'ready)",
        source_path=str(_fixture_path("nested_forms.orc")),
    )

    assert [token.kind for token in tokens] == [
        "lparen",
        "symbol",
        "quoted_symbol",
        "rparen",
    ]
    assert tokens[2].value == "ready"

    forms = parser.read_syntax_forms(
        "(values 'ready)",
        source_path=str(_fixture_path("nested_forms.orc")),
    )
    values_form = forms[0]
    quoted_symbol_atom = values_form.items[1]
    assert quoted_symbol_atom.kind is syntax.AtomKind.QUOTED_SYMBOL
    assert quoted_symbol_atom.value == "ready"


def test_tokenize_workflow_lisp_rejects_empty_quoted_symbol() -> None:
    parser = _parser_module()
    source_path = str(_fixture_path("nested_forms.orc"))

    with pytest.raises(Exception) as exc_info:
        parser.read_syntax_forms("(values ')", source_path=source_path)

    diagnostic = _diagnostic_from_error(exc_info.value)
    assert diagnostic.code == "frontend_parse_error"
    assert "Quoted symbol must include a symbol name" in diagnostic.message
    assert diagnostic.source_file == source_path
    assert diagnostic.line == 1
    assert diagnostic.column == 9


@pytest.mark.parametrize(
    ("fixture_name", "expected_line", "expected_column"),
    [
        ("invalid_unmatched_paren.orc", 3, 24),
        ("invalid_unterminated_string.orc", 2, 14),
    ],
)
def test_read_syntax_forms_reports_parse_diagnostics(
    fixture_name: str,
    expected_line: int,
    expected_column: int,
) -> None:
    parser = _parser_module()
    source_path = _fixture_path(fixture_name)

    with pytest.raises(Exception) as exc_info:
        parser.read_syntax_forms(
            source_path.read_text(encoding="utf-8"),
            source_path=str(source_path),
        )

    diagnostic = _diagnostic_from_error(exc_info.value)
    assert diagnostic.code == "frontend_parse_error"
    assert diagnostic.source_file == str(source_path)
    assert diagnostic.line == expected_line
    assert diagnostic.column == expected_column
    assert diagnostic.span.source_file == str(source_path)
    assert diagnostic.span.line_start == expected_line
    assert diagnostic.enclosing_form_name is None


def test_read_syntax_forms_rejects_bad_escape_sequences() -> None:
    parser = _parser_module()
    source_path = str(_fixture_path("comments_and_literals.orc"))
    source_text = '(:values "bad\\q")'

    with pytest.raises(Exception) as exc_info:
        parser.read_syntax_forms(source_text, source_path=source_path)

    diagnostic = _diagnostic_from_error(exc_info.value)
    assert diagnostic.code == "frontend_parse_error"
    assert diagnostic.source_file == source_path
    assert diagnostic.line == 1
    assert diagnostic.column == 14
    assert diagnostic.span.line_start == 1
    assert diagnostic.span.column_start == 14
    assert diagnostic.enclosing_form_name is None


@pytest.mark.parametrize(
    ("fixture_name", "expected_generated_core_node_id"),
    [
        ("invalid_unknown_header_clause.orc", None),
        ("invalid_defmodule_unsupported_language_name.orc", "module.header.language"),
    ],
)
def test_parse_workflow_module_text_emits_generated_node_ids_for_header_diagnostics(
    fixture_name: str,
    expected_generated_core_node_id: str | None,
) -> None:
    parser = _parser_module()
    source_path = _fixture_path(fixture_name)

    with pytest.raises(Exception) as exc_info:
        parser.parse_workflow_module_text(
            source_path.read_text(encoding="utf-8"),
            source_path=str(source_path),
        )

    diagnostic = _diagnostic_from_error(exc_info.value)
    assert diagnostic.code == "frontend_parse_error"
    assert diagnostic.source_file == str(source_path)
    assert diagnostic.generated_core_node_id == expected_generated_core_node_id
