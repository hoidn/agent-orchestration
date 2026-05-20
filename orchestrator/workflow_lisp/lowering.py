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
from collections.abc import Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from types import MappingProxyType
from typing import Any

from orchestrator.loader import WorkflowLoader
from orchestrator.workflow.executable_ir import ProviderStepConfig
from orchestrator.workflow.elaboration import elaborate_surface_workflow
from orchestrator.workflow.loaded_bundle import LoadedWorkflowBundle, workflow_managed_write_root_inputs
from orchestrator.workflow.lowering import lower_surface_workflow
from orchestrator.workflow.surface_ast import SurfaceStepKind

from .definitions import elaborate_definition_module
from .contracts import (
    GeneratedInternalInput,
    WorkflowBoundaryProjection,
    derive_structured_result_contract,
    derive_workflow_boundary_fields,
    derive_workflow_signature_contracts,
)
from .diagnostics import LispFrontendCompileError, LispFrontendDiagnostic
from .expressions import (
    BacklogDrainExpr,
    CallExpr,
    CommandResultExpr,
    FinalizeSelectedItemExpr,
    FieldAccessExpr,
    LetStarExpr,
    LiteralExpr,
    MatchExpr,
    NameExpr,
    PhaseTargetExpr,
    ProduceOneOfExpr,
    ProcedureCallExpr,
    ProviderResultExpr,
    ResourceTransitionExpr,
    RecordExpr,
    ResumeOrStartExpr,
    ReviewReviseLoopExpr,
    RunProviderPhaseExpr,
    WithPhaseExpr,
)
from .phase import (
    IMPLEMENTATION_ATTEMPT_PHASE_NAME,
    PHASE_TARGET_SPECS,
    PhaseScope,
    is_implementation_attempt_result_type,
)
from .macros import collect_macro_catalog, expand_module_forms
from .reader import read_sexpr_file
from .spans import SourceSpan
from .syntax import WorkflowLispSyntaxModule, build_syntax_module, syntax_head_name, syntax_node_datum
from .type_env import FrontendTypeEnvironment, PathTypeRef, RecordTypeRef, TypeRef, UnionTypeRef
from .typecheck import TypedExpr
from .procedures import ProcedureCatalog, ProcedureLoweringMode, TypedProcedureDef
from .workflows import (
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

_GENERATED_STEP_ID_RE = re.compile(r"[^A-Za-z0-9_]+")


@dataclass(frozen=True)
class LoweringOrigin:
    """Frontend source location for generated workflow dictionary entries.

    Shared loader and semantic-IR diagnostics are usually phrased in terms of
    generated step names, flattened input names, or generated artifact paths.
    A `LoweringOrigin` is the source-map payload used to translate those
    generated names back to the `.orc` span, form path, macro expansion stack,
    and any procedure-lowering notes that explain why the node exists.
    """

    span: SourceSpan
    form_path: tuple[str, ...]
    expansion_stack: tuple[object, ...] = ()
    notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class LoweringOriginMap:
    """Complete source-map index for one lowered workflow.

    Lowering creates more than steps: it also synthesizes boundary inputs,
    internal write roots, projected outputs, and artifact/pointer paths. This
    map records an origin for each generated surface so validation failures
    from the shared YAML-shaped pipeline can be reported against frontend
    source instead of opaque generated names.
    """

    workflow_origin: LoweringOrigin
    step_spans: Mapping[str, LoweringOrigin]
    authored_input_spans: Mapping[str, LoweringOrigin]
    internal_input_spans: Mapping[str, LoweringOrigin]
    generated_output_spans: Mapping[str, LoweringOrigin]
    generated_path_spans: Mapping[str, LoweringOrigin]

    @property
    def workflow_span(self) -> SourceSpan:
        """Return the source span for the workflow definition itself."""

        return self.workflow_origin.span

    @property
    def generated_input_spans(self) -> Mapping[str, LoweringOrigin]:
        """Return authored and synthetic input origins as one mapping."""

        return MappingProxyType({**dict(self.authored_input_spans), **dict(self.internal_input_spans)})


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
    workflows_by_name = {
        **{workflow.definition.name: workflow for workflow in typed_workflows},
        **private_workflows,
    }
    resolved_type_env = type_env or FrontendTypeEnvironment.from_module(_definition_only_module(workflow_path))
    lowered_by_name: dict[str, LoweredWorkflow] = {}
    visiting: set[str] = set()

    def lower_one(workflow_name: str) -> LoweredWorkflow:
        """Lower one workflow after recursively lowering local callees."""

        existing = lowered_by_name.get(workflow_name)
        if existing is not None:
            return existing
        if workflow_name in visiting:
            workflow = workflows_by_name[workflow_name]
            raise LispFrontendCompileError(
                (
                    LispFrontendDiagnostic(
                        code="workflow_signature_mismatch",
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
        ):
            if dependency in workflows_by_name:
                lower_one(dependency)

        lowered = _lower_one_workflow(
            typed_workflow,
            workflow_path=workflow_path,
            workflow_catalog=workflow_catalog,
            imported_workflow_bundles=imported_workflow_bundles or {},
            extern_environment=extern_environment,
            command_boundary_environment=command_boundary_environment,
            lowered_callees=lowered_by_name,
            type_env=resolved_type_env,
            typed_procedures=resolved_procedures,
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
    workflow_catalog: WorkflowCatalog,
    imported_workflow_bundles: Mapping[str, LoadedWorkflowBundle],
    extern_environment: ExternEnvironment,
    command_boundary_environment: CommandBoundaryEnvironment,
    lowered_callees: Mapping[str, LoweredWorkflow],
    type_env: FrontendTypeEnvironment,
    typed_procedures: Mapping[str, TypedProcedureDef],
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
        type_env=type_env,
        step_spans={},
        generated_input_spans=origin_inputs,
        authored_generated_inputs=set(authored_inputs),
        internal_generated_input_reasons={},
        generated_output_spans=origin_outputs,
        generated_path_spans={},
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
    )
    local_values = _signature_local_values(typed_workflow)
    steps, terminal = _lower_expression(typed_workflow.typed_body, context=context, local_values=local_values)

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
        ),
        "steps": steps,
    }
    if context.top_level_artifacts:
        authored_mapping["artifacts"] = dict(context.top_level_artifacts)

    return LoweredWorkflow(
        typed_workflow=typed_workflow,
        authored_mapping=authored_mapping,
        origin_map=LoweringOriginMap(
            workflow_origin=LoweringOrigin(
                span=workflow_origin.span,
                form_path=workflow_origin.form_path,
                expansion_stack=workflow_origin.expansion_stack,
                notes=context.origin_notes or workflow_origin.notes,
            ),
            step_spans=MappingProxyType(dict(context.step_spans)),
            authored_input_spans=MappingProxyType(dict(authored_input_spans)),
            internal_input_spans=MappingProxyType(dict(internal_input_spans)),
            generated_output_spans=MappingProxyType(dict(context.generated_output_spans)),
            generated_path_spans=MappingProxyType(dict(context.generated_path_spans)),
        ),
        boundary_projection=finalized_projection,
    )


@dataclass
class _TerminalResult:
    """Outputs produced by the last lowered expression in a workflow fragment.

    `output_refs` maps frontend return field names to shared workflow refs.
    `hidden_inputs` records generated write roots that must be added to the
    workflow boundary after expression lowering.
    """

    step_name: str
    step_id: str
    output_refs: Mapping[str, str]
    output_kind: str
    hidden_inputs: Mapping[str, LoweringOrigin]


@dataclass
class _LoweringContext:
    """Mutable state threaded through expression lowering.

    The context owns generated step names, source-map origins, top-level
    artifacts, hidden inputs, active phase scope, and lookup tables for external
    providers, command adapters, procedures, workflows, and imported bundles.
    """

    workflow_name: str
    step_name_prefix: str
    workflow_path: Path
    signature: object
    authored_input_contracts: Mapping[str, Mapping[str, Any]]
    workflow_catalog: WorkflowCatalog
    imported_workflow_bundles: Mapping[str, LoadedWorkflowBundle]
    extern_environment: ExternEnvironment
    command_boundary_environment: CommandBoundaryEnvironment
    lowered_callees: Mapping[str, LoweredWorkflow]
    typed_procedures: Mapping[str, TypedProcedureDef]
    type_env: FrontendTypeEnvironment
    step_spans: dict[str, LoweringOrigin]
    generated_input_spans: dict[str, LoweringOrigin]
    authored_generated_inputs: set[str]
    internal_generated_input_reasons: dict[str, str]
    generated_output_spans: Mapping[str, LoweringOrigin]
    generated_path_spans: dict[str, LoweringOrigin]
    top_level_artifacts: dict[str, Any]
    inline_call_counters: dict[str, int]
    origin_notes: tuple[str, ...]
    boundary_projection: WorkflowBoundaryProjection
    return_output_contracts: Mapping[str, Mapping[str, Any]]
    phase_scope: "_ActivePhaseScope | None" = None


@dataclass(frozen=True)
class _ActivePhaseScope:
    """Derived state and artifact refs installed by `with-phase`.

    Phase stdlib forms such as `run-provider-phase` and `produce-one-of` use
    this scope to find canonical bundle paths, temporary bundle paths, snapshot
    roots, candidate roots, and named artifact targets. Keeping those refs here
    prevents high-level frontend code from hand-constructing state paths.
    """

    scope: PhaseScope
    bundle_path_ref: str
    target_refs: Mapping[str, str]
    temp_bundle_path_ref: str | None = None
    snapshot_root_ref: str | None = None
    candidate_root_ref: str | None = None
    runtime_phase_name_ref: str | None = None


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

    missing = next(
        (
            field.generated_name
            for field in boundary_projection.flattened_inputs
            if field.generated_name not in authored_input_spans
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


def _origin_from_source(source: object, *, span: SourceSpan | None = None) -> LoweringOrigin:
    """Build a source-map origin from any typed frontend node-like object."""

    origin_span = span or getattr(source, "span")
    return LoweringOrigin(
        span=origin_span,
        form_path=getattr(source, "form_path", ()),
        expansion_stack=getattr(source, "expansion_stack", ()),
    )


def _origin_from_context_source(context: _LoweringContext, source: object, *, span: SourceSpan | None = None) -> LoweringOrigin:
    """Build an origin and attach active procedure/lowering provenance notes."""

    base = _origin_from_source(source, span=span)
    if not context.origin_notes:
        return base
    return LoweringOrigin(
        span=base.span,
        form_path=base.form_path,
        expansion_stack=base.expansion_stack,
        notes=context.origin_notes,
    )


def _record_step_origin(context: _LoweringContext, *, step_name: str, step_id: str, source: object) -> None:
    """Record both human step name and stable id as aliases to one origin."""

    origin = _origin_from_context_source(context, source)
    context.step_spans[step_name] = origin
    context.step_spans[step_id] = origin


def _lower_expression(
    typed_expr: TypedExpr,
    *,
    context: _LoweringContext,
    local_values: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], _TerminalResult]:
    """Dispatch one typed frontend expression to its concrete lowering routine.

    Every branch returns generated shared workflow steps plus the terminal output
    references that represent the frontend expression value for enclosing forms.
    """

    expr = typed_expr.expr
    if isinstance(expr, CommandResultExpr):
        return _lower_command_result(typed_expr, context=context, local_values=local_values)
    if isinstance(expr, ProviderResultExpr):
        return _lower_provider_result(
            expr,
            result_type=typed_expr.type_ref,
            context=context,
            local_values=local_values,
        )
    if isinstance(expr, RunProviderPhaseExpr):
        return _lower_run_provider_phase(typed_expr, context=context, local_values=local_values)
    if isinstance(expr, ProduceOneOfExpr):
        return _lower_produce_one_of(typed_expr, context=context, local_values=local_values)
    if isinstance(expr, ReviewReviseLoopExpr):
        return _lower_review_revise_loop(typed_expr, context=context, local_values=local_values)
    if isinstance(expr, ResumeOrStartExpr):
        return _lower_resume_or_start(typed_expr, context=context, local_values=local_values)
    if isinstance(expr, ResourceTransitionExpr):
        return _lower_resource_transition(typed_expr, context=context, local_values=local_values)
    if isinstance(expr, FinalizeSelectedItemExpr):
        return _lower_finalize_selected_item(typed_expr, context=context, local_values=local_values)
    if isinstance(expr, BacklogDrainExpr):
        return _lower_backlog_drain(typed_expr, context=context, local_values=local_values)
    if isinstance(expr, CallExpr):
        return _lower_call_expr(typed_expr, context=context, local_values=local_values)
    if isinstance(expr, ProcedureCallExpr):
        return _lower_procedure_call_expr(typed_expr, context=context, local_values=local_values)
    if isinstance(expr, RecordExpr):
        return _lower_record_expr(typed_expr, context=context, local_values=local_values)
    if isinstance(expr, LetStarExpr):
        return _lower_let_star(typed_expr, context=context, local_values=local_values)
    if isinstance(expr, WithPhaseExpr):
        return _lower_with_phase(typed_expr, context=context, local_values=local_values)
    raise _compile_error(
        code="workflow_return_not_exportable",
        message=f"workflow `{context.workflow_name}` cannot lower expression `{type(expr).__name__}` in Stage 3",
        span=typed_expr.span,
        form_path=typed_expr.form_path,
    )


def _lower_command_result(
    typed_expr: TypedExpr,
    *,
    context: _LoweringContext,
    local_values: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], _TerminalResult]:
    """Lower a typed command call to a validating workflow command step.

    In `.orc`, `command-result` means "run this named command boundary and
    treat its JSON output as a typed result." Lowering turns that into an
    ordinary workflow `command` step, appends rendered frontend arguments,
    attaches an `output_bundle` or `variant_output` contract, and exposes refs
    only to fields from the validated JSON bundle.
    """

    expr = typed_expr.expr
    assert isinstance(expr, CommandResultExpr)
    step_name = f"{context.step_name_prefix}__{expr.step_name}"
    step_id = _normalize_generated_step_id(step_name)
    binding = context.command_boundary_environment.bindings_by_name[expr.step_name]
    hidden_input_name = f"__write_root__{step_id}__result_bundle"
    bundle_contract = derive_structured_result_contract(
        typed_expr.type_ref,
        workflow_name=context.workflow_name,
        step_id=step_name,
        span=expr.span,
        form_path=expr.form_path,
    )
    authored_contract = dict(bundle_contract.payload)
    authored_contract["path"] = f"${{inputs.{hidden_input_name}}}"
    _record_step_origin(context, step_name=step_name, step_id=step_id, source=expr)
    context.generated_path_spans[authored_contract["path"]] = _origin_from_context_source(context, expr)

    command = list(binding.stable_command)
    command.extend(_render_argv_tail(expr.argv[len(binding.stable_command) :], local_values=local_values))
    step: dict[str, Any] = {
        "name": step_name,
        "id": step_id,
        "command": command,
        bundle_contract.contract_kind: authored_contract,
    }
    return [step], _TerminalResult(
        step_name=step_name,
        step_id=step_id,
        output_refs=_record_output_refs(step_name, typed_expr.type_ref),
        output_kind="step",
        hidden_inputs={hidden_input_name: _origin_from_context_source(context, expr)},
    )


def _lower_resource_transition(
    typed_expr: TypedExpr,
    *,
    context: _LoweringContext,
    local_values: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], _TerminalResult]:
    """Lower a resource move into a typed certified-adapter command.

    `resource-transition` is the frontend form for queue/item movement plus
    any associated ledger update. The current backend is a named Python adapter
    with declared inputs, outputs, and effects, so workflow source does not need
    inline Python to move files or reconstruct run state.
    """

    expr = typed_expr.expr
    assert isinstance(expr, ResourceTransitionExpr)
    binding = context.command_boundary_environment.bindings_by_name["apply_resource_transition"]
    step_name = context.step_name_prefix
    step_id = _normalize_generated_step_id(step_name)
    hidden_input_name = f"__write_root__{step_id}__result_bundle"
    bundle_contract = derive_structured_result_contract(
        typed_expr.type_ref,
        workflow_name=context.workflow_name,
        step_id=step_name,
        span=expr.span,
        form_path=expr.form_path,
    )
    authored_contract = dict(bundle_contract.payload)
    authored_contract["path"] = f"${{inputs.{hidden_input_name}}}"
    _record_step_origin(context, step_name=step_name, step_id=step_id, source=expr)
    context.generated_path_spans[authored_contract["path"]] = _origin_from_context_source(context, expr)
    payload = _resource_transition_payload(expr, context=context, local_values=local_values)
    step = {
        "name": step_name,
        "id": step_id,
        "command": [*binding.stable_command, json.dumps(payload)],
        bundle_contract.contract_kind: authored_contract,
    }
    when = _render_boolean_predicate(expr.spec.when_expr, local_values=local_values)
    if when is not None:
        step["when"] = when
    return [step], _TerminalResult(
        step_name=step_name,
        step_id=step_id,
        output_refs=_record_output_refs(step_name, typed_expr.type_ref),
        output_kind="step",
        hidden_inputs={hidden_input_name: _origin_from_context_source(context, expr)},
    )


def _lower_provider_result(
    expr: ProviderResultExpr,
    *,
    result_type: TypeRef,
    context: _LoweringContext,
    local_values: Mapping[str, Any],
    step_name: str | None = None,
) -> tuple[list[dict[str, Any]], _TerminalResult]:
    """Lower a typed provider call to a validating workflow provider step.

    In `.orc`, `provider-result` means "ask a configured provider to produce a
    typed record or union." Lowering emits a provider step, points it at the
    prompt asset, injects the expected JSON contract, and stores the semantic
    result in a generated structured bundle. Reports may be artifacts, but the
    validated bundle is what later steps read.
    """

    provider_step_name = step_name or f"{context.step_name_prefix}__result"
    provider_step_id = _normalize_generated_step_id(provider_step_name)
    hidden_input_name = f"__write_root__{provider_step_id}__result_bundle"
    provider_binding = context.extern_environment.bindings_by_name.get(expr.provider.name)
    prompt_binding = context.extern_environment.bindings_by_name.get(expr.prompt.name)
    if not isinstance(provider_binding, ProviderExtern) or not isinstance(prompt_binding, PromptExtern):
        raise _compile_error(
            code="provider_result_provider_invalid",
            message="provider-result lowering requires validated provider/prompt externs",
            span=expr.span,
            form_path=expr.form_path,
        )
    bundle_contract = derive_structured_result_contract(
        result_type,
        workflow_name=context.workflow_name,
        step_id=provider_step_name,
        span=expr.span,
        form_path=expr.form_path,
    )
    authored_contract = dict(bundle_contract.payload)
    hidden_inputs: dict[str, LoweringOrigin] = {}
    generated_steps: list[dict[str, Any]] = []
    provider_step: dict[str, Any] = {
        "name": provider_step_name,
        "id": provider_step_id,
        "provider": provider_binding.provider_id,
        "asset_file": prompt_binding.asset_file,
        "inject_output_contract": True,
        bundle_contract.contract_kind: authored_contract,
    }
    if context.phase_scope is not None and is_implementation_attempt_result_type(result_type):
        authored_contract["path"] = _template_for_ref(context.phase_scope.bundle_path_ref)
        generated_steps.extend(
            _build_phase_prompt_input_prelude(
                expr,
                context=context,
                local_values=local_values,
            )
        )
        provider_step["consumes"] = [
            {
                "artifact": "design",
                "policy": "latest_successful",
                "freshness": "any",
            },
            {
                "artifact": "plan",
                "policy": "latest_successful",
                "freshness": "any",
            },
            {
                "artifact": "execution_report_target",
                "policy": "latest_successful",
                "freshness": "any",
            },
            {
                "artifact": "progress_report_target",
                "policy": "latest_successful",
                "freshness": "any",
            },
        ]
        provider_step["prompt_consumes"] = [
            "design",
            "plan",
            "execution_report_target",
            "progress_report_target",
        ]
    else:
        authored_contract["path"] = f"${{inputs.{hidden_input_name}}}"
        hidden_inputs[hidden_input_name] = _origin_from_context_source(context, expr)
    _record_step_origin(context, step_name=provider_step_name, step_id=provider_step_id, source=expr)
    context.generated_path_spans[authored_contract["path"]] = _origin_from_context_source(context, expr)
    generated_steps.append(provider_step)
    return generated_steps, _TerminalResult(
        step_name=provider_step_name,
        step_id=provider_step_id,
        output_refs=_record_output_refs(provider_step_name, result_type),
        output_kind="step",
        hidden_inputs=hidden_inputs,
    )


