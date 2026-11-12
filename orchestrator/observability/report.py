"""Markdown rendering of the evaluated `report` snapshot (`report_snapshot` in evaluated/views.py)."""

from __future__ import annotations

import json
from typing import Any, Dict, Iterable, Mapping


def _render_kv_lines(items: Iterable[tuple[str, Any]]) -> str:
    return "\n".join(f"- {key}: `{value}`" for key, value in items if value is not None)



def _render_json_fence(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, indent=2)
    fence = "```"
    while fence in payload:
        fence += "`"
    return f"{fence}json\n{payload}\n{fence}"



_TOKEN_FIELDS = ("input", "output", "cache_read", "cache_write")


def _usage_text(usage: Mapping[str, Any]) -> str:
    """Tokens and cost, `unknown` when no attempt reported (never 0); a leading `≥` marks a lower bound."""
    unknown = usage["unknown_attempts"]
    attempts = f"attempts {usage['attempts']}" + (f", {unknown} unknown" if unknown else "")
    if usage["tokens"] is None:
        return f"unknown; {attempts}"
    bound = "≥ " if usage["partial"] else ""
    tokens = ", ".join(f"{key} {usage['tokens'][key]}" for key in _TOKEN_FIELDS)
    cost = "unknown" if usage["cost_usd"] is None else f"{bound}{usage['cost_usd']:.6g}"
    return f"{bound}{tokens}; cost_usd {cost}; {attempts}"


def _render_run_usage(usage: Mapping[str, Any] | None) -> list[str]:
    if usage is None:       # no provider-class step
        return []
    table = usage["price_table"]
    return ["## Usage", _render_kv_lines([("total", _usage_text(usage)),
                                          ("price_table", f"{table['source']} ({table['date']})")]), ""]


def _render_step_usage(step: Mapping[str, Any]) -> list[str]:
    return [_render_kv_lines([("usage", _usage_text(step["usage"]))])] if "usage" in step else []



def _render_programs(programs) -> list[str]:
    """A run with several programs (a `rebased` record): one line per program, index as the rows name it."""
    if not programs:
        return []
    return ["## Programs", *(f"- {index}: `{item['digest']}` since `{item['time']}`"
                             + ("" if item["cut"] is None else f", cut at byte `{item['cut']}`")
                             for index, item in enumerate(programs)), ""]


def render_status_markdown(snapshot: Dict[str, Any]) -> str:
    """Render an evaluated run's report snapshot without invented audit data."""
    return _render_evaluated_status_markdown(snapshot)



def _render_evaluated_status_markdown(snapshot: Dict[str, Any]) -> str:
    run = snapshot["run"]
    lines = ["# Workflow Status", "", "## Run", _render_kv_lines(
        (key, run.get(key)) for key in ("run_id", "status", "workflow_file", "started_at",
                                       "updated_at", "memo_offset", "current_step", "next_effect")), ""]
    if run.get("bound_inputs"):
        lines.extend(["## Inputs", _render_kv_lines(sorted(run["bound_inputs"].items())), ""])
    pending_input = run.get("pending_host_input")
    if isinstance(pending_input, Mapping):
        lines.extend([
            "## Pending Host Input",
            _render_json_fence({key: pending_input.get(key) for key in (
                "request_id", "question", "answer_contract", "deadline", "deadline_elapsed", "show"
            )}),
            "",
        ])
    if run["status"] == "completed":
        lines.extend(["## Outputs", "```json", json.dumps(run["workflow_outputs"], indent=2), "```", ""])
    if run.get("error"):
        lines.extend(["## Run Error", _render_kv_lines(run["error"].items()), ""])
    if run.get('run_ref_cleanup'):
        lines.extend(['## Run-ref Cleanup', ''])
        for pending in run['run_ref_cleanup']:
            lines.append(_render_kv_lines(pending.items()))
            lines.append('')
    lines.extend(_render_programs(run.get("programs")))
    lines.extend(_render_run_usage(run.get("usage")))
    lines.extend(["## Progress", _render_kv_lines(snapshot["progress"].items()), "", "## Steps"])
    for step in snapshot["steps"]:
        lines.extend([f"### {step['name']} ({step['status']})", _render_kv_lines(
            (key, step.get(key)) for key in ("kind", "attempt", "result_path", "started_at", "completed_at",
                                         "agent", "predecessor", "continuation", "locator_present", "program"))])
        lines.extend(_render_step_usage(step))
        if "value" in step:
            lines.append(_render_json_fence(step["value"]))
        if isinstance(step.get("host_settlement"), Mapping):
            lines.extend([
                "Host settlement:",
                _render_json_fence(step["host_settlement"]),
            ])
        if step.get("error"):
            lines.append(_render_kv_lines(step["error"].items()))
        lines.append("")
    return "\n".join(lines) + "\n"
