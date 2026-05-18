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
    for note in diagnostic.notes:
        parts.append(f"note: {note}")
    return "\n".join(parts)


def render_diagnostics(diagnostics: Iterable[LispFrontendDiagnostic]) -> str:
    """Render multiple diagnostics in deterministic order."""

    return "\n\n".join(render_diagnostic(diagnostic) for diagnostic in diagnostics)
