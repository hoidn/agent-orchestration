from pathlib import Path

import pytest

from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from orchestrator.workflow_lisp.reader import read_sexpr_file, read_sexpr_text
from orchestrator.workflow_lisp.sexpr import BoolAtom, IntAtom, KeywordAtom, ListExpr, StringAtom, SymbolAtom
from orchestrator.workflow_lisp.syntax import build_syntax_module


FIXTURES = Path(__file__).parent / "fixtures" / "workflow_lisp"


def test_reader_preserves_spans_for_nested_lists_and_atoms() -> None:
    module = read_sexpr_text(
        '(root :flag true (child 7 "ok"))',
        source_path="inline.orc",
    )

    assert isinstance(module, ListExpr)
    assert len(module.items) == 1
    root = module.items[0]
    assert isinstance(root, ListExpr)
    assert root.span.start.line == 1
    assert root.span.start.column == 1
    assert root.span.start.offset == 0
    assert root.span.end.line == 1
    assert root.span.end.column == 33
    assert root.span.end.offset == 32

    name, keyword, boolean, child = root.items
    assert isinstance(name, SymbolAtom)
    assert name.value == "root"
    assert name.span.start.column == 2
    assert name.span.end.column == 6

    assert isinstance(keyword, KeywordAtom)
    assert keyword.value == ":flag"
    assert keyword.span.start.column == 7
    assert keyword.span.end.column == 12

    assert isinstance(boolean, BoolAtom)
    assert boolean.value is True
    assert boolean.span.start.column == 13
    assert boolean.span.end.column == 17

    assert isinstance(child, ListExpr)
    assert child.span.start.column == 18
    assert child.span.end.column == 32

    child_name, child_int, child_string = child.items
    assert isinstance(child_name, SymbolAtom)
    assert child_name.value == "child"
    assert child_name.span.start.column == 19
    assert child_name.span.end.column == 24

    assert isinstance(child_int, IntAtom)
    assert child_int.value == 7
    assert child_int.span.start.column == 25
    assert child_int.span.end.column == 26

    assert isinstance(child_string, StringAtom)
    assert child_string.value == "ok"
    assert child_string.span.start.column == 27
    assert child_string.span.end.column == 31


def test_reader_ignores_line_comments() -> None:
    source = "\n".join(
        [
            "; leading comment",
            "(workflow-lisp ; trailing comment",
            '  (:language "0.1"))',
            "; final comment",
        ]
    )

    module = read_sexpr_text(source, source_path="comments.orc")

    assert isinstance(module, ListExpr)
    assert len(module.items) == 1
    workflow_lisp = module.items[0]
    assert isinstance(workflow_lisp, ListExpr)
    assert len(workflow_lisp.items) == 2
    assert isinstance(workflow_lisp.items[0], SymbolAtom)
    assert workflow_lisp.items[0].value == "workflow-lisp"
    assert isinstance(workflow_lisp.items[1], ListExpr)


def test_reader_preserves_generic_type_atom_as_one_symbol() -> None:
    module = read_sexpr_text(
        "(defrecord X (field List[Optional[String]]))",
        source_path="inline.orc",
    )

    record_form = module.items[0]
    assert isinstance(record_form, ListExpr)
    field_form = record_form.items[2]
    assert isinstance(field_form, ListExpr)

    atom = field_form.items[1]
    assert isinstance(atom, SymbolAtom)
    assert atom.value == "List[Optional[String]]"


def test_reader_reports_unclosed_list_with_frontend_parse_error() -> None:
    path = FIXTURES / "invalid" / "unclosed_list.orc"

    with pytest.raises(LispFrontendCompileError) as excinfo:
        read_sexpr_file(path)

    diagnostic = excinfo.value.diagnostics[0]
    assert diagnostic.code == "frontend_parse_error"
    assert diagnostic.span.start.path.endswith("unclosed_list.orc")
    assert "unclosed" in diagnostic.message


def test_reader_reports_unterminated_string_with_frontend_parse_error() -> None:
    path = FIXTURES / "invalid" / "unterminated_string.orc"

    with pytest.raises(LispFrontendCompileError) as excinfo:
        read_sexpr_file(path)

    diagnostic = excinfo.value.diagnostics[0]
    assert diagnostic.code == "frontend_parse_error"
    assert diagnostic.span.start.path.endswith("unterminated_string.orc")
    assert "unterminated string" in diagnostic.message


def test_reader_rejects_quoted_phase_target_symbol_with_frontend_parse_error() -> None:
    path = FIXTURES / "invalid" / "phase_target_quoted_symbol_invalid.orc"

    with pytest.raises(LispFrontendCompileError) as excinfo:
        read_sexpr_file(path)

    diagnostic = excinfo.value.diagnostics[0]
    assert diagnostic.code == "frontend_parse_error"
    assert diagnostic.span.start.path.endswith("phase_target_quoted_symbol_invalid.orc")


def test_build_syntax_module_requires_workflow_lisp_root() -> None:
    parse_tree = read_sexpr_text(
        '(not-workflow-lisp (:language "0.1") (:target-dsl "2.14"))',
        source_path="invalid_root.orc",
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        build_syntax_module(parse_tree)

    diagnostic = excinfo.value.diagnostics[0]
    assert diagnostic.code == "frontend_parse_error"
    assert "workflow-lisp" in diagnostic.message


def test_build_syntax_module_rejects_unsupported_target_dsl() -> None:
    parse_tree = read_sexpr_file(FIXTURES / "invalid" / "unsupported_target_dsl.orc")

    with pytest.raises(LispFrontendCompileError) as excinfo:
        build_syntax_module(parse_tree)

    diagnostic = excinfo.value.diagnostics[0]
    assert diagnostic.code == "target_dsl_unsupported"
    assert diagnostic.span.start.line == 3
    assert diagnostic.span.start.column == 16


def test_build_syntax_module_assigns_form_paths_to_top_level_forms() -> None:
    parse_tree = read_sexpr_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defrecord ChecksResult",
                "    (status String)))",
            ]
        ),
        source_path="paths.orc",
    )

    module = build_syntax_module(parse_tree)

    assert module.language_version == "0.1"
    assert module.target_dsl_version == "2.14"
    assert len(module.forms) == 1
    assert module.forms[0].form_path == ("workflow-lisp", "defrecord", "ChecksResult")


def test_build_syntax_module_requires_language_header() -> None:
    parse_tree = read_sexpr_text(
        '(workflow-lisp (:target-dsl "2.14") (defenum Approval APPROVE))',
        source_path="missing_language.orc",
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        build_syntax_module(parse_tree)

    diagnostic = excinfo.value.diagnostics[0]
    assert diagnostic.code == "frontend_parse_error"
    assert "missing required header `:language`" in diagnostic.message


def test_build_syntax_module_rejects_unknown_header_keyword() -> None:
    parse_tree = read_sexpr_text(
        '(workflow-lisp (:language "0.1") (:target-dsl "2.14") (:unknown true))',
        source_path="unknown_header.orc",
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        build_syntax_module(parse_tree)

    diagnostic = excinfo.value.diagnostics[0]
    assert diagnostic.code == "frontend_parse_error"
    assert "unknown header keyword `:unknown`" in diagnostic.message
