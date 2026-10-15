"""Procedure specialization ownership for Workflow Lisp stage-3 compilation."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from dataclasses import replace
from pathlib import Path
from typing import Any, Literal
from types import MappingProxyType

from .contracts import derive_workflow_boundary_fields, is_transportable_result_type
from .diagnostics import LispFrontendCompileError, LispFrontendDiagnostic
from .effects import EMPTY_EFFECT_SUMMARY
from .expression_traversal import _rebuild_with_replacements, is_pure_projection_expr, iter_child_exprs
from .expressions import (
    AgentExpr,
    BindProcExpr,
    GeneratedRelpathSeedExpr,
    LoopStateSeedExpr,
    LoopStateUpdateExpr,
    PhaseTargetExpr,
    ProcRefLiteralExpr,
    ProviderBundlePathExpr,
    CallExpr,
    CommandResultExpr,
    FieldAccessExpr,
    ExprNode,
    EnumMemberExpr,
    FinalizeSelectedItemExpr,
    IfExpr,
    LetStarExpr,
    LiteralExpr,
    MaterializeViewExpr,
    MatchExpr,
    NameExpr,
    ProcedureCallExpr,
    ProduceOneOfExpr,
    ProviderResultExpr,
    RequestInputExpr,
    RecordExpr,
    ResourceTransitionExpr,
    ResumeOrStartExpr,
    RunProviderPhaseExpr,
    UnionVariantExpr,
    WithPhaseExpr,
    WorkflowRefLiteralExpr,
)
from .procedure_refs import ResolvedProcRefValue, resolve_proc_ref_value
from .procedures import (
    ProcedureCallableSpecialization,
    ProcedureCatalog,
    ProcedureLoweringMode,
    ProcedureParam,
    TypedProcedureDef,
    _procedure_signature_local_type_bindings,
    parametric_specialization_name,
    proc_ref_specialization_name as proc_ref_call_specialization_name,
    procedure_type_env_for,
)
from .result_guidance import validate_result_guidance_example
from .syntax import target_dsl_supports_generic_unions, target_dsl_supports_provider_context_values, target_dsl_supports_local_hook_inference
from .spans import SourceSpan
from .type_env import (
    FrontendTypeEnvironment,
    PathTypeRef,
    PrimitiveTypeRef,
    ProcRefTypeRef,
    RecordTypeRef,
    TypeRef,
    UnionTypeRef,
    VariantCaseTypeRef,
    WorkflowRefTypeRef,
    ensure_no_type_params,
    render_type_ref,
    substitute_type_params,
)
from .workflow_refs import (
    ResolvedWorkflowRef,
    collision_specialization_name,
    resolve_workflow_ref_expr,
    specialization_name,
    workflow_ref_binding_identity,
)
from .workflows import TypedWorkflowDef, analyze_workflow_boundary_type


@dataclass(frozen=True)
class ProcedureSpecializationRequest:
    """Compile-time-only specialization inputs for one procedure materialization."""

    procedure: TypedProcedureDef
    type_bindings: Mapping[str, TypeRef]
    workflow_ref_bindings: Mapping[str, ResolvedWorkflowRef]
    proc_ref_bindings: Mapping[str, ResolvedProcRefValue]
    value_bindings: Mapping[str, Any]
    shared_union_field_capabilities: tuple[object, ...]
    remaining_params: tuple[tuple[str, TypeRef], ...]
    workflow_path: Path
    typed_procedures_by_name: Mapping[str, TypedProcedureDef]
    specialized_name: str | None = None
    origin_span: object | None = None
    origin_form_path: tuple[str, ...] | None = None


def procedure_catalog_with_specializations(
    procedure_catalog: ProcedureCatalog,
    typed_procedures: tuple[TypedProcedureDef, ...],
) -> ProcedureCatalog:
    signatures_by_name = dict(procedure_catalog.signatures_by_name)
    definitions_by_name = dict(procedure_catalog.definitions_by_name)
    for procedure in typed_procedures:
        signatures_by_name[procedure.signature.name] = procedure.signature
        definitions_by_name[procedure.definition.name] = procedure.definition
    return ProcedureCatalog(
        signatures_by_name=signatures_by_name,
        definitions_by_name=definitions_by_name,
        call_graph=procedure_catalog.call_graph,
    )


def materialized_specialization_rows(
    procedure: TypedProcedureDef,
    *,
    workflow_ref_bindings: Mapping[str, ResolvedWorkflowRef],
    proc_ref_bindings: Mapping[str, ResolvedProcRefValue],
    typed_procedures: Mapping[str, TypedProcedureDef],
) -> tuple[TypedProcedureDef, ...]:
    """Select exact compiler-owned rows without reconstructing their keys."""

    existing = procedure.specialization
    base_name = existing.base_name if existing is not None else procedure.signature.name
    expected_workflow_bindings = {
        **dict(getattr(existing, "workflow_ref_bindings", {})),
        **dict(workflow_ref_bindings),
    }
    expected_proc_bindings = {
        **dict(getattr(existing, "proc_ref_bindings", {})),
        **dict(proc_ref_bindings),
    }
    expected_proc_identity = tuple(
        sorted(
            (param_name, resolved.call_target_name)
            for param_name, resolved in expected_proc_bindings.items()
        )
    )
    matches: list[TypedProcedureDef] = []
    for candidate in typed_procedures.values():
        specialization = candidate.specialization
        if specialization is None or specialization.base_name != base_name:
            continue
        if workflow_ref_binding_identity(
            specialization.workflow_ref_bindings
        ) != workflow_ref_binding_identity(expected_workflow_bindings):
            continue
        candidate_proc_identity = tuple(
            sorted(
                (param_name, resolved.call_target_name)
                for param_name, resolved in specialization.proc_ref_bindings.items()
            )
        )
        if candidate_proc_identity != expected_proc_identity:
            continue
        if dict(specialization.type_bindings) != dict(
            getattr(existing, "type_bindings", {})
        ):
            continue
        if dict(specialization.value_bindings) != dict(
            getattr(existing, "value_bindings", {})
        ):
            continue
        matches.append(candidate)
    return tuple(matches)


def _procedure_private_boundary_valid(
    procedure: TypedProcedureDef,
    *,
    type_env: FrontendTypeEnvironment,
) -> bool:
    """Return whether a procedure signature can become a private workflow."""

    try:
        if target_dsl_supports_provider_context_values(type_env.target_dsl_version):
            for _, type_ref in (*procedure.signature.params, ("return", procedure.signature.return_type_ref)):
                ensure_no_type_params(
                    type_ref,
                    span=procedure.definition.span,
                    form_path=procedure.definition.form_path,
                    expansion_stack=procedure.definition.expansion_stack,
                )
            return is_transportable_result_type(
                procedure.signature.return_type_ref,
                type_env=type_env,
            ) and all(
                is_transportable_result_type(type_ref, type_env=type_env)
                for _, type_ref in procedure.signature.params
            )
        if not isinstance(procedure.signature.return_type_ref, (RecordTypeRef, UnionTypeRef)):
            return False
        if not analyze_workflow_boundary_type(
            procedure.signature.return_type_ref,
            source_path=("return",),
            allow_union=True,
        ).lowerable:
            return False
        return all(
            analyze_workflow_boundary_type(
                type_ref,
                source_path=(param_name,),
                allow_top_level_workflow_ref=True,
            ).lowerable
            for param_name, type_ref in procedure.signature.params
        )
    except (LispFrontendCompileError, TypeError):
        return False


def _procedure_private_body_valid(
    procedure: TypedProcedureDef,
    *,
    typed_procedures_by_name: Mapping[str, TypedProcedureDef],
    type_env: FrontendTypeEnvironment,
    closed_program: bool = False,
    procedure_type_envs: Mapping[str, FrontendTypeEnvironment] | None = None,
    workflow_signatures_by_name: Mapping[str, Any] | None = None,
) -> bool:
    """Return whether a procedure body exports only workflow-boundary values.

    `workflow_signatures_by_name` optionally enables typing workflow `call`
    let* bindings against the callee's return signature. Only the
    iteration-scope promotion re-check inside procedure-call lowering threads
    it; every other promotion site leaves it unset so existing non-loop procs
    never change lowering mode (defproc lowering-mode contract,
    docs/design/workflow_lisp_frontend_specification.md).
    """

    if closed_program and procedure.signature.requested_lowering_mode is ProcedureLoweringMode.PRIVATE_WORKFLOW:
        # Closed calls return evaluated values; the flat output-export seam is unused.
        return True


    current_type_env = (
        procedure_type_envs.get(procedure.definition.name, type_env)
        if procedure_type_envs is not None
        else type_env
    )
    if procedure.signature.type_params and target_dsl_supports_generic_unions(
        current_type_env.target_dsl_version or ""
    ):
        # An unspecialized generic is a template: only its monomorphic
        # specializations lower, and its signature may still hold applied
        # unions whose payloads are type parameters.
        return False

    return _private_workflow_body_exports_step_backed_outputs(
        procedure.typed_body.expr,
        return_type_ref=procedure.signature.return_type_ref,
        local_values=_procedure_signature_local_values(procedure, type_env=current_type_env),
        local_type_bindings=_procedure_signature_local_type_bindings(procedure),
        typed_procedures_by_name=typed_procedures_by_name,
        type_env=current_type_env,
        procedure_type_envs=procedure_type_envs,
        active_procedures=frozenset({procedure.definition.name}),
        workflow_signatures_by_name=workflow_signatures_by_name,
    )


def _private_workflow_result_type_for_expr(
    expr: Any,
    *,
    local_type_bindings: Mapping[str, TypeRef],
    typed_procedures_by_name: Mapping[str, TypedProcedureDef],
    type_env: FrontendTypeEnvironment,
    workflow_signatures_by_name: Mapping[str, Any] | None = None,
) -> TypeRef | None:
    """Resolve one private-workflow expression type for binding export checks."""

    if isinstance(expr, NameExpr):
        return local_type_bindings.get(expr.name)
    if isinstance(expr, FieldAccessExpr):
        current_type = _private_workflow_result_type_for_expr(
            expr.base,
            local_type_bindings=local_type_bindings,
            typed_procedures_by_name=typed_procedures_by_name,
            type_env=type_env,
            workflow_signatures_by_name=workflow_signatures_by_name,
        )
        for field_name in expr.fields:
            if not isinstance(current_type, (RecordTypeRef, VariantCaseTypeRef)):
                return None
            current_type = type_env.record_field(
                current_type,
                field_name,
                span=expr.span,
                form_path=expr.form_path,
                expansion_stack=expr.expansion_stack,
            )
        return current_type
    if isinstance(expr, LiteralExpr):
        if expr.literal_kind == "string":
            return PrimitiveTypeRef(name="String")
        if expr.literal_kind == "int":
            return PrimitiveTypeRef(name="Int")
        if expr.literal_kind == "bool":
            return PrimitiveTypeRef(name="Bool")
        return None
    if isinstance(expr, RecordExpr | UnionVariantExpr):
        return type_env.resolve_constructor_type(expr)
    if isinstance(
        expr,
        (
            ProviderResultExpr,
            CommandResultExpr,
            RunProviderPhaseExpr,
            ProduceOneOfExpr,
            ResumeOrStartExpr,
            MaterializeViewExpr,
        ),
    ):
        if isinstance(expr, ProviderResultExpr) and expr.capture_context is not None:
            from .context_types import contextual_type

            return contextual_type(
                type_env.resolve_type(
                    expr.returns_type_name,
                    span=expr.span,
                    form_path=expr.form_path,
                ),
                type_env.resolve_type(
                    "Context",
                    span=expr.span,
                    form_path=expr.form_path,
                ),
            )
        return type_env.resolve_type(
            expr.returns_type_name,
            span=expr.span,
            form_path=expr.form_path,
        )
    if isinstance(expr, ResourceTransitionExpr):
        if getattr(expr.spec, "mode", None) == "declared_transition":
            transition_def = type_env.resolve_transition_declaration(
                expr.spec.transition_ref_name or "",
                span=expr.span,
                form_path=expr.form_path,
                expansion_stack=expr.expansion_stack,
            )
            return type_env.resolve_type(
                transition_def.result_type_name,
                span=expr.span,
                form_path=expr.form_path,
                expansion_stack=expr.expansion_stack,
            )
        return type_env.resolve_type(
            "ResourceTransitionResult",
            span=expr.span,
            form_path=expr.form_path,
        )
    if isinstance(expr, FinalizeSelectedItemExpr):
        return type_env.resolve_type(
            "SelectedItemResult",
            span=expr.span,
            form_path=expr.form_path,
        )
    if isinstance(expr, ProcedureCallExpr):
        proc_ref_type = local_type_bindings.get(expr.callee_name)
        if isinstance(proc_ref_type, ProcRefTypeRef):
            return proc_ref_type.return_type_ref
        procedure = typed_procedures_by_name.get(expr.callee_name)
        if procedure is None:
            return None
        return procedure.signature.return_type_ref
    if isinstance(expr, CallExpr):
        # A let*-bound workflow call is step-backed by construction; it only
        # types when the caller threads a workflow-signature lookup, which the
        # iteration-scope promotion re-check alone does (defproc lowering-mode
        # contract, docs/design/workflow_lisp_frontend_specification.md).
        if workflow_signatures_by_name is None:
            return None
        callee_signature = workflow_signatures_by_name.get(expr.callee_name)
        if callee_signature is None:
            return None
        return callee_signature.return_type_ref
    if isinstance(expr, WithPhaseExpr):
        return _private_workflow_result_type_for_expr(
            expr.body,
            local_type_bindings=local_type_bindings,
            typed_procedures_by_name=typed_procedures_by_name,
            type_env=type_env,
            workflow_signatures_by_name=workflow_signatures_by_name,
        )
    if isinstance(expr, MatchExpr):
        subject_type = _private_workflow_result_type_for_expr(
            expr.subject,
            local_type_bindings=local_type_bindings,
            typed_procedures_by_name=typed_procedures_by_name,
            type_env=type_env,
            workflow_signatures_by_name=workflow_signatures_by_name,
        )
        arm_types: list[TypeRef | None] = []
        for arm in expr.arms:
            arm_local_types = dict(local_type_bindings)
            if isinstance(subject_type, UnionTypeRef):
                arm_local_types[arm.binding_name] = type_env.union_variant(
                    subject_type,
                    arm.variant_name,
                    span=expr.subject.span,
                    form_path=expr.subject.form_path,
                )
            arm_types.append(
                _private_workflow_result_type_for_expr(
                    arm.body,
                    local_type_bindings=arm_local_types,
                    typed_procedures_by_name=typed_procedures_by_name,
                    type_env=type_env,
                    workflow_signatures_by_name=workflow_signatures_by_name,
                )
            )
        if arm_types and all(arm_type == arm_types[0] for arm_type in arm_types):
            return arm_types[0]
        return None
    if isinstance(expr, LetStarExpr):
        child_local_types = dict(local_type_bindings)
        for binding_name, binding_expr in expr.bindings:
            binding_type = _private_workflow_result_type_for_expr(
                binding_expr,
                local_type_bindings=child_local_types,
                typed_procedures_by_name=typed_procedures_by_name,
                type_env=type_env,
                workflow_signatures_by_name=workflow_signatures_by_name,
            )
            if binding_type is None:
                return None
            child_local_types[binding_name] = binding_type
        return _private_workflow_result_type_for_expr(
            expr.body,
            local_type_bindings=child_local_types,
            typed_procedures_by_name=typed_procedures_by_name,
            type_env=type_env,
            workflow_signatures_by_name=workflow_signatures_by_name,
        )
    if isinstance(expr, IfExpr):
        then_type = _private_workflow_result_type_for_expr(
            expr.then_expr,
            local_type_bindings=local_type_bindings,
            typed_procedures_by_name=typed_procedures_by_name,
            type_env=type_env,
            workflow_signatures_by_name=workflow_signatures_by_name,
        )
        else_type = _private_workflow_result_type_for_expr(
            expr.else_expr,
            local_type_bindings=local_type_bindings,
            typed_procedures_by_name=typed_procedures_by_name,
            type_env=type_env,
            workflow_signatures_by_name=workflow_signatures_by_name,
        )
        if then_type is not None and then_type == else_type:
            return then_type
        return None
    return None


def _private_workflow_binding_local_value(
    expr: Any,
    *,
    binding_name: str,
    local_values: Mapping[str, Any],
    local_type_bindings: Mapping[str, TypeRef],
    typed_procedures_by_name: Mapping[str, TypedProcedureDef],
    type_env: FrontendTypeEnvironment,
    procedure_type_envs: Mapping[str, FrontendTypeEnvironment] | None = None,
    active_procedures: frozenset[str],
    workflow_signatures_by_name: Mapping[str, Any] | None = None,
) -> Any | None:
    """Return the step-backed local shape one private-workflow binding exports."""

    from .closed.command_templates import is_inline_let_binding_expr

    step_name = f"{binding_name}__{expr.step_name}" if isinstance(expr, CommandResultExpr) else binding_name
    if is_inline_let_binding_expr(expr):
        return _resolve_inline_expr_value(expr, local_values=local_values)
    if isinstance(expr, WithPhaseExpr):
        return _private_workflow_binding_local_value(
            expr.body,
            binding_name=binding_name,
            local_values=local_values,
            local_type_bindings=local_type_bindings,
            typed_procedures_by_name=typed_procedures_by_name,
            type_env=type_env,
            procedure_type_envs=procedure_type_envs,
            active_procedures=active_procedures,
            workflow_signatures_by_name=workflow_signatures_by_name,
        )
    if isinstance(expr, ProcedureCallExpr):
        callee_name = expr.callee_name
        bound_proc_ref = local_values.get(callee_name)
        if isinstance(bound_proc_ref, ResolvedProcRefValue):
            callee_name = bound_proc_ref.call_target_name
        callee = typed_procedures_by_name.get(callee_name)
        if callee is None or callee.definition.name in active_procedures:
            return None
        child_locals = {
            **dict(local_values),
            **_procedure_signature_local_values(callee, type_env=(
                procedure_type_envs.get(callee.definition.name, type_env)
                if procedure_type_envs is not None else type_env
            )),
        }
        child_local_types = _procedure_signature_local_type_bindings(callee)
        for arg_expr, (param_name, _) in zip(expr.args, callee.signature.params, strict=True):
            child_locals[param_name] = _resolve_inline_expr_value(arg_expr, local_values=local_values)
        if not _private_workflow_body_exports_step_backed_outputs(
            callee.typed_body.expr,
            return_type_ref=callee.signature.return_type_ref,
            local_values=child_locals,
            local_type_bindings=child_local_types,
            typed_procedures_by_name=typed_procedures_by_name,
            type_env=(
                procedure_type_envs.get(callee.definition.name, type_env)
                if procedure_type_envs is not None
                else type_env
            ),
            procedure_type_envs=procedure_type_envs,
            active_procedures=active_procedures | {callee.definition.name},
            workflow_signatures_by_name=workflow_signatures_by_name,
        ):
            return None
        return _private_workflow_local_value_for_type(
            callee.signature.return_type_ref,
            step_name=binding_name,
            span=expr.span,
            form_path=expr.form_path,
        )
    binding_type = _private_workflow_result_type_for_expr(
        expr,
        local_type_bindings=local_type_bindings,
        typed_procedures_by_name=typed_procedures_by_name,
        type_env=type_env,
        workflow_signatures_by_name=workflow_signatures_by_name,
    )
    if binding_type is None:
        return None
    if isinstance(expr, MatchExpr):
        if _control_binding_terminal_for_match_subject_impl(expr.subject, local_values=local_values) is None:
            return None
        if not _private_workflow_body_exports_step_backed_outputs(
            expr,
            return_type_ref=binding_type,
            local_values=local_values,
            local_type_bindings=local_type_bindings,
            typed_procedures_by_name=typed_procedures_by_name,
            type_env=type_env,
            procedure_type_envs=procedure_type_envs,
            active_procedures=active_procedures,
            workflow_signatures_by_name=workflow_signatures_by_name,
        ):
            return None
    elif isinstance(expr, LetStarExpr):
        if not _private_workflow_body_exports_step_backed_outputs(
            expr,
            return_type_ref=binding_type,
            local_values=local_values,
            local_type_bindings=local_type_bindings,
            typed_procedures_by_name=typed_procedures_by_name,
            type_env=type_env,
            procedure_type_envs=procedure_type_envs,
            active_procedures=active_procedures,
            workflow_signatures_by_name=workflow_signatures_by_name,
        ):
            return None
    elif not isinstance(
        expr,
        (
            CallExpr,
            CommandResultExpr,
            ProviderResultExpr,
            RequestInputExpr,
            AgentExpr,
            RunProviderPhaseExpr,
            ProduceOneOfExpr,
            ResumeOrStartExpr,
            ResourceTransitionExpr,
            FinalizeSelectedItemExpr,
        ),
    ):
        return None
    return _private_workflow_local_value_for_type(
        binding_type,
        step_name=step_name,
        span=expr.span,
        form_path=expr.form_path,
    )


def _private_workflow_local_value_for_type(
    type_ref: TypeRef,
    *,
    step_name: str,
    span: SourceSpan,
    form_path: tuple[str, ...],
) -> Any | None:
    """Build the local-value projection a structured step would expose."""


    if isinstance(type_ref, (RecordTypeRef, UnionTypeRef)):
        output_refs = {
            field.generated_name: f"root.steps.{step_name}.artifacts.{field.generated_name}"
            for field in derive_workflow_boundary_fields(
                type_ref,
                generated_name="return",
                source_path=("return",),
                span=span,
                form_path=form_path,
            )
        }
        local_value = _build_output_step_local_value(output_refs)
        if isinstance(type_ref, UnionTypeRef):
            source = union_prompt_source_from_output_refs(
                type_ref,
                output_refs=output_refs,
            )
            if source is not None:
                local_value["__typed_union_prompt_source__"] = source
        return local_value
    if isinstance(type_ref, (PathTypeRef, PrimitiveTypeRef)):
        return f"root.steps.{step_name}.artifacts.return"
    return None


def _private_workflow_body_exports_step_backed_outputs(
    expr: Any,
    *,
    return_type_ref: TypeRef,
    local_values: Mapping[str, Any],
    local_type_bindings: Mapping[str, TypeRef],
    typed_procedures_by_name: Mapping[str, TypedProcedureDef],
    type_env: FrontendTypeEnvironment,
    procedure_type_envs: Mapping[str, FrontendTypeEnvironment] | None = None,
    active_procedures: frozenset[str],
    workflow_signatures_by_name: Mapping[str, Any] | None = None,
) -> bool:
    """Check that a private workflow body returns step-backed outputs."""


    if is_pure_projection_expr(expr):
        return True
    if isinstance(
        expr,
        (
            CommandResultExpr,
            ProviderResultExpr,
            RequestInputExpr,
            CallExpr,
            AgentExpr,
            RunProviderPhaseExpr,
            ProduceOneOfExpr,
            ResumeOrStartExpr,
            ResourceTransitionExpr,
            FinalizeSelectedItemExpr,
        ),
    ):
        return True
    if isinstance(expr, WithPhaseExpr):
        return _private_workflow_body_exports_step_backed_outputs(
            expr.body,
            return_type_ref=return_type_ref,
            local_values=local_values,
            local_type_bindings=local_type_bindings,
            typed_procedures_by_name=typed_procedures_by_name,
            type_env=type_env,
            procedure_type_envs=procedure_type_envs,
            active_procedures=active_procedures,
            workflow_signatures_by_name=workflow_signatures_by_name,
        )
    if isinstance(expr, ProcedureCallExpr):
        callee_name = expr.callee_name
        bound_proc_ref = local_values.get(callee_name)
        if isinstance(bound_proc_ref, ResolvedProcRefValue):
            callee_name = bound_proc_ref.call_target_name
        callee = typed_procedures_by_name.get(callee_name)
        if callee is None or callee.definition.name in active_procedures:
            return False
        child_locals = {
            **dict(local_values),
            **_procedure_signature_local_values(callee, type_env=(
                procedure_type_envs.get(callee.definition.name, type_env)
                if procedure_type_envs is not None else type_env
            )),
        }
        child_local_types = _procedure_signature_local_type_bindings(callee)
        for arg_expr, (param_name, _) in zip(expr.args, callee.signature.params, strict=True):
            child_locals[param_name] = _resolve_inline_expr_value(arg_expr, local_values=local_values)
        return _private_workflow_body_exports_step_backed_outputs(
            callee.typed_body.expr,
            return_type_ref=callee.signature.return_type_ref,
            local_values=child_locals,
            local_type_bindings=child_local_types,
            typed_procedures_by_name=typed_procedures_by_name,
            type_env=(
                procedure_type_envs.get(callee.definition.name, type_env)
                if procedure_type_envs is not None
                else type_env
            ),
            procedure_type_envs=procedure_type_envs,
            active_procedures=active_procedures | {callee.definition.name},
            workflow_signatures_by_name=workflow_signatures_by_name,
        )
    if isinstance(expr, LetStarExpr):
        child_locals = dict(local_values)
        child_local_types = dict(local_type_bindings)
        for binding_name, binding_expr in expr.bindings:
            binding_value = _private_workflow_binding_local_value(
                binding_expr,
                binding_name=binding_name,
                local_values=child_locals,
                local_type_bindings=child_local_types,
                typed_procedures_by_name=typed_procedures_by_name,
                type_env=type_env,
                procedure_type_envs=procedure_type_envs,
                active_procedures=active_procedures,
                workflow_signatures_by_name=workflow_signatures_by_name,
            )
            if binding_value is None:
                return False
            child_locals[binding_name] = binding_value
            binding_type = _private_workflow_result_type_for_expr(
                binding_expr,
                local_type_bindings=child_local_types,
                typed_procedures_by_name=typed_procedures_by_name,
                type_env=type_env,
                workflow_signatures_by_name=workflow_signatures_by_name,
            )
            if binding_type is not None:
                child_local_types[binding_name] = binding_type
        return _private_workflow_body_exports_step_backed_outputs(
            expr.body,
            return_type_ref=return_type_ref,
            local_values=child_locals,
            local_type_bindings=child_local_types,
            typed_procedures_by_name=typed_procedures_by_name,
            type_env=type_env,
            procedure_type_envs=procedure_type_envs,
            active_procedures=active_procedures,
            workflow_signatures_by_name=workflow_signatures_by_name,
        )
    if isinstance(expr, MatchExpr):
        return _match_outputs_are_step_backed(
            expr,
            return_type_ref=return_type_ref,
            local_values=local_values,
            local_type_bindings=local_type_bindings,
            typed_procedures_by_name=typed_procedures_by_name,
            type_env=type_env,
            procedure_type_envs=procedure_type_envs,
            active_procedures=active_procedures,
            workflow_signatures_by_name=workflow_signatures_by_name,
        )
    if isinstance(expr, IfExpr):
        return _private_workflow_body_exports_step_backed_outputs(
            expr.then_expr,
            return_type_ref=return_type_ref,
            local_values=local_values,
            local_type_bindings=local_type_bindings,
            typed_procedures_by_name=typed_procedures_by_name,
            type_env=type_env,
            procedure_type_envs=procedure_type_envs,
            active_procedures=active_procedures,
            workflow_signatures_by_name=workflow_signatures_by_name,
        ) and _private_workflow_body_exports_step_backed_outputs(
            expr.else_expr,
            return_type_ref=return_type_ref,
            local_values=local_values,
            local_type_bindings=local_type_bindings,
            typed_procedures_by_name=typed_procedures_by_name,
            type_env=type_env,
            procedure_type_envs=procedure_type_envs,
            active_procedures=active_procedures,
            workflow_signatures_by_name=workflow_signatures_by_name,
        )
    if isinstance(expr, (NameExpr, FieldAccessExpr, EnumMemberExpr)):
        return _inline_outputs_are_step_backed(
            expr,
            return_type_ref=return_type_ref,
            local_values=local_values,
        )
    if isinstance(expr, RecordExpr):
        return _record_outputs_are_step_backed(
            expr,
            return_type_ref=return_type_ref,
            local_values=local_values,
        )
    if isinstance(expr, UnionVariantExpr):
        return _union_variant_outputs_are_step_backed(
            expr,
            return_type_ref=return_type_ref,
            local_values=local_values,
            target_dsl_version=type_env.target_dsl_version,
        )
    return False


def _match_outputs_are_step_backed(
    match_expr: MatchExpr,
    *,
    return_type_ref: TypeRef,
    local_values: Mapping[str, Any],
    local_type_bindings: Mapping[str, TypeRef],
    typed_procedures_by_name: Mapping[str, TypedProcedureDef],
    type_env: FrontendTypeEnvironment,
    procedure_type_envs: Mapping[str, FrontendTypeEnvironment] | None = None,
    active_procedures: frozenset[str],
    workflow_signatures_by_name: Mapping[str, Any] | None = None,
) -> bool:
    """Return whether every match arm exports step-backed outputs."""

    binding_terminal = _control_binding_terminal_for_inline_match_impl(
        _resolve_inline_expr_value(match_expr.subject, local_values=local_values)
    )
    if binding_terminal is None:
        return False
    subject_type = _private_workflow_result_type_for_expr(
        match_expr.subject,
        local_type_bindings=local_type_bindings,
        typed_procedures_by_name=typed_procedures_by_name,
        type_env=type_env,
        workflow_signatures_by_name=workflow_signatures_by_name,
    )
    return all(
        _private_workflow_body_exports_step_backed_outputs(
            arm.body,
            return_type_ref=return_type_ref,
            local_values=_control_match_arm_local_values_impl(
                local_values=local_values,
                binding_name=arm.binding_name,
                binding_terminal=binding_terminal,
                binding_type=(
                    type_env.union_variant(
                        subject_type,
                        arm.variant_name,
                        span=match_expr.subject.span,
                        form_path=match_expr.subject.form_path,
                    )
                    if isinstance(subject_type, UnionTypeRef)
                    else None
                ),
            ),
            local_type_bindings=(
                {
                    **dict(local_type_bindings),
                    arm.binding_name: type_env.union_variant(
                        subject_type,
                        arm.variant_name,
                        span=match_expr.subject.span,
                        form_path=match_expr.subject.form_path,
                    ),
                }
                if isinstance(subject_type, UnionTypeRef)
                else local_type_bindings
            ),
            typed_procedures_by_name=typed_procedures_by_name,
            type_env=type_env,
            procedure_type_envs=procedure_type_envs,
            active_procedures=active_procedures,
            workflow_signatures_by_name=workflow_signatures_by_name,
        )
        for arm in match_expr.arms
    )


def _record_outputs_are_step_backed(
    record_expr: RecordExpr,
    *,
    return_type_ref: TypeRef,
    local_values: Mapping[str, Any],
) -> bool:
    """Return whether all record return fields resolve to existing step refs."""


    if not isinstance(return_type_ref, RecordTypeRef):
        return False
    for _, field_path in _flatten_boundary_leaf_paths(return_type_ref, generated_name="return"):
        value = _record_expr_value_at_path(record_expr, field_path)
        source_ref = _render_existing_output_ref(value, local_values=local_values)
        if not isinstance(source_ref, str) or not source_ref.startswith(("root.steps.", "self.steps.", "parent.steps.")):
            return False
    return True


def _union_variant_outputs_are_step_backed(
    union_expr: UnionVariantExpr,
    *,
    return_type_ref: TypeRef,
    local_values: Mapping[str, Any],
    target_dsl_version: str | None,
) -> bool:
    """Return whether one union variant can lower through a private workflow seam."""


    if not isinstance(return_type_ref, UnionTypeRef):
        return False
    active_field_names = {name for name, _ in union_expr.fields}
    for _, raw_field_path in _flatten_boundary_leaf_paths(return_type_ref, generated_name="return"):
        field_path = _normalize_union_field_path(raw_field_path)
        field_name = field_path[0] if field_path else ""
        if field_name != "variant" and field_name not in active_field_names:
            continue
        value = _union_variant_expr_value_at_path(
            union_expr,
            field_path,
            bound_record_fields=target_dsl_supports_generic_unions(target_dsl_version),
        )
        source_ref = _render_existing_output_ref(value, local_values=local_values)
        if source_ref is not None and source_ref.startswith(("root.steps.", "self.steps.", "parent.steps.")):
            continue
        resolved = _resolve_inline_expr_value(value, local_values=local_values)
        if isinstance(resolved, LiteralExpr):
            continue
        return False
    return True


def _inline_outputs_are_step_backed(
    expr: Any,
    *,
    return_type_ref: TypeRef,
    local_values: Mapping[str, Any],
) -> bool:
    """Return whether one inline alias resolves to existing step-backed refs."""


    output_refs = _flatten_inline_output_refs(_resolve_inline_expr_value(expr, local_values=local_values))
    if not output_refs:
        return False
    for output_name, _ in _flatten_boundary_leaf_paths(return_type_ref, generated_name="return"):
        source_ref = output_refs.get(output_name)
        if not isinstance(source_ref, str) or not source_ref.startswith(("root.steps.", "self.steps.", "parent.steps.")):
            return False
    return True


def _substitute_capture_origin_types(
    expr: ExprNode,
    type_bindings: Mapping[str, TypeRef],
) -> ExprNode:
    """Specialize retained creator types without changing their lexical owners."""

    if not type_bindings:
        return expr

    bindings = dict(type_bindings)
    rewritten_by_id: dict[int, ExprNode] = {}

    def origin_type(origin):
        if origin is None:
            return None
        identity, original_type = origin
        substituted = substitute_type_params(original_type, bindings)
        return origin if substituted == original_type else (identity, substituted)

    def rewrite(node: ExprNode) -> ExprNode:
        known = rewritten_by_id.get(id(node))
        if known is not None:
            return known
        # Field bases are leaves for ordinary traversal, but carry retained
        # creator facts just like standalone lexical references.
        children = (node.base,) if isinstance(node, FieldAccessExpr) else iter_child_exprs(node)
        if isinstance(node, LetStarExpr) and node.condition_normalization_input is not None:
            children = (*children, node.condition_normalization_input)
        replacements = {id(child): rewrite(child) for child in children}
        rewritten = (
            _rebuild_with_replacements(node, replacements)
            if any(replacements[id(child)] is not child for child in children)
            else node
        )
        if isinstance(rewritten, NameExpr):
            origin = origin_type(rewritten.capture_origin)
            if origin is not rewritten.capture_origin:
                rewritten = replace(rewritten, capture_origin=origin)
        elif isinstance(rewritten, LetStarExpr):
            sources = tuple(origin_type(source) for source in rewritten.binding_capture_sources)
            if any(new is not old for new, old in zip(sources, rewritten.binding_capture_sources, strict=True)):
                rewritten = replace(rewritten, binding_capture_sources=sources)
        rewritten_by_id[id(node)] = rewritten
        return rewritten

    return rewrite(expr)


def specialize_typed_procedure(
    procedure: TypedProcedureDef,
    *,
    type_bindings: Mapping[str, TypeRef] | None = None,
    workflow_ref_bindings: Mapping[str, ResolvedWorkflowRef] | None = None,
    proc_ref_bindings: Mapping[str, ResolvedProcRefValue] | None = None,
    value_bindings: Mapping[str, Any] | None = None,
    shared_union_field_capabilities: tuple[object, ...] = (),
    remaining_params: tuple[tuple[str, TypeRef], ...],
    workflow_path: Path,
    type_env: FrontendTypeEnvironment,
    typed_procedures_by_name: Mapping[str, TypedProcedureDef],
    procedure_type_envs: Mapping[str, FrontendTypeEnvironment] | None = None,
    specialized_name: str | None = None,
    origin_span=None,
    origin_form_path: tuple[str, ...] | None = None,
    defer_lowering_resolution: bool = False,
    preserve_inherited_bound_params: bool = False,
) -> TypedProcedureDef:
    existing_specialization = getattr(procedure, "specialization", None)
    merged_type_bindings = {
        **dict(getattr(existing_specialization, "type_bindings", {})),
        **dict(type_bindings or {}),
    }
    merged_workflow_ref_bindings = {
        **dict(getattr(existing_specialization, "workflow_ref_bindings", {})),
        **dict(workflow_ref_bindings or {}),
    }
    merged_proc_ref_bindings = {
        **dict(getattr(existing_specialization, "proc_ref_bindings", {})),
        **dict(proc_ref_bindings or {}),
    }
    merged_value_bindings = {
        **dict(getattr(existing_specialization, "value_bindings", {})),
        **dict(value_bindings or {}),
    }
    request = ProcedureSpecializationRequest(
        procedure=procedure,
        type_bindings=merged_type_bindings,
        workflow_ref_bindings=merged_workflow_ref_bindings,
        proc_ref_bindings=merged_proc_ref_bindings,
        value_bindings=merged_value_bindings,
        shared_union_field_capabilities=shared_union_field_capabilities,
        remaining_params=remaining_params,
        workflow_path=workflow_path,
        typed_procedures_by_name=typed_procedures_by_name,
        specialized_name=specialized_name,
        origin_span=origin_span,
        origin_form_path=origin_form_path,
    )
    substituted_signature_params = tuple(
        (
            name,
            substitute_type_params(type_ref, dict(request.type_bindings)),
        )
        for name, type_ref in request.procedure.signature.params
    )
    bound_param_types = {
        name: type_ref
        for name, type_ref in substituted_signature_params
        if (
            name in request.workflow_ref_bindings
            or name in request.proc_ref_bindings
            or name in request.value_bindings
        )
    }
    if preserve_inherited_bound_params or target_dsl_supports_local_hook_inference(type_env.target_dsl_version):
        # A residual-reference specialization retains the static creator facts
        # of its already-bound parent row, whose params no longer list them.
        bound_param_types = {
            **dict(getattr(existing_specialization, "bound_param_types", {})),
            **bound_param_types,
        }
    bound_names = set(bound_param_types)
    if request.specialized_name is None:
        specialized_name = (
            parametric_specialization_name(request.procedure.signature.name, request.type_bindings)
            if request.type_bindings
            else request.procedure.signature.name
        )
        if request.workflow_ref_bindings:
            specialized_name = specialization_name(specialized_name, request.workflow_ref_bindings)
        if request.proc_ref_bindings:
            specialized_name = proc_ref_call_specialization_name(specialized_name, request.proc_ref_bindings)
    else:
        specialized_name = request.specialized_name
    substituted_return_type = substitute_type_params(
        request.procedure.signature.return_type_ref,
        dict(request.type_bindings),
    )
    specialization = ProcedureCallableSpecialization(
        base_name=getattr(existing_specialization, "base_name", request.procedure.signature.name),
        specialization_key=specialized_name,
        type_bindings=request.type_bindings,
        workflow_ref_bindings=request.workflow_ref_bindings,
        proc_ref_bindings=request.proc_ref_bindings,
        value_bindings=request.value_bindings,
        bound_param_types=bound_param_types,
        shared_union_field_capabilities=request.shared_union_field_capabilities,
        specialized_name=specialized_name,
        origin_span=request.origin_span or request.procedure.definition.span,
        origin_form_path=request.origin_form_path or request.procedure.definition.form_path,
    )
    specialized = TypedProcedureDef(
        definition=replace(
            request.procedure.definition,
            name=specialized_name,
            params=tuple(
                ProcedureParam(
                    name=param.name,
                    type_name=render_type_ref(
                        substitute_type_params(
                            next(
                                type_ref
                                for param_name, type_ref in request.procedure.signature.params
                                if param_name == param.name
                            ),
                            dict(request.type_bindings),
                        )
                    ),
                    span=param.span,
                    form_path=param.form_path,
                    expansion_stack=param.expansion_stack,
                    binding_label=param.binding_label,
                )
                for param in request.procedure.definition.params
                if param.name not in bound_names
            ),
            return_spec=replace(
                request.procedure.definition.return_spec,
                type_name=render_type_ref(substituted_return_type),
            ),
            return_type_name=render_type_ref(substituted_return_type),
            type_params=(),
            where_clauses=(),
        ),
        signature=replace(
            request.procedure.signature,
            name=specialized_name,
            params=request.remaining_params,
            return_type_ref=substituted_return_type,
            type_params=(),
            where_clauses=(),
        ),
        typed_body=replace(
            request.procedure.typed_body,
            expr=_substitute_capture_origin_types(
                request.procedure.typed_body.expr, request.type_bindings,
            ),
        ),
        # Deferred objects are compiler-owned re-typecheck targets, not
        # completed specializations. Non-deferred specializations are still
        # consumed on the lowering compatibility path, so preserve their
        # conservative carrier until that path also moves before lowering.
        direct_effect_summary=(
            EMPTY_EFFECT_SUMMARY
            if defer_lowering_resolution
            else request.procedure.direct_effect_summary
        ),
        transitive_effect_summary=(
            EMPTY_EFFECT_SUMMARY
            if defer_lowering_resolution
            else request.procedure.transitive_effect_summary
        ),
        resolved_lowering_mode=ProcedureLoweringMode.INLINE,
        generated_workflow_name=None,
        specialization=specialization,
    )
    if (
        request.procedure.signature.type_params
        and all(
            type_param.name in request.type_bindings
            for type_param in request.procedure.signature.type_params
        )
        and request.procedure.definition.return_spec.guidance is not None
        and request.procedure.definition.return_spec.guidance.example_expr is not None
    ):
        validate_result_guidance_example(
            specialized.definition.return_spec.guidance,
            expected_type=substituted_return_type,
            type_env=type_env,
        )
    mode = ProcedureLoweringMode.INLINE
    generated_name = None
    if not defer_lowering_resolution:
        boundary_valid = _procedure_private_boundary_valid(
            specialized,
            type_env=procedure_type_env_for(
                specialized,
                procedure_type_envs=procedure_type_envs,
                default=type_env,
            ),
        )
        body_valid = _procedure_private_body_valid(
            specialized,
            typed_procedures_by_name=request.typed_procedures_by_name,
            type_env=type_env,
            procedure_type_envs=procedure_type_envs,
        )
        requested = request.procedure.signature.requested_lowering_mode
        if requested == ProcedureLoweringMode.PRIVATE_WORKFLOW:
            if not boundary_valid or not body_valid:
                raise LispFrontendCompileError(
                    (
                        LispFrontendDiagnostic(
                            code="proc_private_workflow_boundary_invalid",
                            message=(
                                f"procedure `{request.procedure.definition.name}` cannot lower as `private-workflow` in Stage 3 "
                                "after specialization because its body would not export step-backed outputs "
                                "through the shared-validation seam"
                            ),
                            span=request.procedure.definition.span,
                            form_path=request.procedure.definition.form_path,
                        ),
                    )
                )
            mode = ProcedureLoweringMode.PRIVATE_WORKFLOW
        elif requested == ProcedureLoweringMode.AUTO and boundary_valid and body_valid:
            mode = ProcedureLoweringMode.PRIVATE_WORKFLOW
        if mode == ProcedureLoweringMode.PRIVATE_WORKFLOW:
            generated_name = f"%{request.workflow_path.stem}.{specialized_name}.v1"
    return replace(
        specialized,
        resolved_lowering_mode=mode,
        generated_workflow_name=generated_name,
    )


def bound_proc_ref_request(
    resolved: ResolvedProcRefValue,
    *,
    typed_procedures_by_name: Mapping[str, TypedProcedureDef],
    procedure_catalog: ProcedureCatalog,
    proc_ref_env: Mapping[str, ResolvedProcRefValue],
    type_env: FrontendTypeEnvironment,
    procedure_type_envs: Mapping[str, FrontendTypeEnvironment] | None = None,
    origin_span=None,
    origin_form_path: tuple[str, ...] | None = None,
    workflow_catalog=None,
    workflow_ref_env=None,
    typed_workflows_by_name=None,
) -> TypedProcedureDef | None:
    if not resolved.bound_args:
        return None
    base_procedure = typed_procedures_by_name.get(resolved.procedure_name)
    if base_procedure is None:
        return None
    proc_ref_bindings: dict[str, ResolvedProcRefValue] = {}
    value_bindings: dict[str, object] = {}
    workflow_ref_bindings = {}
    for binding in resolved.bound_args:
        if isinstance(binding.type_ref, ProcRefTypeRef):
            resolved_binding = resolve_proc_ref_value(
                binding.value_expr,
                procedure_catalog=procedure_catalog,
                proc_ref_env=proc_ref_env,
                expected_type=binding.type_ref,
            )
            if resolved_binding is not None:
                proc_ref_bindings[binding.name] = resolved_binding
            continue
        if isinstance(binding.type_ref, WorkflowRefTypeRef):
            expression = binding.value_expr
            if isinstance(expression, NameExpr) and expression.name in (workflow_ref_env or {}):
                reference = workflow_ref_env[expression.name]
                if reference is None:
                    return None
            else:
                reference = resolve_workflow_ref_expr(expression, workflow_catalog=workflow_catalog,
                    span=expression.span, form_path=expression.form_path,
                    expansion_stack=expression.expansion_stack, expected_type=binding.type_ref,
                    typed_workflows_by_name=typed_workflows_by_name, allow_extern_rebinding=True)
            workflow_ref_bindings[binding.name] = reference
            continue
        value_bindings[binding.name] = binding.value_expr
    return specialize_typed_procedure(
        base_procedure,
        proc_ref_bindings=proc_ref_bindings,
        workflow_ref_bindings=workflow_ref_bindings,
        value_bindings=value_bindings,
        remaining_params=resolved.residual_params,
        workflow_path=Path(base_procedure.definition.span.start.path),
        type_env=procedure_type_env_for(
            base_procedure,
            procedure_type_envs=procedure_type_envs,
            default=type_env,
        ),
        typed_procedures_by_name=typed_procedures_by_name,
        procedure_type_envs=procedure_type_envs,
        specialized_name=resolved.call_target_name,
        origin_span=origin_span,
        origin_form_path=origin_form_path,
        # Discovery products are inserted into the compiler's procedure-target
        # fixed point and authoritatively re-typechecked before lowering.  Do
        # not validate private-workflow eligibility or retain stale effects on
        # this provisional object.
        defer_lowering_resolution=True,
    )


def discover_proc_ref_specializations(
    *,
    typed_procedures: tuple[TypedProcedureDef, ...],
    typed_workflows: tuple[TypedWorkflowDef, ...],
    procedure_catalog: ProcedureCatalog,
    type_env: FrontendTypeEnvironment,
    visible_typed_procedures_by_name: Mapping[str, TypedProcedureDef] | None = None,
    procedure_type_envs: Mapping[str, FrontendTypeEnvironment] | None = None,
    workflow_catalog=None,
) -> tuple[TypedProcedureDef, ...]:
    from .expressions import LetStarExpr, ProcedureCallExpr

    discovered: dict[str, TypedProcedureDef] = {}
    typed_procedures_by_name = {
        **dict(visible_typed_procedures_by_name or {}),
        **{procedure.definition.name: procedure for procedure in typed_procedures},
    }

    def record_specialization(
        specialized: TypedProcedureDef | None,
    ) -> None:
        if specialized is None:
            return
        if specialized.definition.name in typed_procedures_by_name:
            return
        discovered.setdefault(specialized.definition.name, specialized)

    def walk(node: object, proc_ref_env: Mapping[str, ResolvedProcRefValue], workflow_ref_env) -> None:
        if isinstance(node, ProcedureCallExpr):
            bound_proc_ref = proc_ref_env.get(node.callee_name)
            if bound_proc_ref is not None:
                record_specialization(
                    bound_proc_ref_request(
                        bound_proc_ref,
                        typed_procedures_by_name=typed_procedures_by_name,
                        procedure_catalog=procedure_catalog,
                        proc_ref_env=proc_ref_env,
                        type_env=type_env,
                        procedure_type_envs=procedure_type_envs,
                        origin_span=node.span,
                        origin_form_path=node.form_path,
                        workflow_catalog=workflow_catalog,
                        workflow_ref_env=workflow_ref_env,
                        typed_workflows_by_name={row.definition.name: row for row in typed_workflows},
                    )
                )
            if bound_proc_ref is None or target_dsl_supports_local_hook_inference(type_env.target_dsl_version):
                # A bound consumer can still receive reference-valued residual
                # arguments. Its static row is discovered above; once settled,
                # use that same ordinary specialization path for the actuals.
                callee_name = (bound_proc_ref.call_target_name
                               if bound_proc_ref is not None else node.callee_name)
                signature = procedure_catalog.signatures_by_name.get(callee_name)
                if signature is not None:
                    if len(node.args) != len(signature.params):
                        for arg in node.args:
                            walk(arg, proc_ref_env, workflow_ref_env)
                        return
                    proc_ref_bindings: dict[str, ResolvedProcRefValue] = {}
                    for arg_expr, (param_name, param_type) in zip(node.args, signature.params, strict=True):
                        if not isinstance(param_type, ProcRefTypeRef):
                            continue
                        resolved_binding = resolve_proc_ref_value(
                            arg_expr,
                            procedure_catalog=procedure_catalog,
                            proc_ref_env=proc_ref_env,
                            expected_type=param_type,
                        )
                        if resolved_binding is not None:
                            proc_ref_bindings[param_name] = resolved_binding
                    if proc_ref_bindings:
                        base_procedure = typed_procedures_by_name.get(callee_name)
                        if base_procedure is not None:
                            record_specialization(
                                specialize_typed_procedure(
                                    base_procedure,
                                    proc_ref_bindings=proc_ref_bindings,
                                    remaining_params=tuple(
                                        (param_name, param_type)
                                        for param_name, param_type in signature.params
                                        if param_name not in proc_ref_bindings
                                    ),
                                    workflow_path=Path(base_procedure.definition.span.start.path),
                                    type_env=procedure_type_env_for(
                                        base_procedure,
                                        procedure_type_envs=procedure_type_envs,
                                        default=type_env,
                                    ),
                                    typed_procedures_by_name=typed_procedures_by_name,
                                    procedure_type_envs=procedure_type_envs,
                                    specialized_name=proc_ref_call_specialization_name(
                                        signature.name,
                                        proc_ref_bindings,
                                    ),
                                    origin_span=node.span,
                                    origin_form_path=node.form_path,
                                    # The compiler records this discovery
                                    # product, continues the fixed point, and
                                    # re-typechecks it before lowering.
                                    defer_lowering_resolution=True,
                                    preserve_inherited_bound_params=(bound_proc_ref is not None
                                        and target_dsl_supports_local_hook_inference(type_env.target_dsl_version)),
                                )
                            )
            for arg in node.args:
                walk(arg, proc_ref_env, workflow_ref_env)
            return
        if isinstance(node, LetStarExpr):
            child_env = dict(proc_ref_env)
            child_workflow_env = dict(workflow_ref_env)
            for binding_name, binding_expr in node.bindings:
                walk(binding_expr, child_env, child_workflow_env)
                resolved_binding = resolve_proc_ref_value(
                    binding_expr,
                    procedure_catalog=procedure_catalog,
                    proc_ref_env=child_env,
                )
                if resolved_binding is not None:
                    child_env[binding_name] = resolved_binding
                if isinstance(binding_expr, NameExpr) and binding_expr.name in child_workflow_env:
                    child_workflow_env[binding_name] = child_workflow_env[binding_expr.name]
                elif isinstance(binding_expr, WorkflowRefLiteralExpr):
                    child_workflow_env[binding_name] = resolve_workflow_ref_expr(binding_expr,
                        workflow_catalog=workflow_catalog, span=binding_expr.span,
                        form_path=binding_expr.form_path, expansion_stack=binding_expr.expansion_stack,
                        typed_workflows_by_name={row.definition.name: row for row in typed_workflows},
                        allow_extern_rebinding=True)
            walk(node.body, child_env, child_workflow_env)
            return
        for child in iter_child_exprs(node):
            walk(child, proc_ref_env, workflow_ref_env)

    for procedure in typed_procedures:
        proc_ref_env = dict(getattr(procedure.specialization, "proc_ref_bindings", {}))
        workflow_ref_env = {formal: None for formal, ref in procedure.signature.params
            if isinstance(ref, WorkflowRefTypeRef)}
        workflow_ref_env.update(getattr(procedure.specialization, "workflow_ref_bindings", {}))
        walk(procedure.typed_body.expr, proc_ref_env, workflow_ref_env)
    for workflow in typed_workflows:
        walk(workflow.typed_body.expr, {}, {})
    return tuple(discovered.values())


def _same_specialization_bindings(
    left: TypedProcedureDef,
    right: TypedProcedureDef,
) -> bool:
    """Compare every compile-time binding carried by two specialization rows."""

    left_specialization = left.specialization
    right_specialization = right.specialization
    if left_specialization is None or right_specialization is None:
        return left_specialization is right_specialization
    return (
        left_specialization.base_name == right_specialization.base_name
        and dict(left_specialization.type_bindings)
        == dict(right_specialization.type_bindings)
        and workflow_ref_binding_identity(left_specialization.workflow_ref_bindings)
        == workflow_ref_binding_identity(right_specialization.workflow_ref_bindings)
        and tuple(
            sorted(
                (param_name, resolved.call_target_name)
                for param_name, resolved in left_specialization.proc_ref_bindings.items()
            )
        )
        == tuple(
            sorted(
                (param_name, resolved.call_target_name)
                for param_name, resolved in right_specialization.proc_ref_bindings.items()
            )
        )
        and dict(left_specialization.value_bindings)
        == dict(right_specialization.value_bindings)
    )


def discover_workflow_ref_specializations(
    *,
    typed_procedures: tuple[TypedProcedureDef, ...],
    typed_workflows: tuple[TypedWorkflowDef, ...],
    procedure_catalog: ProcedureCatalog,
    workflow_catalog: object,
    type_env: FrontendTypeEnvironment,
    visible_typed_procedures_by_name: Mapping[str, TypedProcedureDef] | None = None,
    procedure_type_envs: Mapping[str, FrontendTypeEnvironment] | None = None,
) -> tuple[TypedProcedureDef, ...]:
    """Discover concrete WorkflowRef procedure calls for the Stage-3 fixed point."""

    from .expressions import LetStarExpr, ProcedureCallExpr

    candidates_by_legacy_name: dict[str, list[TypedProcedureDef]] = {}
    typed_procedures_by_name = {
        **dict(visible_typed_procedures_by_name or {}),
        **{
            procedure.definition.name: procedure
            for procedure in typed_procedures
        },
    }

    def record_specialization(specialized: TypedProcedureDef | None) -> None:
        if specialized is None:
            return
        candidates = candidates_by_legacy_name.setdefault(
            specialized.definition.name,
            [],
        )
        if any(
            _same_specialization_bindings(candidate, specialized)
            for candidate in candidates
        ):
            return
        candidates.append(specialized)

    def resolve_binding(
        arg_expr: object,
        *,
        expected_type: WorkflowRefTypeRef,
        workflow_ref_env: Mapping[str, ResolvedWorkflowRef],
    ) -> ResolvedWorkflowRef | None:
        if isinstance(arg_expr, NameExpr) and arg_expr.name in workflow_ref_env:
            return workflow_ref_env[arg_expr.name]
        if not isinstance(arg_expr, (WorkflowRefLiteralExpr, NameExpr, EnumMemberExpr)):
            return None
        return resolve_workflow_ref_expr(
            arg_expr,
            workflow_catalog=workflow_catalog,
            span=arg_expr.span,
            form_path=arg_expr.form_path,
            expansion_stack=arg_expr.expansion_stack,
            expected_type=expected_type,
            typed_workflows_by_name={
                workflow.definition.name: workflow for workflow in typed_workflows
            },
            allow_extern_rebinding=True,
        )

    def walk(
        node: object,
        workflow_ref_env: Mapping[str, ResolvedWorkflowRef],
        proc_ref_env: Mapping[str, ResolvedProcRefValue],
    ) -> None:
        if isinstance(node, ProcedureCallExpr):
            bound_proc_ref = proc_ref_env.get(node.callee_name)
            callee_name = (
                bound_proc_ref.call_target_name
                if bound_proc_ref is not None
                else node.callee_name
            )
            procedure = typed_procedures_by_name.get(callee_name)
            signature = (
                procedure.signature
                if procedure is not None
                else procedure_catalog.signatures_by_name.get(callee_name)
            )
            if procedure is not None and signature is not None and len(node.args) == len(signature.params):
                workflow_ref_bindings: dict[str, ResolvedWorkflowRef] = {}
                proc_ref_bindings: dict[str, ResolvedProcRefValue] = {}
                remaining_params: list[tuple[str, TypeRef]] = []
                for arg_expr, (param_name, param_type) in zip(
                    node.args,
                    signature.params,
                    strict=True,
                ):
                    if isinstance(param_type, WorkflowRefTypeRef):
                        resolved = resolve_binding(
                            arg_expr,
                            expected_type=param_type,
                            workflow_ref_env=workflow_ref_env,
                        )
                        if resolved is not None:
                            workflow_ref_bindings[param_name] = resolved
                            continue
                    if isinstance(param_type, ProcRefTypeRef):
                        resolved_proc_ref = resolve_proc_ref_value(
                            arg_expr,
                            procedure_catalog=procedure_catalog,
                            proc_ref_env=proc_ref_env,
                            expected_type=param_type,
                        )
                        if resolved_proc_ref is not None:
                            proc_ref_bindings[param_name] = resolved_proc_ref
                            continue
                    remaining_params.append((param_name, param_type))
                if workflow_ref_bindings:
                    record_specialization(
                        specialize_typed_procedure(
                            procedure,
                            workflow_ref_bindings=workflow_ref_bindings,
                            proc_ref_bindings=proc_ref_bindings,
                            remaining_params=tuple(remaining_params),
                            workflow_path=Path(procedure.definition.span.start.path),
                            type_env=procedure_type_env_for(
                                procedure,
                                procedure_type_envs=procedure_type_envs,
                                default=type_env,
                            ),
                            typed_procedures_by_name=typed_procedures_by_name,
                            procedure_type_envs=procedure_type_envs,
                            origin_span=node.span,
                            origin_form_path=node.form_path,
                            defer_lowering_resolution=True,
                        )
                    )
            for arg in node.args:
                walk(arg, workflow_ref_env, proc_ref_env)
            return
        if isinstance(node, LetStarExpr):
            child_workflow_env = dict(workflow_ref_env)
            for binding_name, binding_expr in node.bindings:
                walk(binding_expr, child_workflow_env, proc_ref_env)
                if isinstance(binding_expr, NameExpr) and binding_expr.name in child_workflow_env:
                    child_workflow_env[binding_name] = child_workflow_env[binding_expr.name]
                    continue
                if isinstance(
                    binding_expr,
                    (WorkflowRefLiteralExpr, NameExpr, EnumMemberExpr),
                ):
                    try:
                        resolved = resolve_workflow_ref_expr(
                            binding_expr,
                            workflow_catalog=workflow_catalog,
                            span=binding_expr.span,
                            form_path=binding_expr.form_path,
                            expansion_stack=binding_expr.expansion_stack,
                            typed_workflows_by_name={
                                workflow.definition.name: workflow
                                for workflow in typed_workflows
                            },
                            allow_extern_rebinding=True,
                        )
                    except LispFrontendCompileError:
                        resolved = None
                    if resolved is not None:
                        child_workflow_env[binding_name] = resolved
            walk(node.body, child_workflow_env, proc_ref_env)
            return
        for child in iter_child_exprs(node):
            walk(child, workflow_ref_env, proc_ref_env)

    for procedure in typed_procedures:
        specialization = procedure.specialization
        walk(
            procedure.typed_body.expr,
            {**{formal: None for formal, ref in procedure.signature.params
                if isinstance(ref, WorkflowRefTypeRef)},
                **dict(getattr(specialization, "workflow_ref_bindings", {}))},
            dict(getattr(specialization, "proc_ref_bindings", {})),
        )
    for workflow in typed_workflows:
        walk(workflow.typed_body.expr, {}, {})

    discovered: dict[str, tuple[tuple[tuple[str, str], ...], TypedProcedureDef]] = {}
    for legacy_name, candidates in candidates_by_legacy_name.items():
        existing_legacy_row = typed_procedures_by_name.get(legacy_name)
        collision_group = len(candidates) > 1 or (
            existing_legacy_row is not None
            and not any(
                _same_specialization_bindings(existing_legacy_row, candidate)
                for candidate in candidates
            )
        )
        for candidate in candidates:
            if any(
                _same_specialization_bindings(existing, candidate)
                for existing in typed_procedures_by_name.values()
            ):
                # Fixed-point rediscovery reuses the exact compiler row even
                # when a later candidate turns its legacy key into a group.
                continue
            identity = workflow_ref_binding_identity(
                candidate.specialization.workflow_ref_bindings
            )
            final_name = (
                collision_specialization_name(
                    legacy_name,
                    candidate.specialization.workflow_ref_bindings,
                )
                if collision_group
                else legacy_name
            )
            if final_name != candidate.definition.name:
                candidate = replace(
                    candidate,
                    definition=replace(candidate.definition, name=final_name),
                    signature=replace(candidate.signature, name=final_name),
                    specialization=replace(
                        candidate.specialization,
                        specialized_name=final_name,
                        specialization_key=final_name,
                    ),
                )

            existing = typed_procedures_by_name.get(final_name)
            if existing is not None:
                if not _same_specialization_bindings(existing, candidate):
                    raise LispFrontendCompileError(
                        (
                            LispFrontendDiagnostic(
                                code="procedure_specialization_key_collision",
                                message=(
                                    "procedure specialization key "
                                    f"`{final_name}` has conflicting WorkflowRef bindings"
                                ),
                                span=candidate.definition.span,
                                form_path=candidate.definition.form_path,
                            ),
                        )
                    )
                continue

            prior = discovered.get(final_name)
            if prior is not None and not _same_specialization_bindings(
                prior[1],
                candidate,
            ):
                raise LispFrontendCompileError(
                    (
                        LispFrontendDiagnostic(
                            code="procedure_specialization_key_collision",
                            message=(
                                "procedure specialization key "
                                f"`{final_name}` has conflicting WorkflowRef bindings"
                            ),
                            span=candidate.definition.span,
                            form_path=candidate.definition.form_path,
                        ),
                    )
                )
            discovered[final_name] = (identity, candidate)
    return tuple(candidate for _, candidate in discovered.values())


_PROVIDER_BUNDLE_PATH_REF_KEY = "__provider_bundle_path_ref__"


_PROVIDER_BUNDLE_PROJECTION_KEY = "__provider_bundle_projection__"


@dataclass(frozen=True)
class ProjectedPathRef:
    """Inline lowered ref plus projection metadata for public output provenance."""

    ref: str
    projection: Mapping[str, Any]


def _projected_provider_bundle_ref(value: Any) -> ProjectedPathRef | None:
    if not isinstance(value, Mapping):
        return None
    path_ref = value.get(_PROVIDER_BUNDLE_PATH_REF_KEY)
    projection = value.get(_PROVIDER_BUNDLE_PROJECTION_KEY)
    if not isinstance(path_ref, str) or not isinstance(projection, Mapping):
        return None
    return ProjectedPathRef(ref=path_ref, projection=dict(projection))


def _value_compile_error(*, code: str, message: str, span, form_path: tuple[str, ...]) -> LispFrontendCompileError:
    return LispFrontendCompileError(
        (
            LispFrontendDiagnostic(
                code=code,
                message=message,
                span=span,
                form_path=form_path,
                phase="lowering",
            ),
        )
    )


def _build_record_local_value(type_ref: RecordTypeRef, *, generated_name: str, type_env: Any | None = None) -> dict[str, Any]:
    """Represent a record parameter as nested refs to flattened inputs."""

    local_value: dict[str, Any] = {}
    for field in type_ref.definition.fields:
        field_type = type_ref.field_types[field.name]
        leaf_name = f"{generated_name}__{field.name}"
        if isinstance(field_type, RecordTypeRef):
            local_value[field.name] = _build_record_local_value(
                field_type,
                generated_name=leaf_name,
                type_env=type_env,
            )
        elif isinstance(field_type, UnionTypeRef):
            local_value[field.name] = _build_union_local_value(
                field_type,
                generated_name=leaf_name,
                type_env=type_env,
            )
        else:
            local_value[field.name] = f"inputs.{leaf_name}"
    return local_value


def _build_union_local_value(type_ref: UnionTypeRef, *, generated_name: str, type_env: Any | None = None) -> dict[str, Any]:
    """Represent a union parameter as nested refs to flattened inputs."""

    local_value: dict[str, Any] = {}
    for leaf_name, field_path in _flatten_boundary_leaf_paths(type_ref, generated_name=generated_name, type_env=type_env):
        _assign_nested_local_value(local_value, field_path, f"inputs.{leaf_name}")
    return local_value


def union_prompt_source_from_output_refs(
    type_ref: UnionTypeRef,
    *,
    output_refs: Mapping[str, str],
) -> dict[str, Any] | None:
    """Preserve branch-specific terminal refs before local-value nesting."""

    def field_source(field_type: TypeRef, prefix: str) -> dict[str, Any] | None:
        if isinstance(field_type, RecordTypeRef):
            fields: dict[str, Any] = {}
            for name, nested_type in field_type.field_types.items():
                child = field_source(nested_type, f"{prefix}__{name}")
                if child is None:
                    return None
                fields[name] = child
            return {"kind": "record", "fields": fields}
        ref = output_refs.get(prefix) or output_refs.get(prefix.removeprefix("return__"))
        return (
            {"kind": "reference", "reference": ref}
            if isinstance(ref, str)
            else None
        )

    discriminant = output_refs.get("return__variant") or output_refs.get("variant")
    if not isinstance(discriminant, str):
        return None
    variants: dict[str, Any] = {}
    for variant_name, fields in type_ref.variant_field_types.items():
        variant_sources: dict[str, Any] = {}
        for field_name, field_type in fields.items():
            source = field_source(field_type, f"return__{field_name}")
            if source is None:
                return None
            variant_sources[field_name] = source
        variants[variant_name] = variant_sources
    return {
        "kind": "union",
        "discriminant": {"kind": "reference", "reference": discriminant},
        "variants": variants,
    }


def _build_nested_record_step_local_value(
    type_ref: RecordTypeRef,
    *,
    step_name: str,
    artifact_prefix: tuple[str, ...],
) -> dict[str, Any]:
    """Represent a nested record result from step artifact refs."""

    local_value: dict[str, Any] = {}
    for field in type_ref.definition.fields:
        field_type = type_ref.field_types[field.name]
        next_prefix = artifact_prefix + (field.name,)
        if isinstance(field_type, RecordTypeRef):
            local_value[field.name] = _build_nested_record_step_local_value(
                field_type,
                step_name=step_name,
                artifact_prefix=next_prefix,
            )
            continue
        local_value[field.name] = f"root.steps.{step_name}.artifacts.{'__'.join(next_prefix)}"
    return local_value


def _build_record_step_local_value(type_ref: RecordTypeRef, *, step_name: str) -> dict[str, Any]:
    """Represent a record result as nested refs to one step's artifacts."""

    local_value: dict[str, Any] = {}
    for field in type_ref.definition.fields:
        field_type = type_ref.field_types[field.name]
        artifact_name = field.name
        if isinstance(field_type, RecordTypeRef):
            local_value[field.name] = _build_nested_record_step_local_value(
                field_type,
                step_name=step_name,
                artifact_prefix=(artifact_name,),
            )
            continue
        local_value[field.name] = f"root.steps.{step_name}.artifacts.{artifact_name}"
    return local_value


