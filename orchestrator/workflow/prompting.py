"""Prompt composition helpers for provider steps."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from hashlib import sha256
from pathlib import Path
from types import MappingProxyType
from typing import Any, Callable, Dict, Mapping, Optional, TypeVar

from ..deps.content_snapshot import (
    DependencyContentSnapshot,
    RenderedContentSnapshot,
    render_content_snapshot,
)

from ..contracts.prompt_contract import (
    render_consumed_artifacts_block,
    render_output_bundle_contract_block,
    render_output_contract_block,
    render_variant_output_contract_block,
    RenderedConsumedArtifact,
    selected_consumed_artifacts_for_prompt,
    stringify_consumed_value,
)
from .assets import AssetResolutionError, WorkflowAssetResolver
from .executor_runtime import RuntimeStepInput
from .prompt_fragment_contract import (
    CompilerPromptAttemptBindingPlan,
    CompilerPromptFragmentContract,
    validate_compiler_prompt_attempt_binding_plan,
    validate_compiler_prompt_fragment_contract,
)
from .pure_expr import canonical_json_for_pure_value
from .view_renderer import (
    ViewRendererError,
    render_view,
    view_bytes_digest,
)


_RenderOwner = TypeVar("_RenderOwner")


@dataclass(frozen=True)
class PromptFragmentRenderTraceRow:
    """Content-free metadata for one target-2.22 rendered fragment slot."""

    rendered_slot_ordinal: int
    slot_name: str
    renderer: Mapping[str, Any]
    value_sha256: str
    raw_renderer_bytes_sha256: str
    substitution_bytes: int
    substitution_bytes_sha256: str

    def __post_init__(self) -> None:
        if (
            type(self.rendered_slot_ordinal) is not int
            or self.rendered_slot_ordinal < 0
            or not isinstance(self.slot_name, str)
            or not self.slot_name
        ):
            raise ValueError(
                "prompt_attempt_binding_plan_invalid: "
                "fragment render trace slot identity is invalid"
            )
        renderer = self.renderer
        if (
            not isinstance(renderer, Mapping)
            or set(renderer) != {"renderer_id", "renderer_version"}
            or not isinstance(renderer.get("renderer_id"), str)
            or not renderer["renderer_id"]
            or type(renderer.get("renderer_version")) is not int
            or renderer["renderer_version"] != 1
        ):
            raise ValueError(
                "prompt_attempt_binding_plan_invalid: "
                "fragment render trace renderer is invalid"
            )
        object.__setattr__(
            self,
            "renderer",
            MappingProxyType(dict(renderer)),
        )
        for field_name in (
            "value_sha256",
            "raw_renderer_bytes_sha256",
            "substitution_bytes_sha256",
        ):
            if not _is_sha256(getattr(self, field_name)):
                raise ValueError(
                    "prompt_attempt_binding_plan_invalid: "
                    f"fragment render trace {field_name} is invalid"
                )
        if (
            type(self.substitution_bytes) is not int
            or self.substitution_bytes < 0
        ):
            raise ValueError(
                "prompt_attempt_binding_plan_invalid: "
                "fragment render trace substitution length is invalid"
            )


@dataclass(frozen=True)
class PromptFragmentRenderResult:
    """One target-2.22 base prompt and its immutable one-render trace."""

    rendered_base: str
    trace: tuple[PromptFragmentRenderTraceRow, ...]
    _trace_sha256: str = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        if not isinstance(self.rendered_base, str):
            raise TypeError(
                "prompt fragment rendered base must be a string"
            )
        if not isinstance(self.trace, tuple) or any(
            type(row) is not PromptFragmentRenderTraceRow
            for row in self.trace
        ):
            raise ValueError(
                "prompt_attempt_binding_plan_invalid: "
                "fragment render trace must be an immutable row tuple"
            )
        if not _is_sha256(self._trace_sha256):
            raise ValueError(
                "prompt_attempt_binding_plan_invalid: "
                "fragment render trace seal is invalid"
            )


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 71
        and value.startswith("sha256:")
        and all(character in "0123456789abcdef" for character in value[7:])
    )


def _trace_projection(
    trace: tuple[PromptFragmentRenderTraceRow, ...],
) -> list[dict[str, Any]]:
    return [
        {
            "rendered_slot_ordinal": row.rendered_slot_ordinal,
            "slot_name": row.slot_name,
            "renderer": dict(row.renderer),
            "value_sha256": row.value_sha256,
            "raw_renderer_bytes_sha256": (
                row.raw_renderer_bytes_sha256
            ),
            "substitution_bytes": row.substitution_bytes,
            "substitution_bytes_sha256": (
                row.substitution_bytes_sha256
            ),
        }
        for row in trace
    ]


def _trace_sha256(
    trace: tuple[PromptFragmentRenderTraceRow, ...],
) -> str:
    payload = json.dumps(
        _trace_projection(trace),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return view_bytes_digest(payload)


def prompt_fragment_transport_value_sha256(value: Any) -> str:
    """Return the canonical transport-value digest for one fragment slot."""

    if isinstance(value, str):
        try:
            payload = value.encode("utf-8", errors="strict")
        except UnicodeEncodeError as exc:
            raise ValueError(
                "prompt fragment value is not valid UTF-8"
            ) from exc
    else:
        try:
            payload = canonical_json_for_pure_value(value).encode(
                "utf-8",
                errors="strict",
            )
        except Exception as exc:
            raise ValueError(
                "prompt fragment value is not transportable"
            ) from exc
    return f"sha256:{sha256(payload).hexdigest()}"


def _target_supports_fragment_trace(
    target_dsl_version: str | None,
) -> bool:
    if target_dsl_version is None:
        return False
    try:
        parts = tuple(
            int(part) for part in target_dsl_version.split(".")
        )
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValueError(
            "prompt_attempt_binding_plan_invalid: "
            "target DSL version is invalid"
        ) from exc
    if not parts:
        raise ValueError(
            "prompt_attempt_binding_plan_invalid: "
            "target DSL version is invalid"
        )
    return parts >= (2, 22)


def _validated_trace_plan_rows(
    contract: CompilerPromptFragmentContract,
    plan: CompilerPromptAttemptBindingPlan,
) -> tuple[Any, ...]:
    try:
        validate_compiler_prompt_attempt_binding_plan(plan)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "prompt_attempt_binding_plan_invalid: "
            "fragment render binding plan is invalid"
        ) from exc
    rendered_plan_rows = tuple(
        row for row in plan.rows if row.slot_kind != "doc"
    )
    if len(rendered_plan_rows) != len(contract.rendered_slots):
        raise ValueError(
            "prompt_attempt_binding_plan_invalid: "
            "fragment render trace coverage is invalid"
        )
    for rendered_slot_ordinal, (plan_row, slot) in enumerate(
        zip(
            rendered_plan_rows,
            contract.rendered_slots,
            strict=True,
        )
    ):
        if (
            plan_row.slot_name != slot.name
            or plan_row.slot_kind != slot.kind
            or plan_row.runtime_source
            != {
                "kind": "rendered_slot",
                "ordinal": rendered_slot_ordinal,
            }
            or plan_row.renderer
            != {
                "renderer_id": slot.renderer_id,
                "renderer_version": 1,
            }
        ):
            raise ValueError(
                "prompt_attempt_binding_plan_invalid: "
                "fragment render trace disagrees with binding plan"
            )
    return rendered_plan_rows


def validate_prompt_fragment_render_trace(
    result: PromptFragmentRenderResult,
    *,
    compiler_prompt_attempt_binding_plan: CompilerPromptAttemptBindingPlan,
) -> tuple[PromptFragmentRenderTraceRow, ...]:
    """Validate one sealed trace against its compiler-owned binding plan."""

    if type(result) is not PromptFragmentRenderResult:
        raise ValueError(
            "prompt_attempt_binding_plan_invalid: "
            "target-2.22 fragment render result is missing"
        )
    try:
        validate_compiler_prompt_attempt_binding_plan(
            compiler_prompt_attempt_binding_plan
        )
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "prompt_attempt_binding_plan_invalid: "
            "fragment render binding plan is invalid"
        ) from exc
    trace = result.trace
    if _trace_sha256(trace) != result._trace_sha256:
        raise ValueError(
            "prompt_attempt_binding_plan_invalid: "
            "fragment render trace seal mismatch"
        )
    rendered_plan_rows = tuple(
        row
        for row in compiler_prompt_attempt_binding_plan.rows
        if row.slot_kind != "doc"
    )
    if len(trace) != len(rendered_plan_rows):
        raise ValueError(
            "prompt_attempt_binding_plan_invalid: "
            "fragment render trace coverage is invalid"
        )
    for rendered_slot_ordinal, (trace_row, plan_row) in enumerate(
        zip(trace, rendered_plan_rows, strict=True)
    ):
        if (
            trace_row.rendered_slot_ordinal
            != rendered_slot_ordinal
            or trace_row.slot_name != plan_row.slot_name
            or trace_row.renderer != plan_row.renderer
            or plan_row.runtime_source
            != {
                "kind": "rendered_slot",
                "ordinal": rendered_slot_ordinal,
            }
        ):
            raise ValueError(
                "prompt_attempt_binding_plan_invalid: "
                "fragment render trace order or identity is invalid"
            )
    return trace


def render_prompt_fragment_base(
    contract: CompilerPromptFragmentContract,
    *,
    resolved_slot_values: Dict[str, Any],
    target_dsl_version: str | None = None,
    compiler_prompt_attempt_binding_plan: (
        CompilerPromptAttemptBindingPlan | None
    ) = None,
) -> str | PromptFragmentRenderResult:
    """Render one closed fragment contract into its in-memory base prompt."""

    validate_compiler_prompt_fragment_contract(contract)
    trace_required = _target_supports_fragment_trace(
        target_dsl_version
    )
    if trace_required:
        if compiler_prompt_attempt_binding_plan is None:
            raise ValueError(
                "prompt_attempt_binding_plan_invalid: "
                "target-2.22 fragment render requires the binding plan"
            )
        _validated_trace_plan_rows(
            contract,
            compiler_prompt_attempt_binding_plan,
        )
    elif compiler_prompt_attempt_binding_plan is not None:
        raise ValueError(
            "prompt_attempt_binding_plan_invalid: "
            "fragment render binding plan requires target DSL 2.22"
        )
    if not isinstance(resolved_slot_values, dict):
        raise TypeError("resolved prompt fragment slot values must be a mapping")
    slot_names = tuple(slot.name for slot in contract.rendered_slots)
    if set(resolved_slot_values) != set(slot_names):
        raise ValueError(
            "resolved prompt fragment slot values must contain exactly "
            "the declared rendered slots"
        )

    rendered_by_name: dict[str, str] = {}
    trace_rows: list[PromptFragmentRenderTraceRow] = []
    for rendered_slot_ordinal, slot in enumerate(
        contract.rendered_slots
    ):
        value = resolved_slot_values[slot.name]
        if slot.renderer_id == "raw-utf8-string":
            if not isinstance(value, str):
                raise TypeError(
                    "raw-utf8-string prompt fragment values must be strings"
                )
            try:
                value.encode("utf-8", errors="strict")
            except UnicodeEncodeError as exc:
                raise ValueError(
                    "raw-utf8-string prompt fragment value is not valid UTF-8"
                ) from exc
            rendered_by_name[slot.name] = value
            if trace_required:
                raw_bytes = value.encode("utf-8", errors="strict")
                trace_rows.append(
                    PromptFragmentRenderTraceRow(
                        rendered_slot_ordinal=rendered_slot_ordinal,
                        slot_name=slot.name,
                        renderer={
                            "renderer_id": slot.renderer_id,
                            "renderer_version": 1,
                        },
                        value_sha256=(
                            prompt_fragment_transport_value_sha256(value)
                        ),
                        raw_renderer_bytes_sha256=(
                            view_bytes_digest(raw_bytes)
                        ),
                        substitution_bytes=len(raw_bytes),
                        substitution_bytes_sha256=(
                            view_bytes_digest(raw_bytes)
                        ),
                    )
                )
            continue
        try:
            rendered = render_view(slot.renderer_id, 1, value)
        except ViewRendererError as exc:
            raise ValueError(
                f"{slot.renderer_id} prompt fragment rendering failed: {exc}"
            ) from exc
        try:
            substitution_text = (
                rendered.decode("utf-8", errors="strict").removesuffix("\n")
            )
        except UnicodeDecodeError as exc:
            raise ValueError(
                f"{slot.renderer_id} prompt fragment renderer returned invalid UTF-8"
            ) from exc
        rendered_by_name[slot.name] = substitution_text
        if trace_required:
            substitution_bytes = substitution_text.encode(
                "utf-8",
                errors="strict",
            )
            trace_rows.append(
                PromptFragmentRenderTraceRow(
                    rendered_slot_ordinal=rendered_slot_ordinal,
                    slot_name=slot.name,
                    renderer={
                        "renderer_id": slot.renderer_id,
                        "renderer_version": 1,
                    },
                    value_sha256=(
                        prompt_fragment_transport_value_sha256(value)
                    ),
                    raw_renderer_bytes_sha256=(
                        view_bytes_digest(rendered)
                    ),
                    substitution_bytes=len(substitution_bytes),
                    substitution_bytes_sha256=(
                        view_bytes_digest(substitution_bytes)
                    ),
                )
            )

    output: list[str] = []
    template = contract.template_utf8
    index = 0
    while index < len(template):
        character = template[index]
        if character == "{":
            if index + 1 < len(template) and template[index + 1] == "{":
                output.append("{")
                index += 2
                continue
            closing = template.find("}", index + 1)
            if closing < 0:
                raise ValueError(
                    "compiler_prompt_fragment_contract_invalid: "
                    "malformed template placeholder"
                )
            name = template[index + 1 : closing]
            try:
                output.append(rendered_by_name[name])
            except KeyError as exc:
                raise ValueError(
                    "compiler_prompt_fragment_contract_invalid: "
                    "template placeholder has no rendered slot"
                ) from exc
            index = closing + 1
            continue
        if character == "}":
            if index + 1 < len(template) and template[index + 1] == "}":
                output.append("}")
                index += 2
                continue
            raise ValueError(
                "compiler_prompt_fragment_contract_invalid: "
                "malformed template placeholder"
            )
        output.append(character)
        index += 1
    rendered_base = "".join(output)
    if not trace_required:
        return rendered_base
    trace = tuple(trace_rows)
    return PromptFragmentRenderResult(
        rendered_base=rendered_base,
        trace=trace,
        _trace_sha256=_trace_sha256(trace),
    )


class PromptCompletionError(Exception):
    """A failure after dependency injection while completing the final prompt."""


@dataclass(frozen=True)
class ContentDependencyAttemptComposition:
    """One attempt's render, final UTF-8 prompt, debug view, and owner result."""

    rendered: RenderedContentSnapshot
    final_prompt: bytes
    debug_injection: dict[str, Any] | None
    render_owner_result: Any = None


