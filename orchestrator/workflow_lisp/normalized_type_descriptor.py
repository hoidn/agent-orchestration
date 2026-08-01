"""Neutral compiler-normalized type descriptor ownership."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

from .loop_state import carrier_metadata_for_type
from .reader import SourceReadTrace, read_sexpr_file, read_sexpr_text
from .syntax import build_syntax_module
from .type_env import (
    FrontendTypeEnvironment,
    ListTypeRef,
    MapTypeRef,
    OptionalTypeRef,
    PathTypeRef,
    PrimitiveTypeRef,
    RecordTypeRef,
    TypeRef,
    UnionTypeRef,
    VariantCaseTypeRef,
)


def _require_exact_descriptor_keys(
    descriptor: Mapping[str, Any],
    expected: set[str],
    *,
    context: str,
) -> None:
    if set(descriptor) != expected:
        raise ValueError(
            f"{context} must contain exactly {sorted(expected)}"
        )


def _require_descriptor_name(value: Any, *, context: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{context} must be a non-empty string")
    return value


def _descriptor_sequence(value: Any, *, context: str) -> Sequence[Any]:
    if (
        not isinstance(value, Sequence)
        or isinstance(value, (str, bytes, bytearray))
    ):
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
        _require_descriptor_name(
            descriptor["name"],
            context=f"{context}.name",
        )
        return
    if kind == "enum":
        _require_exact_descriptor_keys(
            descriptor,
            {"kind", "name", "allowed"},
            context=context,
        )
        _require_descriptor_name(
            descriptor["name"],
            context=f"{context}.name",
        )
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
        _require_descriptor_name(
            descriptor["name"],
            context=f"{context}.name",
        )
        _require_descriptor_name(
            descriptor["under"],
            context=f"{context}.under",
        )
        if not isinstance(descriptor["must_exist_target"], bool):
            raise ValueError(
                f"{context}.must_exist_target must be boolean"
            )
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
        _require_descriptor_name(
            descriptor["name"],
            context=f"{context}.name",
        )
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
        _require_descriptor_name(
            descriptor["name"],
            context=f"{context}.name",
        )
        variants = _descriptor_sequence(
            descriptor["variants"],
            context=f"{context}.variants",
        )
        if not variants:
            raise ValueError(
                f"{context}.variants must be a non-empty sequence"
            )
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
                raise ValueError(
                    f"{context}.variants contains duplicate names"
                )
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


def _load_module_export_info(
    source_path: str,
    *,
    source_read_trace: SourceReadTrace | None = None,
) -> tuple[str, frozenset[str]] | None:
    if source_path.startswith("<prelude:"):
        return None
    path = Path(source_path)
    syntax_module = build_syntax_module(
        read_sexpr_file(
            path,
            source_read_trace=source_read_trace,
        )
    )
    if syntax_module.module_name is None:
        return None
    return syntax_module.module_name, frozenset(syntax_module.exports)


@dataclass(frozen=True)
class _ModuleExportCacheInput:
    canonical_source_path: str
    source_sha256: str
    raw_bytes: bytes = field(compare=False, hash=False, repr=False)


@lru_cache(maxsize=None)
def _cached_module_export_info(
    cache_input: _ModuleExportCacheInput,
) -> tuple[str, frozenset[str]] | None:
    parser_text = (
        cache_input.raw_bytes.decode("utf-8", errors="strict")
        .replace("\r\n", "\n")
        .replace("\r", "\n")
    )
    syntax_module = build_syntax_module(
        read_sexpr_text(
            parser_text,
            source_path=cache_input.canonical_source_path,
        )
    )
    if syntax_module.module_name is None:
        return None
    return syntax_module.module_name, frozenset(syntax_module.exports)


def _module_export_info(
    source_path: str,
    *,
    source_read_trace: SourceReadTrace | None = None,
) -> tuple[str, frozenset[str]] | None:
    if source_read_trace is None:
        if source_path.startswith("<prelude:"):
            return None
        canonical_source_path = Path(source_path).resolve()
        raw_bytes = canonical_source_path.read_bytes()
        return _cached_module_export_info(
            _ModuleExportCacheInput(
                canonical_source_path=str(canonical_source_path),
                source_sha256=hashlib.sha256(raw_bytes).hexdigest(),
                raw_bytes=raw_bytes,
            )
        )
    return _load_module_export_info(
        source_path,
        source_read_trace=source_read_trace,
    )


def _nominal_descriptor_name(
    type_ref: TypeRef,
    *,
    type_env: FrontendTypeEnvironment | None = None,
    source_read_trace: SourceReadTrace | None = None,
) -> str:
    if (
        type_env is not None
        and type_env.session_state is not None
        and carrier_metadata_for_type(
            type_ref,
            session_state=type_env.session_state,
        )
        is not None
    ):
        return "workflow_lisp/private::loop-state-carrier"
    if "::" in type_ref.name:
        return type_ref.name
    if "/" in type_ref.name:
        module_name, member_name = type_ref.name.rsplit("/", 1)
        return f"{module_name}::{member_name}"
    if type_env is not None:
        known_name = type_env.nominal_descriptor_name(type_ref)
        if known_name is not None:
            return known_name
    definition = getattr(type_ref, "definition", None)
    span = getattr(definition, "span", None)
    start = getattr(span, "start", None)
    source_path = getattr(start, "path", None)
    if source_path:
        if source_path.startswith("<compiler:"):
            return type_ref.name
        info = _module_export_info(
            source_path,
            source_read_trace=source_read_trace,
        )
        if info is not None:
            module_name, exported_names = info
            if getattr(definition, "name", None) in exported_names:
                return f"{module_name}::{definition.name}"
    return type_ref.name


def compiler_normalized_type_descriptor(
    type_ref: TypeRef,
    *,
    type_env: FrontendTypeEnvironment,
    source_read_trace: SourceReadTrace | None = None,
) -> dict[str, Any]:
    """Return the compiler's validated, normalized descriptor for one type."""

    descriptor = _build_type_descriptor(
        type_ref,
        type_env=type_env,
        source_read_trace=source_read_trace,
    )
    validate_compiler_normalized_type_descriptor(descriptor)
    return descriptor


