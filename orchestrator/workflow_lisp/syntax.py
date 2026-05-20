"""Immutable syntax objects for the Workflow Lisp frontend."""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum


@dataclass(frozen=True)
class SourceSpan:
    """Source coordinates for one authored syntax region."""

    source_file: str
    byte_start: int
    byte_end: int
    line_start: int
    column_start: int
    line_end: int
    column_end: int


@dataclass(frozen=True)
class SyntaxContext:
    """Frontend context carried on every exposed syntax node."""

    source_path: str
    module_name: str | None = None
    hygiene_marks: tuple[str, ...] = ()
    expansion_stack: tuple[str, ...] = ()


class AtomKind(str, Enum):
    """Supported atom kinds for the MVP lexer surface."""

    SYMBOL = "symbol"
    KEYWORD = "keyword"
    STRING = "string"
    QUOTED_SYMBOL = "quoted_symbol"
    INT = "int"
    FLOAT = "float"
    BOOL = "bool"
    NIL = "nil"


@dataclass(frozen=True)
class SyntaxAtom:
    """One immutable atom with source span and context."""

    kind: AtomKind
    value: str | int | float | bool
    span: SourceSpan
    context: SyntaxContext


@dataclass(frozen=True)
class SyntaxList:
    """One immutable list form with source span and context."""

    items: tuple["SyntaxNode", ...]
    span: SourceSpan
    context: SyntaxContext


SyntaxNode = SyntaxAtom | SyntaxList


@dataclass(frozen=True)
class SyntaxDiagnostic:
    """Structured parser or header diagnostic."""

    code: str
    message: str
    span: SourceSpan
    source_file: str
    line: int
    column: int
    enclosing_form_name: str | None = None
    generated_core_node_id: str | None = None


@dataclass(frozen=True)
class ParsedWorkflowModule:
    """Parsed single-file Workflow Lisp compilation unit."""

    source_path: str
    header_form: SyntaxList
    language_version: str
    target_dsl: str
    body_forms: tuple[SyntaxNode, ...]


def replace_module_name(context: SyntaxContext, module_name: str | None) -> SyntaxContext:
    """Return one context copy with a new module name."""

    return replace(context, module_name=module_name)
