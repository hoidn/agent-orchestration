"""Run page HTML, one function per section.

Input is a `DashboardRunDetail` from `RunProjector.project_detail` and the `CommandSet` from
`CommandBuilder`. A retired run's page holds the summary and its refusal line only. Every value shown is
escaped; every file link is a `FileReferenceResolver` reference rendered through `file_href`.
"""

from __future__ import annotations

from typing import Mapping, Optional
from urllib.parse import quote

from orchestrator.dashboard.effect_html import effect_timing, failed_effects_section, step_href
from orchestrator.dashboard.file_pages import e, file_href, json_html
from orchestrator.dashboard.files import FileReferenceResolver, UnsafePathError


def run_page(detail, commands, *, refresh: Optional[int] = None) -> str:
    row = detail.row
    lines = [
        "<!doctype html>",
        "<html><head><meta charset=\"utf-8\"><title>Run Detail</title>",
    ]
    if refresh is not None:
        lines.append(f"<meta http-equiv=\"refresh\" content=\"{refresh}\">")
    lines.extend([
        "<style>body{font-family:sans-serif;margin:2rem}section{margin-block:1.5rem}pre{background:#f5f5f5;padding:.75rem;overflow:auto}li{margin:.25rem 0}</style>",
        "</head><body><main>",
        f"<h1>Run {e(row.run_dir_id)}</h1>",
        "<section><h2>Summary</h2>",
        "<dl>",
        f"<dt>Workspace</dt><dd>{e(str(row.workspace_root))}</dd>",
        f"<dt>State run id</dt><dd>{e(row.state_run_id or '')}</dd>",
        f"<dt>Workflow</dt><dd>{e(row.workflow_file or '')}</dd>",
        f"<dt>Status</dt><dd>{e(row.display_status)}</dd>",
        "</dl>",
        "</section>",
    ])
    if row.display_status == "retired":
        lines.extend([f"<p>{e(row.failure_summary)}</p>", "</main></body></html>"])
        return "\n".join(lines)
    pending_host_input = detail.state.get("pending_host_input") if isinstance(detail.state, Mapping) else None
    if isinstance(pending_host_input, Mapping):
        lines.extend(_pending_host_input_section(row, pending_host_input))
    lines.extend(warnings_section(list(detail.warnings) + list(commands.warnings)))
    lines.extend(_commands_section(commands))
    if detail.cursor is not None:
        lines.extend(_cursor_section(detail.cursor))
    lines.extend(failed_effects_section(row, detail.steps))
    lines.extend(_timeline_section(row, detail.steps))
    lines.extend(_values_section(detail))
    lines.extend(["</main></body></html>"])
    return "\n".join(lines)


def file_links(row, file_refs) -> list[str]:
    """A `<ul>` of attempt-file links; the effect page shares it."""
    lines = ["<ul>"]
    for name, file_ref in file_refs.items():
        lines.append(
            f"<li>{e(name)} ({e(file_ref.label or '')}): "
            f"<a href=\"{file_href(row, file_ref)}\">"
            f"{e(file_ref.scope)}:{e(file_ref.route_path)}</a></li>"
        )
    lines.append("</ul>")
    return lines


def _pending_host_input_section(row, pending_host_input) -> list[str]:
    lines = [
        "<section><h2>Pending Host Input</h2><dl>",
        f"<dt>Request</dt><dd>{e(pending_host_input.get('request_id', ''))}</dd>",
        f"<dt>Question</dt><dd>{e(pending_host_input.get('question', ''))}</dd>",
        f"<dt>Answer type</dt><dd><pre>{json_html(pending_host_input.get('answer_contract'))}</pre></dd>",
        f"<dt>Deadline</dt><dd>{e(pending_host_input.get('deadline') if pending_host_input.get('deadline') is not None else 'none')}</dd>",
        f"<dt>Deadline elapsed</dt><dd>{e(pending_host_input.get('deadline_elapsed', False))}</dd>",
        "</dl>",
    ]
    shown = pending_host_input.get("show")
    if isinstance(shown, list) and shown:
        lines.extend(_shown_evidence(row, shown))
    lines.append("</section>")
    return lines


def _shown_evidence(row, shown) -> list[str]:
    resolver = FileReferenceResolver(row.workspace_root, row.run_root)
    lines = ["<h3>Shown evidence</h3><ul>"]
    for item in shown:
        if not isinstance(item, Mapping) or not isinstance(item.get("path"), str):
            continue
        path = item["path"]
        digest = item.get("sha256")
        digest_html = f" <span class=\"muted\">SHA-256: {e(digest)}</span>" if isinstance(digest, str) else ""
        try:
            file_ref = resolver.workspace_ref(path, label=path)
        except UnsafePathError:
            lines.append(f"<li>{e(path)} <span class=\"muted\">unsafe path</span>{digest_html}</li>")
            continue
        lines.append(f"<li><a href=\"{file_href(row, file_ref)}\">{e(path)}</a>{digest_html}</li>")
    lines.append("</ul>")
    return lines


def warnings_section(warnings: list[str]) -> list[str]:
    if not warnings:
        return []
    return ["<section><h2>Warnings</h2><ul>", *(f"<li>{e(warning)}</li>" for warning in warnings),
            "</ul></section>"]


def _commands_section(commands) -> list[str]:
    lines = ["<section><h2>Commands</h2>"]
    if commands.report is None and commands.resume is None and not commands.tmux:
        lines.append("<p>Commands unavailable for this run.</p>")
    if commands.report is not None:
        lines.append(f"<p>cwd: <code>{e(str(commands.report.cwd))}</code></p>")
        lines.append(f"<pre>{e(commands.report.shell_text)}</pre>")
    if commands.resume is not None:
        lines.append(f"<pre>{e(commands.resume.shell_text)}</pre>")
    lines.append("</section>")
    return lines


def _cursor_section(cursor) -> list[str]:
    lines = ["<section><h2>Active Cursor</h2><ul>"]
    for node in cursor.nodes:
        lines.append(f"<li>{e(node.kind)}: {e(node.name)} <pre>{json_html(node.details)}</pre></li>")
    lines.append("</ul></section>")
    return lines


def _timeline_section(row, steps) -> list[str]:
    lines = ["<section><h2>Step Timeline</h2><ul>"]
    for step in steps:
        lines.append(
            f"<li><a href=\"{step_href(row, step)}\">{e(step.name)}</a> "
            f"{e(step.status)} {e(step.kind)} <small>{effect_timing(step)}</small></li>"
        )
        if step.file_refs:
            lines.extend(file_links(row, step.file_refs))
    lines.append("</ul></section>")
    return lines


def _values_section(detail) -> list[str]:
    row = detail.row
    return [
        "<section><h2>Inputs</h2>",
        f"<pre>{json_html(detail.bound_inputs)}</pre></section>",
        "<section><h2>Outputs</h2>",
        f"<pre>{json_html(detail.workflow_outputs)}</pre></section>",
        "<section><h2>Run Error</h2>",
        f"<pre>{json_html(detail.error)}</pre></section>",
        f"<p><a href=\"/runs/{quote(row.workspace_id)}/{quote(row.run_dir_id)}/state\">State JSON</a></p>",
    ]
