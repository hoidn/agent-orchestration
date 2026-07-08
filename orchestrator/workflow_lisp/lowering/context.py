"""Shared lowering state objects and context-copy helpers."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from orchestrator.workflow.loaded_bundle import LoadedWorkflowBundle
from orchestrator.workflow.state_layout import GeneratedPathAllocation
from orchestrator.workflow.surface_ast import PrivateExecContextBinding

from ..contracts import WorkflowBoundaryProjection
from ..diagnostics import LispFrontendCompileError, LispFrontendDiagnostic
from ..phase import PhaseScope
from ..procedures import TypedProcedureDef
from ..spans import SourceSpan
from ..type_env import FrontendTypeEnvironment, TypeRef
from ..workflows import (
    CommandBoundaryEnvironment,
    ExternEnvironment,
    TypedWorkflowDef,
    WorkflowCatalog,
)
from .origins import GeneratedSemanticEffectBinding, LoweringOrigin


@dataclass
class _TerminalResult:
    """Outputs produced by the last lowered expression in a workflow fragment."""

    step_name: str
    step_id: str
    output_refs: Mapping[str, str]
    output_kind: str
    hidden_inputs: Mapping[str, LoweringOrigin]
    provider_bundle_identity: Mapping[str, Any] | None = None
    returned_union_type_name: str | None = None
    returned_union_variant_name: str | None = None


@dataclass(frozen=True)
class _NormalizedBindingResult:
    """One normalized `let*` binding shared across lowering entrypoints."""

    binding_type: TypeRef | None
    emitted_steps: list[dict[str, Any]]
    terminal: _TerminalResult | None
    local_value: Any | None


@dataclass
class _LoweringContext:
    """Mutable state threaded through expression lowering."""

    workflow_name: str
    step_name_prefix: str
    workflow_path: Path
    signature: object
    authored_input_contracts: Mapping[str, Mapping[str, Any]]
    workflow_catalog: WorkflowCatalog
    imported_workflow_bundles: Mapping[str, LoadedWorkflowBundle]
    extern_environment: ExternEnvironment
    command_boundary_environment: CommandBoundaryEnvironment
    lowered_callees: Mapping[str, object]
    typed_procedures: Mapping[str, TypedProcedureDef]
    workflows_by_name: Mapping[str, TypedWorkflowDef]
    ensure_workflow_lowered: Any
    specialize_workflow: Any
    type_env: FrontendTypeEnvironment
    step_spans: dict[str, LoweringOrigin]
    generated_input_spans: dict[str, LoweringOrigin]
    authored_generated_inputs: set[str]
    internal_generated_input_reasons: dict[str, str]
    internal_generated_input_contracts: dict[str, dict[str, Any]]
    private_exec_context_bindings: list[PrivateExecContextBinding]
    generated_output_spans: Mapping[str, LoweringOrigin]
    generated_path_spans: dict[str, LoweringOrigin]
    generated_path_allocations: list[GeneratedPathAllocation]
    generated_semantic_effects: list[GeneratedSemanticEffectBinding]
    output_projection_metadata: dict[str, Mapping[str, Any]]
    top_level_artifacts: dict[str, Any]
    inline_call_counters: dict[str, int]
    origin_notes: tuple[str, ...]
    boundary_projection: WorkflowBoundaryProjection
    return_output_contracts: Mapping[str, Mapping[str, Any]]
    local_type_bindings: Mapping[str, TypeRef]
    is_generated_private_workflow: bool
    phase_scope: _ActivePhaseScope | None = None
    iteration_scope: str | None = None
    lowering_schema_version: int | None = None
    wcc_effect_lowerer: Any | None = None
    generated_private_workflow_type_envs: dict[str, FrontendTypeEnvironment] | None = None
    procedure_type_envs: Mapping[str, FrontendTypeEnvironment] | None = None
    active_procedure_calls: frozenset[str] = frozenset()
    composition_scope_id: str | None = None
    parent_composition_scope_id: str | None = None
    composition_scope_kind: str | None = None
    composition_scope_owner_step_name: str | None = None
    requires_guarded_case_step_hoist: bool = False
    # recursion entry points, set by core at construction; break the
    # leaf -> core back-import cycle for mutual recursion only
    lower_expression: Callable[..., Any] | None = None
    lower_call_expr: Callable[..., Any] | None = None
    record_step_origin: Callable[..., Any] | None = None
    normalize_generated_step_id: Callable[..., Any] | None = None


@dataclass(frozen=True)
class _ActivePhaseScope:
    """Derived state and artifact refs installed by `with-phase`."""

    scope: PhaseScope
    bundle_path_ref: str
    target_refs: Mapping[str, str]
    temp_bundle_path_ref: str | None = None
    snapshot_root_ref: str | None = None
    candidate_root_ref: str | None = None
    runtime_phase_name_ref: str | None = None


def _copy_context_with_phase_scope(
    context: _LoweringContext,
    phase_scope: _ActivePhaseScope,
) -> _LoweringContext:
    """Clone lowering context while installing the active phase scope."""

    return replace(context, phase_scope=phase_scope)


def _copy_context_with_step_prefix(
    context: _LoweringContext,
    *,
    step_name_prefix: str,
) -> _LoweringContext:
    """Clone context state while changing the generated step-name prefix."""

    return replace(context, step_name_prefix=step_name_prefix)


def _context_with_local_type_binding(
    context: _LoweringContext,
    *,
    binding_name: str,
    binding_type: TypeRef | None,
) -> _LoweringContext:
    """Return a context extended with one resolved local binding type."""

    if binding_type is None:
        return context
    return replace(
        context,
        local_type_bindings={**dict(context.local_type_bindings), binding_name: binding_type},
    )


def _copy_context_with_iteration_scope(
    context: _LoweringContext,
    *,
    iteration_scope: str | None,
) -> _LoweringContext:
    """Clone context state while changing the active loop-iteration scope."""

    return replace(context, iteration_scope=iteration_scope)


def _copy_context_with_composition_scope(
    context: _LoweringContext,
    *,
    scope_id: str,
    parent_scope_id: str | None,
    scope_kind: str,
    owner_step_name: str | None,
) -> _LoweringContext:
    """Clone context state while setting lowering-time composition scope metadata."""

    return replace(
        context,
        composition_scope_id=scope_id,
        parent_composition_scope_id=parent_scope_id,
        composition_scope_kind=scope_kind,
        composition_scope_owner_step_name=owner_step_name,
    )


def _compile_error(*, code: str, message: str, span: SourceSpan, form_path: tuple[str, ...]) -> LispFrontendCompileError:
    """Create a single lowering-phase frontend compile error."""

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
