"""Lower typed Workflow Lisp workflows into ordinary workflow dictionaries.

This module is the bridge from frontend semantics to the existing workflow
runtime. It takes typechecked frontend expressions and emits the same
dictionary shape produced by YAML loading, so the shared loader, elaborator,
semantic IR builder, and executable IR pipeline can handle the result.

The important rule is that lowering must not make the generated workflow mean
something weaker than the `.orc` source. Provider and command results must be
checked before later steps read them. Fields that exist only for one union case
must be readable only in the branch that proved that case was selected. Every
generated step must still point back to the `.orc` form that caused it.

Terminology used in this module:

- an ordinary workflow dictionary is the Python mapping shape the YAML loader
  produces before shared validation;
- a provider step asks an LLM/provider to produce outputs under a declared
  contract;
- a command step runs a deterministic command or certified adapter;
- a structured bundle is a JSON file validated by `output_bundle` or
  `variant_output`, used as semantic state instead of parsing markdown reports.

For the intended lowering contracts, see
`../../docs/design/workflow_lisp_stdlib_lowering.md`. For the broader architecture
and diagrams, see `../../docs/design/workflow_lisp_frontend_specification.md`.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from types import MappingProxyType
from typing import Any

from orchestrator.exceptions import ValidationSubjectRef, WorkflowValidationError
from orchestrator.loader import WorkflowLoader
from orchestrator.workflow.surface_ast import PrivateExecContextBinding
from orchestrator.workflow.executable_ir import ProviderStepConfig
from orchestrator.workflow.elaboration import elaborate_surface_workflow
from orchestrator.workflow.loaded_bundle import LoadedWorkflowBundle, workflow_managed_write_root_inputs
from orchestrator.workflow.lowering import build_loaded_workflow_bundle
from orchestrator.workflow.references import StructuredStepReference
from orchestrator.workflow.state_layout import (
    GeneratedPathAllocation,
    derive_entrypoint_managed_write_root_allocations,
)
from orchestrator.workflow.surface_ast import SurfaceStep, SurfaceStepKind

from ..conditionals import classify_condition_expr, render_condition_predicate
from ..definitions import elaborate_definition_module
from ..contracts import (
    GeneratedInternalInput,
    WorkflowBoundaryProjection,
    derive_reusable_state_contract_metadata,
    derive_structured_result_contract,
    derive_workflow_boundary_fields,
    derive_workflow_signature_contracts,
)
from ..diagnostics import (
    LispFrontendCompileError,
    LispFrontendDiagnostic,
    with_diagnostic_metadata,
)
from ..expressions import (
    BacklogDrainExpr,
    BindProcExpr,
    CallExpr,
    CommandResultExpr,
    ContinueExpr,
    DoneExpr,
    FinalizeSelectedItemExpr,
    FieldAccessExpr,
    GeneratedRelpathSeedExpr,
    IfExpr,
    LetStarExpr,
    LiteralExpr,
    LoopStateSeedExpr,
    LoopStateUpdateExpr,
    LoopRecurExpr,
    MatchExpr,
    NameExpr,
    PhaseTargetExpr,
    PureOpExpr,
    ProcRefLiteralExpr,
    ProduceOneOfExpr,
    ProcedureCallExpr,
    ProviderBundlePathExpr,
    ProviderResultExpr,
    ResourceTransitionExpr,
    RecordExpr,
    RecordUpdateExpr,
    ResumeOrStartExpr,
    RunProviderPhaseExpr,
    UnionVariantExpr,
    WorkflowRefLiteralExpr,
    WithPhaseExpr,
)
from .generated_paths import allocation_reason
from ..loops import (
    LOOP_STATUS_ALLOWED,
    LOOP_STATUS_OUTPUT_NAME,
    LoopLoweringPlan,
    LoopValueProjection,
    build_loop_lowering_plan,
    internal_loop_contract,
    project_loop_value,
    projection_relpath_fields,
)
from ..phase import (
    IMPLEMENTATION_ATTEMPT_PHASE_NAME,
    PHASE_CONTEXT_NAME,
    PHASE_TARGET_SPECS,
    PhaseScope,
    PromotedEntryHiddenContextRequirement,
    RUN_CONTEXT_NAME,
)
from ..phase_family_boundary import (
    apply_phase_family_boundary_classification,
    record_direct_entry_phase_context_binding,
)
from ..macros import collect_macro_catalog, expand_module_forms
from ..reader import read_sexpr_file
from ..spans import SourceSpan
from ..syntax import WorkflowLispSyntaxModule, build_syntax_module, syntax_head_name, syntax_node_datum
from ..type_env import (
    FrontendTypeEnvironment,
    OptionalTypeRef,
    PathTypeRef,
    PrimitiveTypeRef,
    ProcRefTypeRef,
    RecordTypeRef,
    TypeRef,
    UnionTypeRef,
    VariantCaseTypeRef,
    WorkflowRefTypeRef,
)
from ..typecheck import TypedExpr
from ..procedure_refs import ResolvedProcRefValue, resolve_proc_ref_value
from ..procedures import (
    ProcedureCallableSpecialization,
    ProcedureCatalog,
    ProcedureLoweringMode,
    TypedProcedureDef,
)
from ..procedures import proc_ref_specialization_name as proc_ref_call_specialization_name
from ..workflow_refs import (
    ResolvedWorkflowRef,
    WorkflowCallableSpecialization,
    resolve_workflow_ref_literal,
    resolve_workflow_ref_name,
    specialization_name,
    workflow_ref_binding_names,
    workflow_ref_target_name,
)
from ..workflows import (
    CertifiedAdapterBinding,
    CommandBoundaryEnvironment,
    ExternEnvironment,
    PromptExtern,
    ProviderExtern,
    WorkflowCatalog,
    WorkflowDef,
    WorkflowParam,
    WorkflowSignature,
    TypedWorkflowDef,
    analyze_workflow_boundary_type,
)
from .context import (
    _ActivePhaseScope,
    _copy_context_with_iteration_scope,
    _copy_context_with_phase_scope,
    _copy_context_with_step_prefix,
    _context_with_local_type_binding,
    _LoweringContext,
    _NormalizedBindingResult,
    _TerminalResult,
)
from .origins import (
    _build_validation_subject_bindings,
    _derive_generated_semantic_effects,
    _origin_for_workflow as _origin_for_workflow_owner,
    _origin_from_context_source,
    _origins_with_keys,
    _raise_remapped_validation_error,
    _record_missing_step_origins,
    _record_step_origin,
    _rekey_origin_map,
    _with_origin_key,
    GeneratedSemanticEffectBinding,
    LoweringOrigin,
    LoweringOriginMap,
    ValidationSubjectBinding,
)
from .effects import _lower_command_result, _lower_provider_result
from .control import (
    _materialize_values_step,
    _build_match_projection_anchor_step,
    _binding_terminal_for_inline_match,
    _binding_terminal_for_match_subject,
    _conditional_case_ref,
    _inline_procedure_step_prefix,
    _is_inline_let_binding_expr,
    _lower_expression,
    _lower_if_expr,
    _lower_let_star,
    _lower_loop_recur,
    _lower_match_expr,
    _match_arm_local_values,
)
from .values import (
    _assign_nested_local_value,
    _build_output_step_local_value,
    _build_record_local_value,
    _build_record_step_local_value,
    _flatten_boundary_leaf_paths,
    _flatten_return_output_names,
    _inline_expr_field_value,
    _lower_record_expr,
    _lower_union_variant_expr,
    _phase_target_inline_ref,
    _procedure_signature_local_type_bindings,
    _procedure_signature_local_values,
    _record_output_refs,
    _record_expr_value_at_path,
    _resolve_nested_local_value,
    _resolve_expr_local_value,
    _render_existing_output_ref,
    _render_provider_artifact_ref,
    _return_field_path,
    _resolve_inline_expr_value,
    _signature_local_values,
    _union_variant_materialize_source,
    _boundary_placeholder_literals,
)
from .workflow_calls import (
    _declare_runtime_context_hidden_inputs,
    _lower_call_expr,
    _managed_write_root_binding_step,
    _managed_write_root_bindings,
    _managed_write_root_requirements_for_callable,
    _record_call_binding_label,
    _render_argv_tail,
    _render_boolean_predicate,
    _render_call_binding_ref,
    _render_call_binding_leaf_ref,
    _render_record_call_bindings,
    _render_repeat_until_max_iterations,
)
from .phase_impl import (
    _build_phase_prompt_input_prelude,
    _build_phase_stdlib_prompt_input_prelude,
    _flatten_phase_stdlib_prompt_inputs,
    _join_ref_path,
    _lower_composed_with_phase,
    _lower_workflow_outputs,
    _phase_prompt_inputs_are_direct,
    _phase_prompt_artifact_definition,
    _phase_prompt_input_pointer_path,
    _require_phase_scope_name_match,
    _resolved_proc_ref_value,
    _resolved_workflow_ref_value,
    _resolve_active_phase_scope,
    _surface_contract_from_structured_field,
    _template_for_ref,
    _union_output_contracts,
    _uses_legacy_phase_prompt_input_prelude,
    _workflow_extern_requirements,
)
from .phase_stdlib import (
    _lower_backlog_drain,
    _lower_finalize_selected_item,
    _lower_produce_one_of,
    _lower_resource_transition,
    _lower_resume_or_start,
    _lower_run_provider_phase,
    _lower_with_phase,
    review_loop_result_case_outputs as review_loop_result_case_outputs_owner,
    review_loop_result_output_contracts as review_loop_result_output_contracts_owner,
)
_GENERATED_STEP_ID_RE = re.compile(r"[^A-Za-z0-9_]+")


def _prompt_source_step_fields(prompt_binding: PromptExtern) -> dict[str, str]:
    """Project one canonical prompt extern onto provider-step source fields."""

    return {prompt_binding.source_kind: prompt_binding.path}


def _prompt_source_replace_kwargs(prompt_binding: PromptExtern | None) -> dict[str, Any]:
    """Build dataclass replacement kwargs for provider prompt source fields."""

    if prompt_binding is None:
        return {}
    if prompt_binding.source_kind == "asset_file":
        return {"asset_file": prompt_binding.path, "input_file": None}
    return {"asset_file": None, "input_file": prompt_binding.path}


def _rewrite_prompt_source_mapping(
    payload: Mapping[str, Any],
    prompt_binding: PromptExtern | None,
) -> dict[str, Any]:
    """Rewrite a lowered step mapping to use the requested prompt source."""

    rewritten = dict(payload)
    if prompt_binding is None:
        return rewritten
    rewritten.pop("asset_file", None)
    rewritten.pop("input_file", None)
    rewritten.update(_prompt_source_step_fields(prompt_binding))
    return rewritten


@dataclass(frozen=True)
class LoweredWorkflow:
    """Boundary object between Workflow Lisp and the shared runtime pipeline.

    `typed_workflow` preserves the checked frontend definition, while
    `authored_mapping` is the ordinary workflow dictionary consumed by the
    existing loader, semantic IR builder, and executor. `origin_map` and
    `boundary_projection` keep that generated mapping explainable and connect
    frontend record/union fields to flattened workflow contracts.
    """

    typed_workflow: TypedWorkflowDef
    authored_mapping: Mapping[str, object]
    origin_map: LoweringOriginMap
    boundary_projection: WorkflowBoundaryProjection
    private_exec_context_bindings: tuple[PrivateExecContextBinding, ...] = ()
    compatibility_bridge_inputs: tuple[str, ...] = ()
    generated_path_allocations: tuple[GeneratedPathAllocation, ...] = ()
    private_artifact_ids: tuple[str, ...] = ()


def _origin_for_workflow(*args, **kwargs):
    return _origin_for_workflow_owner(*args, **kwargs)


def lower_workflow_definitions(
    typed_workflows: tuple[TypedWorkflowDef, ...],
    *,
    typed_procedures: tuple[TypedProcedureDef, ...] = (),
    procedure_catalog: ProcedureCatalog | None = None,
    workflow_path: Path,
    workflow_catalog: WorkflowCatalog,
    imported_workflow_bundles: Mapping[str, LoadedWorkflowBundle] | None = None,
    extern_environment: ExternEnvironment,
    command_boundary_environment: CommandBoundaryEnvironment,
    type_env: FrontendTypeEnvironment | None = None,
) -> tuple[LoweredWorkflow, ...]:
    """Lower typechecked frontend workflows into shared workflow dictionaries.

    This is the frontend's main lowering entrypoint. It first decides how each
    `defproc` lowers, synthesizes private workflow boundaries where needed,
    topologically lowers same-file workflow dependencies, and returns mappings
    that can be passed directly into the shared workflow validation pipeline.
    """

    typed_procedures_by_name = {procedure.definition.name: procedure for procedure in typed_procedures}
    from .procedures import _private_workflow_from_procedure, _resolve_procedure_lowering

    resolved_procedures = _resolve_procedure_lowering(
        typed_procedures,
        typed_workflows=typed_workflows,
        workflow_path=workflow_path,
        type_env=type_env or FrontendTypeEnvironment.from_module(_definition_only_module(workflow_path)),
    )
    private_workflows = {
        procedure.generated_workflow_name: _private_workflow_from_procedure(procedure)
        for procedure in resolved_procedures.values()
        if procedure.resolved_lowering_mode == ProcedureLoweringMode.PRIVATE_WORKFLOW
        and procedure.generated_workflow_name is not None
    }
    generated_private_workflow_names = frozenset(private_workflows)
    workflows_by_name: dict[str, TypedWorkflowDef] = {
        **{workflow.definition.name: workflow for workflow in typed_workflows},
        **private_workflows,
    }
    resolved_type_env = type_env or FrontendTypeEnvironment.from_module(_definition_only_module(workflow_path))
    lowered_by_name: dict[str, LoweredWorkflow] = {}
    visiting: set[str] = set()
    specialized_workflows: dict[tuple[str, tuple[tuple[str, str], ...]], TypedWorkflowDef] = {}

    def specialize_workflow(
        base_workflow_name: str,
        bindings: Mapping[str, ResolvedWorkflowRef],
    ) -> TypedWorkflowDef:
        key = (
            base_workflow_name,
            tuple(sorted((name, resolved.workflow_name) for name, resolved in bindings.items())),
        )
        existing = specialized_workflows.get(key)
        if existing is not None:
            return existing
        base = workflows_by_name[base_workflow_name]
        specialized_name = specialization_name(base.signature.name, bindings)
        specialized = TypedWorkflowDef(
            definition=WorkflowDef(
                name=specialized_name,
                params=tuple(param for param in base.definition.params if param.name not in bindings),
                return_type_name=base.definition.return_type_name,
                body=base.definition.body,
                span=base.definition.span,
                form_path=base.definition.form_path,
                expansion_stack=base.definition.expansion_stack,
            ),
            signature=WorkflowSignature(
                name=specialized_name,
                params=tuple((name, type_ref) for name, type_ref in base.signature.params if name not in bindings),
                return_type_ref=base.signature.return_type_ref,
                span=base.signature.span,
                form_path=base.signature.form_path,
                param_defaults={
                    name: default
                    for name, default in base.signature.param_defaults.items()
                    if name not in bindings
                },
                hidden_context_requirements=base.signature.hidden_context_requirements,
                hidden_context_ambiguities=base.signature.hidden_context_ambiguities,
                allow_hidden_context_binding=base.signature.allow_hidden_context_binding,
            ),
            typed_body=base.typed_body,
            effect_summary=base.effect_summary,
            specialization=WorkflowCallableSpecialization(
                base_name=base.signature.name,
                workflow_ref_bindings=dict(bindings),
                specialized_name=specialized_name,
            ),
        )
        workflows_by_name[specialized_name] = specialized
        specialized_workflows[key] = specialized
        return specialized

    def lower_one(workflow_name: str) -> LoweredWorkflow:
        """Lower one workflow after recursively lowering local callees."""

        existing = lowered_by_name.get(workflow_name)
        if existing is not None:
            return existing
        if workflow_name in visiting:
            workflow = workflows_by_name[workflow_name]
            cycle_code = (
                "workflow_ref_specialization_cycle"
                if workflow.specialization is not None
                or any(workflows_by_name[name].specialization is not None for name in visiting)
                else "workflow_signature_mismatch"
            )
            raise LispFrontendCompileError(
                (
                    LispFrontendDiagnostic(
                        code=cycle_code,
                        message=f"cyclic same-file workflow call detected for `{workflow_name}`",
                        span=workflow.definition.span,
                        form_path=workflow.definition.form_path,
                        phase="lowering",
                    ),
                )
            )
        visiting.add(workflow_name)
        typed_workflow = workflows_by_name[workflow_name]

        for dependency in _typed_workflow_dependencies(
            typed_workflow,
            typed_procedures=resolved_procedures,
            workflow_catalog=workflow_catalog,
        ):
            if dependency in workflows_by_name:
                lower_one(dependency)

        lowered = _lower_one_workflow(
            typed_workflow,
            workflow_path=workflow_path,
            generated_private_workflow_names=generated_private_workflow_names,
            workflow_catalog=workflow_catalog,
            imported_workflow_bundles=imported_workflow_bundles or {},
            extern_environment=extern_environment,
            command_boundary_environment=command_boundary_environment,
            lowered_callees=lowered_by_name,
            type_env=resolved_type_env,
            typed_procedures=resolved_procedures,
            workflows_by_name=workflows_by_name,
            ensure_workflow_lowered=lower_one,
            specialize_workflow=specialize_workflow,
        )
        lowered_by_name[workflow_name] = lowered
        visiting.remove(workflow_name)
        return lowered

    private_order = [name for name in private_workflows]
    for workflow_name in private_order:
        lower_one(workflow_name)

    ordered: list[LoweredWorkflow] = []
    included_names: set[str] = set()
    for workflow in typed_workflows:
        if any(isinstance(type_ref, WorkflowRefTypeRef) for _, type_ref in workflow.signature.params):
            continue
        lowered = lower_one(workflow.definition.name)
        ordered.append(lowered)
        included_names.add(lowered.typed_workflow.definition.name)
    for workflow_name in private_order:
        ordered.append(lowered_by_name[workflow_name])
        included_names.add(workflow_name)
    for workflow_name, lowered in lowered_by_name.items():
        if workflow_name not in included_names:
            ordered.append(lowered)
    return tuple(ordered)


def validate_lowered_workflows(
    lowered_workflows: tuple[LoweredWorkflow, ...],
    *,
    workspace_root: Path,
    imported_workflow_bundles: Mapping[str, LoadedWorkflowBundle] | None = None,
) -> Mapping[str, LoadedWorkflowBundle]:
    """Run lowered workflow dictionaries through the existing validation path.

    Lowering is not allowed to be authoritative by itself. This function feeds
    generated mappings into the same loader/elaboration/lowering path used by
    authored YAML and remaps shared validation failures back through
    `LoweringOriginMap`.
    """

    lowered_by_name = {workflow.typed_workflow.definition.name: workflow for workflow in lowered_workflows}
    imported_names = {
        dependency
        for workflow in lowered_workflows
        for dependency in _lowered_workflow_dependencies(workflow)
        if dependency in lowered_by_name
    }
    validated: dict[str, LoadedWorkflowBundle] = {}
    visiting: set[str] = set()

    def validate_one(workflow_name: str) -> LoadedWorkflowBundle:
        """Validate one lowered workflow after validating local dependencies."""

        existing = validated.get(workflow_name)
        if existing is not None:
            return existing
        if workflow_name in visiting:
            lowered = lowered_by_name[workflow_name]
            raise _compile_error(
                code="workflow_signature_mismatch",
                message=f"cyclic same-file workflow call detected for `{workflow_name}`",
                span=lowered.origin_map.workflow_span,
                form_path=lowered.typed_workflow.definition.form_path,
            )
        visiting.add(workflow_name)
        lowered = lowered_by_name[workflow_name]
        imported_bundles = dict(imported_workflow_bundles or {})
        imported_bundles.update(
            {
                dependency: validate_one(dependency)
                for dependency in _lowered_workflow_dependencies(lowered)
                if dependency in lowered_by_name
            }
        )
        bundle = _validate_one_lowered_workflow(
            lowered,
            workspace_root=workspace_root,
            imported_bundles=imported_bundles,
            workflow_is_imported=workflow_name in imported_names,
        )
        validated[workflow_name] = bundle
        visiting.remove(workflow_name)
        return bundle

    for workflow in lowered_workflows:
        validate_one(workflow.typed_workflow.definition.name)
    return MappingProxyType(dict(validated))


def _lower_one_workflow(
    typed_workflow: TypedWorkflowDef,
    *,
    workflow_path: Path,
    generated_private_workflow_names: frozenset[str],
    workflow_catalog: WorkflowCatalog,
    imported_workflow_bundles: Mapping[str, LoadedWorkflowBundle],
    extern_environment: ExternEnvironment,
    command_boundary_environment: CommandBoundaryEnvironment,
    lowered_callees: Mapping[str, LoweredWorkflow],
    type_env: FrontendTypeEnvironment,
    typed_procedures: Mapping[str, TypedProcedureDef],
    workflows_by_name: Mapping[str, TypedWorkflowDef],
    ensure_workflow_lowered: Any,
    specialize_workflow: Any,
) -> LoweredWorkflow:
    """Lower one typed workflow body and assemble its shared mapping.

    The function derives flattened boundary contracts, creates the mutable
    lowering context used by expression visitors, collects hidden managed-write
    inputs, verifies source-map coverage, and returns the final `LoweredWorkflow`
    object consumed by shared validation.
    """

    inputs, outputs, boundary_projection = derive_workflow_signature_contracts(typed_workflow.signature)
    authored_inputs = {name: dict(contract.definition) for name, contract in inputs.items()}
    authored_outputs = {name: dict(contract.definition) for name, contract in outputs.items()}
    is_generated_private_workflow = typed_workflow.definition.name in generated_private_workflow_names
    if isinstance(typed_workflow.signature.return_type_ref, UnionTypeRef) and is_generated_private_workflow:
        for definition in authored_outputs.values():
            if isinstance(definition, dict) and definition.get("type") == "relpath":
                definition["must_exist_target"] = False
    workflow_origin = _origin_for_workflow(typed_workflow, typed_procedures=typed_procedures)
    origin_inputs = {name: workflow_origin for name in authored_inputs}
    origin_outputs = {name: workflow_origin for name in authored_outputs}

    context = _LoweringContext(
        workflow_name=typed_workflow.definition.name,
        step_name_prefix=typed_workflow.definition.name,
        workflow_path=workflow_path,
        signature=typed_workflow.signature,
        authored_input_contracts=MappingProxyType({name: dict(definition) for name, definition in authored_inputs.items()}),
        workflow_catalog=workflow_catalog,
        imported_workflow_bundles=imported_workflow_bundles,
        extern_environment=extern_environment,
        command_boundary_environment=command_boundary_environment,
        lowered_callees=lowered_callees,
        typed_procedures=typed_procedures,
        workflows_by_name=workflows_by_name,
        ensure_workflow_lowered=ensure_workflow_lowered,
        specialize_workflow=specialize_workflow,
        type_env=type_env,
        step_spans={},
        generated_input_spans=origin_inputs,
        authored_generated_inputs=set(authored_inputs),
        internal_generated_input_reasons={},
        internal_generated_input_contracts={},
        private_exec_context_bindings=[],
        generated_output_spans=origin_outputs,
        generated_path_spans={},
        generated_path_allocations=[],
        generated_semantic_effects=[],
        output_projection_metadata={},
        top_level_artifacts={},
        inline_call_counters={},
        origin_notes=workflow_origin.notes,
        boundary_projection=boundary_projection,
        return_output_contracts=MappingProxyType(
            {
                name.removeprefix("return__"): dict(definition)
                for name, definition in authored_outputs.items()
            }
        ),
        local_type_bindings={name: type_ref for name, type_ref in typed_workflow.signature.params},
        is_generated_private_workflow=is_generated_private_workflow,
    )
    local_values = _signature_local_values(typed_workflow)
    steps, terminal = _lower_expression(typed_workflow.typed_body, context=context, local_values=local_values)
    steps, terminal = _normalize_top_level_terminal(
        typed_workflow=typed_workflow,
        authored_outputs=authored_outputs,
        steps=steps,
        terminal=terminal,
        context=context,
    )

    if context.origin_notes:
        noted_origin = LoweringOrigin(
            span=workflow_origin.span,
            form_path=workflow_origin.form_path,
            expansion_stack=workflow_origin.expansion_stack,
            notes=context.origin_notes,
        )
        for key in list(context.generated_input_spans):
            if context.generated_input_spans[key] == workflow_origin:
                context.generated_input_spans[key] = noted_origin
        for key in list(context.generated_output_spans):
            if context.generated_output_spans[key] == workflow_origin:
                context.generated_output_spans[key] = noted_origin

    for hidden_input_name, origin in terminal.hidden_inputs.items():
        authored_inputs[hidden_input_name] = {
            "kind": "relpath",
            "type": "relpath",
        }
        context.generated_input_spans[hidden_input_name] = origin
        context.internal_generated_input_reasons.setdefault(hidden_input_name, "managed_write_root")
    for allocation in context.generated_path_allocations:
        hidden_input_name = allocation.generated_input_name
        reason = allocation_reason(allocation)
        if not isinstance(hidden_input_name, str) or reason is None:
            continue
        authored_inputs.setdefault(
            hidden_input_name,
            {
                "kind": "relpath",
                "type": "relpath",
            },
        )
        origin = context.generated_path_spans.get(allocation.concrete_path_template)
        if origin is not None:
            context.generated_input_spans.setdefault(hidden_input_name, origin)
        context.internal_generated_input_reasons.setdefault(hidden_input_name, reason)
    for hidden_input_name, contract_definition in context.internal_generated_input_contracts.items():
        authored_inputs[hidden_input_name] = dict(contract_definition)

    phase_family_classification = apply_phase_family_boundary_classification(
        workflow_name=typed_workflow.definition.name,
        params=typed_workflow.signature.params,
        boundary_projection=context.boundary_projection,
        context=context,
    )
    record_direct_entry_phase_context_binding(
        context=context,
        typed_workflow=typed_workflow,
        generated_input_names=phase_family_classification.runtime_owned_context_inputs,
    )

    base_allocations = tuple(context.generated_path_allocations)
    for derived_allocation in derive_entrypoint_managed_write_root_allocations(base_allocations):
        source_allocation_id = derived_allocation.projection_hints.get("source_allocation_id")
        source_origin = next(
            (
                context.generated_path_spans.get(allocation.concrete_path_template)
                for allocation in base_allocations
                if allocation.allocation_id == source_allocation_id
            ),
            None,
        )
        context.generated_path_allocations.append(derived_allocation)
        if source_origin is not None:
            context.generated_path_spans.setdefault(
                derived_allocation.concrete_path_template,
                source_origin,
            )

    authored_input_spans = {
        name: origin
        for name, origin in context.generated_input_spans.items()
        if name in context.authored_generated_inputs
    }
    internal_input_spans = {
        name: origin
        for name, origin in context.generated_input_spans.items()
        if name in context.internal_generated_input_reasons
    }
    finalized_projection = replace(
        context.boundary_projection,
        generated_internal_inputs=tuple(
            GeneratedInternalInput(generated_name=name, reason=reason)
            for name, reason in sorted(context.internal_generated_input_reasons.items())
        ),
    )
    _validate_projection_origin_coverage(
        workflow_name=typed_workflow.definition.name,
        boundary_projection=finalized_projection,
        authored_input_spans=authored_input_spans,
        internal_input_spans=internal_input_spans,
        generated_output_spans=context.generated_output_spans,
        span=typed_workflow.definition.span,
        form_path=typed_workflow.definition.form_path,
    )

    authored_mapping: dict[str, object] = {
        "version": "2.14",
        "name": typed_workflow.definition.name,
        "inputs": authored_inputs,
        "outputs": _lower_workflow_outputs(
            typed_workflow=typed_workflow,
            authored_outputs=authored_outputs,
            terminal=terminal,
            context=context,
        ),
        "steps": steps,
    }
    if context.top_level_artifacts:
        authored_mapping["artifacts"] = dict(context.top_level_artifacts)

    generated_semantic_effects = _derive_generated_semantic_effects(
        authored_mapping.get("steps"),
        context=context,
        workflow_origin=workflow_origin,
    )

    return LoweredWorkflow(
        typed_workflow=typed_workflow,
        authored_mapping=authored_mapping,
        origin_map=LoweringOriginMap(
            workflow_name=typed_workflow.definition.name,
            workflow_origin=_with_origin_key(
                LoweringOrigin(
                    span=workflow_origin.span,
                    form_path=workflow_origin.form_path,
                    expansion_stack=workflow_origin.expansion_stack,
                    notes=context.origin_notes or workflow_origin.notes,
                ),
                workflow_name=typed_workflow.definition.name,
                entity_kind="workflow",
                subject_name=typed_workflow.definition.name,
            ),
            step_spans=MappingProxyType(
                _origins_with_keys(
                    context.step_spans,
                    workflow_name=typed_workflow.definition.name,
                    entity_kind="step_id",
                )
            ),
            authored_input_spans=MappingProxyType(
                _origins_with_keys(
                    authored_input_spans,
                    workflow_name=typed_workflow.definition.name,
                    entity_kind="generated_input",
                )
            ),
            internal_input_spans=MappingProxyType(
                _origins_with_keys(
                    internal_input_spans,
                    workflow_name=typed_workflow.definition.name,
                    entity_kind="generated_internal_input",
                )
            ),
            generated_output_spans=MappingProxyType(
                _origins_with_keys(
                    context.generated_output_spans,
                    workflow_name=typed_workflow.definition.name,
                    entity_kind="generated_output",
                )
            ),
            generated_path_spans=MappingProxyType(
                _origins_with_keys(
                    context.generated_path_spans,
                    workflow_name=typed_workflow.definition.name,
                    entity_kind="generated_path",
                )
            ),
            validation_subject_bindings=_build_validation_subject_bindings(
                workflow_name=typed_workflow.definition.name,
                workflow_origin=_with_origin_key(
                    LoweringOrigin(
                        span=workflow_origin.span,
                        form_path=workflow_origin.form_path,
                        expansion_stack=workflow_origin.expansion_stack,
                        notes=context.origin_notes or workflow_origin.notes,
                    ),
                    workflow_name=typed_workflow.definition.name,
                    entity_kind="workflow",
                    subject_name=typed_workflow.definition.name,
                ),
                step_spans=_origins_with_keys(
                    context.step_spans,
                    workflow_name=typed_workflow.definition.name,
                    entity_kind="step_id",
                ),
                generated_inputs={
                    **_origins_with_keys(
                        authored_input_spans,
                        workflow_name=typed_workflow.definition.name,
                        entity_kind="generated_input",
                    ),
                    **_origins_with_keys(
                        internal_input_spans,
                        workflow_name=typed_workflow.definition.name,
                        entity_kind="generated_internal_input",
                    ),
                },
                generated_outputs=_origins_with_keys(
                    context.generated_output_spans,
                    workflow_name=typed_workflow.definition.name,
                    entity_kind="generated_output",
                ),
                generated_paths=_origins_with_keys(
                    context.generated_path_spans,
                    workflow_name=typed_workflow.definition.name,
                    entity_kind="generated_path",
                ),
            ),
            generated_semantic_effects=generated_semantic_effects,
        ),
        boundary_projection=finalized_projection,
        private_exec_context_bindings=tuple(context.private_exec_context_bindings),
        compatibility_bridge_inputs=tuple(
            name
            for name, reason in sorted(context.internal_generated_input_reasons.items())
            if reason == "compatibility_bridge"
        ),
        generated_path_allocations=tuple(context.generated_path_allocations),
        private_artifact_ids=tuple(
            name
            for name, definition in context.top_level_artifacts.items()
            if isinstance(name, str)
            and isinstance(definition, Mapping)
            and definition.get("kind") == "collection"
        ),
    )


def _validate_projection_origin_coverage(
    *,
    workflow_name: str,
    boundary_projection: WorkflowBoundaryProjection,
    authored_input_spans: Mapping[str, LoweringOrigin],
    internal_input_spans: Mapping[str, LoweringOrigin],
    generated_output_spans: Mapping[str, LoweringOrigin],
    span: SourceSpan,
    form_path: tuple[str, ...],
) -> None:
    """Ensure every flattened boundary field has a source-map origin.

    Missing origins make diagnostics and build artifacts misleading, so lowering
    fails before exposing a workflow whose generated inputs or outputs cannot be
    traced back to frontend source.
    """

    internal_input_names = {
        item.generated_name for item in boundary_projection.generated_internal_inputs
    }
    missing = next(
        (
            field.generated_name
            for field in boundary_projection.flattened_inputs
            if field.generated_name not in authored_input_spans
            and not (
                field.generated_name in internal_input_names
                and field.generated_name in internal_input_spans
            )
        ),
        None,
    )
    if missing is None:
        missing = next(
            (
                field.generated_name
                for field in boundary_projection.flattened_outputs
                if field.generated_name not in generated_output_spans
            ),
            None,
        )
    if missing is None:
        missing = next(
            (
                field.generated_name
                for field in boundary_projection.generated_internal_inputs
                if field.generated_name not in internal_input_spans
            ),
            None,
        )
    if missing is None:
        return
    raise LispFrontendCompileError(
        (
            LispFrontendDiagnostic(
                code="workflow_boundary_projection_missing_origin",
                message=f"workflow boundary projection origin missing for `{workflow_name}` field `{missing}`",
                span=span,
                form_path=form_path,
            ),
        )
    )


def _normalize_generated_step_id(raw_name: str) -> str:
    """Convert generated step names into stable shared-workflow step ids."""

    normalized = _GENERATED_STEP_ID_RE.sub("_", raw_name).strip("_")
    if not normalized:
        return "generated_step"
    if not normalized[0].isalpha():
        normalized = f"S_{normalized}"
    return normalized


def _normalize_top_level_terminal(
    *,
    typed_workflow: TypedWorkflowDef,
    authored_outputs: Mapping[str, dict[str, Any]],
    steps: list[dict[str, Any]],
    terminal: _TerminalResult,
    context: _LoweringContext,
) -> tuple[list[dict[str, Any]], _TerminalResult]:
    """Ensure public workflow outputs lower from a concrete root step."""

    if terminal.output_kind == "projection":
        return steps, terminal

    if all(
        isinstance(source_ref, str) and source_ref.startswith("root.steps.")
        for source_ref in terminal.output_refs.values()
    ):
        return steps, terminal

    step_name = f"{typed_workflow.definition.name}__return"
    step_id = _normalize_generated_step_id(step_name)
    values = []
    output_refs: dict[str, str] = {}
    for output_name, definition in authored_outputs.items():
        source_ref = terminal.output_refs.get(output_name)
        if not isinstance(source_ref, str):
            field_name = output_name.removeprefix("return__")
            raise _compile_error(
                code="workflow_return_not_exportable",
                message=f"workflow `{typed_workflow.definition.name}` cannot export return field `{field_name}`",
                span=typed_workflow.definition.body.span,
                form_path=typed_workflow.definition.body.form_path,
            )
        values.append(
            {
                "name": output_name,
                "source": {"ref": source_ref},
                "contract": dict(definition),
            }
        )
        output_refs[output_name] = f"root.steps.{step_name}.artifacts.{output_name}"
    _record_step_origin(
        context,
        step_name=step_name,
        step_id=step_id,
        source=typed_workflow.typed_body.expr,
    )
    return [
        *steps,
        _materialize_values_step(
            step_name=step_name,
            step_id=step_id,
            values=values,
        ),
    ], _TerminalResult(
        step_name=step_name,
        step_id=step_id,
        output_refs=output_refs,
        output_kind="step",
        hidden_inputs=terminal.hidden_inputs,
    )


def _observed_statement_families(steps: Sequence[Mapping[str, Any]]) -> tuple[str, ...]:
    """Summarize lowered steps into the reviewed stdlib family vocabulary."""

    observed: set[str] = set()

    def _visit(nested_steps: Sequence[Mapping[str, Any]]) -> None:
        for step in nested_steps:
            if "provider" in step:
                observed.add("provider_step")
            if "command" in step:
                observed.add("command_step")
            if "output_bundle" in step:
                observed.add("output_bundle")
            if "variant_output" in step:
                observed.add("variant_output")
            if "pre_snapshot" in step:
                observed.add("pre_snapshot")
            if "select_variant_output" in step:
                observed.add("select_variant_output")
            if "repeat_until" in step:
                observed.add("repeat_until")
            if "match" in step:
                observed.add("match")
            if "materialize_artifacts" in step:
                observed.add("materialize_artifacts")
            if "pure_projection" in step:
                observed.add("pure_projection")
            if "call" in step:
                observed.add("workflow_call")
            if step.get("publishes"):
                observed.add("publishes")

            match_block = step.get("match")
            if isinstance(match_block, Mapping):
                cases = match_block.get("cases")
                if isinstance(cases, Mapping):
                    for case in cases.values():
                        if isinstance(case, Mapping):
                            case_steps = case.get("steps")
                            if isinstance(case_steps, Sequence):
                                _visit(case_steps)
            repeat_block = step.get("repeat_until")
            if isinstance(repeat_block, Mapping):
                nested = repeat_block.get("steps")
                if isinstance(nested, Sequence):
                    _visit(nested)

    _visit(steps)
    ordered_tokens = (
        "provider_step",
        "command_step",
        "output_bundle",
        "variant_output",
        "pre_snapshot",
        "select_variant_output",
        "repeat_until",
        "match",
        "materialize_artifacts",
        "pure_projection",
        "workflow_call",
        "publishes",
    )
    return tuple(token for token in ordered_tokens if token in observed)



















































def _output_contracts_for_type(
    type_ref: Any,
    *,
    context: _LoweringContext,
    span: SourceSpan,
    form_path: tuple[str, ...],
) -> dict[str, dict[str, Any]]:
    """Flatten one return-like type into shared output contracts."""

    if isinstance(type_ref, UnionTypeRef):
        return {
            f"return__{output_name}": definition
            for output_name, definition in _union_output_contracts(
                type_ref,
                payload=derive_structured_result_contract(
                    type_ref,
                    workflow_name=context.workflow_name,
                    step_id=context.step_name_prefix,
                    span=span,
                    form_path=form_path,
                ).payload,
                span=span,
                form_path=form_path,
            ).items()
        }
    return {
        field.generated_name: dict(field.contract_definition)
        for field in derive_workflow_boundary_fields(
            type_ref,
            generated_name="return",
            source_path=("return",),
            span=span,
            form_path=form_path,
        )
    }


def _lower_conditional_branch_expr(
    expr: Any,
    *,
    result_type: TypeRef,
    step_name: str,
    context: _LoweringContext,
    local_values: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], _TerminalResult]:
    """Lower one `if` branch, preserving direct refs when possible."""

    output_refs = _inline_output_refs_for_expr(
        expr,
        type_ref=result_type,
        local_values=local_values,
        context=context,
    )
    if output_refs is not None:
        return [], _TerminalResult(
            step_name=step_name,
            step_id=_normalize_generated_step_id(step_name),
            output_refs=output_refs,
            output_kind="projection",
            hidden_inputs={},
        )
    return _lower_expression(
        TypedExpr(
            expr=expr,
            type_ref=result_type,
            span=expr.span,
            form_path=expr.form_path,
        ),
        context=_copy_context_with_step_prefix(context, step_name_prefix=step_name),
        local_values=local_values,
    )


def _inline_output_refs_for_expr(
    expr: Any,
    *,
    type_ref: TypeRef,
    local_values: Mapping[str, Any],
    context: _LoweringContext,
) -> dict[str, str] | None:
    """Resolve direct branch output refs without synthesizing a child step."""

    output_refs: dict[str, str] = {}
    for field in derive_workflow_boundary_fields(
        type_ref,
        generated_name="return",
        source_path=("return",),
        span=expr.span,
        form_path=expr.form_path,
    ):
        leaf_value = _inline_expr_field_value(
            expr,
            field_path=field.source_path[1:],
            local_values=local_values,
            context=context,
        )
        if not isinstance(leaf_value, str):
            return None
        output_refs[field.generated_name] = leaf_value
    return output_refs


def _conditional_case_outputs(
    terminal: _TerminalResult,
    *,
    output_contracts: Mapping[str, Mapping[str, Any]],
    span: SourceSpan,
    form_path: tuple[str, ...],
) -> dict[str, Any]:
    """Project one branch terminal into conditional branch outputs."""

    outputs: dict[str, Any] = {}
    for output_name, contract_definition in output_contracts.items():
        output_ref = terminal.output_refs.get(output_name)
        if output_ref is None and not output_name.startswith("return__"):
            output_ref = terminal.output_refs.get(f"return__{output_name}")
        if not isinstance(output_ref, str):
            raise _compile_error(
                code="workflow_return_not_exportable",
                message=f"conditional branch did not expose projected output `{output_name}`",
                span=span,
                form_path=form_path,
            )
        outputs[output_name] = {
            **dict(contract_definition),
            "from": {"ref": _conditional_case_ref(output_ref, terminal_step_name=terminal.step_name)},
        }
    return outputs


def _conditional_output_refs(
    *,
    step_name: str,
    output_contracts: Mapping[str, Mapping[str, Any]],
    result_type: TypeRef,
) -> dict[str, str]:
    """Build conditional terminal refs, preserving workflow-boundary union names."""

    output_refs = {
        output_name: f"root.steps.{step_name}.artifacts.{output_name}"
        for output_name in output_contracts
    }
    if isinstance(result_type, UnionTypeRef):
        output_refs.update(
            {
                output_name.removeprefix("return__"): ref
                for output_name, ref in output_refs.items()
                if output_name.startswith("return__")
            }
        )
    return output_refs



def _template_for_ref(ref: str) -> str:
    """Wrap a shared ref in substitution syntax when a YAML field needs it."""

    if ref.startswith("${"):
        return ref
    return "${" + ref + "}"


def _resolve_active_phase_scope(
    expr: WithPhaseExpr,
    *,
    local_values: Mapping[str, Any],
) -> _ActivePhaseScope:
    """Resolve derived phase paths and targets for a `with-phase` body."""

    context_value = _resolve_inline_expr_value(expr.ctx_expr, local_values=local_values)
    if not isinstance(context_value, Mapping):
        raise _compile_error(
            code="phase_translation_body_invalid",
            message="`with-phase` lowering requires the phase context to resolve from workflow inputs",
            span=expr.ctx_expr.span,
            form_path=expr.ctx_expr.form_path,
        )
    if "implementation_state_bundle_path" not in context_value:
        state_root_ref = context_value.get("state-root")
        artifact_root_ref = context_value.get("artifact-root")
        runtime_phase_name_ref = context_value.get("phase-name")
        if not isinstance(state_root_ref, str) or not isinstance(artifact_root_ref, str):
            raise _compile_error(
                code="phase_translation_body_invalid",
                message="`with-phase` lowering requires generic phase roots to resolve from workflow inputs",
                span=expr.ctx_expr.span,
                form_path=expr.ctx_expr.form_path,
            )
        target_refs = {
            target_name: _join_ref_path(artifact_root_ref, f"{expr.phase_name}/{suffix}")
            for target_name, (_, _, suffix) in PHASE_TARGET_SPECS.items()
        }
        return _ActivePhaseScope(
            scope=PhaseScope(
                context_record_name="PhaseCtx",
                phase_name=expr.phase_name,
                target_types={},
            ),
            bundle_path_ref=_join_ref_path(state_root_ref, f"phases/{expr.phase_name}/state.json"),
            temp_bundle_path_ref=_join_ref_path(state_root_ref, f"phases/{expr.phase_name}/state.tmp.json"),
            snapshot_root_ref=_join_ref_path(state_root_ref, f"phases/{expr.phase_name}/snapshots"),
            candidate_root_ref=_join_ref_path(state_root_ref, f"phases/{expr.phase_name}/candidates"),
            target_refs=target_refs,
            runtime_phase_name_ref=runtime_phase_name_ref if isinstance(runtime_phase_name_ref, str) else None,
        )
    if expr.phase_name != IMPLEMENTATION_ATTEMPT_PHASE_NAME:
        raise _compile_error(
            code="phase_context_invalid",
            message="`with-phase` supports only the `implementation` phase in the legacy bridge",
            span=expr.span,
            form_path=expr.form_path,
        )
    bundle_ref = context_value.get("implementation_state_bundle_path")
    execution_ref = context_value.get("execution_report_target")
    progress_ref = context_value.get("progress_report_target")
    if not all(isinstance(ref, str) for ref in (bundle_ref, execution_ref, progress_ref)):
        raise _compile_error(
            code="phase_translation_body_invalid",
            message="`with-phase` lowering requires bound relpath fields on the phase context",
            span=expr.ctx_expr.span,
            form_path=expr.ctx_expr.form_path,
        )
    return _ActivePhaseScope(
        scope=PhaseScope(
            context_record_name="ImplementationAttemptPhaseCtx",
            phase_name=expr.phase_name,
            bundle_path_field="implementation_state_bundle_path",
            target_fields={
                "execution-report": "execution_report_target",
                "progress-report": "progress_report_target",
            },
        ),
        bundle_path_ref=bundle_ref,
        target_refs={
            "execution-report": execution_ref,
            "progress-report": progress_ref,
        },
    )


def _infer_inline_binding_type(expr: Any, *, context: _LoweringContext) -> TypeRef | None:
    """Infer a simple inline binding type when no typed lowering result exists."""

    if isinstance(expr, NameExpr):
        return context.local_type_bindings.get(expr.name)
    if isinstance(expr, FieldAccessExpr):
        return _resolve_lowering_expr_type(expr, context=context)
    if isinstance(expr, LiteralExpr):
        if expr.literal_kind == "string":
            return PrimitiveTypeRef(name="String")
        if expr.literal_kind == "int":
            return PrimitiveTypeRef(name="Int")
        if expr.literal_kind == "bool":
            return PrimitiveTypeRef(name="Bool")
        return None
    if isinstance(expr, ProcRefLiteralExpr):
        resolved = _resolved_proc_ref_value(expr, context=context, local_values={})
        return None if resolved is None else resolved.residual_type_ref
    if isinstance(expr, BindProcExpr):
        resolved = _resolved_proc_ref_value(expr, context=context, local_values={})
        return None if resolved is None else resolved.residual_type_ref
    if isinstance(expr, RecordExpr):
        return context.type_env.resolve_type(
            expr.type_name,
            span=expr.span,
            form_path=expr.form_path,
        )
    if isinstance(expr, RecordUpdateExpr):
        return _resolve_lowering_expr_type(expr.base_expr, context=context)
    if isinstance(expr, PureOpExpr):
        return _resolve_pure_op_type(expr, context=context)
    if isinstance(expr, IfExpr):
        return _resolve_lowering_expr_type(expr, context=context)
    if isinstance(expr, ProviderBundlePathExpr):
        return context.type_env.resolve_type(
            expr.target_type_name,
            span=expr.span,
            form_path=expr.form_path,
        )
    return None


def _record_field_value(record_expr: RecordExpr, field_name: str) -> Any:
    """Return one field expression from a frontend record literal."""

    for name, value in record_expr.fields:
        if name == field_name:
            return value
    raise _compile_error(
        code="workflow_return_not_exportable",
        message=f"record return field `{field_name}` is missing from the lowered workflow return expression",
        span=record_expr.span,
        form_path=record_expr.form_path,
    )


def _binding_type_for_expr(expr: Any, *, context: _LoweringContext) -> TypeRef:
    """Infer the type of an effectful `let*` binding for later lowering."""

    if isinstance(expr, WithPhaseExpr):
        binding_type = _resolve_lowering_expr_type(expr, context=context)
        if binding_type is not None:
            return binding_type
        raise _compile_error(
            code="workflow_return_not_exportable",
            message="composed `with-phase` body is not exportable in this Stage 3 slice",
            span=expr.body.span,
            form_path=expr.body.form_path,
        )
    binding_type = _resolve_lowering_expr_type(expr, context=context)
    if binding_type is not None:
        return binding_type
    raise _compile_error(
        code="workflow_return_not_exportable",
        message=f"Stage 3 lowering does not support let* binding `{type(expr).__name__}`",
        span=expr.span,
        form_path=expr.form_path,
    )


def _resolve_lowering_expr_type(expr: Any, *, context: _LoweringContext) -> TypeRef | None:
    """Resolve the type of a lowering-time local expression."""

    if isinstance(expr, NameExpr):
        return context.local_type_bindings.get(expr.name)
    if isinstance(expr, FieldAccessExpr):
        current_type = context.local_type_bindings.get(expr.base.name)
        for field_name in expr.fields:
            if not isinstance(current_type, RecordTypeRef):
                return None
            current_type = context.type_env.record_field(
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
        return context.type_env.resolve_type(
            expr.type_name,
            span=expr.span,
            form_path=expr.form_path,
        )
    if isinstance(expr, RecordUpdateExpr):
        return _resolve_lowering_expr_type(expr.base_expr, context=context)
    if isinstance(expr, LoopStateSeedExpr):
        from ..loop_state import carrier_metadata_for_expr

        metadata = carrier_metadata_for_expr(expr)
        if metadata is None:
            return None
        return context.type_env.resolve_type(
            metadata.generated_type_name,
            span=expr.span,
            form_path=expr.form_path,
        )
    if isinstance(expr, LoopStateUpdateExpr):
        base_type = _resolve_lowering_expr_type(expr.base_expr, context=context)
        if base_type is None:
            return None
        from ..loop_state import carrier_metadata_for_type

        return base_type if carrier_metadata_for_type(base_type) is not None else None
    if isinstance(expr, UnionVariantExpr):
        return context.type_env.resolve_type(
            expr.type_name,
            span=expr.span,
            form_path=expr.form_path,
        )
    if isinstance(expr, PureOpExpr):
        return _resolve_pure_op_type(expr, context=context)
    if isinstance(expr, ProviderBundlePathExpr):
        return context.type_env.resolve_type(
            expr.target_type_name,
            span=expr.span,
            form_path=expr.form_path,
        )
    # schema1_compatibility: legacy lowering type inference for covered structured effects.
    if isinstance(
        expr,
        (
            ProviderResultExpr,
            CommandResultExpr,
            RunProviderPhaseExpr,
            ProduceOneOfExpr,
            ResumeOrStartExpr,
        ),
    ):
        return context.type_env.resolve_type(
            expr.returns_type_name,
            span=expr.span,
            form_path=expr.form_path,
        )
    if isinstance(expr, ResourceTransitionExpr):
        return context.type_env.resolve_type(
            "ResourceTransitionResult",
            span=expr.span,
            form_path=expr.form_path,
        )
    if isinstance(expr, FinalizeSelectedItemExpr):
        return context.type_env.resolve_type(
            "SelectedItemResult",
            span=expr.span,
            form_path=expr.form_path,
        )
    if isinstance(expr, BacklogDrainExpr):
        return context.type_env.resolve_type(
            "DrainResult",
            span=expr.span,
            form_path=expr.form_path,
        )
    if isinstance(expr, DoneExpr):
        return _resolve_lowering_expr_type(expr.result_expr, context=context)
    if isinstance(expr, CallExpr):
        callee = context.lowered_callees.get(expr.callee_name)
        if callee is not None:
            return callee.typed_workflow.signature.return_type_ref
        signature = context.workflow_catalog.signatures_by_name.get(expr.callee_name)
        if signature is not None:
            return signature.return_type_ref
        raise _compile_error(
            code="workflow_call_unknown",
            message=f"unknown workflow callee `{expr.callee_name}` during lowering",
            span=expr.span,
            form_path=expr.form_path,
        )
    if isinstance(expr, ProcedureCallExpr):
        proc_ref_type = context.local_type_bindings.get(expr.callee_name)
        if isinstance(proc_ref_type, ProcRefTypeRef):
            return proc_ref_type.return_type_ref
        procedure = context.typed_procedures.get(expr.callee_name)
        if procedure is None:
            raise _compile_error(
                code="procedure_call_unknown",
                message=f"unknown procedure callee `{expr.callee_name}` during lowering",
                span=expr.span,
                form_path=expr.form_path,
            )
        return procedure.signature.return_type_ref
    # schema1_compatibility: legacy lowering type inference for covered match forms.
    if isinstance(expr, MatchExpr):
        arm_types = [
            _resolve_lowering_expr_type(
                arm.body,
                context=_context_with_local_type_binding(
                    context,
                    binding_name=arm.binding_name,
                    binding_type=_match_arm_binding_type(expr.subject, arm.variant_name, context=context),
                ),
            )
            for arm in expr.arms
        ]
        if arm_types and all(arm_type == arm_types[0] for arm_type in arm_types):
            return arm_types[0]
        return None
    if isinstance(expr, IfExpr):
        then_type = _resolve_lowering_expr_type(expr.then_expr, context=context)
        else_type = _resolve_lowering_expr_type(expr.else_expr, context=context)
        if then_type is not None and then_type == else_type:
            return then_type
        return None
    if isinstance(expr, LetStarExpr):
        binding_name, binding_expr = expr.bindings[0]
        body_expr: Any = expr.body
        if len(expr.bindings) > 1:
            body_expr = LetStarExpr(
                bindings=expr.bindings[1:],
                body=expr.body,
                span=expr.span,
                form_path=expr.form_path,
                expansion_stack=expr.expansion_stack,
            )
        binding_type = _resolve_lowering_expr_type(binding_expr, context=context)
        if binding_type is None:
            binding_type = _infer_inline_binding_type(binding_expr, context=context)
        if binding_type is None:
            return None
        return _resolve_lowering_expr_type(
            body_expr,
            context=_context_with_local_type_binding(
                context,
                binding_name=binding_name,
                binding_type=binding_type,
            ),
        )
    # schema1_compatibility: legacy lowering type inference for covered loop forms.
    if isinstance(expr, LoopRecurExpr):
        state_type = _resolve_lowering_expr_type(expr.initial_state_expr, context=context)
        if state_type is None:
            return None
        loop_context = _context_with_local_type_binding(
            context,
            binding_name=expr.binding_name,
            binding_type=state_type,
        )
        if expr.on_exhausted_result_expr is not None:
            exhausted_type = _resolve_lowering_expr_type(
                expr.on_exhausted_result_expr,
                context=loop_context,
            )
            if exhausted_type is not None:
                return exhausted_type
        return _resolve_lowering_expr_type(
            expr.body_expr,
            context=loop_context,
        )
    if isinstance(expr, WithPhaseExpr):
        return _resolve_lowering_expr_type(expr.body, context=context)
    return None


def _resolve_pure_op_type(expr: PureOpExpr, *, context: _LoweringContext) -> TypeRef | None:
    arg_types = [
        _resolve_lowering_expr_type(arg, context=context)
        or _infer_inline_binding_type(arg, context=context)
        for arg in expr.args
    ]
    if any(arg_type is None for arg_type in arg_types):
        return None
    resolved_arg_types = [arg_type for arg_type in arg_types if arg_type is not None]
    operator = expr.operator
    if operator in {"=", "!=", "<", "<=", ">", ">=", "and", "or", "not", "some?", "string/empty?"}:
        return PrimitiveTypeRef(name="Bool")
    if operator in {"+", "-", "*", "min", "max"}:
        return resolved_arg_types[0]
    if operator == "or-else":
        if len(resolved_arg_types) != 2:
            return None
        first = resolved_arg_types[0]
        if isinstance(first, OptionalTypeRef):
            return first.item_type_ref
        return resolved_arg_types[1]
    if operator in {"string/concat", "symbol/name"}:
        return PrimitiveTypeRef(name="String")
    return None


def _match_arm_binding_type(subject: Any, variant_name: str, *, context: _LoweringContext) -> TypeRef | None:
    """Resolve the variant-case type bound by a lowering-time match arm."""

    subject_type = _resolve_lowering_expr_type(subject, context=context)
    if not isinstance(subject_type, UnionTypeRef):
        return None
    return context.type_env.union_variant(
        subject_type,
        variant_name,
        span=subject.span,
        form_path=subject.form_path,
    )




def _typed_workflow_dependencies(
    typed_workflow: TypedWorkflowDef,
    *,
    typed_procedures: Mapping[str, TypedProcedureDef],
    workflow_catalog: WorkflowCatalog,
) -> set[str]:
    """Find same-file workflow dependencies required before lowering."""

    dependencies: set[str] = set()
    visiting_procedures: set[str] = set()

    def walk(expr: Any) -> None:
        if isinstance(expr, CallExpr):
            signature = workflow_catalog.signatures_by_name.get(expr.callee_name)
            if signature is not None and not any(
                isinstance(type_ref, WorkflowRefTypeRef) for _, type_ref in signature.params
            ):
                dependencies.add(expr.callee_name)
            for _, value in expr.bindings:
                walk(value)
            return
        if isinstance(expr, ProcedureCallExpr):
            for arg in expr.args:
                walk(arg)
            procedure = typed_procedures.get(expr.callee_name)
            if procedure is None:
                return
            if procedure.resolved_lowering_mode == ProcedureLoweringMode.PRIVATE_WORKFLOW:
                assert procedure.generated_workflow_name is not None
                dependencies.add(procedure.generated_workflow_name)
                return
            if procedure.definition.name in visiting_procedures:
                return
            visiting_procedures.add(procedure.definition.name)
            walk(procedure.typed_body.expr)
            visiting_procedures.remove(procedure.definition.name)
            return
        if isinstance(expr, LetStarExpr):
            for _, binding in expr.bindings:
                walk(binding)
            walk(expr.body)
            return
        # schema1_compatibility: legacy dependency walk for covered match forms.
        if isinstance(expr, MatchExpr):
            walk(expr.subject)
            for arm in expr.arms:
                walk(arm.body)
            return
        # schema1_compatibility: legacy dependency walk for covered loop forms.
        if isinstance(expr, LoopRecurExpr):
            walk(expr.max_iterations_expr)
            walk(expr.initial_state_expr)
            walk(expr.body_expr)
            return
        if isinstance(expr, ContinueExpr):
            walk(expr.state_expr)
            return
        if isinstance(expr, DoneExpr):
            walk(expr.result_expr)
            return
        if isinstance(expr, RecordExpr):
            for _, value in expr.fields:
                walk(value)
            return
        if isinstance(expr, WithPhaseExpr):
            walk(expr.ctx_expr)
            walk(expr.body)
            return
        # schema1_compatibility: legacy dependency walk for covered provider results.
        if isinstance(expr, ProviderResultExpr):
            walk(expr.provider)
            walk(expr.prompt)
            for value in expr.inputs:
                walk(value)
            return
        if isinstance(expr, ProviderBundlePathExpr):
            walk(expr.source_expr)
            return
        # schema1_compatibility: legacy dependency walk for covered command results.
        if isinstance(expr, CommandResultExpr):
            for value in expr.argv:
                walk(value)
            return

    walk(typed_workflow.typed_body.expr)
    return dependencies


def _lowered_workflow_dependencies(lowered_workflow: LoweredWorkflow) -> set[str]:
    """Find workflow-call dependencies from an already lowered mapping."""

    dependencies: set[str] = set()
    steps = lowered_workflow.authored_mapping.get("steps")

    def visit(items: Any) -> None:
        if not isinstance(items, list):
            return
        for step in items:
            if not isinstance(step, Mapping):
                continue
            if isinstance(step.get("call"), str):
                dependencies.add(str(step["call"]))
            repeat = step.get("repeat_until")
            if isinstance(repeat, Mapping):
                visit(repeat.get("steps"))
            match = step.get("match")
            if isinstance(match, Mapping):
                for case in (match.get("cases") or {}).values():
                    if isinstance(case, Mapping):
                        visit(case.get("steps"))
            if_block = step.get("then")
            if isinstance(if_block, Mapping):
                visit(if_block.get("steps"))
            else_block = step.get("else")
            if isinstance(else_block, Mapping):
                visit(else_block.get("steps"))

    visit(steps)
    return dependencies


def _validate_one_lowered_workflow(
    lowered_workflow: LoweredWorkflow,
    *,
    workspace_root: Path,
    imported_bundles: Mapping[str, LoadedWorkflowBundle],
    workflow_is_imported: bool,
) -> LoadedWorkflowBundle:
    """Validate one lowered workflow mapping through the shared loader path."""

    loader = WorkflowLoader(workspace_root)
    loader._allow_private_collection_output_schemas = True
    workflow = dict(lowered_workflow.authored_mapping)
    loader.errors = []
    loader._workflow_input_specs = {
        str(name): dict(spec)
        for name, spec in workflow.get("inputs", {}).items()
        if isinstance(name, str) and isinstance(spec, Mapping)
    }
    loader._current_workflow_path = lowered_workflow.typed_workflow.definition.body.span.start.path
    loader._current_workflow_path = Path(loader._current_workflow_path)
    loader._current_source_root = loader._current_workflow_path.parent
    loader._current_imports = dict(imported_bundles)
    loader._current_workflow_is_imported = workflow_is_imported
    loader._normalize_v214_ergonomics(workflow, str(workflow.get("version", "")))
    surface = elaborate_surface_workflow(
        workflow,
        workflow_path=loader._current_workflow_path,
        imported_bundles=imported_bundles,
        generated_path_allocations=lowered_workflow.generated_path_allocations,
        managed_write_root_inputs=tuple(
            item.generated_name
            for item in lowered_workflow.boundary_projection.generated_internal_inputs
            if item.reason == "managed_write_root"
        ),
        runtime_context_inputs=tuple(
            item.generated_name
            for item in lowered_workflow.boundary_projection.generated_internal_inputs
            if item.reason == "runtime_owned_context"
        ),
        private_exec_context_bindings=lowered_workflow.private_exec_context_bindings,
        compatibility_bridge_inputs=lowered_workflow.compatibility_bridge_inputs,
        validation_backend=loader,
        workflow_is_imported=workflow_is_imported,
        allow_generated_step_kinds=True,
    )
    if surface is None or loader.errors:
        _raise_remapped_validation_error(lowered_workflow, loader.errors)
    try:
        return build_loaded_workflow_bundle(
            surface,
            imports=imported_bundles,
            private_artifact_ids=lowered_workflow.private_artifact_ids,
        )
    except WorkflowValidationError as exc:
        _raise_remapped_validation_error(lowered_workflow, list(exc.errors))


def _require_phase_scope_name_match(
    phase_scope: _ActivePhaseScope,
    *,
    authored_name: str,
    form_name: str,
    span: SourceSpan,
    form_path: tuple[str, ...],
) -> None:
    """Require stdlib phase forms to use the enclosing `with-phase` name."""

    if phase_scope.scope.phase_name == authored_name:
        return
    raise _compile_error(
        code="phase_scope_name_mismatch",
        message=f"`{form_name}` name `{authored_name}` must match the active `with-phase` scope `{phase_scope.scope.phase_name}`",
        span=span,
        form_path=form_path,
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


def _definition_only_syntax_module(module_syntax: WorkflowLispSyntaxModule) -> WorkflowLispSyntaxModule:
    """Drop `defworkflow` forms so imports can contribute definitions only."""

    expanded = expand_module_forms(
        module_syntax,
        catalog=collect_macro_catalog(module_syntax),
    )
    definition_forms = []
    for form in expanded.forms:
        if syntax_head_name(syntax_node_datum(form)) == "defworkflow":
            continue
        definition_forms.append(form)
    return WorkflowLispSyntaxModule(
        language_version=expanded.language_version,
        target_dsl_version=expanded.target_dsl_version,
        module_directive=expanded.module_directive,
        imports=expanded.imports,
        export_directive=expanded.export_directive,
        forms=tuple(definition_forms),
        span=expanded.span,
        module_path=expanded.module_path,
    )


def _definition_only_module(workflow_path: Path):
    """Load only definitions from a source path using the current syntax path."""

    syntax_module = build_syntax_module(read_sexpr_file(workflow_path))
    return elaborate_definition_module(_definition_only_syntax_module(syntax_module))
