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
    severity: str | None = None
    form_path: tuple[str, ...] = ()
    expansion_stack: tuple[object, ...] = ()
    notes: tuple[str, ...] = ()
    phase: str | None = None


class LispFrontendCompileError(Exception):
    """Raised when Workflow Lisp compilation accumulates diagnostics."""

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


def serialize_diagnostic(diagnostic: LispFrontendDiagnostic) -> dict[str, object]:
    """Serialize one diagnostic into a machine-readable envelope."""

    return {
        "code": diagnostic.code,
        "severity": diagnostic.severity or "error",
        "message": diagnostic.message,
        "path": diagnostic.span.start.path,
        "line": diagnostic.span.start.line,
        "column": diagnostic.span.start.column,
        "form_path": list(diagnostic.form_path),
        "expansion_stack": [
            _serialize_expansion_frame(frame)
            for frame in diagnostic.expansion_stack
        ],
        "notes": list(diagnostic.notes),
        "phase": diagnostic.phase or _infer_phase(diagnostic.code),
    }


def serialize_diagnostics(
    diagnostics: Iterable[LispFrontendDiagnostic],
) -> list[dict[str, object]]:
    """Serialize multiple diagnostics in deterministic order."""

    return [serialize_diagnostic(diagnostic) for diagnostic in diagnostics]


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


def _serialize_expansion_frame(frame: object) -> dict[str, object]:
    call_span = getattr(frame, "call_span", None)
    definition_span = getattr(frame, "definition_span", None)
    payload: dict[str, object] = {
        "macro_name": getattr(frame, "macro_name", None),
        "expansion_id": getattr(frame, "expansion_id", None),
    }
    if call_span is not None:
        payload["call"] = {
            "path": call_span.start.path,
            "line": call_span.start.line,
            "column": call_span.start.column,
        }
    if definition_span is not None:
        payload["definition"] = {
            "path": definition_span.start.path,
            "line": definition_span.start.line,
            "column": definition_span.start.column,
        }
    return payload


def _infer_phase(code: str) -> str:
    if code.startswith("frontend_parse") or code.startswith("target_dsl_"):
        return "syntax"
    if code.startswith("type_") or code.startswith("provider_result_") or code.startswith("command_result_"):
        return "typecheck"
    if code.startswith("workflow_ref_") or code.startswith("source_map_"):
        return "lowering"
    if code.startswith("entry_workflow_") or code.startswith("imported_workflow_bundle_"):
        return "cli_request"
    return "shared_validation" if code.startswith("workflow_boundary_") else "read"