def _lower_run_provider_phase(
    typed_expr: TypedExpr,
    *,
    context: _LoweringContext,
    local_values: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], _TerminalResult]:
    """Lower the phase helper that runs one provider-backed phase.

    `run-provider-phase` is a convenience form over `provider-result` for phase
    code that has a `with-phase` context. It derives prompt-input
    materializations, consumed-artifact metadata, and the phase result JSON path
    from that context instead of making the `.orc` author spell those paths.
    """

    expr = typed_expr.expr
    assert isinstance(expr, RunProviderPhaseExpr)
    if context.phase_scope is None:
        raise _compile_error(
            code="phase_translation_body_invalid",
            message="`run-provider-phase` lowering requires an active phase scope",
            span=expr.span,
            form_path=expr.form_path,
        )
    _require_phase_scope_name_match(
        context.phase_scope,
        authored_name=expr.phase_name,
        form_name="run-provider-phase",
        span=expr.span,
        form_path=expr.form_path,
    )
    provider_binding = context.extern_environment.bindings_by_name.get(expr.provider.name)
    prompt_binding = context.extern_environment.bindings_by_name.get(expr.prompt.name)
    if not isinstance(provider_binding, ProviderExtern) or not isinstance(prompt_binding, PromptExtern):
        raise _compile_error(
            code="provider_result_provider_invalid",
            message="run-provider-phase lowering requires validated provider/prompt externs",
            span=expr.span,
            form_path=expr.form_path,
        )
    step_name = context.step_name_prefix
    step_id = _normalize_generated_step_id(step_name)
    bundle_contract = derive_structured_result_contract(
        typed_expr.type_ref,
        workflow_name=context.workflow_name,
        step_id=step_name,
        span=expr.span,
        form_path=expr.form_path,
    )
    authored_contract = dict(bundle_contract.payload)
    authored_contract["path"] = context.phase_scope.bundle_path_ref
    _record_step_origin(context, step_name=step_name, step_id=step_id, source=expr)
    generated_steps, consumes, prompt_consumes, hidden_inputs = _build_phase_stdlib_prompt_input_prelude(
        (
            ("inputs", expr.inputs_expr),
            (
                "execution_report_target",
                PhaseTargetExpr("execution-report", expr.span, expr.form_path, expr.expansion_stack),
            ),
            (
                "progress_report_target",
                PhaseTargetExpr("progress-report", expr.span, expr.form_path, expr.expansion_stack),
            ),
        ),
        context=context,
        local_values=local_values,
        source_expr=expr,
    )
    step = {
        "name": step_name,
        "id": step_id,
        "provider": provider_binding.provider_id,
        "asset_file": prompt_binding.asset_file,
        "inject_output_contract": True,
        bundle_contract.contract_kind: authored_contract,
        "consumes": consumes,
        "prompt_consumes": prompt_consumes,
    }
    generated_steps.append(step)
    return generated_steps, _TerminalResult(
        step_name=step_name,
        step_id=step_id,
        output_refs=_record_output_refs(step_name, typed_expr.type_ref),
        output_kind="step",
        hidden_inputs=hidden_inputs,
    )


def _lower_produce_one_of(
    typed_expr: TypedExpr,
    *,
    context: _LoweringContext,
    local_values: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], _TerminalResult]:
    """Lower candidate-file production to evidence-backed variant selection.

    `produce-one-of` is used when a producer may create exactly one of several
    candidate outputs, such as a completed report or blocked-progress report.
    Lowering records file state before the producer runs, runs the producer,
    uses `select_variant_output` to prove which candidate changed, and exposes
    only the fields for the selected variant.
    """

    expr = typed_expr.expr
    assert isinstance(expr, ProduceOneOfExpr)
    if context.phase_scope is None or context.phase_scope.snapshot_root_ref is None:
        raise _compile_error(
            code="phase_translation_body_invalid",
            message="`produce-one-of` lowering requires an active generic phase scope",
            span=expr.span,
            form_path=expr.form_path,
        )
    provider_binding = context.extern_environment.bindings_by_name.get(expr.producer.provider_expr.name)
    prompt_binding = context.extern_environment.bindings_by_name.get(expr.producer.prompt_expr.name)
    if not isinstance(provider_binding, ProviderExtern) or not isinstance(prompt_binding, PromptExtern):
        raise _compile_error(
            code="provider_result_provider_invalid",
            message="produce-one-of lowering requires validated provider/prompt externs",
            span=expr.span,
            form_path=expr.form_path,
        )
    step_prefix = context.step_name_prefix
    execute_step_name = f"{step_prefix}__produce"
    execute_step_id = _normalize_generated_step_id(execute_step_name)
    select_step_name = f"{step_prefix}__select_variant"
    select_step_id = _normalize_generated_step_id(select_step_name)
    result_step_name = step_prefix
    result_step_id = _normalize_generated_step_id(result_step_name)
    _record_step_origin(context, step_name=execute_step_name, step_id=execute_step_id, source=expr)
    _record_step_origin(context, step_name=select_step_name, step_id=select_step_id, source=expr)
    select_contract = derive_structured_result_contract(
        typed_expr.type_ref,
        workflow_name=context.workflow_name,
        step_id=select_step_name,
        span=expr.span,
        form_path=expr.form_path,
    )
    select_payload = dict(select_contract.payload)
    select_payload["path"] = context.phase_scope.bundle_path_ref
    select_payload["evidence"] = {
        "mode": "snapshot_diff",
        "snapshot": {
            "ref": f"root.steps.{execute_step_name}.snapshots.{step_prefix}_before",
        },
    }
    generated_steps, consumes, prompt_consumes, hidden_inputs = _build_phase_stdlib_prompt_input_prelude(
        (
            ("producer", expr.producer.inputs),
            (
                "execution_report_target",
                PhaseTargetExpr("execution-report", expr.span, expr.form_path, expr.expansion_stack),
            ),
            (
                "progress_report_target",
                PhaseTargetExpr("progress-report", expr.span, expr.form_path, expr.expansion_stack),
            ),
        ),
        context=context,
        local_values=local_values,
        source_expr=expr,
    )
    prompt_input_step_name = generated_steps[0]["name"]
    snapshot_candidates = {
        candidate.variant_name: {
            "ref": f"root.steps.{prompt_input_step_name}.artifacts.{_render_candidate_target_artifact_name(candidate)}"
        }
        for candidate in expr.candidates
    }
    union_payload = derive_structured_result_contract(
        typed_expr.type_ref,
        workflow_name=context.workflow_name,
        step_id=result_step_name,
        span=expr.span,
        form_path=expr.form_path,
    ).payload
    output_contracts = _union_output_contracts(
        typed_expr.type_ref,
        payload=union_payload,
        span=expr.span,
        form_path=expr.form_path,
    )
    shared_field_names = {field["name"] for field in union_payload["shared_fields"]}

    def _produce_one_of_case_block(variant_name: str) -> dict[str, Any]:
        variant_payload = union_payload["variants"][variant_name]
        variant_field_names = {field["name"] for field in variant_payload["fields"]}
        variant_relpath_fields = [
            field["name"] for field in variant_payload["fields"] if field.get("type") == "relpath"
        ]
        fallback_relpath_ref = None
        if variant_relpath_fields:
            fallback_relpath_ref = f"root.steps.{select_step_name}.artifacts.{variant_relpath_fields[0]}"
        local_values_payload: list[dict[str, Any]] = []
        case_outputs: dict[str, Any] = {}

        for field_name, definition in output_contracts.items():
            if field_name == "variant":
                case_outputs[field_name] = {
                    **definition,
                    "from": {"ref": f"root.steps.{select_step_name}.artifacts.variant"},
                }
                continue
            if field_name in variant_field_names:
                case_outputs[field_name] = {
                    **definition,
                    "from": {"ref": f"root.steps.{select_step_name}.artifacts.{field_name}"},
                }
                continue
            if field_name in shared_field_names:
                if definition.get("kind") == "scalar" and definition.get("type") == "enum" and variant_name in definition.get("allowed", []):
                    local_values_payload.append(
                        {
                            "name": field_name,
                            "source": {"literal": variant_name},
                            "contract": dict(definition),
                        }
                    )
                    case_outputs[field_name] = {
                        **definition,
                        "from": {"ref": f"self.steps.MaterializeSharedFields.artifacts.{field_name}"},
                    }
                    continue
                if definition.get("kind") == "scalar" and definition.get("type") == "string":
                    local_values_payload.append(
                        {
                            "name": field_name,
                            "source": {"literal": variant_name.lower()},
                            "contract": dict(definition),
                        }
                    )
                    case_outputs[field_name] = {
                        **definition,
                        "from": {"ref": f"self.steps.MaterializeSharedFields.artifacts.{field_name}"},
                    }
                    continue
            if definition.get("kind") == "relpath" and fallback_relpath_ref is not None:
                case_outputs[field_name] = {
                    **definition,
                    "from": {"ref": fallback_relpath_ref},
                }
                continue
            if definition.get("kind") == "scalar" and definition.get("type") == "enum":
                allowed = definition.get("allowed", [])
                literal_value = allowed[0] if isinstance(allowed, list) and allowed else variant_name
                local_values_payload.append(
                    {
                        "name": field_name,
                        "source": {"literal": literal_value},
                        "contract": dict(definition),
                    }
                )
                case_outputs[field_name] = {
                    **definition,
                    "from": {"ref": f"self.steps.MaterializeSharedFields.artifacts.{field_name}"},
                }
                continue
            if definition.get("kind") == "scalar" and definition.get("type") == "string":
                local_values_payload.append(
                    {
                        "name": field_name,
                        "source": {"literal": variant_name.lower()},
                        "contract": dict(definition),
                    }
                )
                case_outputs[field_name] = {
                    **definition,
                    "from": {"ref": f"self.steps.MaterializeSharedFields.artifacts.{field_name}"},
                }
                continue
            raise _compile_error(
                code="produce_one_of_candidate_invalid",
                message=f"`produce-one-of` cannot normalize field `{field_name}` for variant `{variant_name}` in this slice",
                span=expr.span,
                form_path=expr.form_path,
            )

        case_steps: list[dict[str, Any]] = []
        if local_values_payload:
            case_steps.append(
                {
                    "name": "MaterializeSharedFields",
                    "id": "materialize_shared_fields",
                    "materialize_artifacts": {"values": local_values_payload},
                }
            )
        case_steps.append(
            _build_match_projection_anchor_step(
                match_step_name=result_step_name,
                variant_name=variant_name,
                case_outputs=case_outputs,
                context=context,
                span=expr.span,
            )
        )
        return {
            "id": _normalize_generated_step_id(f"{result_step_name}__{variant_name.lower()}"),
            "outputs": case_outputs,
            "steps": case_steps,
        }

    generated_steps.extend(
        [
            {
                "name": execute_step_name,
                "id": execute_step_id,
                "pre_snapshot": {
                    "name": f"{step_prefix}_before",
                    "digest": "sha256",
                    "candidates": snapshot_candidates,
                },
                "provider": provider_binding.provider_id,
                "asset_file": prompt_binding.asset_file,
                "consumes": consumes,
                "prompt_consumes": prompt_consumes,
            },
            {
                "name": select_step_name,
                "id": select_step_id,
                "select_variant_output": select_payload,
            },
            {
                "name": result_step_name,
                "id": result_step_id,
                "match": {
                    "ref": f"root.steps.{select_step_name}.artifacts.variant",
                    "cases": {
                        variant_name: _produce_one_of_case_block(variant_name)
                        for variant_name in union_payload["variants"]
                    },
                },
            },
        ]
    )
    return generated_steps, _TerminalResult(
        step_name=result_step_name,
        step_id=result_step_id,
        output_refs=_record_output_refs(result_step_name, typed_expr.type_ref),
        output_kind="match",
        hidden_inputs=hidden_inputs,
    )


def _lower_review_revise_loop(
    typed_expr: TypedExpr,
    *,
    context: _LoweringContext,
    local_values: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], _TerminalResult]:
    """Lower `review-revise-loop` to a generated `repeat_until` review workflow.

    The helper builds review, fix, and terminal projection steps while keeping
    the public result as a typed union. Markdown reports stay artifacts; the
    structured provider result is the authority for the review decision.
    """

    expr = typed_expr.expr
    assert isinstance(expr, ReviewReviseLoopExpr)
    if context.phase_scope is None:
        raise _compile_error(
            code="phase_translation_body_invalid",
            message="`review-revise-loop` lowering requires an active phase scope",
            span=expr.span,
            form_path=expr.form_path,
        )
    _require_phase_scope_name_match(
        context.phase_scope,
        authored_name=expr.loop_name,
        form_name="review-revise-loop",
        span=expr.span,
        form_path=expr.form_path,
    )
    repeat_step_name = f"{context.step_name_prefix}__loop"
    repeat_step_id = _normalize_generated_step_id(repeat_step_name)
    result_step_name = context.step_name_prefix
    result_step_id = _normalize_generated_step_id(result_step_name)
    _record_step_origin(context, step_name=repeat_step_name, step_id=repeat_step_id, source=expr)
    _record_step_origin(context, step_name=result_step_name, step_id=result_step_id, source=expr)
    review_contract_path = _join_ref_path(
        context.phase_scope.candidate_root_ref or "inputs.phase-ctx__state-root",
        "review-loop/review-result.json",
    )
    review_output_bundle = {
        "path": review_contract_path,
        "fields": [
            {
                "name": "review_decision",
                "json_pointer": "/review_decision",
                "type": "enum",
                "allowed": ["APPROVE", "REVISE", "BLOCKED"],
            },
            {
                "name": "checks_report",
                "json_pointer": "/checks_report",
                "type": "relpath",
                "under": "artifacts/work",
                "must_exist_target": True,
            },
            {
                "name": "review_report",
                "json_pointer": "/review_report",
                "type": "relpath",
                "under": "artifacts/work",
                "must_exist_target": True,
            },
            {
                "name": "progress_report",
                "json_pointer": "/progress_report",
                "type": "relpath",
                "under": "artifacts/work",
                "must_exist_target": True,
            },
            {
                "name": "blocker_class",
                "json_pointer": "/blocker_class",
                "type": "enum",
                "allowed": [
                    "missing_resource",
                    "unavailable_hardware",
                    "roadmap_conflict",
                    "external_dependency_outside_authority",
                    "user_decision_required",
                    "unrecoverable_after_fix_attempt",
                ],
            },
        ],
    }
    review_provider = context.extern_environment.bindings_by_name.get(expr.review_provider.name)
    fix_provider = context.extern_environment.bindings_by_name.get(expr.fix_provider.name)
    review_prompt = context.extern_environment.bindings_by_name.get(expr.review_prompt.name)
    fix_prompt = context.extern_environment.bindings_by_name.get(expr.fix_prompt.name)
    if not isinstance(review_provider, ProviderExtern) or not isinstance(fix_provider, ProviderExtern):
        raise _compile_error(
            code="provider_result_provider_invalid",
            message="review-revise-loop lowering requires validated provider externs",
            span=expr.span,
            form_path=expr.form_path,
        )
    if not isinstance(review_prompt, PromptExtern) or not isinstance(fix_prompt, PromptExtern):
        raise _compile_error(
            code="provider_result_provider_invalid",
            message="review-revise-loop lowering requires validated prompt externs",
            span=expr.span,
            form_path=expr.form_path,
        )
    generated_steps, consumes, prompt_consumes, hidden_inputs = _build_phase_stdlib_prompt_input_prelude(
        (
            ("completed", expr.completed_expr),
            ("inputs", expr.inputs_expr),
        ),
        context=context,
        local_values=local_values,
        source_expr=expr,
    )
    review_result_ref = "parent.steps.ReviewDecision.artifacts"
    route_output_contracts = {
        "variant": {
            "kind": "scalar",
            "type": "enum",
            "allowed": ["APPROVED", "BLOCKED", "REVISE", "EXHAUSTED"],
        },
        "review_decision": {
            "kind": "scalar",
            "type": "enum",
            "allowed": ["APPROVE", "REVISE", "BLOCKED"],
        },
        "checks_report": {
            "kind": "relpath",
            "type": "relpath",
            "under": "artifacts/work",
            "must_exist_target": True,
        },
        "review_report": {
            "kind": "relpath",
            "type": "relpath",
            "under": "artifacts/work",
            "must_exist_target": True,
        },
        "progress_report": {
            "kind": "relpath",
            "type": "relpath",
            "under": "artifacts/work",
            "must_exist_target": True,
        },
        "blocker_class": {
            "kind": "scalar",
            "type": "enum",
            "allowed": [
                "missing_resource",
                "unavailable_hardware",
                "roadmap_conflict",
                "external_dependency_outside_authority",
                "user_decision_required",
                "unrecoverable_after_fix_attempt",
            ],
        },
        "last_review_report": {
            "kind": "relpath",
            "type": "relpath",
            "under": "artifacts/work",
            "must_exist_target": True,
        },
        "reason": {
            "kind": "scalar",
            "type": "string",
        },
    }

    def _route_case_outputs(*, variant_step: str, reason_step: str) -> dict[str, Any]:
        return {
            "variant": {
                **route_output_contracts["variant"],
                "from": {"ref": f"self.steps.{variant_step}.artifacts.variant"},
            },
            "review_decision": {
                **route_output_contracts["review_decision"],
                "from": {"ref": f"{review_result_ref}.review_decision"},
            },
            "checks_report": {
                **route_output_contracts["checks_report"],
                "from": {"ref": f"{review_result_ref}.checks_report"},
            },
            "review_report": {
                **route_output_contracts["review_report"],
                "from": {"ref": f"{review_result_ref}.review_report"},
            },
            "progress_report": {
                **route_output_contracts["progress_report"],
                "from": {"ref": f"{review_result_ref}.progress_report"},
            },
            "blocker_class": {
                **route_output_contracts["blocker_class"],
                "from": {"ref": f"{review_result_ref}.blocker_class"},
            },
            "last_review_report": {
                **route_output_contracts["last_review_report"],
                "from": {"ref": f"{review_result_ref}.review_report"},
            },
            "reason": {
                **route_output_contracts["reason"],
                "from": {"ref": f"self.steps.{reason_step}.artifacts.reason"},
            },
        }

    loop_outputs = {
        "variant": {
            "kind": "scalar",
            "type": "enum",
            "allowed": ["APPROVED", "BLOCKED", "REVISE", "EXHAUSTED"],
            "from": {"ref": "self.steps.RouteDecision.artifacts.variant"},
        },
        "review_decision": {
            "kind": "scalar",
            "type": "enum",
            "allowed": ["APPROVE", "REVISE", "BLOCKED"],
            "from": {"ref": "self.steps.RouteDecision.artifacts.review_decision"},
        },
        "checks_report": {
            "kind": "relpath",
            "type": "relpath",
            "under": "artifacts/work",
            "must_exist_target": True,
            "from": {"ref": "self.steps.RouteDecision.artifacts.checks_report"},
        },
        "review_report": {
            "kind": "relpath",
            "type": "relpath",
            "under": "artifacts/work",
            "must_exist_target": True,
            "from": {"ref": "self.steps.RouteDecision.artifacts.review_report"},
        },
        "progress_report": {
            "kind": "relpath",
            "type": "relpath",
            "under": "artifacts/work",
            "must_exist_target": True,
            "from": {"ref": "self.steps.RouteDecision.artifacts.progress_report"},
        },
        "blocker_class": {
            "kind": "scalar",
            "type": "enum",
            "allowed": [
                "missing_resource",
                "unavailable_hardware",
                "roadmap_conflict",
                "external_dependency_outside_authority",
                "user_decision_required",
                "unrecoverable_after_fix_attempt",
            ],
            "from": {"ref": "self.steps.RouteDecision.artifacts.blocker_class"},
        },
        "last_review_report": {
            "kind": "relpath",
            "type": "relpath",
            "under": "artifacts/work",
            "must_exist_target": True,
            "from": {"ref": "self.steps.RouteDecision.artifacts.last_review_report"},
        },
        "reason": {
            "kind": "scalar",
            "type": "string",
            "from": {"ref": "self.steps.RouteDecision.artifacts.reason"},
        },
    }
    repeat_step = {
        "name": repeat_step_name,
        "id": repeat_step_id,
        "repeat_until": {
            "id": "review_loop_iteration",
            "max_iterations": int(_render_scalar_expr(expr.max_expr, local_values=local_values)),
            "outputs": loop_outputs,
            "condition": {
                "compare": {
                    "left": {"ref": "self.outputs.variant"},
                    "op": "ne",
                    "right": "REVISE",
                }
            },
            "on_exhausted": {
                "outputs": {
                    "variant": "EXHAUSTED",
                    "reason": "max_iterations_reached",
                }
            },
            "steps": [
                {
                    "name": "ReviewDecision",
                    "id": "review_decision",
                    "provider": review_provider.provider_id,
                    "asset_file": review_prompt.asset_file,
                    "consumes": consumes,
                    "prompt_consumes": prompt_consumes,
                    "inject_output_contract": True,
                    "output_bundle": review_output_bundle,
                },
                {
                    "name": "RouteDecision",
                    "id": "route_decision",
                    "match": {
                        "ref": "self.steps.ReviewDecision.artifacts.review_decision",
                        "cases": {
                            "APPROVE": {
                                "id": "approved_case",
                                "outputs": _route_case_outputs(
                                    variant_step="MarkApproved",
                                    reason_step="WriteApprovedReason",
                                ),
                                "steps": [
                                    {
                                        "name": "MarkApproved",
                                        "id": "mark_approved",
                                        "materialize_artifacts": {
                                            "values": [
                                                {
                                                    "name": "variant",
                                                    "source": {"literal": "APPROVED"},
                                                    "contract": dict(route_output_contracts["variant"]),
                                                }
                                            ],
                                        },
                                    },
                                    {
                                        "name": "WriteApprovedReason",
                                        "id": "write_approved_reason",
                                        "materialize_artifacts": {
                                            "values": [
                                                {
                                                    "name": "reason",
                                                    "source": {"literal": "approved"},
                                                    "contract": dict(route_output_contracts["reason"]),
                                                }
                                            ],
                                        },
                                    },
                                ],
                            },
                            "BLOCKED": {
                                "id": "blocked_case",
                                "outputs": _route_case_outputs(
                                    variant_step="MarkBlocked",
                                    reason_step="WriteBlockedReason",
                                ),
                                "steps": [
                                    {
                                        "name": "MarkBlocked",
                                        "id": "mark_blocked",
                                        "materialize_artifacts": {
                                            "values": [
                                                {
                                                    "name": "variant",
                                                    "source": {"literal": "BLOCKED"},
                                                    "contract": dict(route_output_contracts["variant"]),
                                                }
                                            ],
                                        },
                                    },
                                    {
                                        "name": "WriteBlockedReason",
                                        "id": "write_blocked_reason",
                                        "materialize_artifacts": {
                                            "values": [
                                                {
                                                    "name": "reason",
                                                    "source": {"literal": "blocked"},
                                                    "contract": dict(route_output_contracts["reason"]),
                                                }
                                            ],
                                        },
                                    },
                                ],
                            },
                            "REVISE": {
                                "id": "revise_case",
                                "outputs": _route_case_outputs(
                                    variant_step="MarkRevise",
                                    reason_step="WriteReviseReason",
                                ),
                                "steps": [
                                    {
                                        "name": "ApplyFix",
                                        "id": "apply_fix",
                                        "provider": fix_provider.provider_id,
                                        "asset_file": fix_prompt.asset_file,
                                        "consumes": consumes,
                                        "prompt_consumes": prompt_consumes,
                                    },
                                    {
                                        "name": "MarkRevise",
                                        "id": "mark_revise",
                                        "materialize_artifacts": {
                                            "values": [
                                                {
                                                    "name": "variant",
                                                    "source": {"literal": "REVISE"},
                                                    "contract": dict(route_output_contracts["variant"]),
                                                }
                                            ],
                                        },
                                    },
                                    {
                                        "name": "WriteReviseReason",
                                        "id": "write_revise_reason",
                                        "materialize_artifacts": {
                                            "values": [
                                                {
                                                    "name": "reason",
                                                    "source": {"literal": "revise_requested"},
                                                    "contract": dict(route_output_contracts["reason"]),
                                                }
                                            ],
                                        },
                                    },
                                ],
                            },
                        },
                    },
                },
            ],
        },
    }
    result_output_contracts = _review_loop_result_output_contracts(
        typed_expr.type_ref,
        context=context,
        span=expr.span,
        form_path=expr.form_path,
    )

    def _result_case_outputs(*, variant_ref: str) -> dict[str, Any]:
        return {
            field_name: {
                **definition,
                "from": {"ref": variant_ref if field_name == "variant" else f"root.steps.{repeat_step_name}.artifacts.{field_name}"},
            }
            for field_name, definition in result_output_contracts.items()
        }

    result_cases = {
        "APPROVED": {
            "id": _normalize_generated_step_id(f"{result_step_name}__approved"),
            "outputs": _result_case_outputs(
                variant_ref=f"root.steps.{repeat_step_name}.artifacts.variant",
            ),
            "steps": [
                _build_match_projection_anchor_step(
                    match_step_name=result_step_name,
                    variant_name="APPROVED",
                    case_outputs=_result_case_outputs(
                        variant_ref=f"root.steps.{repeat_step_name}.artifacts.variant",
                    ),
                    context=context,
                    span=expr.span,
                )
            ],
        },
        "BLOCKED": {
            "id": _normalize_generated_step_id(f"{result_step_name}__blocked"),
            "outputs": _result_case_outputs(
                variant_ref=f"root.steps.{repeat_step_name}.artifacts.variant",
            ),
            "steps": [
                _build_match_projection_anchor_step(
                    match_step_name=result_step_name,
                    variant_name="BLOCKED",
                    case_outputs=_result_case_outputs(
                        variant_ref=f"root.steps.{repeat_step_name}.artifacts.variant",
                    ),
                    context=context,
                    span=expr.span,
                )
            ],
        },
        "EXHAUSTED": {
            "id": _normalize_generated_step_id(f"{result_step_name}__exhausted"),
            "outputs": _result_case_outputs(
                variant_ref=f"root.steps.{repeat_step_name}.artifacts.variant",
            ),
            "steps": [
                _build_match_projection_anchor_step(
                    match_step_name=result_step_name,
                    variant_name="EXHAUSTED",
                    case_outputs=_result_case_outputs(
                        variant_ref=f"root.steps.{repeat_step_name}.artifacts.variant",
                    ),
                    context=context,
                    span=expr.span,
                )
            ],
        },
        "REVISE": {
            "id": _normalize_generated_step_id(f"{result_step_name}__revise"),
            "outputs": _result_case_outputs(
                variant_ref="self.steps.NormalizeReviseVariant.artifacts.variant",
            ),
            "steps": [
                {
                    "name": "NormalizeReviseVariant",
                    "id": "normalize_revise_variant",
                    "materialize_artifacts": {
                        "values": [
                            {
                                "name": "variant",
                                "source": {"literal": "EXHAUSTED"},
                                "contract": dict(result_output_contracts["variant"]),
                            }
                        ],
                    },
                },
                _build_match_projection_anchor_step(
                    match_step_name=result_step_name,
                    variant_name="REVISE",
                    case_outputs=_result_case_outputs(
                        variant_ref="self.steps.NormalizeReviseVariant.artifacts.variant",
                    ),
                    context=context,
                    span=expr.span,
                ),
            ],
        },
    }
    result_step = {
        "name": result_step_name,
        "id": result_step_id,
        "match": {
            "ref": f"root.steps.{repeat_step_name}.artifacts.variant",
            "cases": result_cases,
        },
    }
    generated_steps.extend([repeat_step, result_step])
    return generated_steps, _TerminalResult(
        step_name=result_step_name,
        step_id=result_step_id,
        output_refs={
            f"return__{field_name}": f"root.steps.{result_step_name}.artifacts.{field_name}"
            for field_name in result_output_contracts
        },
        output_kind="match",
        hidden_inputs=hidden_inputs,
    )


