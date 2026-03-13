"""Test-only helpers for inspecting projection-backed bundle compatibility surfaces."""

from __future__ import annotations

from dataclasses import is_dataclass
from typing import Any

from orchestrator.workflow.conditions import (
    EqualsConditionNode,
    ExistsConditionNode,
    NotExistsConditionNode,
)
from orchestrator.workflow.executable_ir import (
    AssertStepConfig,
    CallStepConfig,
    CommandStepConfig,
    ForEachNode,
    ForEachStepConfig,
    IncrementScalarStepConfig,
    ProviderStepConfig,
    RepeatUntilFrameNode,
    RepeatUntilStepConfig,
    SetScalarStepConfig,
    StepCommonConfig,
    WaitForStepConfig,
)
from orchestrator.workflow.loaded_bundle import LoadedWorkflowBundle, workflow_context
from orchestrator.workflow.predicates import (
    AllOfPredicateNode,
    AnyOfPredicateNode,
    ArtifactBoolPredicateNode,
    ComparePredicateNode,
    NotPredicateNode,
    ScorePredicateNode,
)
from orchestrator.workflow.references import (
    SelfOutputReference,
    StructuredStepReference,
    WorkflowInputReference,
)
from orchestrator.workflow.surface_ast import (
    SurfaceBranchBlock,
    SurfaceContract,
    SurfaceFinallyBlock,
    SurfaceMatchCaseBlock,
    SurfaceRepeatUntilBlock,
    SurfaceStep,
    SurfaceStepCommonConfig,
    SurfaceStepKind,
    SurfaceWorkflow,
)


