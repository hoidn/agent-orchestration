"""Compile-time procedure-reference helpers for Workflow Lisp."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from .diagnostics import LispFrontendCompileError, LispFrontendDiagnostic
from .expressions import NameExpr, ProcRefLiteralExpr
from .type_env import ProcRefTypeRef, TypeRef

if TYPE_CHECKING:
    from .modules import ModuleImportScope
    from .procedures import ProcedureCatalog, ProcedureSignature


@dataclass(frozen=True)
class ProcRefAuthoritySource:
    """Where a resolved procedure reference came from."""

    kind: str
    procedure_name: str


@dataclass(frozen=True)
class ResolvedProcRef:
    """Concrete compile-time procedure target selected from a literal."""

    procedure_name: str
    signature_params: tuple[tuple[str, TypeRef], ...]
    return_type_ref: TypeRef
    authority_source: ProcRefAuthoritySource


@dataclass(frozen=True)
class ProcRefRequirement:
    """Required signature shape for one compile-time proc-ref position."""

    role_name: str
    required_param_types: tuple[TypeRef, ...]
    required_return_type: TypeRef


@dataclass(frozen=True)
class ProcRefResolutionContext:
    """Local/import visibility metadata for ProcRef diagnostics."""

    import_scope: "ModuleImportScope | None" = None
    local_raw_names: frozenset[str] = frozenset()
    visible_procedure_names_by_module: Mapping[str, frozenset[str]] = field(default_factory=dict)


def proc_ref_type_from_signature(signature: "ProcedureSignature") -> ProcRefTypeRef:
    return ProcRefTypeRef(
        name=_proc_ref_type_name(signature.params, signature.return_type_ref),
        param_type_refs=tuple(type_ref for _, type_ref in signature.params),
        return_type_ref=signature.return_type_ref,
    )


def proc_ref_target_name(expr: ProcRefLiteralExpr | NameExpr) -> str:
    if isinstance(expr, ProcRefLiteralExpr):
        return expr.target_name
    return expr.name


def validate_proc_ref_signature(
    expected: ProcRefTypeRef,
    actual_signature: "ProcedureSignature",
    *,
    span,
    form_path,
    expansion_stack=(),
) -> None:
    actual_params = tuple(type_ref for _, type_ref in actual_signature.params)
    if actual_params != expected.param_type_refs or actual_signature.return_type_ref != expected.return_type_ref:
        raise LispFrontendCompileError(
            (
                LispFrontendDiagnostic(
                    code="proc_ref_signature_invalid",
                    message=f"procedure ref `{actual_signature.name}` does not match `{expected.name}`",
                    span=span,
                    form_path=form_path,
                    expansion_stack=expansion_stack,
                ),
            )
        )


def resolve_proc_ref_name(
    target_name: str,
    *,
    procedure_catalog: "ProcedureCatalog",
    span,
    form_path,
    authored_name: str | None = None,
    expansion_stack=(),
    expected_type: ProcRefTypeRef | None = None,
    resolution_context: ProcRefResolutionContext | None = None,
) -> ResolvedProcRef:
    signature = procedure_catalog.signatures_by_name.get(target_name)
    if signature is None:
        _raise_unknown_or_private(
            authored_name=authored_name or target_name,
            resolution_context=resolution_context,
            span=span,
            form_path=form_path,
            expansion_stack=expansion_stack,
        )
    if expected_type is not None:
        validate_proc_ref_signature(
            expected_type,
            signature,
            span=span,
            form_path=form_path,
            expansion_stack=expansion_stack,
        )
    return ResolvedProcRef(
        procedure_name=signature.name,
        signature_params=signature.params,
        return_type_ref=signature.return_type_ref,
        authority_source=ProcRefAuthoritySource(kind="linked_procedure", procedure_name=signature.name),
    )


def resolve_proc_ref_expr(
    expr: ProcRefLiteralExpr | NameExpr,
    *,
    procedure_catalog: "ProcedureCatalog",
    span,
    form_path,
    expected_type: ProcRefTypeRef | None = None,
    resolution_context: ProcRefResolutionContext | None = None,
) -> ResolvedProcRef:
    authored_name = expr.authored_name if isinstance(expr, ProcRefLiteralExpr) else expr.name
    expansion_stack = getattr(expr, "expansion_stack", ())
    return resolve_proc_ref_name(
        proc_ref_target_name(expr),
        procedure_catalog=procedure_catalog,
        span=span,
        form_path=form_path,
        authored_name=authored_name,
        expansion_stack=expansion_stack,
        expected_type=expected_type,
        resolution_context=resolution_context,
    )


def _raise_unknown_or_private(
    *,
    authored_name: str,
    resolution_context: ProcRefResolutionContext | None,
    span,
    form_path,
    expansion_stack,
) -> None:
    if resolution_context is not None:
        qualified_target = _qualified_import_target(
            authored_name,
            import_scope=resolution_context.import_scope,
        )
        if qualified_target is not None:
            module_name, member_name = qualified_target
            visible_names = resolution_context.visible_procedure_names_by_module.get(
                module_name,
                frozenset(),
            )
            if member_name in visible_names:
                raise LispFrontendCompileError(
                    (
                        LispFrontendDiagnostic(
                            code="proc_ref_private_import_invalid",
                            message=(
                                f"procedure ref `{authored_name}` names a private imported procedure"
                            ),
                            span=span,
                            form_path=form_path,
                            expansion_stack=expansion_stack,
                        ),
                    )
                )
    raise LispFrontendCompileError(
        (
            LispFrontendDiagnostic(
                code="proc_ref_unknown",
                message=f"unknown procedure ref `{authored_name}`",
                span=span,
                form_path=form_path,
                expansion_stack=expansion_stack,
            ),
        )
    )


def _qualified_import_target(
    authored_name: str,
    *,
    import_scope: "ModuleImportScope | None",
) -> tuple[str, str] | None:
    if import_scope is None:
        return None
    if authored_name.count(".") == 1:
        alias_name, _, member_name = authored_name.partition(".")
        module_name = import_scope.alias_to_module.get(alias_name)
        if module_name is not None:
            return module_name, member_name
    if "/" in authored_name:
        module_name, _, member_name = authored_name.rpartition("/")
        if module_name in import_scope.explicitly_imported_modules:
            return module_name, member_name
    return None


def _proc_ref_type_name(params: tuple[tuple[str, TypeRef], ...], return_type_ref: TypeRef) -> str:
    if len(params) == 1:
        return f"ProcRef[{params[0][1].name} -> {return_type_ref.name}]"
    if params:
        params_label = " ".join(type_ref.name for _, type_ref in params)
        return f"ProcRef[({params_label}) -> {return_type_ref.name}]"
    return f"ProcRef[() -> {return_type_ref.name}]"
