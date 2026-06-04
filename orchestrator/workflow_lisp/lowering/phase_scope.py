"""Phase-scope owner surface for stdlib lowering."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any

from orchestrator.workflow.loaded_bundle import LoadedWorkflowBundle, workflow_managed_write_root_inputs
from orchestrator.workflow.references import StructuredStepReference
from orchestrator.workflow.surface_ast import SurfaceStep

from ..contracts import derive_reusable_state_contract_metadata, derive_structured_result_contract, derive_workflow_boundary_fields
from ..diagnostics import LispFrontendCompileError, LispFrontendDiagnostic
from ..expressions import (
    BacklogDrainExpr,
    BindProcExpr,
    CallExpr,
    CommandResultExpr,
    ContinueExpr,
    DoneExpr,
    FieldAccessExpr,
    FinalizeSelectedItemExpr,
    GeneratedRelpathSeedExpr,
    IfExpr,
    LetStarExpr,
    LiteralExpr,
    LoopRecurExpr,
    MatchExpr,
    NameExpr,
    PhaseTargetExpr,
    ProcRefLiteralExpr,
    ProcedureCallExpr,
    ProduceOneOfExpr,
    ProviderResultExpr,
    RecordExpr,
    ResourceTransitionExpr,
    ResumeOrStartExpr,
    RunProviderPhaseExpr,
    UnionVariantExpr,
    WorkflowRefLiteralExpr,
    WithPhaseExpr,
)
from ..phase import IMPLEMENTATION_ATTEMPT_PHASE_NAME, PHASE_TARGET_SPECS, PhaseScope
from ..phase_stdlib import is_review_loop_request_kind
from ..procedure_refs import ResolvedProcRefValue, resolve_proc_ref_value
from ..procedures import ProcedureCatalog
from ..spans import SourceSpan
from ..type_env import PathTypeRef, PrimitiveTypeRef, ProcRefTypeRef, RecordTypeRef, TypeRef, UnionTypeRef
from ..typecheck import TypedExpr
from ..workflow_refs import ResolvedWorkflowRef, resolve_workflow_ref_literal, resolve_workflow_ref_name, workflow_ref_target_name
from ..workflows import CertifiedAdapterBinding, PromptExtern, ProviderExtern, analyze_workflow_boundary_type
from . import core as lowering_core
from .context import (
    _ActivePhaseScope,
    _copy_context_with_phase_scope,
    _copy_context_with_step_prefix,
    _LoweringContext,
    _TerminalResult,
)
from .effects import _lower_provider_result
from .origins import LoweringOrigin, _rekey_origin_map
from .values import _render_existing_output_ref, _resolve_inline_expr_value


def _compile_error(*args, **kwargs):
    return lowering_core._compile_error(*args, **kwargs)


def _normalize_generated_step_id(*args, **kwargs):
    return lowering_core._normalize_generated_step_id(*args, **kwargs)


def _record_step_origin(*args, **kwargs):
    return lowering_core._record_step_origin(*args, **kwargs)


def _origin_from_context_source(*args, **kwargs):
    return lowering_core._origin_from_context_source(*args, **kwargs)


def _record_output_refs(*args, **kwargs):
    return lowering_core._record_output_refs(*args, **kwargs)


def _record_missing_step_origins(*args, **kwargs):
    return lowering_core._record_missing_step_origins(*args, **kwargs)


def _materialize_values_step(*args, **kwargs):
    return lowering_core._materialize_values_step(*args, **kwargs)


def _conditional_case_ref(*args, **kwargs):
    return lowering_core._conditional_case_ref(*args, **kwargs)


def _render_boolean_predicate(*args, **kwargs):
    return lowering_core._render_boolean_predicate(*args, **kwargs)


def _template_for_ref(ref: str) -> str:
    if ref.startswith("${"):
        return ref
    return "${" + ref + "}"


def _lower_expression(*args, **kwargs):
    return lowering_core._lower_expression(*args, **kwargs)


def _lower_call_expr(*args, **kwargs):
    return lowering_core._lower_call_expr(*args, **kwargs)


def _render_call_binding_ref(*args, **kwargs):
    return lowering_core._render_call_binding_ref(*args, **kwargs)


def _render_record_call_bindings(*args, **kwargs):
    return lowering_core._render_record_call_bindings(*args, **kwargs)


def _flatten_boundary_leaf_paths(*args, **kwargs):
    return lowering_core._flatten_boundary_leaf_paths(*args, **kwargs)


def _record_expr_value_at_path(*args, **kwargs):
    return lowering_core._record_expr_value_at_path(*args, **kwargs)


def _normalize_union_field_path(*args, **kwargs):
    return lowering_core._normalize_union_field_path(*args, **kwargs)


def _union_variant_expr_value_at_path(*args, **kwargs):
    return lowering_core._union_variant_expr_value_at_path(*args, **kwargs)


def _phase_target_inline_ref(*args, **kwargs):
    return lowering_core._phase_target_inline_ref(*args, **kwargs)


def _join_ref_path(*args, **kwargs):
    return lowering_core._join_ref_path(*args, **kwargs)


def _resolve_nested_local_value(*args, **kwargs):
    return lowering_core._resolve_nested_local_value(*args, **kwargs)




def _lower_with_phase(*args, **kwargs):
    return _phase_stdlib_lower_with_phase_impl(*args, **kwargs)

def _phase_prompt_artifact_definition(
    *,
    contract: Mapping[str, Any],
    input_name: str | None,
    context: _LoweringContext,
    pointer_path: str,
    span: SourceSpan,
    form_path: tuple[str, ...],
) -> dict[str, Any]:
    """Build the top-level artifact entry for a phase prompt input."""

    artifact_contract = dict(contract)
    if artifact_contract.get("inherit") == "source":
        if input_name is None:
            raise _compile_error(
                code="phase_translation_body_invalid",
                message="missing flattened workflow input contract for inherited phase prompt artifact",
                span=span,
                form_path=form_path,
            )
        input_contract = context.authored_input_contracts.get(input_name)
        if input_contract is None:
            raise _compile_error(
                code="phase_translation_body_invalid",
                message=f"missing flattened workflow input contract for `{input_name}`",
                span=span,
                form_path=form_path,
            )
        artifact_contract = dict(input_contract)
    artifact_contract["pointer"] = pointer_path
    return artifact_contract


def _phase_prompt_input_pointer_path(workflow_name: str, artifact_name: str) -> str:
    """Return the compatibility pointer path for a phase prompt artifact."""

    return f".orchestrate/workflow_lisp/{workflow_name}/materialized/{artifact_name}.txt"


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



def _workflow_extern_requirements(
    typed_workflow: TypedWorkflowDef,
    *,
    typed_procedures: Mapping[str, TypedProcedureDef],
) -> tuple[set[str], set[str]]:
    """Collect provider and prompt extern names required by a typed workflow."""

    provider_names: set[str] = set()
    prompt_names: set[str] = set()
    visiting_procedures: set[str] = set()

    def walk(expr: Any) -> None:
        if isinstance(expr, ProviderResultExpr):
            if isinstance(expr.provider, NameExpr):
                provider_names.add(expr.provider.name)
            if isinstance(expr.prompt, NameExpr):
                prompt_names.add(expr.prompt.name)
            for value in expr.inputs:
                walk(value)
            return
        if isinstance(expr, RunProviderPhaseExpr):
            if isinstance(expr.provider, NameExpr):
                provider_names.add(expr.provider.name)
            if isinstance(expr.prompt, NameExpr):
                prompt_names.add(expr.prompt.name)
            walk(expr.ctx_expr)
            walk(expr.inputs_expr)
            return
        if isinstance(expr, ProduceOneOfExpr):
            if isinstance(expr.producer.provider_expr, NameExpr):
                provider_names.add(expr.producer.provider_expr.name)
            if isinstance(expr.producer.prompt_expr, NameExpr):
                prompt_names.add(expr.producer.prompt_expr.name)
            for value in expr.producer.inputs:
                walk(value)
            return
        if isinstance(expr, ProcedureCallExpr):
            for value in expr.args:
                walk(value)
            procedure = typed_procedures.get(expr.callee_name)
            if procedure is None or procedure.definition.name in visiting_procedures:
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
        if isinstance(expr, MatchExpr):
            walk(expr.subject)
            for arm in expr.arms:
                walk(arm.body)
            return
        if isinstance(expr, IfExpr):
            walk(expr.condition_expr)
            walk(expr.then_expr)
            walk(expr.else_expr)
            return
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
        if isinstance(expr, CallExpr):
            for _, value in expr.bindings:
                walk(value)
            return
        if isinstance(expr, CommandResultExpr):
            for value in expr.argv:
                walk(value)

    walk(typed_workflow.typed_body.expr)
    return provider_names, prompt_names


def _same_file_workflow_provider_requirements(
    typed_workflow: TypedWorkflowDef | None,
    *,
    typed_procedures: Mapping[str, TypedProcedureDef],
) -> tuple[int, int]:
    """Count provider and prompt extern requirements for one same-file workflow."""

    if typed_workflow is None:
        return 0, 0
    provider_names, prompt_names = _workflow_extern_requirements(
        typed_workflow,
        typed_procedures=typed_procedures,
    )
    return len(provider_names), len(prompt_names)



def _phase_stdlib_lower_with_phase_impl(
    typed_expr: TypedExpr,
    *,
    context: _LoweringContext,
    local_values: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], _TerminalResult]:
    """Enter a derived phase scope and lower the body inside it."""

    expr = typed_expr.expr
    assert isinstance(expr, WithPhaseExpr)
    return _lower_composed_with_phase(
        expr,
        result_type=typed_expr.type_ref,
        context=context,
        local_values=local_values,
    )


def _lower_composed_with_phase(
    expr: WithPhaseExpr,
    *,
    result_type: TypeRef,
    context: _LoweringContext,
    local_values: Mapping[str, Any],
    step_name_prefix: str | None = None,
) -> tuple[list[dict[str, Any]], _TerminalResult]:
    """Lower a `with-phase` wrapper by lowering only its body under phase scope."""

    lowering_phase_scope = _resolve_active_phase_scope(expr, local_values=local_values)
    scoped_context = _copy_context_with_phase_scope(context, lowering_phase_scope)
    if step_name_prefix is not None:
        if isinstance(expr.body, ProviderResultExpr):
            return _lower_provider_result(
                expr.body,
                result_type=result_type,
                context=scoped_context,
                local_values=local_values,
                step_name=step_name_prefix,
            )
        scoped_context = _copy_context_with_step_prefix(
            scoped_context,
            step_name_prefix=step_name_prefix,
        )
    return _lower_expression(
        TypedExpr(
            expr=expr.body,
            type_ref=result_type,
            span=expr.body.span,
            form_path=expr.body.form_path,
        ),
        context=scoped_context,
        local_values=local_values,
    )


def _lower_workflow_outputs(
    *,
    typed_workflow: TypedWorkflowDef,
    authored_outputs: Mapping[str, dict[str, Any]],
    terminal: _TerminalResult,
) -> dict[str, Any]:
    """Connect terminal expression refs to the workflow's declared outputs."""

    lowered_outputs: dict[str, Any] = {}
    for output_name, definition in authored_outputs.items():
        source_ref = terminal.output_refs.get(output_name)
        if source_ref is None:
            field_name = output_name.removeprefix("return__")
            raise _compile_error(
                code="workflow_return_not_exportable",
                message=f"workflow `{typed_workflow.definition.name}` cannot export return field `{field_name}`",
                span=typed_workflow.definition.body.span,
                form_path=typed_workflow.definition.body.form_path,
            )
        lowered_outputs[output_name] = {
            **definition,
            "from": {"ref": source_ref},
        }
    return lowered_outputs