def _procedure_signature_local_values(procedure: TypedProcedureDef, *, type_env: Any | None = None) -> dict[str, Any]:
    """Seed local value refs from a private workflow procedure signature."""

    local_values: dict[str, Any] = {}
    for param_name, param_type in procedure.signature.params:
        if isinstance(param_type, RecordTypeRef):
            local_values[param_name] = _build_record_local_value(
                param_type,
                generated_name=param_name,
                type_env=type_env,
            )
            continue
        if isinstance(param_type, UnionTypeRef):
            local_values[param_name] = _build_union_local_value(
                param_type,
                generated_name=param_name,
                type_env=type_env,
            )
            continue
        local_values[param_name] = f"inputs.{param_name}"
    if procedure.specialization is not None:
        local_values.update(dict(getattr(procedure.specialization, "workflow_ref_bindings", {})))
        local_values.update(dict(getattr(procedure.specialization, "proc_ref_bindings", {})))
        local_values.update(dict(getattr(procedure.specialization, "value_bindings", {})))
    return local_values


def _signature_local_values(typed_workflow: Any, *, type_env: Any | None = None) -> dict[str, Any]:
    """Seed local value refs from a workflow signature."""

    signature = typed_workflow.signature
    local_values: dict[str, Any] = {}
    for param_name, param_type in signature.params:
        if isinstance(param_type, RecordTypeRef):
            local_values[param_name] = _build_record_local_value(param_type, generated_name=param_name, type_env=type_env)
        elif isinstance(param_type, UnionTypeRef):
            local_values[param_name] = _build_union_local_value(param_type, generated_name=param_name, type_env=type_env)
        else:
            local_values[param_name] = f"inputs.{param_name}"
    specialization = getattr(typed_workflow, "specialization", None)
    if specialization is not None:
        local_values.update(dict(getattr(specialization, "workflow_ref_bindings", {})))
        local_values.update(dict(getattr(specialization, "proc_ref_bindings", {})))
        local_values.update(dict(getattr(specialization, "value_bindings", {})))
    return local_values


