"""Prompt composition helpers for provider steps."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Optional, TypeVar

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


_RenderOwner = TypeVar("_RenderOwner")


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
        if expected_outputs:
            contract_block = render_output_contract_block(expected_outputs)
        elif isinstance(output_bundle, dict) and output_bundle:
            contract_block = render_output_bundle_contract_block(output_bundle)
        elif isinstance(variant_output, dict) and variant_output:
            contract_block = render_variant_output_contract_block(variant_output)
        else:
            return prompt

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
        if position == "prepend":
            return f"{block}\n\n{prompt}" if prompt else block
        if position == "append":
            return f"{prompt}\n\n{block}" if prompt else block
        raise ValueError("invalid_injection_contract")

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
