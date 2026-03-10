"""Prompt composition helpers for provider steps."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, Optional

from ..contracts.prompt_contract import (
    render_consumed_artifacts_block,
    render_output_contract_block,
)
from .assets import AssetResolutionError, WorkflowAssetResolver


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
        step: Dict[str, Any],
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
        step: Dict[str, Any],
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

    def apply_output_contract_prompt_suffix(self, step: Dict[str, Any], prompt: str) -> str:
        """Append deterministic output contract instructions to provider prompts."""
        expected_outputs = step.get("expected_outputs")
        if not expected_outputs:
            return prompt

        if step.get("inject_output_contract", True) is False:
            return prompt

        contract_block = render_output_contract_block(expected_outputs)
        if not prompt:
            return contract_block
        if prompt.endswith("\n"):
            return f"{prompt}\n{contract_block}"
        return f"{prompt}\n\n{contract_block}"

    def apply_consumes_prompt_injection(
        self,
        step: Dict[str, Any],
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

        prompt_consumes = step.get("prompt_consumes")
        allowed_names: Optional[set[str]] = None
        if prompt_consumes is not None:
            if not isinstance(prompt_consumes, list):
                return prompt
            allowed_names = {
                name for name in prompt_consumes
                if isinstance(name, str) and name.strip()
            }
            if not allowed_names:
                return prompt

        reserved_session_artifact: Optional[str] = None
        provider_session = step.get("provider_session")
        if isinstance(provider_session, dict) and provider_session.get("mode") == "resume":
            session_id_from = provider_session.get("session_id_from")
            if isinstance(session_id_from, str) and session_id_from:
                reserved_session_artifact = session_id_from

        consumed_values: Dict[str, Any] = {}
        for key, value in step_consumed_values.items():
            if not isinstance(key, str):
                continue
            if reserved_session_artifact is not None and key == reserved_session_artifact:
                continue
            if allowed_names is not None and key not in allowed_names:
                continue
            if isinstance(value, (str, int, float, bool)):
                consumed_values[key] = value

        if not consumed_values:
            return prompt

        consumes_guidance: Dict[str, Dict[str, str]] = {}
        for consume in consumes:
            if not isinstance(consume, dict):
                continue
            artifact_name = consume.get("artifact")
            if not isinstance(artifact_name, str):
                continue
            if artifact_name not in consumed_values:
                continue

            guidance: Dict[str, str] = {}
            for guidance_key in ("description", "format_hint", "example"):
                guidance_value = consume.get(guidance_key)
                if isinstance(guidance_value, str):
                    guidance[guidance_key] = guidance_value
            if guidance:
                consumes_guidance[artifact_name] = guidance

        consumes_block = render_consumed_artifacts_block(consumed_values, consumes_guidance)
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