def _resolve_nested_local_value(value: Any, field_path: tuple[str, ...]) -> Any:
    """Follow a flattened field path through a nested local-value mapping."""

    current = value
    for field_name in field_path:
        if not isinstance(current, Mapping):
            return None
        current = current.get(field_name)
    return current


def _resolve_expr_local_value(expr: Any, *, local_values: Mapping[str, Any]) -> Any:
    """Resolve simple name, field, and phase-target expressions from locals."""

    if isinstance(expr, NameExpr):
        return local_values.get(expr.name)
    if isinstance(expr, FieldAccessExpr):
        base_value = _resolve_expr_local_value(expr.base, local_values=local_values)
        return _resolve_nested_local_value(base_value, tuple(expr.fields))
    if isinstance(expr, PhaseTargetExpr):
        return None
    return None


def _record_field_value(record_expr: RecordExpr, field_name: str) -> Any:
    for current_name, current_value in record_expr.fields:
        if current_name == field_name:
            return current_value
    return None


def _resolve_inline_field_value(
    value: Any,
    *,
    field_path: tuple[str, ...],
    local_values: Mapping[str, Any],
    retain_expression_facts: bool = False,
) -> Any:
    """Resolve a nested field path through inline mappings or record expressions."""


    current = value
    for field_name in field_path:
        if isinstance(current, RetainedExpressionFact):
            current = current.tag if current.form == "union" and field_name == "variant" else dict(current.fields).get(field_name)
            continue
        if current is not None and not isinstance(current, (Mapping, RecordExpr, UnionVariantExpr)):
            next_current = _resolve_inline_expr_value(current, local_values=local_values, retain_expression_facts=retain_expression_facts)
            if next_current is current:
                return None
            current = next_current
        if isinstance(current, Mapping):
            current = current.get(field_name)
            continue
        if isinstance(current, RecordExpr):
            current = _record_field_value(current, field_name)
            current = _resolve_inline_expr_value(current, local_values=local_values, retain_expression_facts=retain_expression_facts)
            continue
        if isinstance(current, UnionVariantExpr):
            current = _union_variant_expr_value_at_path(current, (field_name,), bound_record_fields=False)
            current = _resolve_inline_expr_value(current, local_values=local_values, retain_expression_facts=retain_expression_facts)
            continue
        return None
    return current


