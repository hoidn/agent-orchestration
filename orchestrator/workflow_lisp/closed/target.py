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
from orchestrator.workflow_lisp.spans import SourcePosition, SourceSpan


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


def _initial_source_location(path: Path) -> SourceSpan:
    """Locate a compiled-only refusal at its known source path's file start."""

    position = SourcePosition(str(Path(path)), 1, 1, 0)
    return SourceSpan(position, position)


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


def _raise_evaluated_execution_unavailable(
    target_dsl_version: str,
    target_span: SourceSpan,
) -> None:
    raise LispFrontendCompileError(
        (_evaluated_execution_unavailable_diagnostic_at_span(
            target_dsl_version,
            target_span,
        ),)
    )


def _evaluated_execution_unavailable_diagnostic_at_span(
    target_dsl_version: str,
    target_span: SourceSpan,
) -> LispFrontendDiagnostic:
    return LispFrontendDiagnostic(
        code="evaluated_execution_unavailable",
        message=(
            f"target DSL {target_dsl_version} runs only on the evaluated route "
            f"(from DSL {syntax.EVALUATED_EXECUTION_MIN_TARGET_DSL_VERSION}); "
            "the flat route cannot execute it"
        ),
        span=target_span,
        phase="lowering",
    )


def _evaluated_execution_unavailable_diagnostic(
    target_dsl_version: str,
    source_path: Path,
) -> LispFrontendDiagnostic:
    """Build a target refusal diagnostic from compiled metadata and source location."""

    return _evaluated_execution_unavailable_diagnostic_at_span(
        target_dsl_version,
        _initial_source_location(source_path),
    )


def refuse_run_at_evaluated_execution_target(path: Path) -> None:
    """Refuse run/resume early when the entry header selects evaluated execution."""

    try:
        target_dsl_version, target_span = _entry_target_header(path)
    except (LispFrontendCompileError, OSError, UnicodeError):
        # This is only an early refusal peek; the regular build owns source diagnostics.
        return
    if syntax.target_dsl_uses_evaluated_execution(target_dsl_version):
        _raise_evaluated_execution_unavailable(target_dsl_version, target_span)


def refuse_compiled_target_at_evaluated_execution_target(
    path: Path,
    target_dsl_version: str,
    source_bytes_by_path: Mapping[Path, bytes],
) -> None:
    """Reject the target parsed by the compiler from its exact source snapshot."""

    if not syntax.target_dsl_uses_evaluated_execution(target_dsl_version):
        return
    try:
        source_bytes = source_bytes_by_path[path]
    except KeyError as exc:
        raise RuntimeError(
            f"compiled entry source `{path}` is absent from its read trace"
        ) from exc
    snapshot_target, target_span = _entry_target_header_from_bytes(
        path,
        source_bytes,
    )
    if snapshot_target != target_dsl_version:
        raise RuntimeError(
            f"compiled entry target `{target_dsl_version}` does not match its source snapshot"
        )
    _raise_evaluated_execution_unavailable(snapshot_target, target_span)