def _managed_inputs_from_mapping(authored_mapping: Mapping[str, object]) -> tuple[str, ...]:
    """Return generated write-root inputs declared by a lowered mapping."""

    inputs = authored_mapping.get("inputs")
    if not isinstance(inputs, Mapping):
        return ()
    return tuple(
        name for name in inputs if isinstance(name, str) and name.startswith("__write_root__")
    )


def _runtime_context_default_value(
    *,
    requirement: PromotedEntryHiddenContextRequirement,
    source_path: tuple[str, ...],
) -> str | None:
    param_name = requirement.param_name
    phase_name = requirement.phase_name
    if source_path == (param_name, "run", "run-id") or source_path == (param_name, "run-id"):
        return None
    if source_path == (param_name, "run", "state-root") or source_path == (param_name, "state-root"):
        return "state/run"
    if source_path == (param_name, "run", "artifact-root") or source_path == (param_name, "artifact-root"):
        return "artifacts/run"
    if requirement.context_kind != PHASE_CONTEXT_NAME or phase_name is None:
        return None
    if source_path == (param_name, "phase-name"):
        return phase_name
    if source_path == (param_name, "state-root"):
        return f"state/{phase_name}"
    if source_path == (param_name, "artifact-root"):
        return f"artifacts/{phase_name}"
    return None


def _declare_runtime_context_hidden_inputs(
    *,
    context: _LoweringContext,
    param_name: str,
    param_type: RecordTypeRef,
    requirement: PromotedEntryHiddenContextRequirement,
    source_expr: Any,
) -> dict[str, Any]:
    """Declare runtime-owned hidden inputs for one omitted promoted-entry context param."""

    origin = _origin_from_context_source(context, source_expr)
    with_bindings: dict[str, Any] = {}
    for flattened_field in derive_workflow_boundary_fields(
        param_type,
        generated_name=param_name,
        source_path=(param_name,),
        span=origin.span,
        form_path=origin.form_path,
    ):
        contract_definition = dict(flattened_field.contract_definition)
        default_value = _runtime_context_default_value(
            requirement=requirement,
            source_path=flattened_field.source_path,
        )
        if default_value is not None:
            contract_definition["default"] = default_value
        context.internal_generated_input_contracts.setdefault(
            flattened_field.generated_name,
            contract_definition,
        )
        context.generated_input_spans.setdefault(flattened_field.generated_name, origin)
        context.internal_generated_input_reasons.setdefault(
            flattened_field.generated_name,
            "runtime_owned_context",
        )
        with_bindings[flattened_field.generated_name] = {
            "ref": f"inputs.{flattened_field.generated_name}",
        }
    return with_bindings