def _retained_inline_child(value):
    from orchestrator.workflow_lisp.expressions import ExprNode
    from orchestrator.workflow_lisp.expression_traversal import is_pure_projection_expr

    if isinstance(value, ExprNode) and not isinstance(value, LiteralExpr):
        return RetainedExpressionFact("opaque", is_pure_projection_expr(value))
    return value


def _retained_inline_constructor(expr, *, local_values):
    from orchestrator.workflow_lisp.expression_traversal import is_pure_projection_expr

    fields = tuple((name, _retained_inline_child(_resolve_inline_expr_value(child,
        local_values=local_values, retain_expression_facts=True))) for name, child in expr.fields)
    tag = _union_variant_expr_value_at_path(expr, ("variant",), bound_record_fields=False)
    return RetainedExpressionFact("union", is_pure_projection_expr(expr), fields, tag)


def _resolve_inline_record(expr, *, local_values, retain_expression_facts):
    from orchestrator.workflow_lisp.expression_traversal import is_pure_projection_expr

    fields = []
    for name, child in expr.fields:
        value = _resolve_inline_expr_value(child, local_values=local_values,
            retain_expression_facts=retain_expression_facts)
        if value is None and not retain_expression_facts:
            return expr
        fields.append((name, _retained_inline_child(value) if retain_expression_facts else value))
    if any(value is None for _, value in fields):
        return RetainedExpressionFact("record", is_pure_projection_expr(expr), tuple(fields))
    return dict(fields)


