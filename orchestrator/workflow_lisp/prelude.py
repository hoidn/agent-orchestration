"""Fixed MVP prelude names for Workflow Lisp definition validation."""

from __future__ import annotations

PRELUDE_TYPE_NAMES: tuple[str, ...] = (
    "String",
    "Int",
    "Float",
    "Bool",
    "Json",
    "Symbol",
    "Provider",
    "Prompt",
    "PathRel",
)

PRELUDE_BUILTIN_FORM_NAMES: tuple[str, ...] = (
    "provider-result",
    "command-result",
    "match",
    "let*",
    "call",
    "with-phase",
    "phase-target",
)

PRELUDE_RESERVED_NAMES: frozenset[str] = frozenset(
    PRELUDE_TYPE_NAMES + PRELUDE_BUILTIN_FORM_NAMES
)
