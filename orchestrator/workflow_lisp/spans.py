"""Source location records for the workflow Lisp frontend."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SourcePosition:
    """One authored source position."""

    path: str
    line: int
    column: int
    offset: int


@dataclass(frozen=True)
class SourceSpan:
    """Closed-open span between two authored positions."""

    start: SourcePosition
    end: SourcePosition