class PromptComposer:
    """Compose provider prompt inputs without owning executor state transitions."""

    def __init__(
        self,
        *,
        workspace: Path,
        asset_resolver: Optional[WorkflowAssetResolver],
    ) -> None:
        self.workspace = workspace
        self.asset_resolver = asset_resolver

    def read_prompt_source(
        self,
        step: RuntimeStepInput,
        *,
        step_name: str,
        contract_violation_result: Callable[[str, Dict[str, Any]], Dict[str, Any]],
    ) -> tuple[str, Optional[Dict[str, Any]]]:
        """Read either a workspace-relative input file or a source-relative asset."""
        if "asset_file" in step:
            if self.asset_resolver is None:
                return "", contract_violation_result(
                    "Provider prompt asset resolution failed",
                    {
                        "step": step_name,
                        "reason": "missing_workflow_source_root",
                    },
                )
            try:
                return self.asset_resolver.read_text(step["asset_file"]), None
            except (AssetResolutionError, OSError) as exc:
                return "", contract_violation_result(
                    "Provider prompt asset resolution failed",
                    {
                        "step": step_name,
                        "reason": "asset_file_read_failed",
                        "path": step.get("asset_file"),
                        "error": str(exc),
                    },
                )

        prompt = ""
        if "input_file" in step:
            input_path = self.workspace / step["input_file"]
            if input_path.exists():
                prompt = input_path.read_text()
        return prompt, None

    def apply_asset_depends_on_prompt_injection(
        self,
        step: RuntimeStepInput,
        prompt: str,
        *,
        step_name: str,
        contract_violation_result: Callable[[str, Dict[str, Any]], Dict[str, Any]],
    ) -> tuple[str, Optional[Dict[str, Any]]]:
        """Inject source-relative asset files into the composed provider prompt."""
        asset_depends_on = step.get("asset_depends_on")
        if not asset_depends_on:
            return prompt, None
        if self.asset_resolver is None:
            return prompt, contract_violation_result(
                "Provider prompt asset resolution failed",
                {
                    "step": step_name,
                    "reason": "missing_workflow_source_root",
                },
            )

        try:
            assets_block = self.asset_resolver.render_content_blocks(asset_depends_on)
        except (AssetResolutionError, OSError) as exc:
            return prompt, contract_violation_result(
                "Provider prompt asset resolution failed",
                {
                    "step": step_name,
                    "reason": "asset_depends_on_read_failed",
                    "paths": list(asset_depends_on) if isinstance(asset_depends_on, list) else asset_depends_on,
                    "error": str(exc),
                },
            )

        if not assets_block:
            return prompt, None
        if not prompt:
            return assets_block, None
        return f"{assets_block}\n\n{prompt}", None

    def apply_output_contract_prompt_suffix(self, step: RuntimeStepInput, prompt: str) -> str:
        """Append deterministic output contract instructions to provider prompts."""
        if step.get("inject_output_contract", True) is False:
            return prompt

        expected_outputs = step.get("expected_outputs")
        output_bundle = step.get("output_bundle")
        variant_output = step.get("variant_output")
        contract_blocks: list[str] = []
        if expected_outputs:
            contract_blocks.append(render_output_contract_block(expected_outputs))
        if isinstance(output_bundle, dict) and output_bundle:
            contract_blocks.append(render_output_bundle_contract_block(output_bundle))
        elif isinstance(variant_output, dict) and variant_output:
            contract_blocks.append(render_variant_output_contract_block(variant_output))
        if not contract_blocks:
            return prompt
        contract_block = "\n\n".join(contract_blocks)

        if not prompt:
            return contract_block
        if prompt.endswith("\n"):
            return f"{prompt}\n{contract_block}"
        return f"{prompt}\n\n{contract_block}"

    @staticmethod
    def apply_rendered_content_dependency(
        prompt: str,
        rendered: RenderedContentSnapshot,
        *,
        position: str,
    ) -> str:
        """Insert one already-rendered immutable content block."""

        if not isinstance(rendered, RenderedContentSnapshot):
            raise TypeError("RenderedContentSnapshot required")
        try:
            block = rendered.block.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError("rendered dependency block must be UTF-8") from exc
        if position not in {"prepend", "append"}:
            raise ValueError("invalid_injection_contract")
        if not block:
            return prompt
        if position == "prepend":
            return f"{block}\n\n{prompt}" if prompt else block
        return f"{prompt}\n\n{block}" if prompt else block

    @staticmethod
    def content_dependency_debug(
        rendered: RenderedContentSnapshot,
    ) -> dict[str, Any] | None:
        """Project truncation into the established provider-result debug shape."""

        if not rendered.was_truncated:
            return None
        rows = rendered.group_truncations
        return {
            "injection_truncated": True,
            "truncation_details": {
                "total_size": sum(row.total_bytes for row in rows),
                "shown_size": sum(row.shown_bytes for row in rows),
                "files_shown": sum(row.status != "omitted" for row in rows),
                "files_truncated": sum(row.status == "truncated" for row in rows),
                "files_omitted": sum(row.status == "omitted" for row in rows),
            },
        }

    def compose_content_dependency_attempt(
        self,
        *,
        base_prompt: str,
        snapshot: DependencyContentSnapshot,
        instruction: str,
        position: str,
        finish_prompt: Callable[[str], str],
        render_owner: Callable[[Callable[[RenderedContentSnapshot], bytes]], _RenderOwner]
        | None = None,
    ) -> ContentDependencyAttemptComposition:
        """Own one render and every later prompt stage for one provider attempt."""

        def compose_from_render(rendered: RenderedContentSnapshot) -> bytes:
            injected = self.apply_rendered_content_dependency(
                base_prompt,
                rendered,
                position=position,
            )
            try:
                final = finish_prompt(injected)
                if not isinstance(final, str):
                    raise TypeError("finish_prompt must return a string")
                return final.encode("utf-8", errors="strict")
            except (TypeError, ValueError, OSError) as exc:
                raise PromptCompletionError(str(exc)) from exc

        owner_result: Any = None
        if render_owner is None:
            rendered = render_content_snapshot(snapshot, instruction=instruction)
            final_prompt = compose_from_render(rendered)
        else:
            owner_result = render_owner(compose_from_render)
            rendered = getattr(owner_result, "rendered", None)
            final_prompt = getattr(owner_result, "final_prompt", None)
            if not isinstance(rendered, RenderedContentSnapshot) or type(final_prompt) is not bytes:
                raise TypeError("render owner returned an invalid composition result")
        return ContentDependencyAttemptComposition(
            rendered=rendered,
            final_prompt=final_prompt,
            debug_injection=self.content_dependency_debug(rendered),
            render_owner_result=owner_result,
        )

    def apply_consumes_prompt_injection(
        self,
        step: RuntimeStepInput,
        prompt: str,
        *,
        resolved_consumes: Dict[str, Any],
        step_name: str,
        consume_identity: str,
        uses_qualified_identities: bool,
    ) -> str:
        """Inject resolved consume values into provider prompts."""
        if step.get("inject_consumes", True) is False:
            return prompt

        consumes = step.get("consumes")
        if not isinstance(consumes, list) or not consumes:
            return prompt

        if not isinstance(resolved_consumes, dict):
            return prompt

        step_consumed_values = resolved_consumes.get(step_name, {})
        if uses_qualified_identities and (not isinstance(step_consumed_values, dict) or not step_consumed_values):
            step_consumed_values = resolved_consumes.get(consume_identity, {})
        if not isinstance(step_consumed_values, dict) or not step_consumed_values:
            return prompt

        selected_consumes = selected_consumed_artifacts_for_prompt(step, step_consumed_values)
        if not selected_consumes:
            return prompt

        rendered_consumes: list[RenderedConsumedArtifact] = []
        for policy, raw_value in selected_consumes:
            rendered_value = stringify_consumed_value(raw_value)
            if rendered_value is None or policy.mode == "none":
                continue
            rendered_consumes.append(
                RenderedConsumedArtifact(
                    artifact_name=policy.artifact_name,
                    mode=policy.mode,
                    rendered_value=rendered_value,
                    label=policy.label,
                    description=policy.description,
                    format_hint=policy.format_hint,
                    example=policy.example,
                    role=policy.role,
                )
            )

        if not rendered_consumes:
            return prompt

        consumes_block = render_consumed_artifacts_block(rendered_consumes)
        position = step.get("consumes_injection_position", "prepend")
        if position == "append":
            if not prompt:
                return consumes_block
            if prompt.endswith("\n"):
                return f"{prompt}\n{consumes_block}"
            return f"{prompt}\n\n{consumes_block}"

        if not prompt:
            return consumes_block
        if prompt.startswith("\n"):
            return f"{consumes_block}{prompt}"
        return f"{consumes_block}\n{prompt}"

    def apply_typed_prompt_input_injection(
        self,
        step: RuntimeStepInput,
        prompt: str,
        *,
        typed_prompt_inputs: list[dict[str, Any]] | tuple[dict[str, Any], ...],
        resolved_typed_values: Dict[str, Any],
        workflow_name: str,
        step_id: str,
    ) -> tuple[str, list[dict[str, Any]]]:
        """Inject rendered typed prompt inputs into one provider prompt."""

        if not typed_prompt_inputs:
            return prompt, []
        from ..workflow_lisp.typed_prompt_inputs import render_typed_prompt_inputs

        rendered_block, evidence = render_typed_prompt_inputs(
            typed_prompt_inputs,
            resolved_typed_values=resolved_typed_values,
            workflow_name=workflow_name,
            step_id=step_id,
        )
        if not rendered_block:
            return prompt, evidence
        if not prompt:
            return rendered_block, evidence
        if prompt.endswith("\n"):
            return f"{prompt}\n{rendered_block}", evidence
        return f"{prompt}\n\n{rendered_block}", evidence