def _type_descriptor(
    type_ref: TypeRef,
    *,
    type_env: FrontendTypeEnvironment,
    source_read_trace: SourceReadTrace | None = None,
) -> dict[str, Any]:
    return compiler_normalized_type_descriptor(
        type_ref,
        type_env=type_env,
        source_read_trace=source_read_trace,
    )


def _build_type_descriptor(
    type_ref: TypeRef,
    *,
    type_env: FrontendTypeEnvironment,
    source_read_trace: SourceReadTrace | None = None,
) -> dict[str, Any]:
    if isinstance(type_ref, PrimitiveTypeRef):
        if type_ref.allowed_values:
            return {
                "kind": "enum",
                "name": type_ref.name,
                "allowed": list(type_ref.allowed_values),
            }
        return {"kind": "primitive", "name": type_ref.name}
    if isinstance(type_ref, PathTypeRef):
        return {
            "kind": "path",
            "name": type_ref.name,
            "under": type_ref.definition.under,
            "must_exist_target": type_ref.definition.must_exist,
        }
    if isinstance(type_ref, OptionalTypeRef):
        return {
            "kind": "optional",
            "item": _type_descriptor(
                type_ref.item_type_ref,
                type_env=type_env,
                source_read_trace=source_read_trace,
            ),
        }
    if isinstance(type_ref, ListTypeRef):
        return {
            "kind": "list",
            "item": _type_descriptor(
                type_ref.item_type_ref,
                type_env=type_env,
                source_read_trace=source_read_trace,
            ),
        }
    if isinstance(type_ref, MapTypeRef):
        return {
            "kind": "map",
            "key": _type_descriptor(
                type_ref.key_type_ref,
                type_env=type_env,
                source_read_trace=source_read_trace,
            ),
            "value": _type_descriptor(
                type_ref.value_type_ref,
                type_env=type_env,
                source_read_trace=source_read_trace,
            ),
        }
    if isinstance(type_ref, RecordTypeRef):
        return {
            "kind": "record",
            "name": _nominal_descriptor_name(
                type_ref,
                type_env=type_env,
                source_read_trace=source_read_trace,
            ),
            "fields": [
                {
                    "name": type_field.name,
                    "type": _type_descriptor(
                        type_ref.field_types[type_field.name],
                        type_env=type_env,
                        source_read_trace=source_read_trace,
                    ),
                }
                for type_field in type_ref.definition.fields
            ],
        }
    if isinstance(type_ref, UnionTypeRef):
        return {
            "kind": "union",
            "name": _nominal_descriptor_name(
                type_ref,
                type_env=type_env,
                source_read_trace=source_read_trace,
            ),
            "variants": [
                {
                    "name": variant.name,
                    "fields": [
                        {
                            "name": type_field.name,
                            "type": _type_descriptor(
                                type_ref.variant_field_types[variant.name][
                                    type_field.name
                                ],
                                type_env=type_env,
                                source_read_trace=source_read_trace,
                            ),
                        }
                        for type_field in variant.fields
                    ],
                }
                for variant in type_ref.definition.variants
            ],
        }
    if isinstance(type_ref, VariantCaseTypeRef):
        # Prefer the resolved field types carried from the union that produced
        # this variant case (`VariantCaseTypeRef.field_types`, type_env.py).
        # Re-resolving `union_name` by bare name fails for caller-module
        # unions lowered inside a specialized generic body, whose
        # defining-module `type_env` cannot see them (gap C,
        # docs/plans/2026-07-07-drain-migration-g8-retirement.md Phase 1
        # Ledger). Same-module refs carry the identical mapping, so the
        # descriptor is unchanged wherever the name lookup used to succeed.
        variant_field_types = type_ref.field_types
        if variant_field_types is None or any(
            type_field.name not in variant_field_types
            for type_field in type_ref.definition.fields
        ):
            union_type = type_env.resolve_type(
                type_ref.union_name,
                span=type_ref.definition.span,
                form_path=(),
            )
            if not isinstance(union_type, UnionTypeRef):
                raise TypeError(
                    f"expected union type for variant case `{type_ref.union_name}`"
                )
            variant_field_types = union_type.variant_field_types[
                type_ref.variant_name
            ]
        return {
            "kind": "variant_case",
            "union_name": type_ref.union_name,
            "variant": type_ref.variant_name,
            "fields": [
                {
                    "name": type_field.name,
                    "type": _type_descriptor(
                        variant_field_types[type_field.name],
                        type_env=type_env,
                        source_read_trace=source_read_trace,
                    ),
                }
                for type_field in type_ref.definition.fields
            ],
        }
    raise TypeError(
        f"unsupported pure type descriptor for `{type(type_ref).__name__}`"
    )
