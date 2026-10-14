"""Machine compile diagnostics for rejected frontend requests."""

from __future__ import annotations

from collections.abc import Iterable

from .diagnostics import LispFrontendDiagnostic, build_compile_diagnostics_document


def build_rejected_compile_diagnostics_document(
    diagnostics: Iterable[LispFrontendDiagnostic],
) -> dict[str, object]:
    """Build the closed machine document for a rejected full compile."""

    return build_compile_diagnostics_document(status="rejected", diagnostics=diagnostics)