def _thaw(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    if isinstance(value, list):
        return [_thaw(item) for item in value]
    if hasattr(value, "items"):
        return {str(key): _thaw(item) for key, item in value.items()}
    if is_dataclass(value):
        return {str(key): _thaw(item) for key, item in vars(value).items()}
    return value


def _set_runtime_field(
    step: dict[str, Any],
    field_name: str,
    value: Any,
    *,
    include_empty: bool = False,
) -> None:
    if value is None:
        return
    if not include_empty and isinstance(value, dict) and not value:
        return
    if not include_empty and isinstance(value, (list, tuple)) and not value:
        return
    step[field_name] = _thaw(value)


def _render_common_config(step: dict[str, Any], common: StepCommonConfig) -> None:
    _set_runtime_field(step, "on", common.on)
    _set_runtime_field(step, "consumes", common.consumes)
    _set_runtime_field(step, "consume_bundle", common.consume_bundle)
    _set_runtime_field(step, "publishes", common.publishes)
    _set_runtime_field(step, "expected_outputs", common.expected_outputs)
    _set_runtime_field(step, "output_bundle", common.output_bundle)
    if common.persist_artifacts_in_state is not None:
        step["persist_artifacts_in_state"] = common.persist_artifacts_in_state
    _set_runtime_field(step, "provider_session", common.provider_session)
    if common.max_visits is not None:
        step["max_visits"] = common.max_visits
    _set_runtime_field(step, "retries", common.retries)
    _set_runtime_field(step, "env", common.env)
    _set_runtime_field(step, "secrets", common.secrets)
    _set_runtime_field(step, "timeout_sec", common.timeout_sec)
    _set_runtime_field(step, "output_capture", common.output_capture)
    _set_runtime_field(step, "output_file", common.output_file)
    if common.allow_parse_error is not None:
        step["allow_parse_error"] = common.allow_parse_error


def materialize_execution_config_for_test(
    config: Any,
    *,
    step_name: str,
    step_id: str,
    nested_steps: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    step: dict[str, Any] = {
        "name": step_name,
        "step_id": step_id,
    }

    if isinstance(
        config,
            (
                CommandStepConfig,
                ProviderStepConfig,
                WaitForStepConfig,
                AssertStepConfig,
                CallStepConfig,
                SetScalarStepConfig,
                IncrementScalarStepConfig,
                ForEachStepConfig,
                RepeatUntilStepConfig,
            ),
    ):
        _render_common_config(step, config.common)

    if isinstance(config, CommandStepConfig):
        _set_runtime_field(step, "command", config.command, include_empty=True)
        return step

    if isinstance(config, ProviderStepConfig):
        step["provider"] = config.provider
        _set_runtime_field(step, "provider_params", config.provider_params)
        _set_runtime_field(step, "input_file", config.input_file)
        _set_runtime_field(step, "asset_file", config.asset_file)
        _set_runtime_field(step, "depends_on", config.depends_on)
        _set_runtime_field(step, "asset_depends_on", config.asset_depends_on)
        if config.inject_output_contract is not None:
            step["inject_output_contract"] = config.inject_output_contract
        if config.inject_consumes is not None:
            step["inject_consumes"] = config.inject_consumes
        _set_runtime_field(step, "prompt_consumes", config.prompt_consumes)
        if config.consumes_injection_position is not None:
            step["consumes_injection_position"] = config.consumes_injection_position
        return step

    if isinstance(config, WaitForStepConfig):
        _set_runtime_field(step, "wait_for", config.wait_for, include_empty=True)
        return step

    if isinstance(config, AssertStepConfig):
        return step

    if isinstance(config, SetScalarStepConfig):
        _set_runtime_field(step, "set_scalar", config.set_scalar, include_empty=True)
        return step

    if isinstance(config, IncrementScalarStepConfig):
        _set_runtime_field(step, "increment_scalar", config.increment_scalar, include_empty=True)
        return step

    if isinstance(config, CallStepConfig):
        step["call"] = config.call
        return step

    if isinstance(config, ForEachStepConfig):
        for_each: dict[str, Any] = {}
        if config.items_from is not None:
            for_each["items_from"] = config.items_from
        else:
            for_each["items"] = _thaw(config.items)
        if config.item_name != "item":
            for_each["as"] = config.item_name
        if nested_steps is not None:
            for_each["steps"] = nested_steps
        step["for_each"] = for_each
        return step

    if isinstance(config, RepeatUntilStepConfig):
        repeat_until: dict[str, Any] = {
            "id": config.body_id,
            "max_iterations": config.max_iterations,
        }
        if nested_steps is not None:
            repeat_until["steps"] = nested_steps
        step["repeat_until"] = repeat_until
        return step

    raise TypeError(f"Unsupported executable config for tests: {type(config).__name__}")


def _surface_ref_text(ref: Any) -> str:
    if isinstance(ref, WorkflowInputReference):
        return f"inputs.{ref.input_name}"
    if isinstance(ref, StructuredStepReference):
        suffix = f"{ref.field}.{ref.member}" if ref.member is not None else ref.field
        return f"{ref.scope}.steps.{ref.step_name}.{suffix}"
    if isinstance(ref, SelfOutputReference):
        return f"self.outputs.{ref.output_name}"
    raise TypeError(f"Unsupported surface ref type: {type(ref).__name__}")


def _surface_operand(value: Any) -> Any:
    if isinstance(value, (WorkflowInputReference, StructuredStepReference, SelfOutputReference)):
        return {"ref": _surface_ref_text(value)}
    return _thaw(value)


def _surface_condition(condition: Any) -> Any:
    if condition is None:
        return None
    if isinstance(condition, EqualsConditionNode):
        return {
            "equals": {
                "left": _thaw(condition.left),
                "right": _thaw(condition.right),
            }
        }
    if isinstance(condition, ExistsConditionNode):
        return {"exists": condition.pattern}
    if isinstance(condition, NotExistsConditionNode):
        return {"not_exists": condition.pattern}
    if isinstance(condition, ArtifactBoolPredicateNode):
        return {"artifact_bool": {"ref": _surface_ref_text(condition.ref)}}
    if isinstance(condition, ComparePredicateNode):
        return {
            "compare": {
                "left": _surface_operand(condition.left),
                "op": condition.op,
                "right": _surface_operand(condition.right),
            }
        }
    if isinstance(condition, ScorePredicateNode):
        payload: dict[str, Any] = {"ref": _surface_ref_text(condition.ref)}
        for key in ("gt", "gte", "lt", "lte"):
            value = getattr(condition, key)
            if value is not None:
                payload[key] = value
        return {"score": payload}
    if isinstance(condition, AllOfPredicateNode):
        return {"all_of": [_surface_condition(item) for item in condition.items]}
    if isinstance(condition, AnyOfPredicateNode):
        return {"any_of": [_surface_condition(item) for item in condition.items]}
    if isinstance(condition, NotPredicateNode):
        return {"not": _surface_condition(condition.item)}
    return _thaw(condition)


def _surface_contracts(contracts: Any) -> dict[str, Any]:
    return {
        str(name): _thaw(contract.definition)
        for name, contract in contracts.items()
        if isinstance(name, str) and isinstance(contract, SurfaceContract)
    }


def _set_if_present(payload: dict[str, Any], key: str, value: Any) -> None:
    if value is None:
        return
    if value == () or value == {}:
        return
    payload[key] = value


def _surface_on(common: SurfaceStepCommonConfig) -> dict[str, Any] | None:
    if common.on is None:
        return None
    payload: dict[str, Any] = {}
    for name in ("success", "failure", "always"):
        handler = getattr(common.on, name)
        if handler is not None and isinstance(handler.goto, str):
            payload[name] = {"goto": handler.goto}
    return payload or None


def _apply_surface_common_fields(payload: dict[str, Any], common: SurfaceStepCommonConfig) -> None:
    _set_if_present(payload, "on", _surface_on(common))
    _set_if_present(payload, "consumes", _thaw(common.consumes))
    _set_if_present(payload, "consume_bundle", _thaw(common.consume_bundle))
    _set_if_present(payload, "publishes", _thaw(common.publishes))
    _set_if_present(payload, "expected_outputs", _thaw(common.expected_outputs))
    _set_if_present(payload, "output_bundle", _thaw(common.output_bundle))
    if common.persist_artifacts_in_state is not None:
        payload["persist_artifacts_in_state"] = common.persist_artifacts_in_state
    _set_if_present(payload, "provider_session", _thaw(common.provider_session))
    if common.max_visits is not None:
        payload["max_visits"] = common.max_visits
    _set_if_present(payload, "retries", _thaw(common.retries))
    _set_if_present(payload, "env", _thaw(common.env))
    _set_if_present(payload, "secrets", _thaw(common.secrets))
    _set_if_present(payload, "timeout_sec", common.timeout_sec)
    _set_if_present(payload, "output_capture", _thaw(common.output_capture))
    _set_if_present(payload, "output_file", _thaw(common.output_file))
    if common.allow_parse_error is not None:
        payload["allow_parse_error"] = common.allow_parse_error


def _surface_branch_block(block: SurfaceBranchBlock) -> dict[str, Any]:
    payload: dict[str, Any] = {"id": block.token, "steps": _surface_steps(block.steps)}
    outputs = _surface_contracts(block.outputs)
    if outputs:
        payload["outputs"] = outputs
    return payload


def _surface_match_case_block(block: SurfaceMatchCaseBlock) -> dict[str, Any]:
    payload: dict[str, Any] = {"id": block.token, "steps": _surface_steps(block.steps)}
    outputs = _surface_contracts(block.outputs)
    if outputs:
        payload["outputs"] = outputs
    return payload


def _surface_repeat_until_block(block: SurfaceRepeatUntilBlock) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": block.token,
        "steps": _surface_steps(block.steps),
        "condition": _surface_condition(block.condition),
    }
    outputs = _surface_contracts(block.outputs)
    if outputs:
        payload["outputs"] = outputs
    if block.max_iterations is not None:
        payload["max_iterations"] = block.max_iterations
    return payload


def _surface_finally_block(block: SurfaceFinallyBlock) -> dict[str, Any]:
    return {
        "id": block.token,
        "steps": _surface_steps(block.steps),
    }


def _surface_step(step: SurfaceStep) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "name": step.name,
        "step_id": step.step_id,
    }
    if step.authored_id is not None:
        payload["id"] = step.authored_id

    _apply_surface_common_fields(payload, step.common)
    when_condition = _surface_condition(step.when_predicate)
    if when_condition is not None:
        payload["when"] = when_condition
    assert_condition = _surface_condition(step.assert_predicate)
    if assert_condition is not None:
        payload["assert"] = assert_condition

    if step.kind is SurfaceStepKind.COMMAND:
        payload["command"] = _thaw(step.command)
    elif step.kind is SurfaceStepKind.PROVIDER:
        payload["provider"] = step.provider
        _set_if_present(payload, "provider_params", _thaw(step.provider_params))
        _set_if_present(payload, "input_file", _thaw(step.input_file))
        _set_if_present(payload, "asset_file", _thaw(step.asset_file))
        _set_if_present(payload, "depends_on", _thaw(step.depends_on))
        _set_if_present(payload, "asset_depends_on", _thaw(step.asset_depends_on))
        if step.inject_output_contract is not None:
            payload["inject_output_contract"] = step.inject_output_contract
        if step.inject_consumes is not None:
            payload["inject_consumes"] = step.inject_consumes
        _set_if_present(payload, "prompt_consumes", _thaw(step.prompt_consumes))
        _set_if_present(payload, "consumes_injection_position", step.consumes_injection_position)
    elif step.kind is SurfaceStepKind.WAIT_FOR:
        payload["wait_for"] = _thaw(step.wait_for)
    elif step.kind is SurfaceStepKind.SET_SCALAR:
        payload["set_scalar"] = _thaw(step.set_scalar)
    elif step.kind is SurfaceStepKind.INCREMENT_SCALAR:
        payload["increment_scalar"] = _thaw(step.increment_scalar)
    elif step.kind is SurfaceStepKind.IF:
        payload["if"] = _surface_condition(step.if_condition)
        if step.then_branch is not None:
            payload["then"] = _surface_branch_block(step.then_branch)
        if step.else_branch is not None:
            payload["else"] = _surface_branch_block(step.else_branch)
    elif step.kind is SurfaceStepKind.MATCH:
        payload["match"] = {
            "ref": _surface_ref_text(step.match_ref),
            "cases": {
                case_name: _surface_match_case_block(block)
                for case_name, block in step.match_cases.items()
            },
        }
    elif step.kind is SurfaceStepKind.FOR_EACH:
        for_each: dict[str, Any] = {"steps": _surface_steps(step.for_each_steps)}
        if step.for_each_items_from is not None:
            for_each["items_from"] = step.for_each_items_from
        else:
            for_each["items"] = _thaw(step.for_each_items)
        if step.for_each_item_name != "item":
            for_each["as"] = step.for_each_item_name
        payload["for_each"] = for_each
    elif step.kind is SurfaceStepKind.REPEAT_UNTIL and step.repeat_until is not None:
        payload["repeat_until"] = _surface_repeat_until_block(step.repeat_until)
    elif step.kind is SurfaceStepKind.CALL:
        payload["call"] = step.call_alias
        if step.call_bindings:
            payload["with"] = {
                name: _surface_operand(value)
                for name, value in step.call_bindings.items()
            }

    return payload


