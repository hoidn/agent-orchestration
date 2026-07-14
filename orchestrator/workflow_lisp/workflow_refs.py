"""Compile-time workflow-reference helpers for Workflow Lisp."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from .diagnostics import LispFrontendCompileError, LispFrontendDiagnostic
from .expression_traversal import iter_child_exprs
from .expressions import (
    CallExpr,
    CommandResultExpr,
    ContinueExpr,
    EnumMemberExpr,
    DoneExpr,
    IfExpr,
    LetStarExpr,
    LoopRecurExpr,
    MatchExpr,
    NameExpr,
    ProcedureCallExpr,
    ProduceOneOfExpr,
    ProviderResultExpr,
    RecordExpr,
    RunProviderPhaseExpr,
    UnionVariantExpr,
    WorkflowRefLiteralExpr,
)
from .spans import SourceSpan
from .type_env import RecordTypeRef, TypeRef, UnionTypeRef, WorkflowRefTypeRef

if TYPE_CHECKING:
    from orchestrator.workflow.loaded_bundle import LoadedWorkflowBundle
    from .procedures import TypedProcedureDef
    from .workflows import TypedWorkflowDef, WorkflowCatalog, WorkflowSignature


@dataclass(frozen=True)
class WorkflowRefAuthoritySource:
    """Where a resolved workflow reference came from."""

    kind: str
    workflow_name: str


@dataclass(frozen=True)
class WorkflowExternRebindingPlan:
    """Provider/prompt extern names that would need explicit rebinding."""

    provider_bindings: Mapping[str, tuple[str, ...]]
    prompt_bindings: Mapping[str, tuple[str, ...]]

    @property
    def is_empty(self) -> bool:
        return not self.provider_bindings and not self.prompt_bindings


@dataclass(frozen=True)
class ResolvedWorkflowRef:
    """Concrete compile-time workflow target selected from a literal."""

    workflow_name: str
    signature_params: tuple[tuple[str, TypeRef], ...]
    return_type_ref: RecordTypeRef | UnionTypeRef
    authority_source: WorkflowRefAuthoritySource
    extern_rebinding_plan: WorkflowExternRebindingPlan


@dataclass(frozen=True)
class WorkflowRefRequirement:
    """Required signature shape for one compile-time workflow-ref position."""

    role_name: str
    required_param_types: tuple[TypeRef, ...]
    required_return_type: TypeRef


@dataclass(frozen=True)
class WorkflowRefCallPlan:
    """Concrete lowered call target and extern plan for one workflow-ref role."""

    role_name: str
    workflow_name: str
    binding_names: tuple[str, ...]
    return_type_ref: RecordTypeRef | UnionTypeRef
    extern_rebinding_plan: WorkflowExternRebindingPlan


@dataclass(frozen=True)
class WorkflowRefEnvironment:
    """Collection of resolved compile-time workflow refs by authored role."""

    refs_by_name: Mapping[str, ResolvedWorkflowRef]


@dataclass(frozen=True)
class WorkflowCallableSpecialization:
    """Compile-time workflow-ref bindings attached to a specialized callable."""

    base_name: str
    workflow_ref_bindings: Mapping[str, ResolvedWorkflowRef]
    specialized_name: str


def workflow_ref_binding_names(params: tuple[tuple[str, TypeRef], ...]) -> tuple[str, ...]:
    return tuple(name for name, type_ref in params if isinstance(type_ref, WorkflowRefTypeRef))


def type_ref_contains_workflow_ref(type_ref: TypeRef) -> bool:
    if isinstance(type_ref, WorkflowRefTypeRef):
        return True
    if isinstance(type_ref, RecordTypeRef):
        return any(type_ref_contains_workflow_ref(field_type) for field_type in type_ref.field_types.values())
    if isinstance(type_ref, UnionTypeRef):
        return any(
            type_ref_contains_workflow_ref(field_type)
            for field_types in type_ref.variant_field_types.values()
            for field_type in field_types.values()
        )
    return False


def validate_workflow_ref_signature(
    expected: WorkflowRefTypeRef,
    actual_signature: "WorkflowSignature",
    *,
    span: SourceSpan,
    form_path: tuple[str, ...],
) -> None:
    actual_params = tuple(type_ref for _, type_ref in actual_signature.params)
    if actual_params != expected.param_type_refs or actual_signature.return_type_ref != expected.return_type_ref:
        raise LispFrontendCompileError(
            (
                LispFrontendDiagnostic(
                    code="workflow_ref_signature_invalid",
                    message=(
                        f"workflow ref `{actual_signature.name}` does not match `{expected.name}`"
                    ),
                    span=span,
                    form_path=form_path,
                ),
            )
        )


def workflow_ref_type_from_signature(signature: "WorkflowSignature") -> WorkflowRefTypeRef:
    return WorkflowRefTypeRef(
        name=_workflow_ref_type_name(signature.params, signature.return_type_ref),
        param_type_refs=tuple(type_ref for _, type_ref in signature.params),
        return_type_ref=signature.return_type_ref,
    )


def workflow_ref_target_name(expr: WorkflowRefLiteralExpr | NameExpr | EnumMemberExpr) -> str:
    if isinstance(expr, WorkflowRefLiteralExpr):
        return expr.target_name
    if isinstance(expr, EnumMemberExpr):
        return f"{expr.enum_name}.{expr.member_name}"
    return expr.name


def resolve_workflow_ref_name(
    target_name: str,
    *,
    workflow_catalog: "WorkflowCatalog",
    span: SourceSpan,
    form_path: tuple[str, ...],
    expansion_stack: tuple[object, ...] = (),
    expected_type: WorkflowRefTypeRef | None = None,
    typed_workflows_by_name: Mapping[str, "TypedWorkflowDef"] | None = None,
    allow_extern_rebinding: bool,
) -> ResolvedWorkflowRef:
    signature = workflow_catalog.signatures_by_name.get(target_name)
    if signature is None:
        raise LispFrontendCompileError(
            (
                LispFrontendDiagnostic(
                    code="workflow_ref_unknown",
                    message=f"unknown workflow ref `{target_name}`",
                    span=span,
                    form_path=form_path,
                    expansion_stack=expansion_stack,
                ),
            )
        )
    if expected_type is not None:
        validate_workflow_ref_signature(
            expected_type,
            signature,
            span=span,
            form_path=form_path,
        )
    imported_bundle = workflow_catalog.imported_bundles_by_name.get(signature.name)
    extern_rebinding_plan = _extern_rebinding_plan_for_target(
        workflow_name=signature.name,
        imported_bundle=imported_bundle,
        typed_workflows_by_name=typed_workflows_by_name or {},
    )
    if not allow_extern_rebinding and not extern_rebinding_plan.is_empty:
        raise LispFrontendCompileError(
            (
                LispFrontendDiagnostic(
                    code="workflow_ref_extern_rebinding_unsatisfied",
                    message=(
                        f"workflow ref `{target_name}` requires provider/prompt extern rebinding in this slice"
                    ),
                    span=span,
                    form_path=form_path,
                    expansion_stack=expansion_stack,
                ),
            )
        )
    authority_kind = "imported_bundle" if imported_bundle is not None else "linked_workflow"
    return ResolvedWorkflowRef(
        workflow_name=signature.name,
        signature_params=signature.params,
        return_type_ref=signature.return_type_ref,
        authority_source=WorkflowRefAuthoritySource(kind=authority_kind, workflow_name=signature.name),
        extern_rebinding_plan=extern_rebinding_plan,
    )


def resolve_workflow_ref_expr(
    expr: WorkflowRefLiteralExpr | NameExpr | EnumMemberExpr,
    *,
    workflow_catalog: "WorkflowCatalog",
    span: SourceSpan,
    form_path: tuple[str, ...],
    expansion_stack: tuple[object, ...] = (),
    expected_type: WorkflowRefTypeRef | None = None,
    typed_workflows_by_name: Mapping[str, "TypedWorkflowDef"] | None = None,
    allow_extern_rebinding: bool,
) -> ResolvedWorkflowRef:
    return resolve_workflow_ref_name(
        workflow_ref_target_name(expr),
        workflow_catalog=workflow_catalog,
        span=span,
        form_path=form_path,
        expansion_stack=expansion_stack,
        expected_type=expected_type,
        typed_workflows_by_name=typed_workflows_by_name,
        allow_extern_rebinding=allow_extern_rebinding,
    )


def resolve_workflow_ref_literal(
    literal: WorkflowRefLiteralExpr,
    *,
    expected_type: WorkflowRefTypeRef,
    workflow_catalog: "WorkflowCatalog",
    typed_workflows_by_name: Mapping[str, "TypedWorkflowDef"] | None = None,
    allow_extern_rebinding: bool,
) -> ResolvedWorkflowRef:
    return resolve_workflow_ref_name(
        literal.target_name,
        workflow_catalog=workflow_catalog,
        span=literal.span,
        form_path=literal.form_path,
        expansion_stack=literal.expansion_stack,
        expected_type=expected_type,
        typed_workflows_by_name=typed_workflows_by_name,
        allow_extern_rebinding=allow_extern_rebinding,
    )


def specialization_name(base_name: str, bindings: Mapping[str, ResolvedWorkflowRef]) -> str:
    parts = [base_name]
    for param_name, resolved in sorted(bindings.items()):
        target = resolved.workflow_name.replace("::", "__").replace("/", "_").replace("-", "_").replace(".", "_")
        parts.extend(("spec", param_name.replace("-", "_"), target))
    return "__".join(parts)


def workflow_ref_binding_identity(
    bindings: Mapping[str, ResolvedWorkflowRef],
) -> tuple[tuple[str, str], ...]:
    """Return the exact, workspace-independent identity of WorkflowRef bindings."""

    return tuple(
        sorted(
            (param_name, resolved.workflow_name)
            for param_name, resolved in bindings.items()
        )
    )


def collision_specialization_name(
    legacy_name: str,
    bindings: Mapping[str, ResolvedWorkflowRef],
) -> str:
    """Disambiguate a colliding legacy key without changing unique keys."""

    identity = workflow_ref_binding_identity(bindings)
    payload = "".join(
        f"{len(param_name)}:{param_name}{len(target_name)}:{target_name}"
        for param_name, target_name in identity
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return f"{legacy_name}__workflow_ref__{digest}"


def collect_workflow_extern_names(expr: Any) -> tuple[set[str], set[str]]:
    providers: set[str] = set()
    prompts: set[str] = set()

    def walk(node: Any) -> None:
        if isinstance(node, ProviderResultExpr):
            if isinstance(node.provider, NameExpr):
                providers.add(node.provider.name)
            if isinstance(node.prompt, NameExpr):
                prompts.add(node.prompt.name)
        elif isinstance(node, RunProviderPhaseExpr):
            if isinstance(node.provider, NameExpr):
                providers.add(node.provider.name)
            if isinstance(node.prompt, NameExpr):
                prompts.add(node.prompt.name)
        elif isinstance(node, ProduceOneOfExpr):
            if isinstance(node.producer.provider_expr, NameExpr):
                providers.add(node.producer.provider_expr.name)
            if isinstance(node.producer.prompt_expr, NameExpr):
                prompts.add(node.producer.prompt_expr.name)
        for child in iter_child_exprs(node):
            walk(child)

    walk(expr)
    return providers, prompts


def _extern_rebinding_plan_for_target(
    *,
    workflow_name: str,
    imported_bundle: "LoadedWorkflowBundle | None",
    typed_workflows_by_name: Mapping[str, "TypedWorkflowDef"],
) -> WorkflowExternRebindingPlan:
    if imported_bundle is not None:
        return WorkflowExternRebindingPlan(provider_bindings={}, prompt_bindings={})
    typed_workflow = typed_workflows_by_name.get(workflow_name)
    if typed_workflow is None:
        return WorkflowExternRebindingPlan(provider_bindings={}, prompt_bindings={})
    provider_names, prompt_names = collect_workflow_extern_names(typed_workflow.typed_body.expr)
    return WorkflowExternRebindingPlan(
        provider_bindings={name: (name,) for name in sorted(provider_names)},
        prompt_bindings={name: (name,) for name in sorted(prompt_names)},
    )


def _workflow_ref_type_name(
    params: tuple[tuple[str, TypeRef], ...],
    return_type_ref: RecordTypeRef | UnionTypeRef,
) -> str:
    param_names = tuple(type_ref.name for _, type_ref in params)
    if len(param_names) == 1:
        params_label = param_names[0]
    else:
        params_label = "(" + " ".join(param_names) + ")"
    return f"WorkflowRef[{params_label} -> {return_type_ref.name}]"
