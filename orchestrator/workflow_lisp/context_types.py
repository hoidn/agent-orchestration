"""Fixed ordinary Workflow Lisp types for portable provider context values."""

from __future__ import annotations

from .definitions import RecordDef, RecordField, UnionDef, UnionVariant
from .spans import SourcePosition, SourceSpan


CONTEXT_TYPE_NAMES = frozenset(
    {
        "Context",
        "ContextOrigin",
        "ContextEvent",
        "ContextFileChange",
        "ContextCoverage",
        "ContextTransform",
        "Contextual",
    }
)


def _span(name: str) -> SourceSpan:
    position = SourcePosition(path=f"<prelude:{name}>", line=1, column=1, offset=0)
    return SourceSpan(start=position, end=position)


def _record(name: str, fields: tuple[tuple[str, object], ...]):
    from .type_env import RecordTypeRef

    return RecordTypeRef(
        name=name,
        definition=RecordDef(
            name=name,
            fields=tuple(
                RecordField(name=field_name, type_name=field_type.name, span=_span(name))
                for field_name, field_type in fields
            ),
            span=_span(name),
        ),
        field_types=dict(fields),
    )


def _union(name: str, variants: tuple[tuple[str, tuple[tuple[str, object], ...]], ...]):
    from .type_env import UnionTypeRef

    return UnionTypeRef(
        name=name,
        definition=UnionDef(
            name=name,
            variants=tuple(
                UnionVariant(
                    name=variant_name,
                    fields=tuple(
                        RecordField(
                            name=field_name,
                            type_name=field_type.name,
                            span=_span(f"{name}.{variant_name}"),
                        )
                        for field_name, field_type in fields
                    ),
                    span=_span(f"{name}.{variant_name}"),
                )
                for variant_name, fields in variants
            ),
            span=_span(name),
        ),
        variant_field_types={variant_name: dict(fields) for variant_name, fields in variants},
    )


def context_fixed_types(type_refs: dict[str, object]) -> tuple[tuple[str, object], ...]:
    """Build the closed portable-context records and unions from prelude scalars."""

    from .type_env import ListTypeRef, PrimitiveTypeRef

    def primitive(name: str):
        value = type_refs.get(name)
        if not isinstance(value, PrimitiveTypeRef) or value.name != name:
            raise TypeError(f"provider context requires primitive `{name}`")
        return value

    def list_of(item):
        return ListTypeRef(name=f"List[{item.name}]", item_type_ref=item)

    string = primitive("String")
    integer = primitive("Int")
    origin = _union(
        "ContextOrigin",
        (
            ("CAPTURED", (("provider", string), ("attempt", string))),
            ("AUTHORED", (("label", string),)),
        ),
    )
    file_change = _record(
        "ContextFileChange",
        (("path", string), ("kind", string)),
    )
    event = _union(
        "ContextEvent",
        (
            ("TASK", (("origin", origin), ("sequence", integer), ("text", string))),
            (
                "ASSISTANT",
                (("origin", origin), ("sequence", integer), ("item_id", string), ("text", string)),
            ),
            (
                "COMMAND",
                (
                    ("origin", origin),
                    ("call_sequence", integer),
                    ("result_sequence", integer),
                    ("item_id", string),
                    ("command", string),
                    ("output", string),
                    ("exit_code", integer),
                ),
            ),
            (
                "FILE_CHANGE",
                (
                    ("origin", origin),
                    ("sequence", integer),
                    ("item_id", string),
                    ("status", string),
                    ("changes", list_of(file_change)),
                ),
            ),
        ),
    )
    coverage = _record(
        "ContextCoverage",
        (
            ("origin", origin),
            ("scope", string),
            ("retained_kinds", list_of(string)),
            ("omitted_kinds", list_of(string)),
            ("conversions", list_of(string)),
        ),
    )
    transform = _record(
        "ContextTransform",
        (("sources", list_of(origin)), ("operation", string), ("loss", list_of(string))),
    )
    context = _record(
        "Context",
        (
            ("schema", string),
            ("events", list_of(event)),
            ("coverage", list_of(coverage)),
            ("lineage", list_of(transform)),
        ),
    )
    return tuple(
        (type_ref.name, type_ref)
        for type_ref in (origin, file_change, event, coverage, transform, context)
    )


def contextual_type(result_type, context_type):
    """Return the one ordinary record representation of ``Contextual[T]``."""

    from .type_env import render_type_ref

    return _record(
        f"Contextual[{render_type_ref(result_type)}]",
        (("result", result_type), ("context", context_type)),
    )


def fixed_context_type(type_refs: dict[str, object]):
    """Return the installed compiler-owned ``Context`` record, never an alias."""

    context = type_refs.get("Context")
    if not (
        is_fixed_context_type(context)
        and context.definition.span.start.path == "<prelude:Context>"
    ):
        raise TypeError("provider context requires the fixed compiler-owned Context type")
    return context


def is_fixed_context_type(type_ref: object) -> bool:
    """Return whether ``type_ref`` is a record with the fixed Context shape."""

    from .type_env import RecordTypeRef

    return (
        isinstance(type_ref, RecordTypeRef)
        and type_ref.name == "Context"
        and type_ref.definition.name == "Context"
        and tuple(type_ref.field_types) == ("schema", "events", "coverage", "lineage")
    )


def is_contextual_type(type_ref: object) -> bool:
    """Return whether a record was constructed by :func:`contextual_type`."""

    from .type_env import RecordTypeRef

    return (
        isinstance(type_ref, RecordTypeRef)
        and type_ref.name.startswith("Contextual[")
        and type_ref.name.endswith("]")
        and tuple(type_ref.field_types) == ("result", "context")
        and type_ref.definition.name == type_ref.name
    )
