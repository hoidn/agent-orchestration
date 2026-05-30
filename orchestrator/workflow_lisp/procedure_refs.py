"""Compile-time procedure-reference helpers for Workflow Lisp."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from .diagnostics import LispFrontendCompileError, LispFrontendDiagnostic
from .expressions import BindProcExpr, NameExpr, ProcRefLiteralExpr
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
class BoundProcArg:
    """One keyword argument captured by `bind-proc`."""

    name: str
    value_expr: object
    type_ref: TypeRef
    source_identity: str
    keyword_span: object
    keyword_form_path: tuple[str, ...]
    keyword_expansion_stack: tuple[object, ...] = ()


@dataclass(frozen=True)
class ResolvedProcRefValue:
    """One compile-time ProcRef value after following forwarding/bind-proc."""

    procedure_name: str
    signature_params: tuple[tuple[str, TypeRef], ...]
    return_type_ref: TypeRef
    authority_source: ProcRefAuthoritySource
    bound_args: tuple[BoundProcArg, ...] = ()

    @property
    def residual_params(self) -> tuple[tuple[str, TypeRef], ...]:
        bound_names = {binding.name for binding in self.bound_args}
        return tuple(
            (name, type_ref)
            for name, type_ref in self.signature_params
            if name not in bound_names
        )

    @property
    def residual_type_ref(self) -> ProcRefTypeRef:
        return proc_ref_type_from_parts(self.residual_params, self.return_type_ref)

    @property
    def call_target_name(self) -> str:
        if not self.bound_args:
            return self.procedure_name
        return proc_ref_specialization_name(
            self.procedure_name,
            self.bound_args,
            signature_params=self.signature_params,
            residual_type_ref=self.residual_type_ref,
        )


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
    return proc_ref_type_from_parts(signature.params, signature.return_type_ref)


def proc_ref_type_from_parts(
    params: tuple[tuple[str, TypeRef], ...],
    return_type_ref: TypeRef,
) -> ProcRefTypeRef:
    return ProcRefTypeRef(
        name=_proc_ref_type_name(params, return_type_ref),
        param_type_refs=tuple(type_ref for _, type_ref in params),
        return_type_ref=return_type_ref,
    )


def proc_ref_target_name(expr: ProcRefLiteralExpr | NameExpr) -> str:
    if isinstance(expr, ProcRefLiteralExpr):
        return expr.target_name
    return expr.name


def proc_ref_specialization_name(
    procedure_name: str,
    bound_args: tuple[BoundProcArg, ...],
    *,
    signature_params: tuple[tuple[str, TypeRef], ...],
    residual_type_ref: ProcRefTypeRef,
) -> str:
    binding_by_name = {binding.name: binding for binding in bound_args}
    digest = hashlib.sha1(
        "|".join(
            [
                procedure_name,
                residual_type_ref.name,
                *(
                    f"{binding.name}:{binding.type_ref.name}:{binding.source_identity}"
                    for param_name, _ in signature_params
                    if (binding := binding_by_name.get(param_name)) is not None
                ),
            ]
        ).encode("utf-8")
    ).hexdigest()[:12]
    normalized_base = procedure_name.replace("/", ".").replace("::", ".").replace("-", "_")
    return f"%proc-ref.{normalized_base}.{digest}"


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


def validate_proc_ref_value(
    value: ResolvedProcRefValue,
    *,
    expected_type: ProcRefTypeRef | None,
    span,
    form_path,
    expansion_stack=(),
) -> None:
    if expected_type is None:
        return
    if value.residual_type_ref != expected_type:
        raise LispFrontendCompileError(
            (
                LispFrontendDiagnostic(
                    code="proc_ref_signature_invalid",
                    message=f"procedure ref `{value.procedure_name}` does not match `{expected_type.name}`",
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
    if (authored_name or target_name).startswith("%let-proc."):
        raise LispFrontendCompileError(
            (
                LispFrontendDiagnostic(
                    code="let_proc_generated_name_private",
                    message="authored references to generated `let-proc` names are not allowed",
                    span=span,
                    form_path=form_path,
                    expansion_stack=expansion_stack,
                ),
            )
        )
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


def resolve_proc_ref_value(
    expr: object,
    *,
    procedure_catalog: "ProcedureCatalog",
    proc_ref_env: Mapping[str, ResolvedProcRefValue] | None = None,
    resolution_context: ProcRefResolutionContext | None = None,
    expected_type: ProcRefTypeRef | None = None,
) -> ResolvedProcRefValue | None:
    env = proc_ref_env or {}
    if isinstance(expr, ResolvedProcRefValue):
        value = expr
    elif isinstance(expr, NameExpr):
        value = env.get(expr.name)
        if value is None:
            return None
    elif isinstance(expr, ProcRefLiteralExpr):
        resolved = resolve_proc_ref_expr(
            expr,
            procedure_catalog=procedure_catalog,
            span=expr.span,
            form_path=expr.form_path,
            resolution_context=resolution_context,
        )
        value = ResolvedProcRefValue(
            procedure_name=resolved.procedure_name,
            signature_params=resolved.signature_params,
            return_type_ref=resolved.return_type_ref,
            authority_source=resolved.authority_source,
        )
    elif isinstance(expr, BindProcExpr):
        base_value = resolve_proc_ref_value(
            expr.base_expr,
            procedure_catalog=procedure_catalog,
            proc_ref_env=env,
            resolution_context=resolution_context,
        )
        if base_value is None:
            return None
        param_types = dict(base_value.signature_params)
        bound_args_by_name = {binding.name: binding for binding in base_value.bound_args}
        for binding in expr.bindings:
            type_ref = param_types.get(binding.name)
            if type_ref is None:
                raise LispFrontendCompileError(
                    (
                        LispFrontendDiagnostic(
                            code="proc_ref_binding_unknown",
                            message=f"unknown `bind-proc` keyword `:{binding.name}`",
                            span=binding.keyword_span,
                            form_path=binding.keyword_form_path,
                            expansion_stack=binding.keyword_expansion_stack,
                        ),
                    )
                )
            if binding.name in bound_args_by_name:
                raise LispFrontendCompileError(
                    (
                        LispFrontendDiagnostic(
                            code="proc_ref_binding_duplicate",
                            message=f"duplicate `bind-proc` keyword `:{binding.name}`",
                            span=binding.keyword_span,
                            form_path=binding.keyword_form_path,
                            expansion_stack=binding.keyword_expansion_stack,
                        ),
                    )
                )
            resolved_proc_ref_binding = None
            if isinstance(type_ref, ProcRefTypeRef):
                resolved_proc_ref_binding = resolve_proc_ref_value(
                    binding.value_expr,
                    procedure_catalog=procedure_catalog,
                    proc_ref_env=env,
                    resolution_context=resolution_context,
                    expected_type=type_ref,
                )
            bound_args_by_name[binding.name] = BoundProcArg(
                name=binding.name,
                value_expr=binding.value_expr,
                type_ref=type_ref,
                source_identity=(
                    _proc_ref_value_identity(resolved_proc_ref_binding)
                    if resolved_proc_ref_binding is not None
                    else _source_identity(binding.value_expr)
                ),
                keyword_span=binding.keyword_span,
                keyword_form_path=binding.keyword_form_path,
                keyword_expansion_stack=binding.keyword_expansion_stack,
            )
        ordered_bound_args = tuple(
            bound_args_by_name[param_name]
            for param_name, _ in base_value.signature_params
            if param_name in bound_args_by_name
        )
        value = ResolvedProcRefValue(
            procedure_name=base_value.procedure_name,
            signature_params=base_value.signature_params,
            return_type_ref=base_value.return_type_ref,
            authority_source=base_value.authority_source,
            bound_args=ordered_bound_args,
        )
    else:
        return None
    validate_proc_ref_value(
        value,
        expected_type=expected_type,
        span=getattr(expr, "span", None),
        form_path=getattr(expr, "form_path", ()),
        expansion_stack=getattr(expr, "expansion_stack", ()),
    )
    return value


def _proc_ref_value_identity(value: ResolvedProcRefValue) -> str:
    return f"proc-ref:{value.call_target_name}"


def _source_identity(expr: object) -> str:
    literal_kind = getattr(expr, "literal_kind", None)
    literal_value = getattr(expr, "value", None)
    if literal_kind is not None:
        return f"literal:{literal_kind}:{literal_value!r}"
    base = getattr(expr, "base", None)
    fields = getattr(expr, "fields", None)
    if isinstance(base, NameExpr) and isinstance(fields, tuple):
        return f"field:{base.name}:{'.'.join(fields)}"
    if isinstance(expr, NameExpr):
        return f"name:{expr.name}"
    span = getattr(expr, "span", None)
    if span is None:
        return repr(expr)
    start = span.start
    return f"{start.path}:{start.line}:{start.column}"


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
