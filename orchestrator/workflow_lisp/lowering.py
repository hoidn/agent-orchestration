"""Lowering for Workflow Lisp MVP frontend outputs into core workflow dictionaries."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Callable, Mapping

from .compiler import CompiledWorkflowModule
from .definitions import (
    DefinitionNode,
    EnumDefinition,
    FunctionDefinition,
    ImportDefinition,
    PathDefinition,
    ProcedureDefinition,
    RecordDefinition,
    UnionDefinition,
    WorkflowParameter,
    WorkflowDefinition,
)
from .expressions import (
    CallExpression,
    CommandResultExpression,
    ExpressionNode,
    FieldAccessExpression,
    LetStarExpression,
    LiteralExpression,
    MatchExpression,
    PhaseTargetExpression,
    ProviderResultExpression,
    RecordExpression,
    ReferenceExpression,
    WithPhaseExpression,
    shape_expression,
)
from .parser import WorkflowLispSyntaxError
from .syntax import AtomKind, SourceSpan, SyntaxAtom, SyntaxDiagnostic


@dataclass(frozen=True)
class LoweredWorkflowModule:
    """Workflow Lisp module lowered into one workflow dictionary per defworkflow."""

    source_path: str
    workflows: MappingProxyType[str, dict[str, Any]]
    source_map: MappingProxyType[str, MappingProxyType[str, SourceSpan]]


@dataclass(frozen=True)
class _WorkflowInputLowering:
    """Lowered boundary inputs plus reference mapping for structured params."""

    contracts: dict[str, dict[str, Any]]
    leaf_input_names: frozenset[str]
    structured_param_names: frozenset[str]
    field_reference_paths: dict[tuple[str, tuple[str, ...]], str]
    source_spans: dict[str, SourceSpan]
    input_type_names: dict[str, str]


@dataclass(frozen=True)
class _FlattenedRecordLeafField:
    """One flattened leaf field for nested record output contracts."""

    flattened_name: str
    json_pointer: str
    type_name: str
    type_span: SourceSpan
    source_span: SourceSpan


def _raise_lowering_error(
    *,
    code: str,
    message: str,
    span: SourceSpan,
    enclosing_form_name: str | None = None,
    generated_core_node_id: str | None = None,
) -> None:
    raise WorkflowLispSyntaxError(
        SyntaxDiagnostic(
            code=code,
            message=message,
            span=span,
            source_file=span.source_file,
            line=span.line_start,
            column=span.column_start,
            enclosing_form_name=enclosing_form_name,
            generated_core_node_id=generated_core_node_id,
        )
    )


def lower_compiled_module(compiled: CompiledWorkflowModule) -> LoweredWorkflowModule:
    """Lower one compiled Workflow Lisp module into runtime workflow dictionaries."""

    callable_signatures: dict[str, WorkflowDefinition | ProcedureDefinition] = {
        workflow.name: workflow
        for workflow in compiled.definition_module.workflow_definitions
        if isinstance(workflow, WorkflowDefinition)
    }
    callable_signatures.update(
        {
            procedure.name: procedure
            for procedure in compiled.definition_module.procedure_definitions
            if isinstance(procedure, ProcedureDefinition)
        }
    )
    definition_table = dict(compiled.definition_module.definition_table)
    function_definitions = {
        function.name: function for function in compiled.definition_module.function_definitions
    }

    lowered: dict[str, dict[str, Any]] = {}
    source_map: dict[str, MappingProxyType[str, SourceSpan]] = {}
    checked_callables: list[tuple[str, ExpressionNode, str]] = [
        (checked.name, checked.expression, "defworkflow")
        for checked in compiled.expression_module.workflows
    ]
    checked_callables.extend(
        [
            (checked.name, checked.expression, "defproc")
            for checked in compiled.expression_module.procedures
        ]
    )
    callable_expressions = {name: expression for name, expression, _ in checked_callables}
    selected_callable_names = _select_callables_to_lower(
        compiled=compiled,
        callable_signatures=callable_signatures,
        callable_expressions=callable_expressions,
        checked_callables=checked_callables,
    )
    for callable_name, checked_expression, form_name in checked_callables:
        if callable_name not in selected_callable_names:
            continue
        signature = callable_signatures.get(callable_name)
        if signature is None:
            _raise_lowering_error(
                code="frontend_lowering_error",
                message=f"Missing callable signature for {callable_name}",
                span=compiled.parsed_module.header_form.span,
                enclosing_form_name=form_name,
            )

        lowered_inputs = _lower_workflow_inputs(
            workflow_name=callable_name,
            parameters=signature.parameters,
            definitions=definition_table,
        )
        inputs = lowered_inputs.contracts
        workflow_input_names = lowered_inputs.leaf_input_names

        lowered_root_expression = _inline_root_expression(
            checked_expression,
            function_definitions=function_definitions,
        )

        step_source_spans: dict[str, SourceSpan] = {}
        root_match_case_steps: list[tuple[str, str, ExpressionNode]] = []
        if isinstance(lowered_root_expression, MatchExpression):
            lowered_steps, root_step_name, step_source_spans, root_match_case_steps = _lower_root_match_expression(
                expression=lowered_root_expression,
                workflow_name=callable_name,
                declared_return_type_name=signature.return_type.name,
                declared_return_type_span=signature.return_type.span,
                definitions=definition_table,
                workflow_signatures=callable_signatures,
                workflow_input_names=workflow_input_names,
                workflow_input_field_paths=lowered_inputs.field_reference_paths,
                workflow_input_structured_names=lowered_inputs.structured_param_names,
            )
        else:
            lowered_step = _lower_root_expression(
                expression=lowered_root_expression,
                workflow_name=callable_name,
                declared_return_type_name=signature.return_type.name,
                declared_return_type_span=signature.return_type.span,
                definitions=definition_table,
                workflow_signatures=callable_signatures,
                workflow_input_names=workflow_input_names,
                workflow_input_field_paths=lowered_inputs.field_reference_paths,
                workflow_input_structured_names=lowered_inputs.structured_param_names,
            )
            lowered_steps = [lowered_step]
            root_step_name = str(lowered_step["name"])

        lowered_workflow: dict[str, Any] = {
            "version": compiled.parsed_module.target_dsl,
            "name": callable_name,
            "inputs": inputs,
            "outputs": _workflow_outputs_for_structured_return(
                type_name=signature.return_type.name,
                type_span=signature.return_type.span,
                definitions=definition_table,
                root_step_name=root_step_name,
            ),
            "steps": lowered_steps,
        }
        call_target_spans = _collect_call_target_spans_from_expression(lowered_root_expression)
        call_targets = _collect_call_targets(lowered_steps)
        lowered_imports: dict[str, str] = {}
        for call_target in call_targets:
            if call_target in callable_signatures:
                lowered_imports[call_target] = _local_callable_import_path(
                    compiled=compiled,
                    call_target=call_target,
                )
                continue
            imported_path = _resolve_imported_call_target_path(
                call_target,
                import_definitions=compiled.definition_module.import_definitions,
            )
            if imported_path is None:
                _raise_lowering_error(
                    code="frontend_lowering_error",
                    message=f"Unable to resolve imported call target for lowering: {call_target}",
                    span=call_target_spans.get(call_target, signature.form_span),
                    enclosing_form_name=form_name,
                    generated_core_node_id=_import_alias_node_id(
                        workflow_name=callable_name,
                        alias=call_target,
                    ),
                )
            lowered_imports[call_target] = imported_path
        if lowered_imports:
            lowered_workflow["imports"] = lowered_imports
        lowered[callable_name] = lowered_workflow
        source_span = lowered_root_expression.span
        workflow_source_map: dict[str, SourceSpan] = {
            _result_node_id(callable_name): source_span,
        }
        for step in lowered_steps:
            step_name = str(step["name"])
            workflow_source_map[_step_node_id(callable_name, step_name)] = step_source_spans.get(
                step_name,
                source_span,
            )
        workflow_source_map.update(
            _workflow_input_source_map_entries(
                workflow_name=callable_name,
                parameters=signature.parameters,
                lowered_inputs=lowered_inputs,
                definitions=definition_table,
            )
        )
        workflow_source_map.update(
            _workflow_output_source_map_entries(
                workflow_name=callable_name,
                type_name=signature.return_type.name,
                type_span=signature.return_type.span,
                definitions=definition_table,
            )
        )
        if isinstance(lowered_root_expression, (ProviderResultExpression, CommandResultExpression)):
            workflow_source_map.update(
                _step_contract_source_map_entries(
                    workflow_name=callable_name,
                    step_name=str(lowered_steps[-1]["name"]),
                    type_name=signature.return_type.name,
                    type_span=signature.return_type.span,
                    definitions=definition_table,
                )
            )
        if isinstance(lowered_root_expression, CallExpression):
            workflow_source_map.update(
                _call_source_map_entries(
                    workflow_name=callable_name,
                    step_name=str(lowered_steps[-1]["name"]),
                    expression=lowered_root_expression,
                    lowered_step=lowered_steps[-1],
                )
            )
        if isinstance(lowered_root_expression, MatchExpression):
            workflow_source_map.update(
                _match_routing_source_map_entries(
                    workflow_name=callable_name,
                    match_step_name=root_step_name,
                    expression=lowered_root_expression,
                )
            )
            for case_variant_name, case_step_name, case_expression, case_step in root_match_case_steps:
                workflow_source_map[
                    _match_case_step_node_id(
                        workflow_name=callable_name,
                        match_step_name=root_step_name,
                        case_variant_name=case_variant_name,
                        case_step_name=case_step_name,
                    )
                ] = case_expression.span
                workflow_source_map.update(
                    _match_case_output_source_map_entries(
                        workflow_name=callable_name,
                        match_step_name=root_step_name,
                        case_variant_name=case_variant_name,
                        type_name=signature.return_type.name,
                        type_span=signature.return_type.span,
                        definitions=definition_table,
                    )
                )
                if not isinstance(case_expression, CallExpression):
                    if isinstance(case_expression, (ProviderResultExpression, CommandResultExpression)):
                        workflow_source_map.update(
                            _match_case_step_contract_source_map_entries(
                                workflow_name=callable_name,
                                match_step_name=root_step_name,
                                case_variant_name=case_variant_name,
                                case_step_name=case_step_name,
                                type_name=case_expression.returns_type_name,
                                type_span=case_expression.returns_type_span,
                                definitions=definition_table,
                            )
                        )
                    continue
                workflow_source_map.update(
                    _match_case_call_source_map_entries(
                        workflow_name=callable_name,
                        match_step_name=root_step_name,
                        case_variant_name=case_variant_name,
                        case_step_name=case_step_name,
                        expression=case_expression,
                        lowered_step=case_step,
                    )
                )
                import_node_id = _import_alias_node_id(
                    workflow_name=callable_name,
                    alias=case_expression.callee_name,
                )
                workflow_source_map.setdefault(import_node_id, case_expression.callee_span)

            authored_case_variants = {case_variant_name for case_variant_name, *_ in root_match_case_steps}
            match_step = lowered_steps[-1] if lowered_steps else {}
            match_block = match_step.get("match") if isinstance(match_step, dict) else None
            match_cases = match_block.get("cases") if isinstance(match_block, dict) else None
            if isinstance(match_cases, dict):
                for case_variant_name, case_payload in match_cases.items():
                    if not isinstance(case_variant_name, str):
                        continue
                    workflow_source_map.setdefault(
                        _match_case_selector_node_id(
                            workflow_name=callable_name,
                            match_step_name=root_step_name,
                            case_variant_name=case_variant_name,
                        ),
                        lowered_root_expression.span,
                    )
                    if case_variant_name in authored_case_variants:
                        continue
                    workflow_source_map.update(
                        _match_case_output_source_map_entries(
                            workflow_name=callable_name,
                            match_step_name=root_step_name,
                            case_variant_name=case_variant_name,
                            type_name=signature.return_type.name,
                            type_span=signature.return_type.span,
                            definitions=definition_table,
                        )
                    )
                    case_step_name = _first_case_step_name(case_payload)
                    if case_step_name is None:
                        continue
                    workflow_source_map.setdefault(
                        _match_case_step_node_id(
                            workflow_name=callable_name,
                            match_step_name=root_step_name,
                            case_variant_name=case_variant_name,
                            case_step_name=case_step_name,
                        ),
                        lowered_root_expression.span,
                    )
                    return_definition = definition_table.get(signature.return_type.name)
                    if not isinstance(return_definition, (RecordDefinition, UnionDefinition)):
                        continue
                    workflow_source_map.update(
                        _match_case_step_contract_source_map_entries(
                            workflow_name=callable_name,
                            match_step_name=root_step_name,
                            case_variant_name=case_variant_name,
                            case_step_name=case_step_name,
                            type_name=signature.return_type.name,
                            type_span=signature.return_type.span,
                            definitions=definition_table,
                        )
                    )
            if isinstance(lowered_root_expression.subject, (ProviderResultExpression, CommandResultExpression)):
                workflow_source_map.update(
                    _step_contract_source_map_entries(
                        workflow_name=callable_name,
                        step_name=str(lowered_steps[0]["name"]),
                        type_name=lowered_root_expression.subject.returns_type_name,
                        type_span=lowered_root_expression.subject.returns_type_span,
                        definitions=definition_table,
                    )
                )
        source_map[callable_name] = MappingProxyType(workflow_source_map)

    return LoweredWorkflowModule(
        source_path=compiled.parsed_module.source_path,
        workflows=MappingProxyType(lowered),
        source_map=MappingProxyType(source_map),
    )


def lower_compiled_module_to_workflow_dicts(compiled: CompiledWorkflowModule) -> MappingProxyType[str, dict[str, Any]]:
    """Compatibility helper returning only lowered workflow dictionaries."""

    return lower_compiled_module(compiled).workflows


def _select_callables_to_lower(
    *,
    compiled: CompiledWorkflowModule,
    callable_signatures: Mapping[str, WorkflowDefinition | ProcedureDefinition],
    callable_expressions: Mapping[str, ExpressionNode],
    checked_callables: list[tuple[str, ExpressionNode, str]],
) -> frozenset[str]:
    ordered_callable_names = tuple(name for name, _, _ in checked_callables)
    if not _is_defmodule_header(compiled):
        return frozenset(ordered_callable_names)
    if not compiled.definition_module.exported_names:
        return frozenset(ordered_callable_names)

    exported_callable_roots = tuple(
        exported_name
        for exported_name in compiled.definition_module.exported_names
        if exported_name in callable_signatures
    )
    if not exported_callable_roots:
        return frozenset()

    local_callable_names = frozenset(callable_signatures)
    selected: set[str] = set()
    frontier = list(exported_callable_roots)
    while frontier:
        callable_name = frontier.pop()
        if callable_name in selected:
            continue
        selected.add(callable_name)
        expression = callable_expressions.get(callable_name)
        if expression is None:
            continue
        for local_target in _collect_local_call_targets_from_expression(
            expression,
            local_callable_names=local_callable_names,
        ):
            if local_target not in selected:
                frontier.append(local_target)

    return frozenset(name for name in ordered_callable_names if name in selected)


def _is_defmodule_header(compiled: CompiledWorkflowModule) -> bool:
    if not compiled.parsed_module.header_form.items:
        return False
    head = compiled.parsed_module.header_form.items[0]
    return isinstance(head, SyntaxAtom) and head.kind is AtomKind.SYMBOL and str(head.value) == "defmodule"


def _local_callable_import_path(*, compiled: CompiledWorkflowModule, call_target: str) -> str:
    if not _is_defmodule_header(compiled):
        return f"./{call_target}.yaml"
    module_filename = Path(compiled.parsed_module.source_path).name
    return f"./{module_filename}#{call_target}"


def _collect_local_call_targets_from_expression(
    expression: ExpressionNode,
    *,
    local_callable_names: frozenset[str],
) -> frozenset[str]:
    targets: set[str] = set()

    def visit(node: ExpressionNode) -> None:
        if isinstance(node, CallExpression):
            if node.callee_name in local_callable_names:
                targets.add(node.callee_name)
            for argument in node.arguments:
                visit(argument.value)
            return
        if isinstance(node, LetStarExpression):
            for binding in node.bindings:
                visit(binding.value)
            visit(node.body)
            return
        if isinstance(node, MatchExpression):
            visit(node.subject)
            for arm in node.arms:
                visit(arm.body)
            return
        if isinstance(node, RecordExpression):
            for field in node.fields:
                visit(field.value)
            return
        if isinstance(node, ProviderResultExpression):
            for provider_input in node.inputs:
                visit(provider_input)
            return
        if isinstance(node, CommandResultExpression):
            for argument in node.argv:
                visit(argument)
            return
        if isinstance(node, WithPhaseExpression):
            visit(node.context)
            visit(node.body)
            return
        if isinstance(node, PhaseTargetExpression):
            visit(node.context)
            return
        if isinstance(node, FieldAccessExpression):
            visit(node.base)
            return
        if isinstance(node, (LiteralExpression, ReferenceExpression)):
            return

    visit(expression)
    return frozenset(targets)


def _collect_call_target_spans_from_expression(expression: ExpressionNode) -> dict[str, SourceSpan]:
    """Collect first-seen call target spans for precise import-resolution diagnostics."""

    target_spans: dict[str, SourceSpan] = {}

    def visit(node: ExpressionNode) -> None:
        if isinstance(node, CallExpression):
            target_spans.setdefault(node.callee_name, node.callee_span)
            for argument in node.arguments:
                visit(argument.value)
            return
        if isinstance(node, LetStarExpression):
            for binding in node.bindings:
                visit(binding.value)
            visit(node.body)
            return
        if isinstance(node, MatchExpression):
            visit(node.subject)
            for arm in node.arms:
                visit(arm.body)
            return
        if isinstance(node, RecordExpression):
            for field in node.fields:
                visit(field.value)
            return
        if isinstance(node, ProviderResultExpression):
            for provider_input in node.inputs:
                visit(provider_input)
            return
        if isinstance(node, CommandResultExpression):
            for argument in node.argv:
                visit(argument)
            return
        if isinstance(node, WithPhaseExpression):
            visit(node.context)
            visit(node.body)
            return
        if isinstance(node, PhaseTargetExpression):
            visit(node.context)
            return
        if isinstance(node, FieldAccessExpression):
            visit(node.base)
            return
        if isinstance(node, (LiteralExpression, ReferenceExpression)):
            return

    visit(expression)
    return target_spans


def _lower_root_expression(
    *,
    expression: ExpressionNode,
    workflow_name: str,
    declared_return_type_name: str,
    declared_return_type_span: SourceSpan,
    definitions: dict[str, DefinitionNode],
    workflow_signatures: dict[str, WorkflowDefinition | ProcedureDefinition],
    workflow_input_names: frozenset[str],
    workflow_input_field_paths: Mapping[tuple[str, tuple[str, ...]], str],
    workflow_input_structured_names: frozenset[str],
    local_reference_bindings: dict[str, str] | None = None,
    generated_core_node_id: str | None = None,
) -> dict[str, Any]:
    node_id = generated_core_node_id or _result_node_id(workflow_name)
    if isinstance(expression, WithPhaseExpression):
        return _lower_root_expression(
            expression=expression.body,
            workflow_name=workflow_name,
            declared_return_type_name=declared_return_type_name,
            declared_return_type_span=declared_return_type_span,
            definitions=definitions,
            workflow_signatures=workflow_signatures,
            workflow_input_names=workflow_input_names,
            workflow_input_field_paths=workflow_input_field_paths,
            workflow_input_structured_names=workflow_input_structured_names,
            local_reference_bindings=local_reference_bindings,
            generated_core_node_id=node_id,
        )
    if isinstance(expression, ProviderResultExpression):
        return _lower_provider_result(
            expression=expression,
            workflow_name=workflow_name,
            declared_return_type_name=declared_return_type_name,
            declared_return_type_span=declared_return_type_span,
            definitions=definitions,
            workflow_input_names=workflow_input_names,
            workflow_input_field_paths=workflow_input_field_paths,
            workflow_input_structured_names=workflow_input_structured_names,
            local_reference_bindings=local_reference_bindings,
            generated_core_node_id=node_id,
        )
    if isinstance(expression, CommandResultExpression):
        return _lower_command_result(
            expression=expression,
            workflow_name=workflow_name,
            declared_return_type_name=declared_return_type_name,
            declared_return_type_span=declared_return_type_span,
            definitions=definitions,
            workflow_input_names=workflow_input_names,
            workflow_input_field_paths=workflow_input_field_paths,
            workflow_input_structured_names=workflow_input_structured_names,
            local_reference_bindings=local_reference_bindings,
            generated_core_node_id=node_id,
        )
    if isinstance(expression, CallExpression):
        return _lower_call_result(
            expression=expression,
            declared_return_type_name=declared_return_type_name,
            declared_return_type_span=declared_return_type_span,
            definitions=definitions,
            workflow_signatures=workflow_signatures,
            workflow_input_names=workflow_input_names,
            workflow_input_field_paths=workflow_input_field_paths,
            workflow_input_structured_names=workflow_input_structured_names,
            local_reference_bindings=local_reference_bindings,
            generated_core_node_id=node_id,
        )
    if isinstance(expression, RecordExpression):
        return _lower_record_result(
            expression=expression,
            declared_return_type_name=declared_return_type_name,
            declared_return_type_span=declared_return_type_span,
            definitions=definitions,
            workflow_input_names=workflow_input_names,
            workflow_input_field_paths=workflow_input_field_paths,
            local_reference_bindings=local_reference_bindings,
            generated_core_node_id=node_id,
        )
    if isinstance(expression, (LiteralExpression, ReferenceExpression, FieldAccessExpression, PhaseTargetExpression)):
        return _lower_scalar_result(
            expression=expression,
            declared_return_type_name=declared_return_type_name,
            declared_return_type_span=declared_return_type_span,
            definitions=definitions,
            workflow_input_names=workflow_input_names,
            workflow_input_field_paths=workflow_input_field_paths,
            workflow_input_structured_names=workflow_input_structured_names,
            local_reference_bindings=local_reference_bindings,
            generated_core_node_id=node_id,
        )
    _raise_lowering_error(
        code="frontend_lowering_error",
        message=(
            "MVP lowering currently supports only defworkflow bodies rooted at "
            "provider-result, command-result, call, record, or scalar expressions"
        ),
        span=expression.span,
        enclosing_form_name="defworkflow",
        generated_core_node_id=node_id,
    )


def _lower_root_match_expression(
    *,
    expression: MatchExpression,
    workflow_name: str,
    declared_return_type_name: str,
    declared_return_type_span: SourceSpan,
    definitions: dict[str, DefinitionNode],
    workflow_signatures: dict[str, WorkflowDefinition | ProcedureDefinition],
    workflow_input_names: frozenset[str],
    workflow_input_field_paths: Mapping[tuple[str, tuple[str, ...]], str],
    workflow_input_structured_names: frozenset[str],
) -> tuple[list[dict[str, Any]], str, dict[str, SourceSpan], list[tuple[str, str, ExpressionNode, dict[str, Any]]]]:
    subject_type_name, subject_type_span = _union_return_for_execution_expression(
        expression.subject,
        workflow_signatures=workflow_signatures,
        generated_core_node_id=_result_node_id(workflow_name),
    )
    subject_step = _lower_root_expression(
        expression=expression.subject,
        workflow_name=workflow_name,
        declared_return_type_name=subject_type_name,
        declared_return_type_span=subject_type_span,
        definitions=definitions,
        workflow_signatures=workflow_signatures,
        workflow_input_names=workflow_input_names,
        workflow_input_field_paths=workflow_input_field_paths,
        workflow_input_structured_names=workflow_input_structured_names,
    )
    subject_step_name = str(subject_step["name"])
    subject_union = definitions.get(subject_type_name)
    if not isinstance(subject_union, UnionDefinition):
        _raise_lowering_error(
            code="frontend_lowering_error",
            message=f"match subject must lower to a union return type; got {subject_type_name}",
            span=subject_type_span,
            enclosing_form_name="match",
            generated_core_node_id=_result_node_id(workflow_name),
        )

    cases: dict[str, Any] = {}
    case_steps: list[tuple[str, str, ExpressionNode, dict[str, Any]]] = []
    for arm in expression.arms:
        case_step = _lower_root_expression(
            expression=arm.body,
            workflow_name=workflow_name,
            declared_return_type_name=declared_return_type_name,
            declared_return_type_span=declared_return_type_span,
            definitions=definitions,
            workflow_signatures=workflow_signatures,
            workflow_input_names=workflow_input_names,
            workflow_input_field_paths=workflow_input_field_paths,
            workflow_input_structured_names=workflow_input_structured_names,
            local_reference_bindings={
                arm.binding_name: f"parent.steps.{subject_step_name}.artifacts"
            },
            generated_core_node_id=_match_case_result_node_id(
                workflow_name=workflow_name,
                match_step_name="MatchResult",
                case_variant_name=arm.variant_name,
            ),
        )
        case_step_name = str(case_step["name"])
        case_steps.append((arm.variant_name, case_step_name, arm.body, case_step))
        cases[arm.variant_name] = {
            "id": f"{arm.variant_name.lower()}_path",
            "outputs": _match_case_outputs_for_structured_return(
                type_name=declared_return_type_name,
                type_span=declared_return_type_span,
                definitions=definitions,
                case_step_name=case_step_name,
            ),
            "steps": [case_step],
        }

    if expression.partial:
        expected_variants = {variant.name for variant in subject_union.variants}
        lowered_variants = {arm.variant_name for arm in expression.arms}
        for missing_variant_name in sorted(expected_variants - lowered_variants):
            case_step = _lower_partial_unhandled_variant_case_step(
                workflow_name=workflow_name,
                variant_name=missing_variant_name,
                declared_return_type_name=declared_return_type_name,
                declared_return_type_span=declared_return_type_span,
                definitions=definitions,
            )
            case_step_name = str(case_step["name"])
            cases[missing_variant_name] = {
                "id": f"{missing_variant_name.lower()}_path",
                "outputs": _match_case_outputs_for_structured_return(
                    type_name=declared_return_type_name,
                    type_span=declared_return_type_span,
                    definitions=definitions,
                    case_step_name=case_step_name,
                ),
                "steps": [case_step],
            }

    match_step_name = "MatchResult"
    return [
        subject_step,
        {
            "name": match_step_name,
            "match": {
                "ref": (
                    f"root.steps.{subject_step_name}.artifacts."
                    f"{_snake_case(subject_union.name)}_variant"
                ),
                "cases": cases,
            },
        },
    ], match_step_name, {
        subject_step_name: expression.subject.span,
        match_step_name: expression.span,
    }, case_steps


def _lower_partial_unhandled_variant_case_step(
    *,
    workflow_name: str,
    variant_name: str,
    declared_return_type_name: str,
    declared_return_type_span: SourceSpan,
    definitions: dict[str, DefinitionNode],
) -> dict[str, Any]:
    variant_token = variant_name.lower()
    step_suffix = "".join(
        segment.capitalize()
        for segment in variant_token.split("_")
        if segment
    )
    if not step_suffix:
        step_suffix = "Variant"
    lowered: dict[str, Any] = {
        "name": f"UnhandledPartial{step_suffix}",
        "command": ["python", "-c", "import sys; sys.exit(66)"],
    }
    lowered.update(
        _output_contract_for_structured_return(
            type_name=declared_return_type_name,
            type_span=declared_return_type_span,
            definitions=definitions,
            path=f"state/{workflow_name}_partial_{variant_token}_unhandled.json",
            enclosing_form_name="match",
            generated_core_node_id=_match_case_result_node_id(
                workflow_name=workflow_name,
                match_step_name="MatchResult",
                case_variant_name=variant_name,
            ),
        )
    )
    return lowered


def _union_return_for_execution_expression(
    expression: ExpressionNode,
    *,
    workflow_signatures: dict[str, WorkflowDefinition | ProcedureDefinition],
    generated_core_node_id: str | None = None,
) -> tuple[str, SourceSpan]:
    if isinstance(expression, WithPhaseExpression):
        return _union_return_for_execution_expression(
            expression.body,
            workflow_signatures=workflow_signatures,
            generated_core_node_id=generated_core_node_id,
        )
    if isinstance(expression, (ProviderResultExpression, CommandResultExpression)):
        return expression.returns_type_name, expression.returns_type_span
    if isinstance(expression, CallExpression):
        callee_signature = workflow_signatures.get(expression.callee_name)
        if callee_signature is not None:
            return callee_signature.return_type.name, callee_signature.return_type.span
        if expression.returns_type_name is not None and expression.returns_type_span is not None:
            return expression.returns_type_name, expression.returns_type_span
        _raise_lowering_error(
            code="frontend_lowering_error",
            message=f"Unknown callee callable during lowering: {expression.callee_name}",
            span=expression.callee_span,
            enclosing_form_name="call",
            generated_core_node_id=generated_core_node_id,
        )
    _raise_lowering_error(
        code="frontend_lowering_error",
        message=(
            "MVP lowering match subjects must be execution expressions rooted at "
            "provider-result, command-result, or call"
        ),
        span=expression.span,
        enclosing_form_name="match",
        generated_core_node_id=generated_core_node_id,
    )


def _match_case_outputs_for_structured_return(
    *,
    type_name: str,
    type_span: SourceSpan,
    definitions: dict[str, DefinitionNode],
    case_step_name: str,
) -> dict[str, Any]:
    definition = definitions.get(type_name)
    if isinstance(definition, RecordDefinition):
        outputs: dict[str, Any] = {}
        for field in _flatten_record_leaf_fields(
            record_definition=definition,
            definitions=definitions,
        ):
            contract = _bundle_field_contract_for_type(field.type_name, field.type_span, definitions)
            contract = _output_contract_from_bundle_contract(contract)
            contract["from"] = {
                "ref": f"self.steps.{case_step_name}.artifacts.{field.flattened_name}"
            }
            outputs[field.flattened_name] = contract
        return outputs

    if isinstance(definition, UnionDefinition):
        discriminant_name = f"{_snake_case(definition.name)}_variant"
        return {
            discriminant_name: {
                "kind": "scalar",
                "type": "enum",
                "allowed": [variant.name for variant in definition.variants],
                "from": {"ref": f"self.steps.{case_step_name}.artifacts.{discriminant_name}"},
            }
        }

    contract = _output_contract_from_bundle_contract(
        _bundle_field_contract_for_type(type_name, type_span, definitions)
    )
    contract["from"] = {"ref": f"self.steps.{case_step_name}.artifacts.result"}
    return {"result": contract}


def _inline_root_expression(
    expression: ExpressionNode,
    *,
    function_definitions: Mapping[str, FunctionDefinition],
) -> ExpressionNode:
    inlined = _inline_expression(
        expression,
        {},
        None,
        function_definitions=function_definitions,
        inline_stack=(),
    )
    while isinstance(inlined, WithPhaseExpression):
        inlined = inlined.body
    return inlined


def _inline_expression(
    expression: ExpressionNode,
    env: dict[str, ExpressionNode],
    current_phase_name: str | None,
    *,
    function_definitions: Mapping[str, FunctionDefinition],
    inline_stack: tuple[str, ...],
) -> ExpressionNode:
    if isinstance(expression, ReferenceExpression):
        resolved = env.get(expression.name)
        if resolved is None:
            return expression
        if isinstance(resolved, ReferenceExpression) and resolved.name == expression.name:
            return resolved
        return _inline_expression(
            resolved,
            env,
            current_phase_name,
            function_definitions=function_definitions,
            inline_stack=inline_stack,
        )

    if isinstance(expression, LetStarExpression):
        local_env = dict(env)
        for binding in expression.bindings:
            local_env[binding.name] = _inline_expression(
                binding.value,
                local_env,
                current_phase_name,
                function_definitions=function_definitions,
                inline_stack=inline_stack,
            )
        return _inline_expression(
            expression.body,
            local_env,
            current_phase_name,
            function_definitions=function_definitions,
            inline_stack=inline_stack,
        )

    if isinstance(expression, WithPhaseExpression):
        return WithPhaseExpression(
            context=_inline_expression(
                expression.context,
                env,
                current_phase_name,
                function_definitions=function_definitions,
                inline_stack=inline_stack,
            ),
            phase_name=expression.phase_name,
            phase_span=expression.phase_span,
            body=_inline_expression(
                expression.body,
                env,
                expression.phase_name,
                function_definitions=function_definitions,
                inline_stack=inline_stack,
            ),
            span=expression.span,
        )

    if isinstance(expression, PhaseTargetExpression):
        return PhaseTargetExpression(
            context=_inline_expression(
                expression.context,
                env,
                current_phase_name,
                function_definitions=function_definitions,
                inline_stack=inline_stack,
            ),
            target_name=expression.target_name,
            target_span=expression.target_span,
            phase_name=expression.phase_name or current_phase_name,
            span=expression.span,
        )

    if isinstance(expression, ProviderResultExpression):
        provider_reference = _inline_reference_expression(
            _inline_expression(
                expression.provider_reference,
                env,
                current_phase_name,
                function_definitions=function_definitions,
                inline_stack=inline_stack,
            ),
            form_name="provider-result",
            role="provider",
        )
        prompt_reference = _inline_reference_expression(
            _inline_expression(
                expression.prompt_reference,
                env,
                current_phase_name,
                function_definitions=function_definitions,
                inline_stack=inline_stack,
            ),
            form_name="provider-result",
            role=":prompt",
        )
        return ProviderResultExpression(
            provider_reference=provider_reference,
            prompt_reference=prompt_reference,
            inputs=tuple(
                _inline_expression(
                    item,
                    env,
                    current_phase_name,
                    function_definitions=function_definitions,
                    inline_stack=inline_stack,
                )
                for item in expression.inputs
            ),
            returns_type_name=expression.returns_type_name,
            returns_type_span=expression.returns_type_span,
            span=expression.span,
        )

    if isinstance(expression, CommandResultExpression):
        return CommandResultExpression(
            command_name=expression.command_name,
            command_name_span=expression.command_name_span,
            argv=tuple(
                _inline_expression(
                    item,
                    env,
                    current_phase_name,
                    function_definitions=function_definitions,
                    inline_stack=inline_stack,
                )
                for item in expression.argv
            ),
            returns_type_name=expression.returns_type_name,
            returns_type_span=expression.returns_type_span,
            span=expression.span,
        )

    if isinstance(expression, CallExpression):
        function_definition = function_definitions.get(expression.callee_name)
        if function_definition is not None:
            if expression.callee_name in inline_stack:
                _raise_lowering_error(
                    code="frontend_lowering_error",
                    message=f"Recursive defun call cannot be lowered: {expression.callee_name}",
                    span=expression.callee_span,
                    enclosing_form_name="call",
                )
            arguments_by_name = {argument.parameter_name: argument for argument in expression.arguments}
            expected_parameters = tuple(parameter.name for parameter in function_definition.parameters)
            provided_names = frozenset(arguments_by_name)
            expected_names = frozenset(expected_parameters)
            missing_names = sorted(expected_names - provided_names)
            if missing_names:
                _raise_lowering_error(
                    code="frontend_lowering_error",
                    message=(
                        f"Missing call argument for function {function_definition.name}: "
                        f"{missing_names[0]}"
                    ),
                    span=expression.span,
                    enclosing_form_name="call",
                )
            unexpected_names = sorted(provided_names - expected_names)
            if unexpected_names:
                _raise_lowering_error(
                    code="frontend_lowering_error",
                    message=(
                        f"Unknown call argument for function {function_definition.name}: "
                        f"{unexpected_names[0]}"
                    ),
                    span=expression.span,
                    enclosing_form_name="call",
                )
            function_env = dict(env)
            for parameter in function_definition.parameters:
                argument = arguments_by_name[parameter.name]
                function_env[parameter.name] = _inline_expression(
                    argument.value,
                    env,
                    current_phase_name,
                    function_definitions=function_definitions,
                    inline_stack=inline_stack,
                )
            if len(function_definition.body_forms) != 1:
                _raise_lowering_error(
                    code="frontend_lowering_error",
                    message=(
                        f"defun {function_definition.name} must have exactly one body expression "
                        "for lowering"
                    ),
                    span=function_definition.form_span,
                    enclosing_form_name="defun",
                )
            return _inline_expression(
                shape_expression(function_definition.body_forms[0]),
                function_env,
                current_phase_name,
                function_definitions=function_definitions,
                inline_stack=(*inline_stack, function_definition.name),
            )
        return CallExpression(
            callee_name=expression.callee_name,
            callee_span=expression.callee_span,
            arguments=tuple(
                argument.__class__(
                    parameter_name=argument.parameter_name,
                    keyword_span=argument.keyword_span,
                    value=_inline_expression(
                        argument.value,
                        env,
                        current_phase_name,
                        function_definitions=function_definitions,
                        inline_stack=inline_stack,
                    ),
                    form_span=argument.form_span,
                )
                for argument in expression.arguments
            ),
            returns_type_name=expression.returns_type_name,
            returns_type_span=expression.returns_type_span,
            span=expression.span,
        )

    if isinstance(expression, FieldAccessExpression):
        return FieldAccessExpression(
            base=_inline_expression(
                expression.base,
                env,
                current_phase_name,
                function_definitions=function_definitions,
                inline_stack=inline_stack,
            ),
            field_name=expression.field_name,
            span=expression.span,
        )

    if isinstance(expression, RecordExpression):
        return RecordExpression(
            type_name=expression.type_name,
            type_span=expression.type_span,
            fields=tuple(
                field.__class__(
                    field_name=field.field_name,
                    field_span=field.field_span,
                    value=_inline_expression(
                        field.value,
                        env,
                        current_phase_name,
                        function_definitions=function_definitions,
                        inline_stack=inline_stack,
                    ),
                    form_span=field.form_span,
                )
                for field in expression.fields
            ),
            span=expression.span,
        )

    if isinstance(expression, MatchExpression):
        inlined_arms = []
        for arm in expression.arms:
            arm_env = dict(env)
            arm_env.pop(arm.binding_name, None)
            inlined_arms.append(
                arm.__class__(
                    variant_name=arm.variant_name,
                    variant_span=arm.variant_span,
                    binding_name=arm.binding_name,
                    binding_span=arm.binding_span,
                    body=_inline_expression(
                        arm.body,
                        arm_env,
                        current_phase_name,
                        function_definitions=function_definitions,
                        inline_stack=inline_stack,
                    ),
                    span=arm.span,
                )
            )
        return MatchExpression(
            subject=_inline_expression(
                expression.subject,
                env,
                current_phase_name,
                function_definitions=function_definitions,
                inline_stack=inline_stack,
            ),
            arms=tuple(inlined_arms),
            partial=expression.partial,
            span=expression.span,
        )

    return expression


def _inline_reference_expression(expression: ExpressionNode, *, form_name: str, role: str) -> ReferenceExpression:
    if isinstance(expression, ReferenceExpression):
        return expression
    _raise_lowering_error(
        code="frontend_lowering_error",
        message=f"{form_name} {role} value must lower to a reference",
        span=expression.span,
        enclosing_form_name=form_name,
    )


def _lower_provider_result(
    *,
    expression: ProviderResultExpression,
    workflow_name: str,
    declared_return_type_name: str,
    declared_return_type_span: SourceSpan,
    definitions: dict[str, DefinitionNode],
    workflow_input_names: frozenset[str],
    workflow_input_field_paths: Mapping[tuple[str, tuple[str, ...]], str],
    workflow_input_structured_names: frozenset[str],
    local_reference_bindings: dict[str, str] | None = None,
    generated_core_node_id: str | None = None,
) -> dict[str, Any]:
    _assert_declared_and_expression_return_match(
        declared_return_type_name=declared_return_type_name,
        declared_return_type_span=declared_return_type_span,
        expression_return_type_name=expression.returns_type_name,
        expression_return_type_span=expression.returns_type_span,
        enclosing_form_name="provider-result",
    )
    provider_inputs = [
        _lower_scalar_expression(
            item,
            workflow_input_names=workflow_input_names,
            workflow_input_field_paths=workflow_input_field_paths,
            workflow_input_structured_names=workflow_input_structured_names,
            local_reference_bindings=local_reference_bindings,
            generated_core_node_id=generated_core_node_id,
        )
        for item in expression.inputs
    ]
    output_contract = _output_contract_for_structured_return(
        type_name=expression.returns_type_name,
        type_span=expression.returns_type_span,
        definitions=definitions,
        path=f"state/{workflow_name}_result.json",
        enclosing_form_name="provider-result",
        generated_core_node_id=generated_core_node_id,
    )
    lowered: dict[str, Any] = {
        "name": "ProviderResult",
        "provider": _reference_to_input_substitution(expression.provider_reference),
        "input_file": _reference_to_input_substitution(expression.prompt_reference),
        "provider_params": {
            "workflow_lisp_inputs": provider_inputs,
        },
    }
    lowered.update(output_contract)
    return lowered


def _lower_command_result(
    *,
    expression: CommandResultExpression,
    workflow_name: str,
    declared_return_type_name: str,
    declared_return_type_span: SourceSpan,
    definitions: dict[str, DefinitionNode],
    workflow_input_names: frozenset[str],
    workflow_input_field_paths: Mapping[tuple[str, tuple[str, ...]], str],
    workflow_input_structured_names: frozenset[str],
    local_reference_bindings: dict[str, str] | None = None,
    generated_core_node_id: str | None = None,
) -> dict[str, Any]:
    _assert_declared_and_expression_return_match(
        declared_return_type_name=declared_return_type_name,
        declared_return_type_span=declared_return_type_span,
        expression_return_type_name=expression.returns_type_name,
        expression_return_type_span=expression.returns_type_span,
        enclosing_form_name="command-result",
    )
    output_contract = _output_contract_for_structured_return(
        type_name=expression.returns_type_name,
        type_span=expression.returns_type_span,
        definitions=definitions,
        path=f"state/{workflow_name}_result.json",
        enclosing_form_name="command-result",
        generated_core_node_id=generated_core_node_id,
    )
    command = [
        _lower_scalar_expression(
            item,
            workflow_input_names=workflow_input_names,
            workflow_input_field_paths=workflow_input_field_paths,
            workflow_input_structured_names=workflow_input_structured_names,
            local_reference_bindings=local_reference_bindings,
            generated_core_node_id=generated_core_node_id,
        )
        for item in expression.argv
    ]
    lowered: dict[str, Any] = {
        "name": "CommandResult",
        "command": command,
    }
    lowered.update(output_contract)
    return lowered


def _lower_call_result(
    *,
    expression: CallExpression,
    declared_return_type_name: str,
    declared_return_type_span: SourceSpan,
    definitions: dict[str, DefinitionNode],
    workflow_signatures: dict[str, WorkflowDefinition | ProcedureDefinition],
    workflow_input_names: frozenset[str],
    workflow_input_field_paths: Mapping[tuple[str, tuple[str, ...]], str],
    workflow_input_structured_names: frozenset[str],
    local_reference_bindings: dict[str, str] | None = None,
    generated_core_node_id: str | None = None,
) -> dict[str, Any]:
    callee_signature = workflow_signatures.get(expression.callee_name)
    if callee_signature is None:
        if expression.returns_type_name is None or expression.returns_type_span is None:
            _raise_lowering_error(
                code="frontend_lowering_error",
                message=f"Unknown callee callable during lowering: {expression.callee_name}",
                span=expression.callee_span,
                enclosing_form_name="call",
                generated_core_node_id=generated_core_node_id,
            )
        _assert_declared_and_expression_return_match(
            declared_return_type_name=declared_return_type_name,
            declared_return_type_span=declared_return_type_span,
            expression_return_type_name=expression.returns_type_name,
            expression_return_type_span=expression.returns_type_span,
            enclosing_form_name="call",
        )
        imported_bindings = {
            argument.parameter_name: _lower_call_binding_value(
                argument.value,
                workflow_input_names=workflow_input_names,
                workflow_input_field_paths=workflow_input_field_paths,
                workflow_input_structured_names=workflow_input_structured_names,
                local_reference_bindings=local_reference_bindings,
                generated_core_node_id=generated_core_node_id,
            )
            for argument in expression.arguments
        }
        return {
            "name": "CallResult",
            "id": "call_result",
            "call": expression.callee_name,
            "with": imported_bindings,
        }
    _assert_declared_and_expression_return_match(
        declared_return_type_name=declared_return_type_name,
        declared_return_type_span=declared_return_type_span,
        expression_return_type_name=callee_signature.return_type.name,
        expression_return_type_span=callee_signature.return_type.span,
        enclosing_form_name="call",
    )
    bindings: dict[str, Any] = {}
    expected_parameters = {parameter.name: parameter for parameter in callee_signature.parameters}
    for argument in expression.arguments:
        parameter = expected_parameters.get(argument.parameter_name)
        if parameter is None:
            _raise_lowering_error(
                code="frontend_lowering_error",
                message=(
                    f"Missing parameter metadata for lowered call argument "
                    f"{argument.parameter_name} on callable {callee_signature.name}"
                ),
                span=argument.form_span,
                enclosing_form_name="call",
                generated_core_node_id=generated_core_node_id,
            )
        bindings.update(
            _lower_call_binding_entries(
                parameter=parameter,
                expression=argument.value,
                definitions=definitions,
                workflow_input_names=workflow_input_names,
                workflow_input_field_paths=workflow_input_field_paths,
                workflow_input_structured_names=workflow_input_structured_names,
                local_reference_bindings=local_reference_bindings,
                generated_core_node_id=generated_core_node_id,
            )
        )

    return {
        "name": "CallResult",
        "id": "call_result",
        "call": expression.callee_name,
        "with": bindings,
    }


def _lower_call_binding_entries(
    *,
    parameter: WorkflowParameter,
    expression: ExpressionNode,
    definitions: dict[str, DefinitionNode],
    workflow_input_names: frozenset[str],
    workflow_input_field_paths: Mapping[tuple[str, tuple[str, ...]], str],
    workflow_input_structured_names: frozenset[str],
    local_reference_bindings: dict[str, str] | None = None,
    generated_core_node_id: str | None = None,
) -> dict[str, Any]:
    definition = definitions.get(parameter.type_ref.name)
    if isinstance(definition, RecordDefinition):
        expanded = _lower_record_parameter_call_binding_entries(
            parameter=parameter,
            expression=expression,
            record_definition=definition,
            definitions=definitions,
            workflow_input_names=workflow_input_names,
            workflow_input_field_paths=workflow_input_field_paths,
            workflow_input_structured_names=workflow_input_structured_names,
            local_reference_bindings=local_reference_bindings,
            generated_core_node_id=generated_core_node_id,
        )
        if expanded is not None:
            return expanded
    return {
        parameter.name: _lower_call_binding_value(
            expression,
            workflow_input_names=workflow_input_names,
            workflow_input_field_paths=workflow_input_field_paths,
            workflow_input_structured_names=workflow_input_structured_names,
            local_reference_bindings=local_reference_bindings,
            generated_core_node_id=generated_core_node_id,
        )
    }


def _lower_record_result(
    *,
    expression: RecordExpression,
    declared_return_type_name: str,
    declared_return_type_span: SourceSpan,
    definitions: dict[str, DefinitionNode],
    workflow_input_names: frozenset[str],
    workflow_input_field_paths: Mapping[tuple[str, tuple[str, ...]], str],
    local_reference_bindings: dict[str, str] | None = None,
    generated_core_node_id: str | None = None,
) -> dict[str, Any]:
    _assert_declared_and_expression_return_match(
        declared_return_type_name=declared_return_type_name,
        declared_return_type_span=declared_return_type_span,
        expression_return_type_name=expression.type_name,
        expression_return_type_span=expression.type_span,
        enclosing_form_name="record",
    )
    definition = definitions.get(expression.type_name)
    if not isinstance(definition, RecordDefinition):
        _raise_lowering_error(
            code="frontend_lowering_error",
            message=f"record return type must resolve to a record for lowering: {expression.type_name}",
            span=expression.type_span,
            enclosing_form_name="record",
            generated_core_node_id=generated_core_node_id,
        )

    field_values = {field.field_name: field for field in expression.fields}
    values: list[dict[str, Any]] = []
    for field in definition.fields:
        value_expression = field_values.get(field.name)
        if value_expression is None:
            _raise_lowering_error(
                code="frontend_lowering_error",
                message=f"record expression is missing field during lowering: {field.name}",
                span=expression.span,
                enclosing_form_name="record",
                generated_core_node_id=generated_core_node_id,
            )
        source, contract = _lower_record_field_value_source(
            field_name=field.name,
            field_type_name=field.type_ref.name,
            field_type_span=field.type_ref.span,
            value_expression=value_expression.value,
            definitions=definitions,
            workflow_input_names=workflow_input_names,
            workflow_input_field_paths=workflow_input_field_paths,
            local_reference_bindings=local_reference_bindings,
            generated_core_node_id=generated_core_node_id,
        )
        values.append(
            {
                "name": field.name,
                "source": source,
                "contract": contract,
            }
        )

    return {
        "name": "RecordResult",
        "id": "record_result",
        "materialize_artifacts": {
            "values": values,
        },
    }


def _lower_scalar_result(
    *,
    expression: LiteralExpression | ReferenceExpression | FieldAccessExpression | PhaseTargetExpression,
    declared_return_type_name: str,
    declared_return_type_span: SourceSpan,
    definitions: dict[str, DefinitionNode],
    workflow_input_names: frozenset[str],
    workflow_input_field_paths: Mapping[tuple[str, tuple[str, ...]], str],
    workflow_input_structured_names: frozenset[str],
    local_reference_bindings: dict[str, str] | None = None,
    generated_core_node_id: str | None = None,
) -> dict[str, Any]:
    return_contract = _bundle_field_contract_for_type(
        declared_return_type_name,
        declared_return_type_span,
        definitions,
    )
    source, contract = _lower_scalar_result_source(
        expression=expression,
        return_contract=return_contract,
        workflow_input_names=workflow_input_names,
        workflow_input_field_paths=workflow_input_field_paths,
        workflow_input_structured_names=workflow_input_structured_names,
        local_reference_bindings=local_reference_bindings,
        generated_core_node_id=generated_core_node_id,
    )
    return {
        "name": "ScalarResult",
        "id": "scalar_result",
        "materialize_artifacts": {
            "values": [
                {
                    "name": "result",
                    "source": source,
                    "contract": contract,
                }
            ]
        },
    }


def _lower_scalar_result_source(
    *,
    expression: LiteralExpression | ReferenceExpression | FieldAccessExpression | PhaseTargetExpression,
    return_contract: dict[str, Any],
    workflow_input_names: frozenset[str],
    workflow_input_field_paths: Mapping[tuple[str, tuple[str, ...]], str],
    workflow_input_structured_names: frozenset[str],
    local_reference_bindings: dict[str, str] | None,
    generated_core_node_id: str | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if isinstance(expression, LiteralExpression):
        return {"literal": expression.value}, return_contract

    if isinstance(expression, ReferenceExpression):
        if expression.name in workflow_input_structured_names:
            _raise_lowering_error(
                code="frontend_lowering_error",
                message=(
                    f"Structured workflow input {expression.name} cannot be lowered as one scalar value; "
                    "reference a field such as "
                    f"{expression.name}.field_name"
                ),
                span=expression.span,
                enclosing_form_name="defworkflow",
                generated_core_node_id=generated_core_node_id,
            )
        if expression.name in workflow_input_names:
            return {"input": expression.name}, {"inherit": "source"}
        _raise_lowering_error(
            code="frontend_lowering_error",
            message=(
                "Scalar-root reference expressions must resolve to one workflow input in MVP lowering; "
                f"got {expression.name}"
            ),
            span=expression.span,
            enclosing_form_name="defworkflow",
            generated_core_node_id=generated_core_node_id,
        )

    if isinstance(expression, FieldAccessExpression):
        reference_path = _lower_field_access_reference_path(
            expression,
            workflow_input_field_paths=workflow_input_field_paths,
            local_reference_bindings=local_reference_bindings,
        )
        if reference_path is not None:
            return {"ref": reference_path}, {"inherit": "source"}
    if isinstance(expression, PhaseTargetExpression):
        return (
            {
                "literal": _lower_phase_target_expression(
                    expression,
                    workflow_input_names=workflow_input_names,
                    workflow_input_field_paths=workflow_input_field_paths,
                    workflow_input_structured_names=workflow_input_structured_names,
                    local_reference_bindings=local_reference_bindings,
                    generated_core_node_id=generated_core_node_id,
                )
            },
            return_contract,
        )
    _raise_lowering_error(
        code="frontend_lowering_error",
        message=(
            "Scalar-root field references must resolve to workflow inputs or match-proved "
            f"variant fields in MVP lowering"
        ),
        span=expression.span,
        enclosing_form_name="defworkflow",
        generated_core_node_id=generated_core_node_id,
    )


def _lower_record_field_value_source(
    *,
    field_name: str,
    field_type_name: str,
    field_type_span: SourceSpan,
    value_expression: ExpressionNode,
    definitions: dict[str, DefinitionNode],
    workflow_input_names: frozenset[str],
    workflow_input_field_paths: Mapping[tuple[str, tuple[str, ...]], str],
    local_reference_bindings: dict[str, str] | None = None,
    generated_core_node_id: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if isinstance(value_expression, LiteralExpression):
        return (
            {"literal": value_expression.value},
            _bundle_field_contract_for_type(
                field_type_name,
                field_type_span,
                definitions,
            ),
        )

    if isinstance(value_expression, ReferenceExpression):
        if value_expression.name in workflow_input_names:
            return ({"input": value_expression.name}, {"inherit": "source"})
        _raise_lowering_error(
            code="frontend_lowering_error",
            message=(
                f"record field {field_name} reference {value_expression.name} is not a workflow input and "
                "cannot lower to materialize source in MVP"
            ),
            span=value_expression.span,
            enclosing_form_name="record",
            generated_core_node_id=generated_core_node_id,
        )

    if isinstance(value_expression, FieldAccessExpression):
        reference_path = _lower_field_access_reference_path(
            value_expression,
            workflow_input_field_paths=workflow_input_field_paths,
            local_reference_bindings=local_reference_bindings,
        )
        if reference_path is not None:
            return ({"ref": reference_path}, {"inherit": "source"})

    if isinstance(value_expression, PhaseTargetExpression):
        return (
            {
                "literal": _lower_phase_target_expression(
                    value_expression,
                    workflow_input_names=workflow_input_names,
                    workflow_input_field_paths=workflow_input_field_paths,
                    workflow_input_structured_names=frozenset(),
                    local_reference_bindings=local_reference_bindings,
                    generated_core_node_id=generated_core_node_id,
                )
            },
            _bundle_field_contract_for_type(
                field_type_name,
                field_type_span,
                definitions,
            ),
        )

    _raise_lowering_error(
        code="frontend_lowering_error",
        message=(
            f"record field {field_name} lowering supports only literals, workflow-input references, "
            "and match-proved variant field references in MVP"
        ),
        span=value_expression.span,
        enclosing_form_name="record",
        generated_core_node_id=generated_core_node_id,
    )


def _assert_declared_and_expression_return_match(
    *,
    declared_return_type_name: str,
    declared_return_type_span: SourceSpan,
    expression_return_type_name: str,
    expression_return_type_span: SourceSpan,
    enclosing_form_name: str,
) -> None:
    if declared_return_type_name == expression_return_type_name:
        return
    _raise_lowering_error(
        code="frontend_lowering_error",
        message=(
            f"{enclosing_form_name} :returns type {expression_return_type_name} "
            f"does not match defworkflow return type {declared_return_type_name}"
        ),
        span=expression_return_type_span,
        enclosing_form_name="defworkflow",
    )


def _lower_call_binding_value(
    expression: ExpressionNode,
    *,
    workflow_input_names: frozenset[str],
    workflow_input_field_paths: Mapping[tuple[str, tuple[str, ...]], str],
    workflow_input_structured_names: frozenset[str],
    local_reference_bindings: dict[str, str] | None = None,
    generated_core_node_id: str | None = None,
) -> Any:
    if isinstance(expression, ReferenceExpression):
        if expression.name in workflow_input_structured_names:
            _raise_lowering_error(
                code="frontend_lowering_error",
                message=(
                    f"Call binding references structured workflow input {expression.name}; "
                    "bind concrete fields instead"
                ),
                span=expression.span,
                enclosing_form_name="call",
                generated_core_node_id=generated_core_node_id,
            )
        return {"ref": f"inputs.{expression.name}"}
    if isinstance(expression, FieldAccessExpression):
        reference_path = _lower_field_access_reference_path(
            expression,
            workflow_input_field_paths=workflow_input_field_paths,
            local_reference_bindings=local_reference_bindings,
        )
        if reference_path is not None:
            return {"ref": reference_path}
    if isinstance(expression, LiteralExpression):
        return expression.value
    if isinstance(expression, PhaseTargetExpression):
        return _lower_phase_target_expression(
            expression,
            workflow_input_names=workflow_input_names,
            workflow_input_field_paths=workflow_input_field_paths,
            workflow_input_structured_names=workflow_input_structured_names,
            local_reference_bindings=local_reference_bindings,
            generated_core_node_id=generated_core_node_id,
        )
    _raise_lowering_error(
        code="frontend_lowering_error",
        message=(
            "MVP lowering call arguments currently support only references, literals, "
            "and match-proved variant field references"
        ),
        span=expression.span,
        enclosing_form_name="call",
        generated_core_node_id=generated_core_node_id,
    )


def _lower_record_parameter_call_binding_entries(
    *,
    parameter: WorkflowParameter,
    expression: ExpressionNode,
    record_definition: RecordDefinition,
    definitions: dict[str, DefinitionNode],
    workflow_input_names: frozenset[str],
    workflow_input_field_paths: Mapping[tuple[str, tuple[str, ...]], str],
    workflow_input_structured_names: frozenset[str],
    local_reference_bindings: dict[str, str] | None,
    generated_core_node_id: str | None,
) -> dict[str, Any] | None:
    if not isinstance(expression, ReferenceExpression):
        if not isinstance(expression, RecordExpression):
            return None
        if expression.type_name != record_definition.name:
            _raise_lowering_error(
                code="frontend_lowering_error",
                message=(
                    f"Call argument {parameter.name} record literal type {expression.type_name} "
                    f"does not match parameter type {record_definition.name}"
                ),
                span=expression.type_span,
                enclosing_form_name="call",
                generated_core_node_id=generated_core_node_id,
            )
    else:
        if expression.name not in workflow_input_structured_names:
            return None

    callee_field_paths = _record_parameter_field_paths(
        parameter_name=parameter.name,
        record_definition=record_definition,
        definitions=definitions,
    )
    if not callee_field_paths:
        return None

    if isinstance(expression, RecordExpression):
        return _lower_record_literal_parameter_call_binding_entries(
            parameter=parameter,
            expression=expression,
            record_definition=record_definition,
            definitions=definitions,
            callee_field_paths=callee_field_paths,
            workflow_input_names=workflow_input_names,
            workflow_input_field_paths=workflow_input_field_paths,
            workflow_input_structured_names=workflow_input_structured_names,
            local_reference_bindings=local_reference_bindings,
            generated_core_node_id=generated_core_node_id,
        )

    bindings: dict[str, Any] = {}
    for field_path, callee_flattened_name in callee_field_paths.items():
        caller_flattened_name = workflow_input_field_paths.get((expression.name, field_path))
        if caller_flattened_name is None:
            dotted = ".".join(field_path)
            _raise_lowering_error(
                code="frontend_lowering_error",
                message=(
                    f"Structured call binding for {parameter.name} cannot resolve field {expression.name}.{dotted} "
                    "from caller inputs"
                ),
                span=expression.span,
                enclosing_form_name="call",
                generated_core_node_id=generated_core_node_id,
            )
        bindings[callee_flattened_name] = {"ref": f"inputs.{caller_flattened_name}"}
    return bindings


def _lower_record_literal_parameter_call_binding_entries(
    *,
    parameter: WorkflowParameter,
    expression: RecordExpression,
    record_definition: RecordDefinition,
    definitions: dict[str, DefinitionNode],
    callee_field_paths: Mapping[tuple[str, ...], str],
    workflow_input_names: frozenset[str],
    workflow_input_field_paths: Mapping[tuple[str, tuple[str, ...]], str],
    workflow_input_structured_names: frozenset[str],
    local_reference_bindings: dict[str, str] | None,
    generated_core_node_id: str | None,
) -> dict[str, Any]:
    literal_fields = {field.field_name: field for field in expression.fields}
    lowered_bindings: dict[str, Any] = {}
    for field in record_definition.fields:
        field_expression = literal_fields.get(field.name)
        if field_expression is None:
            _raise_lowering_error(
                code="frontend_lowering_error",
                message=f"Record call argument {parameter.name} is missing field {field.name}",
                span=expression.span,
                enclosing_form_name="call",
                generated_core_node_id=generated_core_node_id,
            )
        _lower_record_literal_call_binding_field(
            parameter=parameter,
            path=(field.name,),
            value_expression=field_expression.value,
            field_type_name=field.type_ref.name,
            field_type_span=field.type_ref.span,
            definitions=definitions,
            callee_field_paths=callee_field_paths,
            workflow_input_names=workflow_input_names,
            workflow_input_field_paths=workflow_input_field_paths,
            workflow_input_structured_names=workflow_input_structured_names,
            local_reference_bindings=local_reference_bindings,
            generated_core_node_id=generated_core_node_id,
            lowered_bindings=lowered_bindings,
        )
    return lowered_bindings


def _lower_record_literal_call_binding_field(
    *,
    parameter: WorkflowParameter,
    path: tuple[str, ...],
    value_expression: ExpressionNode,
    field_type_name: str,
    field_type_span: SourceSpan,
    definitions: dict[str, DefinitionNode],
    callee_field_paths: Mapping[tuple[str, ...], str],
    workflow_input_names: frozenset[str],
    workflow_input_field_paths: Mapping[tuple[str, tuple[str, ...]], str],
    workflow_input_structured_names: frozenset[str],
    local_reference_bindings: dict[str, str] | None,
    generated_core_node_id: str | None,
    lowered_bindings: dict[str, Any],
) -> None:
    nested_definition = definitions.get(field_type_name)
    if isinstance(nested_definition, RecordDefinition):
        if not isinstance(value_expression, RecordExpression):
            _raise_lowering_error(
                code="frontend_lowering_error",
                message=(
                    f"Record call argument {parameter.name}.{'.'.join(path)} must be a "
                    f"record expression of type {field_type_name}"
                ),
                span=value_expression.span,
                enclosing_form_name="call",
                generated_core_node_id=generated_core_node_id,
            )
        if value_expression.type_name != field_type_name:
            _raise_lowering_error(
                code="frontend_lowering_error",
                message=(
                    f"Record call argument {parameter.name}.{'.'.join(path)} has type "
                    f"{value_expression.type_name}; expected {field_type_name}"
                ),
                span=value_expression.type_span,
                enclosing_form_name="call",
                generated_core_node_id=generated_core_node_id,
            )
        nested_fields = {field.field_name: field for field in value_expression.fields}
        for nested_field in nested_definition.fields:
            nested_expression = nested_fields.get(nested_field.name)
            if nested_expression is None:
                _raise_lowering_error(
                    code="frontend_lowering_error",
                    message=(
                        f"Record call argument {parameter.name}.{'.'.join(path)} is missing field "
                        f"{nested_field.name}"
                    ),
                    span=value_expression.span,
                    enclosing_form_name="call",
                    generated_core_node_id=generated_core_node_id,
                )
            _lower_record_literal_call_binding_field(
                parameter=parameter,
                path=path + (nested_field.name,),
                value_expression=nested_expression.value,
                field_type_name=nested_field.type_ref.name,
                field_type_span=nested_field.type_ref.span,
                definitions=definitions,
                callee_field_paths=callee_field_paths,
                workflow_input_names=workflow_input_names,
                workflow_input_field_paths=workflow_input_field_paths,
                workflow_input_structured_names=workflow_input_structured_names,
                local_reference_bindings=local_reference_bindings,
                generated_core_node_id=generated_core_node_id,
                lowered_bindings=lowered_bindings,
            )
        return

    flattened_name = callee_field_paths.get(path)
    if flattened_name is None:
        _raise_lowering_error(
            code="frontend_lowering_error",
            message=(
                f"Unable to resolve flattened call binding target for {parameter.name}.{'.'.join(path)}"
            ),
            span=field_type_span,
            enclosing_form_name="call",
            generated_core_node_id=generated_core_node_id,
        )
    lowered_bindings[flattened_name] = _lower_call_binding_value(
        value_expression,
        workflow_input_names=workflow_input_names,
        workflow_input_field_paths=workflow_input_field_paths,
        workflow_input_structured_names=workflow_input_structured_names,
        local_reference_bindings=local_reference_bindings,
        generated_core_node_id=generated_core_node_id,
    )


def _record_parameter_field_paths(
    *,
    parameter_name: str,
    record_definition: RecordDefinition,
    definitions: dict[str, DefinitionNode],
) -> dict[tuple[str, ...], str]:
    contracts: dict[str, dict[str, Any]] = {}
    leaf_input_names: set[str] = set()
    source_spans: dict[str, SourceSpan] = {}
    field_reference_paths: dict[tuple[str, tuple[str, ...]], str] = {}
    input_type_names: dict[str, str] = {}
    _expand_record_parameter_inputs(
        workflow_name=None,
        parameter_name=parameter_name,
        record_definition=record_definition,
        definitions=definitions,
        path=(),
        name_segments=(parameter_name,),
        contracts=contracts,
        leaf_input_names=leaf_input_names,
        field_reference_paths=field_reference_paths,
        source_spans=source_spans,
        input_type_names=input_type_names,
    )
    field_paths: dict[tuple[str, ...], str] = {}
    for (base_parameter_name, field_path), flattened_name in field_reference_paths.items():
        if base_parameter_name != parameter_name:
            continue
        field_paths[field_path] = flattened_name
    return field_paths


def _output_contract_for_structured_return(
    *,
    type_name: str,
    type_span: SourceSpan,
    definitions: dict[str, DefinitionNode],
    path: str,
    enclosing_form_name: str,
    generated_core_node_id: str | None = None,
) -> dict[str, Any]:
    definition = definitions.get(type_name)
    if isinstance(definition, RecordDefinition):
        return {
            "output_bundle": _output_bundle_for_record(
                type_name=type_name,
                type_span=type_span,
                definitions=definitions,
                path=path,
                generated_core_node_id=generated_core_node_id,
            )
        }
    if isinstance(definition, UnionDefinition):
        return {
            "variant_output": _variant_output_for_union(
                type_name=type_name,
                type_span=type_span,
                definitions=definitions,
                path=path,
                generated_core_node_id=generated_core_node_id,
            )
        }
    _raise_lowering_error(
        code="frontend_lowering_error",
        message=(
            f"{enclosing_form_name} return type must resolve to a record or union for lowering: "
            f"{type_name}"
        ),
        span=type_span,
        enclosing_form_name=enclosing_form_name,
        generated_core_node_id=generated_core_node_id,
    )


def _workflow_outputs_for_structured_return(
    *,
    type_name: str,
    type_span: SourceSpan,
    definitions: dict[str, DefinitionNode],
    root_step_name: str,
) -> dict[str, Any]:
    definition = definitions.get(type_name)
    if isinstance(definition, RecordDefinition):
        outputs: dict[str, Any] = {}
        for field in _flatten_record_leaf_fields(
            record_definition=definition,
            definitions=definitions,
        ):
            contract = _bundle_field_contract_for_type(field.type_name, field.type_span, definitions)
            contract = _output_contract_from_bundle_contract(contract)
            contract["from"] = {
                "ref": f"root.steps.{root_step_name}.artifacts.{field.flattened_name}"
            }
            outputs[field.flattened_name] = contract
        return outputs
    if isinstance(definition, UnionDefinition):
        return _workflow_outputs_for_union(
            definition=definition,
            definitions=definitions,
            root_step_name=root_step_name,
        )
    contract = _output_contract_from_bundle_contract(
        _bundle_field_contract_for_type(type_name, type_span, definitions)
    )
    contract["from"] = {"ref": f"root.steps.{root_step_name}.artifacts.result"}
    return {"result": contract}


def _workflow_outputs_for_union(
    *,
    definition: UnionDefinition,
    definitions: dict[str, DefinitionNode],
    root_step_name: str,
) -> dict[str, Any]:
    outputs: dict[str, Any] = {}
    discriminant_name = f"{_snake_case(definition.name)}_variant"
    outputs[discriminant_name] = {
        "kind": "scalar",
        "type": "enum",
        "allowed": [variant.name for variant in definition.variants],
        "from": {"ref": f"root.steps.{root_step_name}.artifacts.{discriminant_name}"},
    }

    return outputs


def _workflow_input_source_map_entries(
    *,
    workflow_name: str,
    parameters: tuple[WorkflowParameter, ...],
    lowered_inputs: _WorkflowInputLowering,
    definitions: dict[str, DefinitionNode],
) -> dict[str, SourceSpan]:
    entries: dict[str, SourceSpan] = {}
    for parameter in parameters:
        if parameter.name in lowered_inputs.structured_param_names:
            continue
        entries[_input_node_id(workflow_name, parameter.name)] = parameter.name_span
    for input_name, span in lowered_inputs.source_spans.items():
        entries[_input_node_id(workflow_name, input_name)] = span
    for input_name, input_type_name in lowered_inputs.input_type_names.items():
        entries.update(
            _path_contract_source_map_entries(
                base_node_id=_input_node_id(workflow_name, input_name),
                type_name=input_type_name,
                definitions=definitions,
            )
        )
    return entries


def _workflow_output_source_map_entries(
    *,
    workflow_name: str,
    type_name: str,
    type_span: SourceSpan,
    definitions: dict[str, DefinitionNode],
) -> dict[str, SourceSpan]:
    definition = definitions.get(type_name)
    if isinstance(definition, RecordDefinition):
        entries: dict[str, SourceSpan] = {}
        for field in _flatten_record_leaf_fields(
            record_definition=definition,
            definitions=definitions,
        ):
            node_id = _output_node_id(workflow_name, field.flattened_name)
            entries[node_id] = field.source_span
            entries.update(
                _path_contract_source_map_entries(
                    base_node_id=node_id,
                    type_name=field.type_name,
                    definitions=definitions,
                )
            )
        return entries
    if isinstance(definition, UnionDefinition):
        discriminant_name = f"{_snake_case(definition.name)}_variant"
        return {
            _output_node_id(workflow_name, discriminant_name): definition.name_span,
        }
    _bundle_field_contract_for_type(type_name, type_span, definitions)
    result_node_id = _output_node_id(workflow_name, "result")
    entries = {result_node_id: type_span}
    entries.update(
        _path_contract_source_map_entries(
            base_node_id=result_node_id,
            type_name=type_name,
            definitions=definitions,
        )
    )
    return entries


def _step_contract_source_map_entries(
    *,
    workflow_name: str,
    step_name: str,
    type_name: str,
    type_span: SourceSpan,
    definitions: dict[str, DefinitionNode],
) -> dict[str, SourceSpan]:
    definition = definitions.get(type_name)
    if isinstance(definition, RecordDefinition):
        entries: dict[str, SourceSpan] = {}
        for field in _flatten_record_leaf_fields(
            record_definition=definition,
            definitions=definitions,
        ):
            node_id = _step_bundle_field_node_id(
                workflow_name=workflow_name,
                step_name=step_name,
                field_name=field.flattened_name,
            )
            entries[node_id] = field.source_span
            entries.update(
                _path_contract_source_map_entries(
                    base_node_id=node_id,
                    type_name=field.type_name,
                    definitions=definitions,
                )
            )
        return entries

    if isinstance(definition, UnionDefinition):
        entries = {
            _step_variant_discriminant_node_id(workflow_name=workflow_name, step_name=step_name): definition.name_span,
        }
        for variant in definition.variants:
            for field in variant.fields:
                nested_definition = definitions.get(field.type_ref.name)
                if isinstance(nested_definition, RecordDefinition):
                    for nested_field in _flatten_record_leaf_fields(
                        record_definition=nested_definition,
                        definitions=definitions,
                        path=(field.name,),
                    ):
                        node_id = _step_variant_field_node_id(
                            workflow_name=workflow_name,
                            step_name=step_name,
                            variant_name=variant.name,
                            field_name=nested_field.flattened_name,
                        )
                        entries[node_id] = nested_field.source_span
                        entries.update(
                            _path_contract_source_map_entries(
                                base_node_id=node_id,
                                type_name=nested_field.type_name,
                                definitions=definitions,
                            )
                        )
                    continue
                node_id = _step_variant_field_node_id(
                    workflow_name=workflow_name,
                    step_name=step_name,
                    variant_name=variant.name,
                    field_name=field.name,
                )
                entries[node_id] = field.name_span
                entries.update(
                    _path_contract_source_map_entries(
                        base_node_id=node_id,
                        type_name=field.type_ref.name,
                        definitions=definitions,
                    )
                )
        return entries

    _raise_lowering_error(
        code="frontend_lowering_error",
        message=(
            "MVP lowering output contracts support only record/union return types for source mapping; "
            f"got {type_name}"
        ),
        span=type_span,
    )


def _reference_to_input_substitution(reference: ReferenceExpression) -> str:
    return f"${{inputs.{reference.name}}}"


def _lower_scalar_expression(
    expression: ExpressionNode,
    *,
    workflow_input_names: frozenset[str],
    workflow_input_field_paths: Mapping[tuple[str, tuple[str, ...]], str],
    workflow_input_structured_names: frozenset[str],
    local_reference_bindings: dict[str, str] | None = None,
    generated_core_node_id: str | None = None,
) -> str:
    if isinstance(expression, ReferenceExpression):
        if expression.name in workflow_input_structured_names:
            _raise_lowering_error(
                code="frontend_lowering_error",
                message=(
                    f"Structured workflow input {expression.name} cannot be lowered as one scalar value; "
                    "reference a field such as "
                    f"{expression.name}.field_name"
                ),
                span=expression.span,
                generated_core_node_id=generated_core_node_id,
            )
        if local_reference_bindings and expression.name in local_reference_bindings:
            _raise_lowering_error(
                code="frontend_lowering_error",
                message=(
                    f"Match binding {expression.name} cannot be lowered as one scalar value; "
                    "reference a variant field such as "
                    f"{expression.name}.field_name"
                ),
                span=expression.span,
                enclosing_form_name="match",
                generated_core_node_id=generated_core_node_id,
            )
        if expression.name in workflow_input_names:
            return _reference_to_input_substitution(expression)
        return _reference_to_input_substitution(expression)
    if isinstance(expression, FieldAccessExpression):
        reference_path = _lower_field_access_reference_path(
            expression,
            workflow_input_field_paths=workflow_input_field_paths,
            local_reference_bindings=local_reference_bindings,
        )
        if reference_path is not None:
            return "${" + reference_path + "}"
    if isinstance(expression, LiteralExpression):
        return str(expression.value)
    if isinstance(expression, PhaseTargetExpression):
        return _lower_phase_target_expression(
            expression,
            workflow_input_names=workflow_input_names,
            workflow_input_field_paths=workflow_input_field_paths,
            workflow_input_structured_names=workflow_input_structured_names,
            local_reference_bindings=local_reference_bindings,
            generated_core_node_id=generated_core_node_id,
        )
    if isinstance(
        expression,
        (
            FieldAccessExpression,
            RecordExpression,
            LetStarExpression,
            MatchExpression,
            ProviderResultExpression,
            CommandResultExpression,
        ),
    ):
        _raise_lowering_error(
        code="frontend_lowering_error",
        message=(
            "MVP lowering supports only literal/reference values and match-proved "
            "variant field references in provider inputs and argv"
        ),
        span=expression.span,
        generated_core_node_id=generated_core_node_id,
    )
    _raise_lowering_error(
        code="frontend_lowering_error",
        message="Unsupported expression shape during MVP lowering",
        span=expression.span,
        generated_core_node_id=generated_core_node_id,
    )


def _lower_phase_target_expression(
    expression: PhaseTargetExpression,
    *,
    workflow_input_names: frozenset[str],
    workflow_input_field_paths: Mapping[tuple[str, tuple[str, ...]], str],
    workflow_input_structured_names: frozenset[str],
    local_reference_bindings: dict[str, str] | None,
    generated_core_node_id: str | None,
) -> str:
    base_value = _lower_scalar_expression(
        expression.context,
        workflow_input_names=workflow_input_names,
        workflow_input_field_paths=workflow_input_field_paths,
        workflow_input_structured_names=workflow_input_structured_names,
        local_reference_bindings=local_reference_bindings,
        generated_core_node_id=generated_core_node_id,
    )
    if expression.phase_name:
        return f"{base_value}/{expression.phase_name}/{expression.target_name}"
    return f"{base_value}/{expression.target_name}"


def _lower_workflow_inputs(
    *,
    workflow_name: str,
    parameters: tuple[WorkflowParameter, ...],
    definitions: dict[str, DefinitionNode],
) -> _WorkflowInputLowering:
    contracts: dict[str, dict[str, Any]] = {}
    leaf_input_names: set[str] = set()
    structured_param_names: set[str] = set()
    field_reference_paths: dict[tuple[str, tuple[str, ...]], str] = {}
    source_spans: dict[str, SourceSpan] = {}
    input_type_names: dict[str, str] = {}

    for parameter in parameters:
        definition = definitions.get(parameter.type_ref.name)
        if isinstance(definition, RecordDefinition):
            structured_param_names.add(parameter.name)
            _expand_record_parameter_inputs(
                workflow_name=workflow_name,
                parameter_name=parameter.name,
                record_definition=definition,
                definitions=definitions,
                path=(),
                name_segments=(parameter.name,),
                contracts=contracts,
                leaf_input_names=leaf_input_names,
                field_reference_paths=field_reference_paths,
                source_spans=source_spans,
                input_type_names=input_type_names,
            )
            continue

        contracts[parameter.name] = _input_contract_for_type(
            parameter.type_ref.name,
            definitions,
            parameter.type_ref.span,
            generated_core_node_id=_input_node_id(workflow_name, parameter.name),
        )
        leaf_input_names.add(parameter.name)
        input_type_names[parameter.name] = parameter.type_ref.name

    return _WorkflowInputLowering(
        contracts=contracts,
        leaf_input_names=frozenset(leaf_input_names),
        structured_param_names=frozenset(structured_param_names),
        field_reference_paths=field_reference_paths,
        source_spans=source_spans,
        input_type_names=input_type_names,
    )


def _expand_record_parameter_inputs(
    *,
    workflow_name: str | None,
    parameter_name: str,
    record_definition: RecordDefinition,
    definitions: dict[str, DefinitionNode],
    path: tuple[str, ...],
    name_segments: tuple[str, ...],
    contracts: dict[str, dict[str, Any]],
    leaf_input_names: set[str],
    field_reference_paths: dict[tuple[str, tuple[str, ...]], str],
    source_spans: dict[str, SourceSpan],
    input_type_names: dict[str, str],
) -> None:
    for field in record_definition.fields:
        field_path = path + (field.name,)
        flattened_name_segments = name_segments + (field.name,)
        nested_definition = definitions.get(field.type_ref.name)
        if isinstance(nested_definition, RecordDefinition):
            _expand_record_parameter_inputs(
                workflow_name=workflow_name,
                parameter_name=parameter_name,
                record_definition=nested_definition,
                definitions=definitions,
                path=field_path,
                name_segments=flattened_name_segments,
                contracts=contracts,
                leaf_input_names=leaf_input_names,
                field_reference_paths=field_reference_paths,
                source_spans=source_spans,
                input_type_names=input_type_names,
            )
            continue
        if isinstance(nested_definition, UnionDefinition):
            generated_core_node_id: str | None = None
            if workflow_name is not None:
                generated_core_node_id = _input_node_id(
                    workflow_name,
                    "__".join(flattened_name_segments),
                )
            _raise_lowering_error(
                code="frontend_lowering_error",
                message=(
                    "Record-typed workflow input fields may not contain union-typed fields in MVP lowering: "
                    f"{parameter_name}.{'.'.join(field_path)}"
                ),
                span=field.type_ref.span,
                enclosing_form_name="defworkflow",
                generated_core_node_id=generated_core_node_id,
            )
        flattened_name = "__".join(flattened_name_segments)
        contracts[flattened_name] = _input_contract_for_type(
            field.type_ref.name,
            definitions,
            field.type_ref.span,
            generated_core_node_id=(
                _input_node_id(workflow_name, flattened_name)
                if workflow_name is not None
                else None
            ),
        )
        leaf_input_names.add(flattened_name)
        field_reference_paths[(parameter_name, field_path)] = flattened_name
        source_spans[flattened_name] = field.name_span
        input_type_names[flattened_name] = field.type_ref.name


def _input_contract_for_type(
    type_name: str,
    definitions: dict[str, DefinitionNode],
    span: SourceSpan,
    generated_core_node_id: str | None = None,
) -> dict[str, Any]:
    if type_name in {"String", "Json", "Symbol", "Provider", "Prompt"}:
        return {"kind": "scalar", "type": "string"}
    if type_name == "Int":
        return {"kind": "scalar", "type": "integer"}
    if type_name == "Float":
        return {"kind": "scalar", "type": "float"}
    if type_name == "Bool":
        return {"kind": "scalar", "type": "bool"}
    if type_name == "PathRel":
        return {"type": "relpath"}

    definition = definitions.get(type_name)
    if isinstance(definition, EnumDefinition):
        return {
            "kind": "scalar",
            "type": "enum",
            "allowed": list(definition.values),
        }
    if isinstance(definition, PathDefinition):
        return {
            "type": "relpath",
            "under": definition.under,
            "must_exist_target": definition.must_exist,
        }

    _raise_lowering_error(
        code="frontend_lowering_error",
        message=f"Unsupported workflow input type for MVP lowering: {type_name}",
        span=span,
        enclosing_form_name="defworkflow",
        generated_core_node_id=generated_core_node_id,
    )


def _output_bundle_for_record(
    *,
    type_name: str,
    type_span: SourceSpan,
    definitions: dict[str, DefinitionNode],
    path: str,
    generated_core_node_id: str | None = None,
) -> dict[str, Any]:
    definition = definitions.get(type_name)
    if not isinstance(definition, RecordDefinition):
        _raise_lowering_error(
            code="frontend_lowering_error",
            message=f"command-result return type must resolve to a record for lowering: {type_name}",
            span=type_span,
            enclosing_form_name="command-result",
            generated_core_node_id=generated_core_node_id,
        )

    fields = []
    for field in _flatten_record_leaf_fields(
        record_definition=definition,
        definitions=definitions,
    ):
        field_contract = _bundle_field_contract_for_type(
            field.type_name,
            field.type_span,
            definitions,
            generated_core_node_id=generated_core_node_id,
        )
        field_contract["name"] = field.flattened_name
        field_contract["json_pointer"] = field.json_pointer
        fields.append(field_contract)

    return {
        "path": path,
        "fields": fields,
    }


def _variant_output_for_union(
    *,
    type_name: str,
    type_span: SourceSpan,
    definitions: dict[str, DefinitionNode],
    path: str,
    generated_core_node_id: str | None = None,
) -> dict[str, Any]:
    definition = definitions.get(type_name)
    if not isinstance(definition, UnionDefinition):
        _raise_lowering_error(
            code="frontend_lowering_error",
            message=f"provider-result return type must resolve to a union for lowering: {type_name}",
            span=type_span,
            enclosing_form_name="provider-result",
            generated_core_node_id=generated_core_node_id,
        )

    discriminant_name = f"{_snake_case(type_name)}_variant"
    variants: dict[str, Any] = {}
    for variant in definition.variants:
        fields = []
        for field in variant.fields:
            nested_definition = definitions.get(field.type_ref.name)
            if isinstance(nested_definition, RecordDefinition):
                for nested_field in _flatten_record_leaf_fields(
                    record_definition=nested_definition,
                    definitions=definitions,
                    path=(field.name,),
                ):
                    field_contract = _bundle_field_contract_for_type(
                        nested_field.type_name,
                        nested_field.type_span,
                        definitions,
                        generated_core_node_id=generated_core_node_id,
                    )
                    field_contract["name"] = nested_field.flattened_name
                    field_contract["json_pointer"] = nested_field.json_pointer
                    fields.append(field_contract)
                continue
            field_contract = _bundle_field_contract_for_type(
                field.type_ref.name,
                field.type_ref.span,
                definitions,
                generated_core_node_id=generated_core_node_id,
            )
            field_contract["name"] = field.name
            field_contract["json_pointer"] = f"/{field.name}"
            fields.append(field_contract)
        variants[variant.name] = {"fields": fields}

    return {
        "path": path,
        "discriminant": {
            "name": discriminant_name,
            "json_pointer": f"/{discriminant_name}",
            "type": "enum",
            "allowed": [variant.name for variant in definition.variants],
        },
        "variants": variants,
    }


def _bundle_field_contract_for_type(
    type_name: str,
    span: SourceSpan,
    definitions: dict[str, DefinitionNode],
    *,
    generated_core_node_id: str | None = None,
) -> dict[str, Any]:
    if type_name in {"String", "Json", "Symbol", "Provider", "Prompt"}:
        return {"type": "string"}
    if type_name == "Int":
        return {"type": "integer"}
    if type_name == "Float":
        return {"type": "float"}
    if type_name == "Bool":
        return {"type": "bool"}
    if type_name == "PathRel":
        return {"type": "relpath"}

    definition = definitions.get(type_name)
    if isinstance(definition, EnumDefinition):
        return {
            "type": "enum",
            "allowed": list(definition.values),
        }
    if isinstance(definition, PathDefinition):
        return {
            "type": "relpath",
            "under": definition.under,
            "must_exist_target": definition.must_exist,
        }

    _raise_lowering_error(
        code="frontend_lowering_error",
        message=(
            "MVP lowering output contracts support only scalar/enum/defpath field types; "
            f"got {type_name}"
        ),
        span=span,
        generated_core_node_id=generated_core_node_id,
    )


def _output_contract_from_bundle_contract(bundle_contract: dict[str, Any]) -> dict[str, Any]:
    contract = dict(bundle_contract)
    if contract.get("type") != "relpath":
        contract["kind"] = "scalar"
    return contract


def _path_contract_source_map_entries(
    *,
    base_node_id: str,
    type_name: str,
    definitions: dict[str, DefinitionNode],
) -> dict[str, SourceSpan]:
    definition = definitions.get(type_name)
    if not isinstance(definition, PathDefinition):
        return {}
    return {
        f"{base_node_id}.under": definition.under_span,
        f"{base_node_id}.must_exist_target": definition.must_exist_span,
    }


def _snake_case(name: str) -> str:
    pieces: list[str] = []
    for index, char in enumerate(name):
        if char.isupper() and index > 0:
            pieces.append("_")
        pieces.append(char.lower())
    return "".join(pieces)


def _result_node_id(workflow_name: str) -> str:
    return f"{workflow_name}.result"


def _step_node_id(workflow_name: str, step_name: str) -> str:
    return f"{workflow_name}.step.{step_name}"


def _input_node_id(workflow_name: str, input_name: str) -> str:
    return f"{workflow_name}.input.{input_name}"


def _output_node_id(workflow_name: str, output_name: str) -> str:
    return f"{workflow_name}.output.{output_name}"


def _match_case_result_node_id(*, workflow_name: str, match_step_name: str, case_variant_name: str) -> str:
    return f"{workflow_name}.step.{match_step_name}.case.{case_variant_name}.result"


def _step_bundle_field_node_id(*, workflow_name: str, step_name: str, field_name: str) -> str:
    return f"{workflow_name}.step.{step_name}.contract.output_bundle.field.{field_name}"


def _step_variant_discriminant_node_id(*, workflow_name: str, step_name: str) -> str:
    return f"{workflow_name}.step.{step_name}.contract.variant_output.discriminant"


def _step_variant_field_node_id(
    *,
    workflow_name: str,
    step_name: str,
    variant_name: str,
    field_name: str,
) -> str:
    return f"{workflow_name}.step.{step_name}.contract.variant_output.variant.{variant_name}.field.{field_name}"


def _call_source_map_entries(
    *,
    workflow_name: str,
    step_name: str,
    expression: CallExpression,
    lowered_step: Mapping[str, Any],
) -> dict[str, SourceSpan]:
    entries = {
        _step_call_target_node_id(workflow_name=workflow_name, step_name=step_name): expression.callee_span,
        _import_alias_node_id(workflow_name=workflow_name, alias=expression.callee_name): expression.callee_span,
    }
    entries.update(
        _call_binding_source_map_entries(
            workflow_name=workflow_name,
            step_name=step_name,
            argument_node_id_builder=_step_call_binding_node_id,
            expression=expression,
            lowered_step=lowered_step,
        )
    )
    return entries


def _step_call_target_node_id(*, workflow_name: str, step_name: str) -> str:
    return f"{workflow_name}.step.{step_name}.call"


def _step_call_binding_node_id(*, workflow_name: str, step_name: str, argument_name: str) -> str:
    return f"{workflow_name}.step.{step_name}.with.{argument_name}"


def _match_case_call_source_map_entries(
    *,
    workflow_name: str,
    match_step_name: str,
    case_variant_name: str,
    case_step_name: str,
    expression: CallExpression,
    lowered_step: Mapping[str, Any],
) -> dict[str, SourceSpan]:
    entries = {
        _match_case_step_call_target_node_id(
            workflow_name=workflow_name,
            match_step_name=match_step_name,
            case_variant_name=case_variant_name,
            case_step_name=case_step_name,
        ): expression.callee_span
    }
    entries.update(
        _call_binding_source_map_entries(
            workflow_name=workflow_name,
            step_name=case_step_name,
            argument_node_id_builder=lambda *, workflow_name, step_name, argument_name: _match_case_step_call_binding_node_id(
                workflow_name=workflow_name,
                match_step_name=match_step_name,
                case_variant_name=case_variant_name,
                case_step_name=step_name,
                argument_name=argument_name,
            ),
            expression=expression,
            lowered_step=lowered_step,
        )
    )
    return entries


def _call_binding_source_map_entries(
    *,
    workflow_name: str,
    step_name: str,
    argument_node_id_builder: Callable[..., str],
    expression: CallExpression,
    lowered_step: Mapping[str, Any],
) -> dict[str, SourceSpan]:
    with_bindings = lowered_step.get("with")
    if not isinstance(with_bindings, dict):
        return {}

    entries: dict[str, SourceSpan] = {}
    for binding_name in with_bindings:
        if not isinstance(binding_name, str):
            continue
        binding_span = _call_binding_source_span(binding_name=binding_name, expression=expression)
        if binding_span is None:
            continue
        entries[
            argument_node_id_builder(
                workflow_name=workflow_name,
                step_name=step_name,
                argument_name=binding_name,
            )
        ] = binding_span
    return entries


def _call_binding_source_span(
    *,
    binding_name: str,
    expression: CallExpression,
) -> SourceSpan | None:
    for argument in expression.arguments:
        if binding_name == argument.parameter_name:
            return argument.keyword_span
        prefix = f"{argument.parameter_name}__"
        if binding_name.startswith(prefix):
            return argument.keyword_span
    return None


def _match_case_step_contract_source_map_entries(
    *,
    workflow_name: str,
    match_step_name: str,
    case_variant_name: str,
    case_step_name: str,
    type_name: str,
    type_span: SourceSpan,
    definitions: dict[str, DefinitionNode],
) -> dict[str, SourceSpan]:
    definition = definitions.get(type_name)
    if isinstance(definition, RecordDefinition):
        entries: dict[str, SourceSpan] = {}
        for field in _flatten_record_leaf_fields(
            record_definition=definition,
            definitions=definitions,
        ):
            node_id = _match_case_step_bundle_field_node_id(
                workflow_name=workflow_name,
                match_step_name=match_step_name,
                case_variant_name=case_variant_name,
                case_step_name=case_step_name,
                field_name=field.flattened_name,
            )
            entries[node_id] = field.source_span
            entries.update(
                _path_contract_source_map_entries(
                    base_node_id=node_id,
                    type_name=field.type_name,
                    definitions=definitions,
                )
            )
        return entries

    if isinstance(definition, UnionDefinition):
        entries = {
            _match_case_step_variant_discriminant_node_id(
                workflow_name=workflow_name,
                match_step_name=match_step_name,
                case_variant_name=case_variant_name,
                case_step_name=case_step_name,
            ): definition.name_span,
        }
        for variant in definition.variants:
            for field in variant.fields:
                nested_definition = definitions.get(field.type_ref.name)
                if isinstance(nested_definition, RecordDefinition):
                    for nested_field in _flatten_record_leaf_fields(
                        record_definition=nested_definition,
                        definitions=definitions,
                        path=(field.name,),
                    ):
                        node_id = _match_case_step_variant_field_node_id(
                            workflow_name=workflow_name,
                            match_step_name=match_step_name,
                            case_variant_name=case_variant_name,
                            case_step_name=case_step_name,
                            variant_name=variant.name,
                            field_name=nested_field.flattened_name,
                        )
                        entries[node_id] = nested_field.source_span
                        entries.update(
                            _path_contract_source_map_entries(
                                base_node_id=node_id,
                                type_name=nested_field.type_name,
                                definitions=definitions,
                            )
                        )
                    continue
                node_id = _match_case_step_variant_field_node_id(
                    workflow_name=workflow_name,
                    match_step_name=match_step_name,
                    case_variant_name=case_variant_name,
                    case_step_name=case_step_name,
                    variant_name=variant.name,
                    field_name=field.name,
                )
                entries[node_id] = field.name_span
                entries.update(
                    _path_contract_source_map_entries(
                        base_node_id=node_id,
                        type_name=field.type_ref.name,
                        definitions=definitions,
                    )
                )
        return entries

    _raise_lowering_error(
        code="frontend_lowering_error",
        message=(
            "MVP lowering output contracts support only record/union return types for case source mapping; "
            f"got {type_name}"
        ),
        span=type_span,
    )


def _match_case_step_call_target_node_id(
    *,
    workflow_name: str,
    match_step_name: str,
    case_variant_name: str,
    case_step_name: str,
) -> str:
    return f"{workflow_name}.step.{match_step_name}.case.{case_variant_name}.step.{case_step_name}.call"


def _match_case_step_node_id(
    *,
    workflow_name: str,
    match_step_name: str,
    case_variant_name: str,
    case_step_name: str,
) -> str:
    return f"{workflow_name}.step.{match_step_name}.case.{case_variant_name}.step.{case_step_name}"


def _match_case_step_call_binding_node_id(
    *,
    workflow_name: str,
    match_step_name: str,
    case_variant_name: str,
    case_step_name: str,
    argument_name: str,
) -> str:
    return (
        f"{workflow_name}.step.{match_step_name}.case.{case_variant_name}.step."
        f"{case_step_name}.with.{argument_name}"
    )


def _match_case_output_source_map_entries(
    *,
    workflow_name: str,
    match_step_name: str,
    case_variant_name: str,
    type_name: str,
    type_span: SourceSpan,
    definitions: dict[str, DefinitionNode],
) -> dict[str, SourceSpan]:
    definition = definitions.get(type_name)
    if isinstance(definition, RecordDefinition):
        return {
            _match_case_output_node_id(
                workflow_name=workflow_name,
                match_step_name=match_step_name,
                case_variant_name=case_variant_name,
                output_name=field.flattened_name,
            ): field.source_span
            for field in _flatten_record_leaf_fields(
                record_definition=definition,
                definitions=definitions,
            )
        }
    if isinstance(definition, UnionDefinition):
        discriminant_name = f"{_snake_case(definition.name)}_variant"
        return {
            _match_case_output_node_id(
                workflow_name=workflow_name,
                match_step_name=match_step_name,
                case_variant_name=case_variant_name,
                output_name=discriminant_name,
            ): definition.name_span
        }
    _bundle_field_contract_for_type(type_name, type_span, definitions)
    return {
        _match_case_output_node_id(
            workflow_name=workflow_name,
            match_step_name=match_step_name,
            case_variant_name=case_variant_name,
            output_name="result",
        ): type_span
    }


def _match_case_output_node_id(
    *,
    workflow_name: str,
    match_step_name: str,
    case_variant_name: str,
    output_name: str,
) -> str:
    return f"{workflow_name}.step.{match_step_name}.case.{case_variant_name}.output.{output_name}"


def _match_ref_node_id(*, workflow_name: str, match_step_name: str) -> str:
    return f"{workflow_name}.step.{match_step_name}.match.ref"


def _match_case_selector_node_id(
    *,
    workflow_name: str,
    match_step_name: str,
    case_variant_name: str,
) -> str:
    return f"{workflow_name}.step.{match_step_name}.match.case.{case_variant_name}"


def _match_routing_source_map_entries(
    *,
    workflow_name: str,
    match_step_name: str,
    expression: MatchExpression,
) -> dict[str, SourceSpan]:
    entries = {
        _match_ref_node_id(workflow_name=workflow_name, match_step_name=match_step_name): expression.span,
    }
    for arm in expression.arms:
        entries[
            _match_case_selector_node_id(
                workflow_name=workflow_name,
                match_step_name=match_step_name,
                case_variant_name=arm.variant_name,
            )
        ] = arm.variant_span
    return entries


def _match_case_step_bundle_field_node_id(
    *,
    workflow_name: str,
    match_step_name: str,
    case_variant_name: str,
    case_step_name: str,
    field_name: str,
) -> str:
    return (
        f"{workflow_name}.step.{match_step_name}.case.{case_variant_name}.step.{case_step_name}."
        f"contract.output_bundle.field.{field_name}"
    )


def _match_case_step_variant_discriminant_node_id(
    *,
    workflow_name: str,
    match_step_name: str,
    case_variant_name: str,
    case_step_name: str,
) -> str:
    return (
        f"{workflow_name}.step.{match_step_name}.case.{case_variant_name}.step.{case_step_name}."
        "contract.variant_output.discriminant"
    )


def _match_case_step_variant_field_node_id(
    *,
    workflow_name: str,
    match_step_name: str,
    case_variant_name: str,
    case_step_name: str,
    variant_name: str,
    field_name: str,
) -> str:
    return (
        f"{workflow_name}.step.{match_step_name}.case.{case_variant_name}.step.{case_step_name}."
        f"contract.variant_output.variant.{variant_name}.field.{field_name}"
    )


def _import_alias_node_id(*, workflow_name: str, alias: str) -> str:
    return f"{workflow_name}.import.{alias}"


def _flatten_record_leaf_fields(
    *,
    record_definition: RecordDefinition,
    definitions: dict[str, DefinitionNode],
    path: tuple[str, ...] = (),
) -> tuple[_FlattenedRecordLeafField, ...]:
    fields: list[_FlattenedRecordLeafField] = []
    for field in record_definition.fields:
        nested_path = path + (field.name,)
        nested_definition = definitions.get(field.type_ref.name)
        if isinstance(nested_definition, RecordDefinition):
            fields.extend(
                _flatten_record_leaf_fields(
                    record_definition=nested_definition,
                    definitions=definitions,
                    path=nested_path,
                )
            )
            continue
        fields.append(
            _FlattenedRecordLeafField(
                flattened_name="__".join(nested_path),
                json_pointer="/" + "/".join(nested_path),
                type_name=field.type_ref.name,
                type_span=field.type_ref.span,
                source_span=field.name_span,
            )
        )
    return tuple(fields)


def _lower_field_access_reference_path(
    expression: FieldAccessExpression,
    *,
    workflow_input_field_paths: Mapping[tuple[str, tuple[str, ...]], str],
    local_reference_bindings: dict[str, str] | None = None,
) -> str | None:
    base_reference_name, field_path = _field_access_segments(expression)
    if base_reference_name is None:
        return None
    if not field_path:
        return None
    if local_reference_bindings and base_reference_name in local_reference_bindings:
        return f"{local_reference_bindings[base_reference_name]}.{'.'.join(field_path)}"
    flattened_input_name = workflow_input_field_paths.get((base_reference_name, field_path))
    if flattened_input_name is not None:
        return f"inputs.{flattened_input_name}"
    return None


def _field_access_segments(expression: FieldAccessExpression) -> tuple[str | None, tuple[str, ...]]:
    fields: list[str] = [expression.field_name]
    current: ExpressionNode = expression.base
    while isinstance(current, FieldAccessExpression):
        fields.append(current.field_name)
        current = current.base
    if not isinstance(current, ReferenceExpression):
        return None, ()
    fields.reverse()
    return current.name, tuple(fields)


def _collect_call_targets(steps: list[dict[str, Any]]) -> list[str]:
    targets: list[str] = []
    for step in steps:
        call_target = step.get("call")
        if isinstance(call_target, str):
            if call_target not in targets:
                targets.append(call_target)
        match_block = step.get("match")
        if isinstance(match_block, dict):
            cases = match_block.get("cases")
            if isinstance(cases, dict):
                for case in cases.values():
                    if not isinstance(case, dict):
                        continue
                    nested_steps = case.get("steps")
                    if isinstance(nested_steps, list):
                        for nested_target in _collect_call_targets(nested_steps):
                            if nested_target not in targets:
                                targets.append(nested_target)
    return targets


def _resolve_imported_call_target_path(
    call_target: str,
    *,
    import_definitions: tuple[ImportDefinition, ...],
) -> str | None:
    # `:only` names are exact imports and are validated as unique.
    for import_definition in import_definitions:
        import_path = _module_ref_to_import_path(import_definition.module_ref)
        if call_target in import_definition.only_names:
            return _import_path_for_call_target(import_path=import_path, workflow_name=call_target)

    best_match_path: str | None = None
    best_match_qualifier_len = -1

    # For qualified names, prefer the most specific matching qualifier.
    for import_definition in import_definitions:
        import_path = _module_ref_to_import_path(import_definition.module_ref)
        qualifier = import_definition.alias or import_definition.module_ref
        resolved_member_name = _alias_qualified_member_name(
            call_target=call_target,
            alias=qualifier,
        )
        if resolved_member_name is None:
            continue
        if import_definition.only_names and resolved_member_name not in import_definition.only_names:
            continue
        qualifier_len = len(qualifier)
        if qualifier_len > best_match_qualifier_len:
            best_match_path = _import_path_for_call_target(
                import_path=import_path,
                workflow_name=resolved_member_name,
            )
            best_match_qualifier_len = qualifier_len

    return best_match_path


def _import_path_for_call_target(*, import_path: str, workflow_name: str) -> str:
    """Select one workflow from .orc imports while keeping YAML imports unchanged."""
    path_without_fragment, separator, _ = import_path.partition("#")
    if separator:
        return import_path
    if path_without_fragment.lower().endswith(".orc"):
        return f"{import_path}#{workflow_name}"
    return import_path


def _alias_qualified_member_name(*, call_target: str, alias: str) -> str | None:
    for separator in ("/", "."):
        prefix = f"{alias}{separator}"
        if call_target.startswith(prefix) and len(call_target) > len(prefix):
            return call_target[len(prefix) :]
    return None


def _module_ref_to_import_path(module_ref: str) -> str:
    module_path, separator, fragment = module_ref.partition("#")
    if module_path.endswith(".yaml") or module_path.endswith(".yml") or module_path.endswith(".orc"):
        return module_ref

    if "/" not in module_path and "." in module_path:
        normalized_path = f"{module_path.replace('.', '/')}.yaml"
    else:
        normalized_path = f"{module_path}.yaml"

    if separator:
        return f"{normalized_path}#{fragment}"
    return normalized_path


def _first_case_step_name(case_payload: Any) -> str | None:
    if not isinstance(case_payload, dict):
        return None
    steps = case_payload.get("steps")
    if not isinstance(steps, list) or not steps:
        return None
    first_step = steps[0]
    if not isinstance(first_step, dict):
        return None
    step_name = first_step.get("name")
    if not isinstance(step_name, str):
        return None
    return step_name