def _managed_inputs_from_bundle(bundle: LoadedWorkflowBundle | None) -> tuple[str, ...]:
    """Return generated write-root inputs declared by an imported bundle."""

    if bundle is None:
        return ()
    return workflow_managed_write_root_inputs(bundle)


def _managed_write_root_requirements_for_callable(
    *,
    lowered_callee: LoweredWorkflow | None,
    imported_bundle: LoadedWorkflowBundle | None,
    span: SourceSpan,
    form_path: tuple[str, ...],
) -> tuple[str, ...]:
    """Return deterministic managed write-root inputs for one callable boundary."""

    if lowered_callee is not None:
        managed_projection_inputs = tuple(
            field.generated_name
            for field in lowered_callee.boundary_projection.generated_internal_inputs
            if field.reason == "managed_write_root" and isinstance(field.generated_name, str)
        )
        if managed_projection_inputs:
            return tuple(sorted(managed_projection_inputs))
        return tuple(sorted(_managed_inputs_from_mapping(lowered_callee.authored_mapping)))
    if imported_bundle is not None:
        return tuple(sorted(_managed_inputs_from_bundle(imported_bundle)))
    raise _compile_error(
        code="workflow_call_unknown",
        message="managed write-root discovery requires a lowered callee or imported bundle",
        span=span,
        form_path=form_path,
    )


def _managed_write_root_bindings(
    *,
    caller_workflow_name: str,
    call_step_name: str,
    callee_name: str,
    managed_inputs: tuple[str, ...],
    iteration_scope: str | None = None,
) -> dict[str, str]:
    """Allocate deterministic caller-owned write-root bindings for one call site."""

    base_segments = [
        ".orchestrate/workflow_lisp/calls",
        caller_workflow_name,
        call_step_name,
    ]
    if iteration_scope is not None:
        base_segments.append(iteration_scope)
    base_segments.append(callee_name)
    base_path = "/".join(base_segments)
    return {
        managed_input: f"{base_path}/{managed_input}.json"
        for managed_input in sorted(managed_inputs)
    }


def _signature_local_values(typed_workflow: TypedWorkflowDef | _LoweringContext) -> dict[str, Any]:
    """Seed local value refs from a workflow signature."""

    if isinstance(typed_workflow, _LoweringContext):
        signature = typed_workflow.signature
    else:
        signature = typed_workflow.signature
    local_values: dict[str, Any] = {}
    for param_name, param_type in signature.params:
        if isinstance(param_type, RecordTypeRef):
            local_values[param_name] = _build_record_local_value(param_type, generated_name=param_name)
        else:
            local_values[param_name] = f"inputs.{param_name}"
    specialization = getattr(typed_workflow, "specialization", None)
    if specialization is not None:
        local_values.update(dict(getattr(specialization, "workflow_ref_bindings", {})))
        local_values.update(dict(getattr(specialization, "proc_ref_bindings", {})))
        local_values.update(dict(getattr(specialization, "value_bindings", {})))
    return local_values


def _procedure_signature_local_values(procedure: TypedProcedureDef) -> dict[str, Any]:
    """Seed local value refs from a private workflow procedure signature."""

    local_values: dict[str, Any] = {}
    for param_name, param_type in procedure.signature.params:
        if isinstance(param_type, RecordTypeRef):
            local_values[param_name] = _build_record_local_value(
                param_type,
                generated_name=param_name,
            )
            continue
        local_values[param_name] = f"inputs.{param_name}"
    if procedure.specialization is not None:
        local_values.update(dict(getattr(procedure.specialization, "workflow_ref_bindings", {})))
        local_values.update(dict(getattr(procedure.specialization, "proc_ref_bindings", {})))
        local_values.update(dict(getattr(procedure.specialization, "value_bindings", {})))
    return local_values


def _procedure_signature_local_type_bindings(procedure: TypedProcedureDef) -> dict[str, TypeRef]:
    """Seed local type bindings from a private workflow procedure signature."""

    return {
        param_name: param_type
        for param_name, param_type in procedure.signature.params
    }


def _render_argv_tail(argv: list[Any], *, local_values: Mapping[str, Any]) -> list[str]:
    """Render frontend command arguments after a stable command prefix."""

    rendered: list[str] = []
    for expr in argv:
        rendered.append(_render_scalar_expr(expr, local_values=local_values))
    return rendered


def _render_scalar_expr(expr: Any, *, local_values: Mapping[str, Any]) -> str:
    """Render a scalar expression as a literal or workflow substitution."""

    if isinstance(expr, LiteralExpr):
        return str(expr.value)
    value = _resolve_inline_expr_value(expr, local_values=local_values)
    if isinstance(value, LiteralExpr):
        return str(value.value)
    if isinstance(value, str):
        return "${" + value + "}"
    raise _compile_error(
        code="workflow_return_not_exportable",
        message="Stage 3 lowering requires command argv values to resolve to literals or workflow inputs",
        span=expr.span,
        form_path=expr.form_path,
    )


def _render_repeat_until_max_iterations(expr: Any, *, local_values: Mapping[str, Any]) -> int:
    """Render a repeat limit expression; currently this must be a literal int."""

    value = _resolve_inline_expr_value(expr, local_values=local_values)
    if isinstance(value, LiteralExpr):
        return int(value.value)
    raise _compile_error(
        code="workflow_return_not_exportable",
        message="`backlog-drain :max-iterations` must lower from a literal integer",
        span=expr.span,
        form_path=expr.form_path,
    )


def _render_boolean_predicate(expr: Any | None, *, local_values: Mapping[str, Any]) -> dict[str, Any] | None:
    """Render an optional boolean frontend expression as a shared predicate."""

    if expr is None:
        return None
    value = _resolve_inline_expr_value(expr, local_values=local_values)
    if isinstance(value, LiteralExpr) and value.literal_kind == "bool":
        return render_condition_predicate(
            classify_condition_expr(value, type_ref=PrimitiveTypeRef(name="Bool")),
            local_values=local_values,
        )
    if isinstance(value, str):
        return {"artifact_bool": {"ref": value}}
    if isinstance(expr, (NameExpr, FieldAccessExpr)):
        return render_condition_predicate(
            classify_condition_expr(expr, type_ref=PrimitiveTypeRef(name="Bool")),
            local_values=local_values,
        )
    if isinstance(expr, LiteralExpr) and expr.literal_kind == "bool":
        return render_condition_predicate(
            classify_condition_expr(expr, type_ref=PrimitiveTypeRef(name="Bool")),
            local_values=local_values,
        )
    else:
        raise _compile_error(
            code="workflow_return_not_exportable",
            message="boolean guards must lower from literals or workflow inputs/refs",
            span=expr.span,
            form_path=expr.form_path,
        )