def _lower_resume_or_start(
    typed_expr: TypedExpr,
    *,
    context: _LoweringContext,
    local_values: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], _TerminalResult]:
    """Lower reusable-state logic into validate, branch, and load steps.

    `resume-or-start` means "reuse a prior validated result when it is still
    complete, otherwise run the supplied start expression." A certified adapter
    checks whether the previous JSON bundle and referenced artifacts are still
    valid; a workflow `match` chooses reuse or fresh execution; both branches
    return the same typed result shape.
    """

    expr = typed_expr.expr
    assert isinstance(expr, ResumeOrStartExpr)
    validator_binding = context.command_boundary_environment.bindings_by_name.get("validate_reusable_phase_state")
    if context.phase_scope is not None:
        _require_phase_scope_name_match(
            context.phase_scope,
            authored_name=expr.resume_name,
            form_name="resume-or-start",
            span=expr.span,
            form_path=expr.form_path,
        )
    if not isinstance(validator_binding, CertifiedAdapterBinding):
        raise _compile_error(
            code="resume_or_start_uncertified_backend",
            message="`resume-or-start` lowering requires the certified reusable-state validator binding",
            span=expr.span,
            form_path=expr.form_path,
        )
    validator_step_name = f"{context.step_name_prefix}__resume_decision"
    validator_step_id = _normalize_generated_step_id(validator_step_name)
    branch_step_name = f"{context.step_name_prefix}__select_bundle"
    branch_step_id = _normalize_generated_step_id(branch_step_name)
    loader_step_name = context.step_name_prefix
    loader_step_id = _normalize_generated_step_id(loader_step_name)
    _record_step_origin(context, step_name=validator_step_name, step_id=validator_step_id, source=expr)
    _record_step_origin(context, step_name=branch_step_name, step_id=branch_step_id, source=expr)
    _record_step_origin(context, step_name=loader_step_name, step_id=loader_step_id, source=expr)
    resume_from_ref = _render_existing_output_ref(expr.resume_from_expr, local_values=local_values)
    if resume_from_ref is None:
        raise _compile_error(
            code="resume_or_start_contract_invalid",
            message="`resume-or-start :resume-from` must lower from one workflow input or existing output ref",
            span=expr.resume_from_expr.span,
            form_path=expr.resume_from_expr.form_path,
        )
    validator_hidden_input = f"__write_root__{validator_step_id}__result_bundle"
    validator_payload = json.dumps(
        {
            "resume_from": _template_for_ref(resume_from_ref),
            "expected_return_type": expr.returns_type_name,
            "valid_variants": list(expr.valid_when),
            "required_artifact_fields": {
                key: list(value)
                for key, value in _resume_required_artifact_fields(
                    typed_expr.type_ref,
                    context=context,
                    span=expr.span,
                    form_path=expr.form_path,
                ).items()
            },
        }
    )
    validator_step = {
        "name": validator_step_name,
        "id": validator_step_id,
        "command": [*validator_binding.stable_command, validator_payload],
        "variant_output": {
            "path": f"${{inputs.{validator_hidden_input}}}",
            "discriminant": {
                "name": "variant",
                "json_pointer": "/variant",
                "type": "enum",
                "allowed": ["REUSE", "START"],
            },
            "shared_fields": [],
            "variants": {
                "REUSE": {
                    "fields": [
                        {
                            "name": "source_bundle_path",
                            "json_pointer": "/source_bundle_path",
                            "type": "relpath",
                        }
                    ]
                },
                "START": {
                    "fields": [
                        {
                            "name": "reason_code",
                            "json_pointer": "/reason_code",
                            "type": "string",
                        }
                    ]
                },
            },
        },
    }
    start_context = _copy_context_with_step_prefix(
        context,
        step_name_prefix=f"{context.step_name_prefix}__start",
    )
    start_steps, start_terminal = _lower_expression(
        TypedExpr(
            expr=expr.start_expr,
            type_ref=typed_expr.type_ref,
            span=expr.start_expr.span,
            form_path=expr.start_expr.form_path,
        ),
        context=start_context,
        local_values=local_values,
    )
    start_bundle_ref = _resume_start_bundle_ref(
        expr.start_expr,
        start_terminal=start_terminal,
        context=start_context,
    )
    start_case_steps = list(start_steps)
    start_bundle_output_ref = start_bundle_ref
    if not start_bundle_ref.startswith("root.steps.") and not start_bundle_ref.startswith("self.steps.") and not start_bundle_ref.startswith("parent.steps."):
        capture_step_name = "CaptureFreshBundlePath"
        capture_step_id = "capture_fresh_bundle_path"
        start_case_steps.append(
            {
                "name": capture_step_name,
                "id": capture_step_id,
                "materialize_artifacts": {
                    "values": [
                        {
                            "name": "source_bundle_path",
                            "source": (
                                {"input": start_bundle_ref.removeprefix("inputs.")}
                                if start_bundle_ref.startswith("inputs.")
                                else {"literal": start_bundle_ref}
                            ),
                            "contract": {
                                "kind": "relpath",
                                "type": "relpath",
                            },
                        }
                    ],
                },
            }
        )
        start_bundle_output_ref = f"self.steps.{capture_step_name}.artifacts.source_bundle_path"
    branch_case_outputs = {
        "source_bundle_path": {
            "kind": "relpath",
            "type": "relpath",
            "from": {"ref": f"parent.steps.{validator_step_name}.artifacts.source_bundle_path"},
        }
    }
    branch_step = {
        "name": branch_step_name,
        "id": branch_step_id,
        "match": {
            "ref": f"root.steps.{validator_step_name}.artifacts.variant",
            "cases": {
                "REUSE": {
                    "id": "reuse_bundle",
                    "outputs": branch_case_outputs,
                    "steps": [
                        {
                            "name": "ReuseBranchAnchor",
                            "id": "reuse_branch_anchor",
                            "assert": {
                                "compare": {
                                    "left": {
                                        "ref": f"parent.steps.{validator_step_name}.artifacts.variant",
                                    },
                                    "op": "eq",
                                    "right": "REUSE",
                                }
                            },
                        }
                    ],
                },
                "START": {
                    "id": "start_bundle",
                    "outputs": {
                        "source_bundle_path": {
                            "kind": "relpath",
                            "type": "relpath",
                            "from": {"ref": start_bundle_output_ref},
                        }
                    },
                    "steps": start_case_steps,
                },
            },
        },
    }
    loader_binding_name = f"load_canonical_phase_result__{expr.returns_type_name}"
    loader_binding = context.command_boundary_environment.bindings_by_name.get(loader_binding_name)
    if not isinstance(loader_binding, CertifiedAdapterBinding):
        raise _compile_error(
            code="resume_or_start_uncertified_backend",
            message=f"`resume-or-start` lowering requires `{loader_binding_name}`",
            span=expr.span,
            form_path=expr.form_path,
        )
    loader_contract = derive_structured_result_contract(
        typed_expr.type_ref,
        workflow_name=context.workflow_name,
        step_id=loader_step_name,
        span=expr.span,
        form_path=expr.form_path,
    )
    loader_hidden_input = f"__write_root__{loader_step_id}__result_bundle"
    loader_payload = json.dumps(
        {
            "bundle_path": "${root.steps."
            + branch_step_name
            + ".artifacts.source_bundle_path}",
            "expected_return_type": expr.returns_type_name,
        }
    )
    loader_step = {
        "name": loader_step_name,
        "id": loader_step_id,
        "command": [*loader_binding.stable_command, loader_payload],
        loader_contract.contract_kind: {
            **dict(loader_contract.payload),
            "path": f"${{inputs.{loader_hidden_input}}}",
        },
    }
    hidden_inputs = {
        validator_hidden_input: _origin_from_context_source(context, expr),
        loader_hidden_input: _origin_from_context_source(context, expr),
    }
    hidden_inputs.update(start_terminal.hidden_inputs)
    return [validator_step, branch_step, loader_step], _TerminalResult(
        step_name=loader_step_name,
        step_id=loader_step_id,
        output_refs=_record_output_refs(loader_step_name, typed_expr.type_ref),
        output_kind="step",
        hidden_inputs=hidden_inputs,
    )


def _lower_call_expr(
    typed_expr: TypedExpr,
    *,
    context: _LoweringContext,
    local_values: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], _TerminalResult]:
    """Lower a typed workflow call to the runtime call-step shape.

    Frontend calls pass records and unions as typed values. The current runtime
    call step receives flattened scalar/path inputs, so lowering maps each
    structured argument field to the callee input name. It also adds generated
    write-root inputs used by callees for their result-bundle paths.
    """

    expr = typed_expr.expr
    assert isinstance(expr, CallExpr)
    signature = context.workflow_catalog.signatures_by_name.get(expr.callee_name)
    canonical_name = signature.name if signature is not None else expr.callee_name
    callee = context.lowered_callees.get(canonical_name)
    imported_bundle = context.imported_workflow_bundles.get(canonical_name)
    if callee is None and imported_bundle is None:
        raise _compile_error(
            code="workflow_call_unknown",
            message=f"unknown workflow callee `{expr.callee_name}` during lowering",
            span=expr.span,
            form_path=expr.form_path,
        )
    step_name = f"{context.step_name_prefix}__call_{canonical_name}"
    step_id = _normalize_generated_step_id(step_name)
    with_bindings: dict[str, Any] = {}
    binding_by_name = dict(expr.bindings)
    callee_signature = (
        callee.typed_workflow.signature
        if callee is not None
        else signature
    )
    assert callee_signature is not None
    for param_name, param_type in callee_signature.params:
        value_expr = binding_by_name[param_name]
        if isinstance(param_type, RecordTypeRef):
            for generated_name, field_path in _flatten_boundary_leaf_paths(
                param_type,
                generated_name=param_name,
            ):
                with_bindings[generated_name] = _render_call_binding_ref(
                    value_expr,
                    local_values=local_values,
                    field_path=field_path,
                )
            continue
        with_bindings[param_name] = _render_call_binding_ref(value_expr, local_values=local_values)
    managed_inputs = (
        _managed_inputs_from_mapping(callee.authored_mapping)
        if callee is not None
        else _managed_inputs_from_bundle(imported_bundle)
    )
    for managed_input in managed_inputs:
        with_bindings[managed_input] = (
            f".orchestrate/workflow_lisp/calls/{context.workflow_name}/{step_name}/{canonical_name}/{managed_input}.json"
        )
    _record_step_origin(context, step_name=step_name, step_id=step_id, source=expr)
    step = {
        "name": step_name,
        "id": step_id,
        "call": canonical_name,
        "with": with_bindings,
    }
    return [step], _TerminalResult(
        step_name=step_name,
        step_id=step_id,
        output_refs={
            output_name: f"root.steps.{step_name}.artifacts.{output_name}"
            for output_name, _ in _flatten_boundary_leaf_paths(typed_expr.type_ref, generated_name="return")
        },
        output_kind="call",
        hidden_inputs={},
    )


def _lower_procedure_call_expr(
    typed_expr: TypedExpr,
    *,
    context: _LoweringContext,
    local_values: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], _TerminalResult]:
    """Lower a reusable procedure call without adding a second runtime model.

    A `defproc` is reusable workflow behavior, not just syntax. Lowering either
    inlines its body into the caller or emits a hidden workflow and calls it
    through the same runtime call step used for authored workflows.
    """

    expr = typed_expr.expr
    assert isinstance(expr, ProcedureCallExpr)
    procedure = context.typed_procedures.get(expr.callee_name)
    canonical_name = procedure.signature.name if procedure is not None else expr.callee_name
    if procedure is None:
        raise _compile_error(
            code="procedure_call_unknown",
            message=f"unknown procedure callee `{expr.callee_name}` during lowering",
            span=expr.span,
            form_path=expr.form_path,
        )
    if procedure.resolved_lowering_mode == ProcedureLoweringMode.PRIVATE_WORKFLOW:
        context.origin_notes = _procedure_provenance_notes(expr, procedure)
        assert procedure.generated_workflow_name is not None
        callee = context.lowered_callees.get(procedure.generated_workflow_name)
        if callee is None:
            raise _compile_error(
                code="proc_private_workflow_boundary_invalid",
                message=f"generated private workflow `{procedure.generated_workflow_name}` was not lowered",
                span=expr.span,
                form_path=expr.form_path,
            )
        step_name = f"{context.step_name_prefix}__call_{canonical_name}"
        step_id = _normalize_generated_step_id(step_name)
        with_bindings: dict[str, Any] = {}
        for arg_expr, (param_name, param_type) in zip(expr.args, procedure.signature.params, strict=True):
            if isinstance(param_type, RecordTypeRef):
                for generated_name, field_path in _flatten_boundary_leaf_paths(param_type, generated_name=param_name):
                    with_bindings[generated_name] = _render_call_binding_ref(
                        arg_expr,
                        local_values=local_values,
                        field_path=field_path,
                    )
            else:
                with_bindings[param_name] = _render_call_binding_ref(arg_expr, local_values=local_values)
        for managed_input in _managed_inputs_from_mapping(callee.authored_mapping):
            with_bindings[managed_input] = (
                f".orchestrate/workflow_lisp/calls/{context.workflow_name}/{step_name}/{canonical_name}/{managed_input}.json"
            )
        _record_step_origin(context, step_name=step_name, step_id=step_id, source=expr)
        return [{"name": step_name, "id": step_id, "call": procedure.generated_workflow_name, "with": with_bindings}], _TerminalResult(
            step_name=step_name,
            step_id=step_id,
            output_refs={
                output_name: f"root.steps.{step_name}.artifacts.{output_name}"
                for output_name, _ in _flatten_boundary_leaf_paths(typed_expr.type_ref, generated_name="return")
            },
            output_kind="call",
            hidden_inputs={},
        )

    prefix_ordinal = context.inline_call_counters.get(expr.callee_name, 0) + 1
    context.inline_call_counters[expr.callee_name] = prefix_ordinal
    context.origin_notes = _procedure_provenance_notes(expr, procedure)
    child_locals = dict(local_values)
    for arg_expr, (param_name, _) in zip(expr.args, procedure.signature.params, strict=True):
        child_locals[param_name] = _resolve_inline_expr_value(arg_expr, local_values=local_values)
    child_context = _LoweringContext(
        workflow_name=context.workflow_name,
        step_name_prefix=f"{context.step_name_prefix}__{expr.callee_name}_{prefix_ordinal}",
        workflow_path=context.workflow_path,
        signature=context.signature,
        authored_input_contracts=context.authored_input_contracts,
        workflow_catalog=context.workflow_catalog,
        imported_workflow_bundles=context.imported_workflow_bundles,
        extern_environment=context.extern_environment,
        command_boundary_environment=context.command_boundary_environment,
        lowered_callees=context.lowered_callees,
        typed_procedures=context.typed_procedures,
        type_env=context.type_env,
        step_spans=context.step_spans,
        generated_input_spans=context.generated_input_spans,
        generated_output_spans=context.generated_output_spans,
        generated_path_spans=context.generated_path_spans,
        top_level_artifacts=context.top_level_artifacts,
        inline_call_counters=context.inline_call_counters,
        origin_notes=_procedure_provenance_notes(expr, procedure),
        return_output_contracts=context.return_output_contracts,
        phase_scope=context.phase_scope,
    )
    return _lower_expression(procedure.typed_body, context=child_context, local_values=child_locals)


