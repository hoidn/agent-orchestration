"""File and `state.json` preview pages, and the HTML response helpers every dashboard page shares.

Inputs are a `DashboardRunDetail` (its row's workspace and run roots) and a route path. Every path goes
through `FileReferenceResolver` (confined to the workspace or run root) and every byte shown goes through
`PreviewRenderer` (escaped, capped, inert raw-download headers). Reads only; nothing is written.
"""

from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass, field
from typing import Mapping
from urllib.parse import quote

from orchestrator.dashboard.files import FileReferenceResolver, UnsafePathError
from orchestrator.dashboard.preview import DASHBOARD_CSP, PreviewRenderer


@dataclass(frozen=True)
class DashboardResponse:
    """Testable dashboard response object."""

    status: int
    body: bytes = b""
    headers: Mapping[str, str] = field(default_factory=dict)


def e(value: object) -> str:
    return html.escape(str(value), quote=True)


def html_headers() -> dict[str, str]:
    return {
        "Content-Type": "text/html; charset=utf-8",
        "X-Content-Type-Options": "nosniff",
        "Content-Security-Policy": DASHBOARD_CSP,
    }


def html_response(body: str, *, status: int = 200) -> DashboardResponse:
    return DashboardResponse(status=status, body=body.encode("utf-8"), headers=html_headers())


def error_response(status: int, text: str) -> DashboardResponse:
    return html_response(f"<!doctype html><html><body><h1>{e(text)}</h1></body></html>", status=status)


def json_html(value: object) -> str:
    return html.escape(json.dumps(value, indent=2, default=_json_default, sort_keys=True), quote=False)


def _json_default(value: object) -> object:
    if hasattr(value, "scope") and hasattr(value, "route_path"):
        return {
            "scope": getattr(value, "scope"),
            "route_path": getattr(value, "route_path"),
            "status": getattr(value, "status", None),
        }
    return str(value)


def file_href(row, file_ref) -> str:
    return (
        f"/runs/{quote(row.workspace_id)}/{quote(row.run_dir_id)}"
        f"/files/{quote(file_ref.scope)}/{quote(file_ref.route_path)}"
    )


def state_preview(detail) -> DashboardResponse:
    try:
        resolver = FileReferenceResolver(detail.row.workspace_root, detail.row.run_root)
        file_ref = resolver.run_ref("state.json", label="state json")
    except UnsafePathError:
        return error_response(400, "Unsafe state path")
    if file_ref.status != "ok":
        body = (
            "<!doctype html><html><body><main>"
            f"<h1>{e(file_ref.status)}</h1>"
            "<p>state.json</p>"
            "</main></body></html>"
        )
        return html_response(body)

    preview = PreviewRenderer().preview(file_ref.absolute_path)
    lines = [
        "<!doctype html>",
        "<html><head><meta charset=\"utf-8\"><title>State Preview</title></head><body><main>",
        f"<h1>State JSON for {e(detail.row.run_dir_id)}</h1>",
        f"<p>Status: {e(preview.status)}</p>",
    ]
    if preview.truncated:
        size = preview.size_bytes if preview.size_bytes is not None else ""
        lines.append(f"<p>Preview truncated at dashboard cap; file size {e(size)} bytes.</p>")
    lines.extend([
        f"<pre>{preview.display_text}</pre>",
        "</main></body></html>",
    ])
    return DashboardResponse(
        status=200,
        body="\n".join(lines).encode("utf-8"),
        headers={**html_headers(), **dict(preview.headers)},
    )


def file_route(detail, *, scope: str, route_path: str, raw: bool) -> DashboardResponse:
    try:
        resolver = FileReferenceResolver(detail.row.workspace_root, detail.row.run_root)
        if scope == "workspace":
            file_ref = resolver.workspace_ref(route_path)
        elif scope == "run":
            file_ref = resolver.run_ref(route_path)
        else:
            return error_response(404, "Unknown file scope")
    except UnsafePathError:
        return error_response(400, "Unsafe path")

    renderer = PreviewRenderer()
    if raw:
        if file_ref.status != "ok":
            return error_response(404, file_ref.status)
        raw_result = renderer.raw(file_ref.absolute_path)
        return DashboardResponse(
            status=200 if raw_result.status == "ok" else 404,
            body=raw_result.body,
            headers=dict(raw_result.headers),
        )

    if file_ref.status != "ok":
        body = (
            "<!doctype html><html><body><main>"
            f"<h1>{e(file_ref.status)}</h1>"
            f"<p>{e(scope)}:{e(route_path)}</p>"
            "</main></body></html>"
        )
        return html_response(body)
    return _file_preview_page(detail, scope, file_ref, renderer.preview(file_ref.absolute_path))


def _file_preview_page(detail, scope, file_ref, preview) -> DashboardResponse:
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
        f"<h1>{e(scope)}:{e(file_ref.route_path)}</h1>",
        f"<p>Status: {e(preview.status)}</p>",
        f"<p><a href=\"{file_href(detail.row, file_ref)}?raw=1\">Download raw</a></p>",
    ]
    if preview.truncated:
        size = preview.size_bytes if preview.size_bytes is not None else ""
        lines.append(f"<p>Preview truncated at dashboard cap; file size {e(size)} bytes.</p>")
    if preview.status == "ok" and is_markdown:
        lines.extend([
            '<article class="markdown-preview">',
            render_markdown_preview(preview.display_text),
            "</article>",
            "</main></body></html>",
        ])
    else:
        lines.extend([
            f"<pre>{preview.display_text}</pre>",
            "</main></body></html>",
        ])
    return DashboardResponse(
        status=200,
        body="\n".join(lines).encode("utf-8"),
        headers={**html_headers(), **dict(preview.headers)},
    )


def render_markdown_preview(escaped_text: str) -> str:
    """Headings, lists, fenced code and inline emphasis over text `PreviewRenderer` already escaped."""
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

    for line in escaped_text.splitlines():
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
            rendered.append(f"<h{level}>{markdown_inline(heading_match.group(2))}</h{level}>")
            continue
        if stripped.startswith("- ") or stripped.startswith("* "):
            close_paragraph()
            if not in_list:
                rendered.append("<ul>")
                in_list = True
            rendered.append(f"<li>{markdown_inline(stripped[2:].strip())}</li>")
            continue
        paragraph.append(markdown_inline(stripped))

    close_paragraph()
    close_list()
    if in_code:
        close_code()
    return "\n".join(rendered)


def markdown_inline(escaped_text: str) -> str:
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", escaped_text)
    text = re.sub(r"\*\*([^*\n]+)\*\*", r"<strong>\1</strong>", text)
    return re.sub(r"\*([^*\n]+)\*", r"<em>\1</em>", text)
