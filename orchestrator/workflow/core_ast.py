"""Shared Core Workflow AST built from validated authored workflow surfaces."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

from orchestrator.exceptions import ValidationError, ValidationSubjectRef, WorkflowValidationError

from .surface_ast import (
    ImportedWorkflowMetadata,
    PrivateExecContextBinding,
    SurfaceBranchBlock,
    SurfaceContract,
    SurfaceFinallyBlock,
    SurfaceMatchCaseBlock,
    SurfaceRepeatUntilBlock,
    SurfaceStep,
    SurfaceStepKind,
    SurfaceWorkflow,
    WorkflowProvenance,
    empty_frozen_mapping,
)
from .state_layout import GeneratedPathAllocation


CORE_WORKFLOW_AST_SCHEMA_VERSION = "core_workflow_ast.v1"


@dataclass(frozen=True)
class CoreWorkflowImport:
    alias: str
    workflow_path: Path
    source_root: Path
    generated_path_allocations: tuple[GeneratedPathAllocation, ...] = ()
    managed_write_root_inputs: tuple[str, ...] = ()
    runtime_context_inputs: tuple[str, ...] = ()
    private_exec_context_bindings: tuple[PrivateExecContextBinding, ...] = ()
    compatibility_bridge_inputs: tuple[str, ...] = ()
    workflow_name: str | None = None
    output_names: tuple[str, ...] = ()


@dataclass(frozen=True)
class CoreWorkflowContract:
    name: str
    kind: str | None
    value_type: str | None
    definition: Mapping[str, Any]
    from_ref: Any = None


@dataclass(frozen=True)
class CoreStmtMeta:
    id: str
    step_id: str
    step_kind: str
    display_name: str | None = None
    lexical_scope: tuple[str, ...] = ()
    origin_key: str | None = None
    generated_by: str | None = None


@dataclass(frozen=True)
class CoreBranchBlock:
    branch_name: str
    token: str
    step_id: str
    statements: tuple[Any, ...]
    outputs: Mapping[str, CoreWorkflowContract] = field(default_factory=empty_frozen_mapping)


@dataclass(frozen=True)
class CoreMatchCaseBlock:
    case_name: str
    token: str
    step_id: str
    statements: tuple[Any, ...]
    outputs: Mapping[str, CoreWorkflowContract] = field(default_factory=empty_frozen_mapping)


@dataclass(frozen=True)
class CoreCommandStep:
    meta: CoreStmtMeta
    common: Any
    command: Any
    boundary_kind: str | None = None
    boundary_name: str | None = None
    _surface_step: SurfaceStep | None = field(default=None, repr=False, compare=False)


@dataclass(frozen=True)
class CoreProviderStep:
    meta: CoreStmtMeta
    common: Any
    provider: str | None
    provider_params: Any = None
    managed_jobs: Any = None
    input_file: Any = None
    asset_file: Any = None
    depends_on: Mapping[str, Any] = field(default_factory=empty_frozen_mapping)
    asset_depends_on: tuple[Any, ...] = ()
    inject_output_contract: bool | None = None
    inject_consumes: bool | None = None
    prompt_consumes: tuple[Any, ...] | None = None
    typed_prompt_inputs: tuple[Any, ...] = ()
    consumes_injection_position: str | None = None
    _surface_step: SurfaceStep | None = field(default=None, repr=False, compare=False)


@dataclass(frozen=True)
class CoreAdjudicatedProviderStep:
    meta: CoreStmtMeta
    common: Any
    adjudicated_provider: Mapping[str, Any] = field(default_factory=empty_frozen_mapping)
    _surface_step: SurfaceStep | None = field(default=None, repr=False, compare=False)


@dataclass(frozen=True)
class CoreWaitForStep:
    meta: CoreStmtMeta
    common: Any
    wait_for: Mapping[str, Any] = field(default_factory=empty_frozen_mapping)
    _surface_step: SurfaceStep | None = field(default=None, repr=False, compare=False)


@dataclass(frozen=True)
class CoreAssertStep:
    meta: CoreStmtMeta
    common: Any
    assert_predicate: Any = None
    _surface_step: SurfaceStep | None = field(default=None, repr=False, compare=False)


@dataclass(frozen=True)
class CoreSetScalarStep:
    meta: CoreStmtMeta
    common: Any
    set_scalar: Mapping[str, Any] = field(default_factory=empty_frozen_mapping)
    _surface_step: SurfaceStep | None = field(default=None, repr=False, compare=False)


@dataclass(frozen=True)
class CoreResourceTransitionStep:
    meta: CoreStmtMeta
    common: Any
    resource_transition: Mapping[str, Any] = field(default_factory=empty_frozen_mapping)
    _surface_step: SurfaceStep | None = field(default=None, repr=False, compare=False)


@dataclass(frozen=True)
class CorePureProjectionStep:
    meta: CoreStmtMeta
    common: Any
    pure_projection: Mapping[str, Any] = field(default_factory=empty_frozen_mapping)
    _surface_step: SurfaceStep | None = field(default=None, repr=False, compare=False)


@dataclass(frozen=True)
class CoreMaterializeViewStep:
    meta: CoreStmtMeta
    common: Any
    materialize_view: Mapping[str, Any] = field(default_factory=empty_frozen_mapping)
    _surface_step: SurfaceStep | None = field(default=None, repr=False, compare=False)


@dataclass(frozen=True)
class CoreIncrementScalarStep:
    meta: CoreStmtMeta
    common: Any
    increment_scalar: Mapping[str, Any] = field(default_factory=empty_frozen_mapping)
    _surface_step: SurfaceStep | None = field(default=None, repr=False, compare=False)


@dataclass(frozen=True)
class CoreMaterializeArtifactsStep:
    meta: CoreStmtMeta
    common: Any
    materialize_artifacts: Mapping[str, Any] = field(default_factory=empty_frozen_mapping)
    _surface_step: SurfaceStep | None = field(default=None, repr=False, compare=False)


@dataclass(frozen=True)
class CoreSelectVariantOutputStep:
    meta: CoreStmtMeta
    common: Any
    select_variant_output: Mapping[str, Any] = field(default_factory=empty_frozen_mapping)
    _surface_step: SurfaceStep | None = field(default=None, repr=False, compare=False)


@dataclass(frozen=True)
class CoreCallStep:
    meta: CoreStmtMeta
    common: Any
    call_alias: str | None = None
    call_bindings: Mapping[str, Any] = field(default_factory=empty_frozen_mapping)
    _surface_step: SurfaceStep | None = field(default=None, repr=False, compare=False)


@dataclass(frozen=True)
class CoreIf:
    meta: CoreStmtMeta
    common: Any
    condition: Any
    then_branch: CoreBranchBlock
    else_branch: CoreBranchBlock | None = None
    _surface_step: SurfaceStep | None = field(default=None, repr=False, compare=False)


@dataclass(frozen=True)
class CoreMatch:
    meta: CoreStmtMeta
    common: Any
    match_ref: Any
    cases: Mapping[str, CoreMatchCaseBlock] = field(default_factory=empty_frozen_mapping)
    _surface_step: SurfaceStep | None = field(default=None, repr=False, compare=False)


@dataclass(frozen=True)
class CoreForEach:
    meta: CoreStmtMeta
    common: Any
    items: tuple[Any, ...] = ()
    items_from: str | None = None
    item_name: str = "item"
    statements: tuple[Any, ...] = ()
    _surface_step: SurfaceStep | None = field(default=None, repr=False, compare=False)


@dataclass(frozen=True)
class CoreRepeatUntil:
    meta: CoreStmtMeta
    common: Any
    condition: Any
    max_iterations: int | None
    step_id: str
    token: str
    statements: tuple[Any, ...]
    outputs: Mapping[str, CoreWorkflowContract] = field(default_factory=empty_frozen_mapping)
    on_exhausted_outputs: Mapping[str, Any] = field(default_factory=empty_frozen_mapping)
    _surface_step: SurfaceStep | None = field(default=None, repr=False, compare=False)


@dataclass(frozen=True)
class CoreFinally:
    token: str
    step_id: str
    statements: tuple[Any, ...]


@dataclass(frozen=True)
class CoreWorkflowAST:
    schema_version: str
    workflow_name: str
    dsl_version: str
    inputs: Mapping[str, CoreWorkflowContract]
    outputs: Mapping[str, CoreWorkflowContract]
    artifacts: Mapping[str, CoreWorkflowContract]
    providers: Mapping[str, Any]
    imports: Mapping[str, CoreWorkflowImport]
    body: tuple[Any, ...]
    finalization: CoreFinally | None = None
    provenance: WorkflowProvenance | None = None
    _surface_workflow: SurfaceWorkflow | None = field(default=None, repr=False, compare=False)


def build_core_workflow_ast(
    surface: SurfaceWorkflow,
    imports: Mapping[str, Any],
    provenance: WorkflowProvenance,
) -> CoreWorkflowAST:
    workflow_name = surface.name or ""
    command_boundary_metadata = _load_command_boundary_metadata(provenance, workflow_name=workflow_name)
    core_workflow_ast = CoreWorkflowAST(
        schema_version=CORE_WORKFLOW_AST_SCHEMA_VERSION,
        workflow_name=workflow_name,
        dsl_version=surface.version,
        inputs=MappingProxyType({name: _contract_from_surface(contract) for name, contract in surface.inputs.items()}),
        outputs=MappingProxyType({name: _contract_from_surface(contract) for name, contract in surface.outputs.items()}),
        artifacts=MappingProxyType({name: _contract_from_surface(contract) for name, contract in surface.artifacts.items()}),
        providers=MappingProxyType(dict(surface.providers)),
        imports=MappingProxyType(
            {
                alias: _import_from_surface(alias, metadata, imports.get(alias))
                for alias, metadata in surface.imports.items()
            }
        ),
        body=_build_statements(
            surface.steps,
            workflow_name=workflow_name,
            scope=(),
            generated_by=None,
            command_boundary_metadata=command_boundary_metadata,
        ),
        finalization=_build_finalization(
            surface,
            workflow_name=workflow_name,
            command_boundary_metadata=command_boundary_metadata,
        ),
        provenance=provenance,
        _surface_workflow=surface,
    )
    validate_core_workflow_ast(core_workflow_ast, imports=imports)
    return core_workflow_ast


def validate_core_workflow_ast(
    core_workflow_ast: CoreWorkflowAST,
    *,
    imports: Mapping[str, Any],
) -> None:
    errors: list[ValidationError] = []
    if core_workflow_ast.schema_version != CORE_WORKFLOW_AST_SCHEMA_VERSION:
        errors.append(
            ValidationError(
                message=(
                    "core_workflow_ast_invalid: unsupported core workflow AST schema "
                    f"`{core_workflow_ast.schema_version}`"
                )
            )
        )
    seen_ids: set[str] = set()
    for statement in _iter_statements(core_workflow_ast):
        meta = getattr(statement, "meta", None)
        if meta is None:
            continue
        if meta.id in seen_ids:
            errors.append(
                ValidationError(
                    message=f"core_workflow_ast_invalid: duplicate statement id `{meta.id}`",
                    subject_refs=_subject_refs_for_meta(core_workflow_ast.workflow_name, meta),
                )
            )
        seen_ids.add(meta.id)
        if not isinstance(meta.origin_key, str) or not meta.origin_key:
            errors.append(
                ValidationError(
                    message=(
                        "core_workflow_ast_invalid: statement "
                        f"`{meta.id}` is missing a source-map origin key"
                    ),
                    subject_refs=_subject_refs_for_meta(core_workflow_ast.workflow_name, meta),
                )
            )
        if isinstance(statement, CoreCallStep):
            alias = statement.call_alias
            if isinstance(alias, str) and alias and alias not in core_workflow_ast.imports and alias not in imports:
                errors.append(
                    ValidationError(
                        message=(
                            "core_workflow_ast_invalid: call statement "
                            f"`{meta.id}` references unknown import alias `{alias}`"
                        ),
                        subject_refs=_subject_refs_for_meta(core_workflow_ast.workflow_name, meta),
                    )
                )
    if errors:
        raise WorkflowValidationError(errors)


def lower_core_workflow_ast(core_workflow_ast: CoreWorkflowAST):
    from .lowering import _lower_surface_workflow_impl

    return _lower_surface_workflow_impl(_surface_workflow_from_core_ast(core_workflow_ast))


def workflow_core_ast_to_json(core_workflow_ast: CoreWorkflowAST) -> dict[str, Any]:
    return {
        "schema_version": core_workflow_ast.schema_version,
        "workflow_name": core_workflow_ast.workflow_name,
        "dsl_version": core_workflow_ast.dsl_version,
        "inputs": {name: _contract_to_json(contract) for name, contract in sorted(core_workflow_ast.inputs.items())},
        "outputs": {name: _contract_to_json(contract) for name, contract in sorted(core_workflow_ast.outputs.items())},
        "artifacts": {name: _contract_to_json(contract) for name, contract in sorted(core_workflow_ast.artifacts.items())},
        "providers": {str(name): _json_data(payload) for name, payload in sorted(core_workflow_ast.providers.items())},
        "imports": {alias: _import_to_json(metadata) for alias, metadata in sorted(core_workflow_ast.imports.items())},
        "body": [_statement_to_json(statement) for statement in core_workflow_ast.body],
        "finalization": _finally_to_json(core_workflow_ast.finalization),
    }


def _subject_refs_for_meta(workflow_name: str, meta: CoreStmtMeta) -> tuple[ValidationSubjectRef, ...]:
    return (
        ValidationSubjectRef(
            subject_kind="step_id",
            subject_name=meta.step_id,
            workflow_name=workflow_name or None,
        ),
    )


def _contract_from_surface(contract: SurfaceContract) -> CoreWorkflowContract:
    return CoreWorkflowContract(
        name=contract.name,
        kind=contract.kind,
        value_type=contract.value_type,
        definition=contract.definition,
        from_ref=contract.from_ref,
    )


def _import_from_surface(
    alias: str,
    metadata: ImportedWorkflowMetadata,
    imported_bundle: Any,
) -> CoreWorkflowImport:
    workflow_name = metadata.workflow_name
    output_names = metadata.output_names
    if workflow_name is None and imported_bundle is not None:
        workflow_name = imported_bundle.surface.name
    if not output_names and imported_bundle is not None:
        output_names = tuple(imported_bundle.surface.outputs)
    return CoreWorkflowImport(
        alias=alias,
        workflow_path=metadata.workflow_path,
        source_root=metadata.source_root,
        generated_path_allocations=metadata.generated_path_allocations,
        managed_write_root_inputs=metadata.managed_write_root_inputs,
        runtime_context_inputs=metadata.runtime_context_inputs,
        private_exec_context_bindings=metadata.private_exec_context_bindings,
        compatibility_bridge_inputs=metadata.compatibility_bridge_inputs,
        workflow_name=workflow_name,
        output_names=output_names,
    )


def _build_finalization(
    surface: SurfaceWorkflow,
    *,
    workflow_name: str,
    command_boundary_metadata: Mapping[str, tuple[str, str]],
) -> CoreFinally | None:
    if surface.finalization is None:
        return None
    return CoreFinally(
        token=surface.finalization.token,
        step_id=surface.finalization.step_id,
        statements=_build_statements(
            surface.finalization.steps,
            workflow_name=workflow_name,
            scope=("finally", surface.finalization.step_id),
            generated_by=surface.finalization.step_id,
            command_boundary_metadata=command_boundary_metadata,
        ),
    )


def _build_statements(
    steps: tuple[SurfaceStep, ...],
    *,
    workflow_name: str,
    scope: tuple[str, ...],
    generated_by: str | None,
    command_boundary_metadata: Mapping[str, tuple[str, str]],
) -> tuple[Any, ...]:
    return tuple(
        _build_statement(
            step,
            workflow_name=workflow_name,
            scope=scope,
            generated_by=generated_by,
            command_boundary_metadata=command_boundary_metadata,
        )
        for step in steps
    )


def _build_statement(
    step: SurfaceStep,
    *,
    workflow_name: str,
    scope: tuple[str, ...],
    generated_by: str | None,
    command_boundary_metadata: Mapping[str, tuple[str, str]],
) -> Any:
    meta = CoreStmtMeta(
        id=".".join(scope + (step.step_id,)),
        step_id=step.authored_id or step.step_id,
        step_kind=step.kind.value,
        display_name=step.name,
        lexical_scope=scope,
        origin_key=_origin_key(workflow_name, scope, step.step_id),
        generated_by=generated_by,
    )
    if step.kind is SurfaceStepKind.COMMAND:
        boundary_kind, boundary_name = command_boundary_metadata.get(step.step_id, ("external_tool", step.name))
        return CoreCommandStep(
            meta=meta,
            common=step.common,
            command=step.command,
            boundary_kind=boundary_kind,
            boundary_name=boundary_name,
            _surface_step=step,
        )
    if step.kind is SurfaceStepKind.PROVIDER:
        return CoreProviderStep(
            meta=meta,
            common=step.common,
            provider=step.provider,
            provider_params=step.provider_params,
            managed_jobs=step.managed_jobs,
            input_file=step.input_file,
            asset_file=step.asset_file,
            depends_on=step.depends_on,
            asset_depends_on=step.asset_depends_on,
            inject_output_contract=step.inject_output_contract,
            inject_consumes=step.inject_consumes,
            prompt_consumes=step.prompt_consumes,
            typed_prompt_inputs=step.typed_prompt_inputs,
            consumes_injection_position=step.consumes_injection_position,
            _surface_step=step,
        )
    if step.kind is SurfaceStepKind.ADJUDICATED_PROVIDER:
        return CoreAdjudicatedProviderStep(
            meta=meta,
            common=step.common,
            adjudicated_provider=step.adjudicated_provider,
            _surface_step=step,
        )
    if step.kind is SurfaceStepKind.WAIT_FOR:
        return CoreWaitForStep(
            meta=meta,
            common=step.common,
            wait_for=step.wait_for,
            _surface_step=step,
        )
    if step.kind is SurfaceStepKind.ASSERT:
        return CoreAssertStep(
            meta=meta,
            common=step.common,
            assert_predicate=step.assert_predicate,
            _surface_step=step,
        )
    if step.kind is SurfaceStepKind.SET_SCALAR:
        return CoreSetScalarStep(
            meta=meta,
            common=step.common,
            set_scalar=step.set_scalar,
            _surface_step=step,
        )
    if step.kind is SurfaceStepKind.RESOURCE_TRANSITION:
        return CoreResourceTransitionStep(
            meta=meta,
            common=step.common,
            resource_transition=step.resource_transition,
            _surface_step=step,
        )
    if step.kind is SurfaceStepKind.PURE_PROJECTION:
        return CorePureProjectionStep(
            meta=meta,
            common=step.common,
            pure_projection=step.pure_projection,
            _surface_step=step,
        )
    if step.kind is SurfaceStepKind.MATERIALIZE_VIEW:
        return CoreMaterializeViewStep(
            meta=meta,
            common=step.common,
            materialize_view=step.materialize_view,
            _surface_step=step,
        )
    if step.kind is SurfaceStepKind.INCREMENT_SCALAR:
        return CoreIncrementScalarStep(
            meta=meta,
            common=step.common,
            increment_scalar=step.increment_scalar,
            _surface_step=step,
        )
    if step.kind is SurfaceStepKind.MATERIALIZE_ARTIFACTS:
        return CoreMaterializeArtifactsStep(
            meta=meta,
            common=step.common,
            materialize_artifacts=step.materialize_artifacts,
            _surface_step=step,
        )
    if step.kind is SurfaceStepKind.SELECT_VARIANT_OUTPUT:
        return CoreSelectVariantOutputStep(
            meta=meta,
            common=step.common,
            select_variant_output=step.select_variant_output,
            _surface_step=step,
        )
    if step.kind is SurfaceStepKind.CALL:
        return CoreCallStep(
            meta=meta,
            common=step.common,
            call_alias=step.call_alias,
            call_bindings=step.call_bindings,
            _surface_step=step,
        )
    if step.kind is SurfaceStepKind.IF:
        return CoreIf(
            meta=meta,
            common=step.common,
            condition=step.if_condition,
            then_branch=_build_branch_block(
                step.then_branch,
                workflow_name=workflow_name,
                parent_meta=meta,
                command_boundary_metadata=command_boundary_metadata,
            ),
            else_branch=(
                _build_branch_block(
                    step.else_branch,
                    workflow_name=workflow_name,
                    parent_meta=meta,
                    command_boundary_metadata=command_boundary_metadata,
                )
                if step.else_branch is not None
                else None
            ),
            _surface_step=step,
        )
    if step.kind is SurfaceStepKind.MATCH:
        return CoreMatch(
            meta=meta,
            common=step.common,
            match_ref=step.match_ref,
            cases=MappingProxyType(
                {
                    case_name: _build_match_case_block(
                        case_block,
                        workflow_name=workflow_name,
                        parent_meta=meta,
                        command_boundary_metadata=command_boundary_metadata,
                    )
                    for case_name, case_block in step.match_cases.items()
                }
            ),
            _surface_step=step,
        )
    if step.kind is SurfaceStepKind.FOR_EACH:
        return CoreForEach(
            meta=meta,
            common=step.common,
            items=step.for_each_items,
            items_from=step.for_each_items_from,
            item_name=step.for_each_item_name,
            statements=_build_statements(
                step.for_each_steps,
                workflow_name=workflow_name,
                scope=scope + (step.step_id,),
                generated_by=meta.id,
                command_boundary_metadata=command_boundary_metadata,
            ),
            _surface_step=step,
        )
    if step.kind is SurfaceStepKind.REPEAT_UNTIL:
        repeat_until = step.repeat_until
        if repeat_until is None:
            raise ValueError(f"repeat_until step `{step.step_id}` is missing its typed body")
        return CoreRepeatUntil(
            meta=meta,
            common=step.common,
            condition=repeat_until.condition,
            max_iterations=repeat_until.max_iterations,
            step_id=repeat_until.step_id,
            token=repeat_until.token,
            statements=_build_statements(
                repeat_until.steps,
                workflow_name=workflow_name,
                scope=scope + (step.step_id, repeat_until.step_id),
                generated_by=meta.id,
                command_boundary_metadata=command_boundary_metadata,
            ),
            outputs=MappingProxyType(
                {name: _contract_from_surface(contract) for name, contract in repeat_until.outputs.items()}
            ),
            on_exhausted_outputs=repeat_until.on_exhausted_outputs,
            _surface_step=step,
        )
    raise ValueError(f"Unsupported core statement kind `{step.kind.value}`")


def _build_branch_block(
    branch: SurfaceBranchBlock,
    *,
    workflow_name: str,
    parent_meta: CoreStmtMeta,
    command_boundary_metadata: Mapping[str, tuple[str, str]],
) -> CoreBranchBlock:
    return CoreBranchBlock(
        branch_name=branch.branch_name,
        token=branch.token,
        step_id=branch.step_id,
        statements=_build_statements(
            branch.steps,
            workflow_name=workflow_name,
            scope=parent_meta.lexical_scope + (parent_meta.step_id, branch.step_id),
            generated_by=parent_meta.id,
            command_boundary_metadata=command_boundary_metadata,
        ),
        outputs=MappingProxyType({name: _contract_from_surface(contract) for name, contract in branch.outputs.items()}),
    )


def _build_match_case_block(
    case_block: SurfaceMatchCaseBlock,
    *,
    workflow_name: str,
    parent_meta: CoreStmtMeta,
    command_boundary_metadata: Mapping[str, tuple[str, str]],
) -> CoreMatchCaseBlock:
    return CoreMatchCaseBlock(
        case_name=case_block.case_name,
        token=case_block.token,
        step_id=case_block.step_id,
        statements=_build_statements(
            case_block.steps,
            workflow_name=workflow_name,
            scope=parent_meta.lexical_scope + (parent_meta.step_id, case_block.step_id),
            generated_by=parent_meta.id,
            command_boundary_metadata=command_boundary_metadata,
        ),
        outputs=MappingProxyType(
            {name: _contract_from_surface(contract) for name, contract in case_block.outputs.items()}
        ),
    )


def _load_command_boundary_metadata(
    provenance: WorkflowProvenance,
    *,
    workflow_name: str,
) -> Mapping[str, tuple[str, str]]:
    source_trace_path = provenance.frontend_source_trace_path
    if not workflow_name or not isinstance(source_trace_path, Path) or not source_trace_path.exists():
        return MappingProxyType({})
    try:
        payload = json.loads(source_trace_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return MappingProxyType({})
    workflows = payload.get("workflows")
    if not isinstance(workflows, Mapping):
        return MappingProxyType({})
    workflow_payload = workflows.get(workflow_name)
    if not isinstance(workflow_payload, Mapping):
        return MappingProxyType({})
    command_boundaries = workflow_payload.get("command_boundaries")
    if not isinstance(command_boundaries, list):
        return MappingProxyType({})
    metadata: dict[str, tuple[str, str]] = {}
    for boundary in command_boundaries:
        if not isinstance(boundary, Mapping):
            continue
        step_id = boundary.get("step_id")
        boundary_kind = boundary.get("boundary_kind")
        boundary_name = boundary.get("adapter_name") or boundary.get("command_name")
        if (
            isinstance(step_id, str)
            and step_id
            and isinstance(boundary_kind, str)
            and boundary_kind
            and isinstance(boundary_name, str)
            and boundary_name
        ):
            metadata[step_id] = (boundary_kind, boundary_name)
            if not step_id.startswith("root."):
                metadata[f"root.{step_id}"] = (boundary_kind, boundary_name)
    return MappingProxyType(metadata)


def _surface_workflow_from_core_ast(core_workflow_ast: CoreWorkflowAST) -> SurfaceWorkflow:
    provenance = core_workflow_ast.provenance
    if provenance is None:
        raise ValueError("CoreWorkflowAST must retain workflow provenance for lowering")
    return SurfaceWorkflow(
        version=core_workflow_ast.dsl_version,
        name=core_workflow_ast.workflow_name or None,
        steps=tuple(_surface_step_from_core_statement(statement) for statement in core_workflow_ast.body),
        provenance=provenance,
        providers=MappingProxyType(dict(core_workflow_ast.providers)),
        artifacts=MappingProxyType(
            {name: _surface_contract_from_core(contract) for name, contract in core_workflow_ast.artifacts.items()}
        ),
        inputs=MappingProxyType(
            {name: _surface_contract_from_core(contract) for name, contract in core_workflow_ast.inputs.items()}
        ),
        outputs=MappingProxyType(
            {name: _surface_contract_from_core(contract) for name, contract in core_workflow_ast.outputs.items()}
        ),
        imports=MappingProxyType(
            {
                alias: ImportedWorkflowMetadata(
                    alias=metadata.alias,
                    workflow_path=metadata.workflow_path,
                    source_root=metadata.source_root,
                    generated_path_allocations=metadata.generated_path_allocations,
                    managed_write_root_inputs=metadata.managed_write_root_inputs,
                    runtime_context_inputs=metadata.runtime_context_inputs,
                    private_exec_context_bindings=metadata.private_exec_context_bindings,
                    compatibility_bridge_inputs=metadata.compatibility_bridge_inputs,
                    workflow_name=metadata.workflow_name,
                    output_names=metadata.output_names,
                )
                for alias, metadata in core_workflow_ast.imports.items()
            }
        ),
        finalization=(
            _surface_finally_from_core(core_workflow_ast.finalization)
            if core_workflow_ast.finalization is not None
            else None
        ),
    )


def _surface_contract_from_core(contract: CoreWorkflowContract) -> SurfaceContract:
    return SurfaceContract(
        name=contract.name,
        kind=contract.kind,
        value_type=contract.value_type,
        definition=contract.definition,
        from_ref=contract.from_ref,
    )


def _surface_finally_from_core(finalization: CoreFinally) -> SurfaceFinallyBlock:
    return SurfaceFinallyBlock(
        token=finalization.token,
        step_id=finalization.step_id,
        steps=tuple(_surface_step_from_core_statement(statement) for statement in finalization.statements),
    )


def _surface_branch_from_core(branch: CoreBranchBlock) -> SurfaceBranchBlock:
    return SurfaceBranchBlock(
        branch_name=branch.branch_name,
        token=branch.token,
        step_id=branch.step_id,
        steps=tuple(_surface_step_from_core_statement(statement) for statement in branch.statements),
        outputs=MappingProxyType(
            {name: _surface_contract_from_core(contract) for name, contract in branch.outputs.items()}
        ),
    )


def _surface_match_case_from_core(case: CoreMatchCaseBlock) -> SurfaceMatchCaseBlock:
    return SurfaceMatchCaseBlock(
        case_name=case.case_name,
        token=case.token,
        step_id=case.step_id,
        steps=tuple(_surface_step_from_core_statement(statement) for statement in case.statements),
        outputs=MappingProxyType(
            {name: _surface_contract_from_core(contract) for name, contract in case.outputs.items()}
        ),
    )


def _surface_repeat_until_from_core(statement: CoreRepeatUntil) -> SurfaceRepeatUntilBlock:
    return SurfaceRepeatUntilBlock(
        token=statement.token,
        step_id=statement.step_id,
        steps=tuple(_surface_step_from_core_statement(item) for item in statement.statements),
        outputs=MappingProxyType(
            {name: _surface_contract_from_core(contract) for name, contract in statement.outputs.items()}
        ),
        condition=statement.condition,
        max_iterations=statement.max_iterations,
        on_exhausted_outputs=statement.on_exhausted_outputs,
    )


def _surface_step_from_core_statement(statement: Any) -> SurfaceStep:
    meta = getattr(statement, "meta", None)
    if meta is None:
        raise TypeError(f"Unsupported core statement type `{type(statement).__name__}`")
    step_id = _normalized_surface_step_id(meta.id)
    authored_id = meta.step_id if meta.step_id != step_id else None
    kwargs: dict[str, Any] = {
        "name": meta.display_name or meta.step_id,
        "step_id": step_id,
        "kind": SurfaceStepKind(meta.step_kind),
        "authored_id": authored_id,
        "common": statement.common,
    }
    source_step = getattr(statement, "_surface_step", None)
    if source_step is not None:
        kwargs["when_predicate"] = source_step.when_predicate
        kwargs["assert_predicate"] = source_step.assert_predicate
    if isinstance(statement, CoreCommandStep):
        kwargs["command"] = statement.command
    elif isinstance(statement, CoreProviderStep):
        kwargs.update(
            provider=statement.provider,
            provider_params=statement.provider_params,
            managed_jobs=statement.managed_jobs,
            input_file=statement.input_file,
            asset_file=statement.asset_file,
            depends_on=statement.depends_on,
            asset_depends_on=statement.asset_depends_on,
            inject_output_contract=statement.inject_output_contract,
            inject_consumes=statement.inject_consumes,
            prompt_consumes=statement.prompt_consumes,
            typed_prompt_inputs=statement.typed_prompt_inputs,
            consumes_injection_position=statement.consumes_injection_position,
        )
    elif isinstance(statement, CoreAdjudicatedProviderStep):
        kwargs["adjudicated_provider"] = statement.adjudicated_provider
    elif isinstance(statement, CoreWaitForStep):
        kwargs["wait_for"] = statement.wait_for
    elif isinstance(statement, CoreAssertStep):
        kwargs["assert_predicate"] = statement.assert_predicate
    elif isinstance(statement, CoreSetScalarStep):
        kwargs["set_scalar"] = statement.set_scalar
    elif isinstance(statement, CoreResourceTransitionStep):
        kwargs["resource_transition"] = statement.resource_transition
    elif isinstance(statement, CorePureProjectionStep):
        kwargs["pure_projection"] = statement.pure_projection
    elif isinstance(statement, CoreMaterializeViewStep):
        kwargs["materialize_view"] = statement.materialize_view
    elif isinstance(statement, CoreIncrementScalarStep):
        kwargs["increment_scalar"] = statement.increment_scalar
    elif isinstance(statement, CoreMaterializeArtifactsStep):
        kwargs["materialize_artifacts"] = statement.materialize_artifacts
    elif isinstance(statement, CoreSelectVariantOutputStep):
        kwargs["select_variant_output"] = statement.select_variant_output
    elif isinstance(statement, CoreCallStep):
        kwargs["call_alias"] = statement.call_alias
        kwargs["call_bindings"] = statement.call_bindings
    elif isinstance(statement, CoreIf):
        kwargs["if_condition"] = statement.condition
        kwargs["then_branch"] = _surface_branch_from_core(statement.then_branch)
        kwargs["else_branch"] = (
            _surface_branch_from_core(statement.else_branch)
            if statement.else_branch is not None
            else None
        )
    elif isinstance(statement, CoreMatch):
        kwargs["match_ref"] = statement.match_ref
        kwargs["match_cases"] = MappingProxyType(
            {
                case_name: _surface_match_case_from_core(case)
                for case_name, case in statement.cases.items()
            }
        )
    elif isinstance(statement, CoreForEach):
        kwargs["for_each_items"] = statement.items
        kwargs["for_each_items_from"] = statement.items_from
        kwargs["for_each_item_name"] = statement.item_name
        kwargs["for_each_steps"] = tuple(
            _surface_step_from_core_statement(item)
            for item in statement.statements
        )
    elif isinstance(statement, CoreRepeatUntil):
        kwargs["repeat_until"] = _surface_repeat_until_from_core(statement)
    else:
        raise TypeError(f"Unsupported core statement type `{type(statement).__name__}`")
    return SurfaceStep(**kwargs)


def _normalized_surface_step_id(step_id: str) -> str:
    for prefix in ("root.", "finally."):
        index = step_id.rfind(prefix)
        if index >= 0:
            return step_id[index:]
    return step_id


def _iter_statements(core_workflow_ast: CoreWorkflowAST):
    yield from _iter_nested_statements(core_workflow_ast.body)
    if core_workflow_ast.finalization is not None:
        yield from _iter_nested_statements(core_workflow_ast.finalization.statements)


def _iter_nested_statements(statements: tuple[Any, ...]):
    for statement in statements:
        yield statement
        if isinstance(statement, CoreIf):
            yield from _iter_nested_statements(statement.then_branch.statements)
            if statement.else_branch is not None:
                yield from _iter_nested_statements(statement.else_branch.statements)
        elif isinstance(statement, CoreMatch):
            for case in statement.cases.values():
                yield from _iter_nested_statements(case.statements)
        elif isinstance(statement, CoreForEach):
            yield from _iter_nested_statements(statement.statements)
        elif isinstance(statement, CoreRepeatUntil):
            yield from _iter_nested_statements(statement.statements)


def _origin_key(workflow_name: str, scope: tuple[str, ...], step_id: str) -> str:
    return f"{workflow_name or '<workflow>'}::{'.'.join(scope + (step_id,))}"


def _contract_to_json(contract: CoreWorkflowContract) -> dict[str, Any]:
    return {
        "name": contract.name,
        "kind": contract.kind,
        "value_type": contract.value_type,
        "definition": _json_data(contract.definition),
        "from_ref": _json_data(contract.from_ref),
    }


def _import_to_json(metadata: CoreWorkflowImport) -> dict[str, Any]:
    return {
        "alias": metadata.alias,
        "workflow_path": str(metadata.workflow_path),
        "source_root": str(metadata.source_root),
        "generated_path_allocations": [
            _generated_path_allocation_to_json(allocation)
            for allocation in metadata.generated_path_allocations
        ],
        "managed_write_root_inputs": list(metadata.managed_write_root_inputs),
        "runtime_context_inputs": list(metadata.runtime_context_inputs),
        "private_exec_context_bindings": [
            _private_exec_context_binding_to_json(binding)
            for binding in metadata.private_exec_context_bindings
        ],
        "compatibility_bridge_inputs": list(metadata.compatibility_bridge_inputs),
        "workflow_name": metadata.workflow_name,
        "output_names": list(metadata.output_names),
    }


def _private_exec_context_binding_to_json(binding: PrivateExecContextBinding) -> dict[str, Any]:
    return {
        "binding_id": binding.binding_id,
        "source_param_name": binding.source_param_name,
        "context_family": binding.context_family,
        "bridge_class": binding.bridge_class,
        "generated_input_names": list(binding.generated_input_names),
        "required_capabilities": list(binding.required_capabilities),
        "derived_phase_identity": binding.derived_phase_identity,
        "allocation_ids": list(binding.allocation_ids),
        "projection_hints": _json_data(binding.projection_hints),
        "source_provenance": _json_data(binding.source_provenance),
    }


def _generated_path_allocation_to_json(allocation: GeneratedPathAllocation) -> dict[str, Any]:
    return {
        "allocation_id": allocation.allocation_id,
        "workflow_name": allocation.workflow_name,
        "semantic_role": allocation.semantic_role.value,
        "privacy": allocation.privacy.value,
        "resume_scope": allocation.resume_scope.value,
        "stable_identity": allocation.stable_identity,
        "concrete_path_template": allocation.concrete_path_template,
        "generated_input_name": allocation.generated_input_name,
        "path_safety_policy": allocation.path_safety_policy,
        "projection_hints": _json_data(allocation.projection_hints),
    }


def _meta_to_json(meta: CoreStmtMeta) -> dict[str, Any]:
    return {
        "id": meta.id,
        "step_id": meta.step_id,
        "step_kind": meta.step_kind,
        "display_name": meta.display_name,
        "lexical_scope": list(meta.lexical_scope),
        "origin_key": meta.origin_key,
        "generated_by": meta.generated_by,
    }


def _statement_to_json(statement: Any) -> dict[str, Any]:
    payload = {"meta": _meta_to_json(statement.meta), "common": _json_data(statement.common)}
    if isinstance(statement, CoreCommandStep):
        payload.update(
            {
                "kind": "command",
                "command": _json_data(statement.command),
                "boundary_kind": statement.boundary_kind,
                "boundary_name": statement.boundary_name,
            }
        )
        return payload
    if isinstance(statement, CoreProviderStep):
        payload.update(
            {
                "kind": "provider",
                "provider": statement.provider,
                "provider_params": _json_data(statement.provider_params),
                "managed_jobs": _json_data(statement.managed_jobs),
                "input_file": _json_data(statement.input_file),
                "asset_file": _json_data(statement.asset_file),
                "depends_on": _json_data(statement.depends_on),
                "asset_depends_on": _json_data(statement.asset_depends_on),
                "inject_output_contract": statement.inject_output_contract,
                "inject_consumes": statement.inject_consumes,
                "prompt_consumes": _json_data(statement.prompt_consumes),
                "typed_prompt_inputs": _json_data(statement.typed_prompt_inputs),
                "consumes_injection_position": statement.consumes_injection_position,
            }
        )
        return payload
    if isinstance(statement, CoreAdjudicatedProviderStep):
        payload.update({"kind": "adjudicated_provider", "adjudicated_provider": _json_data(statement.adjudicated_provider)})
        return payload
    if isinstance(statement, CoreWaitForStep):
        payload.update({"kind": "wait_for", "wait_for": _json_data(statement.wait_for)})
        return payload
    if isinstance(statement, CoreAssertStep):
        payload.update({"kind": "assert", "assert_predicate": _json_data(statement.assert_predicate)})
        return payload
    if isinstance(statement, CoreSetScalarStep):
        payload.update({"kind": "set_scalar", "set_scalar": _json_data(statement.set_scalar)})
        return payload
    if isinstance(statement, CoreResourceTransitionStep):
        payload.update({"kind": "resource_transition", "resource_transition": _json_data(statement.resource_transition)})
        return payload
    if isinstance(statement, CorePureProjectionStep):
        payload.update({"kind": "pure_projection", "pure_projection": _json_data(statement.pure_projection)})
        return payload
    if isinstance(statement, CoreMaterializeViewStep):
        payload.update({"kind": "materialize_view", "materialize_view": _json_data(statement.materialize_view)})
        return payload
    if isinstance(statement, CoreIncrementScalarStep):
        payload.update({"kind": "increment_scalar", "increment_scalar": _json_data(statement.increment_scalar)})
        return payload
    if isinstance(statement, CoreMaterializeArtifactsStep):
        payload.update({"kind": "materialize_artifacts", "materialize_artifacts": _json_data(statement.materialize_artifacts)})
        return payload
    if isinstance(statement, CoreSelectVariantOutputStep):
        payload.update({"kind": "select_variant_output", "select_variant_output": _json_data(statement.select_variant_output)})
        return payload
    if isinstance(statement, CoreCallStep):
        payload.update({"kind": "call", "call_alias": statement.call_alias, "call_bindings": _json_data(statement.call_bindings)})
        return payload
    if isinstance(statement, CoreIf):
        payload.update(
            {
                "kind": "if",
                "condition": _json_data(statement.condition),
                "then_branch": _branch_to_json(statement.then_branch),
                "else_branch": _branch_to_json(statement.else_branch),
            }
        )
        return payload
    if isinstance(statement, CoreMatch):
        payload.update(
            {
                "kind": "match",
                "match_ref": _json_data(statement.match_ref),
                "cases": {
                    case_name: _match_case_to_json(case)
                    for case_name, case in sorted(statement.cases.items())
                },
            }
        )
        return payload
    if isinstance(statement, CoreForEach):
        payload.update(
            {
                "kind": "for_each",
                "items": _json_data(statement.items),
                "items_from": statement.items_from,
                "item_name": statement.item_name,
                "statements": [_statement_to_json(item) for item in statement.statements],
            }
        )
        return payload
    if isinstance(statement, CoreRepeatUntil):
        payload.update(
            {
                "kind": "repeat_until",
                "condition": _json_data(statement.condition),
                "max_iterations": statement.max_iterations,
                "step_id": statement.step_id,
                "token": statement.token,
                "outputs": {name: _contract_to_json(contract) for name, contract in sorted(statement.outputs.items())},
                "on_exhausted_outputs": _json_data(statement.on_exhausted_outputs),
                "statements": [_statement_to_json(item) for item in statement.statements],
            }
        )
        return payload
    raise TypeError(f"Unsupported core statement type `{type(statement).__name__}`")


def _branch_to_json(branch: CoreBranchBlock | None) -> dict[str, Any] | None:
    if branch is None:
        return None
    return {
        "branch_name": branch.branch_name,
        "token": branch.token,
        "step_id": branch.step_id,
        "outputs": {name: _contract_to_json(contract) for name, contract in sorted(branch.outputs.items())},
        "statements": [_statement_to_json(statement) for statement in branch.statements],
    }


def _match_case_to_json(case: CoreMatchCaseBlock) -> dict[str, Any]:
    return {
        "case_name": case.case_name,
        "token": case.token,
        "step_id": case.step_id,
        "outputs": {name: _contract_to_json(contract) for name, contract in sorted(case.outputs.items())},
        "statements": [_statement_to_json(statement) for statement in case.statements],
    }


def _finally_to_json(finalization: CoreFinally | None) -> dict[str, Any] | None:
    if finalization is None:
        return None
    return {
        "token": finalization.token,
        "step_id": finalization.step_id,
        "statements": [_statement_to_json(statement) for statement in finalization.statements],
    }


def _json_data(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _json_data(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_json_data(item) for item in value]
    if isinstance(value, list):
        return [_json_data(item) for item in value]
    if hasattr(value, "__dict__"):
        return {
            key: _json_data(item)
            for key, item in vars(value).items()
            if not key.startswith("_")
        }
    return repr(value)
