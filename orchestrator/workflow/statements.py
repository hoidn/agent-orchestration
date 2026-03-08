"""Structured statement helpers for v2.x control flow."""

from __future__ import annotations

from typing import Any, Dict, Optional


STRUCTURED_IF_VERSION = "2.2"
STRUCTURED_FINALLY_VERSION = "2.3"


def is_if_statement(step: Any) -> bool:
    """Return True when a step declaration uses structured if/else syntax."""
    return isinstance(step, dict) and any(key in step for key in ("if", "then", "else"))


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
