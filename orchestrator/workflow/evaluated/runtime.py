"""Minimal pure execution on a durably published evaluated run."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Mapping

from .authority import RunAuthority
from .machine import evaluate_closed_program
from .memo import append_record


logger = logging.getLogger(__name__)


def execute_pure_run(
    authority: RunAuthority,
    inputs: Mapping[str, Any],
    *,
    run_id: str,
) -> tuple[int, Any]:
    """Evaluate the checked table and persist its terminal outcome."""
    if not isinstance(authority, RunAuthority):
        raise TypeError("authority must be a checked RunAuthority")
    try:
        value = evaluate_closed_program(
            authority.program, inputs, run_id=run_id
        ).json_value()
    except Exception as exc:
        code = getattr(exc, "code", "evaluated_execution_failed")
        message = str(exc) or code
        append_record(
            authority.memo_path,
            {"record": "terminal", "outcome": "failed", "code": code, "message": message},
        )
        logger.error("[%s] %s", code, message)
        return 1, None
    append_record(
        authority.memo_path,
        {"record": "terminal", "outcome": "completed", "value": value},
    )
    return 0, value