def _surface_steps(steps: tuple[SurfaceStep, ...]) -> list[dict[str, Any]]:
    return [_surface_step(step) for step in steps]


def _surface_workflow(surface: SurfaceWorkflow) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "version": surface.version,
        "steps": _surface_steps(surface.steps),
    }
    if surface.name is not None:
        payload["name"] = surface.name
    if not surface.strict_flow:
        payload["strict_flow"] = surface.strict_flow
    _set_if_present(payload, "context", _thaw(surface.context))
    _set_if_present(payload, "providers", _thaw(surface.providers))
    _set_if_present(payload, "secrets", _thaw(surface.secrets))
    _set_if_present(payload, "inbox_dir", surface.inbox_dir)
    _set_if_present(payload, "processed_dir", surface.processed_dir)
    _set_if_present(payload, "failed_dir", surface.failed_dir)
    _set_if_present(payload, "task_extension", surface.task_extension)
    _set_if_present(payload, "max_transitions", surface.max_transitions)
    artifacts = _surface_contracts(surface.artifacts)
    if artifacts:
        payload["artifacts"] = artifacts
    inputs = _surface_contracts(surface.inputs)
    if inputs:
        payload["inputs"] = inputs
    outputs = _surface_contracts(surface.outputs)
    if outputs:
        payload["outputs"] = outputs
    if surface.imports:
        payload["imports"] = {
            alias: str(metadata.workflow_path)
            for alias, metadata in surface.imports.items()
        }
    if surface.finalization is not None:
        payload["finally"] = _surface_finally_block(surface.finalization)
    return payload


