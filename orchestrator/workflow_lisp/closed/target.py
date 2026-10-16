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
from orchestrator.contracts.closed_program.targets import SUPPORTED_TARGET_DSL_VERSIONS
from orchestrator.workflow_lisp.reader import SourceReadTrace, read_sexpr_file, read_sexpr_text
from orchestrator.workflow_lisp.sexpr import KeywordAtom, ListExpr, StringAtom
from orchestrator.workflow_lisp.spans import SourcePosition, SourceSpan


def require_supported_typed_program_targets(
    value: object,
    *,
    source_path: Path | str,
) -> None:
    """Validate the retained target metadata for a typed capsule graph."""

    from .frontend import TypedProgram

    if not isinstance(value, TypedProgram):
        return
    pending = [value]
    seen: set[int] = set()
    while pending:
        program = pending.pop()
        if not isinstance(program, TypedProgram):
            continue
        if id(program) in seen:
            continue
        seen.add(id(program))
        entry_definition = getattr(getattr(program, "entry", None), "definition", None)
        fallback_path = str(source_path or getattr(program, "entry_dir", "<typed-program>"))
        span = getattr(entry_definition, "span", None) or SourceSpan(
            start=SourcePosition(path=fallback_path, line=1, column=1, offset=0),
            end=SourcePosition(path=fallback_path, line=1, column=1, offset=0),
        )
        for target in (
            program.target,
            *(
                getattr(environment, "target_dsl_version", None)
                for environment in program.module_type_envs.values()
            ),
        ):
            if not isinstance(target, str) or target not in SUPPORTED_TARGET_DSL_VERSIONS:
                raise LispFrontendCompileError((LispFrontendDiagnostic(
                    code="target_dsl_unsupported",
                    message=f"unsupported target DSL `{target}`",
                    span=span,
                    form_path=("workflow-lisp",),
                ),))
        pending.extend(program.imported_programs.values())


def _entry_target_header_from_tree(
    parse_tree: ListExpr,
) -> tuple[str, SourceSpan]:
    syntax_module = syntax.build_syntax_module(parse_tree)
    header = _raw_entry_target_header_from_tree(parse_tree)
    assert header is not None
    return syntax_module.target_dsl_version, header[1]


def _raw_entry_target_header_from_tree(
    parse_tree: ListExpr,
) -> tuple[str, SourceSpan] | None:
    """Read the target header after the syntax frontend validates its shape."""

    root = parse_tree.items[0]
    if not isinstance(root, ListExpr):
        return None
    for form in root.items[1:]:
        if (
            isinstance(form, ListExpr)
            and len(form.items) == 2
            and isinstance(form.items[0], KeywordAtom)
            and form.items[0].value == ":target-dsl"
            and isinstance(form.items[1], StringAtom)
        ):
            return form.items[1].value, form.items[1].span
    return None


def _is_retired_entry_target(target: str) -> bool:
    try:
        major, minor = (int(part) for part in target.split("."))
    except ValueError:
        return False
    return target == f"{major}.{minor}" and major == 2 and 14 <= minor < 35


def _entry_target_header_for_retirement(
    parse_tree: ListExpr,
) -> tuple[str, SourceSpan]:
    try:
        return _entry_target_header_from_tree(parse_tree)
    except LispFrontendCompileError as exc:
        if not any(
            diagnostic.code == "target_dsl_unsupported"
            for diagnostic in exc.diagnostics
        ):
            raise
        header = _raw_entry_target_header_from_tree(parse_tree)
        if header is None or not _is_retired_entry_target(header[0]):
            raise
        return header


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
    return _entry_target_header_for_retirement(parse_tree)


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
    path = resolve_path_preserving_fd(path)
    parse_tree = read_sexpr_file(path, source_read_trace=source_read_trace)
    _refuse_retired_entry_target(parse_tree)


def refuse_retired_entry_target_from_bytes(path: Path, source_bytes: bytes) -> None:
    """Apply the public-entry refusal to a compiler-captured source snapshot."""
    source_text = source_bytes.decode("utf-8", errors="strict")
    parser_text = source_text.replace("\r\n", "\n").replace("\r", "\n")
    parse_tree = read_sexpr_text(parser_text, source_path=str(path))
    _refuse_retired_entry_target(parse_tree)


def _refuse_retired_entry_target(parse_tree: ListExpr) -> None:
    target, span = _entry_target_header_for_retirement(parse_tree)
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