def _lower_let_star(
    typed_expr: TypedExpr,
    *,
    context: _LoweringContext,
    local_values: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], _TerminalResult]:
    """Lower sequential bindings into ordered workflow steps and local refs.

    Each binding contributes steps and a structured local value for later
    bindings. The special match-after-binding path preserves the proof that a
    matched union value is the same value just produced by the binding.
    """

    expr = typed_expr.expr
    assert isinstance(expr, LetStarExpr)
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
    binding_type = _binding_type_for_expr(binding_expr, context=context)
    provider_step_name = f"{context.step_name_prefix}__{binding_name}"
    if isinstance(binding_expr, ProviderResultExpr):
        binding_steps, binding_terminal = _lower_provider_result(
            binding_expr,
            result_type=binding_type,
            context=context,
            local_values=local_values,
            step_name=provider_step_name,
        )
    else:
        binding_steps, binding_terminal = _lower_expression(
            TypedExpr(
                expr=binding_expr,
                type_ref=binding_type,
                span=binding_expr.span,
                form_path=binding_expr.form_path,
            ),
            context=_copy_context_with_step_prefix(context, step_name_prefix=provider_step_name),
            local_values=local_values,
        )
    local_bindings = dict(local_values)
    if isinstance(binding_type, (RecordTypeRef, UnionTypeRef)):
        local_bindings[binding_name] = _build_output_step_local_value(binding_terminal.output_refs)

    if isinstance(body_expr, MatchExpr):
        lowered_steps, terminal = _lower_match_expr(
            body_expr,
            context=context,
            binding_name=binding_name,
            binding_terminal=binding_terminal,
            local_values=local_bindings,
        )
    else:
        lowered_steps, terminal = _lower_expression(
            TypedExpr(
                expr=body_expr,
                type_ref=typed_expr.type_ref,
                span=body_expr.span,
                form_path=body_expr.form_path,
            ),
            context=context,
            local_values=local_bindings,
        )
    hidden_inputs = dict(binding_terminal.hidden_inputs)
    hidden_inputs.update(terminal.hidden_inputs)
    return [*binding_steps, *lowered_steps], _TerminalResult(
        step_name=terminal.step_name,
        step_id=terminal.step_id,
        output_refs=terminal.output_refs,
        output_kind=terminal.output_kind,
        hidden_inputs=hidden_inputs,
    )


def _lower_match_expr(
    match_expr: MatchExpr,
    *,
    context: _LoweringContext,
    binding_name: str,
    binding_terminal: _TerminalResult,
    local_values: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], _TerminalResult]:
    """Lower a tagged-union branch to the runtime `match` step form.

    A frontend union has a discriminant plus fields that exist only for some
    variants. The runtime `match` step checks the discriminant. Inside each
    branch, lowering exposes refs only for the proven variant, then projects all
    branches back into one result for enclosing code.
    """

    match_step_name = f"{context.step_name_prefix}__match_{binding_name}"
    match_step_id = _normalize_generated_step_id(match_step_name)
    cases: dict[str, Any] = {}
    for arm in match_expr.arms:
        case_steps: list[dict[str, Any]] = []
        if not isinstance(arm.body, RecordExpr):
            raise _compile_error(
                code="workflow_return_not_exportable",
                message="Stage 3 lowering requires match arms to return record expressions",
                span=arm.body.span,
                form_path=arm.body.form_path,
            )
        case_outputs: dict[str, Any] = {}
        for field_name, contract_definition in context.return_output_contracts.items():
            generated_output_name = f"return__{field_name}"
            lowered_output = _lower_match_output_field(
                record_expr=arm.body,
                field_name=field_name,
                generated_output_name=generated_output_name,
                contract_definition=contract_definition,
                match_step_id=match_step_id,
                variant_name=arm.variant_name,
                binding_name=arm.binding_name,
                binding_terminal=binding_terminal,
                context=context,
                local_values=local_values,
            )
            case_steps.extend(lowered_output["steps"])
            case_outputs[generated_output_name] = lowered_output["output"]
        case_name = f"{match_step_name}__{arm.variant_name.lower()}"
        if not case_steps:
            case_steps.append(
                _build_match_projection_anchor_step(
                    match_step_name=match_step_name,
                    variant_name=arm.variant_name,
                    case_outputs=case_outputs,
                    context=context,
                    span=arm.body.span,
                )
            )
        cases[arm.variant_name] = {
            "id": _normalize_generated_step_id(case_name),
            "outputs": case_outputs,
            "steps": case_steps,
        }

    _record_step_origin(context, step_name=match_step_name, step_id=match_step_id, source=match_expr)
    match_step = {
        "name": match_step_name,
        "id": match_step_id,
        "match": {
            "ref": binding_terminal.output_refs["return__variant"],
            "cases": cases,
        },
    }
    return [match_step], _TerminalResult(
        step_name=match_step_name,
        step_id=match_step_id,
        output_refs={
            f"return__{field_name}": f"root.steps.{match_step_name}.artifacts.return__{field_name}"
            for field_name in context.return_output_contracts
        },
        output_kind="match",
        hidden_inputs={},
    )


def _lower_finalize_selected_item(
    typed_expr: TypedExpr,
    *,
    context: _LoweringContext,
    local_values: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], _TerminalResult]:
    """Lower selected-item finalization into typed routing steps.

    The selected-item workflow has several possible terminal causes: completed
    implementation, selection rejection, roadmap block, plan block, or
    implementation block. This helper emits the branch logic and state
    materialization needed to return one `SelectedItemResult` union instead of
    scattering that logic across handwritten scripts.
    """

    expr = typed_expr.expr
    assert isinstance(expr, FinalizeSelectedItemExpr)
    roadmap_value = _resolve_inline_expr_value(expr.spec.roadmap_expr, local_values=local_values)
    plan_value = _resolve_inline_expr_value(expr.spec.plan_expr, local_values=local_values)
    implementation_value = _resolve_inline_expr_value(expr.spec.implementation_expr, local_values=local_values)
    selected_value = _resolve_inline_expr_value(expr.spec.selected_expr, local_values=local_values)
    queue_transition_value = _resolve_inline_expr_value(expr.spec.queue_transition_expr, local_values=local_values)
    if not all(
        isinstance(value, Mapping)
        for value in (roadmap_value, plan_value, implementation_value, selected_value, queue_transition_value)
    ):
        raise _compile_error(
            code="workflow_return_not_exportable",
            message="`finalize-selected-item` lowering requires prior structured results and selected-item inputs",
            span=expr.span,
            form_path=expr.form_path,
        )
    step_name = context.step_name_prefix
    step_id = _normalize_generated_step_id(step_name)
    run_state_ref = selected_value.get("final-plan-gate-state")
    roadmap_status_ref = roadmap_value.get("status")
    plan_variant_ref = plan_value.get("variant")
    plan_summary_ref = plan_value.get("progress-report-path")
    plan_blocker_ref = plan_value.get("blocker-class")
    implementation_variant_ref = implementation_value.get("variant")
    implementation_summary_ref = implementation_value.get("execution-report-path")
    implementation_blocked_summary_ref = implementation_value.get("progress-report-path")
    implementation_blocker_ref = implementation_value.get("blocker-class")
    queue_transition_id_ref = queue_transition_value.get("transition-id")
    if not all(
        isinstance(ref, str)
        for ref in (
            run_state_ref,
            roadmap_status_ref,
            plan_variant_ref,
            plan_summary_ref,
            plan_blocker_ref,
            implementation_variant_ref,
            implementation_summary_ref,
            implementation_blocked_summary_ref,
            implementation_blocker_ref,
            queue_transition_id_ref,
        )
    ):
        raise _compile_error(
            code="workflow_return_not_exportable",
            message="`finalize-selected-item` lowering requires roadmap, plan, implementation, queue-transition, and selection refs",
            span=expr.span,
            form_path=expr.form_path,
        )
    summary_contract = dict(_required_output_contract(context, "summary-path", expr))
    run_state_contract = dict(_required_output_contract(context, "run-state", expr))
    variant_contract = dict(_required_output_contract(context, "variant", expr))
    blocker_contract = context.return_output_contracts.get("blocker-class")
    if blocker_contract is None:
        raise _compile_error(
            code="workflow_return_not_exportable",
            message="`finalize-selected-item` requires the `SelectedItemResult.blocker-class` contract",
            span=expr.span,
            form_path=expr.form_path,
        )
    summary_artifact_name = "selected_item_summary"
    summary_pointer_path = _selected_item_summary_pointer_path(context.workflow_name)
    context.top_level_artifacts[summary_artifact_name] = {
        **summary_contract,
        "pointer": summary_pointer_path,
    }
    context.generated_path_spans[summary_pointer_path] = _origin_from_context_source(context, expr)
    selected_active_value = selected_value.get("is-active")
    placeholder_blocker_value = blocker_contract["allowed"][0]
    result_output_definitions = {
        "return__variant": dict(variant_contract),
        "return__summary-path": dict(summary_contract),
        "return__run-state": dict(run_state_contract),
        "return__blocker-class": dict(blocker_contract),
    }

    def _when_from_value(value: Any) -> dict[str, Any] | None:
        if isinstance(value, LiteralExpr):
            operand: bool | dict[str, str] = bool(value.value)
        elif isinstance(value, str):
            operand = {"ref": value}
        else:
            return None
        return {
            "compare": {
                "left": operand,
                "op": "eq",
                "right": True,
            }
        }

    queue_transition_materialize_step = {
        "name": "FinalizeSelectedItemQueueTransition",
        "id": _normalize_generated_step_id("FinalizeSelectedItemQueueTransition"),
        "materialize_artifacts": {
            "values": [
                {
                    "name": "queue_transition_id",
                    "source": {"ref": queue_transition_id_ref},
                    "contract": {"kind": "scalar", "type": "string"},
                }
            ]
        },
    }
    queue_transition_when = _when_from_value(selected_active_value)
    if queue_transition_when is not None:
        queue_transition_materialize_step["when"] = queue_transition_when
    _record_step_origin(
        context,
        step_name=queue_transition_materialize_step["name"],
        step_id=queue_transition_materialize_step["id"],
        source=expr,
    )

    def _outcome_values(*, variant: str, summary_ref: str, include_blocker_ref: str | None) -> list[dict[str, Any]]:
        values: list[dict[str, Any]] = [
            {
                "name": "return__variant",
                "source": {"literal": variant},
                "contract": dict(variant_contract),
            },
            {
                "name": "return__summary-path",
                "source": {"ref": summary_ref},
                "contract": dict(summary_contract),
            },
            {
                "name": "return__run-state",
                "source": {"ref": run_state_ref},
                "contract": dict(run_state_contract),
            },
            {
                "name": "roadmap_status",
                "source": {"ref": roadmap_status_ref},
                "contract": {"kind": "scalar", "type": "string"},
            },
        ]
        if include_blocker_ref is not None:
            values.append(
                {
                    "name": "return__blocker-class",
                    "source": {"ref": include_blocker_ref},
                    "contract": dict(blocker_contract),
                }
            )
        return values

    def _publish_summary_step(*, name: str, summary_ref: str) -> dict[str, Any]:
        return {
            "name": name,
            "id": _normalize_generated_step_id(name),
            "materialize_artifacts": {
                "values": [
                    {
                        "name": summary_artifact_name,
                        "source": {"ref": summary_ref},
                        "contract": dict(summary_contract),
                        "pointer": {"path": summary_pointer_path},
                    }
                ]
            },
            "publishes": [{"artifact": summary_artifact_name, "from": summary_artifact_name}],
        }

    def _forward_result_outputs(source_ref_prefix: str) -> dict[str, Any]:
        return {
            name: {
                **definition,
                "from": {"ref": f"{source_ref_prefix}.{name}"},
            }
            for name, definition in result_output_definitions.items()
        }

    plan_blocked_outcome_name = "FinalizeSelectedItemOutcomeBlockedByPlan"
    plan_approved_match_name = "FinalizeSelectedItemImplementationResult"
    implementation_completed_outcome_name = "FinalizeSelectedItemOutcomeCompleted"
    implementation_blocked_outcome_name = "FinalizeSelectedItemOutcomeBlockedByImplementation"
    implementation_cases = {
        "COMPLETED": {
            "id": _normalize_generated_step_id(f"{step_name}__completed"),
            "outputs": _forward_result_outputs(
                f"self.steps.{implementation_completed_outcome_name}.artifacts"
            ),
            "steps": [
                {
                    "name": implementation_completed_outcome_name,
                    "id": _normalize_generated_step_id(implementation_completed_outcome_name),
                    "materialize_artifacts": {
                        "values": _outcome_values(
                            variant="CONTINUE",
                            summary_ref=implementation_summary_ref,
                            include_blocker_ref=None,
                        )
                        + [
                            {
                                "name": "return__blocker-class",
                                "source": {"literal": placeholder_blocker_value},
                                "contract": dict(blocker_contract),
                            }
                        ]
                    },
                }
            ],
        },
        "BLOCKED": {
            "id": _normalize_generated_step_id(f"{step_name}__blocked"),
            "outputs": _forward_result_outputs(
                f"self.steps.{implementation_blocked_outcome_name}.artifacts"
            ),
            "steps": [
                {
                    "name": implementation_blocked_outcome_name,
                    "id": _normalize_generated_step_id(implementation_blocked_outcome_name),
                    "materialize_artifacts": {
                        "values": _outcome_values(
                            variant="BLOCKED",
                            summary_ref=implementation_blocked_summary_ref,
                            include_blocker_ref=implementation_blocker_ref,
                        )
                    },
                }
            ],
        },
    }
    implementation_match_step = {
        "name": plan_approved_match_name,
        "id": _normalize_generated_step_id(plan_approved_match_name),
        "match": {
            "ref": implementation_variant_ref,
            "cases": implementation_cases,
        },
    }
    plan_cases = {
        "APPROVED": {
            "id": _normalize_generated_step_id(f"{step_name}__plan_approved"),
            "outputs": _forward_result_outputs(
                f"root.steps.{plan_approved_match_name}.artifacts"
            ),
            "steps": [
                _publish_summary_step(
                    name="PublishSelectedItemApprovedSummary",
                    summary_ref=f"root.steps.{plan_approved_match_name}.artifacts.return__summary-path",
                ),
                _build_match_projection_anchor_step(
                    match_step_name=step_name,
                    variant_name="APPROVED",
                    case_outputs=_forward_result_outputs(
                        f"root.steps.{plan_approved_match_name}.artifacts"
                    ),
                    context=context,
                    span=expr.span,
                ),
            ],
        },
        "BLOCKED": {
            "id": _normalize_generated_step_id(f"{step_name}__plan_blocked"),
            "outputs": _forward_result_outputs(
                f"self.steps.{plan_blocked_outcome_name}.artifacts"
            ),
            "steps": [
                {
                    "name": plan_blocked_outcome_name,
                    "id": _normalize_generated_step_id(plan_blocked_outcome_name),
                    "materialize_artifacts": {
                        "values": _outcome_values(
                            variant="BLOCKED",
                            summary_ref=plan_summary_ref,
                            include_blocker_ref=plan_blocker_ref,
                        )
                    },
                },
                _publish_summary_step(
                    name="PublishSelectedItemPlanBlockedSummary",
                    summary_ref=plan_summary_ref,
                ),
                _build_match_projection_anchor_step(
                    match_step_name=step_name,
                    variant_name="BLOCKED",
                    case_outputs=_forward_result_outputs(
                        f"self.steps.{plan_blocked_outcome_name}.artifacts"
                    ),
                    context=context,
                    span=expr.span,
                ),
            ],
        },
    }
    _record_step_origin(context, step_name=step_name, step_id=step_id, source=expr)
    _record_step_origin(
        context,
        step_name=implementation_match_step["name"],
        step_id=implementation_match_step["id"],
        source=expr,
    )
    step = {
        "name": step_name,
        "id": step_id,
        "match": {
            "ref": plan_variant_ref,
            "cases": plan_cases,
        },
    }
    return [queue_transition_materialize_step, implementation_match_step, step], _TerminalResult(
        step_name=step_name,
        step_id=step_id,
        output_refs={
            f"return__{field_name}": f"root.steps.{step_name}.artifacts.return__{field_name}"
            for field_name in context.return_output_contracts
        },
        output_kind="match",
        hidden_inputs={},
    )


