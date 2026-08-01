"""Neutral validation for compiler-normalized transport type descriptors."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


def _require_exact_descriptor_keys(
    descriptor: Mapping[str, Any],
    expected: set[str],
    *,
    context: str,
) -> None:
    if set(descriptor) != expected:
        raise ValueError(f"{context} must contain exactly {sorted(expected)}")


def _require_descriptor_name(value: Any, *, context: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{context} must be a non-empty string")
    return value


def _descriptor_sequence(value: Any, *, context: str) -> Sequence[Any]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise ValueError(f"{context} must be a sequence")
    return value


def _validate_normalized_descriptor_fields(
    fields: Any,
    *,
    context: str,
) -> None:
    names: set[str] = set()
    for index, descriptor_field in enumerate(
        _descriptor_sequence(fields, context=context)
    ):
        field_context = f"{context}[{index}]"
        if not isinstance(descriptor_field, Mapping):
            raise ValueError(f"{field_context} must be a mapping")
        _require_exact_descriptor_keys(
            descriptor_field,
            {"name", "type"},
            context=field_context,
        )
        name = _require_descriptor_name(
            descriptor_field["name"],
            context=f"{field_context}.name",
        )
        if name in names:
            raise ValueError(f"{context} contains duplicate names")
        names.add(name)
        validate_compiler_normalized_type_descriptor(
            descriptor_field["type"],
            context=f"{field_context}.type",
        )


def validate_compiler_normalized_type_descriptor(
    descriptor: Any,
    *,
    context: str = "normalized_type_descriptor",
) -> None:
    """Validate the compiler's one closed normalized type-descriptor schema."""

    if not isinstance(descriptor, Mapping):
        raise ValueError(f"{context} must be a mapping")
    kind = descriptor.get("kind")
    if kind == "primitive":
        _require_exact_descriptor_keys(
            descriptor,
            {"kind", "name"},
            context=context,
        )
        _require_descriptor_name(descriptor["name"], context=f"{context}.name")
        return
    if kind == "enum":
        _require_exact_descriptor_keys(
            descriptor,
            {"kind", "name", "allowed"},
            context=context,
        )
        _require_descriptor_name(descriptor["name"], context=f"{context}.name")
        allowed = _descriptor_sequence(
            descriptor["allowed"],
            context=f"{context}.allowed",
        )
        if (
            not allowed
            or any(not isinstance(item, str) or not item for item in allowed)
            or len(set(allowed)) != len(allowed)
        ):
            raise ValueError(
                f"{context}.allowed must be a non-empty unique string sequence"
            )
        return
    if kind == "path":
        _require_exact_descriptor_keys(
            descriptor,
            {"kind", "name", "under", "must_exist_target"},
            context=context,
        )
        _require_descriptor_name(descriptor["name"], context=f"{context}.name")
        _require_descriptor_name(descriptor["under"], context=f"{context}.under")
        if not isinstance(descriptor["must_exist_target"], bool):
            raise ValueError(f"{context}.must_exist_target must be boolean")
        return
    if kind in {"optional", "list"}:
        _require_exact_descriptor_keys(
            descriptor,
            {"kind", "item"},
            context=context,
        )
        validate_compiler_normalized_type_descriptor(
            descriptor["item"],
            context=f"{context}.item",
        )
        return
    if kind == "map":
        _require_exact_descriptor_keys(
            descriptor,
            {"kind", "key", "value"},
            context=context,
        )
        validate_compiler_normalized_type_descriptor(
            descriptor["key"],
            context=f"{context}.key",
        )
        validate_compiler_normalized_type_descriptor(
            descriptor["value"],
            context=f"{context}.value",
        )
        return
    if kind == "record":
        _require_exact_descriptor_keys(
            descriptor,
            {"kind", "name", "fields"},
            context=context,
        )
        _require_descriptor_name(descriptor["name"], context=f"{context}.name")
        _validate_normalized_descriptor_fields(
            descriptor["fields"],
            context=f"{context}.fields",
        )
        return
    if kind == "union":
        _require_exact_descriptor_keys(
            descriptor,
            {"kind", "name", "variants"},
            context=context,
        )
        _require_descriptor_name(descriptor["name"], context=f"{context}.name")
        variants = _descriptor_sequence(
            descriptor["variants"],
            context=f"{context}.variants",
        )
        if not variants:
            raise ValueError(f"{context}.variants must be a non-empty sequence")
        names: set[str] = set()
        for index, variant in enumerate(variants):
            variant_context = f"{context}.variants[{index}]"
            if not isinstance(variant, Mapping):
                raise ValueError(f"{variant_context} must be a mapping")
            _require_exact_descriptor_keys(
                variant,
                {"name", "fields"},
                context=variant_context,
            )
            name = _require_descriptor_name(
                variant["name"],
                context=f"{variant_context}.name",
            )
            if name in names:
                raise ValueError(f"{context}.variants contains duplicate names")
            names.add(name)
            _validate_normalized_descriptor_fields(
                variant["fields"],
                context=f"{variant_context}.fields",
            )
        return
    if kind == "variant_case":
        _require_exact_descriptor_keys(
            descriptor,
            {"kind", "union_name", "variant", "fields"},
            context=context,
        )
        _require_descriptor_name(
            descriptor["union_name"],
            context=f"{context}.union_name",
        )
        _require_descriptor_name(
            descriptor["variant"],
            context=f"{context}.variant",
        )
        _validate_normalized_descriptor_fields(
            descriptor["fields"],
            context=f"{context}.fields",
        )
        return
    raise ValueError(f"{context} uses an unsupported type kind")


__all__ = ["validate_compiler_normalized_type_descriptor"]
