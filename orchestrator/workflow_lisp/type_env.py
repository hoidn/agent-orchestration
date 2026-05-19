"""Resolved frontend-local type references for Workflow Lisp expressions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from .definitions import EnumDef, PathDef, RecordDef, UnionDef, UnionVariant, WorkflowLispModule
from .diagnostics import LispFrontendCompileError, LispFrontendDiagnostic
from .spans import SourcePosition, SourceSpan

if TYPE_CHECKING:
    from .modules import ModuleImportScope


PRELUDE_PRIMITIVE_TYPE_NAMES = frozenset(
    {
        "String",
        "Int",
        "Bool",
        "Json",
        "Provider",
        "Prompt",
        "PathRel",
        "RunId",
        "Symbol",
    }
)


def _prelude_span(name: str) -> SourceSpan:
    return SourceSpan(
        start=SourcePosition(path=f"<prelude:{name}>", line=1, column=1, offset=0),
        end=SourcePosition(path=f"<prelude:{name}>", line=1, column=1, offset=0),
    )


PRELUDE_PATH_TYPES = {
    "Path.state-root": PathDef(
        name="Path.state-root",
        kind="relpath",
        under="state",
        must_exist=False,
        span=_prelude_span("Path.state-root"),
    ),
    "Path.artifact-root": PathDef(
        name="Path.artifact-root",
        kind="relpath",
        under="artifacts",
        must_exist=False,
        span=_prelude_span("Path.artifact-root"),
    ),
}


PRELUDE_TYPE_NAMES = PRELUDE_PRIMITIVE_TYPE_NAMES | frozenset(PRELUDE_PATH_TYPES)


@dataclass(frozen=True)
class PrimitiveTypeRef:
    """One prelude or enum type reference."""

    name: str
    allowed_values: tuple[str, ...] = ()


@dataclass(frozen=True)
class PathTypeRef:
    """One resolved path-contract type reference."""

    name: str
    definition: PathDef


@dataclass(frozen=True)
class RecordTypeRef:
    """One resolved record type reference."""

    name: str
    definition: RecordDef
    field_types: dict[str, "TypeRef"]


@dataclass(frozen=True)
class UnionTypeRef:
    """One resolved union type reference."""

    name: str
    definition: UnionDef
    variant_field_types: dict[str, dict[str, "TypeRef"]]


@dataclass(frozen=True)
class VariantCaseTypeRef:
    """One resolved union-variant payload reference."""

    union_name: str
    variant_name: str
    definition: UnionVariant


TypeRef = PrimitiveTypeRef | PathTypeRef | RecordTypeRef | UnionTypeRef | VariantCaseTypeRef


class FrontendTypeEnvironment:
    """Resolved type lookup helpers derived from a Stage 1 module."""

    def __init__(
        self,
        type_refs: dict[str, TypeRef],
        *,
        import_scope: "ModuleImportScope | None" = None,
        canonical_name_overrides: dict[str, str] | None = None,
    ):
        self._type_refs = dict(type_refs)
        self._import_scope = import_scope
        self._canonical_name_overrides = dict(canonical_name_overrides or {})

    @classmethod
    def from_module(
        cls,
        module: WorkflowLispModule,
        *,
        import_scope: "ModuleImportScope | None" = None,
        imported_type_refs: dict[str, TypeRef] | None = None,
    ) -> "FrontendTypeEnvironment":
        type_refs: dict[str, TypeRef] = {
            name: PrimitiveTypeRef(name=name) for name in PRELUDE_PRIMITIVE_TYPE_NAMES
        }
        type_refs.update(
            {
                name: PathTypeRef(name=name, definition=definition)
                for name, definition in PRELUDE_PATH_TYPES.items()
            }
        )
        for definition in module.definitions:
            if isinstance(definition, EnumDef):
                type_refs[definition.name] = PrimitiveTypeRef(
                    name=definition.name,
                    allowed_values=tuple(value.name for value in definition.values),
                )
            elif isinstance(definition, PathDef):
                type_refs[definition.name] = PathTypeRef(name=definition.name, definition=definition)
            elif isinstance(definition, RecordDef):
                type_refs[definition.name] = RecordTypeRef(
                    name=definition.name,
                    definition=definition,
                    field_types={},
                )
            elif isinstance(definition, UnionDef):
                type_refs[definition.name] = UnionTypeRef(
                    name=definition.name,
                    definition=definition,
                    variant_field_types={},
                )
        for definition in module.definitions:
            if isinstance(definition, RecordDef):
                record_ref = type_refs.get(definition.name)
                if isinstance(record_ref, RecordTypeRef):
                    record_ref.field_types.update(
                        {
                            field.name: type_refs[field.type_name]
                            for field in definition.fields
                            if field.type_name in type_refs
                        }
                    )
            elif isinstance(definition, UnionDef):
                union_ref = type_refs.get(definition.name)
                if isinstance(union_ref, UnionTypeRef):
                    union_ref.variant_field_types.update(
                        {
                            variant.name: {
                                field.name: type_refs[field.type_name]
                                for field in variant.fields
                                if field.type_name in type_refs
                            }
                            for variant in definition.variants
                        }
                    )
        if imported_type_refs:
            type_refs.update(imported_type_refs)
        return cls(type_refs, import_scope=import_scope)

    def resolve_type(
        self,
        name: str,
        *,
        span: SourceSpan,
        form_path: tuple[str, ...],
        expansion_stack: tuple[object, ...] = (),
    ) -> TypeRef:
        lookup_name = self._canonical_name_overrides.get(name, name)
        local_ref = self._type_refs.get(lookup_name)
        if local_ref is not None:
            return local_ref
        if self._import_scope is not None:
            lookup_name = self._import_scope.resolve_type_name(
                lookup_name,
                span=span,
                form_path=form_path,
            )
        try:
            return self._type_refs[lookup_name]
        except KeyError:
            _raise_error(
                f"unknown type `{name}`",
                code="type_unknown",
                span=span,
                form_path=form_path,
                expansion_stack=expansion_stack,
            )

    def record_field(
        self,
        record_type: RecordTypeRef | VariantCaseTypeRef,
        field_name: str,
        *,
        span: SourceSpan,
        form_path: tuple[str, ...],
        expansion_stack: tuple[object, ...] = (),
    ) -> TypeRef:
        fields = (
            record_type.definition.fields
            if isinstance(record_type, (RecordTypeRef, VariantCaseTypeRef))
            else ()
        )
        for field in fields:
            if field.name == field_name:
                if isinstance(record_type, RecordTypeRef):
                    resolved = record_type.field_types.get(field_name)
                else:
                    union_type = self._type_refs.get(record_type.union_name)
                    resolved = (
                        union_type.variant_field_types.get(record_type.variant_name, {}).get(field_name)
                        if isinstance(union_type, UnionTypeRef)
                        else None
                    )
                if resolved is not None:
                    return resolved
                return self.resolve_type(
                    field.type_name,
                    span=span,
                    form_path=form_path,
                    expansion_stack=expansion_stack,
                )
        _raise_error(
            f"unknown field `{field_name}`",
            code="record_field_unknown",
            span=span,
            form_path=form_path,
            expansion_stack=expansion_stack,
        )

    def union_variant(
        self,
        union_type: UnionTypeRef,
        variant_name: str,
        *,
        span: SourceSpan,
        form_path: tuple[str, ...],
        expansion_stack: tuple[object, ...] = (),
    ) -> VariantCaseTypeRef:
        for variant in union_type.definition.variants:
            if variant.name == variant_name:
                return VariantCaseTypeRef(
                    union_name=union_type.name,
                    variant_name=variant_name,
                    definition=variant,
                )
        _raise_error(
            f"unknown union variant `{variant_name}` for `{union_type.name}`",
            code="union_variant_unknown",
            span=span,
            form_path=form_path,
            expansion_stack=expansion_stack,
        )

    def field_exists_in_other_variant(
        self,
        variant_type: VariantCaseTypeRef,
        field_name: str,
    ) -> bool:
        union_type = self._type_refs.get(variant_type.union_name)
        if not isinstance(union_type, UnionTypeRef):
            return False
        for variant in union_type.definition.variants:
            if variant.name == variant_type.variant_name:
                continue
            for field in variant.fields:
                if field.name == field_name:
                    return True
        return False


def _raise_error(
    message: str,
    *,
    code: str,
    span: SourceSpan,
    form_path: tuple[str, ...],
    expansion_stack: tuple[object, ...] = (),
) -> None:
    raise LispFrontendCompileError(
        (
            LispFrontendDiagnostic(
                code=code,
                message=message,
                span=span,
                form_path=form_path,
                expansion_stack=expansion_stack,
            ),
        )
    )