def _render_call_binding_ref(
    expr: Any,
    *,
    local_values: Mapping[str, Any],
    field_path: tuple[str, ...] = (),
) -> Any:
    """Render one frontend expression as a `call.with` binding value.

    Structured records are flattened at workflow boundaries, so `field_path`
    selects the specific leaf needed for one generated `with` entry.
    """

    value = _resolve_expr_local_value(expr, local_values=local_values)
    if field_path:
        value = _resolve_nested_local_value(value, field_path)
    return _render_call_binding_leaf_ref(value, source_expr=expr)


def _render_record_call_bindings(
    param_name: str,
    param_type: RecordTypeRef,
    value_expr: Any,
    *,
    local_values: Mapping[str, Any],
) -> dict[str, Any]:
    """Lower one record-typed call argument into flattened `call.with` refs."""

    bindings: dict[str, Any] = {}
    resolved_value = _resolve_inline_expr_value(value_expr, local_values=local_values)
    for generated_name, field_path in _flatten_boundary_leaf_paths(param_type, generated_name=param_name):
        leaf_source_expr = value_expr
        if isinstance(resolved_value, Mapping):
            leaf_value = _resolve_nested_local_value(resolved_value, field_path)
        elif isinstance(resolved_value, RecordExpr):
            leaf_source_expr = _record_expr_value_at_path(resolved_value, field_path)
            leaf_value = _resolve_inline_expr_value(leaf_source_expr, local_values=local_values)
        else:
            leaf_value = _inline_expr_field_value(
                value_expr,
                field_path=field_path,
                local_values=local_values,
            )
        bindings[generated_name] = _render_call_binding_leaf_ref(
            leaf_value,
            source_expr=leaf_source_expr,
            binding_label=_record_call_binding_label(param_name, field_path),
        )
    return bindings


def _record_call_binding_label(param_name: str, field_path: tuple[str, ...]) -> str:
    """Render an authored record leaf path for diagnostics."""

    if not field_path:
        return param_name
    return f"{param_name}.{'.'.join(field_path)}"


def _render_call_binding_leaf_ref(
    value: Any,
    *,
    source_expr: Any,
    binding_label: str | None = None,
) -> dict[str, str]:
    """Apply the shared ref-only authority rule for runtime call bindings."""

    if isinstance(value, str):
        return {"ref": value}
    if binding_label is None:
        message = "Stage 3 lowering requires same-file call bindings to resolve to workflow inputs"
    else:
        message = f"record call binding `{binding_label}` must lower from workflow inputs or prior outputs"
    raise _compile_error(
        code="workflow_signature_mismatch",
        message=message,
        span=source_expr.span,
        form_path=source_expr.form_path,
    )


def _build_call_bindings_from_record_value(
    param_name: str,
    param_type: Any,
    value: Mapping[str, Any],
    *,
    source_expr: Any,
) -> dict[str, Any]:
    """Flatten a record value into `call.with` bindings for one parameter."""

    if not isinstance(param_type, RecordTypeRef):
        raise _compile_error(
            code="workflow_signature_mismatch",
            message="record binding helper requires a record-typed workflow parameter",
            span=source_expr.span,
            form_path=source_expr.form_path,
        )
    bindings: dict[str, Any] = {}
    for generated_name, field_path in _flatten_boundary_leaf_paths(param_type, generated_name=param_name):
        ref = _resolve_nested_local_value(value, field_path)
        bindings[generated_name] = _render_call_binding_leaf_ref(
            ref,
            source_expr=source_expr,
            binding_label=_record_call_binding_label(param_name, field_path),
        )
    return bindings


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


def _resource_transition_payload(
    expr: ResourceTransitionExpr,
    *,
    context: _LoweringContext,
    local_values: Mapping[str, Any],
) -> dict[str, Any]:
    """Build the JSON payload sent to the resource-transition adapter."""

    payload: dict[str, Any] = {
        "transition_name": expr.spec.transition_name,
        "from": expr.spec.from_queue_name.rsplit(".", 1)[-1],
        "to": expr.spec.to_queue_name.rsplit(".", 1)[-1],
        "event": expr.spec.event_name,
    }
    ledger_value = _resolve_inline_expr_value(expr.spec.ledger_expr, local_values=local_values)
    if isinstance(ledger_value, LiteralExpr):
        payload["ledger_path"] = str(ledger_value.value)
    elif isinstance(ledger_value, str):
        payload["ledger_path"] = "${" + ledger_value + "}"
    else:
        raise _compile_error(
            code="workflow_return_not_exportable",
            message="`resource-transition :ledger` must lower from a literal or workflow input path",
            span=expr.spec.ledger_expr.span,
            form_path=expr.spec.ledger_expr.form_path,
        )

    resource_value = _resolve_inline_expr_value(expr.spec.resource_expr, local_values=local_values)
    resource_type = _resolve_signature_expr_type(expr.spec.resource_expr, context=context)
    if isinstance(resource_value, LiteralExpr):
        if isinstance(resource_type, PathTypeRef):
            payload["resource_path"] = str(resource_value.value)
        else:
            payload["resource_id"] = str(resource_value.value)
    elif isinstance(resource_value, str):
        if isinstance(resource_type, PathTypeRef):
            payload["resource_path"] = "${" + resource_value + "}"
        else:
            payload["resource_id"] = "${" + resource_value + "}"
    else:
        raise _compile_error(
            code="workflow_return_not_exportable",
            message="`resource-transition :resource` must lower from a literal or workflow input value",
            span=expr.spec.resource_expr.span,
            form_path=expr.spec.resource_expr.form_path,
        )

    if isinstance(expr.spec.resource_expr, FieldAccessExpr):
        base_value = local_values.get(expr.spec.resource_expr.base.name)
        if isinstance(base_value, Mapping):
            sibling_path_ref = base_value.get("item-path")
            if "resource_path" not in payload and isinstance(sibling_path_ref, str):
                payload["resource_path"] = "${" + sibling_path_ref + "}"
            sibling_id_ref = base_value.get("item-id")
            if "resource_id" not in payload and isinstance(sibling_id_ref, str):
                payload["resource_id"] = "${" + sibling_id_ref + "}"
    return payload


def _resolve_signature_expr_type(expr: Any, *, context: _LoweringContext) -> TypeRef | None:
    """Resolve the frontend type of a signature-rooted expression."""

    if isinstance(expr, NameExpr):
        return _signature_param_type(expr.name, context=context)
    if isinstance(expr, FieldAccessExpr):
        current_type = _signature_param_type(expr.base.name, context=context)
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
    return None


