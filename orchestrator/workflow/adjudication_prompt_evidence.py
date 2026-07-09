"""Consumed-artifact evidence selection for adjudication prompts."""

from __future__ import annotations

from typing import Any, Callable, Dict, Mapping

from ..contracts.prompt_contract import selected_consumed_artifacts_for_prompt


def adjudication_consumed_artifacts_for_prompt(
    step: Dict[str, Any],
    state: Dict[str, Any],
    *,
    step_name: str,
    consume_identity: str,
    uses_qualified_identities: Callable[[], bool],
    workflow_artifacts: Mapping[str, Any],
    private_workflow_artifacts: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, str]]:
    """Select evaluator evidence without depending on the executor object."""
    if step.get("inject_consumes", True) is False:
        return {}, {}
    consumes = step.get("consumes")
    if not isinstance(consumes, list) or not consumes:
        return {}, {}
    resolved_consumes = state.get("_resolved_consumes", {})
    if not isinstance(resolved_consumes, dict):
        return {}, {}

    step_consumed_values = resolved_consumes.get(step_name, {})
    if uses_qualified_identities() and (
        not isinstance(step_consumed_values, dict) or not step_consumed_values
    ):
        step_consumed_values = resolved_consumes.get(consume_identity, {})
    if not isinstance(step_consumed_values, dict) or not step_consumed_values:
        return {}, {}
    selected_consumes = selected_consumed_artifacts_for_prompt(step, step_consumed_values)
    if not selected_consumes:
        return {}, {}

    injected_values: dict[str, Any] = {}
    for policy, value in selected_consumes:
        if isinstance(value, (str, int, float, bool, list, dict)):
            injected_values[policy.artifact_name] = value

    relpath_targets: dict[str, str] = {}
    for consume in consumes:
        if not isinstance(consume, dict):
            continue
        artifact_name = consume.get("artifact")
        if not isinstance(artifact_name, str) or artifact_name not in injected_values:
            continue
        artifact_spec = workflow_artifacts.get(artifact_name)
        if not isinstance(artifact_spec, dict):
            artifact_spec = private_workflow_artifacts.get(artifact_name, {})
        artifact_kind = "relpath"
        if isinstance(artifact_spec, dict) and isinstance(artifact_spec.get("kind"), str):
            artifact_kind = artifact_spec["kind"]
        value = injected_values[artifact_name]
        if artifact_kind == "relpath" and isinstance(artifact_spec, dict) and isinstance(value, str):
            relpath_targets[artifact_name] = value
    return injected_values, relpath_targets
