"""Structural parametric constraint normalization and checking."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from .diagnostics import LispFrontendCompileError, LispFrontendDiagnostic
from .procedures import ProcedureConstraintFieldRequirementSyntax, ProcedureConstraintSyntax
from .spans import SourceSpan
from .type_env import (
    FrontendTypeEnvironment,
    PathTypeRef,
    RecordTypeRef,
    TypeRef,
    UnionTypeRef,
    render_type_ref,
    type_refs_compatible,
)


@dataclass(frozen=True)
class SharedUnionFieldCapability:
    """Compile-time proof that one concrete union exposes a shared field."""

    union_type_name: str
    field_name: str
    field_type_ref: TypeRef
    type_param_name: str | None = None


@dataclass(frozen=True)
class ConstraintEvaluationResult:
    """Compile-time outputs produced by successful structural checking."""

    shared_union_field_capabilities: tuple[SharedUnionFieldCapability, ...] = ()


def provisional_shared_union_field_capabilities(
    *,
    where_clauses: tuple[ProcedureConstraintSyntax, ...],
    type_env: FrontendTypeEnvironment,
    type_param_names: frozenset[str] = frozenset(),
) -> tuple[SharedUnionFieldCapability, ...]:
    """Return authored shared-field capabilities keyed by the type-parameter name."""

    capabilities: list[SharedUnionFieldCapability] = []
    for clause in where_clauses:
        if clause.constraint_name != "has-shared-union-field":
            continue
        if clause.field_name is None or clause.field_type_name is None:
            continue
        if clause.field_type_name in type_param_names:
            # Covered by the call-site pass (`evaluate_parametric_constraints`),
            # which resolves the field type from the bound `type_bindings` once a
            # concrete call site is known.
            continue
        capabilities.append(
            SharedUnionFieldCapability(
                union_type_name="",
                field_name=clause.field_name,
                field_type_ref=type_env.resolve_type(
                    clause.field_type_name,
                    span=clause.span,
                    form_path=clause.form_path,
                    expansion_stack=clause.expansion_stack,
                ),
                type_param_name=clause.subject_name,
            )
        )
    return tuple(capabilities)


@dataclass(frozen=True)
class _NormalizedFieldRequirement:
    field_name: str
    field_type_ref: TypeRef
    authored_type_name: str
    syntax: ProcedureConstraintFieldRequirementSyntax


@dataclass(frozen=True)
class _NormalizedConstraint:
    subject_name: str
    constraint_name: str
    syntax: ProcedureConstraintSyntax


@dataclass(frozen=True)
class _KindConstraint(_NormalizedConstraint):
    expected_kind: str


@dataclass(frozen=True)
class _FieldConstraint(_NormalizedConstraint):
    field_name: str
    field_type_ref: TypeRef
    authored_type_name: str


@dataclass(frozen=True)
class _UnionVariantConstraint(_NormalizedConstraint):
    variant_name: str
    field_requirements: tuple[_NormalizedFieldRequirement, ...]


def evaluate_parametric_constraints(
    *,
    procedure_name: str,
    where_clauses: tuple[ProcedureConstraintSyntax, ...],
    type_bindings: Mapping[str, TypeRef],
    type_env: FrontendTypeEnvironment,
    call_span: SourceSpan,
    call_form_path: tuple[str, ...],
    call_expansion_stack: tuple[object, ...] = (),
) -> ConstraintEvaluationResult:
    """Validate first-tranche structural constraints for one generic call."""

    capabilities: list[SharedUnionFieldCapability] = []
    for clause in where_clauses:
        normalized = _normalize_constraint(clause, type_env=type_env, type_bindings=type_bindings)
        concrete_type = type_bindings.get(normalized.subject_name)
        if concrete_type is None:
            _raise_constraint_error(
                code="parametric_constraint_malformed",
                message=(
                    f"procedure `{procedure_name}` could not resolve a concrete type binding for "
                    f"`{normalized.subject_name}` before checking `{_render_constraint(clause)}`"
                ),
                span=call_span,
                form_path=call_form_path,
                expansion_stack=call_expansion_stack,
                notes=_constraint_notes(clause),
            )
        capabilities.extend(
            _check_constraint(
                procedure_name=procedure_name,
                constraint=normalized,
                concrete_type=concrete_type,
                call_span=call_span,
                call_form_path=call_form_path,
                call_expansion_stack=call_expansion_stack,
            )
        )
    return ConstraintEvaluationResult(shared_union_field_capabilities=tuple(capabilities))


def _resolve_field_type_ref(
    field_type_name: str,
    *,
    type_bindings: Mapping[str, TypeRef],
    type_env: FrontendTypeEnvironment,
    span: SourceSpan,
    form_path: tuple[str, ...],
    expansion_stack: tuple[object, ...],
) -> TypeRef:
    """Resolve a constraint field-type name, deferring to the call site's
    bound type parameters (rule 3) before falling back to the type
    environment. Contract: docs/design/workflow_lisp_parametric_type_system.md,
    Constraint Vocabulary rule 3."""
    if field_type_name in type_bindings:
        return type_bindings[field_type_name]
    return type_env.resolve_type(
        field_type_name,
        span=span,
        form_path=form_path,
        expansion_stack=expansion_stack,
    )


def _normalize_constraint(
    clause: ProcedureConstraintSyntax,
    *,
    type_env: FrontendTypeEnvironment,
    type_bindings: Mapping[str, TypeRef],
) -> _NormalizedConstraint:
    if clause.constraint_name == "is-record":
        return _KindConstraint(
            subject_name=clause.subject_name,
            constraint_name=clause.constraint_name,
            syntax=clause,
            expected_kind="record",
        )
    if clause.constraint_name == "is-union":
        return _KindConstraint(
            subject_name=clause.subject_name,
            constraint_name=clause.constraint_name,
            syntax=clause,
            expected_kind="union",
        )
    if clause.constraint_name in {"has-field", "has-shared-union-field"}:
        if clause.field_name is None or clause.field_type_name is None:
            _raise_constraint_error(
                code="parametric_constraint_malformed",
                message=f"malformed structural constraint `{_render_constraint(clause)}`",
                span=clause.span,
                form_path=clause.form_path,
                expansion_stack=clause.expansion_stack,
            )
        return _FieldConstraint(
            subject_name=clause.subject_name,
            constraint_name=clause.constraint_name,
            syntax=clause,
            field_name=clause.field_name,
            field_type_ref=_resolve_field_type_ref(
                clause.field_type_name,
                type_bindings=type_bindings,
                type_env=type_env,
                span=clause.span,
                form_path=clause.form_path,
                expansion_stack=clause.expansion_stack,
            ),
            authored_type_name=clause.field_type_name,
        )
    if clause.constraint_name == "has-union-variant":
        if clause.variant_name is None:
            _raise_constraint_error(
                code="parametric_constraint_malformed",
                message=f"malformed structural constraint `{_render_constraint(clause)}`",
                span=clause.span,
                form_path=clause.form_path,
                expansion_stack=clause.expansion_stack,
            )
        return _UnionVariantConstraint(
            subject_name=clause.subject_name,
            constraint_name=clause.constraint_name,
            syntax=clause,
            variant_name=clause.variant_name,
            field_requirements=tuple(
                _normalize_field_requirement(
                    requirement,
                    type_env=type_env,
                    type_bindings=type_bindings,
                    form_path=clause.form_path,
                )
                for requirement in clause.field_requirements
            ),
        )
    _raise_constraint_error(
        code="parametric_constraint_unknown",
        message=f"unknown structural constraint `{clause.constraint_name}` in `{_render_constraint(clause)}`",
        span=clause.span,
        form_path=clause.form_path,
        expansion_stack=clause.expansion_stack,
    )


def _normalize_field_requirement(
    requirement: ProcedureConstraintFieldRequirementSyntax,
    *,
    type_env: FrontendTypeEnvironment,
    type_bindings: Mapping[str, TypeRef],
    form_path: tuple[str, ...],
) -> _NormalizedFieldRequirement:
    return _NormalizedFieldRequirement(
        field_name=requirement.field_name,
        field_type_ref=_resolve_field_type_ref(
            requirement.field_type_name,
            type_bindings=type_bindings,
            type_env=type_env,
            span=requirement.span,
            form_path=form_path,
            expansion_stack=requirement.expansion_stack,
        ),
        authored_type_name=requirement.field_type_name,
        syntax=requirement,
    )


def _check_constraint(
    *,
    procedure_name: str,
    constraint: _NormalizedConstraint,
    concrete_type: TypeRef,
    call_span: SourceSpan,
    call_form_path: tuple[str, ...],
    call_expansion_stack: tuple[object, ...],
) -> tuple[SharedUnionFieldCapability, ...]:
    if isinstance(constraint, _KindConstraint):
        if constraint.expected_kind == "record" and isinstance(concrete_type, RecordTypeRef):
            return ()
        if constraint.expected_kind == "union" and isinstance(concrete_type, UnionTypeRef):
            return ()
        _raise_unsatisfied_constraint(
            procedure_name=procedure_name,
            clause=constraint.syntax,
            concrete_type=concrete_type,
            detail=f"`{render_type_ref(concrete_type)}` is not a {constraint.expected_kind}",
            call_span=call_span,
            call_form_path=call_form_path,
            call_expansion_stack=call_expansion_stack,
        )
    if isinstance(constraint, _FieldConstraint):
        if constraint.constraint_name == "has-field":
            _check_record_field_constraint(
                procedure_name=procedure_name,
                constraint=constraint,
                concrete_type=concrete_type,
                call_span=call_span,
                call_form_path=call_form_path,
                call_expansion_stack=call_expansion_stack,
            )
            return ()
        capability = _check_shared_union_field_constraint(
            procedure_name=procedure_name,
            constraint=constraint,
            concrete_type=concrete_type,
            call_span=call_span,
            call_form_path=call_form_path,
            call_expansion_stack=call_expansion_stack,
        )
        return (capability,)
    if isinstance(constraint, _UnionVariantConstraint):
        _check_union_variant_constraint(
            procedure_name=procedure_name,
            constraint=constraint,
            concrete_type=concrete_type,
            call_span=call_span,
            call_form_path=call_form_path,
            call_expansion_stack=call_expansion_stack,
        )
        return ()
    _raise_constraint_error(
        code="parametric_constraint_malformed",
        message=f"unhandled structural constraint `{constraint.constraint_name}`",
        span=call_span,
        form_path=call_form_path,
        expansion_stack=call_expansion_stack,
    )


def constraint_field_type_satisfied(actual: TypeRef, expected: TypeRef) -> bool:
    """Directional rule-4 check: `actual` (the caller's concrete field type)
    is assignable to `expected` (the constraint's field type).
    Contract: docs/design/workflow_lisp_parametric_type_system.md,
    Constraint Vocabulary rule 4."""
    if type_refs_compatible(expected, actual):
        return True
    if isinstance(expected, PathTypeRef) and isinstance(actual, PathTypeRef):
        return (
            actual.definition.under == expected.definition.under
            and (actual.definition.must_exist or not expected.definition.must_exist)
        )
    return False


def _check_record_field_constraint(
    *,
    procedure_name: str,
    constraint: _FieldConstraint,
    concrete_type: TypeRef,
    call_span: SourceSpan,
    call_form_path: tuple[str, ...],
    call_expansion_stack: tuple[object, ...],
) -> None:
    if not isinstance(concrete_type, RecordTypeRef):
        _raise_unsatisfied_constraint(
            procedure_name=procedure_name,
            clause=constraint.syntax,
            concrete_type=concrete_type,
            detail=f"`{render_type_ref(concrete_type)}` is not a record",
            call_span=call_span,
            call_form_path=call_form_path,
            call_expansion_stack=call_expansion_stack,
        )
    actual_type = concrete_type.field_types.get(constraint.field_name)
    if actual_type is None:
        _raise_unsatisfied_constraint(
            procedure_name=procedure_name,
            clause=constraint.syntax,
            concrete_type=concrete_type,
            detail=f"record `{concrete_type.name}` does not declare field `{constraint.field_name}`",
            call_span=call_span,
            call_form_path=call_form_path,
            call_expansion_stack=call_expansion_stack,
        )
    if not constraint_field_type_satisfied(actual_type, constraint.field_type_ref):
        _raise_unsatisfied_constraint(
            procedure_name=procedure_name,
            clause=constraint.syntax,
            concrete_type=concrete_type,
            detail=(
                f"field `{constraint.field_name}` has type `{render_type_ref(actual_type)}`"
                f" instead of `{constraint.authored_type_name}`"
            ),
            call_span=call_span,
            call_form_path=call_form_path,
            call_expansion_stack=call_expansion_stack,
        )


def _check_union_variant_constraint(
    *,
    procedure_name: str,
    constraint: _UnionVariantConstraint,
    concrete_type: TypeRef,
    call_span: SourceSpan,
    call_form_path: tuple[str, ...],
    call_expansion_stack: tuple[object, ...],
) -> None:
    if not isinstance(concrete_type, UnionTypeRef):
        _raise_unsatisfied_constraint(
            procedure_name=procedure_name,
            clause=constraint.syntax,
            concrete_type=concrete_type,
            detail=f"`{render_type_ref(concrete_type)}` is not a union",
            call_span=call_span,
            call_form_path=call_form_path,
            call_expansion_stack=call_expansion_stack,
        )
    variant_field_types = concrete_type.variant_field_types.get(constraint.variant_name)
    if variant_field_types is None:
        _raise_unsatisfied_constraint(
            procedure_name=procedure_name,
            clause=constraint.syntax,
            concrete_type=concrete_type,
            detail=f"union `{concrete_type.name}` does not declare variant `{constraint.variant_name}`",
            call_span=call_span,
            call_form_path=call_form_path,
            call_expansion_stack=call_expansion_stack,
        )
    for requirement in constraint.field_requirements:
        actual_type = variant_field_types.get(requirement.field_name)
        if actual_type is None:
            _raise_unsatisfied_constraint(
                procedure_name=procedure_name,
                clause=constraint.syntax,
                concrete_type=concrete_type,
                detail=(
                    f"variant `{constraint.variant_name}` of `{concrete_type.name}` does not declare "
                    f"field `{requirement.field_name}`"
                ),
                call_span=call_span,
                call_form_path=call_form_path,
                call_expansion_stack=call_expansion_stack,
            )
        if not constraint_field_type_satisfied(actual_type, requirement.field_type_ref):
            _raise_unsatisfied_constraint(
                procedure_name=procedure_name,
                clause=constraint.syntax,
                concrete_type=concrete_type,
                detail=(
                    f"variant `{constraint.variant_name}` field `{requirement.field_name}` has type "
                    f"`{render_type_ref(actual_type)}` instead of `{requirement.authored_type_name}`"
                ),
                call_span=call_span,
                call_form_path=call_form_path,
                call_expansion_stack=call_expansion_stack,
            )


def _check_shared_union_field_constraint(
    *,
    procedure_name: str,
    constraint: _FieldConstraint,
    concrete_type: TypeRef,
    call_span: SourceSpan,
    call_form_path: tuple[str, ...],
    call_expansion_stack: tuple[object, ...],
) -> SharedUnionFieldCapability:
    if not isinstance(concrete_type, UnionTypeRef):
        _raise_unsatisfied_constraint(
            procedure_name=procedure_name,
            clause=constraint.syntax,
            concrete_type=concrete_type,
            detail=f"`{render_type_ref(concrete_type)}` is not a union",
            call_span=call_span,
            call_form_path=call_form_path,
            call_expansion_stack=call_expansion_stack,
        )
    if not concrete_type.definition.variants:
        _raise_unsatisfied_constraint(
            procedure_name=procedure_name,
            clause=constraint.syntax,
            concrete_type=concrete_type,
            detail=f"union `{concrete_type.name}` has no variants",
            call_span=call_span,
            call_form_path=call_form_path,
            call_expansion_stack=call_expansion_stack,
        )
    for variant in concrete_type.definition.variants:
        actual_type = concrete_type.variant_field_types.get(variant.name, {}).get(constraint.field_name)
        if actual_type is None:
            _raise_unsatisfied_constraint(
                procedure_name=procedure_name,
                clause=constraint.syntax,
                concrete_type=concrete_type,
                detail=(
                    f"variant `{variant.name}` of `{concrete_type.name}` does not declare "
                    f"shared field `{constraint.field_name}`"
                ),
                call_span=call_span,
                call_form_path=call_form_path,
                call_expansion_stack=call_expansion_stack,
            )
        if not constraint_field_type_satisfied(actual_type, constraint.field_type_ref):
            _raise_unsatisfied_constraint(
                procedure_name=procedure_name,
                clause=constraint.syntax,
                concrete_type=concrete_type,
                detail=(
                    f"variant `{variant.name}` field `{constraint.field_name}` has type "
                    f"`{render_type_ref(actual_type)}` instead of `{constraint.authored_type_name}`"
                ),
                call_span=call_span,
                call_form_path=call_form_path,
                call_expansion_stack=call_expansion_stack,
            )
    return SharedUnionFieldCapability(
        union_type_name=concrete_type.name,
        field_name=constraint.field_name,
        field_type_ref=constraint.field_type_ref,
    )


def _raise_unsatisfied_constraint(
    *,
    procedure_name: str,
    clause: ProcedureConstraintSyntax,
    concrete_type: TypeRef,
    detail: str,
    call_span: SourceSpan,
    call_form_path: tuple[str, ...],
    call_expansion_stack: tuple[object, ...],
) -> None:
    _raise_constraint_error(
        code="parametric_constraint_unsatisfied",
        message=(
            f"procedure `{procedure_name}` requires `{_render_constraint(clause)}` for "
            f"`{clause.subject_name}`, but the inferred concrete type `{render_type_ref(concrete_type)}` "
            f"does not satisfy it: {detail}"
        ),
        span=call_span,
        form_path=call_form_path,
        expansion_stack=call_expansion_stack,
        notes=_constraint_notes(clause),
    )


def _render_constraint(clause: ProcedureConstraintSyntax) -> str:
    parts = [clause.subject_name, clause.constraint_name]
    if clause.variant_name is not None:
        parts.append(clause.variant_name)
    if clause.field_name is not None and clause.field_type_name is not None:
        parts.extend((clause.field_name, clause.field_type_name))
    parts.extend(
        f"({requirement.field_name} {requirement.field_type_name})"
        for requirement in clause.field_requirements
    )
    return " ".join(parts)


def _constraint_notes(clause: ProcedureConstraintSyntax) -> tuple[str, ...]:
    return (
        "constraint declared at "
        f"{clause.span.start.path}:{clause.span.start.line}:{clause.span.start.column}",
    )


def _raise_constraint_error(
    *,
    code: str,
    message: str,
    span: SourceSpan,
    form_path: tuple[str, ...],
    expansion_stack: tuple[object, ...] = (),
    notes: tuple[str, ...] = (),
) -> None:
    raise LispFrontendCompileError(
        (
            LispFrontendDiagnostic(
                code=code,
                message=message,
                span=span,
                form_path=form_path,
                expansion_stack=expansion_stack,
                notes=notes,
                phase="typecheck",
            ),
        )
    )
