"""Stdlib HTTP server for the local read-only workflow dashboard.

Routes: `/runs`, `/runs/<workspace>/<run>` (run page), `.../steps/<effect>` (effect page), `.../state`
(derived `state.json` preview) and `.../files/<workspace|run>/<path>` (escaped preview or `?raw=1`
attachment). A retired run's routes below its run page return 404 with the refusal line.
"""

from __future__ import annotations

import html
import json
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Mapping, Optional
from urllib.parse import parse_qs, quote, unquote, urlsplit

from orchestrator.dashboard.commands import CommandBuilder
from orchestrator.dashboard.effect_html import effect_timing, failed_effects_section, step_href
from orchestrator.dashboard.files import FileReferenceResolver, UnsafePathError
from orchestrator.dashboard.preview import DASHBOARD_CSP
from orchestrator.dashboard.preview import PreviewRenderer
from orchestrator.dashboard.projection import RunProjector
from orchestrator.dashboard.scanner import RunScanner


@dataclass(frozen=True)
class DashboardResponse:
    """Testable dashboard response object."""

    status: int
    body: bytes = b""
    headers: Mapping[str, str] = field(default_factory=dict)


class DashboardApp:
    """Explicit route dispatcher for dashboard pages."""

    def __init__(
        self,
        scanner: RunScanner,
        *,
        now: str | datetime | Callable[[], str | datetime] | None = None,
    ) -> None:
        self.scanner = scanner
        self._now_provider = self._coerce_now_provider(now)

    def handle(self, method: str, target: str) -> DashboardResponse:
        request_now = self._now()
        if method != "GET":
            return self._response(405, "Method not allowed")
        parsed = urlsplit(target)
        if parsed.path == "/":
            return DashboardResponse(status=302, headers={"Location": "/runs"})
        if parsed.path == "/runs":
            query = parse_qs(parsed.query)
            return self._runs_index(query, request_now)
        segments = [unquote(segment) for segment in parsed.path.strip("/").split("/") if segment]
        if len(segments) >= 3 and segments[0] == "runs":
            workspace_id, run_dir_id = segments[1], segments[2]
            links_files = len(segments) == 3 or (len(segments) >= 5 and segments[3] == "steps")
            detail = self._find_detail(workspace_id, run_dir_id, request_now, attempt_files=links_files)
            if detail is None:
                return self._response(404, "Run not found")
            if len(segments) == 3:
                return self._run_detail(detail, refresh=self._refresh_seconds(parse_qs(parsed.query)))
            if detail.row.display_status == "retired":
                return self._response(404, detail.row.failure_summary)
            if len(segments) == 4 and segments[3] == "state":
                return self._state_preview(detail)
            if len(segments) >= 5 and segments[3] == "steps":
                return self._step_detail(detail, "/".join(segments[4:]))
            if len(segments) >= 6 and segments[3] == "files":
                query = parse_qs(parsed.query)
                return self._file_route(
                    detail,
                    scope=segments[4],
                    route_path="/".join(segments[5:]),
                    raw=self._first(query, "raw") == "1",
                )
        return self._response(404, "Not found")

    def _runs_index(self, query: Mapping[str, list[str]], now: datetime) -> DashboardResponse:
        scan = self.scanner.scan()
        projector = RunProjector(now=now)
        rows = self._filter_rows(projector.project_index(scan.runs), query, now)
        refresh = self._refresh_seconds(query)
        lines = [
            "<!doctype html>",
            "<html><head><meta charset=\"utf-8\"><title>Workflow Runs</title>",
        ]
        if refresh is not None:
            lines.append(f"<meta http-equiv=\"refresh\" content=\"{refresh}\">")
        lines.extend([
            "<style>body{font-family:sans-serif;margin:2rem}table{border-collapse:collapse;width:100%}td,th{border:1px solid #bbb;padding:.35rem;text-align:left}code{white-space:pre-wrap}</style>",
            "</head><body>",
            "<main>",
            "<h1>Workflow Runs</h1>",
            '<p><a href="/runs">Refresh</a></p>',
            "<table>",
            "<thead><tr><th>Workspace</th><th>Run</th><th>State Run ID</th><th>Workflow</th><th>Status</th><th>Cursor</th><th>Started</th><th>Elapsed</th><th>Updated</th><th>Read time</th><th>Failure</th></tr></thead>",
            "<tbody>",
        ])
        if not rows:
            lines.append("<tr><td colspan=\"11\">No runs matched.</td></tr>")
        for row in rows:
            detail_href = f"/runs/{quote(row.workspace_id)}/{quote(row.run_dir_id)}"
            elapsed = self._format_duration(row.elapsed_seconds) if row.elapsed_seconds is not None else ""
            lines.append(
                "<tr>"
                f"<td>{self._e(row.workspace_label)}<br><small>{self._e(str(row.workspace_root))}</small></td>"
                f"<td><a href=\"{detail_href}\">{self._e(row.run_dir_id)}</a></td>"
                f"<td>{self._e(row.state_run_id or '')}</td>"
                f"<td>{self._e(row.workflow_file or '')}</td>"
                f"<td>{self._e(row.display_status)}</td>"
                f"<td>{self._e(row.cursor_summary)}</td>"
                f"<td>{self._e(row.started_at or '')}</td>"
                f"<td>{self._e(elapsed)}</td>"
                f"<td>{self._e(row.updated_at or '')}</td>"
                f"<td>{self._e(row.read_time or '')}</td>"
                f"<td>{self._e(row.failure_summary)}</td>"
                "</tr>"
            )
        lines.extend(["</tbody></table>", "</main>", "</body></html>"])
        return self._html_response("\n".join(lines))

    def _find_detail(self, workspace_id: str, run_dir_id: str, now: datetime, *, attempt_files: bool = False):
        scan = self.scanner.scan()
        for run in scan.runs:
            if run.workspace.id == workspace_id and run.run_dir_id == run_dir_id:
                return RunProjector(now=now).project_detail(run, attempt_files=attempt_files)
        return None

    def _run_detail(self, detail, *, refresh: Optional[int] = None) -> DashboardResponse:
        row = detail.row
        commands = CommandBuilder().build(self._run_record_for_detail(detail))
        lines = [
            "<!doctype html>",
            "<html><head><meta charset=\"utf-8\"><title>Run Detail</title>",
        ]
        if refresh is not None:
            lines.append(f"<meta http-equiv=\"refresh\" content=\"{refresh}\">")
        lines.extend([
            "<style>body{font-family:sans-serif;margin:2rem}section{margin-block:1.5rem}pre{background:#f5f5f5;padding:.75rem;overflow:auto}li{margin:.25rem 0}</style>",
            "</head><body><main>",
            f"<h1>Run {self._e(row.run_dir_id)}</h1>",
            "<section><h2>Summary</h2>",
            "<dl>",
            f"<dt>Workspace</dt><dd>{self._e(str(row.workspace_root))}</dd>",
            f"<dt>State run id</dt><dd>{self._e(row.state_run_id or '')}</dd>",
            f"<dt>Workflow</dt><dd>{self._e(row.workflow_file or '')}</dd>",
            f"<dt>Status</dt><dd>{self._e(row.display_status)}</dd>",
            "</dl>",
            "</section>",
        ])
        if row.display_status == "retired":
            lines.extend([f"<p>{self._e(row.failure_summary)}</p>", "</main></body></html>"])
            return self._html_response("\n".join(lines))
        pending_host_input = (
            detail.state.get("pending_host_input")
            if isinstance(detail.state, Mapping)
            else None
        )
        if isinstance(pending_host_input, Mapping):
            lines.extend([
                "<section><h2>Pending Host Input</h2><dl>",
                f"<dt>Request</dt><dd>{self._e(pending_host_input.get('request_id', ''))}</dd>",
                f"<dt>Question</dt><dd>{self._e(pending_host_input.get('question', ''))}</dd>",
                f"<dt>Answer type</dt><dd><pre>{self._json(pending_host_input.get('answer_contract'))}</pre></dd>",
                f"<dt>Deadline</dt><dd>{self._e(pending_host_input.get('deadline') if pending_host_input.get('deadline') is not None else 'none')}</dd>",
                f"<dt>Deadline elapsed</dt><dd>{self._e(pending_host_input.get('deadline_elapsed', False))}</dd>",
                "</dl>",
            ])
            shown = pending_host_input.get("show")
            if isinstance(shown, list) and shown:
                resolver = FileReferenceResolver(row.workspace_root, row.run_root)
                lines.append("<h3>Shown evidence</h3><ul>")
                for item in shown:
                    if not isinstance(item, Mapping) or not isinstance(item.get("path"), str):
                        continue
                    path = item["path"]
                    digest = item.get("sha256")
                    digest_html = (
                        f" <span class=\"muted\">SHA-256: {self._e(digest)}</span>"
                        if isinstance(digest, str)
                        else ""
                    )
                    try:
                        file_ref = resolver.workspace_ref(path, label=path)
                    except UnsafePathError:
                        lines.append(
                            f"<li>{self._e(path)} <span class=\"muted\">unsafe path</span>"
                            f"{digest_html}</li>"
                        )
                        continue
                    lines.append(
                        f"<li><a href=\"{self._file_href(row, file_ref)}\">{self._e(path)}</a>"
                        f"{digest_html}</li>"
                    )
                lines.append("</ul>")
            lines.append("</section>")
        all_warnings = list(detail.warnings) + list(commands.warnings)
        if all_warnings:
            lines.extend(["<section><h2>Warnings</h2><ul>"])
            for warning in all_warnings:
                lines.append(f"<li>{self._e(warning)}</li>")
            lines.append("</ul></section>")

        lines.extend(["<section><h2>Commands</h2>"])
        if commands.report is None and commands.resume is None and not commands.tmux:
            lines.append("<p>Commands unavailable for this run.</p>")
        if commands.report is not None:
            lines.append(f"<p>cwd: <code>{self._e(str(commands.report.cwd))}</code></p>")
            lines.append(f"<pre>{self._e(commands.report.shell_text)}</pre>")
        if commands.resume is not None:
            lines.append(f"<pre>{self._e(commands.resume.shell_text)}</pre>")
        lines.append("</section>")

        if detail.cursor is not None:
            lines.extend(["<section><h2>Active Cursor</h2><ul>"])
            for node in detail.cursor.nodes:
                lines.append(
                    f"<li>{self._e(node.kind)}: {self._e(node.name)} "
                    f"<pre>{self._json(node.details)}</pre></li>"
                )
            lines.append("</ul></section>")

        lines.extend(failed_effects_section(row, detail.steps))

        lines.extend(["<section><h2>Step Timeline</h2><ul>"])
        for step in detail.steps:
            lines.append(
                f"<li><a href=\"{step_href(row, step)}\">{self._e(step.name)}</a> "
                f"{self._e(step.status)} {self._e(step.kind)} <small>{effect_timing(step)}</small></li>"
            )
            if step.file_refs:
                lines.append("<ul>")
                for name, file_ref in step.file_refs.items():
                    lines.append(
                        f"<li>{self._e(name)} ({self._e(file_ref.label or '')}): "
                        f"<a href=\"{self._file_href(row, file_ref)}\">"
                        f"{self._e(file_ref.scope)}:{self._e(file_ref.route_path)}</a></li>"
                    )
                lines.append("</ul>")
        lines.append("</ul></section>")

        lines.append("<section><h2>Inputs</h2>")
        lines.append(f"<pre>{self._json(detail.bound_inputs)}</pre></section>")
        lines.append("<section><h2>Outputs</h2>")
        lines.append(f"<pre>{self._json(detail.workflow_outputs)}</pre></section>")
        lines.append("<section><h2>Run Error</h2>")
        lines.append(f"<pre>{self._json(detail.error)}</pre></section>")
        lines.append(f"<p><a href=\"/runs/{quote(row.workspace_id)}/{quote(row.run_dir_id)}/state\">State JSON</a></p>")
        lines.extend(["</main></body></html>"])
        return self._html_response("\n".join(lines))

    def _step_detail(self, detail, step_ref: str) -> DashboardResponse:
        row = detail.row
        step = next(
            (
                candidate
                for candidate in detail.steps
                if step_ref in {candidate.ref, candidate.name, candidate.step_id}
            ),
            None,
        )
        if step is None:
            return self._response(404, "Step not found")
        lines = [
            "<!doctype html>",
            "<html><head><meta charset=\"utf-8\"><title>Step Detail</title></head><body><main>",
            f"<h1>{self._e(step.name)}</h1>",
            f"<p>Status: {self._e(step.status)}</p>",
            f"<p>Kind: {self._e(step.kind)}</p>",
            f"<p>Step id: {self._e(step.step_id or '')}</p>",
            f"<p>Duration: {self._e(str(step.duration_ms) + ' ms' if step.duration_ms is not None else '')}</p>",
            f"<p>Attempt: {self._e(step.attempt if step.attempt is not None else '')}</p>",
            f"<p>Started: {self._e(step.started_at or '')}</p>",
            f"<p>Completed: {self._e(step.completed_at or '')}</p>",
            "<h2>Output Preview</h2>",
            f"<pre>{self._e(step.output_preview)}</pre>",
            "<h2>Error</h2>",
            f"<pre>{self._json(step.error)}</pre>",
            "<h2>Outcome</h2>",
            f"<pre>{self._json(step.outcome)}</pre>",
        ]
        if step.file_refs:
            lines.extend(["<h2>Files</h2>", "<ul>"])
            for name, file_ref in step.file_refs.items():
                lines.append(
                    f"<li>{self._e(name)} ({self._e(file_ref.label or '')}): "
                    f"<a href=\"{self._file_href(row, file_ref)}\">"
                    f"{self._e(file_ref.scope)}:{self._e(file_ref.route_path)}</a></li>"
                )
            lines.append("</ul>")
        lines.extend([
            f"<p><a href=\"/runs/{quote(row.workspace_id)}/{quote(row.run_dir_id)}\">Back to run</a></p>",
            "</main></body></html>",
        ])
        return self._html_response("\n".join(lines))

    def _state_preview(self, detail) -> DashboardResponse:
        try:
            resolver = FileReferenceResolver(detail.row.workspace_root, detail.row.run_root)
            file_ref = resolver.run_ref("state.json", label="state json")
        except UnsafePathError:
            return self._response(400, "Unsafe state path")
        if file_ref.status != "ok":
            body = (
                "<!doctype html><html><body><main>"
                f"<h1>{self._e(file_ref.status)}</h1>"
                "<p>state.json</p>"
                "</main></body></html>"
            )
            return self._html_response(body)

        preview = PreviewRenderer().preview(file_ref.absolute_path)
        lines = [
            "<!doctype html>",
            "<html><head><meta charset=\"utf-8\"><title>State Preview</title></head><body><main>",
            f"<h1>State JSON for {self._e(detail.row.run_dir_id)}</h1>",
            f"<p>Status: {self._e(preview.status)}</p>",
        ]
        if preview.truncated:
            size = preview.size_bytes if preview.size_bytes is not None else ""
            lines.append(
                f"<p>Preview truncated at dashboard cap; file size {self._e(size)} bytes.</p>"
            )
        lines.extend([
            f"<pre>{preview.display_text}</pre>",
            "</main></body></html>",
        ])
        return DashboardResponse(
            status=200,
            body="\n".join(lines).encode("utf-8"),
            headers={**self._html_headers(), **dict(preview.headers)},
        )

    def _file_route(
        self,
        detail,
        *,
        scope: str,
        route_path: str,
        raw: bool,
    ) -> DashboardResponse:
        try:
            resolver = FileReferenceResolver(detail.row.workspace_root, detail.row.run_root)
            if scope == "workspace":
                file_ref = resolver.workspace_ref(route_path)
            elif scope == "run":
                file_ref = resolver.run_ref(route_path)
            else:
                return self._response(404, "Unknown file scope")
        except UnsafePathError:
            return self._response(400, "Unsafe path")

        renderer = PreviewRenderer()
        if raw:
            if file_ref.status != "ok":
                return self._response(404, file_ref.status)
            raw_result = renderer.raw(file_ref.absolute_path)
            return DashboardResponse(
                status=200 if raw_result.status == "ok" else 404,
                body=raw_result.body,
                headers=dict(raw_result.headers),
            )

        if file_ref.status != "ok":
            body = (
                "<!doctype html><html><body><main>"
                f"<h1>{self._e(file_ref.status)}</h1>"
                f"<p>{self._e(scope)}:{self._e(route_path)}</p>"
                "</main></body></html>"
            )
            return self._html_response(body)

        preview = renderer.preview(file_ref.absolute_path)
        is_markdown = file_ref.route_path.lower().endswith((".md", ".markdown"))
        lines = [
            "<!doctype html>",
            "<html><head><meta charset=\"utf-8\"><title>File Preview</title>"
            "<style>body{font-family:sans-serif;margin:2rem;line-height:1.45}"
            "pre{background:#f5f5f5;padding:.75rem;overflow:auto}"
            ".markdown-preview{max-width:56rem}"
            ".markdown-preview code{background:#f2f2f2;padding:.08rem .2rem;border-radius:3px}"
            ".markdown-preview pre code{background:transparent;padding:0}"
            "</style></head><body><main>",
            f"<h1>{self._e(scope)}:{self._e(file_ref.route_path)}</h1>",
            f"<p>Status: {self._e(preview.status)}</p>",
            f"<p><a href=\"{self._file_href(detail.row, file_ref)}?raw=1\">Download raw</a></p>",
        ]
        if preview.truncated:
            size = preview.size_bytes if preview.size_bytes is not None else ""
            lines.append(
                f"<p>Preview truncated at dashboard cap; file size {self._e(size)} bytes.</p>"
            )
        if preview.status == "ok" and is_markdown:
            lines.extend([
                '<article class="markdown-preview">',
                self._render_markdown_preview(preview.display_text),
                "</article>",
                "</main></body></html>",
            ])
        else:
            lines.extend([
                f"<pre>{preview.display_text}</pre>",
                "</main></body></html>",
            ])
        body = "\n".join(lines)
        return DashboardResponse(
            status=200,
            body=body.encode("utf-8"),
            headers={**self._html_headers(), **dict(preview.headers)},
        )

    def _render_markdown_preview(
        self,
        escaped_text: str,
        *,
        link_mapper: Optional[Callable[[str], Optional[str]]] = None,
    ) -> str:
        lines = escaped_text.splitlines()
        rendered: list[str] = []
        paragraph: list[str] = []
        in_list = False
        in_code = False
        code_lines: list[str] = []

        def close_paragraph() -> None:
            if paragraph:
                rendered.append(f"<p>{' '.join(paragraph)}</p>")
                paragraph.clear()

        def close_list() -> None:
            nonlocal in_list
            if in_list:
                rendered.append("</ul>")
                in_list = False

        def close_code() -> None:
            if code_lines:
                rendered.append(f"<pre><code>{chr(10).join(code_lines)}</code></pre>")
                code_lines.clear()

        for line in lines:
            stripped = line.strip()
            if stripped.startswith("```"):
                close_paragraph()
                close_list()
                if in_code:
                    close_code()
                    in_code = False
                else:
                    in_code = True
                continue
            if in_code:
                code_lines.append(line)
                continue
            if not stripped:
                close_paragraph()
                close_list()
                continue
            heading_match = re.match(r"^(#{1,6})\s+(.+)$", stripped)
            if heading_match:
                close_paragraph()
                close_list()
                level = len(heading_match.group(1))
                rendered.append(
                    f"<h{level}>{self._markdown_inline(heading_match.group(2), link_mapper=link_mapper)}</h{level}>"
                )
                continue
            if stripped.startswith("- ") or stripped.startswith("* "):
                close_paragraph()
                if not in_list:
                    rendered.append("<ul>")
                    in_list = True
                rendered.append(
                    f"<li>{self._markdown_inline(stripped[2:].strip(), link_mapper=link_mapper)}</li>"
                )
                continue
            paragraph.append(self._markdown_inline(stripped, link_mapper=link_mapper))

        close_paragraph()
        close_list()
        if in_code:
            close_code()
        return "\n".join(rendered)

    def _markdown_inline(
        self,
        escaped_text: str,
        *,
        link_mapper: Optional[Callable[[str], Optional[str]]] = None,
    ) -> str:
        text = re.sub(r"`([^`]+)`", r"<code>\1</code>", escaped_text)
        text = re.sub(r"\*\*([^*\n]+)\*\*", r"<strong>\1</strong>", text)
        text = re.sub(r"\*([^*\n]+)\*", r"<em>\1</em>", text)

        if link_mapper is None:
            return text

        def replace_link(match: re.Match[str]) -> str:
            label = match.group(1)
            mapped_href = link_mapper(match.group(2))
            if not mapped_href:
                return match.group(0)
            return f'<a href="{self._e(mapped_href)}">{label}</a>'

        return re.sub(r"\[([^\]\n]+)\]\(([^)\s]+)\)", replace_link, text)

    def _file_href(self, row, file_ref) -> str:
        return (
            f"/runs/{quote(row.workspace_id)}/{quote(row.run_dir_id)}"
            f"/files/{quote(file_ref.scope)}/{quote(file_ref.route_path)}"
        )

    def _run_record_for_detail(self, detail):
        scan = self.scanner.scan()
        for run in scan.runs:
            if (
                run.workspace.id == detail.row.workspace_id
                and run.run_dir_id == detail.row.run_dir_id
            ):
                return run
        raise LookupError("run disappeared during dashboard request")

    def _filter_rows(self, rows, query: Mapping[str, list[str]], now: datetime):
        workspace_filter = self._first(query, "workspace")
        status_filter = self._first(query, "status")
        workflow_filter = self._first(query, "workflow")
        search_filter = self._first(query, "search")
        recency_filter = self._parse_recency(self._first(query, "recency"))
        filtered = []
        for row in rows:
            if workspace_filter and workspace_filter not in {
                row.workspace_id,
                row.workspace_label,
                str(row.workspace_root),
            }:
                continue
            if status_filter and status_filter != row.display_status:
                continue
            if workflow_filter:
                haystack = (row.workflow_file or "").lower()
                if workflow_filter.lower() not in haystack:
                    continue
            if search_filter:
                haystack = " ".join(
                    [
                        row.run_dir_id,
                        row.state_run_id or "",
                        row.workflow_file or "",
                        row.failure_summary or "",
                    ]
                ).lower()
                if search_filter.lower() not in haystack:
                    continue
            if recency_filter is not None:
                updated_at = self._parse_datetime(row.updated_at)
                if updated_at is None or now - updated_at > recency_filter:
                    continue
            filtered.append(row)
        filtered.sort(key=self._run_recency_sort_key)
        return filtered

    def _run_recency_sort_key(self, row) -> tuple[float, str, str, str]:
        return (
            -self._run_recency_timestamp(row),
            row.workspace_label,
            row.workspace_id,
            row.run_dir_id,
        )

    def _run_recency_timestamp(self, row) -> float:
        updated_at = self._parse_datetime(row.updated_at)
        if updated_at is not None:
            return updated_at.timestamp()
        started_at = self._parse_datetime(row.started_at)
        if started_at is not None:
            return started_at.timestamp()
        return float("-inf")

    def _html_response(
        self,
        body: str,
        *,
        status: int = 200,
        script_nonce: Optional[str] = None,
    ) -> DashboardResponse:
        return DashboardResponse(
            status=status,
            body=body.encode("utf-8"),
            headers=self._html_headers(script_nonce=script_nonce),
        )

    def _response(self, status: int, text: str) -> DashboardResponse:
        return self._html_response(
            f"<!doctype html><html><body><h1>{self._e(text)}</h1></body></html>",
            status=status,
        )

    def _html_headers(self, *, script_nonce: Optional[str] = None) -> dict[str, str]:
        csp = DASHBOARD_CSP
        if script_nonce:
            csp = (
                "default-src 'none'; base-uri 'none'; object-src 'none'; "
                f"frame-ancestors 'none'; script-src 'nonce-{script_nonce}'; "
                "connect-src 'self'; style-src 'unsafe-inline'; img-src 'self' data:"
            )
        return {
            "Content-Type": "text/html; charset=utf-8",
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": csp,
        }

    def _now(self) -> datetime:
        return self._now_provider()

    def _coerce_now_provider(
        self,
        value: str | datetime | Callable[[], str | datetime] | None,
    ) -> Callable[[], datetime]:
        if callable(value):
            return lambda: self._coerce_now_value(value())
        fixed = self._coerce_now_value(value) if value is not None else None
        if fixed is not None:
            return lambda: fixed
        return lambda: datetime.now(timezone.utc)

    def _coerce_now_value(self, value: str | datetime) -> datetime:
        if isinstance(value, datetime):
            return value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)
        if isinstance(value, str):
            parsed = self._parse_datetime(value)
            if parsed is not None:
                return parsed
        return datetime.now(timezone.utc)

    def _parse_datetime(self, value: object) -> Optional[datetime]:
        if not isinstance(value, str) or not value:
            return None
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    def _parse_recency(self, value: Optional[str]) -> Optional[timedelta]:
        if not value:
            return None
        units = {"m": 60, "h": 3600, "d": 86400}
        try:
            if value[-1] in units:
                seconds = int(value[:-1]) * units[value[-1]]
            else:
                seconds = int(value)
        except (ValueError, IndexError):
            return None
        return timedelta(seconds=seconds)

    def _refresh_seconds(self, query: Mapping[str, list[str]]) -> Optional[int]:
        value = self._first(query, "refresh")
        if value is None:
            return None
        try:
            seconds = int(value)
        except ValueError:
            return None
        if seconds < 1 or seconds > 3600:
            return None
        return seconds

    def _first(self, query: Mapping[str, list[str]], key: str) -> Optional[str]:
        values = query.get(key)
        if not values:
            return None
        return unquote(values[0])

    def _e(self, value: object) -> str:
        return html.escape(str(value), quote=True)

    def _format_duration(self, seconds_value: float) -> str:
        seconds = int(seconds_value)
        if seconds < 60:
            return f"{seconds}s"
        minutes, seconds = divmod(seconds, 60)
        if minutes < 60:
            return f"{minutes}m {seconds}s"
        hours, minutes = divmod(minutes, 60)
        return f"{hours}h {minutes}m"

    def _json(self, value: object) -> str:
        return html.escape(
            json.dumps(value, indent=2, default=self._json_default, sort_keys=True),
            quote=False,
        )

    def _json_default(self, value: object) -> object:
        if hasattr(value, "scope") and hasattr(value, "route_path"):
            return {
                "scope": getattr(value, "scope"),
                "route_path": getattr(value, "route_path"),
                "status": getattr(value, "status", None),
            }
        return str(value)



def serve_dashboard(*, scanner: RunScanner, host: str = "127.0.0.1", port: Optional[int] = None) -> int:
    """Serve the dashboard until interrupted."""
    bind_port = 8765 if port is None else port
    app = DashboardApp(scanner)

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 - stdlib hook name
            response = app.handle("GET", self.path)
            self.send_response(response.status)
            for name, value in response.headers.items():
                self.send_header(name, value)
            self.end_headers()
            self.wfile.write(response.body)

        def log_message(self, format: str, *args: object) -> None:
            print(format % args, file=sys.stderr)

    server = ThreadingHTTPServer((host, bind_port), Handler)
    actual_host, actual_port = server.server_address
    print(f"Dashboard listening on http://{actual_host}:{actual_port}/runs")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        return 0
    finally:
        server.server_close()
    return 0

