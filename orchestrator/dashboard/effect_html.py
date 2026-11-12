"""HTML fragments for evaluated effect rows: attempt and timing, and links to failed effects.

Inputs are `DashboardStep` and `DashboardIndexRow` values projected from the evaluated view, whose
fields `orchestrator/workflow/evaluated/views.py` owns. Every value is escaped; no file or state access.
"""

from __future__ import annotations

from html import escape
from typing import Mapping
from urllib.parse import quote


def step_href(row, step) -> str:
    """Route of one effect page under its run (the same route the step timeline links)."""
    return f"/runs/{quote(row.workspace_id)}/{quote(row.run_dir_id)}/steps/{quote(step.ref)}"


def effect_timing(step) -> str:
    """Escaped `attempt N, started T, completed T, duration D ms`; parts the row lacks are left out."""
    parts = [
        f"attempt {step.attempt}" if step.attempt is not None else "",
        f"started {step.started_at}" if step.started_at else "",
        f"completed {step.completed_at}" if step.completed_at else "",
        f"duration {step.duration_ms} ms" if step.duration_ms is not None else "",
    ]
    return escape(", ".join(part for part in parts if part))


def failed_effects_section(row, steps) -> list[str]:
    """Run-page section linking each failed effect with its error code; no lines when none failed."""
    failed = [step for step in steps if step.status == "failed"]
    if not failed:
        return []
    lines = ["<section><h2>Failed Effects</h2><ul>"]
    for step in failed:
        code = step.error.get("code") if isinstance(step.error, Mapping) else None
        lines.append(f"<li><a href=\"{step_href(row, step)}\">{escape(step.name)}</a> "
                     f"<code>{escape(str(code or 'unknown'))}</code></li>")
    lines.append("</ul></section>")
    return lines