def _signature_param_type(name: str, *, context: _LoweringContext) -> TypeRef | None:
    """Return the type of a workflow parameter in the active context."""

    for param_name, param_type in context.signature.params:
        if param_name == name:
            return param_type
    return None


def _resolve_inline_expr_value(expr: Any, *, local_values: Mapping[str, Any]) -> Any:
    """Resolve literals, names, fields, and record expressions for inline use."""

    if isinstance(expr, LiteralExpr):
        return expr
    if isinstance(expr, GeneratedRelpathSeedExpr):
        return expr
    if isinstance(expr, WorkflowRefLiteralExpr):
        return expr
    if isinstance(expr, (ProcRefLiteralExpr, BindProcExpr)):
        return expr
    if isinstance(expr, LetStarExpr):
        child_locals = dict(local_values)
        for binding_name, binding_expr in expr.bindings:
            resolved_binding = _resolve_inline_expr_value(binding_expr, local_values=child_locals)
            if resolved_binding is None:
                return expr
            child_locals[binding_name] = resolved_binding
        return _resolve_inline_expr_value(expr.body, local_values=child_locals)
    if isinstance(expr, IfExpr):
        condition_value = _resolve_inline_expr_value(expr.condition_expr, local_values=local_values)
        if isinstance(condition_value, LiteralExpr) and condition_value.literal_kind == "bool":
            branch = expr.then_expr if condition_value.value else expr.else_expr
            return _resolve_inline_expr_value(branch, local_values=local_values)
        return expr
    resolved = _resolve_expr_local_value(expr, local_values=local_values)
    if isinstance(resolved, (str, Mapping, LiteralExpr, RecordExpr)):
        return resolved
    if resolved is not None:
        if resolved is expr:
            return expr
        return _resolve_inline_expr_value(resolved, local_values=local_values)
    if isinstance(expr, NameExpr):
        bound = local_values.get(expr.name)
        if bound is None:
            return None
        if isinstance(bound, (str, Mapping)):
            return bound
        if bound is expr:
            return expr
        return _resolve_inline_expr_value(bound, local_values=local_values)
    if isinstance(expr, FieldAccessExpr):
        return _resolve_inline_field_value(
            local_values.get(expr.base.name),
            field_path=tuple(expr.fields),
            local_values=local_values,
        )
    return expr


def _resolved_workflow_ref_value(
    value: Any,
    *,
    context: _LoweringContext,
    expected_type: WorkflowRefTypeRef | None,
) -> ResolvedWorkflowRef | None:
    if isinstance(value, ResolvedWorkflowRef):
        return value
    if isinstance(value, WorkflowRefLiteralExpr):
        if expected_type is None:
            signature = context.workflow_catalog.signatures_by_name.get(value.target_name)
            if signature is None:
                raise _compile_error(
                    code="workflow_ref_unknown",
                    message=f"unknown workflow ref `{value.target_name}`",
                    span=value.span,
                    form_path=value.form_path,
                )
            expected_type = WorkflowRefTypeRef(
                name=f"WorkflowRef[{ ' '.join(type_ref.name for _, type_ref in signature.params) } -> {signature.return_type_ref.name}]",
                param_type_refs=tuple(type_ref for _, type_ref in signature.params),
                return_type_ref=signature.return_type_ref,
            )
        return resolve_workflow_ref_literal(
            value,
            expected_type=expected_type,
            workflow_catalog=context.workflow_catalog,
            typed_workflows_by_name=context.workflows_by_name,
            allow_extern_rebinding=False,
        )
    if isinstance(value, NameExpr):
        return resolve_workflow_ref_name(
            workflow_ref_target_name(value),
            workflow_catalog=context.workflow_catalog,
            span=value.span,
            form_path=value.form_path,
            expansion_stack=value.expansion_stack,
            expected_type=expected_type,
            typed_workflows_by_name=context.workflows_by_name,
            allow_extern_rebinding=False,
        )
    return None


def _proc_ref_env_from_local_values(
    local_values: Mapping[str, Any],
    *,
    context: _LoweringContext,
) -> dict[str, ResolvedProcRefValue]:
    env: dict[str, ResolvedProcRefValue] = {}
    for name, value in local_values.items():
        if isinstance(value, ResolvedProcRefValue):
            env[name] = value
    return env


def _resolved_proc_ref_value(
    value: Any,
    *,
    context: _LoweringContext,
    local_values: Mapping[str, Any],
    expected_type: ProcRefTypeRef | None = None,
) -> ResolvedProcRefValue | None:
    if isinstance(value, ResolvedProcRefValue):
        return value
    if not isinstance(value, (NameExpr, ProcRefLiteralExpr, BindProcExpr)):
        return None
    procedure_catalog = getattr(context, "procedure_catalog", None)
    if procedure_catalog is None:
        procedure_catalog = ProcedureCatalog(
            signatures_by_name={
                name: procedure.signature
                for name, procedure in context.typed_procedures.items()
            },
            definitions_by_name={
                name: procedure.definition
                for name, procedure in context.typed_procedures.items()
            },
            call_graph={},
        )
    return resolve_proc_ref_value(
        value,
        procedure_catalog=procedure_catalog,
        proc_ref_env=_proc_ref_env_from_local_values(local_values, context=context),
        expected_type=expected_type,
    )


def _resolve_inline_field_value(
    value: Any,
    *,
    field_path: tuple[str, ...],
    local_values: Mapping[str, Any],
) -> Any:
    """Resolve a nested field path through inline mappings or record expressions."""

    current = value
    for field_name in field_path:
        if current is not None and not isinstance(current, (Mapping, RecordExpr, UnionVariantExpr)):
            next_current = _resolve_inline_expr_value(current, local_values=local_values)
            if next_current is current:
                return None
            current = next_current
        if isinstance(current, Mapping):
            current = current.get(field_name)
            continue
        if isinstance(current, RecordExpr):
            current = _record_field_value(current, field_name)
            current = _resolve_inline_expr_value(current, local_values=local_values)
            continue
        if isinstance(current, UnionVariantExpr):
            current = _union_variant_expr_value_at_path(current, (field_name,))
            current = _resolve_inline_expr_value(current, local_values=local_values)
            continue
        return None
    return current


