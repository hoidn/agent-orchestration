"""Structured statement helpers for v2.x control flow."""

from __future__ import annotations

import re
from typing import Any, Dict, Optional


STRUCTURED_IF_VERSION = "2.2"
STRUCTURED_FINALLY_VERSION = "2.3"
STRUCTURED_MATCH_VERSION = "2.6"
STRUCTURED_REPEAT_UNTIL_VERSION = "2.7"
STRUCTURED_REPEAT_UNTIL_ON_EXHAUSTED_VERSION = "2.12"
_NON_ALNUM_RE = re.compile(r"[^A-Za-z0-9]+")


def is_if_statement(step: Any) -> bool:
    """Return True when a step declaration uses structured if/else syntax."""
    return isinstance(step, dict) and any(key in step for key in ("if", "then", "else"))


def is_match_statement(step: Any) -> bool:
    """Return True when a step declaration uses structured match syntax."""
    return isinstance(step, dict) and "match" in step


def is_repeat_until_statement(step: Any) -> bool:
    """Return True when a step declaration uses structured repeat_until syntax."""
    return isinstance(step, dict) and "repeat_until" in step


def normalize_branch_block(branch: Any, branch_name: str) -> Optional[Dict[str, Any]]:
    """Normalize author-friendly branch syntax into a dict form."""
    if branch is None:
        return None
    if isinstance(branch, list):
        return {
            "id": None,
            "steps": branch,
            "outputs": {},
            "branch_name": branch_name,
        }
    if isinstance(branch, dict):
        return {
            "id": branch.get("id"),
            "steps": branch.get("steps"),
            "outputs": branch.get("outputs", {}),
            "branch_name": branch_name,
        }
    return None


def branch_token(branch_name: str, branch_block: Dict[str, Any]) -> str:
    """Return the stable id token for one structured branch."""
    authored = branch_block.get("id")
    if isinstance(authored, str) and authored:
        return authored
    return branch_name


def normalize_match_case_block(case_block: Any, case_name: str) -> Optional[Dict[str, Any]]:
    """Normalize one authored match case into the common block shape."""
    if case_block is None:
        return None
    if isinstance(case_block, list):
        return {
            "id": None,
            "steps": case_block,
            "outputs": {},
            "case_name": case_name,
        }
    if isinstance(case_block, dict):
        return {
            "id": case_block.get("id"),
            "steps": case_block.get("steps"),
            "outputs": case_block.get("outputs", {}),
            "case_name": case_name,
        }
    return None


def match_case_token(case_name: str, case_block: Dict[str, Any]) -> str:
    """Return the stable id token for one structured match case."""
    authored = case_block.get("id")
    if isinstance(authored, str) and authored:
        return authored
    token = _NON_ALNUM_RE.sub("_", case_name).strip("_").lower()
    if not token:
        return "case"
    if token[0].isdigit():
        return f"case_{token}"
    return token


def normalize_repeat_until_block(block: Any) -> Optional[Dict[str, Any]]:
    """Normalize authored repeat_until syntax into a dict form."""
    if not isinstance(block, dict):
        return None
    return {
        "id": block.get("id"),
        "steps": block.get("steps"),
        "outputs": block.get("outputs", {}),
        "condition": block.get("condition"),
        "max_iterations": block.get("max_iterations"),
        "on_exhausted": block.get("on_exhausted"),
    }


def repeat_until_body_token(block: Dict[str, Any]) -> str:
    """Return the stable token for a repeat_until body block."""
    authored = block.get("id")
    if isinstance(authored, str) and authored:
        return authored
    return "repeat_until"


def normalize_finally_block(block: Any) -> Optional[Dict[str, Any]]:
    """Normalize author-friendly finalization syntax into a dict form."""
    if block is None:
        return None
    if isinstance(block, list):
        return {
            "id": None,
            "steps": block,
        }
    if isinstance(block, dict):
        return {
            "id": block.get("id"),
            "steps": block.get("steps"),
        }
    return None


def finally_block_token(block: Dict[str, Any]) -> str:
    """Return the stable token for a workflow finally block."""
    authored = block.get("id")
    if isinstance(authored, str) and authored:
        return authored
    return "finally"
