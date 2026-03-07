"""Lower structured workflow statements to executable step nodes."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, Iterable, List

from .identity import assign_step_ids
from .predicates import TYPED_PREDICATE_OPERATOR_KEYS
from .statements import branch_token, is_if_statement, normalize_branch_block


def lower_structured_steps(steps: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Lower top-level structured statements into flat executable steps."""
    lowered: List[Dict[str, Any]] = []
    for step in steps:
        if not is_if_statement(step):
            lowered.append(step)
            continue
        lowered.extend(_lower_if_statement(step))
    return lowered


def _lower_if_statement(step: Dict[str, Any]) -> List[Dict[str, Any]]:
    statement_name = step["name"]
    statement_step_id = step["step_id"]
    condition = deepcopy(step["if"])

    lowered: List[Dict[str, Any]] = []
    branch_metadata: Dict[str, Dict[str, Any]] = {}

    for branch_name in ("then", "else"):
        branch = normalize_branch_block(step.get(branch_name), branch_name)
        if branch is None:
            continue

        branch_steps = deepcopy(branch.get("steps") or [])
        branch_step_id = f"{statement_step_id}.{branch_token(branch_name, branch)}"
        assign_step_ids(branch_steps, parent_step_id=branch_step_id)
        local_name_map = {
            nested_step["name"]: f"{statement_name}.{branch_name}.{nested_step['name']}"
            for nested_step in branch_steps
            if isinstance(nested_step, dict) and isinstance(nested_step.get("name"), str)
        }
        marker_name = f"{statement_name}.{branch_name}"
        guard = {
            "condition": deepcopy(condition),
            "invert": branch_name == "else",
            "statement_name": statement_name,
            "branch_name": branch_name,
        }

        lowered.append(
            {
                "name": marker_name,
                "step_id": branch_step_id,
                "structured_if_branch": {
                    "statement_name": statement_name,
                    "branch_name": branch_name,
                },
                "structured_if_guard": deepcopy(guard),
            }
        )

        branch_step_names: List[str] = []
        for branch_step in branch_steps:
            if not isinstance(branch_step, dict):
                continue
            original_name = branch_step.get("name")
            lowered_name = local_name_map.get(original_name, original_name)
            if isinstance(lowered_name, str):
                branch_step["name"] = lowered_name
            branch_step["structured_if_guard"] = deepcopy(guard)
            _rewrite_step_structured_refs(branch_step, local_name_map)
            branch_step_names.append(branch_step["name"])
            lowered.append(branch_step)

        outputs = deepcopy(branch.get("outputs") or {})
        _rewrite_output_refs(outputs, local_name_map)
        branch_metadata[branch_name] = {
            "marker": marker_name,
            "step_id": branch_step_id,
            "steps": branch_step_names,
            "outputs": outputs,
        }

    lowered.append(
        {
            "name": statement_name,
            "step_id": statement_step_id,
            "structured_if_join": {
                "statement_name": statement_name,
                "branches": branch_metadata,
            },
        }
    )
    return lowered


def _rewrite_step_structured_refs(step: Dict[str, Any], local_name_map: Dict[str, str]) -> None:
    """Rewrite branch-local structured refs on lowered executable steps."""
    for field_name in ("when", "assert"):
        if field_name in step:
            step[field_name] = _rewrite_condition_structured_refs(step[field_name], local_name_map)
    for field_name in ("command", "input_file", "output_file", "provider_params"):
        if field_name in step:
            step[field_name] = _rewrite_legacy_step_variables(step[field_name], local_name_map)


def _rewrite_condition_structured_refs(node: Any, local_name_map: Dict[str, str]) -> Any:
    if not isinstance(node, dict):
        return _rewrite_legacy_step_variables(node, local_name_map)

    if any(key in node for key in TYPED_PREDICATE_OPERATOR_KEYS):
        return _rewrite_typed_predicate(node, local_name_map)

    rewritten = deepcopy(node)
    if "equals" in rewritten and isinstance(rewritten["equals"], dict):
        equals = dict(rewritten["equals"])
        for side in ("left", "right"):
            value = equals.get(side)
            if isinstance(value, dict):
                equals[side] = _rewrite_typed_predicate(value, local_name_map)
        rewritten["equals"] = equals
    return _rewrite_legacy_step_variables(rewritten, local_name_map)


def _rewrite_typed_predicate(node: Any, local_name_map: Dict[str, str]) -> Any:
    if not isinstance(node, dict):
        return node

    rewritten = deepcopy(node)

    if "artifact_bool" in rewritten and isinstance(rewritten["artifact_bool"], dict):
        ref = rewritten["artifact_bool"].get("ref")
        rewritten["artifact_bool"]["ref"] = _rewrite_structured_ref(ref, local_name_map)
        return rewritten

    if "compare" in rewritten and isinstance(rewritten["compare"], dict):
        compare = dict(rewritten["compare"])
        for side in ("left", "right"):
            operand = compare.get(side)
            if isinstance(operand, dict) and "ref" in operand:
                compare[side] = {
                    "ref": _rewrite_structured_ref(operand.get("ref"), local_name_map)
                }
        rewritten["compare"] = compare
        return rewritten

    if "all_of" in rewritten and isinstance(rewritten["all_of"], list):
        rewritten["all_of"] = [
            _rewrite_typed_predicate(item, local_name_map) for item in rewritten["all_of"]
        ]
        return rewritten

    if "any_of" in rewritten and isinstance(rewritten["any_of"], list):
        rewritten["any_of"] = [
            _rewrite_typed_predicate(item, local_name_map) for item in rewritten["any_of"]
        ]
        return rewritten

    if "not" in rewritten:
        rewritten["not"] = _rewrite_typed_predicate(rewritten["not"], local_name_map)
        return rewritten

    return rewritten


def _rewrite_output_refs(outputs: Dict[str, Any], local_name_map: Dict[str, str]) -> None:
    for spec in outputs.values():
        if not isinstance(spec, dict):
            continue
        binding = spec.get("from")
        if not isinstance(binding, dict) or "ref" not in binding:
            continue
        binding["ref"] = _rewrite_structured_ref(binding.get("ref"), local_name_map)


def _rewrite_structured_ref(ref: Any, local_name_map: Dict[str, str]) -> Any:
    if not isinstance(ref, str):
        return ref
    if ref.startswith("parent.steps."):
        return f"root.steps.{ref[len('parent.steps.'):]}"
    if not ref.startswith("self.steps."):
        return ref

    remainder = ref[len("self.steps."):]
    for original_name in sorted(local_name_map.keys(), key=len, reverse=True):
        prefix = f"{original_name}."
        if not remainder.startswith(prefix):
            continue
        suffix = remainder[len(prefix):]
        return f"root.steps.{local_name_map[original_name]}.{suffix}"
    return ref


def _rewrite_legacy_step_variables(value: Any, local_name_map: Dict[str, str]) -> Any:
    if isinstance(value, str):
        rewritten = value
        for original_name in sorted(local_name_map.keys(), key=len, reverse=True):
            rewritten = rewritten.replace(
                f"${{steps.{original_name}.",
                f"${{steps.{local_name_map[original_name]}.",
            )
        return rewritten
    if isinstance(value, list):
        return [_rewrite_legacy_step_variables(item, local_name_map) for item in value]
    if isinstance(value, dict):
        return {
            key: _rewrite_legacy_step_variables(item, local_name_map)
            for key, item in value.items()
        }
    return value
