"""Structured statement helpers for v2.2 control flow."""

from __future__ import annotations

from typing import Any, Dict, Optional


STRUCTURED_IF_VERSION = "2.2"


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
