"""Pure prompt assembly for checked Workflow Lisp provider effects."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from orchestrator.contracts.prompt_contract import (
    render_output_bundle_contract_block,
    render_output_contract_block,
    render_variant_output_contract_block,
)
from orchestrator.deps.content_snapshot import (
    DependencyContentSnapshot,
    render_content_snapshot,
)
from orchestrator.deps.injector import DependencyInjector
from orchestrator.workflow.prompting import (
    PromptComposer,
    append_prompt_block,
    render_prompt_fragment_value,
    substitute_prompt_template,
)
from orchestrator.workflow.evaluated.values import EvaluatedValue
from orchestrator.workflow_lisp.closed.sites import _effect_value_children
from orchestrator.workflow_lisp.typed_prompt_inputs import (
    render_typed_prompt_input_blocks,
)


def _evaluated_values(
    node: Mapping[str, Any], operands: Sequence[EvaluatedValue]
) -> tuple[Any, ...]:
    children = _effect_value_children(dict(node))
    if len(operands) != len(children) or not all(
        isinstance(value, EvaluatedValue) for value in operands
    ):
        raise ValueError("provider operands do not match the checked effect node")
    return tuple(value.json_value() for value in operands)


def _template_base(prompt: Mapping[str, Any], values: Sequence[Any]) -> str:
    fills = prompt.get("fills", ())
    if not isinstance(fills, list) or len(fills) != len(values):
        raise ValueError("checked prompt fills do not match evaluated operands")
    substitutions: dict[str, str] = {}
    for fill, value in zip(fills, values, strict=True):
        if not isinstance(fill, Mapping) or fill.get("kind") == "doc":
            continue
        name = fill.get("name")
        renderer_id = fill.get("renderer_id")
        if not isinstance(name, str) or not isinstance(renderer_id, str):
            raise ValueError("checked prompt fill has no renderer")
        substitutions[name], _rendered = render_prompt_fragment_value(
            renderer_id,
            value,
        )
    template = prompt.get("template")
    if not isinstance(template, str):
        raise ValueError("checked prompt template is invalid")
    return substitute_prompt_template(template, substitutions)


def _dependency_block(
    snapshot: DependencyContentSnapshot | None,
    *,
    instruction: str | None,
    required: bool,
    position: str,
    prompt: str,
) -> str:
    if snapshot is None:
        raise ValueError("captured dependency snapshot is required")
    selected_instruction = instruction
    if selected_instruction is None:
        selected_instruction = DependencyInjector._get_default_instruction(
            "content",
            required,
        )
    rendered = render_content_snapshot(snapshot, instruction=selected_instruction)
    return PromptComposer.apply_rendered_content_dependency(
        prompt,
        rendered,
        position=position,
    )


def _with_dependencies(
    node: Mapping[str, Any],
    fills: Sequence[Mapping[str, Any]],
    prompt: str,
    snapshot: DependencyContentSnapshot | None,
) -> str:
    dependencies = node.get("dependencies")
    if isinstance(dependencies, Mapping):
        required_count = len(dependencies.get("required", ()))
        optional_count = len(dependencies.get("optional", ()))
        if required_count + optional_count:
            return _dependency_block(
                snapshot,
                instruction=dependencies.get("instruction"),
                required=required_count > 0,
                position=str(dependencies.get("position", "prepend")),
                prompt=prompt,
            )
    if any(fill.get("kind") == "doc" for fill in fills):
        return _dependency_block(
            snapshot,
            instruction=None,
            required=True,
            position="prepend",
            prompt=prompt,
        )
    return prompt


def provider_expected_outputs(
    fills: Sequence[Mapping[str, Any]], fill_values: Sequence[Any]
) -> list[dict[str, Any]]:
    """The same output-position rows feed prompt rendering and validation."""
    return [
        {
            "name": fill["name"],
            "path": value,
            "type": "string",
            "required": True,
        }
        for fill, value in zip(fills, fill_values, strict=True)
        if fill.get("output_role") == "required_string_file"
    ]


def _output_contract_prompt(
    prompt: str,
    node: Mapping[str, Any],
    fills: Sequence[Mapping[str, Any]],
    fill_values: Sequence[Any],
    result_path: str,
) -> str:
    expected_outputs = provider_expected_outputs(fills, fill_values)
    contributions: list[tuple[str, str]] = []
    if expected_outputs:
        contributions.append(
            ("output_positions", render_output_contract_block(expected_outputs))
        )
    contract = node.get("contract")
    if isinstance(contract, Mapping):
        payload = contract.get("payload")
        if not isinstance(payload, Mapping):
            raise ValueError("checked provider result contract is invalid")
        contract_payload = {**payload, "path": result_path}
        if contract.get("kind") == "output_bundle":
            block = render_output_bundle_contract_block(contract_payload)
        elif contract.get("kind") == "variant_output":
            block = render_variant_output_contract_block(contract_payload)
        else:
            raise ValueError("checked provider result contract kind is invalid")
        contributions.append(("structured_result", block))
    for _kind, insertion in PromptComposer._output_contract_insertions(
        prompt,
        contributions,
    ):
        prompt += insertion
    return prompt


def assemble_provider_prompt(
    checked_node: Mapping[str, Any],
    evaluated_operands: Sequence[EvaluatedValue],
    *,
    source_text: str | None,
    dependency_snapshot: DependencyContentSnapshot | None,
    result_path: str,
) -> str:
    """Assemble a prompt from one checked provider operation and captured inputs."""

    if checked_node.get("class") != "provider":
        raise TypeError("checked provider effect node required")
    if not isinstance(result_path, str) or not result_path:
        raise ValueError("explicit provider result path is required")
    operand_values = _evaluated_values(checked_node, evaluated_operands)
    input_rows = checked_node.get("inputs", ())
    prompt_data = checked_node.get("prompt")
    if not isinstance(prompt_data, Mapping):
        raise ValueError("checked provider prompt shape is invalid")
    input_values = operand_values[: len(input_rows)]
    fill_rows = prompt_data.get("fills", ())
    fill_start = len(input_rows)
    fill_values = operand_values[fill_start : fill_start + len(fill_rows)]
    if "template" in prompt_data:
        prompt = _template_base(prompt_data, fill_values)
    else:
        if not isinstance(source_text, str):
            raise ValueError("captured provider prompt source text is required")
        prompt = source_text
    typed_rows = [
        (
            str(row[0]),
            str(row[1]),
            1,
            value,
        )
        for row, value in zip(input_rows, input_values, strict=True)
    ]
    typed_block, _rendered = render_typed_prompt_input_blocks(typed_rows)
    prompt = _with_dependencies(
        checked_node,
        tuple(fill for fill in fill_rows if isinstance(fill, Mapping)),
        prompt,
        dependency_snapshot,
    )
    if "template" not in prompt_data:
        prompt = append_prompt_block(prompt, typed_block)
    return _output_contract_prompt(
        prompt,
        checked_node,
        fill_rows,
        fill_values,
        result_path,
    )