def _build_phase_prompt_input_prelude(
    expr: ProviderResultExpr,
    *,
    context: _LoweringContext,
    local_values: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Build legacy implementation-phase prompt materialization steps."""

    phase_scope = context.phase_scope
    if phase_scope is None:
        return []

    if len(expr.inputs) != 4:
        raise _compile_error(
            code="phase_translation_body_invalid",
            message="phase-scoped provider-result requires design, plan, and both report targets in this slice",
            span=expr.span,
            form_path=expr.form_path,
        )

    design_expr, plan_expr, *report_target_exprs = expr.inputs
    target_inputs = _phase_prompt_report_target_inputs(
        report_target_exprs,
        span=expr.span,
        form_path=expr.form_path,
    )
    phase_prompt_inputs = (
        ("design", design_expr),
        ("plan", plan_expr),
        ("execution_report_target", target_inputs["execution_report_target"]),
        ("progress_report_target", target_inputs["progress_report_target"]),
    )

    values: list[dict[str, Any]] = []
    publishes: list[dict[str, str]] = []
    for artifact_name, input_expr in phase_prompt_inputs:
        raw_source_node, _ = _resolve_phase_prompt_input_source(
            input_expr,
            artifact_name=artifact_name,
            context=context,
            local_values=local_values,
        )
        input_name = _materialize_source_input_name(raw_source_node)
        if artifact_name in {"design", "plan"} and input_name is None:
            raise _compile_error(
                code="phase_translation_body_invalid",
                message="phase prompt-input materialization must lower from flattened workflow inputs",
                span=input_expr.span,
                form_path=input_expr.form_path,
            )
        source_node = raw_source_node
        contract_input_name = input_name
        if artifact_name in {"execution_report_target", "progress_report_target"}:
            if input_name is None:
                raise _compile_error(
                    code="phase_translation_body_invalid",
                    message="phase report targets must lower from flattened workflow inputs",
                    span=input_expr.span,
                    form_path=input_expr.form_path,
                )
            source_node = {"ref": f"inputs.{input_name}"}
            input_name = None
        pointer_path = _phase_prompt_input_pointer_path(context.workflow_name, artifact_name)
        artifact_contract = _phase_prompt_input_contract(
            artifact_name,
            input_name=contract_input_name,
            context=context,
            span=input_expr.span,
            form_path=input_expr.form_path,
        )
        values.append(
            {
                "name": artifact_name,
                "source": source_node,
                "contract": artifact_contract,
                "pointer": {"path": pointer_path},
            }
        )
        context.top_level_artifacts[artifact_name] = _phase_prompt_artifact_definition(
            contract=artifact_contract,
            input_name=contract_input_name,
            context=context,
            pointer_path=pointer_path,
            span=input_expr.span,
            form_path=input_expr.form_path,
        )
        context.generated_path_spans[pointer_path] = _origin_from_context_source(context, input_expr)
        publishes.append({"artifact": artifact_name, "from": artifact_name})

    step_name = "MaterializeImplementationAttemptPromptInputs"
    step_id = _normalize_generated_step_id(step_name)
    _record_step_origin(context, step_name=step_name, step_id=step_id, source=expr)
    return [
        {
            "name": step_name,
            "id": step_id,
            "materialize_artifacts": {"values": values},
            "publishes": publishes,
        }
    ]


def _uses_legacy_phase_prompt_input_prelude(expr: ProviderResultExpr) -> bool:
    """Return whether one phase-scoped provider-result uses the retained four-input surface."""

    if len(expr.inputs) != 4:
        return False
    report_targets = expr.inputs[2:]
    return {
        target_expr.target_name
        for target_expr in report_targets
        if isinstance(target_expr, PhaseTargetExpr)
    } == {"execution-report", "progress-report"}


def _phase_prompt_inputs_are_direct(
    prompt_input_specs: tuple[tuple[str, Any], ...],
    *,
    context: _LoweringContext,
    local_values: Mapping[str, Any],
) -> bool:
    """Return whether prompt inputs come directly from workflow inputs or approved targets."""

    for base_name, prompt_input in prompt_input_specs:
        for artifact_name, input_expr in _flatten_phase_stdlib_prompt_inputs(
            prompt_input,
            base_name=base_name,
            local_values=local_values,
        ):
            source_node, extra_hidden_inputs = _resolve_phase_prompt_input_source(
                input_expr,
                artifact_name=artifact_name,
                context=context,
                local_values=local_values,
            )
            if extra_hidden_inputs:
                return False
            input_name = source_node.get("input")
            if isinstance(input_name, str):
                continue
            source_ref = source_node.get("ref")
            if isinstance(source_ref, str) and source_ref.startswith("inputs."):
                continue
            return False
    return True


def _build_phase_stdlib_prompt_input_prelude(
    prompt_input_specs: tuple[tuple[str, Any], ...],
    *,
    context: _LoweringContext,
    local_values: Mapping[str, Any],
    source_expr: Any,
) -> tuple[list[dict[str, Any]], list[dict[str, str]], list[str], dict[str, LoweringOrigin]]:
    """Build phase-stdlib prompt materialization, consumes, and hidden inputs."""

    phase_scope = context.phase_scope
    if phase_scope is None:
        return [], [], [], {}

    flattened_inputs: list[tuple[str, Any]] = []
    for base_name, prompt_input in prompt_input_specs:
        flattened_inputs.extend(
            _flatten_phase_stdlib_prompt_inputs(
                prompt_input,
                base_name=base_name,
                local_values=local_values,
            )
        )

    values: list[dict[str, Any]] = []
    publishes: list[dict[str, str]] = []
    artifact_names: list[str] = []
    hidden_inputs: dict[str, LoweringOrigin] = {}
    for artifact_name, input_expr in flattened_inputs:
        raw_source_node, extra_hidden_inputs = _resolve_phase_prompt_input_source(
            input_expr,
            artifact_name=artifact_name,
            context=context,
            local_values=local_values,
        )
        hidden_inputs.update(extra_hidden_inputs)
        for hidden_input_name in extra_hidden_inputs:
            context.internal_generated_input_reasons.setdefault(hidden_input_name, "phase_prompt_transport")
        contract_input_name = _materialize_contract_input_name(raw_source_node)
        pointer_path = _phase_prompt_input_pointer_path(context.workflow_name, artifact_name)
        if contract_input_name is None or contract_input_name.startswith("__phase_prompt__"):
            if not isinstance(input_expr, PhaseTargetExpr):
                value_contract = _phase_prompt_local_value_contract(
                    artifact_name,
                    context=context,
                    span=source_expr.span,
                    form_path=source_expr.form_path,
                )
                if value_contract is None:
                    raise _compile_error(
                        code="phase_translation_body_invalid",
                        message=(
                            "phase stdlib prompt inputs must lower from flattened workflow inputs, "
                            "approved phase targets, or typed step-backed state"
                        ),
                        span=source_expr.span,
                        form_path=source_expr.form_path,
                    )
            else:
                value_contract = _phase_target_prompt_input_contract(input_expr)
        else:
            value_contract = (
                {"inherit": "source"}
                if raw_source_node.get("input") == contract_input_name
                else _authored_input_contract(
                    contract_input_name,
                    context=context,
                    span=source_expr.span,
                    form_path=source_expr.form_path,
                )
            )
        values.append(
            {
                "name": artifact_name,
                "source": raw_source_node,
                "contract": value_contract,
                "pointer": {"path": pointer_path},
            }
        )
        context.top_level_artifacts[artifact_name] = _phase_prompt_artifact_definition(
            contract=value_contract,
            input_name=contract_input_name,
            context=context,
            pointer_path=pointer_path,
            span=source_expr.span,
            form_path=source_expr.form_path,
        )
        context.generated_path_spans[pointer_path] = _origin_from_context_source(context, source_expr)
        publishes.append({"artifact": artifact_name, "from": artifact_name})
        artifact_names.append(artifact_name)

    step_name = f"{context.step_name_prefix}__prompt_inputs"
    step_id = _normalize_generated_step_id(step_name)
    _record_step_origin(context, step_name=step_name, step_id=step_id, source=source_expr)
    return (
        [
            {
                "name": step_name,
                "id": step_id,
                "materialize_artifacts": {"values": values},
                "publishes": publishes,
            }
        ],
        [
            {
                "artifact": artifact_name,
                "policy": "latest_successful",
                "freshness": "any",
            }
            for artifact_name in artifact_names
        ],
        artifact_names,
        hidden_inputs,
    )


def _phase_prompt_local_value_contract(
    artifact_name: str,
    *,
    context: _LoweringContext,
    span: SourceSpan,
    form_path: tuple[str, ...],
) -> dict[str, Any] | None:
    """Infer one prompt-input contract from flattened local type bindings."""

    field_path = tuple(segment for segment in artifact_name.split("__") if segment)
    if not field_path:
        return None
    current_type = context.local_type_bindings.get(field_path[0])
    if current_type is None:
        return None
    for field_name in field_path[1:]:
        if not isinstance(current_type, RecordTypeRef):
            return None
        current_type = context.type_env.record_field(
            current_type,
            field_name,
            span=span,
            form_path=form_path,
        )
    fields = derive_workflow_boundary_fields(
        current_type,
        generated_name=artifact_name,
        source_path=(artifact_name,),
        span=span,
        form_path=form_path,
    )
    if len(fields) != 1:
        return None
    return dict(fields[0].contract_definition)


def _flatten_phase_stdlib_prompt_inputs(
    expr: Any,
    *,
    base_name: str,
    local_values: Mapping[str, Any],
) -> list[tuple[str, Any]]:
    """Flatten record/tuple prompt inputs into materializable artifact inputs."""

    if isinstance(expr, tuple):
        flattened: list[tuple[str, Any]] = []
        for item in expr:
            item_value = _resolve_inline_expr_value(item, local_values=local_values)
            child_name = base_name
            if isinstance(item, FieldAccessExpr) and item.fields:
                child_name = item.fields[-1]
            elif isinstance(item, NameExpr):
                child_name = item.name
            elif isinstance(item_value, str) and item_value.startswith("inputs."):
                child_name = item_value.removeprefix("inputs.").split("__")[-1]
            flattened.extend(
                _flatten_phase_stdlib_prompt_inputs(
                    item,
                    base_name=child_name,
                    local_values=local_values,
                )
            )
        return flattened

    value = _resolve_inline_expr_value(expr, local_values=local_values)
    if isinstance(value, Mapping):
        flattened = []
        for field_name, field_value in value.items():
            child_name = field_name if base_name in {"inputs", "producer"} else f"{base_name}__{field_name}"
            flattened.extend(
                _flatten_phase_stdlib_prompt_inputs(
                    field_value,
                    base_name=child_name,
                    local_values=local_values,
                )
            )
        return flattened
    if isinstance(value, RecordExpr):
        flattened = []
        for field_name, field_expr in value.fields:
            child_name = field_name if base_name in {"inputs", "producer"} else f"{base_name}__{field_name}"
            flattened.extend(
                _flatten_phase_stdlib_prompt_inputs(
                    field_expr,
                    base_name=child_name,
                    local_values=local_values,
                )
            )
        return flattened
    return [(base_name, value if value is not None else expr)]


def _resolve_phase_prompt_input_source(
    expr: Any,
    *,
    artifact_name: str,
    context: _LoweringContext,
    local_values: Mapping[str, Any],
) -> tuple[dict[str, str], dict[str, LoweringOrigin]]:
    """Resolve a phase prompt input to a materialize_artifacts source node."""

    if isinstance(expr, PhaseTargetExpr):
        phase_scope = context.phase_scope
        if phase_scope is None:
            raise _compile_error(
                code="phase_translation_body_invalid",
                message="phase-target lowering requires an active phase scope",
                span=expr.span,
                form_path=expr.form_path,
            )
        target_ref = phase_scope.target_refs.get(expr.target_name)
        if target_ref is None:
            raise _compile_error(
                code="phase_target_unknown",
                message=f"`phase-target` does not support `{expr.target_name}` in this slice",
                span=expr.span,
                form_path=expr.form_path,
            )
        if (
            target_ref.startswith("inputs.")
            or target_ref.startswith("root.steps.")
            or target_ref.startswith("self.steps.")
            or target_ref.startswith("parent.steps.")
        ):
            return _materialize_source_from_ref(target_ref), {}
        hidden_input_name = f"__phase_prompt__{context.step_name_prefix}__{artifact_name}"
        return (
            {"input": hidden_input_name},
            {hidden_input_name: _origin_from_context_source(context, expr)},
        )

    value = _resolve_inline_expr_value(expr, local_values=local_values)
    if isinstance(value, str):
        return _materialize_source_from_ref(value), {}
    raise _compile_error(
        code="phase_translation_body_invalid",
        message="phase-scoped provider-result inputs must lower from workflow inputs or approved phase targets",
        span=expr.span,
        form_path=expr.form_path,
    )


def _materialize_source_from_ref(ref: str) -> dict[str, str]:
    """Convert a workflow ref into a materialize_artifacts source mapping."""

    if ref.startswith("inputs."):
        return {"input": ref.removeprefix("inputs.")}
    return {"ref": ref}


def _phase_prompt_report_target_inputs(
    exprs: list[Any],
    *,
    span: SourceSpan,
    form_path: tuple[str, ...],
) -> dict[str, PhaseTargetExpr]:
    """Validate and classify execution/progress report target expressions."""

    if len(exprs) != 2:
        raise _compile_error(
            code="phase_translation_body_invalid",
            message="phase-scoped provider-result requires both execution and progress report targets",
            span=span,
            form_path=form_path,
        )

    inputs_by_artifact: dict[str, PhaseTargetExpr] = {}
    for expr in exprs:
        if not isinstance(expr, PhaseTargetExpr):
            raise _compile_error(
                code="phase_translation_body_invalid",
                message="phase-scoped provider-result report inputs must be phase-target references",
                span=expr.span,
                form_path=expr.form_path,
            )
        artifact_name = _phase_prompt_artifact_name_for_target(expr)
        if artifact_name in inputs_by_artifact:
            raise _compile_error(
                code="phase_translation_body_invalid",
                message="phase-scoped provider-result requires each approved report target exactly once",
                span=expr.span,
                form_path=expr.form_path,
            )
        inputs_by_artifact[artifact_name] = expr

    missing = [
        artifact_name
        for artifact_name in ("execution_report_target", "progress_report_target")
        if artifact_name not in inputs_by_artifact
    ]
    if missing:
        raise _compile_error(
            code="phase_translation_body_invalid",
            message="phase-scoped provider-result requires both execution and progress report targets",
            span=span,
            form_path=form_path,
        )
    return inputs_by_artifact


def _phase_prompt_artifact_name_for_target(expr: PhaseTargetExpr) -> str:
    """Map approved phase targets to prompt artifact names."""

    if expr.target_name == "execution-report":
        return "execution_report_target"
    if expr.target_name == "progress-report":
        return "progress_report_target"
    raise _compile_error(
        code="phase_target_unknown",
        message=f"`phase-target` does not support `{expr.target_name}` in this slice",
        span=expr.span,
        form_path=expr.form_path,
    )


def _materialize_source_input_name(source: Mapping[str, str]) -> str | None:
    """Return the direct input name used by a materialization source."""

    input_name = source.get("input")
    if isinstance(input_name, str):
        return input_name
    return None


def _materialize_contract_input_name(source: Mapping[str, str]) -> str | None:
    """Return the input whose contract should govern a materialized source."""

    input_name = _materialize_source_input_name(source)
    if input_name is not None:
        return input_name
    ref = source.get("ref")
    if isinstance(ref, str) and ref.startswith("inputs."):
        return ref.removeprefix("inputs.")
    return None


def _authored_input_contract(
    input_name: str,
    *,
    context: _LoweringContext,
    span: SourceSpan,
    form_path: tuple[str, ...],
) -> dict[str, Any]:
    """Return a flattened workflow input contract by generated input name."""

    input_contract = context.authored_input_contracts.get(input_name)
    if input_contract is None:
        raise _compile_error(
            code="phase_translation_body_invalid",
            message=f"missing flattened workflow input contract for `{input_name}`",
            span=span,
            form_path=form_path,
        )
    return dict(input_contract)


def _phase_target_prompt_input_contract(target_expr: PhaseTargetExpr) -> dict[str, Any]:
    """Build the contract for an approved generated phase target."""

    spec = PHASE_TARGET_SPECS.get(target_expr.target_name)
    if spec is None:
        raise _compile_error(
            code="phase_target_unknown",
            message=f"`phase-target` does not support `{target_expr.target_name}` in this slice",
            span=target_expr.span,
            form_path=target_expr.form_path,
        )
    _, under_root, _ = spec
    return {
        "kind": "relpath",
        "type": "relpath",
        "under": under_root,
        "must_exist_target": False,
    }


def _phase_prompt_input_contract(
    artifact_name: str,
    *,
    input_name: str | None,
    context: _LoweringContext,
    span: SourceSpan,
    form_path: tuple[str, ...],
) -> dict[str, Any]:
    """Choose the contract for one phase prompt materialization artifact."""

    if artifact_name in {"design", "plan"}:
        return {"inherit": "source"}
    if input_name is None:
        raise _compile_error(
            code="phase_translation_body_invalid",
            message=f"missing flattened workflow input contract for `{artifact_name}`",
            span=span,
            form_path=form_path,
        )
    input_contract = context.authored_input_contracts.get(input_name)
    if input_contract is None:
        raise _compile_error(
            code="phase_translation_body_invalid",
            message=f"missing flattened workflow input contract for `{input_name}`",
            span=span,
            form_path=form_path,
        )
    return dict(input_contract)

def _surface_contract_from_structured_field(field: Mapping[str, Any]) -> dict[str, Any]:
    """Convert one JSON-bundle field contract to a workflow output contract.

    Structured-result contracts describe fields inside provider/command JSON
    bundles. Workflow outputs use the same basic scalar/path keys but omit
    bundle-only metadata, so this helper keeps just the fields the runtime
    output-contract validator understands.
    """

    definition = {
        key: value
        for key, value in field.items()
        if key in {"type", "allowed", "under", "must_exist_target"}
    }
    definition["kind"] = "relpath" if definition.get("type") == "relpath" else "scalar"
    return definition


def _union_case_contract_definitions(
    type_ref: UnionTypeRef,
    *,
    variant_name: str,
    workflow_name: str,
    step_name: str,
    span: SourceSpan,
    form_path: tuple[str, ...],
) -> dict[str, dict[str, Any]]:
    """Build the output contracts visible inside one union match case."""

    contract = derive_structured_result_contract(
        type_ref,
        workflow_name=workflow_name,
        step_id=step_name,
        span=span,
        form_path=form_path,
    )
    payload = contract.payload
    outputs = {
        "variant": _surface_contract_from_structured_field(payload["discriminant"]),
    }
    for field in payload["shared_fields"]:
        outputs[field["name"]] = _surface_contract_from_structured_field(field)
    variant_payload = payload["variants"][variant_name]
    for field in variant_payload["fields"]:
        outputs[field["name"]] = _surface_contract_from_structured_field(field)
    return outputs


def _review_loop_result_case_outputs(
    type_ref: Any,
    *,
    variant_name: str,
    source_step_name: str,
    context: _LoweringContext,
    span: SourceSpan,
    form_path: tuple[str, ...],
) -> dict[str, Any]:
    """Build branch outputs for one review-loop terminal variant."""

    return review_loop_result_case_outputs_owner(
        type_ref,
        variant_name=variant_name,
        source_step_name=source_step_name,
        context=context,
        span=span,
        form_path=form_path,
    )


def _review_loop_result_output_contracts(
    type_ref: Any,
    *,
    context: _LoweringContext,
    span: SourceSpan,
    form_path: tuple[str, ...],
) -> dict[str, dict[str, Any]]:
    """Build all flattened output contracts for a review-loop result union."""

    return review_loop_result_output_contracts_owner(
        type_ref,
        context=context,
        span=span,
        form_path=form_path,
    )


def _union_output_contracts(
    type_ref: Any,
    *,
    payload: Mapping[str, Any],
    span: SourceSpan,
    form_path: tuple[str, ...],
) -> dict[str, dict[str, Any]]:
    """Flatten all shared and variant-specific union output contracts."""

    if not isinstance(type_ref, UnionTypeRef):
        raise _compile_error(
            code="review_loop_result_contract_invalid",
            message="`review-revise-loop` lowering requires a union return type",
            span=span,
            form_path=form_path,
        )
    outputs = {
        "variant": _surface_contract_from_structured_field(payload["discriminant"]),
    }
    for field in payload["shared_fields"]:
        outputs[field["name"]] = _surface_contract_from_structured_field(field)
    for variant_payload in payload["variants"].values():
        for field in variant_payload["fields"]:
            definition = _surface_contract_from_structured_field(field)
            if definition.get("type") == "relpath":
                definition["must_exist_target"] = False
            outputs.setdefault(field["name"], definition)
    return outputs



def _join_ref_path(base_ref: str, suffix: str) -> str:
    """Append a path suffix to a substitution ref without losing templating."""

    if base_ref.startswith("${"):
        return f"{base_ref}/{suffix}"
    return "${" + base_ref + "}/" + suffix
