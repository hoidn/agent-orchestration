"""Workflow Lisp typed prompt input helpers and deterministic rendering."""

from __future__ import annotations


def select_prompt_fragment_renderer(
    type_ref: object,
    *,
    kind: str,
) -> str | None:
    """Select the closed Q1 fragment renderer without widening authored inputs."""

    from .type_env import (
        ListTypeRef,
        PathTypeRef,
        PrimitiveTypeRef,
        RecordTypeRef,
        UnionTypeRef,
    )


    if kind == "path":
        return "posix-path-line" if isinstance(type_ref, PathTypeRef) else None
    if kind != "value":
        return None

    def canonical_json_admissible(candidate: object) -> bool:
        if isinstance(candidate, PrimitiveTypeRef):
            return candidate.name in {
                "String",
                "Int",
                "Float",
                "Bool",
                "Json",
                "Value",
            } or bool(candidate.allowed_values)
        if isinstance(candidate, (PathTypeRef, RecordTypeRef)):
            return True
        if isinstance(candidate, UnionTypeRef):
            return True
        if isinstance(candidate, ListTypeRef):
            return canonical_json_admissible(candidate.item_type_ref)
        return False

    return "canonical-json" if canonical_json_admissible(type_ref) else None