def _materialize_loop_steps(
    bundle: LoadedWorkflowBundle,
    loop_node_id: str,
    node_ids: tuple[str, ...],
    *,
    loop_kind: str,
) -> list[dict[str, Any]]:
    if loop_kind == "for_each":
        projection = bundle.projection.for_each_nodes.get(loop_node_id)
    else:
        projection = bundle.projection.repeat_until_nodes.get(loop_node_id)

    materialized: list[dict[str, Any]] = []
    for node_id in node_ids:
        child_node = bundle.ir.nodes[node_id]
        if child_node.execution_config is not None:
            child_step = materialize_execution_config_for_test(
                child_node.execution_config,
                step_name=child_node.presentation_name,
                step_id=child_node.step_id,
            )
        else:
            child_step = {
                "name": child_node.presentation_name,
                "step_id": child_node.step_id,
            }
        child_step["step_id"] = child_node.step_id
        if projection is not None and node_id in projection.nested_presentation_keys:
            child_step["name"] = projection.nested_presentation_keys[node_id]
        elif not isinstance(child_step.get("name"), str) or not child_step["name"]:
            child_step["name"] = child_node.presentation_name
        materialized.append(child_step)
    return materialized


def materialize_projection_step(
    bundle: LoadedWorkflowBundle,
    node_id: str,
) -> dict[str, Any]:
    node = bundle.ir.nodes[node_id]
    if node.execution_config is not None:
        step = materialize_execution_config_for_test(
            node.execution_config,
            step_name=node.presentation_name,
            step_id=node.step_id,
        )
    else:
        step = {
            "name": node.presentation_name,
            "step_id": node.step_id,
        }
    step["step_id"] = node.step_id
    step["name"] = bundle.projection.presentation_key_by_node_id.get(node_id, node.presentation_name)

    if isinstance(node, ForEachNode):
        for_each = step.get("for_each")
        if isinstance(for_each, dict):
            for_each["steps"] = _materialize_loop_steps(
                bundle,
                node.node_id,
                node.body_node_ids,
                loop_kind="for_each",
            )
    elif isinstance(node, RepeatUntilFrameNode):
        repeat_until = step.get("repeat_until")
        if isinstance(repeat_until, dict):
            repeat_until["steps"] = _materialize_loop_steps(
                bundle,
                node.node_id,
                node.body_node_ids,
                loop_kind="repeat_until",
            )

    return step


def materialize_projection_body_steps(bundle: LoadedWorkflowBundle) -> list[dict[str, Any]]:
    return [materialize_projection_step(bundle, node_id) for node_id in bundle.ir.body_region]


def materialize_projection_finalization_steps(bundle: LoadedWorkflowBundle) -> list[dict[str, Any]]:
    return [materialize_projection_step(bundle, node_id) for node_id in bundle.ir.finalization_region]


def thaw_surface_workflow(bundle: LoadedWorkflowBundle) -> dict[str, Any]:
    return _surface_workflow(bundle.surface)


def bundle_context_dict(bundle: LoadedWorkflowBundle) -> dict[str, Any]:
    return _thaw(workflow_context(bundle))
