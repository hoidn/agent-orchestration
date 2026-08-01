"""Neutral compiler-normalized type descriptor ownership."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

from orchestrator.workflow.type_descriptor import (
    validate_compiler_normalized_type_descriptor,
)

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
