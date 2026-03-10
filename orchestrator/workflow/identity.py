"""Stable workflow step identity helpers."""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable, Tuple

from .statements import (
    branch_token,
    finally_block_token,
    is_if_statement,
    is_match_statement,
    match_case_token,
    normalize_branch_block,
    normalize_finally_block,
    normalize_match_case_block,
)


STEP_ID_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")
_NON_ALNUM_RE = re.compile(r"[^A-Za-z0-9]+")


def authored_id_is_valid(value: Any) -> bool:
    """Return True when an authored stable id matches the DSL contract."""
    return isinstance(value, str) and bool(STEP_ID_PATTERN.fullmatch(value))


def assign_step_ids(steps: Iterable[Dict[str, Any]], parent_step_id: str = "root") -> None:
    """Annotate steps recursively with stable internal step ids."""
    used_tokens = {
        step.get("id")
        for step in steps
        if isinstance(step, dict) and authored_id_is_valid(step.get("id"))
    }
    for index, step in enumerate(steps):
        if not isinstance(step, dict):
            continue

        token = step.get("id")
        if not authored_id_is_valid(token):
            token = _dedupe_token(_compiler_token(step, index), used_tokens)
        else:
            used_tokens.add(token)

        step_id = f"{parent_step_id}.{token}"
        step["step_id"] = step_id

        if is_if_statement(step):
            for branch_name in ("then", "else"):
                branch = normalize_branch_block(step.get(branch_name), branch_name)
                if branch is None:
                    continue
                nested_steps = branch.get("steps")
                if isinstance(nested_steps, list):
                    assign_step_ids(
                        nested_steps,
                        parent_step_id=f"{step_id}.{branch_token(branch_name, branch)}",
                    )
            continue

        if is_match_statement(step):
            match = step.get("match")
            cases = match.get("cases") if isinstance(match, dict) else {}
            if not isinstance(cases, dict):
                continue
            for case_name, authored_case in cases.items():
                case = normalize_match_case_block(authored_case, str(case_name))
                if case is None:
                    continue
                nested_steps = case.get("steps")
                if isinstance(nested_steps, list):
                    assign_step_ids(
                        nested_steps,
                        parent_step_id=f"{step_id}.{match_case_token(str(case_name), case)}",
                    )
            continue

        for_each = step.get("for_each")
        if isinstance(for_each, dict):
            nested_steps = for_each.get("steps")
            if isinstance(nested_steps, list):
                assign_step_ids(nested_steps, parent_step_id=step_id)

        repeat_until = step.get("repeat_until")
        if isinstance(repeat_until, dict):
            nested_steps = repeat_until.get("steps")
            if isinstance(nested_steps, list):
                body_token = repeat_until.get("id")
                if not authored_id_is_valid(body_token):
                    body_token = "repeat_until"
                assign_step_ids(nested_steps, parent_step_id=f"{step_id}.{body_token}")


def assign_finalization_step_ids(finally_block: Any) -> Dict[str, Any] | None:
    """Annotate a normalized finalization block with stable nested step ids."""
    normalized = normalize_finally_block(finally_block)
    if normalized is None:
        return None
    steps = normalized.get("steps")
    if isinstance(steps, list):
        assign_step_ids(
            steps,
            parent_step_id=f"root.finally.{finally_block_token(normalized)}",
        )
    return normalized


def runtime_step_id(step: Dict[str, Any], fallback_index: int = 0) -> str:
    """Return the durable step id for a loaded step, deriving a fallback when missing."""
    configured = step.get("step_id")
    if isinstance(configured, str) and configured:
        return configured

    token = step.get("id")
    if authored_id_is_valid(token):
        return f"root.{token}"
    return f"root.{_compiler_token(step, fallback_index)}"


def iteration_step_id(base_step_id: str, index: int, nested_step: Dict[str, Any], nested_index: int) -> str:
    """Return the qualified identity for a loop iteration step."""
    nested_base = runtime_step_id(nested_step, nested_index)
    prefix = f"{base_step_id}."
    if nested_base.startswith(prefix):
        suffix = nested_base[len(prefix):]
    else:
        suffix = nested_base.split(".", 1)[1] if "." in nested_base else nested_base
    return f"{base_step_id}#{index}.{suffix}"


def step_scope_tuple(step_id: str) -> Tuple[str, ...]:
    """Return lexical scope tokens for a step id."""
    if not isinstance(step_id, str) or not step_id:
        return ("root",)
    return tuple(token for token in step_id.split(".") if token)


def _compiler_token(step: Dict[str, Any], index: int) -> str:
    name = step.get("name")
    if isinstance(name, str) and name:
        token = _NON_ALNUM_RE.sub("_", name).strip("_")
        if token:
            if token[0].isdigit():
                token = f"step_{token}"
            return token.lower()
    return f"step_{index}"


def _dedupe_token(base_token: str, used_tokens: set[str]) -> str:
    token = base_token
    suffix = 2
    while token in used_tokens:
        token = f"{base_token}_{suffix}"
        suffix += 1
    used_tokens.add(token)
    return token