def _resolve_inline_expr_value(expr: Any, *, local_values: Mapping[str, Any], retain_expression_facts: bool = False) -> Any:
    """Resolve literals, names, fields, and record expressions for inline use."""

    if isinstance(expr, RetainedExpressionFact):
        return expr
    if retain_expression_facts and isinstance(expr, UnionVariantExpr):
        return _retained_inline_constructor(expr, local_values=local_values)


    if isinstance(expr, LiteralExpr | GeneratedRelpathSeedExpr | WorkflowRefLiteralExpr):
        return expr
    if isinstance(expr, EnumMemberExpr):
        return LiteralExpr(
            value=expr.member_name,
            literal_kind="string",
            span=expr.span,
            form_path=expr.form_path,
            expansion_stack=expr.expansion_stack,
        )
    if isinstance(expr, ProcRefLiteralExpr | BindProcExpr):
        return expr
    if isinstance(expr, RecordExpr):
        return _resolve_inline_record(expr, local_values=local_values,
            retain_expression_facts=retain_expression_facts)
    if isinstance(expr, LoopStateSeedExpr):
        return _loop_state_seed_inline_value(expr, local_values=local_values, retain_expression_facts=retain_expression_facts)
    if isinstance(expr, LoopStateUpdateExpr):
        return _loop_state_update_inline_value(expr, local_values=local_values, retain_expression_facts=retain_expression_facts)
    if isinstance(expr, LetStarExpr):
        child_locals = _resolve_inline_let_bindings(expr.bindings, local_values=local_values, retain_expression_facts=retain_expression_facts)
        if child_locals is None:
            return expr
        return _resolve_inline_expr_value(expr.body, local_values=child_locals, retain_expression_facts=retain_expression_facts)
    if isinstance(expr, IfExpr):
        condition_value = _resolve_inline_expr_value(expr.condition_expr, local_values=local_values, retain_expression_facts=retain_expression_facts)
        if isinstance(condition_value, LiteralExpr) and condition_value.literal_kind == "bool":
            branch = expr.then_expr if condition_value.value else expr.else_expr
            return _resolve_inline_expr_value(branch, local_values=local_values, retain_expression_facts=retain_expression_facts)
        return expr
    if isinstance(expr, ProviderBundlePathExpr):
        source_value = _resolve_inline_expr_value(expr.source_expr, local_values=local_values, retain_expression_facts=retain_expression_facts)
        projected = _projected_provider_bundle_ref(source_value)
        if projected is None:
            return expr
        return projected
    resolved = _resolve_expr_local_value(expr, local_values=local_values)
    if retain_expression_facts and isinstance(resolved, (RecordExpr, UnionVariantExpr)):
        return _resolve_inline_expr_value(resolved, local_values=local_values, retain_expression_facts=True)
    if isinstance(resolved, (str, Mapping, LiteralExpr, RecordExpr, ProjectedPathRef)):
        return resolved
    if resolved is not None:
        if resolved is expr:
            return expr
        return _resolve_inline_expr_value(resolved, local_values=local_values, retain_expression_facts=retain_expression_facts)
    if isinstance(expr, NameExpr):
        bound = local_values.get(expr.name)
        if bound is None:
            return None
        if isinstance(bound, (str, Mapping)):
            return bound
        if bound is expr:
            return expr
        return _resolve_inline_expr_value(bound, local_values=local_values, retain_expression_facts=retain_expression_facts)
    if isinstance(expr, FieldAccessExpr):
        return _resolve_inline_field_value(
            local_values.get(expr.base.name),
            field_path=tuple(expr.fields),
            local_values=local_values, retain_expression_facts=retain_expression_facts,
        )
    return expr


