"""Typed diagnostics and rendering helpers for the workflow Lisp frontend."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .spans import SourceSpan


@dataclass(frozen=True)
class LispFrontendDiagnostic:
    """One deterministic frontend diagnostic."""

    code: str
    message: str
    span: SourceSpan
    form_path: tuple[str, ...] = ()
    expansion_stack: tuple[object, ...] = ()
    notes: tuple[str, ...] = ()


class LispFrontendCompileError(Exception):
    """Raised when Stage 1 frontend compilation fails."""

    def __init__(self, diagnostics: tuple[LispFrontendDiagnostic, ...]):
        self.diagnostics = diagnostics
        super().__init__(render_diagnostics(diagnostics))


def render_diagnostic(diagnostic: LispFrontendDiagnostic) -> str:
    """Render one diagnostic into stable human-readable text."""

    location = (
        f"{diagnostic.span.start.path}:"
        f"{diagnostic.span.start.line}:"
        f"{diagnostic.span.start.column}"
    )
    parts = [f"{location}: [{diagnostic.code}] {diagnostic.message}"]
    if diagnostic.form_path:
        parts.append(f"form: {' > '.join(diagnostic.form_path)}")
    for note in _render_expansion_notes(diagnostic.expansion_stack):
        parts.append(f"note: {note}")
    for note in diagnostic.notes:
        parts.append(f"note: {note}")
    return "\n".join(parts)


def render_diagnostics(diagnostics: Iterable[LispFrontendDiagnostic]) -> str:
    """Render multiple diagnostics in deterministic order."""

    return "\n\n".join(render_diagnostic(diagnostic) for diagnostic in diagnostics)


def _render_expansion_notes(expansion_stack: tuple[object, ...]) -> tuple[str, ...]:
    notes: list[str] = []
    for frame in expansion_stack:
        macro_name = getattr(frame, "macro_name", None)
        expansion_id = getattr(frame, "expansion_id", None)
        call_span = getattr(frame, "call_span", None)
        definition_span = getattr(frame, "definition_span", None)
        if macro_name is None or call_span is None or definition_span is None:
            continue
        call_location = (
            f"{call_span.start.path}:{call_span.start.line}:{call_span.start.column}"
        )
        definition_location = (
            f"{definition_span.start.path}:{definition_span.start.line}:{definition_span.start.column}"
        )
        if expansion_id:
            notes.append(
                f"expanded from macro `{macro_name}` call at {call_location} ({expansion_id})"
            )
        else:
            notes.append(f"expanded from macro `{macro_name}` call at {call_location}")
        notes.append(f"macro definition at {definition_location}")
    return tuple(notes)
