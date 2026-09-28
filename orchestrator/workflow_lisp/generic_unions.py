"""First-order generic unions (target 2.33): application, instantiation, ordering.

Contract: `docs/design/workflow_lisp_parametric_type_system.md`, section
"Proposed CF-1 First-Order Generic Unions".

Representation. A generic declaration (`defunion Outcome :forall (T E) ...`)
is a `UnionDef` with non-empty `type_params`; its template `UnionTypeRef` has
`type_args == ()` and variant field types that contain `TypeParamRef`s. An
application such as `Outcome[Int String]` is a `UnionTypeRef` with:

- `definition`: the generic declaration itself (constructor identity; imports
  share this object, and its span carries the defining module path);
- `type_args`: the ordered resolved argument types (argument identities);
- `variant_field_types`: the template's field types with the arguments
  substituted, so constructors and matches check the instantiated payload;
- `name`: `<template name>[<rendered args>]`, e.g. `Outcome[Int String]` or
  `gu/lib::Outcome[Int String]` for an imported template.

Applied unions compare by constructor identity plus argument compatibility
(`type_env.type_refs_compatible`); legacy unions keep their existing rules.
Arguments may still be `TypeParamRef`s inside a generic `defproc`; they stay
compile-time only until specialization substitutes them.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable

from .definitions import DefinitionNode, UnionDef
from .diagnostics import LispFrontendCompileError, LispFrontendDiagnostic
from .spans import SourceSpan
from .syntax import GENERIC_UNION_MIN_TARGET_DSL_VERSION, target_dsl_supports_generic_unions
from .type_env import (
    TypeRef,
    UnionTypeRef,
    _first_type_param_ref,
    _render_type_expr,
    reject_untransportable_union_payloads,
    render_type_ref,
    substitute_type_params,
)
from .type_expressions import (
    AppliedTypeExpr,
    ParsedTypeExpr,
    parse_type_expression,
    type_expression_application_heads,
)


def application_target_diagnostic(
    parsed: ParsedTypeExpr,
    *,
    authored_name: str,
    target_dsl_version: str,
    span: SourceSpan,
    form_path: tuple[str, ...],
    expansion_stack: tuple[object, ...] = (),
) -> LispFrontendDiagnostic | None:
    """Return the target diagnostic for a type application below target 2.33."""

    if target_dsl_supports_generic_unions(target_dsl_version) or not type_expression_application_heads(parsed):
        return None
    return LispFrontendDiagnostic(
        code="generic_union_requires_dsl_2_33",
        message=(
            f"type application `{authored_name}` requires target DSL "
            f"{GENERIC_UNION_MIN_TARGET_DSL_VERSION} or newer; module targets {target_dsl_version}"
        ),
        span=span,
        form_path=form_path,
        expansion_stack=expansion_stack,
    )


def is_generic_union_template(type_ref: object) -> bool:
    """Return whether `type_ref` is an unapplied generic union declaration."""

    return (
        isinstance(type_ref, UnionTypeRef)
        and bool(type_ref.definition.type_params)
        and not type_ref.type_args
    )


def reject_unapplied_generic_union(
    template: UnionTypeRef,
    *,
    span: SourceSpan,
    form_path: tuple[str, ...],
    expansion_stack: tuple[object, ...] = (),
) -> None:
    """Reject a bare generic union name used as a type."""

    params = " ".join(template.definition.type_params)
    _raise(
        "generic_union_arity_mismatch",
        f"generic union `{template.name}` must be applied to "
        f"{len(template.definition.type_params)} type argument(s) `[{params}]`",
        span=span,
        form_path=form_path,
        expansion_stack=expansion_stack,
        notes=_declared_at(template.definition),
    )


def resolve_generic_union_application(
    parsed: AppliedTypeExpr,
    *,
    head_ref: TypeRef,
    resolve_arg: Callable[[ParsedTypeExpr], TypeRef],
    span: SourceSpan,
    form_path: tuple[str, ...],
    expansion_stack: tuple[object, ...] = (),
) -> UnionTypeRef:
    """Resolve `Head[Arg ...]` to an applied union, checking head and arity."""

    definition = getattr(head_ref, "definition", None)
    if not is_generic_union_template(head_ref):
        _raise(
            "generic_union_not_generic",
            f"`{parsed.head}` is not a generic union and cannot take type arguments",
            span=span,
            form_path=form_path,
            expansion_stack=expansion_stack,
            notes=_declared_at(definition),
        )
    type_params = head_ref.definition.type_params
    if len(parsed.args) != len(type_params):
        _raise(
            "generic_union_arity_mismatch",
            f"generic union `{parsed.head}` expects {len(type_params)} type argument(s) "
            f"`[{' '.join(type_params)}]` but got {len(parsed.args)}",
            span=span,
            form_path=form_path,
            expansion_stack=expansion_stack,
            notes=_declared_at(definition),
        )
    type_args = tuple(
        _resolve_argument(
            arg,
            head=parsed.head,
            definition=definition,
            resolve_arg=resolve_arg,
            span=span,
            form_path=form_path,
            expansion_stack=expansion_stack,
        )
        for arg in parsed.args
    )
    applied = instantiate_generic_union(head_ref, type_args)
    reject_untransportable_union_payloads(
        applied,
        span=span,
        form_path=form_path,
        expansion_stack=expansion_stack,
        notes=_declared_at(definition),
    )
    return applied


def instantiate_generic_union(
    template: UnionTypeRef,
    type_args: tuple[TypeRef, ...],
) -> UnionTypeRef:
    """Apply a generic union template to resolved argument types."""

    bindings = dict(zip(template.definition.type_params, type_args, strict=True))
    return _applied_union(template, template.name, type_args, bindings)


def substitute_applied_union(
    applied: UnionTypeRef,
    bindings: dict[str, TypeRef],
) -> UnionTypeRef:
    """Substitute procedure type parameters inside an applied union."""

    type_args = tuple(substitute_type_params(arg, bindings) for arg in applied.type_args)
    # Applied names are always `<template name>[...]`; template names have no `[`.
    return _applied_union(applied, applied.name.partition("[")[0], type_args, bindings)


def applied_union_name(base_name: str, type_args: tuple[TypeRef, ...]) -> str:
    """Render `Head[Arg ...]`; `base_name` is the template name as seen by the renderer."""

    return f"{base_name}[{' '.join(render_type_ref(arg) for arg in type_args)}]"


def bind_applied_union_arguments(
    expected: UnionTypeRef,
    actual: UnionTypeRef,
    *,
    bind: Callable[[TypeRef, TypeRef], None],
    raise_error: Callable[..., None],
    span: SourceSpan,
    form_path: tuple[str, ...],
) -> None:
    """Match an applied union from a generic signature against a concrete one.

    Invariant binding: `actual` must apply the same declaration (defining
    module included) with the same arity, and then `bind` matches each
    argument position in order, phantom arguments included. `bind` is the
    caller's recursive binder, so repeated parameters unify through it.
    A constructor mismatch is a `type_mismatch` noting both declarations.
    """

    if expected.definition != actual.definition or len(expected.type_args) != len(actual.type_args):
        raise_error(
            f"procedure argument expected `{expected.name}` but got `{actual.name}`, "
            "which does not apply the same generic union declaration",
            code="type_mismatch",
            span=span,
            form_path=form_path,
            notes=(*_declared_at(expected.definition), *_declared_at(actual.definition)),
        )
    for expected_arg, actual_arg in zip(expected.type_args, actual.type_args, strict=True):
        bind(expected_arg, actual_arg)


def generic_union_fill_order(
    definitions: Iterable[DefinitionNode],
    *,
    lookup: Callable[[str], object],
) -> tuple[UnionDef, ...]:
    """Order local generic unions so each follows the generic unions it applies.

    Instantiating an application needs the applied template's field types, so
    templates are resolved dependencies-first. A generic union whose fields
    apply itself, directly or through other local generic unions, is a
    recursive instantiation cycle and is rejected. Imported templates are
    already resolved, and the module graph is acyclic.
    """

    generic = [
        definition
        for definition in definitions
        if isinstance(definition, UnionDef) and definition.type_params
    ]
    ordered: list[UnionDef] = []
    active: list[UnionDef] = []

    def visit(definition: UnionDef) -> None:
        if _contains(ordered, definition):
            return
        active.append(definition)
        for variant in definition.variants:
            for field in variant.fields:
                for dependency in _applied_generic_unions(field.type_name, field.span, lookup):
                    if _contains(active, dependency):
                        _raise_cycle(active, dependency, span=field.span)
                    if _contains(generic, dependency):
                        visit(dependency)
        active.pop()
        ordered.append(definition)

    for definition in generic:
        visit(definition)
    return tuple(ordered)


def _applied_union(
    source: UnionTypeRef,
    base_name: str,
    type_args: tuple[TypeRef, ...],
    bindings: dict[str, TypeRef],
) -> UnionTypeRef:
    # Only substitute fields that mention a parameter: parameter-free field
    # types may be records whose fields are still being resolved, and must
    # stay shared references rather than copies.
    return UnionTypeRef(
        name=applied_union_name(base_name, type_args),
        definition=source.definition,
        variant_field_types={
            variant_name: {
                field_name: (
                    substitute_type_params(field_type, bindings)
                    if _first_type_param_ref(field_type) is not None
                    else field_type
                )
                for field_name, field_type in field_types.items()
            }
            for variant_name, field_types in source.variant_field_types.items()
        },
        type_args=type_args,
    )


def _resolve_argument(
    arg: ParsedTypeExpr,
    *,
    head: str,
    definition: UnionDef,
    resolve_arg: Callable[[ParsedTypeExpr], TypeRef],
    span: SourceSpan,
    form_path: tuple[str, ...],
    expansion_stack: tuple[object, ...],
) -> TypeRef:
    try:
        return resolve_arg(arg)
    except LispFrontendCompileError as error:
        # Re-report an unknown argument name as an unresolved application
        # argument, pointing at the generic declaration as well.
        if error.diagnostics[0].code != "type_unknown":
            raise
        raise LispFrontendCompileError(
            (
                LispFrontendDiagnostic(
                    code="generic_union_unresolved_argument",
                    message=(
                        f"type argument `{_render_type_expr(arg)}` of generic union `{head}` "
                        "does not resolve to a type in scope"
                    ),
                    span=span,
                    form_path=form_path,
                    expansion_stack=expansion_stack,
                    notes=_declared_at(definition),
                ),
            )
        ) from error


def _applied_generic_unions(
    type_name: str,
    span: SourceSpan,
    lookup: Callable[[str], object],
) -> tuple[UnionDef, ...]:
    parsed = parse_type_expression(type_name, span=span, form_path=())
    return tuple(
        target.definition
        for target in (lookup(head) for head in type_expression_application_heads(parsed))
        if isinstance(target, UnionTypeRef) and target.definition.type_params
    )


def _contains(definitions: list[UnionDef], definition: UnionDef) -> bool:
    return any(candidate is definition for candidate in definitions)


def _raise_cycle(active: list[UnionDef], dependency: UnionDef, *, span: SourceSpan) -> None:
    start = next(index for index, candidate in enumerate(active) if candidate is dependency)
    path = " -> ".join(definition.name for definition in (*active[start:], dependency))
    _raise(
        "generic_union_instantiation_cycle",
        f"generic union `{dependency.name}` is instantiated recursively ({path})",
        span=span,
        form_path=("workflow-lisp", "defunion", active[-1].name),
        notes=_declared_at(dependency),
    )


def _declared_at(definition: object) -> tuple[str, ...]:
    span = getattr(definition, "span", None)
    if span is None:
        return ()
    start = span.start
    return (f"`{definition.name}` declared at {start.path}:{start.line}:{start.column}",)


def _raise(
    code: str,
    message: str,
    *,
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
            ),
        )
    )