def _resolve_inline_let_bindings(
    bindings: tuple[tuple[str, Any], ...], *, local_values: Mapping[str, Any],
    retain_expression_facts: bool = False,
) -> dict[str, Any] | None:
    """Resolve a suffix's aliases in order, without constructing another AST."""
    child_locals = dict(local_values)
    for name, expr in bindings:
        value = _resolve_inline_expr_value(expr, local_values=child_locals, retain_expression_facts=retain_expression_facts)
        if value is None:
            return None
        child_locals[name] = value
    return child_locals


def _loop_state_seed_inline_value(
    expr: LoopStateSeedExpr,
    *,
    local_values: Mapping[str, Any],
    retain_expression_facts: bool = False,
) -> Any:
    inline_value: dict[str, Any] = {}
    for field in expr.fields:
        resolved_value = _resolve_inline_expr_value(field.value_expr, local_values=local_values, retain_expression_facts=retain_expression_facts)
        if resolved_value is None:
            return expr
        inline_value[field.name] = resolved_value
    return inline_value


def _loop_state_update_inline_value(
    expr: LoopStateUpdateExpr,
    *,
    local_values: Mapping[str, Any],
    retain_expression_facts: bool = False,
) -> Any:
    base_value = _resolve_inline_expr_value(expr.base_expr, local_values=local_values, retain_expression_facts=retain_expression_facts)
    if not isinstance(base_value, Mapping):
        return expr
    updated_value = {name: _clone_inline_value(value) for name, value in base_value.items()}
    for field_name, field_expr in expr.overrides:
        resolved_value = _resolve_inline_expr_value(field_expr, local_values=local_values, retain_expression_facts=retain_expression_facts)
        if resolved_value is None:
            return expr
        updated_value[field_name] = resolved_value
    return updated_value


def _clone_inline_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            key: _clone_inline_value(item)
            for key, item in value.items()
        }
    return value


def _build_output_step_local_value(
    output_refs: Mapping[str, str],
    *,
    type_ref: RecordTypeRef | UnionTypeRef | None = None,
    type_env: Any | None = None,
) -> dict[str, Any]:
    """Convert flattened terminal output refs into nested local-value shape."""

    field_paths = (
        dict(
            _flatten_boundary_leaf_paths(
                type_ref,
                generated_name="return",
                type_env=type_env,
            )
        )
        if type_ref is not None
        else {}
    )
    local_value: dict[str, Any] = {}
    for output_name, ref in output_refs.items():
        field_path = field_paths.get(
            output_name,
            tuple(output_name.removeprefix("return__").split("__")),
        )
        current = local_value
        for field_name in field_path[:-1]:
            next_current = current.get(field_name)
            if not isinstance(next_current, dict):
                next_current = {}
                current[field_name] = next_current
            current = next_current
        current[field_path[-1]] = ref
    return local_value


def _flatten_inline_output_refs(local_value: Any) -> dict[str, str]:
    """Flatten nested local-value mappings back into generated output refs."""

    if not isinstance(local_value, Mapping):
        return {}
    output_refs: dict[str, str] = {}

    def visit(value: Any, *, path: tuple[str, ...]) -> None:
        if isinstance(value, Mapping):
            for key, item in value.items():
                if key in {
                    "__lowering_returned_union_type",
                    "__typed_union_prompt_source__",
                }:
                    continue
                if isinstance(key, str):
                    visit(item, path=path + (key,))
            return
        if isinstance(value, str):
            output_refs[f"return__{'__'.join(path)}"] = value

    visit(local_value, path=())
    return output_refs


def _flatten_boundary_leaf_paths(
    type_ref: RecordTypeRef | UnionTypeRef,
    *,
    generated_name: str,
    field_path: tuple[str, ...] = (),
    type_env: Any | None = None,
) -> tuple[tuple[str, tuple[str, ...]], ...]:
    """Return generated boundary names paired with frontend field paths."""

    if isinstance(type_ref, UnionTypeRef):
        return tuple(
            (field.generated_name, field_path + field.source_path[1:])
            for field in derive_workflow_boundary_fields(
                type_ref,
                generated_name=generated_name,
                source_path=(generated_name,),
                span=type_ref.definition.span,
                form_path=("workflow-lisp", "defunion", type_ref.name),
                type_env=type_env,
            )
        )
    flattened: list[tuple[str, tuple[str, ...]]] = []
    for field in type_ref.definition.fields:
        field_type = type_ref.field_types[field.name]
        next_generated_name = f"{generated_name}__{field.name}"
        next_field_path = field_path + (field.name,)
        if isinstance(field_type, (RecordTypeRef, UnionTypeRef)):
            flattened.extend(
                _flatten_boundary_leaf_paths(
                    field_type,
                    generated_name=next_generated_name,
                    field_path=next_field_path,
                    type_env=type_env,
                )
            )
            continue
        flattened.append((next_generated_name, next_field_path))
    return tuple(flattened)


