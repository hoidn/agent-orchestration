"""Pure lexical capture facts; generated workflow emission stays with its owner."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..type_env import TypeRef, UnionTypeRef, VariantCaseTypeRef


def helper_capture_payload(
    capture_type: TypeRef, *, type_env: Any, span: Any, form_path: tuple[str, ...],
) -> tuple[tuple[Any, ...], Mapping[str, TypeRef]] | None:
    """Expose a variant's payload without manufacturing a nominal record type."""
    if not isinstance(capture_type, VariantCaseTypeRef):
        return None
    union_type = type_env.resolve_type(capture_type.union_name, span=span, form_path=form_path)
    assert isinstance(union_type, UnionTypeRef)
    return capture_type.definition.fields, union_type.variant_field_types[capture_type.variant_name]
