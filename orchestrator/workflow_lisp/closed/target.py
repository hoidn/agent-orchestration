"""Target selection and availability checks for evaluated execution."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from orchestrator._common.safe_tree import resolve_path_preserving_fd
from orchestrator.workflow_lisp import syntax
from orchestrator.workflow_lisp.diagnostics import (
    LispFrontendCompileError,
    LispFrontendDiagnostic,
)
from orchestrator.workflow_lisp.reader import SourceReadTrace, read_sexpr_file, read_sexpr_text
from orchestrator.workflow_lisp.sexpr import KeywordAtom, ListExpr, StringAtom
from orchestrator.workflow_lisp.spans import SourceSpan


def _entry_target_header_from_tree(
    parse_tree: ListExpr,
) -> tuple[str, SourceSpan]:
    syntax_module = syntax.build_syntax_module(parse_tree)
    root = parse_tree.items[0]
    assert isinstance(root, ListExpr)
    for form in root.items[1:]:
        if (
            isinstance(form, ListExpr)
            and len(form.items) == 2
            and isinstance(form.items[0], KeywordAtom)
            and form.items[0].value == ":target-dsl"
            and isinstance(form.items[1], StringAtom)
        ):
            return syntax_module.target_dsl_version, form.items[1].span
    raise AssertionError("validated module is missing its :target-dsl header")


def _entry_target_header(
    path: Path,
    *,
    source_read_trace: SourceReadTrace | None = None,
) -> tuple[str, SourceSpan]:
    path = resolve_path_preserving_fd(path)
    return _entry_target_header_from_tree(
        read_sexpr_file(path, source_read_trace=source_read_trace)
    )


def _entry_target_header_from_bytes(
    path: Path,
    source_bytes: bytes,
) -> tuple[str, SourceSpan]:
    source_text = source_bytes.decode("utf-8", errors="strict")
    parser_text = source_text.replace("\r\n", "\n").replace("\r", "\n")
    parse_tree = read_sexpr_text(parser_text, source_path=str(path))
    return _entry_target_header_from_tree(parse_tree)


def entry_target_dsl_version(
    path: Path,
    *,
    source_read_trace: SourceReadTrace | None = None,
) -> str:
    """Return the target declared by one entry module without resolving imports."""

    target_dsl_version, _span = _entry_target_header(
        path, source_read_trace=source_read_trace
    )
    return target_dsl_version


def refuse_retired_entry_target(
    path: Path, *, source_read_trace: SourceReadTrace | None = None,
) -> None:
    """Admit executable entries without changing imported-module analysis."""
    target, span = _entry_target_header(path, source_read_trace=source_read_trace)
    if not syntax.target_dsl_uses_evaluated_execution(target):
        _raise_retired_execution_target(target, span)


def _raise_retired_execution_target(target: str, span: SourceSpan) -> None:
    raise LispFrontendCompileError((LispFrontendDiagnostic(
        code="workflow_execution_target_retired",
        message=(f"target DSL {target} execution is retired; use a separately retained "
                 "complete release/environment qualified for this source or run"),
        span=span, phase="lowering",
    ),))


def refuse_compiled_retired_entry_target(
    path: Path, target: str, source_bytes_by_path: Mapping[Path, bytes],
) -> None:
    """Guard publication against the compiler's captured entry, not a fresh peek."""
    if syntax.target_dsl_uses_evaluated_execution(target):
        return
    captured_target, span = _entry_target_header_from_bytes(path, source_bytes_by_path[path])
    if captured_target != target:
        raise RuntimeError("compiled entry target does not match its source snapshot")
    _raise_retired_execution_target(target, span)
