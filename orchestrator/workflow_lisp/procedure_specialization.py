"""Procedure specialization ownership for Workflow Lisp stage-3 compilation."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from dataclasses import replace
from pathlib import Path
from typing import Any

from .contracts import derive_workflow_boundary_fields
from .diagnostics import LispFrontendCompileError, LispFrontendDiagnostic
from .effects import EMPTY_EFFECT_SUMMARY
from .expression_traversal import iter_child_exprs
from .expressions import (
    CallExpr,
    CommandResultExpr,
    FieldAccessExpr,
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
    RecordExpr,
    ResourceTransitionExpr,
    ResumeOrStartExpr,
    RunProviderPhaseExpr,
    UnionVariantExpr,
    WithPhaseExpr,
)
from .lowering.pure_projection import is_pure_projection_expr
from .procedure_refs import ResolvedProcRefValue, resolve_proc_ref_value
from .procedures import (
    ProcedureCallableSpecialization,
    ProcedureCatalog,
    ProcedureLoweringMode,
    ProcedureParam,
    TypedProcedureDef,
    parametric_specialization_name,
    proc_ref_specialization_name as proc_ref_call_specialization_name,
    procedure_type_env_for,
)
from .result_guidance import validate_result_guidance_example
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
    render_type_ref,
    substitute_type_params,
)
from .workflow_refs import ResolvedWorkflowRef, specialization_name
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


def _procedure_private_boundary_valid(procedure: TypedProcedureDef) -> bool:
    """Return whether a procedure signature can become a private workflow."""

    try:
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
    except TypeError:
        return False


def _procedure_private_body_valid(
    procedure: TypedProcedureDef,
    *,
    typed_procedures_by_name: Mapping[str, TypedProcedureDef],
    type_env: FrontendTypeEnvironment,
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

    from .lowering.values import (
        _procedure_signature_local_type_bindings,
        _procedure_signature_local_values,
    )

    current_type_env = (
        procedure_type_envs.get(procedure.definition.name, type_env)
        if procedure_type_envs is not None
        else type_env
    )

    return _private_workflow_body_exports_step_backed_outputs(
        procedure.typed_body.expr,
        return_type_ref=procedure.signature.return_type_ref,
        local_values=_procedure_signature_local_values(procedure),
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
    if isinstance(expr, RecordExpr):
        return type_env.resolve_type(
            expr.type_name,
            span=expr.span,
            form_path=expr.form_path,
        )
    if isinstance(expr, UnionVariantExpr):
        return type_env.resolve_type(
            expr.type_name,
            span=expr.span,
            form_path=expr.form_path,
        )
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

    from .lowering.control import _binding_terminal_for_match_subject, _is_inline_let_binding_expr
    from .lowering.values import _procedure_signature_local_type_bindings, _resolve_inline_expr_value
    from .lowering.workflow_calls import _managed_write_root_binding_step

    _ = _managed_write_root_binding_step

    step_name = f"{binding_name}__{expr.step_name}" if isinstance(expr, CommandResultExpr) else binding_name
    if _is_inline_let_binding_expr(expr):
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
        callee = typed_procedures_by_name.get(expr.callee_name)
        if callee is None or callee.definition.name in active_procedures:
            return None
        child_locals = dict(local_values)
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
        if _binding_terminal_for_match_subject(expr.subject, local_values=local_values) is None:
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

    from .lowering.values import _build_output_step_local_value

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
        return _build_output_step_local_value(output_refs)
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

    from .lowering.values import (
        _procedure_signature_local_type_bindings,
        _resolve_inline_expr_value,
    )

    if is_pure_projection_expr(expr):
        return True
    if isinstance(
        expr,
        (
            CommandResultExpr,
            ProviderResultExpr,
            CallExpr,
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
        callee = typed_procedures_by_name.get(expr.callee_name)
        if callee is None or callee.definition.name in active_procedures:
            return False
        child_locals = dict(local_values)
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

    from .lowering.control import _binding_terminal_for_inline_match, _match_arm_local_values
    from .lowering.values import _resolve_inline_expr_value
    binding_terminal = _binding_terminal_for_inline_match(
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
            local_values=_match_arm_local_values(
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

    from .lowering.values import (
        _flatten_boundary_leaf_paths,
        _record_expr_value_at_path,
        _render_existing_output_ref,
    )

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
) -> bool:
    """Return whether one union variant can lower through a private workflow seam."""

    from .lowering.values import (
        _flatten_boundary_leaf_paths,
        _normalize_union_field_path,
        _render_existing_output_ref,
        _resolve_inline_expr_value,
        _union_variant_expr_value_at_path,
    )

    if not isinstance(return_type_ref, UnionTypeRef):
        return False
    active_field_names = {name for name, _ in union_expr.fields}
    for _, raw_field_path in _flatten_boundary_leaf_paths(return_type_ref, generated_name="return"):
        field_path = _normalize_union_field_path(raw_field_path)
        field_name = field_path[0] if field_path else ""
        if field_name != "variant" and field_name not in active_field_names:
            continue
        value = _union_variant_expr_value_at_path(union_expr, field_path)
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

    from .lowering.values import (
        _flatten_boundary_leaf_paths,
        _flatten_inline_output_refs,
        _resolve_inline_expr_value,
    )

    output_refs = _flatten_inline_output_refs(_resolve_inline_expr_value(expr, local_values=local_values))
    if not output_refs:
        return False
    for output_name, _ in _flatten_boundary_leaf_paths(return_type_ref, generated_name="return"):
        source_ref = output_refs.get(output_name)
        if not isinstance(source_ref, str) or not source_ref.startswith(("root.steps.", "self.steps.", "parent.steps.")):
            return False
    return True


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
        typed_body=request.procedure.typed_body,
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
        boundary_valid = _procedure_private_boundary_valid(specialized)
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
) -> TypedProcedureDef | None:
    if not resolved.bound_args:
        return None
    base_procedure = typed_procedures_by_name.get(resolved.procedure_name)
    if base_procedure is None:
        return None
    proc_ref_bindings: dict[str, ResolvedProcRefValue] = {}
    value_bindings: dict[str, object] = {}
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
        value_bindings[binding.name] = binding.value_expr
    return specialize_typed_procedure(
        base_procedure,
        proc_ref_bindings=proc_ref_bindings,
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
    )


def discover_proc_ref_specializations(
    *,
    typed_procedures: tuple[TypedProcedureDef, ...],
    typed_workflows: tuple[TypedWorkflowDef, ...],
    procedure_catalog: ProcedureCatalog,
    type_env: FrontendTypeEnvironment,
    procedure_type_envs: Mapping[str, FrontendTypeEnvironment] | None = None,
) -> tuple[TypedProcedureDef, ...]:
    from .expressions import LetStarExpr, ProcedureCallExpr

    discovered: dict[str, TypedProcedureDef] = {}
    typed_procedures_by_name = {procedure.definition.name: procedure for procedure in typed_procedures}

    def record_specialization(
        specialized: TypedProcedureDef | None,
    ) -> None:
        if specialized is None:
            return
        if specialized.definition.name in typed_procedures_by_name:
            return
        discovered.setdefault(specialized.definition.name, specialized)

    def walk(node: object, proc_ref_env: Mapping[str, ResolvedProcRefValue]) -> None:
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
                    )
                )
            else:
                signature = procedure_catalog.signatures_by_name.get(node.callee_name)
                if signature is not None:
                    if len(node.args) != len(signature.params):
                        for arg in node.args:
                            walk(arg, proc_ref_env)
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
                        base_procedure = typed_procedures_by_name.get(signature.name)
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
                                )
                            )
            for arg in node.args:
                walk(arg, proc_ref_env)
            return
        if isinstance(node, LetStarExpr):
            child_env = dict(proc_ref_env)
            for binding_name, binding_expr in node.bindings:
                walk(binding_expr, child_env)
                resolved_binding = resolve_proc_ref_value(
                    binding_expr,
                    procedure_catalog=procedure_catalog,
                    proc_ref_env=child_env,
                )
                if resolved_binding is not None:
                    child_env[binding_name] = resolved_binding
            walk(node.body, child_env)
            return
        for child in iter_child_exprs(node):
            walk(child, proc_ref_env)

    for procedure in typed_procedures:
        proc_ref_env = dict(getattr(procedure.specialization, "proc_ref_bindings", {}))
        walk(procedure.typed_body.expr, proc_ref_env)
    for workflow in typed_workflows:
        walk(workflow.typed_body.expr, {})
    return tuple(discovered.values())
