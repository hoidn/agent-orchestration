"""S-expression parse-tree nodes for the workflow Lisp frontend."""

from __future__ import annotations

from dataclasses import dataclass

from .spans import SourceSpan


@dataclass(frozen=True)
class ListExpr:
    """Authored list form."""

    items: tuple["SExpr", ...]
    span: SourceSpan


@dataclass(frozen=True)
class SymbolAtom:
    """Authored symbol atom."""

    value: str
    span: SourceSpan


@dataclass(frozen=True)
class KeywordAtom:
    """Authored keyword atom."""

    value: str
    span: SourceSpan


@dataclass(frozen=True)
class StringAtom:
    """Authored string atom."""

    value: str
    span: SourceSpan


@dataclass(frozen=True)
class IntAtom:
    """Authored integer atom."""

    value: int
    span: SourceSpan


@dataclass(frozen=True)
class FloatAtom:
    """Authored float atom."""

    value: float
    span: SourceSpan


@dataclass(frozen=True)
class BoolAtom:
    """Authored boolean atom."""

    value: bool
    span: SourceSpan


SExpr = ListExpr | SymbolAtom | KeywordAtom | StringAtom | IntAtom | FloatAtom | BoolAtom