def _record_expr_value_at_path(record_expr: RecordExpr, field_path: tuple[str, ...]) -> Any:
    """Read a nested field from an authored `record` expression."""

    current: Any = record_expr
    for field_name in field_path:
        if isinstance(current, RecordExpr):
            current = _record_field_value(current, field_name)
            continue
        if isinstance(current, UnionVariantExpr):
            current = _union_variant_expr_value_at_path(current, (field_name,), bound_record_fields=False)
            continue
        if not isinstance(current, RecordExpr):
            raise _value_compile_error(
                code="workflow_return_not_exportable",
                message=(
                    f"record return field `{'__'.join(field_path)}` must lower from nested record or variant expressions "
                    "when the workflow return type contains nested records"
                ),
                span=record_expr.span,
                form_path=record_expr.form_path,
            )
    return current


def _normalize_union_field_path(field_path: tuple[str, ...]) -> tuple[str, ...]:
    normalized: list[str] = []
    for segment in field_path:
        normalized.extend(part for part in segment.split("__") if part)
    return tuple(normalized)


def _union_variant_expr_value_at_path(
    union_expr: UnionVariantExpr,
    field_path: tuple[str, ...],
    *,
    bound_record_fields: bool,
) -> Any:
    """Read a field from one compiler-generated union variant literal.

    `bound_record_fields` (target 2.33+) lets a nested record field populated
    from a bound name lower as a field access; older targets reject it.
    """

    field_path = _normalize_union_field_path(field_path)
    if not field_path:
        return union_expr
    field_name = field_path[0]
    if field_name == "variant":
        return LiteralExpr(
            value=union_expr.variant_name,
            literal_kind="string",
            span=union_expr.span,
            form_path=union_expr.form_path,
            expansion_stack=union_expr.expansion_stack,
        )
    for current_name, current_value in union_expr.fields:
        if current_name != field_name:
            continue
        if len(field_path) == 1:
            return current_value
        if isinstance(current_value, (RecordExpr, UnionVariantExpr)):
            return _record_expr_value_at_path(current_value, field_path[1:])
        if bound_record_fields and isinstance(current_value, NameExpr):
            # A nested record populated from a bound value: read the leaf
            # through the same field access an author would write.
            return FieldAccessExpr(
                base=current_value,
                fields=field_path[1:],
                span=current_value.span,
                form_path=current_value.form_path,
                expansion_stack=current_value.expansion_stack,
            )
        if bound_record_fields and isinstance(current_value, FieldAccessExpr):
            return replace(
                current_value, fields=current_value.fields + field_path[1:],
                shared_field_types=(
                    current_value.shared_field_types + (None,) * len(field_path[1:])
                    if current_value.shared_field_types else ()
                ),
            )
        raise _value_compile_error(
            code="workflow_return_not_exportable",
            message=(
                f"union return field `{'__'.join(field_path)}` must lower from nested record expressions "
                "when the workflow return type contains nested records"
            ),
            span=union_expr.span,
            form_path=union_expr.form_path,
        )
    return None


def _render_existing_output_ref(
    expr: Any,
    *,
    local_values: Mapping[str, Any],
    context: Any | None = None,
) -> str | None:
    """Return a shared runtime ref when an expression already names one."""

    if isinstance(expr, PhaseTargetExpr):
        if context is None or context.phase_scope is None:
            return None
        return context.phase_scope.target_refs.get(expr.target_name)
    value = _resolve_inline_expr_value(expr, local_values=local_values)
    if isinstance(value, ProjectedPathRef):
        return value.ref
    if not isinstance(value, str):
        return None
    if value.startswith(("root.steps.", "self.steps.", "parent.steps.", "inputs.")):
        return value
    return None


def _assign_nested_local_value(target: dict[str, Any], field_path: tuple[str, ...], ref: str) -> None:
    """Assign a flattened ref into a nested local-value mapping."""

    current = target
    for field_name in field_path[:-1]:
        nested = current.get(field_name)
        if not isinstance(nested, dict):
            nested = {}
            current[field_name] = nested
        current = nested
    current[field_path[-1]] = ref


def inline_expr_projection_source(
    expr: Any, *, field_path: tuple[str, ...], bound_record_fields: bool,
) -> Any:
    if isinstance(expr, RecordExpr):
        return _record_expr_value_at_path(expr, field_path)
    if isinstance(expr, UnionVariantExpr):
        return _union_variant_expr_value_at_path(
            expr, field_path, bound_record_fields=bound_record_fields,
        )
    return expr


def inline_expr_field_value(
    expr: Any, *, field_path: tuple[str, ...], local_values: Mapping[str, Any],
    bound_record_fields: bool, phase_target_values: Mapping[str, Any] | None,
    retain_expression_facts: bool = False,
) -> Any:
    """Pure projected-leaf resolution using explicit phase availability."""
    selected = inline_expr_projection_source(
        expr, field_path=field_path, bound_record_fields=bound_record_fields,
    )
    if isinstance(selected, PhaseTargetExpr) and phase_target_values is not None:
        return phase_target_values.get(selected.target_name)
    if isinstance(expr, LetStarExpr):
        return inline_let_field_value(
            expr.bindings, body=expr.body, field_path=field_path, local_values=local_values, retain_expression_facts=retain_expression_facts,
        )
    value = _resolve_inline_expr_value(selected, local_values=local_values, retain_expression_facts=retain_expression_facts)
    if isinstance(expr, (RecordExpr, UnionVariantExpr)):
        return value
    return _resolve_nested_local_value(value, field_path) if field_path else value


def inline_let_field_value(bindings: tuple[tuple[str, Any], ...], *, body: Any, field_path: tuple[str, ...], local_values: Mapping[str, Any], retain_expression_facts: bool = False) -> Any:
    """Project a complete suffix using the same resolved-value path as a Let node."""
    child_values = _resolve_inline_let_bindings(bindings, local_values=local_values, retain_expression_facts=retain_expression_facts)
    if child_values is None:
        return None
    value = _resolve_inline_expr_value(body, local_values=child_values, retain_expression_facts=retain_expression_facts)
    return _resolve_nested_local_value(value, field_path) if field_path else value


def _resolve_procedure_lowering(
    typed_procedures: tuple[TypedProcedureDef, ...],
    *,
    typed_workflows: tuple[TypedWorkflowDef, ...],
    workflow_path: Path,
    closed_program: bool = False,
    type_env: FrontendTypeEnvironment,
    procedure_type_envs: Mapping[str, FrontendTypeEnvironment] | None = None,
) -> Mapping[str, TypedProcedureDef]:

    call_counts, lowerable_call_sites = _procedure_private_call_site_analysis(
        typed_procedures,
        typed_workflows=typed_workflows,
        type_env=type_env,
        procedure_type_envs=procedure_type_envs,
    )
    resolved: dict[str, TypedProcedureDef] = {}
    typed_procedures_by_name = {
        procedure.definition.name: procedure for procedure in typed_procedures
    }
    for procedure in typed_procedures:
        requested = procedure.signature.requested_lowering_mode
        boundary_valid = _procedure_private_boundary_valid(
            procedure,
            type_env=procedure_type_env_for(
                procedure,
                procedure_type_envs=procedure_type_envs,
                default=type_env,
            ),
        )
        procedure_type_env = procedure_type_env_for(
            procedure,
            procedure_type_envs=procedure_type_envs,
            default=type_env,
        )
        compile_time_proc_ref_template = (
            bool(procedure.signature.type_params)
            and target_dsl_supports_provider_context_values(
                procedure_type_env.target_dsl_version
            )
        ) or any(
            isinstance(type_ref, ProcRefTypeRef)
            for _, type_ref in procedure.signature.params
        )
        body_valid = _procedure_private_body_valid(
            procedure,
            closed_program=closed_program,
            typed_procedures_by_name=typed_procedures_by_name,
            type_env=type_env,
            procedure_type_envs=procedure_type_envs,
        )
        if (
            requested == ProcedureLoweringMode.PRIVATE_WORKFLOW
            and not boundary_valid
            and not compile_time_proc_ref_template
        ):
            raise _value_compile_error(
                code="proc_private_workflow_boundary_invalid",
                message=f"procedure `{procedure.definition.name}` cannot lower as `private-workflow` in Stage 3",
                span=procedure.definition.span,
                form_path=procedure.definition.form_path,
            )
        if (
            requested == ProcedureLoweringMode.PRIVATE_WORKFLOW
            and not body_valid
            and not compile_time_proc_ref_template
        ):
            raise _value_compile_error(
                code="proc_private_workflow_boundary_invalid",
                message=(
                    f"procedure `{procedure.definition.name}` cannot lower as `private-workflow` in Stage 3 "
                    "because its body would not export step-backed outputs through the shared-validation seam"
                ),
                span=procedure.definition.span,
                form_path=procedure.definition.form_path,
            )
        if (
            requested == ProcedureLoweringMode.PRIVATE_WORKFLOW
            and compile_time_proc_ref_template
        ):
            # The generic ProcRef-bearing definition is a compile-time
            # specialization template, not a runtime workflow boundary.  Its
            # authoritative monomorphic specializations are validated below
            # after compiler fixed-point re-typechecking.
            mode = ProcedureLoweringMode.INLINE
        elif requested == ProcedureLoweringMode.PRIVATE_WORKFLOW:
            mode = ProcedureLoweringMode.PRIVATE_WORKFLOW
        elif (
            requested == ProcedureLoweringMode.AUTO
            and boundary_valid
            and body_valid
            and (
                call_counts.get(procedure.definition.name, 0) > 1
                or (
                    procedure.specialization is not None
                    and any(
                        bool(getattr(procedure.specialization, field_name, {}))
                        for field_name in (
                            "type_bindings",
                            "workflow_ref_bindings",
                            "proc_ref_bindings",
                        )
                    )
                )
            )
            and lowerable_call_sites.get(procedure.definition.name, True)
        ):
            mode = ProcedureLoweringMode.PRIVATE_WORKFLOW
        else:
            mode = ProcedureLoweringMode.INLINE
        generated_name = None
        if mode == ProcedureLoweringMode.PRIVATE_WORKFLOW:
            generated_name = f"%{workflow_path.stem}.{procedure.definition.name}.v1"
        resolved[procedure.definition.name] = TypedProcedureDef(
            definition=procedure.definition,
            signature=procedure.signature,
            typed_body=procedure.typed_body,
            direct_effect_summary=procedure.direct_effect_summary,
            transitive_effect_summary=procedure.transitive_effect_summary,
            resolved_lowering_mode=mode,
            generated_workflow_name=generated_name,
            specialization=procedure.specialization,
        )
    return MappingProxyType(resolved)


def _procedure_private_call_site_analysis(
    typed_procedures: tuple[TypedProcedureDef, ...],
    *,
    typed_workflows: tuple[TypedWorkflowDef, ...],
    type_env: FrontendTypeEnvironment,
    procedure_type_envs: Mapping[str, FrontendTypeEnvironment] | None = None,
) -> tuple[Mapping[str, int], Mapping[str, bool]]:
    """Count procedure call sites and whether each can cross a workflow boundary."""


    typed_procedures_by_name = {
        procedure.definition.name: procedure for procedure in typed_procedures
    }
    distinct_call_sites: dict[str, set[tuple[SourceSpan, tuple[str, ...]]]] = {}
    lowerable: dict[str, bool] = {}

    def walk(
        expr: Any,
        *,
        local_values: Mapping[str, Any],
        current_type_env: FrontendTypeEnvironment,
    ) -> None:
        if isinstance(expr, ProcedureCallExpr):
            distinct_call_sites.setdefault(expr.callee_name, set()).add((expr.span, expr.form_path))
            call_site_lowerable = True
            for arg in expr.args:
                walk(arg, local_values=local_values, current_type_env=current_type_env)
                if _resolve_expr_local_value(arg, local_values=local_values) is None:
                    call_site_lowerable = False
            lowerable[expr.callee_name] = lowerable.get(expr.callee_name, True) and call_site_lowerable
            callee = typed_procedures_by_name.get(expr.callee_name)
            if callee is not None:
                child_locals = {}
                for arg_expr, (param_name, _) in zip(expr.args, callee.signature.params, strict=True):
                    child_locals[param_name] = _resolve_expr_local_value(arg_expr, local_values=local_values)
                walk(
                    callee.typed_body.expr,
                    local_values=child_locals,
                    current_type_env=procedure_type_env_for(
                        callee,
                        procedure_type_envs=procedure_type_envs,
                        default=current_type_env,
                    ),
                )
            return
        if isinstance(expr, LetStarExpr):
            child_locals = dict(local_values)
            for binding_name, binding in expr.bindings:
                walk(binding, local_values=child_locals, current_type_env=current_type_env)
                resolved_binding = _resolve_expr_local_value(binding, local_values=child_locals)
                if resolved_binding is not None:
                    child_locals[binding_name] = resolved_binding
                # schema1_compatibility: legacy local-value projection for covered provider results.
                elif isinstance(binding, ProviderResultExpr):
                    binding_type = current_type_env.resolve_type(
                        binding.returns_type_name,
                        span=binding.span,
                        form_path=binding.form_path,
                    )
                    if isinstance(binding_type, RecordTypeRef):
                        child_locals[binding_name] = _build_record_step_local_value(
                            binding_type,
                            step_name=binding_name,
                        )
            walk(expr.body, local_values=child_locals, current_type_env=current_type_env)
            return
        # schema1_compatibility: legacy procedure traversal for covered match forms.
        if isinstance(expr, MatchExpr):
            walk(expr.subject, local_values=local_values, current_type_env=current_type_env)
            for arm in expr.arms:
                walk(arm.body, local_values=local_values, current_type_env=current_type_env)
            return
        if isinstance(expr, RecordExpr):
            for _, value in expr.fields:
                walk(value, local_values=local_values, current_type_env=current_type_env)
            return
        if isinstance(expr, WithPhaseExpr):
            walk(expr.ctx_expr, local_values=local_values, current_type_env=current_type_env)
            walk(expr.body, local_values=local_values, current_type_env=current_type_env)
            return
        # schema1_compatibility: legacy procedure traversal for covered provider results.
        if isinstance(expr, ProviderResultExpr):
            walk(expr.provider, local_values=local_values, current_type_env=current_type_env)
            walk(expr.prompt, local_values=local_values, current_type_env=current_type_env)
            for value in expr.inputs:
                walk(value, local_values=local_values, current_type_env=current_type_env)
            return
        # schema1_compatibility: legacy procedure traversal for covered command results.
        if isinstance(expr, CommandResultExpr):
            for value in expr.argv:
                walk(value, local_values=local_values, current_type_env=current_type_env)
            return
        if isinstance(expr, CallExpr):
            for _, value in expr.bindings:
                walk(value, local_values=local_values, current_type_env=current_type_env)

    for workflow in typed_workflows:
        walk(
            workflow.typed_body.expr,
            local_values=_signature_local_values(workflow, type_env=type_env),
            current_type_env=type_env,
        )
    return MappingProxyType(
        {
            callee_name: len(call_sites)
            for callee_name, call_sites in distinct_call_sites.items()
        }
    ), MappingProxyType(lowerable)