def _lower_backlog_drain(
    typed_expr: TypedExpr,
    *,
    context: _LoweringContext,
    local_values: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], _TerminalResult]:
    """Lower the autonomous backlog loop to a runtime repeat-until workflow.

    `backlog-drain` is the frontend form for "keep selecting work until there
    is no work, a block occurs, or the iteration cap is reached." Lowering emits
    the loop, calls the selector/runner/gap-drafter workflows through checked
    workflow refs, carries loop state, and normalizes the final result with a
    certified adapter.
    """

    expr = typed_expr.expr
    assert isinstance(expr, BacklogDrainExpr)
    step_name = context.step_name_prefix
    step_id = _normalize_generated_step_id(step_name)
    selector_call_name = f"{step_name}__selector"
    run_item_call_name = f"{step_name}__run_item"
    gap_drafter_call_name = f"{step_name}__gap_drafter"
    selector_signature = context.workflow_catalog.signatures_by_name.get(expr.spec.selector_name)
    run_item_signature = context.workflow_catalog.signatures_by_name.get(expr.spec.run_item_name)
    gap_drafter_signature = context.workflow_catalog.signatures_by_name.get(expr.spec.gap_drafter_name)
    if selector_signature is None or run_item_signature is None or gap_drafter_signature is None:
        raise _compile_error(
            code="workflow_call_unknown",
            message="`backlog-drain` lowering requires all referenced workflows to resolve before lowering",
            span=expr.span,
            form_path=expr.form_path,
        )
    selector_callee = context.lowered_callees.get(expr.spec.selector_name)
    run_item_callee = context.lowered_callees.get(expr.spec.run_item_name)
    gap_drafter_callee = context.lowered_callees.get(expr.spec.gap_drafter_name)
    selector_imported = context.imported_workflow_bundles.get(expr.spec.selector_name)
    run_item_imported = context.imported_workflow_bundles.get(expr.spec.run_item_name)
    gap_drafter_imported = context.imported_workflow_bundles.get(expr.spec.gap_drafter_name)
    if (
        (selector_callee is None and selector_imported is None)
        or (run_item_callee is None and run_item_imported is None)
        or (gap_drafter_callee is None and gap_drafter_imported is None)
    ):
        raise _compile_error(
            code="workflow_call_unknown",
            message="`backlog-drain` lowering requires referenced workflows to be available as same-file callees or registered imported bundles",
            span=expr.span,
            form_path=expr.form_path,
        )
    ctx_value = _resolve_inline_expr_value(expr.spec.ctx_expr, local_values=local_values)
    if not isinstance(ctx_value, Mapping):
        raise _compile_error(
            code="workflow_signature_mismatch",
            message="`backlog-drain :ctx` must lower from workflow inputs in this Stage 3 slice",
            span=expr.spec.ctx_expr.span,
            form_path=expr.spec.ctx_expr.form_path,
        )
    _validate_backlog_drain_provider_metadata(
        expr,
        context=context,
        local_values=local_values,
        selector_workflow=selector_callee.typed_workflow if selector_callee is not None else None,
        run_item_workflow=run_item_callee.typed_workflow if run_item_callee is not None else None,
        gap_drafter_workflow=gap_drafter_callee.typed_workflow if gap_drafter_callee is not None else None,
        selector_imported=selector_imported,
        run_item_imported=run_item_imported,
        gap_drafter_imported=gap_drafter_imported,
    )
    selector_call_target = _specialize_backlog_drain_call_target(
        workflow_name=expr.spec.selector_name,
        role_name="selector",
        imported_bundle=selector_imported,
        providers_expr=expr.spec.providers_expr,
        context=context,
        local_values=local_values,
    )
    run_item_call_target = _specialize_backlog_drain_call_target(
        workflow_name=expr.spec.run_item_name,
        role_name="run-item",
        imported_bundle=run_item_imported,
        providers_expr=expr.spec.providers_expr,
        context=context,
        local_values=local_values,
    )
    gap_drafter_call_target = _specialize_backlog_drain_call_target(
        workflow_name=expr.spec.gap_drafter_name,
        role_name="gap-drafter",
        imported_bundle=gap_drafter_imported,
        providers_expr=expr.spec.providers_expr,
        context=context,
        local_values=local_values,
    )
    selection_payload_type = run_item_signature.params[1][1]
    if not isinstance(selection_payload_type, RecordTypeRef):
        raise _compile_error(
            code="workflow_signature_mismatch",
            message="`backlog-drain :run-item` second parameter must remain a record payload",
            span=expr.span,
            form_path=expr.form_path,
        )
    selection_value: dict[str, Any] = {}
    for _, field_path in _flatten_boundary_leaf_paths(
        selection_payload_type,
        generated_name=run_item_signature.params[1][0],
    ):
        _assign_nested_local_value(
            selection_value,
            field_path,
            f"self.steps.{selector_call_name}.artifacts.return__selection__{'__'.join(field_path)}",
        )
    gap_value = {
        "gap-id": f"self.steps.{selector_call_name}.artifacts.return__gap__gap-id",
    }
    run_mapping = ctx_value.get("run")
    if not isinstance(selection_value, Mapping) or not isinstance(gap_value, Mapping) or not isinstance(run_mapping, Mapping):
        raise _compile_error(
            code="workflow_signature_mismatch",
            message="`backlog-drain` lowering requires typed selector outputs and DrainCtx.run fields",
            span=expr.span,
            form_path=expr.form_path,
        )

    def _return_contract(field_name: str) -> dict[str, Any]:
        contract = context.return_output_contracts.get(field_name)
        if contract is None:
            raise _compile_error(
                code="workflow_return_not_exportable",
                message=f"`backlog-drain` cannot lower missing return contract `{field_name}`",
                span=expr.span,
                form_path=expr.form_path,
            )
        return dict(contract)

    selector_with = _build_call_bindings_from_record_value(
        selector_signature.params[0][0],
        selector_signature.params[0][1],
        ctx_value,
        source_expr=expr.spec.ctx_expr,
    )
    item_ctx_value = {
        "run": run_mapping,
        "item-id": selection_value.get("item-id"),
        "state-root": selection_value.get("item-state-root"),
        "artifact-root": run_mapping.get("artifact-root"),
        "ledger": ctx_value.get("ledger"),
    }
    run_item_with = {
        **_build_call_bindings_from_record_value(
            run_item_signature.params[0][0],
            run_item_signature.params[0][1],
            item_ctx_value,
            source_expr=expr.spec.ctx_expr,
        ),
        **_build_call_bindings_from_record_value(
            run_item_signature.params[1][0],
            run_item_signature.params[1][1],
            selection_value,
            source_expr=expr.spec.ctx_expr,
        ),
    }
    gap_drafter_with = {
        **_build_call_bindings_from_record_value(
            gap_drafter_signature.params[0][0],
            gap_drafter_signature.params[0][1],
            ctx_value,
            source_expr=expr.spec.ctx_expr,
        ),
        **_build_call_bindings_from_record_value(
            gap_drafter_signature.params[1][0],
            gap_drafter_signature.params[1][1],
            gap_value,
            source_expr=expr.spec.ctx_expr,
        ),
    }
    items_processed_artifact = f"{step_name}__items_processed"
    items_processed_contract = {"kind": "scalar", "type": "integer"}
    context.top_level_artifacts[items_processed_artifact] = dict(items_processed_contract)
    accumulator_status_contract = {
        "kind": "scalar",
        "type": "enum",
        "allowed": ["CONTINUE", "EMPTY", "COMPLETED", "BLOCKED"],
    }
    accumulator_run_state_contract = {
        "kind": "relpath",
        "type": "relpath",
        "under": "state",
        "must_exist_target": False,
    }
    accumulator_progress_contract = {
        "kind": "relpath",
        "type": "relpath",
        "under": "artifacts/work",
        "must_exist_target": False,
    }
    accumulator_blocker_contract = dict(_return_contract("blocker-class"))
    placeholder_run_state_ref = "inputs.ctx__manifest"
    placeholder_progress_ref = f"artifacts/work/.orchestrate/workflow_lisp/{step_name}/unused_progress_report.md"
    placeholder_blocker_value = accumulator_blocker_contract["allowed"][0]
    hidden_inputs: dict[str, LoweringOrigin] = {}

    loop_output_definitions = {
        "acc__loop-status": dict(accumulator_status_contract),
        "acc__items-processed": dict(items_processed_contract),
        "acc__run-state": dict(accumulator_run_state_contract),
        "acc__progress-report-path": dict(accumulator_progress_contract),
        "acc__blocker-class": dict(accumulator_blocker_contract),
    }
    loop_outputs = {
        name: {
            **definition,
            "from": {"ref": f"self.steps.{step_name}__route_selection.artifacts.{name}"},
        }
        for name, definition in loop_output_definitions.items()
    }

    def _materialize_outputs_step(
        *,
        name: str,
        step_id_value: str,
        values: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return {
            "name": name,
            "id": step_id_value,
            "materialize_artifacts": {
                "values": values,
            },
        }

    def _scalar_step(
        *,
        name: str,
        step_id_value: str,
        operation: str,
        by: int | None = None,
        publish: bool = False,
    ) -> dict[str, Any]:
        payload = {"artifact": items_processed_artifact}
        if operation == "set":
            payload["value"] = 0
        else:
            assert by is not None
            payload["by"] = by
        step: dict[str, Any] = {
            "name": name,
            "id": step_id_value,
            f"{operation}_scalar": payload,
        }
        if publish:
            step["publishes"] = [{"artifact": items_processed_artifact, "from": items_processed_artifact}]
        return step

    def _managed_call_step(
        *,
        generated_name: str,
        call_target: str,
        with_bindings: Mapping[str, Any],
        lowered_callee: LoweredWorkflow | None,
        imported_bundle: LoadedWorkflowBundle | None,
    ) -> dict[str, Any]:
        step = {
            "name": generated_name,
            "id": _normalize_generated_step_id(generated_name),
            "call": call_target,
            "with": dict(with_bindings),
        }
        if lowered_callee is not None:
            managed_inputs = _managed_inputs_from_mapping(lowered_callee.authored_mapping)
        else:
            managed_inputs = workflow_managed_write_root_inputs(imported_bundle)
        for managed_input in managed_inputs:
            step["with"][managed_input] = (
                f".orchestrate/workflow_lisp/calls/{context.workflow_name}/{generated_name}/${{loop.index}}/{call_target}/{managed_input}.json"
            )
            hidden_inputs[managed_input] = _origin_from_context_source(context, expr)
        _record_step_origin(context, step_name=generated_name, step_id=step["id"], source=expr)
        return step

    def _accumulator_marker_step(
        *,
        name: str,
        step_id_value: str,
        loop_status: str,
        run_state_ref: str,
        progress_ref: str | None = None,
        blocker_ref: str | None = None,
    ) -> dict[str, Any]:
        return _materialize_outputs_step(
            name=name,
            step_id_value=step_id_value,
            values=[
                {
                    "name": "acc__loop-status",
                    "source": {"literal": loop_status},
                    "contract": dict(accumulator_status_contract),
                },
                {
                    "name": "acc__run-state",
                    "source": {"ref": run_state_ref},
                    "contract": dict(accumulator_run_state_contract),
                },
                {
                    "name": "acc__progress-report-path",
                    "source": {"ref": progress_ref} if progress_ref is not None else {"literal": placeholder_progress_ref},
                    "contract": dict(accumulator_progress_contract),
                },
                {
                    "name": "acc__blocker-class",
                    "source": {"ref": blocker_ref} if blocker_ref is not None else {"literal": placeholder_blocker_value},
                    "contract": dict(accumulator_blocker_contract),
                },
            ],
        )

    def _accumulator_outputs(
        *,
        marker_step_name: str,
        items_processed_ref: str,
    ) -> dict[str, Any]:
        return {
            "acc__loop-status": {
                **loop_output_definitions["acc__loop-status"],
                "from": {"ref": f"self.steps.{marker_step_name}.artifacts.acc__loop-status"},
            },
            "acc__items-processed": {
                **loop_output_definitions["acc__items-processed"],
                "from": {"ref": items_processed_ref},
            },
            "acc__run-state": {
                **loop_output_definitions["acc__run-state"],
                "from": {"ref": f"self.steps.{marker_step_name}.artifacts.acc__run-state"},
            },
            "acc__progress-report-path": {
                **loop_output_definitions["acc__progress-report-path"],
                "from": {"ref": f"self.steps.{marker_step_name}.artifacts.acc__progress-report-path"},
            },
            "acc__blocker-class": {
                **loop_output_definitions["acc__blocker-class"],
                "from": {"ref": f"self.steps.{marker_step_name}.artifacts.acc__blocker-class"},
            },
        }

    selector_call_step = _managed_call_step(
        generated_name=selector_call_name,
        call_target=selector_call_target,
        with_bindings=selector_with,
        lowered_callee=selector_callee,
        imported_bundle=selector_imported,
    )
    gap_drafter_call_step = _managed_call_step(
        generated_name=gap_drafter_call_name,
        call_target=gap_drafter_call_target,
        with_bindings=gap_drafter_with,
        lowered_callee=gap_drafter_callee,
        imported_bundle=gap_drafter_imported,
    )
    gap_drafter_call_step["when"] = {
        "compare": {
            "left": {"ref": f"self.steps.{selector_call_name}.artifacts.return__variant"},
            "op": "eq",
            "right": "GAP",
        }
    }
    run_item_call_step = _managed_call_step(
        generated_name=run_item_call_name,
        call_target=run_item_call_target,
        with_bindings=run_item_with,
        lowered_callee=run_item_callee,
        imported_bundle=run_item_imported,
    )
    run_item_call_step["when"] = {
        "compare": {
            "left": {"ref": f"self.steps.{selector_call_name}.artifacts.return__variant"},
            "op": "eq",
            "right": "SELECTED",
        }
    }

    current_items_step_name = f"{step_name}__current_items_processed"
    current_items_ref = f"self.steps.{current_items_step_name}.artifacts.{items_processed_artifact}"
    parent_current_items_ref = f"parent.steps.{current_items_step_name}.artifacts.{items_processed_artifact}"
    current_items_step = _scalar_step(
        name=current_items_step_name,
        step_id_value=_normalize_generated_step_id(current_items_step_name),
        operation="increment",
        by=0,
    )

    empty_route_step_name = f"{step_name}__route_empty_selection"
    empty_marker_name = "MarkEmptySelection"
    completed_marker_name = "MarkCompletedSelection"
    empty_route_step = {
        "name": empty_route_step_name,
        "id": _normalize_generated_step_id(empty_route_step_name),
        "when": {
            "compare": {
                "left": {"ref": f"self.steps.{selector_call_name}.artifacts.return__variant"},
                "op": "eq",
                "right": "EMPTY",
            }
        },
        "if": {
            "compare": {
                "left": {"ref": current_items_ref},
                "op": "eq",
                "right": 0,
            }
        },
        "then": {
            "id": _normalize_generated_step_id(f"{empty_route_step_name}__empty"),
            "outputs": _accumulator_outputs(
                marker_step_name=empty_marker_name,
                items_processed_ref=parent_current_items_ref,
            ),
            "steps": [
                _accumulator_marker_step(
                    name=empty_marker_name,
                    step_id_value="mark_empty_selection",
                    loop_status="EMPTY",
                    run_state_ref=f"parent.steps.{selector_call_name}.artifacts.return__run-state",
                )
            ],
        },
        "else": {
            "id": _normalize_generated_step_id(f"{empty_route_step_name}__completed"),
            "outputs": _accumulator_outputs(
                marker_step_name=completed_marker_name,
                items_processed_ref=parent_current_items_ref,
            ),
            "steps": [
                _accumulator_marker_step(
                    name=completed_marker_name,
                    step_id_value="mark_completed_selection",
                    loop_status="COMPLETED",
                    run_state_ref=f"parent.steps.{selector_call_name}.artifacts.return__run-state",
                )
            ],
        },
    }

    gap_route_step_name = f"{step_name}__route_gap_result"
    if isinstance(gap_drafter_signature.return_type_ref, RecordTypeRef):
        gap_marker_name = "MarkGapContinue"
        gap_route_step = {
            "name": gap_route_step_name,
            "id": _normalize_generated_step_id(gap_route_step_name),
            "when": {
                "compare": {
                    "left": {"ref": f"self.steps.{selector_call_name}.artifacts.return__variant"},
                    "op": "eq",
                    "right": "GAP",
                }
            },
            "if": {
                "compare": {
                    "left": 1,
                    "op": "eq",
                    "right": 1,
                }
            },
            "then": {
                "id": _normalize_generated_step_id(f"{gap_route_step_name}__continue"),
                "outputs": _accumulator_outputs(
                    marker_step_name=gap_marker_name,
                    items_processed_ref=parent_current_items_ref,
                ),
                "steps": [
                    _accumulator_marker_step(
                        name=gap_marker_name,
                        step_id_value="mark_gap_continue",
                        loop_status="CONTINUE",
                        run_state_ref=f"parent.steps.{gap_drafter_call_name}.artifacts.return__run-state",
                    )
                ],
            },
            "else": {
                "id": _normalize_generated_step_id(f"{gap_route_step_name}__continue_else"),
                "outputs": _accumulator_outputs(
                    marker_step_name=gap_marker_name,
                    items_processed_ref=parent_current_items_ref,
                ),
                "steps": [
                    _accumulator_marker_step(
                        name=gap_marker_name,
                        step_id_value="mark_gap_continue_else",
                        loop_status="CONTINUE",
                        run_state_ref=f"parent.steps.{gap_drafter_call_name}.artifacts.return__run-state",
                    )
                ],
            },
        }
    else:
        gap_continue_marker_name = "MarkGapContinue"
        gap_blocked_marker_name = "MarkGapBlocked"
        gap_route_step = {
            "name": gap_route_step_name,
            "id": _normalize_generated_step_id(gap_route_step_name),
            "when": {
                "compare": {
                    "left": {"ref": f"self.steps.{selector_call_name}.artifacts.return__variant"},
                    "op": "eq",
                    "right": "GAP",
                }
            },
            "match": {
                "ref": f"self.steps.{gap_drafter_call_name}.artifacts.return__variant",
                "cases": {
                    "CONTINUE": {
                        "id": _normalize_generated_step_id(f"{gap_route_step_name}__continue"),
                        "outputs": _accumulator_outputs(
                            marker_step_name=gap_continue_marker_name,
                            items_processed_ref=parent_current_items_ref,
                        ),
                        "steps": [
                            _accumulator_marker_step(
                                name=gap_continue_marker_name,
                                step_id_value="mark_gap_continue",
                                loop_status="CONTINUE",
                                run_state_ref=f"parent.steps.{gap_drafter_call_name}.artifacts.return__run-state",
                            )
                        ],
                    },
                    "BLOCKED": {
                        "id": _normalize_generated_step_id(f"{gap_route_step_name}__blocked"),
                        "outputs": _accumulator_outputs(
                            marker_step_name=gap_blocked_marker_name,
                            items_processed_ref=parent_current_items_ref,
                        ),
                        "steps": [
                            _accumulator_marker_step(
                                name=gap_blocked_marker_name,
                                step_id_value="mark_gap_blocked",
                                loop_status="BLOCKED",
                                run_state_ref=placeholder_run_state_ref,
                                progress_ref=f"parent.steps.{gap_drafter_call_name}.artifacts.return__progress-report-path",
                                blocker_ref=f"parent.steps.{gap_drafter_call_name}.artifacts.return__blocker-class",
                            )
                        ],
                    },
                },
            },
        }

    selected_route_step_name = f"{step_name}__route_selected_result"
    increment_selected_step_name = "IncrementSelectedItemsProcessed"
    incremented_items_ref = f"self.steps.{increment_selected_step_name}.artifacts.{items_processed_artifact}"
    selected_continue_marker_name = "MarkSelectedContinue"
    selected_blocked_marker_name = "MarkSelectedBlocked"
    selected_route_step = {
        "name": selected_route_step_name,
        "id": _normalize_generated_step_id(selected_route_step_name),
        "when": {
            "compare": {
                "left": {"ref": f"self.steps.{selector_call_name}.artifacts.return__variant"},
                "op": "eq",
                "right": "SELECTED",
            }
        },
        "match": {
            "ref": f"self.steps.{run_item_call_name}.artifacts.return__variant",
            "cases": {
                "CONTINUE": {
                    "id": _normalize_generated_step_id(f"{selected_route_step_name}__continue"),
                    "outputs": _accumulator_outputs(
                        marker_step_name=selected_continue_marker_name,
                        items_processed_ref=incremented_items_ref,
                    ),
                    "steps": [
                        _scalar_step(
                            name=increment_selected_step_name,
                            step_id_value="increment_selected_items_processed",
                            operation="increment",
                            by=1,
                            publish=True,
                        ),
                        _accumulator_marker_step(
                            name=selected_continue_marker_name,
                            step_id_value="mark_selected_continue",
                            loop_status="CONTINUE",
                            run_state_ref=f"parent.steps.{run_item_call_name}.artifacts.return__run-state",
                        ),
                    ],
                },
                "BLOCKED": {
                    "id": _normalize_generated_step_id(f"{selected_route_step_name}__blocked"),
                    "outputs": _accumulator_outputs(
                        marker_step_name=selected_blocked_marker_name,
                        items_processed_ref=parent_current_items_ref,
                    ),
                    "steps": [
                        _accumulator_marker_step(
                            name=selected_blocked_marker_name,
                            step_id_value="mark_selected_blocked",
                            loop_status="BLOCKED",
                            run_state_ref=f"parent.steps.{run_item_call_name}.artifacts.return__run-state",
                            progress_ref=f"parent.steps.{run_item_call_name}.artifacts.return__summary-path",
                            blocker_ref=f"parent.steps.{run_item_call_name}.artifacts.return__blocker-class",
                        )
                    ],
                },
            },
        },
    }

    route_selection_step_name = f"{step_name}__route_selection"

    def _forward_accumulator_outputs(source_step_name: str) -> dict[str, Any]:
        return {
            name: {
                **definition,
                "from": {"ref": f"parent.steps.{source_step_name}.artifacts.{name}"},
            }
            for name, definition in loop_output_definitions.items()
        }

    route_selection_step = {
        "name": route_selection_step_name,
        "id": _normalize_generated_step_id(route_selection_step_name),
        "match": {
            "ref": f"self.steps.{selector_call_name}.artifacts.return__variant",
            "cases": {
                "EMPTY": {
                    "id": _normalize_generated_step_id(f"{route_selection_step_name}__empty"),
                    "outputs": _forward_accumulator_outputs(empty_route_step_name),
                    "steps": [
                        _build_match_projection_anchor_step(
                            match_step_name=route_selection_step_name,
                            variant_name="EMPTY",
                            case_outputs=_forward_accumulator_outputs(empty_route_step_name),
                            context=context,
                            span=expr.span,
                        )
                    ],
                },
                "GAP": {
                    "id": _normalize_generated_step_id(f"{route_selection_step_name}__gap"),
                    "outputs": _forward_accumulator_outputs(gap_route_step_name),
                    "steps": [
                        _build_match_projection_anchor_step(
                            match_step_name=route_selection_step_name,
                            variant_name="GAP",
                            case_outputs=_forward_accumulator_outputs(gap_route_step_name),
                            context=context,
                            span=expr.span,
                        )
                    ],
                },
                "SELECTED": {
                    "id": _normalize_generated_step_id(f"{route_selection_step_name}__selected"),
                    "outputs": _forward_accumulator_outputs(selected_route_step_name),
                    "steps": [
                        _build_match_projection_anchor_step(
                            match_step_name=route_selection_step_name,
                            variant_name="SELECTED",
                            case_outputs=_forward_accumulator_outputs(selected_route_step_name),
                            context=context,
                            span=expr.span,
                        )
                    ],
                },
            },
        },
    }

    seed_items_processed_step_name = f"{step_name}__seed_items_processed"
    seed_items_processed_step = _scalar_step(
        name=seed_items_processed_step_name,
        step_id_value=_normalize_generated_step_id(seed_items_processed_step_name),
        operation="set",
        publish=True,
    )
    _record_step_origin(
        context,
        step_name=seed_items_processed_step_name,
        step_id=seed_items_processed_step["id"],
        source=expr,
    )
    _record_step_origin(context, step_name=step_name, step_id=step_id, source=expr)
    _record_step_origin(context, step_name=current_items_step_name, step_id=current_items_step["id"], source=expr)
    _record_step_origin(context, step_name=empty_route_step_name, step_id=empty_route_step["id"], source=expr)
    _record_step_origin(context, step_name=gap_route_step_name, step_id=gap_route_step["id"], source=expr)
    _record_step_origin(context, step_name=selected_route_step_name, step_id=selected_route_step["id"], source=expr)
    _record_step_origin(context, step_name=route_selection_step_name, step_id=route_selection_step["id"], source=expr)

    repeat_step = {
        "name": step_name,
        "id": step_id,
        "repeat_until": {
            "id": f"{step_id}__iteration",
            "max_iterations": _render_repeat_until_max_iterations(
                expr.spec.max_iterations_expr,
                local_values=local_values,
            ),
            "steps": [
                selector_call_step,
                current_items_step,
                empty_route_step,
                gap_drafter_call_step,
                gap_route_step,
                run_item_call_step,
                selected_route_step,
                route_selection_step,
            ],
            "outputs": loop_outputs,
            "condition": {
                "compare": {
                    "left": {"ref": "self.outputs.acc__loop-status"},
                    "op": "ne",
                    "right": "CONTINUE",
                }
            },
        },
    }

    result_output_definitions = {
        f"return__{field_name}": dict(contract)
        for field_name, contract in context.return_output_contracts.items()
    }

    def _return_marker_step(
        *,
        name: str,
        step_id_value: str,
        variant: str,
        run_state_ref: str,
        items_processed_ref: str,
        progress_ref: str,
        blocker_ref: str,
    ) -> dict[str, Any]:
        return _materialize_outputs_step(
            name=name,
            step_id_value=step_id_value,
            values=[
                {
                    "name": "return__variant",
                    "source": {"literal": variant},
                    "contract": dict(result_output_definitions["return__variant"]),
                },
                {
                    "name": "return__run-state",
                    "source": {"ref": run_state_ref},
                    "contract": dict(result_output_definitions["return__run-state"]),
                },
                {
                    "name": "return__items-processed",
                    "source": {"ref": items_processed_ref},
                    "contract": dict(result_output_definitions["return__items-processed"]),
                },
                {
                    "name": "return__progress-report-path",
                    "source": {"ref": progress_ref},
                    "contract": dict(result_output_definitions["return__progress-report-path"]),
                },
                {
                    "name": "return__blocker-class",
                    "source": {"ref": blocker_ref},
                    "contract": dict(result_output_definitions["return__blocker-class"]),
                },
            ],
        )

    def _forward_return_outputs(source_step_name: str) -> dict[str, Any]:
        return {
            name: {
                **definition,
                "from": {"ref": f"self.steps.{source_step_name}.artifacts.{name}"},
            }
            for name, definition in result_output_definitions.items()
        }

    normalize_step_name = f"{step_name}__normalize_result"
    normalize_step_id = _normalize_generated_step_id(normalize_step_name)
    _record_step_origin(context, step_name=normalize_step_name, step_id=normalize_step_id, source=expr)
    normalize_step = {
        "name": normalize_step_name,
        "id": normalize_step_id,
        "match": {
            "ref": f"root.steps.{step_name}.artifacts.acc__loop-status",
            "cases": {
                "EMPTY": {
                    "id": _normalize_generated_step_id(f"{normalize_step_name}__empty"),
                    "outputs": _forward_return_outputs("EmitDrainEmpty"),
                    "steps": [
                        _return_marker_step(
                            name="EmitDrainEmpty",
                            step_id_value="emit_drain_empty",
                            variant="EMPTY",
                            run_state_ref=f"root.steps.{step_name}.artifacts.acc__run-state",
                            items_processed_ref=f"root.steps.{step_name}.artifacts.acc__items-processed",
                            progress_ref=f"root.steps.{step_name}.artifacts.acc__progress-report-path",
                            blocker_ref=f"root.steps.{step_name}.artifacts.acc__blocker-class",
                        )
                    ],
                },
                "COMPLETED": {
                    "id": _normalize_generated_step_id(f"{normalize_step_name}__completed"),
                    "outputs": _forward_return_outputs("EmitDrainCompleted"),
                    "steps": [
                        _return_marker_step(
                            name="EmitDrainCompleted",
                            step_id_value="emit_drain_completed",
                            variant="COMPLETED",
                            run_state_ref=f"root.steps.{step_name}.artifacts.acc__run-state",
                            items_processed_ref=f"root.steps.{step_name}.artifacts.acc__items-processed",
                            progress_ref=f"root.steps.{step_name}.artifacts.acc__progress-report-path",
                            blocker_ref=f"root.steps.{step_name}.artifacts.acc__blocker-class",
                        )
                    ],
                },
                "BLOCKED": {
                    "id": _normalize_generated_step_id(f"{normalize_step_name}__blocked"),
                    "outputs": _forward_return_outputs("EmitDrainBlocked"),
                    "steps": [
                        _return_marker_step(
                            name="EmitDrainBlocked",
                            step_id_value="emit_drain_blocked",
                            variant="BLOCKED",
                            run_state_ref=f"root.steps.{step_name}.artifacts.acc__run-state",
                            items_processed_ref=f"root.steps.{step_name}.artifacts.acc__items-processed",
                            progress_ref=f"root.steps.{step_name}.artifacts.acc__progress-report-path",
                            blocker_ref=f"root.steps.{step_name}.artifacts.acc__blocker-class",
                        )
                    ],
                },
                "CONTINUE": {
                    "id": _normalize_generated_step_id(f"{normalize_step_name}__continue"),
                    "outputs": _forward_return_outputs("EmitDrainContinue"),
                    "steps": [
                        _return_marker_step(
                            name="EmitDrainContinue",
                            step_id_value="emit_drain_continue",
                            variant="BLOCKED",
                            run_state_ref=f"root.steps.{step_name}.artifacts.acc__run-state",
                            items_processed_ref=f"root.steps.{step_name}.artifacts.acc__items-processed",
                            progress_ref=f"root.steps.{step_name}.artifacts.acc__progress-report-path",
                            blocker_ref=f"root.steps.{step_name}.artifacts.acc__blocker-class",
                        )
                    ],
                },
            },
        },
    }
    return [seed_items_processed_step, repeat_step, normalize_step], _TerminalResult(
        step_name=normalize_step_name,
        step_id=normalize_step_id,
        output_refs={
            f"return__{field_name}": f"root.steps.{normalize_step_name}.artifacts.return__{field_name}"
            for field_name in context.return_output_contracts
        },
        output_kind="match",
        hidden_inputs=hidden_inputs,
    )


def _required_output_contract(
    context: _LoweringContext,
    field_name: str,
    source_expr: Any,
) -> Mapping[str, Any]:
    """Return a declared workflow output contract or raise a frontend error."""

    contract = context.return_output_contracts.get(field_name)
    if contract is None:
        raise _compile_error(
            code="workflow_return_not_exportable",
            message=f"missing lowered workflow return contract for `{field_name}`",
            span=source_expr.span,
            form_path=source_expr.form_path,
        )
    return contract


def _selected_item_summary_pointer_path(workflow_name: str) -> str:
    """Return the compatibility pointer path for selected-item summaries."""

    return f".orchestrate/workflow_lisp/{workflow_name}/selected_item_summary.txt"


def _validate_backlog_drain_provider_metadata(
    expr: BacklogDrainExpr,
    *,
    context: _LoweringContext,
    local_values: Mapping[str, Any],
    selector_workflow: TypedWorkflowDef | None,
    run_item_workflow: TypedWorkflowDef | None,
    gap_drafter_workflow: TypedWorkflowDef | None,
    selector_imported: LoadedWorkflowBundle | None,
    run_item_imported: LoadedWorkflowBundle | None,
    gap_drafter_imported: LoadedWorkflowBundle | None,
) -> None:
    """Verify backlog-drain provider metadata covers callee requirements."""

    required_provider_names = set()
    required_prompt_names = set()
    for role_name, workflow in (
        ("selector", selector_workflow),
        ("run-item", run_item_workflow),
        ("gap-drafter", gap_drafter_workflow),
    ):
        provider_count, prompt_count = _same_file_workflow_provider_requirements(
            workflow,
            typed_procedures=context.typed_procedures,
        )
        if provider_count:
            required_provider_names.add(f"providers.{role_name}")
        if prompt_count:
            required_prompt_names.add(f"prompts.{role_name}")
    for role_name, imported_bundle in (
        ("selector", selector_imported),
        ("run-item", run_item_imported),
        ("gap-drafter", gap_drafter_imported),
    ):
        provider_count, prompt_count = _imported_bundle_provider_requirements(imported_bundle)
        if provider_count:
            required_provider_names.add(f"providers.{role_name}")
        if prompt_count:
            required_prompt_names.add(f"prompts.{role_name}")

    if not required_provider_names and not required_prompt_names:
        return
    if expr.spec.providers_expr is None:
        raise _compile_error(
            code="backlog_drain_contract_invalid",
            message="`backlog-drain :providers` must satisfy the provider/prompt extern requirements of the selected workflows",
            span=expr.span,
            form_path=expr.form_path,
        )
    available_names = _provider_metadata_names(expr.spec.providers_expr, local_values=local_values)
    missing_names = sorted((required_provider_names | required_prompt_names) - available_names)
    if missing_names:
        raise _compile_error(
            code="backlog_drain_contract_invalid",
            message=(
                "`backlog-drain :providers` is missing required extern bindings: "
                + ", ".join(missing_names)
            ),
            span=expr.spec.providers_expr.span,
            form_path=expr.spec.providers_expr.form_path,
        )


def _imported_bundle_provider_requirements(bundle: LoadedWorkflowBundle | None) -> tuple[int, int]:
    """Count provider/prompt use inside an imported workflow bundle."""

    if bundle is None:
        return 0, 0
    provider_count = 0
    prompt_count = 0
    for step in bundle.surface.steps:
        provider_count += _count_surface_provider_steps(step)
        prompt_count += _count_surface_prompt_steps(step)
    return provider_count, prompt_count


def _count_surface_provider_steps(step: Any) -> int:
    """Count provider steps recursively in an elaborated workflow step tree."""

    total = 1 if getattr(step, "kind", None) == SurfaceStepKind.PROVIDER else 0
    total += sum(_count_surface_provider_steps(nested) for nested in _surface_nested_steps(step))
    return total


def _count_surface_prompt_steps(step: Any) -> int:
    """Count provider steps with prompt assets in an elaborated step tree."""

    total = 1 if getattr(step, "kind", None) == SurfaceStepKind.PROVIDER and getattr(step, "asset_file", None) else 0
    total += sum(_count_surface_prompt_steps(nested) for nested in _surface_nested_steps(step))
    return total


def _surface_nested_steps(step: Any) -> tuple[Any, ...]:
    """Return child steps nested under structured control-flow nodes."""

    nested: list[Any] = []
    then_branch = getattr(step, "then_branch", None)
    else_branch = getattr(step, "else_branch", None)
    if then_branch is not None:
        nested.extend(getattr(then_branch, "steps", ()))
    if else_branch is not None:
        nested.extend(getattr(else_branch, "steps", ()))
    match_cases = getattr(step, "match_cases", None)
    if isinstance(match_cases, Mapping):
        for case in match_cases.values():
            nested.extend(getattr(case, "steps", ()))
    repeat_until = getattr(step, "repeat_until", None)
    if repeat_until is not None:
        nested.extend(getattr(repeat_until, "steps", ()))
    nested.extend(getattr(step, "for_each_steps", ()))
    return tuple(nested)


def _specialize_backlog_drain_call_target(
    *,
    workflow_name: str,
    role_name: str,
    imported_bundle: LoadedWorkflowBundle | None,
    providers_expr: Any | None,
    context: _LoweringContext,
    local_values: Mapping[str, Any],
) -> str:
    """Create a provider/prompt-rebound call target for a drain role if needed."""

    same_file_callee = context.lowered_callees.get(workflow_name)
    if (imported_bundle is None and same_file_callee is None) or providers_expr is None:
        return workflow_name
    provider_name, prompt_name = _provider_role_binding_names(
        providers_expr,
        role_name=role_name,
        local_values=local_values,
    )
    if provider_name is None and prompt_name is None:
        return workflow_name
    provider_binding = context.extern_environment.bindings_by_name.get(provider_name) if provider_name else None
    prompt_binding = context.extern_environment.bindings_by_name.get(prompt_name) if prompt_name else None
    provider_id = provider_binding.provider_id if isinstance(provider_binding, ProviderExtern) else None
    prompt_path = prompt_binding.asset_file if isinstance(prompt_binding, PromptExtern) else None
    specialized_name = f"{workflow_name}__{role_name.replace('-', '_')}_rebound"
    if imported_bundle is not None:
        specialized_bundle = _specialize_imported_bundle_provider_metadata(
            imported_bundle,
            provider_id=provider_id,
            prompt_path=prompt_path,
            alias=specialized_name,
        )
        mutable_imports = context.imported_workflow_bundles
        if isinstance(mutable_imports, dict):
            mutable_imports[specialized_name] = specialized_bundle
    if same_file_callee is not None:
        specialized_workflow = _specialize_same_file_lowered_workflow_provider_metadata(
            same_file_callee,
            provider_id=provider_id,
            prompt_path=prompt_path,
            alias=specialized_name,
        )
        mutable_callees = context.lowered_callees
        if isinstance(mutable_callees, dict):
            mutable_callees[specialized_name] = specialized_workflow
    return specialized_name


def _provider_role_binding_names(
    expr: Any,
    *,
    role_name: str,
    local_values: Mapping[str, Any],
) -> tuple[str | None, str | None]:
    """Extract provider and prompt binding names for one drain role."""

    resolved = _resolve_inline_expr_value(expr, local_values=local_values)
    role_value = _mapping_field(resolved, role_name)
    if role_value is None:
        role_value = _mapping_field(resolved, role_name.replace("-", "_"))
    return _find_first_nameexpr(role_value, prefix="providers."), _find_first_nameexpr(role_value, prefix="prompts.")


def _mapping_field(value: Any, field_name: str) -> Any | None:
    """Read a field from a resolved mapping or frontend record expression."""

    if isinstance(value, Mapping):
        return value.get(field_name)
    if isinstance(value, RecordExpr):
        for name, field_value in value.fields:
            if name == field_name:
                return field_value
        return None
    return None


def _find_first_nameexpr(value: Any, *, prefix: str) -> str | None:
    """Find the first nested name expression with the requested prefix."""

    if isinstance(value, NameExpr):
        return value.name if value.name.startswith(prefix) else None
    if isinstance(value, RecordExpr):
        for _, field_value in value.fields:
            name = _find_first_nameexpr(field_value, prefix=prefix)
            if name is not None:
                return name
        return None
    if isinstance(value, Mapping):
        for field_value in value.values():
            name = _find_first_nameexpr(field_value, prefix=prefix)
            if name is not None:
                return name
    if isinstance(value, tuple):
        for item in value:
            name = _find_first_nameexpr(item, prefix=prefix)
            if name is not None:
                return name
    return None


def _specialize_imported_bundle_provider_metadata(
    bundle: LoadedWorkflowBundle,
    *,
    provider_id: str | None,
    prompt_path: str | None,
    alias: str,
) -> LoadedWorkflowBundle:
    """Clone an imported bundle with provider or prompt metadata rebound."""

    if provider_id is None and prompt_path is None:
        return bundle

    def rewrite_surface_step(step: Any) -> Any:
        updated_step = step
        if getattr(step, "kind", None) == SurfaceStepKind.PROVIDER:
            updated_step = replace(
                updated_step,
                provider=provider_id or getattr(updated_step, "provider", None),
                asset_file=prompt_path or getattr(updated_step, "asset_file", None),
            )
        then_branch = getattr(updated_step, "then_branch", None)
        else_branch = getattr(updated_step, "else_branch", None)
        match_cases = getattr(updated_step, "match_cases", None)
        repeat_until = getattr(updated_step, "repeat_until", None)
        for_each_steps = getattr(updated_step, "for_each_steps", ())
        replacements: dict[str, Any] = {}
        if then_branch is not None:
            replacements["then_branch"] = replace(
                then_branch,
                steps=tuple(rewrite_surface_step(step) for step in then_branch.steps),
            )
        if else_branch is not None:
            replacements["else_branch"] = replace(
                else_branch,
                steps=tuple(rewrite_surface_step(step) for step in else_branch.steps),
            )
        if isinstance(match_cases, Mapping):
            replacements["match_cases"] = MappingProxyType(
                {
                    name: replace(case, steps=tuple(rewrite_surface_step(step) for step in case.steps))
                    for name, case in match_cases.items()
                }
            )
        if repeat_until is not None:
            replacements["repeat_until"] = replace(
                repeat_until,
                steps=tuple(rewrite_surface_step(step) for step in repeat_until.steps),
            )
        if for_each_steps:
            replacements["for_each_steps"] = tuple(rewrite_surface_step(step) for step in for_each_steps)
        if replacements:
            updated_step = replace(updated_step, **replacements)
        return updated_step

    rewritten_surface = replace(
        bundle.surface,
        name=alias,
        steps=tuple(rewrite_surface_step(step) for step in bundle.surface.steps),
    )
    rewritten_nodes = {}
    for node_id, node in bundle.ir.nodes.items():
        execution_config = getattr(node, "execution_config", None)
        if isinstance(execution_config, ProviderStepConfig):
            execution_config = replace(
                execution_config,
                provider=provider_id or execution_config.provider,
                asset_file=prompt_path or execution_config.asset_file,
            )
            rewritten_nodes[node_id] = replace(node, execution_config=execution_config)
        else:
            rewritten_nodes[node_id] = node
    rewritten_ir = replace(
        bundle.ir,
        name=alias,
        nodes=MappingProxyType(rewritten_nodes),
    )
    return replace(bundle, surface=rewritten_surface, ir=rewritten_ir)


def _specialize_same_file_lowered_workflow_provider_metadata(
    lowered_workflow: LoweredWorkflow,
    *,
    provider_id: str | None,
    prompt_path: str | None,
    alias: str,
) -> LoweredWorkflow:
    """Clone a same-file lowered workflow with provider/prompt metadata rebound."""

    if provider_id is None and prompt_path is None:
        return lowered_workflow

    def rewrite(value: Any) -> Any:
        if isinstance(value, list):
            return [rewrite(item) for item in value]
        if isinstance(value, Mapping):
            rewritten = {
                key: rewrite(item)
                for key, item in value.items()
            }
            if isinstance(value.get("provider"), str):
                rewritten["provider"] = provider_id or str(value["provider"])
                if "asset_file" in rewritten:
                    rewritten["asset_file"] = prompt_path or rewritten["asset_file"]
            return rewritten
        return value

    definition = replace(lowered_workflow.typed_workflow.definition, name=alias)
    signature = replace(lowered_workflow.typed_workflow.signature, name=alias)
    typed_workflow = replace(
        lowered_workflow.typed_workflow,
        definition=definition,
        signature=signature,
    )
    authored_mapping = rewrite(lowered_workflow.authored_mapping)
    assert isinstance(authored_mapping, dict)
    authored_mapping["name"] = alias
    return LoweredWorkflow(
        typed_workflow=typed_workflow,
        authored_mapping=authored_mapping,
        origin_map=lowered_workflow.origin_map,
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
        if isinstance(expr, ReviewReviseLoopExpr):
            if isinstance(expr.review_provider, NameExpr):
                provider_names.add(expr.review_provider.name)
            if isinstance(expr.fix_provider, NameExpr):
                provider_names.add(expr.fix_provider.name)
            if isinstance(expr.review_prompt, NameExpr):
                prompt_names.add(expr.review_prompt.name)
            if isinstance(expr.fix_prompt, NameExpr):
                prompt_names.add(expr.fix_prompt.name)
            for value in expr.inputs:
                walk(value)
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
    """Return provider and prompt requirement counts for a same-file workflow."""

    if typed_workflow is None:
        return 0, 0
    provider_names, prompt_names = _workflow_extern_requirements(
        typed_workflow,
        typed_procedures=typed_procedures,
    )
    return len(provider_names), len(prompt_names)


def _provider_metadata_names(expr: Any, *, local_values: Mapping[str, Any]) -> set[str]:
    """Collect provider/prompt name expressions reachable from a metadata value."""

    resolved = _resolve_inline_expr_value(expr, local_values=local_values)
    names: set[str] = set()

    def walk(value: Any) -> None:
        if isinstance(value, NameExpr):
            names.add(value.name)
            return
        if isinstance(value, RecordExpr):
            for _, field_value in value.fields:
                walk(field_value)
            return
        if isinstance(value, Mapping):
            for field_value in value.values():
                walk(field_value)
            return
        if isinstance(value, tuple):
            for item in value:
                walk(item)

    walk(resolved if resolved is not None else expr)
    return names


def _lower_with_phase(
    typed_expr: TypedExpr,
    *,
    context: _LoweringContext,
    local_values: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], _TerminalResult]:
    """Enter a derived phase scope and lower the body inside it."""

    expr = typed_expr.expr
    assert isinstance(expr, WithPhaseExpr)
    lowering_phase_scope = _resolve_active_phase_scope(expr, local_values=local_values)
    scoped_context = _copy_context_with_phase_scope(context, lowering_phase_scope)
    return _lower_expression(
        TypedExpr(
            expr=expr.body,
            type_ref=typed_expr.type_ref,
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


def _managed_inputs_from_bundle(bundle: LoadedWorkflowBundle | None) -> tuple[str, ...]:
    """Return generated write-root inputs declared by an imported bundle."""

    if bundle is None:
        return ()
    inputs = getattr(bundle.surface, "inputs", {})
    if not isinstance(inputs, Mapping):
        return ()
    return tuple(
        name for name in inputs if isinstance(name, str) and name.startswith("__write_root__")
    )


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
    return local_values


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
    if isinstance(value, LiteralExpr):
        operand: bool | dict[str, str] = bool(value.value)
    elif isinstance(value, str):
        operand = {"ref": value}
    else:
        raise _compile_error(
            code="workflow_return_not_exportable",
            message="boolean guards must lower from literals or workflow inputs/refs",
            span=expr.span,
            form_path=expr.form_path,
        )
    return {
        "compare": {
            "left": operand,
            "op": "eq",
            "right": True,
        }
    }


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
    if isinstance(value, str):
        return {"ref": value}
    raise _compile_error(
        code="workflow_signature_mismatch",
        message="Stage 3 lowering requires same-file call bindings to resolve to workflow inputs",
        span=expr.span,
        form_path=expr.form_path,
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
        if not isinstance(ref, str):
            raise _compile_error(
                code="workflow_signature_mismatch",
                message="Stage 3 lowering requires synthesized call bindings to resolve to workflow inputs or prior outputs",
                span=source_expr.span,
                form_path=source_expr.form_path,
            )
        bindings[generated_name] = {"ref": ref}
    return bindings


def _resolve_expr_local_value(expr: Any, *, local_values: Mapping[str, Any]) -> Any:
    """Resolve simple name, field, and phase-target expressions from locals."""

    if isinstance(expr, NameExpr):
        return local_values.get(expr.name)
    if isinstance(expr, FieldAccessExpr):
        base_value = local_values.get(expr.base.name)
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


def _resolve_inline_field_value(
    value: Any,
    *,
    field_path: tuple[str, ...],
    local_values: Mapping[str, Any],
) -> Any:
    """Resolve a nested field path through inline mappings or record expressions."""

    current = value
    for field_name in field_path:
        if current is not None and not isinstance(current, (Mapping, RecordExpr)):
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
                raise _compile_error(
                    code="phase_translation_body_invalid",
                    message="phase stdlib prompt inputs must lower from flattened workflow inputs or approved phase targets",
                    span=source_expr.span,
                    form_path=source_expr.form_path,
                )
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


def _resolve_nested_local_value(value: Any, field_path: tuple[str, ...]) -> Any:
    """Follow a flattened field path through a nested local-value mapping."""

    current = value
    for field_name in field_path:
        if not isinstance(current, Mapping):
            return None
        current = current.get(field_name)
    return current


def _build_record_local_value(type_ref: RecordTypeRef, *, generated_name: str) -> dict[str, Any]:
    """Represent a record parameter as nested refs to flattened inputs."""

    local_value: dict[str, Any] = {}
    for field in type_ref.definition.fields:
        field_type = type_ref.field_types[field.name]
        leaf_name = f"{generated_name}__{field.name}"
        if isinstance(field_type, RecordTypeRef):
            local_value[field.name] = _build_record_local_value(field_type, generated_name=leaf_name)
        else:
            local_value[field.name] = f"inputs.{leaf_name}"
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


def _build_output_step_local_value(output_refs: Mapping[str, str]) -> dict[str, Any]:
    """Convert flattened terminal output refs into nested local-value shape."""

    local_value: dict[str, Any] = {}
    for output_name, ref in output_refs.items():
        field_path = output_name.removeprefix("return__").split("__")
        current = local_value
        for field_name in field_path[:-1]:
            next_current = current.get(field_name)
            if not isinstance(next_current, dict):
                next_current = {}
                current[field_name] = next_current
            current = next_current
        current[field_path[-1]] = ref
    return local_value


def _build_union_step_local_value(output_refs: Mapping[str, str]) -> dict[str, Any]:
    """Represent union outputs with the same nested mapping as records."""

    return _build_output_step_local_value(output_refs)


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


def _flatten_boundary_leaf_paths(
    type_ref: RecordTypeRef | UnionTypeRef,
    *,
    generated_name: str,
    field_path: tuple[str, ...] = (),
) -> tuple[tuple[str, tuple[str, ...]], ...]:
    """Return generated boundary names paired with frontend field paths."""

    if isinstance(type_ref, UnionTypeRef):
        return tuple(
            (field.generated_name, field.source_path[1:])
            for field in derive_workflow_boundary_fields(
                type_ref,
                generated_name=generated_name,
                source_path=("return",),
                span=type_ref.definition.span,
                form_path=("workflow-lisp", "defunion", type_ref.name),
            )
        )
    flattened: list[tuple[str, tuple[str, ...]]] = []
    for field in type_ref.definition.fields:
        field_type = type_ref.field_types[field.name]
        next_generated_name = f"{generated_name}__{field.name}"
        next_field_path = field_path + (field.name,)
        if isinstance(field_type, RecordTypeRef):
            flattened.extend(
                _flatten_boundary_leaf_paths(
                    field_type,
                    generated_name=next_generated_name,
                    field_path=next_field_path,
                )
            )
            continue
        flattened.append((next_generated_name, next_field_path))
    return tuple(flattened)


def _flatten_record_output_refs(step_name: str, type_ref: RecordTypeRef) -> dict[str, str]:
    """Build flattened workflow return refs for a record-producing step."""

    return {
        f"return__{'__'.join(field_path)}": f"root.steps.{step_name}.artifacts.{'__'.join(field_path)}"
        for _, field_path in _flatten_boundary_leaf_paths(type_ref, generated_name="return")
    }


def _record_expr_value_at_path(record_expr: RecordExpr, field_path: tuple[str, ...]) -> Any:
    """Read a nested field from an authored `record` expression."""

    current: Any = record_expr
    for field_name in field_path:
        if not isinstance(current, RecordExpr):
            raise _compile_error(
                code="workflow_return_not_exportable",
                message=(
                    f"record return field `{'__'.join(field_path)}` must lower from nested record expressions "
                    "when the workflow return type contains nested records"
                ),
                span=record_expr.span,
                form_path=record_expr.form_path,
            )
        current = _record_field_value(current, field_name)
    return current


def _render_provider_artifact_ref(provider_step_name: str, field_access: FieldAccessExpr) -> str | None:
    """Render a provider result field access as a step artifact ref."""

    if not field_access.fields:
        return None
    return f"root.steps.{provider_step_name}.artifacts.{'__'.join(field_access.fields)}"


def _record_output_refs(step_name: str, type_ref: Any) -> dict[str, str]:
    """Return flattened output refs for a record or union result type."""

    if isinstance(type_ref, RecordTypeRef):
        return _flatten_record_output_refs(step_name, type_ref)
    if isinstance(type_ref, UnionTypeRef):
        return {
            output_name: f"root.steps.{step_name}.artifacts.{'__'.join(field_path)}"
            for output_name, field_path in _flatten_boundary_leaf_paths(type_ref, generated_name="return")
        }
    return {}


def _flatten_return_output_names(context: _LoweringContext) -> tuple[str, ...]:
    """Return flattened output names for the active workflow return contract."""

    return tuple(f"return__{field_name}" for field_name in context.return_output_contracts)


def _return_field_path(field_name: str) -> tuple[str, ...]:
    """Convert a flattened return field name into a nested field path."""

    return tuple(field_name.split("__"))


def _build_match_projection_anchor_step(
    *,
    match_step_name: str,
    variant_name: str,
    case_outputs: Mapping[str, Any],
    context: _LoweringContext,
    span: SourceSpan,
) -> dict[str, Any]:
    """Build a small step that gives a match branch stable output refs."""

    anchor_ref = _first_case_output_ref(case_outputs)
    if anchor_ref is None:
        raise _compile_error(
            code="workflow_return_not_exportable",
            message="match return arms must expose at least one exportable field in this Stage 3 slice",
            span=span,
            form_path=context.signature.form_path,
        )
    step_name = f"{match_step_name}__{variant_name.lower()}__projection_anchor"
    step_id = _normalize_generated_step_id(step_name)
    _record_step_origin(
        context,
        step_name=step_name,
        step_id=step_id,
        source=LoweringOrigin(span=span, form_path=context.signature.form_path),
    )
    return {
        "name": step_name,
        "id": step_id,
        "assert": {
            "compare": {
                "left": {"ref": anchor_ref},
                "op": "eq",
                "right": {"ref": anchor_ref},
            }
        },
    }


def _first_case_output_ref(case_outputs: Mapping[str, Any]) -> str | None:
    """Find any output ref suitable for a match projection anchor assert."""

    for output in case_outputs.values():
        if not isinstance(output, Mapping):
            continue
        source = output.get("from")
        if isinstance(source, Mapping) and isinstance(source.get("ref"), str):
            return str(source["ref"])
    return None


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

    if not isinstance(type_ref, UnionTypeRef):
        raise _compile_error(
            code="review_loop_result_contract_invalid",
            message="`review-revise-loop` lowering requires a union return type",
            span=span,
            form_path=form_path,
        )
    contracts = _union_case_contract_definitions(
        type_ref,
        variant_name=variant_name,
        workflow_name=context.workflow_name,
        step_name=context.step_name_prefix,
        span=span,
        form_path=form_path,
    )
    return {
        field_name: {
            **definition,
            "from": {"ref": f"root.steps.{source_step_name}.artifacts.{field_name}"},
        }
        for field_name, definition in contracts.items()
    }


def _review_loop_result_output_contracts(
    type_ref: Any,
    *,
    context: _LoweringContext,
    span: SourceSpan,
    form_path: tuple[str, ...],
) -> dict[str, dict[str, Any]]:
    """Build all flattened output contracts for a review-loop result union."""

    return _union_output_contracts(
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
            outputs.setdefault(field["name"], _surface_contract_from_structured_field(field))
    return outputs


def _resume_start_bundle_ref(
    start_expr: Any,
    *,
    start_terminal: _TerminalResult,
    context: _LoweringContext,
) -> str:
    """Find the canonical bundle path produced by a `resume-or-start` start arm."""

    if isinstance(start_expr, CommandResultExpr):
        return f"inputs.__write_root__{start_terminal.step_id}__result_bundle"
    if isinstance(start_expr, CallExpr):
        bundle_input_name = _call_result_bundle_input_name(
            start_expr.callee_name,
            context=context,
            span=start_expr.span,
            form_path=start_expr.form_path,
        )
        return (
            f".orchestrate/workflow_lisp/calls/{context.workflow_name}/{start_terminal.step_name}/"
            f"{start_expr.callee_name}/{bundle_input_name}.json"
        )
    if isinstance(start_expr, (RunProviderPhaseExpr, ProduceOneOfExpr)):
        if context.phase_scope is None:
            raise _compile_error(
                code="phase_translation_body_invalid",
                message="phase-scoped resume start lowering requires an active phase scope",
                span=start_expr.span,
                form_path=start_expr.form_path,
            )
        return context.phase_scope.bundle_path_ref
    if isinstance(start_expr, ProviderResultExpr):
        if context.phase_scope is None:
            raise _compile_error(
                code="resume_or_start_contract_invalid",
                message="`resume-or-start :start` provider results must lower inside an active phase scope",
                span=start_expr.span,
                form_path=start_expr.form_path,
            )
        return context.phase_scope.bundle_path_ref
    raise _compile_error(
        code="resume_or_start_contract_invalid",
        message="`resume-or-start :start` must lower to one canonical bundle path in this slice",
        span=start_expr.span,
        form_path=start_expr.form_path,
    )


def _call_result_bundle_input_name(
    callee_name: str,
    *,
    context: _LoweringContext,
    span: SourceSpan,
    form_path: tuple[str, ...],
) -> str:
    """Find the generated bundle input name for a structured workflow call."""

    lowered_callee = context.lowered_callees.get(callee_name)
    if lowered_callee is None:
        raise _compile_error(
            code="resume_or_start_contract_invalid",
            message="`resume-or-start :start` workflow call must lower through an available structured-result callee",
            span=span,
            form_path=form_path,
        )
    return _workflow_result_bundle_input_name(
        lowered_callee.authored_mapping,
        span=span,
        form_path=form_path,
    )


def _workflow_result_bundle_input_name(
    authored_mapping: Mapping[str, object],
    *,
    span: SourceSpan,
    form_path: tuple[str, ...],
) -> str:
    """Inspect a lowered callee and recover its terminal result-bundle input."""

    outputs = authored_mapping.get("outputs")
    if not isinstance(outputs, Mapping):
        raise _compile_error(
            code="resume_or_start_contract_invalid",
            message="`resume-or-start :start` workflow call must expose step-backed return outputs",
            span=span,
            form_path=form_path,
        )
    terminal_step_name: str | None = None
    for output_spec in outputs.values():
        if not isinstance(output_spec, Mapping):
            continue
        source = output_spec.get("from")
        if not isinstance(source, Mapping):
            continue
        ref = source.get("ref")
        if not isinstance(ref, str):
            continue
        match = re.match(r"^(?:self|root)\.steps\.([^.]+)\.artifacts\.[^.]+$", ref)
        if match is None:
            continue
        candidate = match.group(1)
        if terminal_step_name is None:
            terminal_step_name = candidate
            continue
        if terminal_step_name != candidate:
            raise _compile_error(
                code="resume_or_start_contract_invalid",
                message="`resume-or-start :start` workflow call must normalize through one terminal structured-result step",
                span=span,
                form_path=form_path,
            )
    if terminal_step_name is None:
        raise _compile_error(
            code="resume_or_start_contract_invalid",
            message="`resume-or-start :start` workflow call must expose return outputs backed by one terminal step",
            span=span,
            form_path=form_path,
        )
    terminal_step = _find_authored_step_by_name(authored_mapping.get("steps"), terminal_step_name)
    if terminal_step is None:
        raise _compile_error(
            code="resume_or_start_contract_invalid",
            message="`resume-or-start :start` workflow call terminal step is not available for bundle recovery",
            span=span,
            form_path=form_path,
        )
    for contract_key in ("output_bundle", "variant_output"):
        contract = terminal_step.get(contract_key)
        if not isinstance(contract, Mapping):
            continue
        path = contract.get("path")
        if isinstance(path, str) and path.startswith("${inputs.") and path.endswith("}"):
            return path.removeprefix("${inputs.").removesuffix("}")
    raise _compile_error(
        code="resume_or_start_contract_invalid",
        message="`resume-or-start :start` workflow call must expose one canonical structured-result bundle path",
        span=span,
        form_path=form_path,
    )


def _find_authored_step_by_name(steps: Any, step_name: str) -> Mapping[str, object] | None:
    """Find a generated step by name, recursing through match/repeat bodies."""

    if not isinstance(steps, list):
        return None
    for step in steps:
        if not isinstance(step, Mapping):
            continue
        if step.get("name") == step_name:
            return step
        repeat = step.get("repeat_until")
        if isinstance(repeat, Mapping):
            found = _find_authored_step_by_name(repeat.get("steps"), step_name)
            if found is not None:
                return found
        match = step.get("match")
        if isinstance(match, Mapping):
            for case in (match.get("cases") or {}).values():
                if not isinstance(case, Mapping):
                    continue
                found = _find_authored_step_by_name(case.get("steps"), step_name)
                if found is not None:
                    return found
    return None


def _resume_required_artifact_fields(
    type_ref: Any,
    *,
    context: _LoweringContext,
    span: SourceSpan,
    form_path: tuple[str, ...],
) -> Mapping[str, tuple[str, ...]]:
    """Compute artifact fields that must still exist for reusable state."""

    if isinstance(type_ref, RecordTypeRef):
        fields = derive_structured_result_contract(
            type_ref,
            workflow_name=context.workflow_name,
            step_id=context.step_name_prefix,
            span=span,
            form_path=form_path,
        ).payload["fields"]
        return {
            type_ref.name: tuple(
                field.name
                for index, field in enumerate(type_ref.definition.fields)
                if _surface_contract_from_structured_field(fields[index])["kind"] == "relpath"
            )
        }
    if not isinstance(type_ref, UnionTypeRef):
        return {}
    required: dict[str, tuple[str, ...]] = {}
    for variant in type_ref.definition.variants:
        contracts = _union_case_contract_definitions(
            type_ref,
            variant_name=variant.name,
            workflow_name=context.workflow_name,
            step_name=context.step_name_prefix,
            span=span,
            form_path=form_path,
        )
        required[variant.name] = tuple(
            field_name
            for field_name, definition in contracts.items()
            if field_name != "variant" and definition.get("kind") == "relpath"
        )
    return required


def _origin_for_workflow(
    typed_workflow: TypedWorkflowDef,
    *,
    typed_procedures: Mapping[str, TypedProcedureDef],
) -> LoweringOrigin:
    """Choose the source-map origin for an authored workflow mapping."""

    body_expr = typed_workflow.typed_body.expr
    if isinstance(body_expr, ProcedureCallExpr):
        procedure = typed_procedures.get(body_expr.callee_name)
        if procedure is not None and procedure.resolved_lowering_mode == ProcedureLoweringMode.INLINE:
            return LoweringOrigin(
                span=typed_workflow.definition.span,
                form_path=typed_workflow.definition.form_path,
                expansion_stack=typed_workflow.definition.expansion_stack,
                notes=_procedure_provenance_notes(body_expr, procedure),
            )
    return _origin_from_source(typed_workflow.definition)


def _procedure_provenance_notes(call_expr: ProcedureCallExpr, procedure: TypedProcedureDef) -> tuple[str, ...]:
    """Describe the call site and definition behind an inlined procedure."""

    call_start = call_expr.span.start
    definition_start = procedure.definition.span.start
    return (
        f"procedure call site at {call_start.path}:{call_start.line}:{call_start.column}",
        f"procedure definition at {definition_start.path}:{definition_start.line}:{definition_start.column}",
    )


def _lower_match_output_field(
    *,
    record_expr: RecordExpr,
    field_name: str,
    generated_output_name: str,
    contract_definition: Mapping[str, Any],
    match_step_id: str,
    variant_name: str,
    binding_name: str,
    binding_terminal: _TerminalResult,
    context: _LoweringContext,
    local_values: Mapping[str, Any],
) -> dict[str, Any]:
    """Lower one matched record field into a branch-local output projection."""

    value = _record_expr_value_at_path(record_expr, _return_field_path(field_name))
    if isinstance(value, FieldAccessExpr) and value.base.name == binding_name:
        bound_ref = binding_terminal.output_refs.get(f"return__{'__'.join(value.fields)}")
        if bound_ref is not None:
            return {
                "steps": [],
                "output": {
                    **contract_definition,
                    "from": {"ref": bound_ref},
                },
            }
    source_ref = _render_existing_output_ref(value, local_values=local_values)
    if source_ref is not None:
        return {
            "steps": [],
            "output": {
                **contract_definition,
                "from": {"ref": source_ref},
            },
        }
    raise _compile_error(
        code="workflow_return_not_exportable",
        message=(
            f"record return field `{field_name}` must lower from the matched structured result "
            "in this Stage 3 slice"
        ),
        span=record_expr.span,
        form_path=record_expr.form_path,
    )


def _lower_record_expr(
    typed_expr: TypedExpr,
    *,
    context: _LoweringContext,
    local_values: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], _TerminalResult]:
    """Project a record return expression from existing step-backed refs."""

    record_expr = typed_expr.expr
    assert isinstance(record_expr, RecordExpr)
    output_refs: dict[str, str] = {}
    for field_name in context.return_output_contracts:
        output_name = f"return__{field_name}"
        value = _record_expr_value_at_path(record_expr, _return_field_path(field_name))
        source_ref = _render_existing_output_ref(value, local_values=local_values)
        if source_ref is None:
            raise _compile_error(
                code="workflow_return_not_exportable",
                message=(
                    f"record return field `{field_name}` must lower from an existing step artifact "
                    "or structured statement output in this Stage 3 slice"
                ),
                span=record_expr.span,
                form_path=record_expr.form_path,
            )
        output_refs[output_name] = source_ref
    return [], _TerminalResult(
        step_name=context.step_name_prefix,
        step_id=f"{_normalize_generated_step_id(context.step_name_prefix)}__return_projection",
        output_refs=output_refs,
        output_kind="projection",
        hidden_inputs={},
    )


def _render_existing_output_ref(expr: Any, *, local_values: Mapping[str, Any]) -> str | None:
    """Return a shared runtime ref when an expression already names one."""

    value = _resolve_inline_expr_value(expr, local_values=local_values)
    if not isinstance(value, str):
        return None
    if value.startswith("root.steps.") or value.startswith("self.steps.") or value.startswith("inputs."):
        return value
    return None


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


def _copy_context_with_phase_scope(
    context: _LoweringContext,
    phase_scope: _ActivePhaseScope,
) -> _LoweringContext:
    """Clone lowering context while installing the active phase scope."""

    return _LoweringContext(
        workflow_name=context.workflow_name,
        step_name_prefix=context.step_name_prefix,
        workflow_path=context.workflow_path,
        signature=context.signature,
        authored_input_contracts=context.authored_input_contracts,
        workflow_catalog=context.workflow_catalog,
        imported_workflow_bundles=context.imported_workflow_bundles,
        extern_environment=context.extern_environment,
        command_boundary_environment=context.command_boundary_environment,
        lowered_callees=context.lowered_callees,
        typed_procedures=context.typed_procedures,
        type_env=context.type_env,
        step_spans=context.step_spans,
        generated_input_spans=context.generated_input_spans,
        authored_generated_inputs=context.authored_generated_inputs,
        internal_generated_input_reasons=context.internal_generated_input_reasons,
        generated_output_spans=context.generated_output_spans,
        generated_path_spans=context.generated_path_spans,
        top_level_artifacts=context.top_level_artifacts,
        inline_call_counters=context.inline_call_counters,
        origin_notes=context.origin_notes,
        boundary_projection=context.boundary_projection,
        return_output_contracts=context.return_output_contracts,
        phase_scope=phase_scope,
    )


def _copy_context_with_step_prefix(context: _LoweringContext, *, step_name_prefix: str) -> _LoweringContext:
    """Clone context state while changing the generated step-name prefix."""

    return _LoweringContext(
        workflow_name=context.workflow_name,
        step_name_prefix=step_name_prefix,
        workflow_path=context.workflow_path,
        signature=context.signature,
        authored_input_contracts=context.authored_input_contracts,
        workflow_catalog=context.workflow_catalog,
        imported_workflow_bundles=context.imported_workflow_bundles,
        extern_environment=context.extern_environment,
        command_boundary_environment=context.command_boundary_environment,
        lowered_callees=context.lowered_callees,
        typed_procedures=context.typed_procedures,
        type_env=context.type_env,
        step_spans=context.step_spans,
        generated_input_spans=context.generated_input_spans,
        authored_generated_inputs=context.authored_generated_inputs,
        internal_generated_input_reasons=context.internal_generated_input_reasons,
        generated_output_spans=context.generated_output_spans,
        generated_path_spans=context.generated_path_spans,
        top_level_artifacts=context.top_level_artifacts,
        inline_call_counters=context.inline_call_counters,
        origin_notes=context.origin_notes,
        boundary_projection=context.boundary_projection,
        return_output_contracts=context.return_output_contracts,
        phase_scope=context.phase_scope,
    )


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

    if isinstance(
        expr,
        (
            ProviderResultExpr,
            CommandResultExpr,
            RunProviderPhaseExpr,
            ProduceOneOfExpr,
            ReviewReviseLoopExpr,
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
        procedure = context.typed_procedures.get(expr.callee_name)
        if procedure is None:
            raise _compile_error(
                code="procedure_call_unknown",
                message=f"unknown procedure callee `{expr.callee_name}` during lowering",
                span=expr.span,
                form_path=expr.form_path,
            )
        return procedure.signature.return_type_ref
    raise _compile_error(
        code="workflow_return_not_exportable",
        message=f"Stage 3 lowering does not support let* binding `{type(expr).__name__}`",
        span=expr.span,
        form_path=expr.form_path,
    )


def _render_candidate_target(candidate: Any, *, context: _LoweringContext) -> str:
    """Render the output target for a `produce-one-of` candidate."""

    for field_spec in candidate.fields:
        target_expr = getattr(field_spec, "target_expr", None)
        if isinstance(target_expr, PhaseTargetExpr):
            target_ref = context.phase_scope.target_refs.get(target_expr.target_name) if context.phase_scope is not None else None
            if isinstance(target_ref, str):
                return target_ref
    raise _compile_error(
        code="produce_one_of_candidate_invalid",
        message=f"`produce-one-of` candidate `{candidate.variant_name}` requires a phase-target path",
        span=context.signature.span,
        form_path=context.signature.form_path,
    )


def _render_candidate_target_artifact_name(candidate: Any) -> str:
    """Choose the artifact name exposed for a `produce-one-of` candidate."""

    for field_spec in candidate.fields:
        target_expr = getattr(field_spec, "target_expr", None)
        if isinstance(target_expr, PhaseTargetExpr):
            return _phase_prompt_artifact_name_for_target(target_expr)
    fallback_target = next(
        (getattr(field_spec, "target_expr", None) for field_spec in candidate.fields if getattr(field_spec, "target_expr", None) is not None),
        None,
    )
    if fallback_target is None:
        raise ValueError(f"`produce-one-of` candidate `{candidate.variant_name}` requires a phase-target path")
    raise _compile_error(
        code="produce_one_of_candidate_invalid",
        message=f"`produce-one-of` candidate `{candidate.variant_name}` requires a phase-target path",
        span=fallback_target.span,
        form_path=fallback_target.form_path,
    )


def _join_ref_path(base_ref: str, suffix: str) -> str:
    """Append a path suffix to a substitution ref without losing templating."""

    if base_ref.startswith("${"):
        return f"{base_ref}/{suffix}"
    return "${" + base_ref + "}/" + suffix


def _resolve_procedure_lowering(
    typed_procedures: tuple[TypedProcedureDef, ...],
    *,
    typed_workflows: tuple[TypedWorkflowDef, ...],
    workflow_path: Path,
    type_env: FrontendTypeEnvironment,
) -> Mapping[str, TypedProcedureDef]:
    """Decide inline versus private-workflow lowering for each procedure."""

    call_counts, lowerable_call_sites = _procedure_private_call_site_analysis(
        typed_procedures,
        typed_workflows=typed_workflows,
        type_env=type_env,
    )
    resolved: dict[str, TypedProcedureDef] = {}
    typed_procedures_by_name = {
        procedure.definition.name: procedure for procedure in typed_procedures
    }
    for procedure in typed_procedures:
        requested = procedure.signature.requested_lowering_mode
        boundary_valid = _procedure_private_boundary_valid(procedure)
        body_valid = _procedure_private_body_valid(
            procedure,
            typed_procedures_by_name=typed_procedures_by_name,
            type_env=type_env,
        )
        if requested == ProcedureLoweringMode.PRIVATE_WORKFLOW and not boundary_valid:
            raise _compile_error(
                code="proc_private_workflow_boundary_invalid",
                message=f"procedure `{procedure.definition.name}` cannot lower as `private-workflow` in Stage 3",
                span=procedure.definition.span,
                form_path=procedure.definition.form_path,
            )
        if requested == ProcedureLoweringMode.PRIVATE_WORKFLOW and not body_valid:
            raise _compile_error(
                code="proc_private_workflow_boundary_invalid",
                message=(
                    f"procedure `{procedure.definition.name}` cannot lower as `private-workflow` in Stage 3 "
                    "because its body would not export step-backed outputs through the shared-validation seam"
                ),
                span=procedure.definition.span,
                form_path=procedure.definition.form_path,
            )
        if requested == ProcedureLoweringMode.PRIVATE_WORKFLOW:
            mode = ProcedureLoweringMode.PRIVATE_WORKFLOW
        elif (
            requested == ProcedureLoweringMode.AUTO
            and boundary_valid
            and body_valid
            and call_counts.get(procedure.definition.name, 0) > 1
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
        )
    return MappingProxyType(resolved)


def _procedure_private_call_site_analysis(
    typed_procedures: tuple[TypedProcedureDef, ...],
    *,
    typed_workflows: tuple[TypedWorkflowDef, ...],
    type_env: FrontendTypeEnvironment,
) -> tuple[Mapping[str, int], Mapping[str, bool]]:
    """Count procedure call sites and whether each can cross a workflow boundary."""

    typed_procedures_by_name = {
        procedure.definition.name: procedure for procedure in typed_procedures
    }
    distinct_call_sites: dict[str, set[tuple[SourceSpan, tuple[str, ...]]]] = {}
    lowerable: dict[str, bool] = {}

    def walk(expr: Any, *, local_values: Mapping[str, Any]) -> None:
        if isinstance(expr, ProcedureCallExpr):
            distinct_call_sites.setdefault(expr.callee_name, set()).add((expr.span, expr.form_path))
            call_site_lowerable = True
            for arg in expr.args:
                walk(arg, local_values=local_values)
                if _resolve_expr_local_value(arg, local_values=local_values) is None:
                    call_site_lowerable = False
            lowerable[expr.callee_name] = lowerable.get(expr.callee_name, True) and call_site_lowerable
            callee = typed_procedures_by_name.get(expr.callee_name)
            if callee is not None:
                child_locals = {}
                for arg_expr, (param_name, _) in zip(expr.args, callee.signature.params, strict=True):
                    child_locals[param_name] = _resolve_expr_local_value(arg_expr, local_values=local_values)
                walk(callee.typed_body.expr, local_values=child_locals)
            return
        if isinstance(expr, LetStarExpr):
            child_locals = dict(local_values)
            for binding_name, binding in expr.bindings:
                walk(binding, local_values=child_locals)
                resolved_binding = _resolve_expr_local_value(binding, local_values=child_locals)
                if resolved_binding is not None:
                    child_locals[binding_name] = resolved_binding
                elif isinstance(binding, ProviderResultExpr):
                    binding_type = type_env.resolve_type(
                        binding.returns_type_name,
                        span=binding.span,
                        form_path=binding.form_path,
                    )
                    if isinstance(binding_type, RecordTypeRef):
                        child_locals[binding_name] = _build_record_step_local_value(
                            binding_type,
                            step_name=binding_name,
                        )
            walk(expr.body, local_values=child_locals)
            return
        if isinstance(expr, MatchExpr):
            walk(expr.subject, local_values=local_values)
            for arm in expr.arms:
                walk(arm.body, local_values=local_values)
            return
        if isinstance(expr, RecordExpr):
            for _, value in expr.fields:
                walk(value, local_values=local_values)
            return
        if isinstance(expr, WithPhaseExpr):
            walk(expr.ctx_expr, local_values=local_values)
            walk(expr.body, local_values=local_values)
            return
        if isinstance(expr, ProviderResultExpr):
            walk(expr.provider, local_values=local_values)
            walk(expr.prompt, local_values=local_values)
            for value in expr.inputs:
                walk(value, local_values=local_values)
            return
        if isinstance(expr, CommandResultExpr):
            for value in expr.argv:
                walk(value, local_values=local_values)
            return
        if isinstance(expr, CallExpr):
            for _, value in expr.bindings:
                walk(value, local_values=local_values)

    for workflow in typed_workflows:
        walk(workflow.typed_body.expr, local_values=_signature_local_values(workflow))
    return MappingProxyType(
        {
            callee_name: len(call_sites)
            for callee_name, call_sites in distinct_call_sites.items()
        }
    ), MappingProxyType(lowerable)


def _procedure_private_boundary_valid(procedure: TypedProcedureDef) -> bool:
    """Return whether a procedure signature can become a private workflow."""

    if not isinstance(procedure.signature.return_type_ref, RecordTypeRef):
        return False
    if not analyze_workflow_boundary_type(procedure.signature.return_type_ref, source_path=("return",)).lowerable:
        return False
    return all(
        analyze_workflow_boundary_type(type_ref, source_path=(param_name,)).lowerable
        for param_name, type_ref in procedure.signature.params
    )


def _procedure_private_body_valid(
    procedure: TypedProcedureDef,
    *,
    typed_procedures_by_name: Mapping[str, TypedProcedureDef],
    type_env: FrontendTypeEnvironment,
) -> bool:
    """Return whether a procedure body exports only workflow-boundary values."""

    return _private_workflow_body_exports_step_backed_outputs(
        procedure.typed_body.expr,
        return_type_ref=procedure.signature.return_type_ref,
        local_values=_procedure_signature_local_values(procedure),
        typed_procedures_by_name=typed_procedures_by_name,
        type_env=type_env,
        active_procedures=frozenset({procedure.definition.name}),
    )


def _private_workflow_body_exports_step_backed_outputs(
    expr: Any,
    *,
    return_type_ref: TypeRef,
    local_values: Mapping[str, Any],
    typed_procedures_by_name: Mapping[str, TypedProcedureDef],
    type_env: FrontendTypeEnvironment,
    active_procedures: frozenset[str],
) -> bool:
    """Check that a private workflow body returns step-backed outputs."""

    if isinstance(expr, (CommandResultExpr, ProviderResultExpr, CallExpr)):
        return True
    if isinstance(expr, WithPhaseExpr):
        return _private_workflow_body_exports_step_backed_outputs(
            expr.body,
            return_type_ref=return_type_ref,
            local_values=local_values,
            typed_procedures_by_name=typed_procedures_by_name,
            type_env=type_env,
            active_procedures=active_procedures,
        )
    if isinstance(expr, ProcedureCallExpr):
        callee = typed_procedures_by_name.get(expr.callee_name)
        if callee is None or callee.definition.name in active_procedures:
            return False
        child_locals = dict(local_values)
        for arg_expr, (param_name, _) in zip(expr.args, callee.signature.params, strict=True):
            child_locals[param_name] = _resolve_inline_expr_value(arg_expr, local_values=local_values)
        return _private_workflow_body_exports_step_backed_outputs(
            callee.typed_body.expr,
            return_type_ref=callee.signature.return_type_ref,
            local_values=child_locals,
            typed_procedures_by_name=typed_procedures_by_name,
            type_env=type_env,
            active_procedures=active_procedures | {callee.definition.name},
        )
    if isinstance(expr, LetStarExpr):
        child_locals = dict(local_values)
        for binding_name, binding_expr in expr.bindings:
            if not isinstance(binding_expr, ProviderResultExpr):
                return False
            binding_type = type_env.resolve_type(
                binding_expr.returns_type_name,
                span=binding_expr.span,
                form_path=binding_expr.form_path,
            )
            if isinstance(binding_type, RecordTypeRef):
                child_locals[binding_name] = _build_record_step_local_value(
                    binding_type,
                    step_name=binding_name,
                )
        return _private_workflow_body_exports_step_backed_outputs(
            expr.body,
            return_type_ref=return_type_ref,
            local_values=child_locals,
            typed_procedures_by_name=typed_procedures_by_name,
            type_env=type_env,
            active_procedures=active_procedures,
        )
    if isinstance(expr, MatchExpr):
        return _match_outputs_are_step_backed(
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
    return False


def _match_outputs_are_step_backed(
    match_expr: MatchExpr,
    *,
    return_type_ref: TypeRef,
    local_values: Mapping[str, Any],
) -> bool:
    """Return whether every match arm projects step-backed record outputs."""

    return all(
        isinstance(arm.body, RecordExpr)
        and _record_outputs_are_step_backed(
            arm.body,
            return_type_ref=return_type_ref,
            local_values=local_values,
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
        if not isinstance(source_ref, str) or not source_ref.startswith(("root.steps.", "self.steps.")):
            return False
    return True


def _private_workflow_from_procedure(procedure: TypedProcedureDef) -> TypedWorkflowDef:
    """Synthesize a typed private workflow wrapper for a procedure body."""

    assert procedure.generated_workflow_name is not None
    assert isinstance(procedure.signature.return_type_ref, RecordTypeRef)
    definition = WorkflowDef(
        name=procedure.generated_workflow_name,
        params=tuple(
            WorkflowParam(
                name=param.name,
                type_name=param.type_name,
                span=param.span,
                form_path=param.form_path,
                expansion_stack=param.expansion_stack,
            )
            for param in procedure.definition.params
        ),
        return_type_name=procedure.definition.return_type_name,
        body=procedure.definition.body,
        span=procedure.definition.span,
        form_path=procedure.definition.form_path,
        expansion_stack=procedure.definition.expansion_stack,
    )
    signature = WorkflowSignature(
        name=procedure.generated_workflow_name,
        params=procedure.signature.params,
        return_type_ref=procedure.signature.return_type_ref,
        span=procedure.signature.span,
        form_path=procedure.signature.form_path,
    )
    return TypedWorkflowDef(
        definition=definition,
        signature=signature,
        typed_body=procedure.typed_body,
        effect_summary=procedure.transitive_effect_summary,
    )


def _procedure_provenance_notes(expr: ProcedureCallExpr, procedure: TypedProcedureDef) -> tuple[str, ...]:
    """Describe the source locations behind generated procedure code."""

    call = expr.span.start
    definition = procedure.definition.span.start
    return (
        f"procedure call site at {call.path}:{call.line}:{call.column}",
        f"procedure definition at {definition.path}:{definition.line}:{definition.column}",
    )


def _origin_for_workflow(
    typed_workflow: TypedWorkflowDef,
    *,
    typed_procedures: Mapping[str, TypedProcedureDef],
) -> LoweringOrigin:
    """Choose workflow-level provenance for authored and generated workflows."""

    notes: tuple[str, ...] = ()
    body_expr = typed_workflow.typed_body.expr
    if isinstance(body_expr, ProcedureCallExpr):
        procedure = typed_procedures.get(body_expr.callee_name)
        if procedure is not None and procedure.resolved_lowering_mode == ProcedureLoweringMode.INLINE:
            notes = _procedure_provenance_notes(body_expr, procedure)
    elif typed_workflow.definition.name.startswith("%") and ".v1" in typed_workflow.definition.name:
        procedure_name = typed_workflow.definition.name.removeprefix("%").split(".")[-2]
        procedure = typed_procedures.get(procedure_name)
        if procedure is not None:
            notes = (
                f"procedure definition at {procedure.definition.span.start.path}:{procedure.definition.span.start.line}:{procedure.definition.span.start.column}",
            )
    return LoweringOrigin(
        span=typed_workflow.definition.span,
        form_path=typed_workflow.definition.form_path,
        expansion_stack=typed_workflow.definition.expansion_stack,
        notes=notes,
    )

def _typed_workflow_dependencies(
    typed_workflow: TypedWorkflowDef,
    *,
    typed_procedures: Mapping[str, TypedProcedureDef],
) -> set[str]:
    """Find same-file workflow dependencies required before lowering."""

    dependencies: set[str] = set()
    visiting_procedures: set[str] = set()

    def walk(expr: Any) -> None:
        if isinstance(expr, CallExpr):
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
        if isinstance(expr, MatchExpr):
            walk(expr.subject)
            for arm in expr.arms:
                walk(arm.body)
            return
        if isinstance(expr, RecordExpr):
            for _, value in expr.fields:
                walk(value)
            return
        if isinstance(expr, WithPhaseExpr):
            walk(expr.ctx_expr)
            walk(expr.body)
            return
        if isinstance(expr, ProviderResultExpr):
            walk(expr.provider)
            walk(expr.prompt)
            for value in expr.inputs:
                walk(value)
            return
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
        validation_backend=loader,
        workflow_is_imported=workflow_is_imported,
    )
    if surface is None or loader.errors:
        _raise_remapped_validation_error(lowered_workflow, loader.errors)
    ir, projection = lower_surface_workflow(surface)
    return LoadedWorkflowBundle(
        surface=surface,
        ir=ir,
        projection=projection,
        imports=MappingProxyType(dict(imported_bundles)),
        provenance=surface.provenance,
    )


def _raise_remapped_validation_error(
    lowered_workflow: LoweredWorkflow,
    errors: list[Any],
) -> None:
    """Convert shared validation errors into frontend diagnostics when possible."""

    diagnostics: list[LispFrontendDiagnostic] = []
    for error in errors:
        message = str(error.message)
        origin = _remap_validation_message(lowered_workflow.origin_map, message)
        if origin is None:
            diagnostics.append(
                LispFrontendDiagnostic(
                    code="source_map_missing",
                    message=message,
                    span=lowered_workflow.origin_map.workflow_span,
                    form_path=lowered_workflow.typed_workflow.definition.form_path,
                    expansion_stack=lowered_workflow.origin_map.workflow_origin.expansion_stack,
                )
            )
            continue
        diagnostics.append(
            LispFrontendDiagnostic(
                code=_shared_validation_diagnostic_code(message),
                message=message,
                span=origin.span,
                form_path=origin.form_path or lowered_workflow.typed_workflow.definition.form_path,
                expansion_stack=origin.expansion_stack,
                notes=origin.notes,
            )
        )
    raise LispFrontendCompileError(tuple(diagnostics))


def _remap_validation_message(origin_map: LoweringOriginMap, message: str) -> LoweringOrigin | None:
    """Best-effort map a shared validation message back to frontend origin."""

    for key, origin in origin_map.step_spans.items():
        if key in message:
            return origin
    for key, origin in origin_map.generated_input_spans.items():
        if key in message:
            return origin
    for key, origin in origin_map.generated_output_spans.items():
        if key in message:
            return origin
    for key, origin in origin_map.generated_path_spans.items():
        if key in message:
            return origin
    if "output" in message or "input" in message or "workflow" in message:
        return origin_map.workflow_origin
    return None


def _shared_validation_diagnostic_code(message: str) -> str:
    """Classify a shared validation message as a frontend diagnostic code."""

    if "parent directory traversal" in message or "absolute paths not allowed" in message:
        return "path_definition_invalid"
    return "workflow_boundary_type_invalid"


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


def _definition_only_module(workflow_path: Path):
    """Load only type/procedure definitions from a workflow source file."""

    return elaborate_definition_module(
        _definition_only_syntax_module(build_syntax_module(read_sexpr_file(workflow_path)))
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
