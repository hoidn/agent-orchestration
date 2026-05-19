"""Lower typed Workflow Lisp workflows into authored workflow mappings."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any

from orchestrator.loader import WorkflowLoader
from orchestrator.workflow.elaboration import elaborate_surface_workflow
from orchestrator.workflow.loaded_bundle import LoadedWorkflowBundle
from orchestrator.workflow.lowering import lower_surface_workflow

from .definitions import elaborate_definition_module
from .contracts import derive_structured_result_contract, derive_workflow_signature_contracts
from .diagnostics import LispFrontendCompileError, LispFrontendDiagnostic
from .expressions import (
    CallExpr,
    CommandResultExpr,
    FieldAccessExpr,
    LetStarExpr,
    LiteralExpr,
    MatchExpr,
    NameExpr,
    ProviderResultExpr,
    RecordExpr,
)
from .reader import read_sexpr_file
from .sexpr import ListExpr, SymbolAtom
from .spans import SourceSpan
from .syntax import WorkflowLispSyntaxModule, build_syntax_module
from .type_env import FrontendTypeEnvironment, RecordTypeRef, TypeRef
from .typecheck import TypedExpr
from .workflows import (
    CommandBoundaryEnvironment,
    ExternEnvironment,
    PromptExtern,
    ProviderExtern,
    TypedWorkflowDef,
)

_GENERATED_STEP_ID_RE = re.compile(r"[^A-Za-z0-9_]+")


@dataclass(frozen=True)
class LoweringOriginMap:
    workflow_span: SourceSpan
    step_spans: Mapping[str, SourceSpan]
    generated_input_spans: Mapping[str, SourceSpan]
    generated_output_spans: Mapping[str, SourceSpan]
    generated_path_spans: Mapping[str, SourceSpan]


@dataclass(frozen=True)
class LoweredWorkflow:
    typed_workflow: TypedWorkflowDef
    authored_mapping: Mapping[str, object]
    origin_map: LoweringOriginMap


def lower_workflow_definitions(
    typed_workflows: tuple[TypedWorkflowDef, ...],
    *,
    workflow_path: Path,
    extern_environment: ExternEnvironment,
    command_boundary_environment: CommandBoundaryEnvironment,
) -> tuple[LoweredWorkflow, ...]:
    """Lower typed workflows into authored workflow mappings."""

    workflows_by_name = {workflow.definition.name: workflow for workflow in typed_workflows}
    type_env = FrontendTypeEnvironment.from_module(
        elaborate_definition_module(_definition_only_syntax_module(build_syntax_module(read_sexpr_file(workflow_path))))
    )
    lowered_by_name: dict[str, LoweredWorkflow] = {}
    visiting: set[str] = set()

    def lower_one(workflow_name: str) -> LoweredWorkflow:
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
                    ),
                )
            )
        visiting.add(workflow_name)
        typed_workflow = workflows_by_name[workflow_name]

        for dependency in _typed_workflow_dependencies(typed_workflow):
            if dependency in workflows_by_name:
                lower_one(dependency)

        lowered = _lower_one_workflow(
            typed_workflow,
            workflow_path=workflow_path,
            extern_environment=extern_environment,
            command_boundary_environment=command_boundary_environment,
            lowered_callees=lowered_by_name,
            type_env=type_env,
        )
        lowered_by_name[workflow_name] = lowered
        visiting.remove(workflow_name)
        return lowered

    ordered: list[LoweredWorkflow] = []
    for workflow in typed_workflows:
        ordered.append(lower_one(workflow.definition.name))
    return tuple(ordered)


def validate_lowered_workflows(
    lowered_workflows: tuple[LoweredWorkflow, ...],
    *,
    workspace_root: Path,
) -> Mapping[str, LoadedWorkflowBundle]:
    """Validate authored mappings through the shared elaboration and lowering seam."""

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
        imported_bundles = {
            dependency: validate_one(dependency)
            for dependency in _lowered_workflow_dependencies(lowered)
            if dependency in lowered_by_name
        }
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
    extern_environment: ExternEnvironment,
    command_boundary_environment: CommandBoundaryEnvironment,
    lowered_callees: Mapping[str, LoweredWorkflow],
    type_env: FrontendTypeEnvironment,
) -> LoweredWorkflow:
    inputs, outputs, flattened_fields = derive_workflow_signature_contracts(typed_workflow.signature)
    authored_inputs = {name: dict(contract.definition) for name, contract in inputs.items()}
    authored_outputs = {name: dict(contract.definition) for name, contract in outputs.items()}
    origin_outputs = {field.generated_name: typed_workflow.definition.span for field in flattened_fields}

    context = _LoweringContext(
        workflow_name=typed_workflow.definition.name,
        workflow_path=workflow_path,
        signature=typed_workflow.signature,
        extern_environment=extern_environment,
        command_boundary_environment=command_boundary_environment,
        lowered_callees=lowered_callees,
        type_env=type_env,
        step_spans={},
        generated_input_spans={},
        generated_output_spans=origin_outputs,
        generated_path_spans={},
        top_level_artifacts={},
        return_output_contracts=MappingProxyType(
            {
                name.removeprefix("return__"): dict(definition)
                for name, definition in authored_outputs.items()
            }
        ),
    )
    local_values = _signature_local_values(typed_workflow)
    steps, terminal = _lower_expression(typed_workflow.typed_body, context=context, local_values=local_values)

    for hidden_input_name, span in terminal.hidden_inputs.items():
        authored_inputs[hidden_input_name] = {
            "kind": "relpath",
            "type": "relpath",
        }
        context.generated_input_spans[hidden_input_name] = span

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
            workflow_span=typed_workflow.definition.span,
            step_spans=MappingProxyType(dict(context.step_spans)),
            generated_input_spans=MappingProxyType(dict(context.generated_input_spans)),
            generated_output_spans=MappingProxyType(dict(context.generated_output_spans)),
            generated_path_spans=MappingProxyType(dict(context.generated_path_spans)),
        ),
    )


@dataclass
class _TerminalResult:
    step_name: str
    step_id: str
    output_refs: Mapping[str, str]
    output_kind: str
    hidden_inputs: Mapping[str, SourceSpan]


@dataclass
class _LoweringContext:
    workflow_name: str
    workflow_path: Path
    signature: object
    extern_environment: ExternEnvironment
    command_boundary_environment: CommandBoundaryEnvironment
    lowered_callees: Mapping[str, LoweredWorkflow]
    type_env: FrontendTypeEnvironment
    step_spans: dict[str, SourceSpan]
    generated_input_spans: dict[str, SourceSpan]
    generated_output_spans: Mapping[str, SourceSpan]
    generated_path_spans: dict[str, SourceSpan]
    top_level_artifacts: dict[str, Any]
    return_output_contracts: Mapping[str, Mapping[str, Any]]


def _normalize_generated_step_id(raw_name: str) -> str:
    normalized = _GENERATED_STEP_ID_RE.sub("_", raw_name).strip("_")
    if not normalized:
        return "generated_step"
    if not normalized[0].isalpha():
        normalized = f"S_{normalized}"
    return normalized


def _record_step_origin(context: _LoweringContext, *, step_name: str, step_id: str, span: SourceSpan) -> None:
    context.step_spans[step_name] = span
    context.step_spans[step_id] = span


def _lower_expression(
    typed_expr: TypedExpr,
    *,
    context: _LoweringContext,
    local_values: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], _TerminalResult]:
    expr = typed_expr.expr
    if isinstance(expr, CommandResultExpr):
        return _lower_command_result(typed_expr, context=context)
    if isinstance(expr, ProviderResultExpr):
        return _lower_provider_result(
            expr,
            result_type=typed_expr.type_ref,
            context=context,
        )
    if isinstance(expr, CallExpr):
        return _lower_call_expr(typed_expr, context=context, local_values=local_values)
    if isinstance(expr, RecordExpr):
        return _lower_record_expr(typed_expr, context=context, local_values=local_values)
    if isinstance(expr, LetStarExpr):
        return _lower_let_star(typed_expr, context=context, local_values=local_values)
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
) -> tuple[list[dict[str, Any]], _TerminalResult]:
    expr = typed_expr.expr
    assert isinstance(expr, CommandResultExpr)
    step_name = f"{context.workflow_name}__{expr.step_name}"
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
    _record_step_origin(context, step_name=step_name, step_id=step_id, span=expr.span)
    context.generated_path_spans[authored_contract["path"]] = expr.span

    command = list(binding.stable_command)
    command.extend(_render_argv_tail(expr.argv[len(binding.stable_command) :], local_values=_signature_local_values(context)))
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
        hidden_inputs={hidden_input_name: expr.span},
    )


def _lower_provider_result(
    expr: ProviderResultExpr,
    *,
    result_type: TypeRef,
    context: _LoweringContext,
    step_name: str | None = None,
) -> tuple[list[dict[str, Any]], _TerminalResult]:
    provider_step_name = step_name or f"{context.workflow_name}__result"
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
    authored_contract["path"] = f"${{inputs.{hidden_input_name}}}"
    _record_step_origin(context, step_name=provider_step_name, step_id=provider_step_id, span=expr.span)
    context.generated_path_spans[authored_contract["path"]] = expr.span
    provider_step = {
        "name": provider_step_name,
        "id": provider_step_id,
        "provider": provider_binding.provider_id,
        "asset_file": prompt_binding.asset_file,
        "inject_output_contract": True,
        bundle_contract.contract_kind: authored_contract,
    }
    return [provider_step], _TerminalResult(
        step_name=provider_step_name,
        step_id=provider_step_id,
        output_refs=_record_output_refs(provider_step_name, result_type),
        output_kind="step",
        hidden_inputs={hidden_input_name: expr.span},
    )


def _lower_call_expr(
    typed_expr: TypedExpr,
    *,
    context: _LoweringContext,
    local_values: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], _TerminalResult]:
    expr = typed_expr.expr
    assert isinstance(expr, CallExpr)
    callee = context.lowered_callees.get(expr.callee_name)
    if callee is None:
        raise _compile_error(
            code="workflow_call_unknown",
            message=f"unknown workflow callee `{expr.callee_name}` during lowering",
            span=expr.span,
            form_path=expr.form_path,
        )
    step_name = f"{context.workflow_name}__call_{expr.callee_name}"
    step_id = _normalize_generated_step_id(step_name)
    with_bindings: dict[str, Any] = {}
    binding_by_name = dict(expr.bindings)
    for param_name, param_type in callee.typed_workflow.signature.params:
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
    for managed_input in _managed_inputs_from_mapping(callee.authored_mapping):
        with_bindings[managed_input] = (
            f".orchestrate/workflow_lisp/calls/{context.workflow_name}/{step_name}/{expr.callee_name}/{managed_input}.json"
        )
    _record_step_origin(context, step_name=step_name, step_id=step_id, span=expr.span)
    step = {
        "name": step_name,
        "id": step_id,
        "call": expr.callee_name,
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


def _lower_let_star(
    typed_expr: TypedExpr,
    *,
    context: _LoweringContext,
    local_values: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], _TerminalResult]:
    expr = typed_expr.expr
    assert isinstance(expr, LetStarExpr)
    if len(expr.bindings) != 1:
        raise _compile_error(
            code="workflow_return_not_exportable",
            message="Stage 3 lowering supports only one let* binding in workflow bodies",
            span=expr.span,
            form_path=expr.form_path,
        )
    binding_name, binding_expr = expr.bindings[0]
    if not isinstance(binding_expr, ProviderResultExpr):
        raise _compile_error(
            code="workflow_return_not_exportable",
            message="Stage 3 lowering supports let* only for provider-result bindings",
            span=binding_expr.span,
            form_path=binding_expr.form_path,
        )
    provider_step_name = f"{context.workflow_name}__{binding_name}"
    binding_type = context.type_env.resolve_type(
        binding_expr.returns_type_name,
        span=binding_expr.span,
        form_path=binding_expr.form_path,
    )
    provider_steps, provider_terminal = _lower_provider_result(
        binding_expr,
        result_type=binding_type,
        context=context,
        step_name=provider_step_name,
    )
    local_bindings = dict(local_values)
    if isinstance(binding_type, RecordTypeRef):
        local_bindings[binding_name] = _build_record_step_local_value(
            binding_type,
            step_name=provider_step_name,
        )

    if isinstance(expr.body, MatchExpr):
        lowered_steps, terminal = _lower_match_expr(
            expr.body,
            context=context,
            binding_name=binding_name,
            provider_step_name=provider_step_name,
        )
    else:
        lowered_steps, terminal = _lower_expression(
            TypedExpr(
                expr=expr.body,
                type_ref=typed_expr.type_ref,
                span=expr.body.span,
                form_path=expr.body.form_path,
            ),
            context=context,
            local_values=local_bindings,
        )
    hidden_inputs = dict(provider_terminal.hidden_inputs)
    hidden_inputs.update(terminal.hidden_inputs)
    return [*provider_steps, *lowered_steps], _TerminalResult(
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
    provider_step_name: str,
) -> tuple[list[dict[str, Any]], _TerminalResult]:
    match_step_name = f"{context.workflow_name}__match_{binding_name}"
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
                provider_step_name=provider_step_name,
                context=context,
            )
            case_steps.extend(lowered_output["steps"])
            case_outputs[generated_output_name] = lowered_output["output"]
        case_name = f"{match_step_name}__{arm.variant_name.lower()}"
        cases[arm.variant_name] = {
            "id": _normalize_generated_step_id(case_name),
            "outputs": case_outputs,
            "steps": case_steps,
        }

    _record_step_origin(context, step_name=match_step_name, step_id=match_step_id, span=match_expr.span)
    match_step = {
        "name": match_step_name,
        "id": match_step_id,
        "match": {
            "ref": f"root.steps.{provider_step_name}.artifacts.variant",
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


def _lower_workflow_outputs(
    *,
    typed_workflow: TypedWorkflowDef,
    authored_outputs: Mapping[str, dict[str, Any]],
    terminal: _TerminalResult,
) -> dict[str, Any]:
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
    inputs = authored_mapping.get("inputs")
    if not isinstance(inputs, Mapping):
        return ()
    return tuple(
        name for name in inputs if isinstance(name, str) and name.startswith("__write_root__")
    )


def _signature_local_values(typed_workflow: TypedWorkflowDef | _LoweringContext) -> dict[str, Any]:
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


def _render_argv_tail(argv: list[Any], *, local_values: Mapping[str, Any]) -> list[str]:
    rendered: list[str] = []
    for expr in argv:
        rendered.append(_render_scalar_expr(expr, local_values=local_values))
    return rendered


def _render_scalar_expr(expr: Any, *, local_values: Mapping[str, Any]) -> str:
    from .expressions import LiteralExpr

    if isinstance(expr, LiteralExpr):
        return str(expr.value)
    value = _resolve_expr_local_value(expr, local_values=local_values)
    if isinstance(value, str):
        return "${" + value + "}"
    raise _compile_error(
        code="workflow_return_not_exportable",
        message="Stage 3 lowering requires command argv values to resolve to literals or workflow inputs",
        span=expr.span,
        form_path=expr.form_path,
    )


def _render_call_binding_ref(
    expr: Any,
    *,
    local_values: Mapping[str, Any],
    field_path: tuple[str, ...] = (),
) -> Any:
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


def _resolve_expr_local_value(expr: Any, *, local_values: Mapping[str, Any]) -> Any:
    if isinstance(expr, NameExpr):
        return local_values.get(expr.name)
    if isinstance(expr, FieldAccessExpr):
        base_value = local_values.get(expr.base.name)
        return _resolve_nested_local_value(base_value, tuple(expr.fields))
    return None


def _resolve_nested_local_value(value: Any, field_path: tuple[str, ...]) -> Any:
    current = value
    for field_name in field_path:
        if not isinstance(current, Mapping):
            return None
        current = current.get(field_name)
    return current


def _build_record_local_value(type_ref: RecordTypeRef, *, generated_name: str) -> dict[str, Any]:
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


def _build_nested_record_step_local_value(
    type_ref: RecordTypeRef,
    *,
    step_name: str,
    artifact_prefix: tuple[str, ...],
) -> dict[str, Any]:
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


def _flatten_boundary_leaf_paths(
    type_ref: RecordTypeRef,
    *,
    generated_name: str,
    field_path: tuple[str, ...] = (),
) -> tuple[tuple[str, tuple[str, ...]], ...]:
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
    return {
        f"return__{'__'.join(field_path)}": f"root.steps.{step_name}.artifacts.{'__'.join(field_path)}"
        for _, field_path in _flatten_boundary_leaf_paths(type_ref, generated_name="return")
    }


def _record_expr_value_at_path(record_expr: RecordExpr, field_path: tuple[str, ...]) -> Any:
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
    if not field_access.fields:
        return None
    return f"root.steps.{provider_step_name}.artifacts.{'__'.join(field_access.fields)}"


def _record_output_refs(step_name: str, type_ref: Any) -> dict[str, str]:
    if isinstance(type_ref, RecordTypeRef):
        return _flatten_record_output_refs(step_name, type_ref)
    return {}


def _flatten_return_output_names(context: _LoweringContext) -> tuple[str, ...]:
    return tuple(f"return__{field_name}" for field_name in context.return_output_contracts)


def _return_field_path(field_name: str) -> tuple[str, ...]:
    return tuple(field_name.split("__"))


def _lower_match_output_field(
    *,
    record_expr: RecordExpr,
    field_name: str,
    generated_output_name: str,
    contract_definition: Mapping[str, Any],
    match_step_id: str,
    variant_name: str,
    binding_name: str,
    provider_step_name: str,
    context: _LoweringContext,
) -> dict[str, Any]:
    value = _record_expr_value_at_path(record_expr, _return_field_path(field_name))
    if isinstance(value, FieldAccessExpr) and value.base.name == binding_name:
        provider_ref = _render_provider_artifact_ref(provider_step_name, value)
        if provider_ref is not None:
            return {
                "steps": [],
                "output": {
                    **contract_definition,
                    "from": {"ref": provider_ref},
                },
            }
    raise _compile_error(
        code="workflow_return_not_exportable",
        message=(
            f"record return field `{field_name}` must lower from the matched provider result "
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
        step_name=context.workflow_name,
        step_id=f"{_normalize_generated_step_id(context.workflow_name)}__return_projection",
        output_refs=output_refs,
        output_kind="projection",
        hidden_inputs={},
    )


def _render_existing_output_ref(expr: Any, *, local_values: Mapping[str, Any]) -> str | None:
    value = _resolve_expr_local_value(expr, local_values=local_values)
    if not isinstance(value, str):
        return None
    if value.startswith("root.steps.") or value.startswith("self.steps."):
        return value
    return None


def _record_field_value(record_expr: RecordExpr, field_name: str) -> Any:
    for name, value in record_expr.fields:
        if name == field_name:
            return value
    raise _compile_error(
        code="workflow_return_not_exportable",
        message=f"record return field `{field_name}` is missing from the lowered workflow return expression",
        span=record_expr.span,
        form_path=record_expr.form_path,
    )


def _typed_workflow_dependencies(typed_workflow: TypedWorkflowDef) -> set[str]:
    dependencies: set[str] = set()

    def walk(expr: Any) -> None:
        if isinstance(expr, CallExpr):
            dependencies.add(expr.callee_name)
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

    walk(typed_workflow.typed_body.expr)
    return dependencies


def _lowered_workflow_dependencies(lowered_workflow: LoweredWorkflow) -> set[str]:
    steps = lowered_workflow.authored_mapping.get("steps")
    dependencies: set[str] = set()
    if isinstance(steps, list):
        for step in steps:
            if isinstance(step, Mapping) and isinstance(step.get("call"), str):
                dependencies.add(str(step["call"]))
    return dependencies


def _validate_one_lowered_workflow(
    lowered_workflow: LoweredWorkflow,
    *,
    workspace_root: Path,
    imported_bundles: Mapping[str, LoadedWorkflowBundle],
    workflow_is_imported: bool,
) -> LoadedWorkflowBundle:
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
    diagnostics: list[LispFrontendDiagnostic] = []
    for error in errors:
        message = str(error.message)
        span = _remap_validation_message(lowered_workflow.origin_map, message)
        if span is None:
            diagnostics.append(
                LispFrontendDiagnostic(
                    code="source_map_missing",
                    message=message,
                    span=lowered_workflow.origin_map.workflow_span,
                    form_path=lowered_workflow.typed_workflow.definition.form_path,
                )
            )
            continue
        diagnostics.append(
            LispFrontendDiagnostic(
                code="workflow_boundary_type_invalid",
                message=message,
                span=span,
                form_path=lowered_workflow.typed_workflow.definition.form_path,
            )
        )
    raise LispFrontendCompileError(tuple(diagnostics))


def _remap_validation_message(origin_map: LoweringOriginMap, message: str) -> SourceSpan | None:
    for key, span in origin_map.step_spans.items():
        if key in message:
            return span
    for key, span in origin_map.generated_input_spans.items():
        if key in message:
            return span
    for key, span in origin_map.generated_output_spans.items():
        if key in message:
            return span
    for key, span in origin_map.generated_path_spans.items():
        if key in message:
            return span
    if "output" in message or "input" in message or "workflow" in message:
        return origin_map.workflow_span
    return None


def _compile_error(*, code: str, message: str, span: SourceSpan, form_path: tuple[str, ...]) -> LispFrontendCompileError:
    return LispFrontendCompileError(
        (
            LispFrontendDiagnostic(
                code=code,
                message=message,
                span=span,
                form_path=form_path,
            ),
        )
    )


def _definition_only_syntax_module(module_syntax: WorkflowLispSyntaxModule) -> WorkflowLispSyntaxModule:
    definition_forms = []
    for form in module_syntax.forms:
        datum = form.datum
        if not isinstance(datum, ListExpr) or not datum.items:
            continue
        head = datum.items[0]
        if isinstance(head, SymbolAtom) and head.value == "defworkflow":
            continue
        definition_forms.append(form)
    return WorkflowLispSyntaxModule(
        language_version=module_syntax.language_version,
        target_dsl_version=module_syntax.target_dsl_version,
        forms=tuple(definition_forms),
        span=module_syntax.span,
        module_path=module_syntax.module_path,
    )