def resolved_surface_proc_ref(
    value: Any, *, typed_procedures: Mapping[str, Any], local_values: Mapping[str, Any],
    procedure_catalog: Any = None, expected_type: Any = None,
) -> Any:
    from orchestrator.workflow_lisp.expressions import BindProcExpr, ProcRefLiteralExpr
    from orchestrator.workflow_lisp.procedure_refs import ResolvedProcRefValue, resolve_proc_ref_value
    from orchestrator.workflow_lisp.procedures import ProcedureCatalog

    if isinstance(value, ResolvedProcRefValue):
        return value
    if not isinstance(value, (NameExpr, ProcRefLiteralExpr, BindProcExpr)):
        return None
    if procedure_catalog is None:
        procedure_catalog = ProcedureCatalog(
            signatures_by_name={name: proc.signature for name, proc in typed_procedures.items()},
            definitions_by_name={name: proc.definition for name, proc in typed_procedures.items()},
            call_graph={},
        )
    return resolve_proc_ref_value(
        value, procedure_catalog=procedure_catalog,
        proc_ref_env={name: ref for name, ref in local_values.items() if isinstance(ref, ResolvedProcRefValue)},
        expected_type=expected_type,
    )


def resolved_surface_workflow_ref(
    value: Any, *, workflow_catalog: Any, typed_workflows: Mapping[str, Any],
    expected_type: Any = None,
) -> Any:
    from orchestrator.workflow_lisp.expressions import EnumMemberExpr, WorkflowRefLiteralExpr
    from orchestrator.workflow_lisp.workflow_refs import (
        ResolvedWorkflowRef, resolve_workflow_ref_literal, resolve_workflow_ref_name,
        workflow_ref_target_name,
    )
    from orchestrator.workflow_lisp.type_env import WorkflowRefTypeRef

    if isinstance(value, ResolvedWorkflowRef):
        return value
    if isinstance(value, WorkflowRefLiteralExpr):
        if expected_type is None:
            signature = workflow_catalog.signatures_by_name.get(value.target_name)
            if signature is None:
                raise _value_compile_error(
                    code="workflow_ref_unknown", message=f"unknown workflow ref `{value.target_name}`",
                    span=value.span, form_path=value.form_path,
                )
            expected_type = WorkflowRefTypeRef(
                name=f"WorkflowRef[{ ' '.join(type_ref.name for _, type_ref in signature.params) } -> {signature.return_type_ref.name}]",
                param_type_refs=tuple(type_ref for _, type_ref in signature.params),
                return_type_ref=signature.return_type_ref,
            )
        return resolve_workflow_ref_literal(
            value, expected_type=expected_type, workflow_catalog=workflow_catalog,
            typed_workflows_by_name=typed_workflows, allow_extern_rebinding=False,
        )
    if isinstance(value, (NameExpr, EnumMemberExpr)):
        return resolve_workflow_ref_name(
            workflow_ref_target_name(value), workflow_catalog=workflow_catalog,
            span=value.span, form_path=value.form_path, expansion_stack=value.expansion_stack,
            expected_type=expected_type, typed_workflows_by_name=typed_workflows,
            allow_extern_rebinding=False,
        )
    return None


def _surface_procedure_callee(
    call: Any, *, local_values: Mapping[str, Any], typed_procedures: Mapping[str, Any],
    procedure_catalog: Any,
) -> Any:

    if call.specialized_callee_name is not None:
        name = call.specialized_callee_name
        code = "procedure_lowering_unresolved"
        message = f"compiler-owned specialization row `{name}` is missing during lowering"
    else:
        bound = resolved_surface_proc_ref(
            local_values.get(call.callee_name), typed_procedures=typed_procedures,
            procedure_catalog=procedure_catalog, local_values=local_values,
        )
        if bound is not None:
            name = bound.call_target_name
            code = "procedure_lowering_unresolved"
            message = f"compiler-owned bound ProcRef specialization row `{name}` is missing during lowering"
        else:
            name = call.callee_name
            code = "procedure_call_unknown"
            message = f"unknown procedure callee `{name}` during lowering"
    procedure = typed_procedures.get(name)
    if procedure is None:
        raise _value_compile_error(code=code, message=message, span=call.span, form_path=call.form_path)
    return procedure


def _surface_procedure_actuals(
    procedure: Any, args: tuple[Any, ...], *, local_values: Mapping[str, Any],
    typed_procedures: Mapping[str, Any], procedure_catalog: Any,
    workflow_catalog: Any, typed_workflows: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], tuple[Any, ...]]:
    from orchestrator.workflow_lisp.expressions import EnumMemberExpr
    from orchestrator.workflow_lisp.type_env import ProcRefTypeRef, WorkflowRefTypeRef

    workflow_refs = {}
    proc_refs = {}
    residual = []
    for arg, (name, param_type) in zip(args, procedure.signature.params, strict=True):
        if isinstance(param_type, WorkflowRefTypeRef):
            candidate = arg if isinstance(arg, EnumMemberExpr) else _resolve_inline_expr_value(arg, local_values=local_values) or arg
            resolved = resolved_surface_workflow_ref(
                candidate, workflow_catalog=workflow_catalog, typed_workflows=typed_workflows,
                expected_type=param_type,
            )
            if resolved is None:
                raise _value_compile_error(
                    code="workflow_ref_literal_required",
                    message="workflow-ref arguments must be literals or forwarded workflow-ref bindings",
                    span=arg.span, form_path=arg.form_path,
                )
            workflow_refs[name] = resolved
            continue
        if isinstance(param_type, ProcRefTypeRef):
            resolved = resolved_surface_proc_ref(
                _resolve_inline_expr_value(arg, local_values=local_values) or arg,
                typed_procedures=typed_procedures, procedure_catalog=procedure_catalog,
                local_values=local_values, expected_type=param_type,
            )
            if resolved is not None:
                proc_refs[name] = resolved
                continue
        residual.append(arg)
    return workflow_refs, proc_refs, tuple(residual)


def select_surface_procedure_call(
    call: Any, *, local_values: Mapping[str, Any], typed_procedures: Mapping[str, Any],
    procedure_catalog: Any, workflow_catalog: Any, typed_workflows: Mapping[str, Any],
) -> tuple[Any, tuple[Any, ...]]:

    procedure = _surface_procedure_callee(
        call, local_values=local_values, typed_procedures=typed_procedures,
        procedure_catalog=procedure_catalog,
    )
    workflow_refs, proc_refs, residual = _surface_procedure_actuals(
        procedure, call.args, local_values=local_values, typed_procedures=typed_procedures,
        procedure_catalog=procedure_catalog, workflow_catalog=workflow_catalog,
        typed_workflows=typed_workflows,
    )
    if not (workflow_refs or proc_refs):
        return procedure, call.args
    rows = materialized_specialization_rows(
        procedure, workflow_ref_bindings=workflow_refs, proc_ref_bindings=proc_refs,
        typed_procedures=typed_procedures,
    )
    if len(rows) != 1:
        raise _value_compile_error(
            code="procedure_lowering_unresolved",
            message="compiler-owned procedure specialization row with exact compile-time bindings is missing or ambiguous during lowering",
            span=call.span, form_path=call.form_path,
        )
    return rows[0], residual


def inline_procedure_bindings(
    procedure: Any, *, caller_values: Mapping[str, Any], actual_values: tuple[Any, ...],
) -> dict[str, Any]:
    values = dict(caller_values)
    values.update(procedure_specialization_bindings(procedure))
    for value, (name, _) in zip(actual_values, procedure.signature.params, strict=True):
        values[name] = value
    return values


def procedure_specialization_bindings(procedure: Any) -> dict[str, Any]:
    values: dict[str, Any] = {}
    if procedure.specialization is not None:
        for kind in ("workflow_ref_bindings", "proc_ref_bindings", "value_bindings"):
            values.update(dict(getattr(procedure.specialization, kind, {})))
    return values


RUNTIME_REFERENCE = object()


@dataclass(frozen=True)
class RetainedExpressionFact:
    """Closed-only constructor facts selected under their creation locals."""

    form: Literal["record", "union", "opaque"]
    projection_candidate: bool
    fields: tuple[tuple[str, Any], ...] = ()
    tag: LiteralExpr | None = None


def schema1_iteration_private_override_applies(
    procedure: Any, *, iteration_scope: Any, workflow_name: str,
    default_type_env: Any, typed_procedures: Mapping[str, Any],
    procedure_type_envs: Mapping[str, Any], workflow_signatures: Mapping[str, Any],
) -> bool:
    """Surface-only iteration override, with the existing private eligibility."""
    from orchestrator.workflow_lisp.expression_traversal import walk_expr
    from orchestrator.workflow_lisp.expressions import LoopRecurExpr
    from orchestrator.workflow_lisp.procedures import ProcedureLoweringMode, procedure_type_env_for

    if not (
        procedure.resolved_lowering_mode == ProcedureLoweringMode.INLINE
        and iteration_scope is not None
        and not workflow_name.startswith("%composition.")
        and not any(isinstance(node, LoopRecurExpr) for node in walk_expr(procedure.typed_body.expr))
    ):
        return False
    procedure_type_env = procedure_type_env_for(
        procedure, procedure_type_envs=procedure_type_envs, default=default_type_env,
    )
    return _procedure_private_boundary_valid(
        procedure, type_env=procedure_type_env,
    ) and _procedure_private_body_valid(
        procedure, typed_procedures_by_name=typed_procedures,
        type_env=procedure_type_env, procedure_type_envs=procedure_type_envs,
        workflow_signatures_by_name=workflow_signatures,
    )


def _control_binding_terminal_for_match_subject_impl(
    subject: Any,
    *,
    local_values: Mapping[str, Any],
) -> Mapping[str, str] | None:
    resolved_subject = _resolve_inline_expr_value(subject, local_values=local_values)
    return _control_binding_terminal_for_inline_match_impl(resolved_subject)


def _control_match_arm_local_values_impl(
    *,
    local_values: Mapping[str, Any],
    binding_name: str,
    binding_terminal: Mapping[str, str],
    binding_type: TypeRef | None = None,
) -> dict[str, Any]:
    localized_output_refs = {
        output_name: _match_subject_scope_value(output_ref)
        for output_name, output_ref in binding_terminal.items()
    }
    if isinstance(binding_type, VariantCaseTypeRef):
        allowed_field_names = {"variant", *(field.name for field in binding_type.definition.fields)}
        localized_output_refs = {
            output_name: output_ref
            for output_name, output_ref in localized_output_refs.items()
            if output_name == "return__variant"
            or output_name.removeprefix("return__").split("__", 1)[0] in allowed_field_names
        }
    binding_value = _build_output_step_local_value(localized_output_refs)
    if isinstance(binding_type, UnionTypeRef):
        source = union_prompt_source_from_output_refs(
            binding_type,
            output_refs=localized_output_refs,
        )
        if source is not None:
            binding_value["__typed_union_prompt_source__"] = source
    return {
        **local_values,
        binding_name: binding_value,
    }


def _control_binding_terminal_for_inline_match_impl(local_value: Any) -> Mapping[str, str] | None:
    output_refs = _flatten_inline_output_refs(local_value)
    if "return__variant" not in output_refs:
        return None
    return output_refs


def _match_subject_scope_value(value: Any) -> Any:
    if isinstance(value, str):
        if value.startswith("self.steps."):
            return "parent.steps." + value.removeprefix("self.steps.")
        return value
    if isinstance(value, Mapping):
        return {name: _match_subject_scope_value(item) for name, item in value.items()}
    return value
