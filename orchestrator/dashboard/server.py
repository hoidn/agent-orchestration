"""Stdlib HTTP server for the local read-only workflow dashboard."""

from __future__ import annotations

import html
import json
import posixpath
import re
import secrets
import shlex
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Mapping, Optional
from types import SimpleNamespace
from urllib.parse import parse_qs, quote, unquote, urlsplit

import yaml

from orchestrator.dashboard.commands import CommandBuilder
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


class _ProviderFlowBuilder:
    """Build a compact Mermaid graph of provider steps and repeat-loop feedback."""

    def __init__(
        self,
        app: "DashboardApp",
        source_nodes: Optional[list[dict[str, object]]] = None,
    ) -> None:
        self._app = app
        self._source_nodes = source_nodes
        self._counter = 0
        self._nodes: list[tuple[str, str, str]] = []
        self._edges: list[tuple[str, str, str, str]] = []

    def walk_sequence(self, nodes: list[dict[str, object]]) -> tuple[list[str], list[str]]:
        sequence = [node for node in nodes if isinstance(node, Mapping)]
        if not sequence:
            return [], []
        if all(str(node.get("kind") or "") in {"case", "branch"} for node in sequence):
            first_ids: list[str] = []
            last_ids: list[str] = []
            for node in sequence:
                first, last = self.walk_node(node)
                first_ids.extend(first)
                last_ids.extend(last)
            return self._unique(first_ids), self._unique(last_ids)

        first_ids: list[str] = []
        current_last: list[str] = []
        for node in sequence:
            node_first, node_last = self.walk_node(node)
            if not node_first:
                continue
            if current_last:
                self._connect(current_last, node_first)
            if not first_ids:
                first_ids = list(node_first)
            current_last = list(node_last or node_first)
        return self._unique(first_ids), self._unique(current_last)

    def walk_node(self, node: Mapping[str, object]) -> tuple[list[str], list[str]]:
        label = str(node.get("label") or "step")
        kind = str(node.get("kind") or "step")
        children = node.get("children")
        child_nodes = children if isinstance(children, list) else []

        if bool(node.get("provider")):
            node_id = self._add_node(label, "provider")
            return [node_id], [node_id]

        if kind.startswith("repeat_until") and self._app._node_has_provider_descendant(node):
            loop_label = f"{label}<br/>{kind}"
            loop_id = self._add_node(loop_label, "loop")
            child_first, child_last = self.walk_sequence(child_nodes)
            if child_first:
                self._connect([loop_id], child_first)
            if child_first and child_last:
                self._connect(child_last, child_first, label="repeat", dotted=True)
            return [loop_id], child_last or [loop_id]

        if child_nodes:
            return self.walk_sequence(child_nodes)
        return [], []

    def render(self) -> str:
        lines = ["flowchart TD"]
        for node_id, label, class_name in self._nodes:
            if class_name == "loop":
                lines.append(f"  {node_id}{{{{\"{self._label(label)}\"}}}}:::{class_name}")
            else:
                lines.append(f"  {node_id}[\"{self._label(label)}\"]:::{class_name}")
        for source, target, label, style in self._edges:
            if style == "dotted":
                edge = f"-. {label} .->" if label else "-.->"
            else:
                edge = f"-- {label} -->" if label else "-->"
            lines.append(f"  {source} {edge} {target}")
        lines.extend(
            [
                "  classDef provider fill:#dceeff,stroke:#2f80c1,stroke-width:2px,color:#102a43;",
                "  classDef loop fill:#fff7ed,stroke:#c2410c,stroke-width:2px,color:#431407;",
            ]
        )
        return "\n".join(lines)

    def render_svg(self) -> str:
        items = self._compact_flow_items()
        if not items:
            return ""
        width = 980
        left = 28
        top = 36
        gap_x = 32
        gap_y = 28
        row_height = 118
        cursor_x = left
        cursor_y = top
        positions: dict[int, tuple[int, int, int, int]] = {}
        for index, item in enumerate(items):
            item_width = 310 if item["kind"] == "loop_group" else 168
            item_height = 98 if item["kind"] == "loop_group" else 58
            if cursor_x > left and cursor_x + item_width > width - left:
                cursor_x = left
                cursor_y += row_height + gap_y
            positions[index] = (cursor_x, cursor_y, item_width, item_height)
            cursor_x += item_width + gap_x
        height = cursor_y + row_height + top
        parts = [
            f"<svg class=\"provider-flow-svg\" viewBox=\"0 0 {width} {height}\" "
            "role=\"img\" aria-label=\"Compact provider flow diagram\" "
            "xmlns=\"http://www.w3.org/2000/svg\">",
            "<defs><marker id=\"provider-flow-arrow\" markerWidth=\"10\" markerHeight=\"10\" "
            "refX=\"9\" refY=\"3\" orient=\"auto\" markerUnits=\"strokeWidth\">"
            "<path d=\"M0,0 L0,6 L9,3 z\" fill=\"#52616b\" /></marker></defs>",
        ]
        for index in range(len(items) - 1):
            source_x, source_y, source_w, source_h = positions[index]
            target_x, target_y, _target_w, target_h = positions[index + 1]
            if source_y != target_y:
                continue
            sx = source_x + source_w
            sy = source_y + source_h / 2
            tx = target_x
            ty = target_y + target_h / 2
            if tx > sx:
                path = f"M {sx:.0f} {sy:.0f} L {tx:.0f} {ty:.0f}"
                parts.append(
                    f"<path d=\"{path}\" fill=\"none\" stroke=\"#52616b\" "
                    "stroke-width=\"2\" marker-end=\"url(#provider-flow-arrow)\" />"
                )
        for index, item in enumerate(items):
            x, y, item_width, item_height = positions[index]
            if item["kind"] == "loop_group":
                parts.extend(self._render_loop_group_svg(item, x, y, item_width, item_height))
            else:
                parts.extend(
                    self._render_provider_card_svg(
                        str(item["label"]),
                        x,
                        y + 20,
                        item_width,
                        58,
                    )
                )
        parts.append("</svg>")
        return "".join(parts)

    def render_strip_html(self) -> str:
        items = (
            self._app._compact_provider_flow_items(self._source_nodes)
            if self._source_nodes is not None
            else self._compact_flow_items()
        )
        if not items:
            return ""
        parts = ["<div class=\"provider-flow-strip\">"]
        rows = self._flow_rows(items)
        for row_index, row in enumerate(rows):
            reverse_row = row_index % 2 == 1
            display_row = list(reversed(row)) if reverse_row else row
            direction_class = " reverse" if reverse_row else ""
            parts.append(
                f"<div class=\"provider-flow-row{direction_class}\" "
                f"style=\"--flow-columns:{len(row)}\">"
            )
            for item_index, item in enumerate(display_row):
                stage_classes = ["provider-flow-stage"]
                if item_index < len(row) - 1:
                    stage_classes.append("has-prev" if reverse_row else "has-next")
                elif row_index < len(rows) - 1:
                    stage_classes.append("turn-next")
                parts.append(f"<div class=\"{' '.join(stage_classes)}\">")
                parts.append(self._flow_item_html(item))
                parts.append("</div>")
            parts.append("</div>")
        parts.append("</div>")
        return "".join(parts)

    def _flow_rows(self, items: list[dict[str, object]]) -> list[list[dict[str, object]]]:
        if len(items) <= 4:
            return [items]
        per_row = min(4, max(2, (len(items) + 1) // 2))
        return [items[index : index + per_row] for index in range(0, len(items), per_row)]

    def _flow_item_html(self, item: dict[str, object]) -> str:
        if item["kind"] == "loop_group":
            providers = [str(provider) for provider in item.get("providers", []) if provider]
            parts = [
                "<div class=\"provider-flow-card provider-flow-loop-card\">",
                f"<div class=\"provider-flow-loop-title\">"
                f"{self._flow_label_html(str(item['label']))}</div>",
                "<div class=\"provider-flow-loop-body\">",
            ]
            for provider_index, provider in enumerate(providers[:2]):
                if provider_index > 0:
                    parts.append("<span class=\"provider-flow-mini-arrow\" aria-hidden=\"true\">&#8594;</span>")
                parts.append(
                    "<span class=\"provider-flow-mini-provider\">"
                    f"{self._flow_label_html(provider)}</span>"
                )
            parts.extend(
                [
                    "</div>",
                    "<div class=\"provider-flow-loop-note\">loops until approved</div>",
                    "</div>",
                ]
            )
            return "".join(parts)
        return (
            "<div class=\"provider-flow-card provider-flow-provider-card\">"
            f"{self._flow_label_html(str(item['label']))}</div>"
        )

    def _flow_label_html(self, label: str) -> str:
        escaped = html.escape(label)
        return re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "<wbr>", escaped)

    def _render_loop_group_svg(
        self,
        item: dict[str, object],
        x: int,
        y: int,
        width: int,
        height: int,
    ) -> list[str]:
        title = str(item["label"])
        providers = [str(provider) for provider in item.get("providers", []) if provider]
        parts = [
            f"<rect x=\"{x}\" y=\"{y}\" width=\"{width}\" height=\"{height}\" rx=\"10\" "
            "fill=\"#fffaf3\" stroke=\"#c2410c\" stroke-width=\"2\" stroke-dasharray=\"5 4\" />",
            f"<text class=\"provider-flow-group-title\" x=\"{x + width / 2:.0f}\" y=\"{y + 19}\" "
            "text-anchor=\"middle\" font-size=\"12\" font-weight=\"700\" fill=\"#8a330d\">"
            f"{html.escape(title)}</text>",
        ]
        if not providers:
            return parts
        card_gap = 14
        inner_y = y + 32
        card_w = int((width - 34 - card_gap) / 2) if len(providers) >= 2 else width - 34
        card_h = 42
        first_x = x + 17
        second_x = first_x + card_w + card_gap
        parts.extend(self._render_provider_card_svg(providers[0], first_x, inner_y, card_w, card_h, compact=True))
        if len(providers) >= 2:
            parts.extend(self._render_provider_card_svg(providers[1], second_x, inner_y, card_w, card_h, compact=True))
            sy = inner_y + card_h / 2
            parts.append(
                f"<path d=\"M {first_x + card_w:.0f} {sy:.0f} L {second_x:.0f} {sy:.0f}\" "
                "fill=\"none\" stroke=\"#52616b\" stroke-width=\"2\" marker-end=\"url(#provider-flow-arrow)\" />"
            )
            arc_y = inner_y + card_h + 14
            parts.append(
                f"<path d=\"M {second_x + card_w / 2:.0f} {arc_y:.0f} "
                f"C {second_x + card_w / 2:.0f} {arc_y + 18:.0f}, "
                f"{first_x + card_w / 2:.0f} {arc_y + 18:.0f}, "
                f"{first_x + card_w / 2:.0f} {arc_y:.0f}\" "
                "fill=\"none\" stroke=\"#c2410c\" stroke-width=\"2\" stroke-dasharray=\"5 4\" "
                "marker-end=\"url(#provider-flow-arrow)\" />"
            )
            parts.append(
                f"<text x=\"{x + width / 2:.0f}\" y=\"{y + height - 8}\" "
                "text-anchor=\"middle\" font-size=\"11\" fill=\"#c2410c\">loops until approved</text>"
            )
        return parts

    def _render_provider_card_svg(
        self,
        label: str,
        x: int,
        y: int,
        width: int,
        height: int,
        *,
        compact: bool = False,
    ) -> list[str]:
        parts = [
            f"<rect x=\"{x}\" y=\"{y}\" width=\"{width}\" height=\"{height}\" "
            f"rx=\"8\" fill=\"#dceeff\" stroke=\"#2f80c1\" stroke-width=\"2\" />"
        ]
        label_parts = self._wrap_svg_label(label, 16 if compact else 18)
        line_height = 13 if compact else 15
        base_y = y + height / 2 - (len(label_parts[:2]) - 1) * line_height / 2 + 4
        for offset, label_part in enumerate(label_parts[:2]):
            parts.append(
                f"<text x=\"{x + width / 2:.0f}\" y=\"{base_y + offset * line_height:.0f}\" "
                f"text-anchor=\"middle\" font-size=\"{12 if compact else 13}\" font-weight=\"650\" "
                "fill=\"#102a43\">"
                f"{html.escape(label_part)}</text>"
            )
        return parts

    def _compact_flow_items(self) -> list[dict[str, object]]:
        items: list[dict[str, object]] = []
        display_nodes = self._compact_display_nodes()
        index = 0
        while index < len(display_nodes):
            item = display_nodes[index]
            if item["class_name"] == "loop":
                providers: list[str] = []
                cursor = index + 1
                while cursor < len(display_nodes) and display_nodes[cursor]["class_name"] != "loop":
                    if display_nodes[cursor]["class_name"] == "provider":
                        providers.append(display_nodes[cursor]["label"])
                    cursor += 1
                if len(providers) >= 2:
                    items.append({"kind": "loop_group", "label": item["label"], "providers": providers[:2]})
                    index = cursor
                    continue
                index += 1
                continue
            items.append({"kind": "provider", "label": item["label"]})
            index += 1
        return items

    def _compact_display_nodes(self) -> list[dict[str, str]]:
        display_nodes: list[dict[str, str]] = []
        seen: set[tuple[str, str]] = set()
        for _node_id, label, class_name in self._nodes:
            compact_label = label.replace("<br/>", " ")
            if class_name == "loop":
                compact_label = compact_label.replace("repeat_until", "loop")
            key = (compact_label, class_name)
            if key in seen:
                continue
            seen.add(key)
            display_nodes.append({"label": compact_label, "class_name": class_name})
        return display_nodes

    def _loop_feedback_ranges(self, display_nodes: list[dict[str, str]]) -> list[tuple[int, int]]:
        ranges: list[tuple[int, int]] = []
        for index, item in enumerate(display_nodes):
            if item["class_name"] != "loop":
                continue
            provider_indexes: list[int] = []
            for child_index in range(index + 1, len(display_nodes)):
                if display_nodes[child_index]["class_name"] == "loop":
                    break
                if display_nodes[child_index]["class_name"] == "provider":
                    provider_indexes.append(child_index)
            if len(provider_indexes) >= 2:
                ranges.append((provider_indexes[0], provider_indexes[-1]))
        return ranges

    def _wrap_svg_label(self, label: str, width: int) -> list[str]:
        words = label.split()
        if not words:
            return [label]
        lines: list[str] = []
        current = ""
        for word in words:
            candidate = f"{current} {word}".strip()
            if current and len(candidate) > width:
                lines.append(current)
                current = word
            else:
                current = candidate
        if current:
            lines.append(current)
        return lines

    def _add_node(self, label: str, class_name: str) -> str:
        self._counter += 1
        node_id = f"n{self._counter}"
        self._nodes.append((node_id, label, class_name))
        return node_id

    def _connect(
        self,
        sources: list[str],
        targets: list[str],
        *,
        label: str = "",
        dotted: bool = False,
    ) -> None:
        style = "dotted" if dotted else "solid"
        for source in self._unique(sources):
            for target in self._unique(targets):
                if source != target:
                    self._edges.append((source, target, label, style))

    def _unique(self, values: list[str]) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for value in values:
            if value in seen:
                continue
            seen.add(value)
            result.append(value)
        return result

    def _label(self, value: str) -> str:
        return value.replace("\\", "\\\\").replace('"', '\\"')


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
            detail = self._find_detail(workspace_id, run_dir_id, request_now)
            if detail is None:
                return self._response(404, "Run not found")
            if len(segments) == 3:
                return self._run_detail(detail, refresh=self._refresh_seconds(parse_qs(parsed.query)))
            if len(segments) == 5 and segments[3] == "summaries" and segments[4] == "live.json":
                return self._summary_live_json(detail)
            if len(segments) == 4 and segments[3] == "summaries":
                return self._summary_hub(detail)
            if len(segments) == 4 and segments[3] == "tmux":
                return self._tmux_view(detail)
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
            "<thead><tr><th>Workspace</th><th>Run</th><th>State Run ID</th><th>Workflow</th><th>Persisted</th><th>Display</th><th>Cursor</th><th>Started</th><th>Elapsed</th><th>Updated</th><th>Current step start</th><th>State mtime</th><th>Read time</th><th>Heartbeat</th><th>Availability</th><th>Failure</th></tr></thead>",
            "<tbody>",
        ])
        if not rows:
            lines.append("<tr><td colspan=\"16\">No runs matched.</td></tr>")
        for row in rows:
            detail_href = f"/runs/{quote(row.workspace_id)}/{quote(row.run_dir_id)}"
            workflow = row.workflow_name or row.workflow_file or ""
            display = row.display_status
            if row.display_status_reason:
                display = f"{display} ({row.display_status_reason})"
            elapsed = (
                self._format_duration(row.elapsed_seconds)
                if row.elapsed_seconds is not None
                else ""
            )
            current_step_started = row.current_step_started_at or ""
            if row.current_step_age_seconds is not None:
                current_step_started = (
                    f"{current_step_started} "
                    f"({self._format_duration(row.current_step_age_seconds)})"
                )
            heartbeat = row.heartbeat_at or ""
            if row.heartbeat_age_seconds is not None:
                heartbeat = f"{heartbeat} ({self._format_duration(row.heartbeat_age_seconds)})"
            lines.append(
                "<tr>"
                f"<td>{self._e(row.workspace_label)}<br><small>{self._e(str(row.workspace_root))}</small></td>"
                f"<td><a href=\"{detail_href}\">{self._e(row.run_dir_id)}</a></td>"
                f"<td>{self._e(row.state_run_id or '')}</td>"
                f"<td>{self._e(workflow)}</td>"
                f"<td>{self._e(row.persisted_status)}</td>"
                f"<td>{self._e(display)}</td>"
                f"<td>{self._e(row.cursor_summary)}</td>"
                f"<td>{self._e(row.started_at or '')}</td>"
                f"<td>{self._e(elapsed)}</td>"
                f"<td>{self._e(row.updated_at or '')}</td>"
                f"<td>{self._e(current_step_started)}</td>"
                f"<td>{self._e(self._format_timestamp(row.state_mtime))}</td>"
                f"<td>{self._e(row.read_time or '')}</td>"
                f"<td>{self._e(heartbeat)}</td>"
                f"<td>{self._e(self._format_availability(row.availability))}</td>"
                f"<td>{self._e(row.failure_summary)}</td>"
                "</tr>"
            )
        lines.extend(["</tbody></table>", "</main>", "</body></html>"])
        return self._html_response("\n".join(lines))

    def _find_detail(self, workspace_id: str, run_dir_id: str, now: datetime):
        scan = self.scanner.scan()
        for run in scan.runs:
            if run.workspace.id == workspace_id and run.run_dir_id == run_dir_id:
                return RunProjector(now=now).project_detail(run)
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
            f"<dt>Workflow</dt><dd>{self._e(row.workflow_name or row.workflow_file or '')}</dd>",
            f"<dt>Persisted status</dt><dd>{self._e(row.persisted_status)}</dd>",
            f"<dt>Display status</dt><dd>{self._e(row.display_status)} {self._e(row.display_status_reason or '')}</dd>",
            "</dl>",
            "</section>",
        ])
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

        lines.extend(["<section><h2>Summary Hub</h2>"])
        summary_href = f"/runs/{quote(row.workspace_id)}/{quote(row.run_dir_id)}/summaries"
        if (row.run_root / "summaries" / "index.json").exists():
            lines.append(f"<p><a href=\"{summary_href}\">Open Summary Hub</a></p>")
        else:
            lines.append("<p>No summary hub is available for this run.</p>")
        lines.append("</section>")

        lines.extend(["<section><h2>Step Timeline</h2><ul>"])
        for step in detail.steps:
            href = f"/runs/{quote(row.workspace_id)}/{quote(row.run_dir_id)}/steps/{quote(step.ref)}"
            lines.append(
                f"<li><a href=\"{href}\">{self._e(step.name)}</a> "
                f"{self._e(step.status)} {self._e(step.kind)}</li>"
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

        lines.extend(["<section><h2>Observability Files</h2>"])
        self._append_file_group(
            lines,
            row,
            "Prompt Audits",
            detail.observability_files.get("prompt_audits", []),
        )
        self._append_file_group(
            lines,
            row,
            "Execution Logs",
            list(detail.observability_files.get("stdout", []))
            + list(detail.observability_files.get("stderr", [])),
        )
        self._append_file_group(
            lines,
            row,
            "Provider Sessions",
            list(detail.observability_files.get("provider_sessions", []))
            + list(detail.observability_files.get("provider_transport", [])),
        )
        self._append_file_group(
            lines,
            row,
            "State Backups",
            detail.observability_files.get("state_backups", []),
        )
        self._append_file_group(
            lines,
            row,
            "Summary Hub Files",
            detail.observability_files.get("summaries", []),
        )
        lines.append("</section>")

        lines.extend(["<section><h2>Common Artifacts</h2>"])
        if detail.common_artifact_refs:
            lines.append("<ul>")
            for name, file_ref in detail.common_artifact_refs.items():
                lines.append(
                    f"<li>{self._e(name)}: <a href=\"{self._file_href(row, file_ref)}\">"
                    f"{self._e(file_ref.scope)}:{self._e(file_ref.route_path)}</a></li>"
                )
            lines.append("</ul>")
        else:
            lines.append("<p>No common artifact file references.</p>")
        lines.append("</section>")

        lines.append("<section><h2>Inputs</h2>")
        lines.append(f"<pre>{self._json(detail.bound_inputs)}</pre></section>")
        lines.append("<section><h2>Outputs</h2>")
        lines.append(f"<pre>{self._json(detail.workflow_outputs)}</pre></section>")
        lines.append("<section><h2>Run Error</h2>")
        lines.append(f"<pre>{self._json(detail.error)}</pre></section>")
        lines.append("<section><h2>Finalization</h2>")
        lines.append(f"<pre>{self._json(detail.finalization)}</pre></section>")
        lines.append("<section><h2>artifact_versions</h2>")
        lines.append(f"<pre>{self._json(detail.artifact_versions)}</pre></section>")
        lines.append("<section><h2>artifact_consumes</h2>")
        lines.append(f"<pre>{self._json(detail.artifact_consumes)}</pre></section>")
        lines.append("<section><h2>call_frame_artifact_versions</h2>")
        lines.append(f"<pre>{self._json(detail.call_frame_artifact_versions)}</pre></section>")
        lines.append("<section><h2>call_frame_artifact_consumes</h2>")
        lines.append(f"<pre>{self._json(detail.call_frame_artifact_consumes)}</pre></section>")
        lines.append(f"<p><a href=\"/runs/{quote(row.workspace_id)}/{quote(row.run_dir_id)}/state\">State JSON</a></p>")
        lines.extend(["</main></body></html>"])
        return self._html_response("\n".join(lines))

    def _summary_hub(self, detail) -> DashboardResponse:
        row = detail.row
        resolver = FileReferenceResolver(row.workspace_root, row.run_root)
        back_href = f"/runs/{quote(row.workspace_id)}/{quote(row.run_dir_id)}"
        live_href = f"/runs/{quote(row.workspace_id)}/{quote(row.run_dir_id)}/summaries/live.json"
        script_nonce = secrets.token_urlsafe(16)
        index_path = row.run_root / "summaries" / "index.json"
        summary_entries = self._summary_index_entries(row.run_root)
        workflow_structure_html = self._summary_workflow_structure_html(detail, summary_entries)
        tmux_session_html = self._summary_tmux_session_html(row)
        lines = [
            "<!doctype html>",
            "<html><head><meta charset=\"utf-8\"><title>Summary Hub</title>",
            self._summary_hub_style(),
            "</head><body><main>",
            "<header class=\"summary-hero\">",
            "<div>",
            "<p class=\"eyebrow\">Workflow observability</p>",
            f"<h1>Summary Hub</h1><p class=\"run-id\">{self._e(row.run_dir_id)}</p>",
            "</div>",
            f"<p class=\"summary-actions\"><a href=\"{back_href}\">Back to run</a></p>",
            "</header>",
            "<div class=\"summary-top-grid\">",
            f"<section id=\"live-current-step\" class=\"live-panel\" data-live-url=\"{live_href}\">",
            "<h2>Current Step</h2>",
            "<dl class=\"live-grid\">",
            "<dt>Run</dt><dd><span data-live-field=\"run-status\">Loading...</span></dd>",
            "<dt>Step</dt><dd><span data-live-field=\"step-name\">Loading...</span></dd>",
            "<dt>Provider step</dt><dd><span data-live-field=\"provider-step\">Loading...</span> "
            "<a data-live-link=\"provider-prompt\" hidden>Prompt</a> "
            "<a data-live-link=\"provider-stderr\" hidden>Log</a></dd>",
            "<dt>Started</dt><dd><span data-live-field=\"step-started\"></span></dd>",
            "<dt>Age</dt><dd><span data-live-field=\"step-age\"></span></dd>",
            "<dt>Heartbeat</dt><dd><span data-live-field=\"heartbeat\"></span></dd>",
            "<dt>Summaries</dt><dd><span data-live-field=\"summary-counts\"></span></dd>",
            "<dt>Latest current-step summary</dt><dd><a data-live-link=\"latest-summary\" hidden>Open summary</a><span data-live-field=\"latest-summary-empty\">None yet.</span></dd>",
            "<dt>Live agent note</dt><dd><pre class=\"live-note-text\" data-live-field=\"live-note\">No live note yet.</pre><a data-live-link=\"live-note\" hidden>Open live note</a></dd>",
            "</dl>",
            "<p class=\"muted\">Updates every few seconds from run state and summary artifacts.</p>",
            "</section>",
            tmux_session_html,
            "</div>",
            workflow_structure_html,
        ]
        if not index_path.exists():
            lines.extend(
                [
                    "<section><h2>No Summary Hub</h2>",
                    "<p>No summary hub is available for this run.</p>",
                    "</section></main></body></html>",
                ]
            )
            return self._html_response("\n".join(lines), script_nonce=script_nonce)

        try:
            index_payload = json.loads(index_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            index_ref = resolver.run_ref("summaries/index.json", label="summary index")
            lines.extend(
                [
                    "<section><h2>Summary index is invalid</h2>",
                    f"<p>{self._e(exc)}</p>",
                    f"<p><a href=\"{self._file_href(row, index_ref)}\">View index file</a></p>",
                    "</section></main></body></html>",
                ]
            )
            return self._html_response("\n".join(lines), script_nonce=script_nonce)

        entries = index_payload.get("entries") if isinstance(index_payload, Mapping) else None
        if not isinstance(entries, list):
            entries = []
            warning = "Summary index is invalid: entries must be a list."
        else:
            warning = ""
        counts: dict[str, int] = {}
        for entry in entries:
            if isinstance(entry, Mapping):
                kind = str(entry.get("kind") or "step")
                counts[kind] = counts.get(kind, 0) + 1
        counts_text = ", ".join(f"{kind}={count}" for kind, count in sorted(counts.items())) or "none"
        lines.extend(
            [
                "<section><h2>Overview</h2>",
                f"<p>Total summaries: {self._e(len(entries))}; {self._e(counts_text)}</p>",
            ]
        )
        if warning:
            lines.append(f"<p>{self._e(warning)}</p>")
        lines.append("</section>")

        lines.append(self._summary_provider_visit_stats_html(row, resolver, entries))

        lines.extend(
            [
                "<section><h2>Summary Entries</h2>",
                "<table>",
                "<thead><tr><th>Step</th><th>Kind</th><th>Profile</th><th>Status</th><th>Duration</th><th>Frame</th><th>Files</th></tr></thead>",
                "<tbody>",
            ]
        )
        if not entries:
            lines.append("<tr><td colspan=\"7\">No summary entries.</td></tr>")
        for entry in entries:
            if not isinstance(entry, Mapping):
                continue
            duration = entry.get("duration_ms")
            duration_text = f"{duration} ms" if duration is not None else ""
            file_links = self._summary_entry_links(row, resolver, entry)
            context_label = self._summary_entry_context_label(entry)
            step_label = self._step_label_html(self._str_or_none(entry.get("step_name")) or "", context_label)
            lines.append(
                "<tr>"
                f"<td>{step_label}</td>"
                f"<td>{self._e(entry.get('kind') or '')}</td>"
                f"<td>{self._e(entry.get('profile') or '')}</td>"
                f"<td>{self._e(entry.get('status') or '')}</td>"
                f"<td>{self._e(duration_text)}</td>"
                f"<td>{self._e(entry.get('frame_root') or '')}</td>"
                f"<td>{file_links}</td>"
                "</tr>"
            )
        lines.extend(["</tbody></table>", "</section>"])

        lines.extend(["<section><h2>Run Summary Preview</h2>"])
        try:
            summary_ref = resolver.run_ref("summaries/run-summary.md", label="run summary")
        except UnsafePathError:
            summary_ref = None
        if summary_ref is not None and summary_ref.status == "ok":
            preview = PreviewRenderer().preview(summary_ref.absolute_path)
            if preview.status == "ok":
                if preview.truncated:
                    size = preview.size_bytes if preview.size_bytes is not None else ""
                    lines.append(
                        f"<p>Preview truncated at dashboard cap; file size {self._e(size)} bytes.</p>"
                    )
                lines.extend(
                    [
                        '<article class="markdown-preview run-summary-preview">',
                        self._render_markdown_preview(
                            preview.display_text,
                            link_mapper=self._run_summary_preview_link_mapper(row, resolver),
                        ),
                        "</article>",
                    ]
                )
            else:
                lines.append(f"<p>{self._e(preview.status)}</p>")
            lines.append(f"<p><a href=\"{self._file_href(row, summary_ref)}\">Open run-summary.md</a></p>")
        else:
            lines.append("<p>No run-summary.md file is available.</p>")
        lines.extend([
            "</section>",
            self._summary_live_script(script_nonce),
            "</main></body></html>",
        ])
        return self._html_response("\n".join(lines), script_nonce=script_nonce)

    def _summary_provider_visit_stats_html(
        self,
        row,
        resolver: FileReferenceResolver,
        entries: Sequence[object],
    ) -> str:
        stats: dict[str, dict[str, object]] = {}
        for entry in entries:
            if not isinstance(entry, Mapping):
                continue
            if entry.get("kind") != "provider":
                continue
            step_name = self._str_or_none(entry.get("step_name")) or "(unnamed provider)"
            stat = stats.setdefault(
                step_name,
                {
                    "visits": 0,
                    "statuses": {},
                    "latest_context": "",
                    "first_href": "",
                    "error_href": "",
                },
            )
            stat["visits"] = int(stat["visits"]) + 1
            status = self._str_or_none(entry.get("status")) or "unknown"
            statuses = stat["statuses"]
            if isinstance(statuses, dict):
                statuses[status] = int(statuses.get(status, 0)) + 1
            stat["latest_context"] = self._summary_entry_context_label(entry)
            for key in ("summary_path", "error_path", "snapshot_path"):
                path = entry.get(key)
                if not isinstance(path, str) or not path:
                    continue
                try:
                    file_ref = resolver.run_ref(path, label=key)
                except UnsafePathError:
                    continue
                href = self._file_href(row, file_ref)
                if not stat["first_href"]:
                    stat["first_href"] = href
                if key == "error_path" and not stat["error_href"]:
                    stat["error_href"] = href

        lines = ["<section class=\"provider-visit-stats\"><h2>Provider Visit Stats</h2>"]
        if not stats:
            lines.append("<p class=\"muted\">No provider summary visits recorded yet.</p></section>")
            return "\n".join(lines)

        lines.extend(
            [
                "<table>",
                "<thead><tr><th>Provider step</th><th>Visits</th><th>Status counts</th><th>Latest context</th><th>Files</th></tr></thead>",
                "<tbody>",
            ]
        )
        for step_name, stat in sorted(
            stats.items(),
            key=lambda item: (-int(item[1]["visits"]), item[0].lower()),
        ):
            visits = int(stat["visits"])
            statuses = stat["statuses"] if isinstance(stat["statuses"], dict) else {}
            status_text = ", ".join(
                f"{count} {name}" for name, count in sorted(statuses.items())
            )
            latest_context = self._str_or_none(stat.get("latest_context")) or ""
            first_href = self._str_or_none(stat.get("first_href"))
            error_href = self._str_or_none(stat.get("error_href"))
            name_html = self._e(step_name)
            if first_href:
                name_html = f"<a href=\"{first_href}\">{name_html}</a>"
            file_links = []
            if first_href:
                file_links.append(f"<a href=\"{first_href}\">first artifact</a>")
            if error_href and error_href != first_href:
                file_links.append(f"<a href=\"{error_href}\">first error</a>")
            lines.append(
                "<tr>"
                f"<td>{name_html}</td>"
                f"<td>{visits} {'visit' if visits == 1 else 'visits'}</td>"
                f"<td>{self._e(status_text)}</td>"
                f"<td>{self._e(latest_context)}</td>"
                f"<td>{' '.join(file_links)}</td>"
                "</tr>"
            )
        lines.extend(["</tbody></table>", "</section>"])
        return "\n".join(lines)

    def _summary_hub_style(self) -> str:
        return (
            "<style>"
            "*{box-sizing:border-box}"
            "html{background:#f4f7fb}"
            "body{font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,\"Segoe UI\",sans-serif;margin:0;color:#1f2933;overflow-x:hidden}"
            "main{max-width:1440px;margin:0 auto;padding:1.15rem 1.4rem 2rem}"
            "section{margin-block:1rem}"
            "h1,h2,h3,p{overflow-wrap:anywhere}"
            "h1{margin:.05rem 0;font-size:1.8rem;letter-spacing:0}"
            "h2{margin:.05rem 0 .65rem;font-size:1.2rem;letter-spacing:0}"
            "h3{letter-spacing:0}"
            "a{color:#15517f}"
            "table{border-collapse:collapse;width:100%;font-size:.86rem;table-layout:fixed}"
            "td,th{border:1px solid #cfd8e3;padding:.38rem;text-align:left;vertical-align:top;overflow-wrap:anywhere}"
            "pre{background:#f1f5f9;border:1px solid #d8e0e6;border-radius:6px;padding:.65rem;overflow:auto;max-width:100%}"
            "code{white-space:pre-wrap}"
            ".muted{color:#64748b}"
            ".summary-hero{display:flex;align-items:flex-end;justify-content:space-between;gap:1rem;margin-bottom:.9rem;border-bottom:1px solid #d8e0e6;padding-bottom:.75rem}"
            ".eyebrow{margin:0;color:#64748b;text-transform:uppercase;font-size:.72rem;font-weight:700;letter-spacing:.08em}"
            ".run-id{margin:.15rem 0 0;color:#475569;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:.86rem}"
            ".summary-actions{margin:0;white-space:nowrap}"
            ".summary-top-grid{display:grid;grid-template-columns:minmax(0,1.45fr) minmax(18rem,.55fr);gap:.9rem;align-items:start}"
            ".workflow-map,.live-panel,.tmux-session{border:1px solid #cbd5e1;border-radius:10px;background:#fff;box-shadow:0 1px 2px rgba(15,23,42,.04)}"
            ".workflow-map{padding:.95rem}"
            ".workflow-map h2{margin:.25rem 0 .5rem}"
            ".workflow-source{margin:.25rem 0 .75rem;color:#52616b}"
            ".workflow-tree,.workflow-tree ol{list-style:none;margin:.15rem 0 0 .75rem;padding:0;border-left:1px solid #d8e0e6}"
            ".workflow-tree{margin-left:0;border-left:0}"
            ".workflow-node{margin:.16rem 0;padding-left:.6rem}"
            ".workflow-node.provider{margin:.38rem 0}"
            ".workflow-card{border-radius:6px;background:transparent;padding:.06rem 0;box-shadow:none}"
            ".workflow-node.provider>.workflow-card{border:1px solid #78a8d8;border-left:5px solid #2f80c1;background:#f7fbff;padding:.45rem .6rem}"
            ".workflow-node.deterministic>.workflow-card{border:0;border-left:0;background:transparent;padding:.02rem 0}"
            ".workflow-node.contains-provider>.workflow-card{border-left:3px solid #93c5fd;background:#f8fbff;padding:.16rem 0 .16rem .45rem}"
            ".workflow-title{display:inline-flex;gap:.35rem;align-items:center;flex-wrap:wrap;cursor:pointer;line-height:1.25;max-width:100%}"
            ".workflow-node.provider>.workflow-card>.workflow-title{display:flex}"
            ".workflow-name{font-weight:600}"
            ".workflow-node.deterministic .workflow-name{font-weight:500;font-size:.92rem;color:#2f3b45}"
            ".workflow-node.provider .workflow-name{font-weight:700;font-size:1rem;color:#102a43}"
            ".workflow-kind{font-size:.72rem;background:#edf2f5;color:#52616b;border-radius:999px;padding:.05rem .35rem}"
            ".workflow-node.provider .workflow-kind{background:#dceeff;color:#15517f}"
            ".workflow-node.observed .workflow-kind{background:#f4efe2;color:#6b4e16}"
            ".workflow-badge{font-size:.72rem;color:#52616b;background:#edf2f5;border-radius:999px;padding:.05rem .35rem}"
            ".workflow-badge.provider-inside{background:#dceeff;color:#15517f}"
            ".workflow-details{margin-top:.45rem;padding-top:.45rem;border-top:1px solid #e5edf2}"
            ".workflow-links{display:grid;grid-template-columns:repeat(auto-fit,minmax(14rem,1fr));gap:.35rem .75rem}"
            ".workflow-link-group{font-size:.9rem}"
            ".workflow-link-group strong{display:block;color:#52616b;margin-bottom:.15rem}"
            ".workflow-link-group a{display:inline-block;margin:0 .35rem .2rem 0}"
            ".workflow-summary-meta{margin:.1rem 0 .35rem;color:#52616b;font-size:.9rem}"
            ".summary-context{color:#52616b;font-size:.85rem}"
            ".provider-visit-stats table{margin-top:.45rem}"
            ".provider-visit-stats td:nth-child(2),.provider-visit-stats td:nth-child(3){white-space:nowrap}"
            ".markdown-preview{max-width:60rem}"
            ".markdown-preview code{background:#edf2f5;padding:.08rem .2rem;border-radius:3px}"
            ".markdown-preview pre code{background:transparent;padding:0}"
            ".run-summary-preview{background:#fff;border:1px solid #d8e0e6;border-radius:8px;padding:.75rem .9rem}"
            ".run-summary-preview h1:first-child,.run-summary-preview h2:first-child{margin-top:0}"
            ".workflow-invocations{display:grid;gap:.35rem}"
            ".workflow-invocation{border:1px solid #d8e0e6;border-radius:6px;background:#fff;padding:.3rem .45rem}"
            ".workflow-invocation>summary{cursor:pointer;font-weight:600;color:#243b53}"
            ".workflow-invocation-body{margin-top:.35rem;padding-top:.35rem;border-top:1px solid #edf2f5}"
            ".provider-flow{border:1px solid #d8e0e6;border-radius:8px;background:#f8fafc;margin:.75rem 0 1rem;padding:.75rem;overflow:hidden}"
            ".provider-flow h3{margin:.1rem 0 .35rem}"
            ".provider-flow-strip{display:grid;gap:.75rem;margin:.65rem 0 .35rem}"
            ".provider-flow-row{display:grid;grid-template-columns:repeat(var(--flow-columns),minmax(0,1fr));gap:.7rem .8rem;align-items:start}"
            ".provider-flow-provider-card,.provider-flow-loop-card{border-radius:6px;border:1px solid #9fc6e8;background:#edf6ff;color:#102a43;box-sizing:border-box}"
            ".provider-flow-stage{position:relative;min-width:0;max-width:100%}"
            ".provider-flow-stage.has-next::after{content:'\\279C';position:absolute;right:-.62rem;top:50%;transform:translateY(-50%);color:#334155;font-weight:900;font-size:1.08rem;line-height:1;z-index:1}"
            ".provider-flow-stage.has-prev::after{content:'\\279C';position:absolute;right:-.62rem;top:50%;transform:translateY(-50%) rotate(180deg);color:#334155;font-weight:900;font-size:1.08rem;line-height:1;z-index:1}"
            ".provider-flow-stage.turn-next::after{content:'\\279C';position:absolute;left:50%;bottom:-.68rem;transform:translateX(-50%) rotate(90deg);color:#334155;font-weight:900;font-size:1.08rem;line-height:1;z-index:1}"
            ".provider-flow-provider-card{width:100%;min-height:2.7rem;padding:.48rem .6rem;font-weight:700;text-align:center;display:flex;align-items:center;justify-content:center;line-height:1.15;overflow-wrap:anywhere;word-break:normal}"
            ".provider-flow-loop-card{width:100%;min-height:7.2rem;padding:.44rem .5rem;background:#fffaf3;border-color:#d98b54;overflow:hidden}"
            ".provider-flow-loop-title{font-weight:700;color:#8a330d;text-align:center;font-size:.82rem;line-height:1.12;margin-bottom:.34rem}"
            ".provider-flow-loop-body{display:flex;flex-direction:column;align-items:center;justify-content:center;gap:.16rem;flex-wrap:nowrap}"
            ".provider-flow-mini-provider{width:100%;background:#edf6ff;border:1px solid #9fc6e8;border-radius:5px;padding:.24rem .32rem;font-weight:700;font-size:.76rem;line-height:1.08;text-align:center;min-width:0;overflow-wrap:anywhere;word-break:normal}"
            ".provider-flow-mini-arrow{align-self:center;color:#52616b;font-weight:700;line-height:.8;transform:rotate(90deg)}"
            ".provider-flow-loop-note{text-align:center;color:#a4410c;font-size:.78rem;margin-top:.3rem}"
            ".provider-flow-source{margin-top:.6rem}"
            ".provider-flow-mermaid{white-space:pre-wrap;overflow-wrap:break-word;margin:.5rem 0 0}"
            ".live-panel{padding:.85rem .95rem;background:#fff}"
            ".live-grid{display:grid;grid-template-columns:max-content minmax(10rem,1fr) max-content minmax(10rem,1fr);gap:.32rem .75rem}"
            ".live-grid dt{font-weight:600}"
            ".live-grid dd{margin:0}"
            ".live-grid dt:nth-of-type(9){grid-column:1 / -1;margin-top:.35rem}"
            ".live-grid dd:nth-of-type(9){grid-column:1 / -1}"
            ".live-note-text{white-space:pre-wrap;overflow-wrap:break-word;max-height:8.5rem;margin:.15rem 0 .25rem;font-size:.84rem;line-height:1.3}"
            ".tmux-session{padding:.85rem .95rem;background:#fff}"
            ".tmux-session p{margin:.2rem 0 .55rem}"
            ".tmux-session details{margin-top:.4rem}"
            ".tmux-session pre{font-size:.78rem;white-space:pre-wrap}"
            "@media (max-width: 900px){main{padding:.85rem}.summary-hero{align-items:flex-start;flex-direction:column}.summary-top-grid{grid-template-columns:1fr}.provider-flow-row{grid-template-columns:1fr}.provider-flow-stage::after{display:none}.live-grid{grid-template-columns:1fr}.live-grid dt{margin-top:.3rem}}"
            "</style>"
        )

    def _summary_tmux_session_html(self, row) -> str:
        tmux = self._summary_tmux_session_payload(row)
        if tmux is None:
            return ""
        label = tmux["target"] or tmux["socket"]
        href = f"/runs/{quote(row.workspace_id)}/{quote(row.run_dir_id)}/tmux"
        target_text = (
            f"<p>Workflow tmux session: <a href=\"{self._e(href)}\">{self._e(label)}</a></p>"
            if tmux["target"]
            else f"<p>Workflow tmux socket: <a href=\"{self._e(href)}\">{self._e(label)}</a></p>"
        )
        return (
            "<section id=\"tmux-session\" class=\"tmux-session\">"
            "<h2>Terminal</h2>"
            f"{target_text}"
            "<details>"
            "<summary>Attach command</summary>"
            f"<pre>{self._e(tmux['shell_text'])}</pre>"
            "</details>"
            "</section>"
        )

    def _tmux_view(self, detail) -> DashboardResponse:
        row = detail.row
        back_href = f"/runs/{quote(row.workspace_id)}/{quote(row.run_dir_id)}/summaries"
        tmux = self._summary_tmux_session_payload(row)
        if tmux is None:
            return self._response(404, "No tmux session metadata is available for this run.")
        target = tmux.get("target")
        if not isinstance(target, str) or not target:
            return self._response(404, "No tmux pane target could be resolved for this run.")
        socket = str(tmux["socket"])
        try:
            pane = self._capture_tmux_pane(socket, target)
            error = None
        except RuntimeError as exc:
            pane = ""
            error = str(exc)
        lines = [
            "<!doctype html>",
            "<html><head><meta charset=\"utf-8\"><title>Tmux Pane</title>",
            "<meta http-equiv=\"refresh\" content=\"3\">",
            "<style>body{font-family:sans-serif;margin:2rem;color:#1f2933}"
            "pre{background:#07111f;color:#e5eef9;padding:1rem;overflow:auto;white-space:pre-wrap}"
            "code{background:#f5f5f5;padding:.1rem .25rem}</style>",
            "</head><body><main>",
            f"<h1>Tmux Pane: {self._e(target)}</h1>",
            f"<p><a href=\"{back_href}\">Back to Summary Hub</a></p>",
            f"<p>Socket: <code>{self._e(socket)}</code></p>",
            f"<p>Attach manually: <code>{self._e(str(tmux['shell_text']))}</code></p>",
        ]
        if error:
            lines.append(f"<p>{self._e(error)}</p>")
        lines.append(f"<pre>{self._e(pane)}</pre>")
        lines.append("</main></body></html>")
        return self._html_response("\n".join(lines))

    def _summary_tmux_session_payload(self, row) -> Optional[dict[str, object]]:
        metadata_path = row.run_root / "monitor_process.json"
        try:
            raw = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(raw, Mapping):
            return None
        tmux_raw = raw.get("tmux")
        if not isinstance(tmux_raw, str) or not tmux_raw:
            return None
        socket = tmux_raw.split(",", 1)[0]
        if not socket:
            return None
        pid = raw.get("pid")
        target = self._str_or_none(raw.get("tmux_target")) or self._str_or_none(raw.get("tmux_session"))
        if target is None and isinstance(pid, int):
            target = self._resolve_tmux_target(socket, pid)
        argv = ["tmux", "-S", socket, "attach"]
        if target:
            argv.extend(["-t", target])

        return {
            "socket": socket,
            "target": target,
            "shell_text": shlex.join(argv),
        }

    def _resolve_tmux_target(self, socket: str, pid: int) -> Optional[str]:
        try:
            result = subprocess.run(
                [
                    "tmux",
                    "-S",
                    socket,
                    "list-panes",
                    "-a",
                    "-F",
                    "#{session_name}:#{window_index}.#{pane_index}\t#{pane_pid}",
                ],
                capture_output=True,
                check=False,
                encoding="utf-8",
                timeout=0.5,
            )
        except (OSError, subprocess.TimeoutExpired):
            return None
        if result.returncode != 0:
            return None
        for line in result.stdout.splitlines():
            target, sep, pane_pid_raw = line.partition("\t")
            if not sep:
                continue
            try:
                pane_pid = int(pane_pid_raw)
            except ValueError:
                continue
            if pid == pane_pid or self._process_is_descendant(pid, pane_pid):
                return target
        return None

    def _capture_tmux_pane(self, socket: str, target: str, lines: int = 240) -> str:
        try:
            result = subprocess.run(
                [
                    "tmux",
                    "-S",
                    socket,
                    "capture-pane",
                    "-p",
                    "-J",
                    "-t",
                    target,
                    "-S",
                    f"-{max(1, int(lines))}",
                ],
                capture_output=True,
                check=False,
                encoding="utf-8",
                timeout=1.0,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise RuntimeError(f"tmux capture failed: {exc}") from exc
        if result.returncode != 0:
            message = result.stderr.strip() or f"tmux exited {result.returncode}"
            raise RuntimeError(message)
        return result.stdout

    def _process_is_descendant(self, pid: int, ancestor_pid: int) -> bool:
        seen: set[int] = set()
        current = pid
        for _ in range(64):
            if current == ancestor_pid:
                return True
            if current in seen:
                return False
            seen.add(current)
            parent = self._process_parent_pid(current)
            if parent is None or parent <= 0:
                return False
            current = parent
        return False

    def _process_parent_pid(self, pid: int) -> Optional[int]:
        try:
            stat = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
        except OSError:
            return None
        close_paren = stat.rfind(")")
        if close_paren < 0:
            return None
        fields = stat[close_paren + 2 :].split()
        if len(fields) < 2:
            return None
        try:
            return int(fields[1])
        except ValueError:
            return None

    def _summary_live_json(self, detail) -> DashboardResponse:
        return self._json_response(self._summary_live_payload(detail))

    def _summary_live_payload(self, detail) -> dict[str, object]:
        row = detail.row
        resolver = FileReferenceResolver(row.workspace_root, row.run_root)
        state = detail.state if isinstance(detail.state, Mapping) else {}
        current_step = state.get("current_step") if isinstance(state.get("current_step"), Mapping) else {}
        current_name = self._str_or_none(current_step.get("name"))
        current_step_id = self._str_or_none(current_step.get("step_id"))
        current_iteration = self._current_step_iteration(state, current_name)
        current_visit_count = current_step.get("visit_count")
        current_context_label = self._context_label(
            current_iteration,
            current_visit_count,
            iteration_scope=current_name,
        )
        current_display_name = self._display_name_with_context(current_name, current_context_label)
        entries = self._summary_index_entries(row.run_root)
        current_provider_step = self._current_provider_step_payload(row, resolver, state)
        counts: dict[str, int] = {}
        for entry in entries:
            kind = str(entry.get("kind") or "step")
            counts[kind] = counts.get(kind, 0) + 1

        latest = None
        if current_name:
            for entry in reversed(entries):
                if str(entry.get("step_name") or "") == current_name:
                    latest = self._summary_entry_payload(row, resolver, entry)
                    break

        step_href = None
        if current_name or current_step_id:
            for step in detail.steps:
                if current_name in {step.name, step.ref} or current_step_id in {step.step_id, step.ref}:
                    step_href = f"/runs/{quote(row.workspace_id)}/{quote(row.run_dir_id)}/steps/{quote(step.ref)}"
                    break

        return {
            "schema": "dashboard_summary_live/v1",
            "run": {
                "run_dir_id": row.run_dir_id,
                "state_run_id": row.state_run_id,
                "persisted_status": row.persisted_status,
                "display_status": row.display_status,
                "display_status_reason": row.display_status_reason,
                "cursor_summary": row.cursor_summary,
                "read_time": row.read_time,
            },
            "current_step": {
                "name": current_name,
                "display_name": current_display_name,
                "step_id": current_step_id,
                "iteration": current_iteration,
                "visit_count": current_visit_count,
                "context_label": current_context_label,
                "started_at": self._str_or_none(current_step.get("started_at")),
                "age_seconds": row.current_step_age_seconds,
                "age_text": (
                    self._format_duration(row.current_step_age_seconds)
                    if row.current_step_age_seconds is not None
                    else ""
                ),
                "heartbeat_at": row.heartbeat_at,
                "heartbeat_age_seconds": row.heartbeat_age_seconds,
                "heartbeat_age_text": (
                    self._format_duration(row.heartbeat_age_seconds)
                    if row.heartbeat_age_seconds is not None
                    else ""
                ),
                "step_href": step_href,
            },
            "current_provider_step": current_provider_step,
            "summaries": {
                "total": len(entries),
                "counts": counts,
                "current_step_latest": latest,
            },
            "live_note": self._live_agent_note_payload(
                row,
                resolver,
                state,
                current_name,
                current_step_id,
                current_provider_step,
            ),
        }

    def _current_provider_step_payload(
        self,
        row,
        resolver: FileReferenceResolver,
        state: Mapping[str, object] | None = None,
    ) -> dict[str, object]:
        state_provider = self._current_provider_step_from_state(state or {})
        candidates: list[dict[str, object]] = []
        for prompt_path in row.run_root.rglob("logs/*.prompt.txt"):
            if not prompt_path.is_file():
                continue
            try:
                prompt_stat = prompt_path.stat()
                prompt_rel = prompt_path.relative_to(row.run_root).as_posix()
            except (OSError, ValueError):
                continue
            qualified_name = prompt_path.name[: -len(".prompt.txt")]
            stderr_path = prompt_path.with_name(f"{qualified_name}.stderr")
            stdout_path = prompt_path.with_name(f"{qualified_name}.stdout")
            stderr_exists = stderr_path.is_file()
            try:
                stderr_mtime_ns = stderr_path.stat().st_mtime_ns if stderr_exists else None
            except OSError:
                stderr_exists = False
                stderr_mtime_ns = None
            in_progress = not stderr_exists or (
                stderr_mtime_ns is not None and stderr_mtime_ns < prompt_stat.st_mtime_ns
            )
            candidates.append(
                {
                    "qualified_name": qualified_name,
                    "name": qualified_name.split(".")[-1],
                    "prompt_path": prompt_path,
                    "prompt_rel": prompt_rel,
                    "stderr_path": stderr_path,
                    "stdout_path": stdout_path,
                    "in_progress": in_progress,
                    "mtime_ns": prompt_stat.st_mtime_ns,
                    "updated_at": datetime.fromtimestamp(prompt_stat.st_mtime, timezone.utc).isoformat(),
                }
            )

        if state_provider is not None:
            matching_log = None
            for candidate in candidates:
                if state_provider["name"] in {candidate["name"], candidate["qualified_name"]}:
                    matching_log = candidate
                    break
            if matching_log is None:
                return state_provider
            candidates = [dict(matching_log, in_progress=True)]

        live_note_provider = None
        if state_provider is None:
            live_note_provider = self._current_provider_step_from_live_note_metadata(row, resolver)

        if not candidates:
            if live_note_provider is not None:
                return live_note_provider
            return {
                "available": False,
                "reason": "No provider prompt log has been recorded for this run yet.",
            }

        active_candidates = [candidate for candidate in candidates if candidate["in_progress"]]
        selected = max(active_candidates or candidates, key=lambda candidate: int(candidate["mtime_ns"]))
        if live_note_provider is not None and self._provider_payload_is_newer_than_log(live_note_provider, selected):
            return live_note_provider
        prompt_href = None
        try:
            prompt_href = self._file_href(row, resolver.run_ref(str(selected["prompt_rel"])))
        except UnsafePathError:
            prompt_href = None

        stderr_href = None
        stderr_path = selected["stderr_path"]
        if isinstance(stderr_path, Path) and stderr_path.is_file():
            try:
                stderr_href = self._file_href(row, resolver.run_ref(stderr_path.relative_to(row.run_root).as_posix()))
            except (UnsafePathError, ValueError):
                stderr_href = None

        stdout_href = None
        stdout_path = selected["stdout_path"]
        if isinstance(stdout_path, Path) and stdout_path.is_file():
            try:
                stdout_href = self._file_href(row, resolver.run_ref(stdout_path.relative_to(row.run_root).as_posix()))
            except (UnsafePathError, ValueError):
                stdout_href = None

        return {
            "available": True,
            "name": selected["name"],
            "qualified_name": selected["qualified_name"],
            "status": "in_progress" if selected["in_progress"] else "most_recent",
            "updated_at": selected["updated_at"],
            "display_name": self._display_name_with_context(
                self._str_or_none(selected.get("name")),
                self._frame_root_context_label(self._str_or_none(selected.get("prompt_rel")) or ""),
            ),
            "prompt_href": prompt_href,
            "stderr_href": stderr_href,
            "stdout_href": stdout_href,
        }

    def _provider_payload_is_newer_than_log(
        self,
        provider_payload: Mapping[str, object],
        log_candidate: Mapping[str, object],
    ) -> bool:
        provider_time = self._parse_dashboard_datetime(self._str_or_none(provider_payload.get("updated_at")))
        log_time = self._parse_dashboard_datetime(self._str_or_none(log_candidate.get("updated_at")))
        if provider_time is None or log_time is None:
            return False
        return provider_time >= log_time

    def _current_provider_step_from_live_note_metadata(
        self,
        row,
        resolver: FileReferenceResolver,
    ) -> dict[str, object] | None:
        try:
            metadata_ref = resolver.run_ref("summaries/live-current-step.json", label="live note metadata")
        except UnsafePathError:
            return None
        if metadata_ref.status != "ok":
            return None
        try:
            metadata = json.loads(metadata_ref.absolute_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(metadata, Mapping):
            return None
        step_name = self._str_or_none(metadata.get("step_name"))
        if not step_name:
            return None
        return {
            "available": True,
            "name": step_name,
            "qualified_name": step_name,
            "step_id": self._str_or_none(metadata.get("step_id")),
            "visit_count": metadata.get("visit_count"),
            "status": "most_recent",
            "updated_at": self._str_or_none(metadata.get("generated_at")),
            "display_name": step_name,
            "prompt_href": None,
            "stderr_href": None,
            "stdout_href": None,
        }

    def _current_provider_step_from_state(self, state: Mapping[str, object]) -> dict[str, object] | None:
        candidates: list[dict[str, object]] = []

        def visit(run_state: Mapping[str, object], frame_root: str | None = None) -> None:
            current = run_state.get("current_step")
            if isinstance(current, Mapping):
                step_type = self._str_or_none(current.get("type"))
                status = self._str_or_none(current.get("status"))
                name = self._str_or_none(current.get("name"))
                if step_type == "provider" and status in {None, "running", "in_progress"} and name:
                    candidates.append(
                        {
                            "available": True,
                            "name": name,
                            "qualified_name": name,
                            "step_id": self._str_or_none(current.get("step_id")),
                            "visit_count": current.get("visit_count"),
                            "status": "in_progress",
                            "updated_at": (
                                self._str_or_none(current.get("last_heartbeat_at"))
                                or self._str_or_none(current.get("started_at"))
                            ),
                            "display_name": self._display_name_with_context(
                                name,
                                self._frame_root_context_label(frame_root or ""),
                            ),
                            "prompt_href": None,
                            "stderr_href": None,
                            "stdout_href": None,
                        }
                    )
            frames = run_state.get("call_frames")
            if not isinstance(frames, Mapping):
                return
            for frame_id, frame in frames.items():
                if not isinstance(frame, Mapping):
                    continue
                nested_state = frame.get("state")
                if isinstance(nested_state, Mapping):
                    visit(nested_state, f"call_frames/{frame_id}")

        visit(state)
        return candidates[-1] if candidates else None

    def _live_agent_note_payload(
        self,
        row,
        resolver: FileReferenceResolver,
        state: Mapping[str, object],
        current_name: Optional[str],
        current_step_id: Optional[str],
        current_provider_step: Mapping[str, object] | None = None,
    ) -> dict[str, object]:
        try:
            metadata_ref = resolver.run_ref("summaries/live-current-step.json", label="live note metadata")
            note_ref = resolver.run_ref("summaries/live-current-step.md", label="live note")
            error_ref = resolver.run_ref("summaries/live-current-step.error.json", label="live note error")
        except UnsafePathError:
            return self._live_agent_note_unavailable(state, "Live note paths are unsafe.")
        metadata = None
        metadata_error_reason = None
        if metadata_ref.status == "ok":
            try:
                loaded_metadata = json.loads(metadata_ref.absolute_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                metadata_error_reason = "Live note metadata is unreadable."
            else:
                if isinstance(loaded_metadata, Mapping):
                    metadata = loaded_metadata
                else:
                    metadata_error_reason = "Live note metadata is invalid."

        error_payload = self._current_live_agent_note_error_payload(
            row,
            state,
            error_ref,
            metadata_ref,
            metadata,
            current_name,
            current_step_id,
            current_provider_step,
        )
        if error_payload is not None:
            return error_payload
        if metadata_ref.status != "ok" or note_ref.status != "ok":
            return self._live_agent_note_unavailable(
                state,
                "Live agent notes are enabled, but no note artifact is available yet.",
            )
        if metadata is None:
            return self._live_agent_note_unavailable(
                state,
                metadata_error_reason or "Live note metadata is unreadable.",
            )
        note_step_name = self._str_or_none(metadata.get("step_name"))
        note_step_id = self._str_or_none(metadata.get("step_id"))
        if not self._live_note_matches_current_context(
            metadata,
            current_name,
            current_step_id,
            current_provider_step,
        ):
            return self._live_agent_note_unavailable(state, "The latest live note belongs to a different step.")
        try:
            text = note_ref.absolute_path.read_text(encoding="utf-8")[:4000]
        except OSError:
            text = ""
        return {
            "available": True,
            "text": text,
            "step_name": note_step_name,
            "step_id": note_step_id,
            "visit_count": metadata.get("visit_count"),
            "provider": self._str_or_none(metadata.get("provider")),
            "generated_at": self._str_or_none(metadata.get("generated_at")),
            "summary_href": self._file_href(row, note_ref),
            "metadata_href": self._file_href(row, metadata_ref),
        }

    def _current_live_agent_note_error_payload(
        self,
        row,
        state: Mapping[str, object],
        error_ref,
        metadata_ref,
        note_metadata: Mapping[str, object] | None,
        current_name: Optional[str],
        current_step_id: Optional[str],
        current_provider_step: Mapping[str, object] | None,
    ) -> dict[str, object] | None:
        if error_ref.status != "ok":
            return None
        try:
            payload = json.loads(error_ref.absolute_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(payload, Mapping):
            return None
        if not self._live_note_matches_current_context(
            payload,
            current_name,
            current_step_id,
            current_provider_step,
        ):
            return None
        if self._live_note_error_superseded(
            error_payload=payload,
            error_ref=error_ref,
            note_metadata=note_metadata,
            metadata_ref=metadata_ref,
            current_name=current_name,
            current_step_id=current_step_id,
            current_provider_step=current_provider_step,
        ):
            return None
        stage = self._str_or_none(payload.get("stage"))
        step_name = self._str_or_none(payload.get("step_name"))
        error = payload.get("error")
        message = ""
        if isinstance(error, Mapping):
            message = (
                self._str_or_none(error.get("stderr"))
                or self._str_or_none(error.get("message"))
                or self._str_or_none(error.get("stdout"))
                or ""
            )
        elif error is not None:
            message = str(error)
        reason = "Live note provider failed"
        if step_name:
            reason += f" for {step_name}"
        if stage:
            reason += f" during {stage}"
        if message:
            reason += f": {message[:1000]}"
        return {
            "available": False,
            "reason": reason,
            "step_name": step_name,
            "step_id": self._str_or_none(payload.get("step_id")),
            "visit_count": payload.get("visit_count"),
            "provider": self._str_or_none(payload.get("provider")),
            "generated_at": self._str_or_none(payload.get("generated_at")),
            "stage": stage,
            "error_href": self._file_href(row, error_ref),
        }

    def _live_note_error_superseded(
        self,
        *,
        error_payload: Mapping[str, object],
        error_ref,
        note_metadata: Mapping[str, object] | None,
        metadata_ref,
        current_name: Optional[str],
        current_step_id: Optional[str],
        current_provider_step: Mapping[str, object] | None,
    ) -> bool:
        if note_metadata is None:
            return False
        if not self._live_note_matches_current_context(
            note_metadata,
            current_name,
            current_step_id,
            current_provider_step,
        ):
            return False
        note_time = self._parse_dashboard_datetime(self._str_or_none(note_metadata.get("generated_at")))
        error_time = self._parse_dashboard_datetime(self._str_or_none(error_payload.get("generated_at")))
        if note_time is not None and error_time is not None:
            return note_time >= error_time
        try:
            return metadata_ref.absolute_path.stat().st_mtime >= error_ref.absolute_path.stat().st_mtime
        except OSError:
            return False

    def _parse_dashboard_datetime(self, value: Optional[str]) -> Optional[datetime]:
        if not value:
            return None
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    def _live_note_matches_current_context(
        self,
        metadata: Mapping[str, object],
        current_name: Optional[str],
        current_step_id: Optional[str],
        current_provider_step: Mapping[str, object] | None = None,
    ) -> bool:
        note_step_name = self._str_or_none(metadata.get("step_name"))
        note_step_id = self._str_or_none(metadata.get("step_id"))
        provider_names: set[str] = set()
        if isinstance(current_provider_step, Mapping) and current_provider_step.get("available") is True:
            for key in ("name", "qualified_name"):
                value = self._str_or_none(current_provider_step.get(key))
                if value:
                    provider_names.add(value)

        matches_current_step = True
        if current_name and note_step_name and note_step_name != current_name:
            matches_current_step = False
        if current_step_id and note_step_id and note_step_id != current_step_id:
            matches_current_step = False

        matches_provider_step = bool(note_step_name and note_step_name in provider_names)
        return matches_current_step or matches_provider_step

    def _live_agent_note_unavailable(
        self,
        state: Mapping[str, object],
        enabled_reason: str,
    ) -> dict[str, object]:
        observability = state.get("observability")
        step_summaries = (
            observability.get("step_summaries")
            if isinstance(observability, Mapping)
            and isinstance(observability.get("step_summaries"), Mapping)
            else None
        )
        live_cfg = (
            step_summaries.get("live_agent_notes")
            if isinstance(step_summaries, Mapping)
            and isinstance(step_summaries.get("live_agent_notes"), Mapping)
            else None
        )
        if not isinstance(live_cfg, Mapping) or live_cfg.get("enabled") is not True:
            return {
                "available": False,
                "reason": "Live agent notes are not enabled for this run.",
            }
        return {
            "available": False,
            "reason": (
                f"{enabled_reason} Notes are generated only while a session provider "
                "step is streaming output."
            ),
            "provider": self._str_or_none(live_cfg.get("provider")),
        }

    def _summary_index_entries(self, run_root) -> list[Mapping[str, object]]:
        index_path = run_root / "summaries" / "index.json"
        try:
            payload = json.loads(index_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        entries = payload.get("entries") if isinstance(payload, Mapping) else None
        if not isinstance(entries, list):
            return []
        return [entry for entry in entries if isinstance(entry, Mapping)]

    def _summary_workflow_structure_html(
        self,
        detail,
        entries: list[Mapping[str, object]],
    ) -> str:
        row = detail.row
        workflow_file = self._str_or_none(
            detail.state.get("workflow_file") if isinstance(detail.state, Mapping) else None
        ) or row.workflow_file
        payload, unavailable_reason = self._read_workflow_yaml_for_structure(row, workflow_file)
        if payload is not None:
            workflow_name = self._str_or_none(payload.get("name")) or workflow_file or "workflow"
            steps = payload.get("steps")
            if isinstance(steps, list) and steps:
                nodes = [
                    self._workflow_step_node(detail, workflow_file, payload, step, entries)
                    for step in steps
                ]
            else:
                nodes = [{"label": "(no authored steps found)", "kind": "empty", "children": [], "links": []}]
            provider_flow = self._provider_flow_mermaid_html(nodes)
            return (
                "<section class=\"workflow-map\"><h2>Workflow Structure</h2>"
                f"<p class=\"workflow-source\">Authored workflow structure. Workflow: {self._e(workflow_name)}</p>"
                f"{provider_flow}"
                f"{self._render_workflow_nodes_html(row, nodes)}"
                "</section>"
            )

        note = "Observed summary sequence"
        if unavailable_reason:
            note = f"{note}. {unavailable_reason}"
        observed = self._observed_summary_step_nodes(entries)
        if not observed:
            observed = [{"label": "(no workflow file or summary entries available)", "kind": "empty", "children": [], "links": []}]
        return (
            "<section class=\"workflow-map\"><h2>Workflow Structure</h2>"
            f"<p class=\"workflow-source\">{self._e(note)}</p>"
            f"{self._provider_flow_mermaid_html(observed)}"
            f"{self._render_workflow_nodes_html(row, observed)}"
            "</section>"
        )

    def _provider_flow_mermaid_html(self, nodes: list[dict[str, object]]) -> str:
        builder = _ProviderFlowBuilder(self, nodes)
        first_ids, _last_ids = builder.walk_sequence(nodes)
        if not first_ids:
            return ""
        mermaid = builder.render()
        flow_strip = builder.render_strip_html()
        return (
            "<section class=\"provider-flow\">"
            "<h3>Provider Flow</h3>"
            "<p class=\"workflow-source\">Compact provider sequence. Deterministic routing details are in the tree below.</p>"
            f"{flow_strip}"
            "<details class=\"provider-flow-source\">"
            "<summary>Mermaid source</summary>"
            f"<pre class=\"mermaid provider-flow-mermaid\">{self._e(mermaid)}</pre>"
            "</details>"
            "</section>"
        )

    def _compact_provider_flow_items(
        self,
        nodes: list[dict[str, object]],
    ) -> list[dict[str, object]]:
        paths = [path for path in self._provider_flow_item_paths(nodes) if path]
        if not paths:
            return []
        return max(
            paths,
            key=lambda path: (
                len(path),
                sum(1 for item in path if item.get("kind") == "loop_group"),
            ),
        )

    def _provider_flow_item_paths(
        self,
        nodes: object,
    ) -> list[list[dict[str, object]]]:
        sequence = [node for node in nodes if isinstance(node, Mapping)] if isinstance(nodes, list) else []
        if not sequence:
            return [[]]
        if all(str(node.get("kind") or "") in {"case", "branch"} for node in sequence):
            branch_paths: list[list[dict[str, object]]] = []
            for node in sequence:
                branch_paths.extend(self._provider_flow_item_paths(node.get("children")))
            return branch_paths or [[]]

        paths: list[list[dict[str, object]]] = [[]]
        for node in sequence:
            node_paths = self._provider_flow_node_item_paths(node)
            if not node_paths:
                continue
            paths = [prefix + suffix for prefix in paths for suffix in node_paths]
        return paths

    def _provider_flow_node_item_paths(
        self,
        node: Mapping[str, object],
    ) -> list[list[dict[str, object]]]:
        label = str(node.get("label") or "")
        kind = str(node.get("kind") or "")
        children = node.get("children")
        if bool(node.get("provider")):
            return [[{"kind": "provider", "label": label}]]
        if kind.startswith("repeat_until"):
            loop_item = self._provider_flow_review_loop_item(node)
            if loop_item is not None:
                return [[loop_item]]
        if isinstance(children, list) and children:
            return self._provider_flow_item_paths(children)
        return []

    def _provider_flow_review_loop_item(
        self,
        node: Mapping[str, object],
    ) -> Optional[dict[str, object]]:
        label = str(node.get("label") or "")
        if "ReviewLoop" not in label:
            return None
        child_paths = [path for path in self._provider_flow_item_paths(node.get("children")) if path]
        if not child_paths:
            return None
        longest = max(child_paths, key=len)
        providers = [
            str(item.get("label"))
            for item in longest
            if isinstance(item, Mapping) and item.get("kind") == "provider" and item.get("label")
        ]
        if len(providers) < 2:
            return None
        return {
            "kind": "loop_group",
            "label": f"{label} {str(node.get('kind') or '').replace('repeat_until', 'loop')}",
            "providers": providers[:2],
        }

    def _provider_flow_mermaid(self, nodes: list[dict[str, object]]) -> str:
        builder = _ProviderFlowBuilder(self)
        first_ids, _last_ids = builder.walk_sequence(nodes)
        if not first_ids:
            return ""
        return builder.render()

    def _read_workflow_yaml_for_structure(
        self,
        row,
        workflow_file: Optional[str],
    ) -> tuple[Mapping[str, Any] | None, str]:
        if not workflow_file:
            return None, "authored workflow file is not recorded in state."
        resolver = FileReferenceResolver(row.workspace_root, row.run_root)
        try:
            workflow_path = Path(workflow_file)
            if workflow_path.is_absolute():
                resolved = workflow_path.resolve(strict=False)
                workspace_root = row.workspace_root.resolve(strict=False)
                resolved.relative_to(workspace_root)
            else:
                ref = resolver.workspace_ref(workflow_file)
                if ref.status != "ok":
                    return None, "authored workflow file is not readable."
                resolved = ref.absolute_path
        except (OSError, UnsafePathError, ValueError):
            return None, "authored workflow file is not safe to read."
        try:
            payload = yaml.safe_load(resolved.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError):
            return None, "authored workflow file could not be parsed."
        if not isinstance(payload, Mapping):
            return None, "authored workflow file is not a mapping."
        return payload, ""

    def _observed_summary_step_nodes(
        self,
        entries: list[Mapping[str, object]],
    ) -> list[dict[str, object]]:
        nodes: list[dict[str, object]] = []
        by_step: dict[str, dict[str, object]] = {}
        for entry in entries:
            step_name = self._str_or_none(entry.get("step_name"))
            if not step_name:
                continue
            node = by_step.get(step_name)
            if node is None:
                node = {
                    "label": step_name,
                    "kind": "observed",
                    "children": [],
                    "links": [],
                    "summaries": [],
                    "observed": True,
                    "provider": False,
                }
                by_step[step_name] = node
                nodes.append(node)
            if self._str_or_none(entry.get("kind")) == "provider":
                node["kind"] = "provider"
                node["provider"] = True
        return nodes

    def _workflow_step_node(
        self,
        detail,
        workflow_file: Optional[str],
        workflow_payload: Mapping[str, Any],
        step: object,
        summary_entries: list[Mapping[str, object]],
    ) -> dict[str, object]:
        if not isinstance(step, Mapping):
            return {"label": "(invalid step)", "kind": "invalid", "children": [], "links": [], "summaries": []}
        name = (
            self._str_or_none(step.get("name"))
            or self._str_or_none(step.get("id"))
            or "(unnamed step)"
        )
        children: list[dict[str, object]] = []
        repeat_until = step.get("repeat_until") if isinstance(step.get("repeat_until"), Mapping) else None
        match = step.get("match") if isinstance(step.get("match"), Mapping) else None
        if_block = step.get("if")
        kind = self._workflow_step_kind(step)

        if repeat_until is not None:
            children.extend(
                self._workflow_nodes_from_steps(
                    detail, workflow_file, workflow_payload, repeat_until.get("steps"), summary_entries
                )
            )
        if match is not None:
            cases = match.get("cases")
            if isinstance(cases, Mapping):
                for case_name, case_block in cases.items():
                    children.append(
                        {
                            "label": f"case {case_name}",
                            "kind": "case",
                            "children": self._workflow_nodes_from_block(
                                detail, workflow_file, workflow_payload, case_block, summary_entries
                            ),
                            "links": [],
                            "summaries": [],
                        }
                    )
        if if_block is not None:
            children.append(
                {
                    "label": "then",
                    "kind": "branch",
                    "children": self._workflow_nodes_from_block(
                        detail, workflow_file, workflow_payload, step.get("then"), summary_entries
                    ),
                    "links": [],
                    "summaries": [],
                }
            )
            children.append(
                {
                    "label": "else",
                    "kind": "branch",
                    "children": self._workflow_nodes_from_block(
                        detail, workflow_file, workflow_payload, step.get("else"), summary_entries
                    ),
                    "links": [],
                    "summaries": [],
                }
            )
        called_children = self._called_workflow_nodes(detail, workflow_file, workflow_payload, step, summary_entries)
        if called_children:
            children.extend(called_children)
        summaries = self._workflow_summary_links(detail.row, summary_entries, name, kind)
        invocations = self._workflow_summary_invocations(detail, workflow_file, step, name, summaries)
        links = [] if invocations else self._workflow_step_link_groups(detail, workflow_file, step, name)
        return {
            "label": name,
            "kind": kind,
            "children": children,
            "links": links,
            "summaries": summaries,
            "invocations": invocations,
            "provider": kind in {"provider", "adjudicated_provider"},
        }

    def _workflow_step_kind(self, step: Mapping[str, object]) -> str:
        repeat_until = step.get("repeat_until")
        if isinstance(repeat_until, Mapping):
            max_iterations = repeat_until.get("max_iterations")
            suffix = f" max={max_iterations}" if max_iterations is not None else ""
            return f"repeat_until{suffix}"
        if "match" in step:
            return "match"
        if "if" in step:
            return "if"
        call = self._str_or_none(step.get("call"))
        if call:
            return f"call {call}"
        if "adjudicated_provider" in step:
            return "adjudicated_provider"
        if "provider" in step:
            return "provider"
        if "command" in step:
            return "command"
        if "materialize_artifacts" in step:
            return "materialize_artifacts"
        if "select_variant_output" in step:
            return "select_variant_output"
        if "variant_output" in step:
            return "variant_output"
        if "assert" in step:
            return "assert"
        if "wait_for" in step:
            return "wait_for"
        return "step"

    def _workflow_nodes_from_block(
        self,
        detail,
        workflow_file: Optional[str],
        workflow_payload: Mapping[str, Any],
        block: object,
        summary_entries: list[Mapping[str, object]],
    ) -> list[dict[str, object]]:
        if isinstance(block, Mapping):
            return self._workflow_nodes_from_steps(detail, workflow_file, workflow_payload, block.get("steps"), summary_entries)
        return self._workflow_nodes_from_steps(detail, workflow_file, workflow_payload, block, summary_entries)

    def _workflow_nodes_from_steps(
        self,
        detail,
        workflow_file: Optional[str],
        workflow_payload: Mapping[str, Any],
        steps: object,
        summary_entries: list[Mapping[str, object]],
    ) -> list[dict[str, object]]:
        if not isinstance(steps, list):
            return []
        return [
            self._workflow_step_node(detail, workflow_file, workflow_payload, step, summary_entries)
            for step in steps
        ]

    def _called_workflow_nodes(
        self,
        detail,
        workflow_file: Optional[str],
        workflow_payload: Mapping[str, Any],
        step: Mapping[str, object],
        summary_entries: list[Mapping[str, object]],
    ) -> list[dict[str, object]]:
        call_alias = self._str_or_none(step.get("call"))
        if not call_alias:
            return []
        imports = workflow_payload.get("imports")
        if not isinstance(imports, Mapping):
            return []
        import_path = self._str_or_none(imports.get(call_alias))
        if not import_path:
            return []
        called_workflow_file = self._resolve_import_workflow_file(detail.row, workflow_file, import_path)
        if not called_workflow_file:
            return []
        called_payload, _reason = self._read_workflow_yaml_for_structure(detail.row, called_workflow_file)
        if called_payload is None:
            return []
        called_steps = called_payload.get("steps")
        if not isinstance(called_steps, list) or not called_steps:
            return []
        called_detail = self._called_workflow_detail(detail, called_workflow_file)
        return [
            self._workflow_step_node(called_detail, called_workflow_file, called_payload, called_step, summary_entries)
            for called_step in called_steps
        ]

    def _resolve_import_workflow_file(
        self,
        row,
        workflow_file: Optional[str],
        import_path: str,
    ) -> Optional[str]:
        if not workflow_file:
            return None
        try:
            workflow_path = Path(workflow_file)
            workspace_root = row.workspace_root.resolve(strict=False)
            if workflow_path.is_absolute():
                workflow_relative = workflow_path.resolve(strict=False).relative_to(workspace_root)
            else:
                workflow_relative = workflow_path
            candidate = (workspace_root / workflow_relative.parent / import_path).resolve(strict=False)
            candidate_relative = candidate.relative_to(workspace_root).as_posix()
            FileReferenceResolver(row.workspace_root, row.run_root).workspace_ref(candidate_relative)
            return candidate_relative
        except (OSError, UnsafePathError, ValueError):
            return None

    def _called_workflow_detail(self, detail, workflow_file: str):
        state = self._called_workflow_state(detail, workflow_file)
        if state is None:
            return detail
        return SimpleNamespace(
            row=detail.row,
            state=state,
            artifact_versions=self._project_artifact_versions_for_workflow_map(detail.row, state),
            artifact_consumes=dict(state.get("artifact_consumes") if isinstance(state.get("artifact_consumes"), Mapping) else {}),
            root_detail=getattr(detail, "root_detail", detail),
        )

    def _called_workflow_state(self, detail, workflow_file: str) -> Optional[Mapping[str, Any]]:
        state = detail.state if isinstance(detail.state, Mapping) else {}
        frames = state.get("call_frames")
        if not isinstance(frames, Mapping):
            return None
        candidates: list[Mapping[str, Any]] = []
        for frame in frames.values():
            if not isinstance(frame, Mapping):
                continue
            frame_state = frame.get("state")
            if not isinstance(frame_state, Mapping):
                continue
            if self._str_or_none(frame_state.get("workflow_file")) == workflow_file:
                candidates.append(frame_state)
        return candidates[-1] if candidates else None

    def _project_artifact_versions_for_workflow_map(
        self,
        row,
        state: Mapping[str, Any],
    ) -> dict[str, list[dict[str, Any]]]:
        versions = state.get("artifact_versions")
        if not isinstance(versions, Mapping):
            return {}
        resolver = FileReferenceResolver(row.workspace_root, row.run_root)
        projected: dict[str, list[dict[str, Any]]] = {}
        for artifact_name, entries in versions.items():
            if not isinstance(artifact_name, str) or not isinstance(entries, list):
                continue
            projected_entries: list[dict[str, Any]] = []
            for entry in entries:
                if not isinstance(entry, Mapping):
                    continue
                copy_entry = dict(entry)
                value = copy_entry.get("value")
                if isinstance(value, str):
                    try:
                        copy_entry["file_ref"] = resolver.from_any(value, label=artifact_name)
                    except UnsafePathError:
                        pass
                projected_entries.append(copy_entry)
            projected[artifact_name] = projected_entries
        return projected

    def _workflow_step_link_groups(
        self,
        detail,
        workflow_file: Optional[str],
        step: Mapping[str, object],
        step_name: str,
    ) -> list[dict[str, object]]:
        groups: list[dict[str, object]] = []
        prompt_links = self._workflow_prompt_links(detail.row, workflow_file, step)
        if prompt_links:
            groups.append({"title": "Prompts", "links": prompt_links})
        input_links = self._workflow_input_links(detail, step)
        if input_links:
            groups.append({"title": "Inputs", "links": input_links})
        output_links = self._workflow_output_links(detail, step, step_name)
        if output_links:
            groups.append({"title": "Outputs", "links": output_links})
        publish_links = self._workflow_published_links(detail, step)
        if publish_links:
            groups.append({"title": "Published", "links": publish_links})
        consume_links = self._workflow_consumed_links(detail, step, step_name)
        if consume_links:
            groups.append({"title": "Consumed", "links": consume_links})
        return groups

    def _workflow_input_links(
        self,
        detail,
        step: Mapping[str, object],
    ) -> list[dict[str, str]]:
        links: list[dict[str, str]] = []
        seen: set[tuple[str, str]] = set()
        resolver = FileReferenceResolver(detail.row.workspace_root, detail.row.run_root)

        def add_link(label: str, value: str, *, display_label: Optional[str] = None) -> None:
            value = self._substitute_bound_inputs(detail, value)
            try:
                file_ref = resolver.from_any(value, label=label)
            except UnsafePathError:
                return
            if file_ref.status != "ok":
                return
            key = (label, file_ref.route_path)
            if key in seen:
                return
            seen.add(key)
            links.append(
                {
                    "label": display_label or label,
                    "href": self._file_href(detail.row, file_ref),
                    "path": file_ref.route_path,
                }
            )

        depends_on = step.get("depends_on")
        if isinstance(depends_on, Mapping):
            required = depends_on.get("required")
            if isinstance(required, list):
                for index, value in enumerate(required, start=1):
                    if isinstance(value, str):
                        add_link(self._workflow_dependency_label(value, index), value)
        return links

    def _workflow_dependency_label(self, value: str, index: int) -> str:
        input_match = re.fullmatch(r"\$\{inputs\.([A-Za-z_][A-Za-z0-9_]*)\}", value.strip())
        if input_match is not None:
            return input_match.group(1)
        name = Path(value).name
        if name:
            return name
        return f"required {index}"

    def _workflow_output_links(
        self,
        detail,
        step: Mapping[str, object],
        step_name: str,
    ) -> list[dict[str, str]]:
        links: list[dict[str, str]] = []
        seen: set[tuple[str, str]] = set()
        resolver = FileReferenceResolver(detail.row.workspace_root, detail.row.run_root)

        def add_link(label: str, value: str, *, display_label: Optional[str] = None) -> None:
            value = self._substitute_bound_inputs(detail, value)
            try:
                file_ref = resolver.from_any(value, label=label)
            except UnsafePathError:
                return
            if file_ref.status != "ok":
                return
            key = (label, file_ref.route_path)
            if key in seen:
                return
            seen.add(key)
            links.append(
                {
                    "label": display_label or label,
                    "href": self._file_href(detail.row, file_ref),
                    "path": file_ref.route_path,
                }
            )

        output_bundle = step.get("output_bundle")
        if isinstance(output_bundle, Mapping):
            path = output_bundle.get("path")
            if isinstance(path, str):
                add_link("output_bundle", path)
                self._add_output_bundle_field_links(detail, output_bundle, path, add_link)
        expected_outputs = step.get("expected_outputs")
        if isinstance(expected_outputs, list):
            for output in expected_outputs:
                if not isinstance(output, Mapping):
                    continue
                name = self._str_or_none(output.get("name")) or "expected_output"
                path = output.get("path")
                if isinstance(path, str):
                    target = self._expected_output_target(detail, path)
                    if target:
                        add_link(f"{name} target", target, display_label=self._display_label_for_relpath_target(target))
                        add_link(name, path, display_label=f"{name} pointer")
                    else:
                        add_link(name, path)

        state = detail.state if isinstance(detail.state, Mapping) else {}
        steps = state.get("steps")
        step_state = self._step_state_for_workflow_step(steps, step_name) if isinstance(steps, Mapping) else None
        artifacts = step_state.get("artifacts") if isinstance(step_state, Mapping) else None
        if isinstance(artifacts, Mapping):
            for artifact_name, value in artifacts.items():
                if isinstance(artifact_name, str) and isinstance(value, str):
                    add_link(artifact_name, value, display_label=self._display_label_for_relpath_target(value))
        return links

    def _display_label_for_relpath_target(self, value: str) -> str:
        name = Path(value).name
        return name or value

    def _add_output_bundle_field_links(self, detail, output_bundle: Mapping[str, object], path: str, add_link) -> None:
        bundle_path = self._substitute_bound_inputs(detail, path)
        try:
            bundle_ref = FileReferenceResolver(detail.row.workspace_root, detail.row.run_root).from_any(
                bundle_path,
                label="output_bundle",
            )
        except UnsafePathError:
            return
        if bundle_ref.status != "ok":
            return
        try:
            bundle_payload = json.loads(bundle_ref.absolute_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        fields = output_bundle.get("fields")
        if not isinstance(fields, list):
            return
        for field in fields:
            if not isinstance(field, Mapping):
                continue
            field_type = self._str_or_none(field.get("type"))
            if field_type != "relpath":
                continue
            field_name = self._str_or_none(field.get("name")) or "bundle_field"
            pointer = field.get("json_pointer")
            value = self._json_pointer_value(
                bundle_payload,
                pointer if isinstance(pointer, str) else None,
            )
            if isinstance(value, str):
                add_link(field_name, value, display_label=self._display_label_for_relpath_target(value))

    def _expected_output_target(self, detail, path: str) -> Optional[str]:
        pointer_path = self._substitute_bound_inputs(detail, path)
        try:
            pointer_ref = FileReferenceResolver(detail.row.workspace_root, detail.row.run_root).from_any(
                pointer_path,
                label="expected_output",
            )
        except UnsafePathError:
            return None
        if pointer_ref.status != "ok":
            return None
        try:
            value = pointer_ref.absolute_path.read_text(encoding="utf-8").strip()
        except OSError:
            return None
        return value or None

    def _step_state_for_workflow_step(self, steps: Mapping[str, object], step_name: str) -> Optional[Mapping[str, object]]:
        direct = steps.get(step_name)
        if isinstance(direct, Mapping):
            return direct
        suffixes = (f".{step_name}", f"]{step_name}")
        for key, value in reversed(list(steps.items())):
            if isinstance(key, str) and key.endswith(suffixes) and isinstance(value, Mapping):
                return value
        return None

    def _substitute_bound_inputs(self, detail, value: str) -> str:
        state = detail.state if isinstance(detail.state, Mapping) else {}
        bound_inputs = state.get("bound_inputs")
        if not isinstance(bound_inputs, Mapping):
            return value

        def replace(match: re.Match[str]) -> str:
            key = match.group(1)
            replacement = bound_inputs.get(key)
            return str(replacement) if replacement is not None else match.group(0)

        return re.sub(r"\$\{inputs\.([A-Za-z_][A-Za-z0-9_]*)\}", replace, value)

    def _json_pointer_value(self, payload: object, pointer: Optional[str]) -> object:
        if pointer is None:
            return None
        if pointer == "":
            # Empty RFC 6901 pointer addresses the document root (root results).
            return payload
        if not pointer.startswith("/"):
            return None
        current = payload
        for raw_part in pointer.split("/")[1:]:
            part = raw_part.replace("~1", "/").replace("~0", "~")
            if isinstance(current, Mapping):
                current = current.get(part)
            elif isinstance(current, list):
                try:
                    current = current[int(part)]
                except (ValueError, IndexError):
                    return None
            else:
                return None
        return current

    def _workflow_prompt_links(
        self,
        row,
        workflow_file: Optional[str],
        step: Mapping[str, object],
    ) -> list[dict[str, str]]:
        links: list[dict[str, str]] = []
        for label, value in self._workflow_prompt_specs(step):
            if not value:
                continue
            file_ref = self._resolve_prompt_ref(row, workflow_file, label, value)
            if file_ref is not None and file_ref.status == "ok":
                links.append({"label": label, "href": self._file_href(row, file_ref), "path": file_ref.route_path})
        return links

    def _workflow_prompt_specs(self, step: Mapping[str, object]) -> list[tuple[str, str]]:
        specs: list[tuple[str, str]] = []
        for key in ("asset_file", "input_file", "rubric_asset_file", "rubric_input_file"):
            value = step.get(key)
            if isinstance(value, str):
                specs.append((key, value))
        asset_depends = step.get("asset_depends_on")
        if isinstance(asset_depends, list):
            for value in asset_depends:
                if isinstance(value, str):
                    specs.append(("asset_depends_on", value))
        adjudicated = step.get("adjudicated_provider")
        if isinstance(adjudicated, Mapping):
            candidates = adjudicated.get("candidates")
            if isinstance(candidates, list):
                for candidate in candidates:
                    if isinstance(candidate, Mapping):
                        candidate_id = self._str_or_none(candidate.get("id")) or "candidate"
                        for key in ("asset_file", "input_file"):
                            value = candidate.get(key)
                            if isinstance(value, str):
                                specs.append((f"{candidate_id}.{key}", value))
            evaluator = adjudicated.get("evaluator")
            if isinstance(evaluator, Mapping):
                for key in ("asset_file", "input_file", "rubric_asset_file", "rubric_input_file"):
                    value = evaluator.get(key)
                    if isinstance(value, str):
                        specs.append((f"evaluator.{key}", value))
        return specs

    def _resolve_prompt_ref(
        self,
        row,
        workflow_file: Optional[str],
        label: str,
        value: str,
    ):
        resolver = FileReferenceResolver(row.workspace_root, row.run_root)
        try:
            if "asset" in label:
                prompt_path = self._workflow_relative_asset_path(row, workflow_file, value)
                if prompt_path is None:
                    return None
                return resolver.workspace_ref(prompt_path, label=label)
            return resolver.workspace_ref(value, label=label)
        except (OSError, UnsafePathError, ValueError):
            return None

    def _workflow_relative_asset_path(
        self,
        row,
        workflow_file: Optional[str],
        asset_path: str,
    ) -> Optional[str]:
        if not workflow_file:
            return None
        workflow_path = Path(workflow_file)
        try:
            if workflow_path.is_absolute():
                relative_workflow = workflow_path.resolve(strict=False).relative_to(
                    row.workspace_root.resolve(strict=False)
                )
            else:
                relative_workflow = workflow_path
        except (OSError, ValueError):
            return None
        return (relative_workflow.parent / asset_path).as_posix()

    def _workflow_published_links(
        self,
        detail,
        step: Mapping[str, object],
    ) -> list[dict[str, str]]:
        links: list[dict[str, str]] = []
        publishes = step.get("publishes")
        if not isinstance(publishes, list):
            return links
        for item in publishes:
            if not isinstance(item, Mapping):
                continue
            artifact_name = self._str_or_none(item.get("artifact"))
            if not artifact_name:
                continue
            file_ref = self._artifact_file_ref(detail.artifact_versions, artifact_name, None)
            if file_ref is not None and file_ref.status == "ok":
                links.append(
                    {
                        "label": artifact_name,
                        "href": self._file_href(detail.row, file_ref),
                        "path": file_ref.route_path,
                    }
                )
        return links

    def _workflow_consumed_links(
        self,
        detail,
        step: Mapping[str, object],
        step_name: str,
    ) -> list[dict[str, str]]:
        links: list[dict[str, str]] = []
        consumes = step.get("consumes")
        if not isinstance(consumes, list):
            return links
        step_consumes = detail.artifact_consumes.get(step_name)
        if not isinstance(step_consumes, Mapping):
            step_consumes = {}
        for item in consumes:
            if not isinstance(item, Mapping):
                continue
            artifact_name = self._str_or_none(item.get("artifact"))
            if not artifact_name:
                continue
            version = step_consumes.get(artifact_name)
            file_ref = self._artifact_file_ref(detail.artifact_versions, artifact_name, version)
            if file_ref is not None and file_ref.status == "ok":
                links.append(
                    {
                        "label": artifact_name,
                        "href": self._file_href(detail.row, file_ref),
                        "path": file_ref.route_path,
                    }
                )
        return links

    def _workflow_summary_invocations(
        self,
        detail,
        workflow_file: Optional[str],
        step: Mapping[str, object],
        step_name: str,
        summaries: list[dict[str, object]],
    ) -> list[dict[str, object]]:
        grouped: dict[str, list[dict[str, object]]] = {}
        for summary in summaries:
            key = self._str_or_none(summary.get("invocation_key"))
            if not key:
                key = f"summary:{len(grouped)}"
            grouped.setdefault(key, []).append(summary)
        if len(grouped) <= 1:
            return []

        invocations: list[dict[str, object]] = []
        for index, group in enumerate(grouped.values(), start=1):
            first = group[0]
            invocation_detail = self._detail_for_summary_invocation(detail, first) or detail
            invocations.append(
                {
                    "label": f"Invocation {index}",
                    "context_label": self._str_or_none(first.get("context_label")) or "",
                    "summaries": group,
                    "links": self._workflow_step_link_groups(invocation_detail, workflow_file, step, step_name),
                }
            )
        return invocations

    def _detail_for_summary_invocation(self, detail, summary: Mapping[str, object]):
        frame_root = self._str_or_none(summary.get("frame_root"))
        frame_state = self._state_for_frame_root(detail, frame_root)
        if frame_state is None:
            return None
        return SimpleNamespace(
            row=detail.row,
            state=frame_state,
            artifact_versions=self._project_artifact_versions_for_workflow_map(detail.row, frame_state),
            artifact_consumes=dict(
                frame_state.get("artifact_consumes")
                if isinstance(frame_state.get("artifact_consumes"), Mapping)
                else {}
            ),
            root_detail=getattr(detail, "root_detail", detail),
        )

    def _state_for_frame_root(
        self,
        detail,
        frame_root: Optional[str],
    ) -> Optional[Mapping[str, Any]]:
        if not frame_root:
            return None
        root_detail = getattr(detail, "root_detail", detail)
        current = root_detail.state if isinstance(root_detail.state, Mapping) else {}
        for raw_frame in frame_root.split("call_frames/")[1:]:
            frame_id = raw_frame.split("/", 1)[0]
            if not frame_id:
                return None
            state_frame_id = frame_id.replace("__visit__", "::visit::")
            frames = current.get("call_frames")
            if not isinstance(frames, Mapping):
                return None
            frame = frames.get(state_frame_id)
            if not isinstance(frame, Mapping):
                return None
            frame_state = frame.get("state")
            if not isinstance(frame_state, Mapping):
                return None
            current = frame_state
        return current if current is not root_detail.state else None

    def _workflow_summary_links(
        self,
        row,
        entries: list[Mapping[str, object]],
        step_name: str,
        step_kind: str,
    ) -> list[dict[str, object]]:
        resolver = FileReferenceResolver(row.workspace_root, row.run_root)
        links: list[dict[str, object]] = []
        for entry in entries:
            entry_step = self._str_or_none(entry.get("step_name"))
            if not entry_step or not self._summary_entry_matches_step(entry_step, step_name):
                continue
            entry_kind = self._str_or_none(entry.get("kind")) or ""
            if entry_kind == "provider" and step_kind not in {"provider", "adjudicated_provider"}:
                continue
            payload = {
                "kind": entry_kind,
                "profile": self._str_or_none(entry.get("profile")) or "",
                "status": self._str_or_none(entry.get("status")) or "",
                "duration_ms": entry.get("duration_ms"),
                "context_label": self._summary_entry_context_label(entry),
                "frame_root": self._str_or_none(entry.get("frame_root")) or "",
                "step_id": self._str_or_none(entry.get("step_id")) or "",
                "invocation_key": self._summary_entry_invocation_key(entry),
                "links": [],
            }
            file_links: list[dict[str, str]] = []
            for key, label in (
                ("summary_path", "summary"),
                ("snapshot_path", "snapshot"),
                ("report_path", "report"),
                ("error_path", "error"),
            ):
                value = entry.get(key)
                if not isinstance(value, str) or not value:
                    continue
                try:
                    file_ref = resolver.run_ref(value)
                except UnsafePathError:
                    continue
                if file_ref.status == "ok":
                    file_links.append(
                        {
                            "label": label,
                            "href": self._file_href(row, file_ref),
                            "path": file_ref.route_path,
                        }
                    )
            payload["links"] = file_links
            links.append(payload)
        return links

    def _summary_entry_invocation_key(self, entry: Mapping[str, object]) -> str:
        frame_root = self._str_or_none(entry.get("frame_root"))
        if frame_root:
            return f"frame:{frame_root}"
        step_id = self._str_or_none(entry.get("step_id"))
        if step_id:
            return f"step:{step_id}"
        for key in ("summary_path", "snapshot_path", "error_path"):
            value = self._str_or_none(entry.get(key))
            if value:
                return f"path:{value}"
        return ""

    def _summary_entry_matches_step(self, entry_step: str, step_name: str) -> bool:
        if entry_step == step_name:
            return True
        return entry_step.endswith(f".{step_name}") or entry_step.endswith(f"]{step_name}")

    def _artifact_file_ref(
        self,
        artifact_versions: Mapping[str, object],
        artifact_name: str,
        version: object,
    ):
        entries = artifact_versions.get(artifact_name)
        if not isinstance(entries, list):
            return None
        selected = None
        for entry in entries:
            if not isinstance(entry, Mapping):
                continue
            if version is not None and entry.get("version") != version:
                continue
            selected = entry
        if selected is None:
            for entry in reversed(entries):
                if isinstance(entry, Mapping):
                    selected = entry
                    break
        if not isinstance(selected, Mapping):
            return None
        file_ref = selected.get("file_ref")
        if hasattr(file_ref, "status") and hasattr(file_ref, "route_path"):
            return file_ref
        return None

    def _render_workflow_nodes_html(self, row, nodes: list[dict[str, object]]) -> str:
        return f"<ol class=\"workflow-tree\">{''.join(self._render_workflow_node_html(row, node) for node in nodes)}</ol>"

    def _render_workflow_node_html(self, row, node: Mapping[str, object]) -> str:
        observed_class = " observed" if node.get("observed") else ""
        provider_class = " provider" if node.get("provider") else " deterministic"
        contains_provider = (
            not bool(node.get("provider"))
            and self._node_has_provider_descendant(node)
        )
        contains_provider_class = " contains-provider" if contains_provider else ""
        label = str(node.get("label") or "")
        kind = str(node.get("kind") or "step")
        summaries = node.get("summaries")
        summary_count = len(summaries) if isinstance(summaries, list) else 0
        invocations = node.get("invocations")
        invocation_count = len(invocations) if isinstance(invocations, list) else 0
        link_groups = node.get("links")
        if invocation_count and isinstance(invocations, list):
            link_count = sum(
                len(group.get("links", []))
                for invocation in invocations
                if isinstance(invocation, Mapping)
                for group in invocation.get("links", [])
                if isinstance(group, Mapping)
            )
        else:
            link_count = (
                sum(len(group.get("links", [])) for group in link_groups if isinstance(group, Mapping))
                if isinstance(link_groups, list)
                else 0
            )
        parts = [
            f"<li class=\"workflow-node{provider_class}{contains_provider_class}{observed_class}\">",
            "<details class=\"workflow-card\">",
            "<summary class=\"workflow-title\">",
            f"<span class=\"workflow-name\">{self._e(label)}</span>",
            f"<span class=\"workflow-kind\">{self._e(kind)}</span>",
        ]
        if contains_provider:
            parts.append('<span class="workflow-badge provider-inside">provider inside</span>')
        if summary_count:
            plural = "summaries" if summary_count != 1 else "summary"
            parts.append(f"<span class=\"workflow-badge\">{summary_count} {plural}</span>")
        if link_count:
            plural = "links" if link_count != 1 else "link"
            parts.append(f"<span class=\"workflow-badge\">{link_count} {plural}</span>")
        parts.extend([
            "</summary>",
            "<div class=\"workflow-details\">",
        ])
        if invocation_count and isinstance(invocations, list):
            parts.append("<div class=\"workflow-invocations\">")
            for invocation in invocations:
                if not isinstance(invocation, Mapping):
                    continue
                label_text = self._str_or_none(invocation.get("label")) or "Invocation"
                context_text = self._str_or_none(invocation.get("context_label")) or ""
                parts.append("<details class=\"workflow-invocation\">")
                parts.append("<summary>")
                parts.append(f"<span>{self._e(label_text)}</span>")
                if context_text:
                    parts.append(f" <span class=\"summary-context\">{self._e(context_text)}</span>")
                parts.append("</summary><div class=\"workflow-invocation-body\">")
                invocation_summaries = invocation.get("summaries")
                if isinstance(invocation_summaries, list) and invocation_summaries:
                    parts.append(self._render_workflow_summaries_html(invocation_summaries))
                invocation_links = invocation.get("links")
                if isinstance(invocation_links, list) and invocation_links:
                    parts.append(self._render_workflow_link_groups_html(invocation_links))
                parts.append("</div></details>")
            parts.append("</div>")
        elif summary_count and isinstance(summaries, list):
            parts.append(self._render_workflow_summaries_html(summaries))
        if not invocation_count and isinstance(link_groups, list) and link_groups:
            parts.append(self._render_workflow_link_groups_html(link_groups))
        if not summary_count and not link_count:
            parts.append("<p class=\"muted\">No linked summary, prompt, input, output, publish, or consume files for this step.</p>")
        parts.append("</div>")
        children = node.get("children")
        if isinstance(children, list) and children:
            parts.append(self._render_workflow_nodes_html(row, children))
        parts.append("</details></li>")
        return "".join(parts)

    def _render_workflow_summaries_html(self, summaries: list[object]) -> str:
        parts = ["<div class=\"workflow-link-group\"><strong>Step summary artifacts</strong>"]
        for summary in summaries:
            if not isinstance(summary, Mapping):
                continue
            duration = summary.get("duration_ms")
            duration_text = f" {duration} ms" if duration is not None else ""
            context_text = self._str_or_none(summary.get("context_label"))
            meta = " ".join(
                part
                for part in (
                    self._str_or_none(summary.get("kind")),
                    self._str_or_none(summary.get("status")),
                    context_text,
                )
                if part
            )
            parts.append(f"<p class=\"workflow-summary-meta\">{self._e(meta + duration_text)}</p>")
            summary_links = summary.get("links")
            if isinstance(summary_links, list):
                parts.extend(self._render_workflow_file_links(summary_links, default_label="summary"))
        parts.append("</div>")
        return "".join(parts)

    def _render_workflow_link_groups_html(self, link_groups: list[object]) -> str:
        parts = ["<div class=\"workflow-links\">"]
        for group in link_groups:
            if not isinstance(group, Mapping):
                continue
            links = group.get("links")
            if not isinstance(links, list) or not links:
                continue
            parts.append("<div class=\"workflow-link-group\">")
            parts.append(f"<strong>{self._e(group.get('title') or '')}</strong>")
            parts.extend(self._render_workflow_file_links(links, default_label="file"))
            parts.append("</div>")
        parts.append("</div>")
        return "".join(parts)

    def _render_workflow_file_links(
        self,
        links: list[object],
        *,
        default_label: str,
    ) -> list[str]:
        parts: list[str] = []
        for link in links:
            if not isinstance(link, Mapping):
                continue
            href = self._str_or_none(link.get("href"))
            if not href:
                continue
            label_text = self._str_or_none(link.get("label")) or default_label
            path_text = self._str_or_none(link.get("path")) or label_text
            parts.append(
                f"<a href=\"{self._e(href)}\" title=\"{self._e(path_text)}\">"
                f"{self._e(label_text)}</a>"
            )
        return parts

    def _node_has_provider_descendant(self, node: Mapping[str, object]) -> bool:
        children = node.get("children")
        if not isinstance(children, list):
            return False
        for child in children:
            if not isinstance(child, Mapping):
                continue
            if child.get("provider") or self._node_has_provider_descendant(child):
                return True
        return False

    def _summary_entry_payload(self, row, resolver: FileReferenceResolver, entry: Mapping[str, object]) -> dict[str, object]:
        context_label = self._summary_entry_context_label(entry)
        step_name = str(entry.get("step_name") or "")
        payload: dict[str, object] = {
            "step_name": step_name,
            "display_step_name": self._display_name_with_context(step_name, context_label),
            "context_label": context_label,
            "kind": str(entry.get("kind") or ""),
            "profile": str(entry.get("profile") or ""),
            "status": str(entry.get("status") or ""),
            "duration_ms": entry.get("duration_ms"),
            "frame_root": str(entry.get("frame_root") or ""),
        }
        for key, output_key in (
            ("summary_path", "summary_href"),
            ("snapshot_path", "snapshot_href"),
            ("report_path", "report_href"),
            ("error_path", "error_href"),
        ):
            value = entry.get(key)
            if not isinstance(value, str) or not value:
                payload[output_key] = None
                continue
            try:
                file_ref = resolver.run_ref(value)
            except UnsafePathError:
                payload[output_key] = None
                continue
            payload[output_key] = self._file_href(row, file_ref)
        return payload

    def _summary_entry_context_label(self, entry: Mapping[str, object]) -> str:
        explicit_iteration = entry.get("iteration")
        explicit_visit = entry.get("visit_count")
        if explicit_iteration is not None or explicit_visit is not None:
            frame_root = self._str_or_none(entry.get("frame_root")) or ""
            frame_label = self._frame_root_context_label(frame_root)
            step_label = self._step_identity_context_label(
                self._str_or_none(entry.get("step_id")),
                explicit_iteration,
                explicit_visit,
            )
            labels = [label for label in (frame_label, step_label) if label]
            if labels:
                return " / ".join(dict.fromkeys(labels))
            return self._context_label(explicit_iteration, explicit_visit)
        frame_root = self._str_or_none(entry.get("frame_root")) or ""
        for key in ("summary_path", "snapshot_path", "error_path"):
            value = self._str_or_none(entry.get(key))
            if value and not frame_root:
                frame_root = value
        frame_label = self._frame_root_context_label(frame_root)
        step_label = self._step_identity_context_label(self._str_or_none(entry.get("step_id")), None, None)
        labels = [label for label in (frame_label, step_label) if label]
        return " / ".join(dict.fromkeys(labels))

    def _step_identity_context_label(
        self,
        step_id: Optional[str],
        explicit_iteration: object,
        explicit_visit: object,
    ) -> str:
        iteration = explicit_iteration
        iteration_scope = None
        if step_id:
            iteration_match = re.search(r"(?:^|\.)(?:root\.)?([A-Za-z0-9_]+)#(\d+)", step_id)
            if iteration_match is not None:
                iteration = iteration_match.group(2)
                iteration_scope = iteration_match.group(1)
        visit = explicit_visit
        if iteration is not None and visit == 1:
            visit = None
        return self._context_label(iteration, visit, iteration_scope=iteration_scope)

    def _frame_root_context_label(self, value: str) -> str:
        if not value:
            return ""
        frame_labels: list[str] = []
        frames = value.split("call_frames/")
        for raw_frame in frames[1:]:
            frame_id = raw_frame.split("/", 1)[0]
            if not frame_id:
                continue
            label = self._call_frame_context_label(frame_id)
            if label:
                frame_labels.append(label)
        if frame_labels:
            return " / ".join(frame_labels)

        iteration_match = re.search(r"(?:^|[/.])(?:root\.)?([A-Za-z0-9_]+)#(\d+)", value)
        visit_match = re.search(r"(?:^|[/.])(?:root\.)?([A-Za-z0-9_]+)(?:__visit__|::visit::)(\d+)", value)
        iteration = iteration_match.group(2) if iteration_match else None
        iteration_scope = iteration_match.group(1) if iteration_match else None
        visit = visit_match.group(2) if visit_match else None
        return self._context_label(iteration, visit, iteration_scope=iteration_scope)

    def _call_frame_context_label(self, frame_id: str) -> str:
        iteration_match = re.search(r"(?:^|\.)(?:root\.)?([A-Za-z0-9_]+)#(\d+)", frame_id)
        visit_match = re.search(r"([A-Za-z0-9_]+)(?:__visit__|::visit::)(\d+)", frame_id)
        iteration = iteration_match.group(2) if iteration_match else None
        iteration_scope = iteration_match.group(1) if iteration_match else None
        visit = visit_match.group(2) if visit_match else None
        visit_scope = visit_match.group(1) if visit_match else None
        if iteration is not None:
            return self._context_label(iteration, visit, iteration_scope=iteration_scope)
        if visit is not None:
            return self._context_label(None, visit, visit_scope=visit_scope)
        return ""

    def _current_step_iteration(self, state: Mapping[str, object], current_name: Optional[str]) -> object:
        if not current_name:
            return None
        steps = state.get("steps")
        step_state = steps.get(current_name) if isinstance(steps, Mapping) else None
        if isinstance(step_state, Mapping):
            debug = step_state.get("debug")
            structured_repeat = (
                debug.get("structured_repeat_until")
                if isinstance(debug, Mapping)
                and isinstance(debug.get("structured_repeat_until"), Mapping)
                else None
            )
            if isinstance(structured_repeat, Mapping) and structured_repeat.get("current_iteration") is not None:
                return structured_repeat.get("current_iteration")
        repeat_until = state.get("repeat_until")
        repeat_state = repeat_until.get(current_name) if isinstance(repeat_until, Mapping) else None
        if isinstance(repeat_state, Mapping):
            return repeat_state.get("current_iteration")
        return None

    def _context_label(
        self,
        iteration: object,
        visit_count: object,
        *,
        iteration_scope: object = None,
        visit_scope: object = None,
    ) -> str:
        parts: list[str] = []
        if iteration is not None and iteration != "":
            scope = self._str_or_none(iteration_scope)
            prefix = f"{scope} " if scope else ""
            parts.append(f"{prefix}iteration {iteration}")
        if visit_count is not None and visit_count != "":
            scope = self._str_or_none(visit_scope)
            prefix = f"{scope} " if scope else ""
            parts.append(f"{prefix}visit {visit_count}")
        return " / ".join(parts)

    def _display_name_with_context(self, name: Optional[str], context_label: str) -> Optional[str]:
        if not name:
            return name
        if not context_label:
            return name
        return f"{name} ({context_label})"

    def _step_label_html(self, name: str, context_label: str) -> str:
        if not context_label:
            return self._e(name)
        return (
            f"{self._e(name)} "
            f"<span class=\"summary-context\">{self._e(context_label)}</span>"
        )

    def _summary_live_script(self, nonce: str) -> str:
        return (
            f"<script nonce=\"{self._e(nonce)}\">\n"
            "(() => {\n"
            "  const root = document.getElementById('live-current-step');\n"
            "  if (!root || !root.dataset.liveUrl) return;\n"
            "  const text = (name, value) => {\n"
            "    const el = root.querySelector(`[data-live-field=\"${name}\"]`);\n"
            "    if (el) el.textContent = value || '';\n"
            "  };\n"
            "  const refresh = async () => {\n"
            "    let data;\n"
            "    try {\n"
            "      const response = await fetch(root.dataset.liveUrl, {cache: 'no-store'});\n"
            "      if (!response.ok) return;\n"
            "      data = await response.json();\n"
            "    } catch (_error) { return; }\n"
            "    const run = data.run || {};\n"
            "    const step = data.current_step || {};\n"
            "    const providerStep = data.current_provider_step || {};\n"
            "    const summaries = data.summaries || {};\n"
            "    text('run-status', [run.display_status, run.display_status_reason].filter(Boolean).join(' '));\n"
            "    text('step-name', step.display_name || step.name || 'No current step');\n"
            "    const providerName = providerStep.display_name || providerStep.name || providerStep.qualified_name || 'provider';\n"
            "    const providerLabel = providerStep.available ? `${providerName} (${providerStep.status || 'active'})` : (providerStep.reason || 'No provider step yet');\n"
            "    text('provider-step', providerLabel);\n"
            "    const promptLink = root.querySelector('[data-live-link=\"provider-prompt\"]');\n"
            "    if (promptLink && providerStep.prompt_href) {\n"
            "      promptLink.href = providerStep.prompt_href;\n"
            "      promptLink.textContent = 'Prompt';\n"
            "      promptLink.hidden = false;\n"
            "    } else if (promptLink) {\n"
            "      promptLink.hidden = true;\n"
            "    }\n"
            "    const stderrLink = root.querySelector('[data-live-link=\"provider-stderr\"]');\n"
            "    if (stderrLink && (providerStep.stderr_href || providerStep.stdout_href)) {\n"
            "      stderrLink.href = providerStep.stderr_href || providerStep.stdout_href;\n"
            "      stderrLink.textContent = providerStep.stderr_href ? 'Log' : 'Output';\n"
            "      stderrLink.hidden = false;\n"
            "    } else if (stderrLink) {\n"
            "      stderrLink.hidden = true;\n"
            "    }\n"
            "    text('step-started', step.started_at || '');\n"
            "    text('step-age', step.age_text || '');\n"
            "    text('heartbeat', [step.heartbeat_at, step.heartbeat_age_text].filter(Boolean).join(' '));\n"
            "    const counts = summaries.counts || {};\n"
            "    const countText = Object.keys(counts).sort().map((key) => `${key}=${counts[key]}`).join(', ');\n"
            "    text('summary-counts', `${summaries.total || 0}${countText ? ` (${countText})` : ''}`);\n"
            "    const latest = summaries.current_step_latest || {};\n"
            "    const liveNote = data.live_note || {};\n"
            "    const link = root.querySelector('[data-live-link=\"latest-summary\"]');\n"
            "    const empty = root.querySelector('[data-live-field=\"latest-summary-empty\"]');\n"
            "    if (link && latest.summary_href) {\n"
            "      link.href = latest.summary_href;\n"
            "      link.textContent = [latest.kind, latest.status].filter(Boolean).join(' ') || 'Open summary';\n"
            "      link.hidden = false;\n"
            "      if (empty) empty.hidden = true;\n"
            "    } else {\n"
            "      if (link) link.hidden = true;\n"
            "      if (empty) empty.hidden = false;\n"
            "    }\n"
            "    text('live-note', liveNote.text || liveNote.reason || 'No live note yet.');\n"
            "    const liveLink = root.querySelector('[data-live-link=\"live-note\"]');\n"
            "    const liveHref = liveNote.summary_href || liveNote.error_href;\n"
            "    if (liveLink && liveHref) {\n"
            "      liveLink.href = liveHref;\n"
            "      const liveLabel = liveNote.summary_href ? 'Open live note' : 'Open live note error';\n"
            "      liveLink.textContent = liveNote.generated_at ? `${liveLabel} (${liveNote.generated_at})` : liveLabel;\n"
            "      liveLink.hidden = false;\n"
            "    } else if (liveLink) {\n"
            "      liveLink.hidden = true;\n"
            "    }\n"
            "  };\n"
            "  refresh();\n"
            "  setInterval(refresh, 3000);\n"
            "})();\n"
            "</script>"
        )

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
            f"<p>Visit count: {self._e(step.visit_count if step.visit_count is not None else '')}</p>",
            f"<p>Duration: {self._e(str(step.duration_ms) + ' ms' if step.duration_ms is not None else '')}</p>",
            "<h2>Output Preview</h2>",
            f"<pre>{self._e(step.output_preview)}</pre>",
            "<h2>Error</h2>",
            f"<pre>{self._json(step.error)}</pre>",
            "<h2>Outcome</h2>",
            f"<pre>{self._json(step.outcome)}</pre>",
            "<h2>Debug</h2>",
            f"<pre>{self._json(step.debug)}</pre>",
            "<h2>Provider Session</h2>",
            f"<pre>{self._json(step.provider_session)}</pre>",
            "<h2>Artifacts</h2>",
            f"<pre>{self._json(step.artifacts)}</pre>",
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

    def _run_summary_preview_link_mapper(
        self,
        row,
        resolver: FileReferenceResolver,
    ) -> Callable[[str], Optional[str]]:
        def map_href(href: str) -> Optional[str]:
            href_text = html.unescape(href).strip()
            if re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", href_text):
                return None
            if href_text.startswith("//"):
                return None
            if href_text.startswith("/"):
                return None
            route_path = posixpath.normpath(posixpath.join("summaries", href_text))
            if route_path == "." or route_path.startswith("../") or route_path == "..":
                return None
            try:
                file_ref = resolver.run_ref(route_path)
            except UnsafePathError:
                return None
            return self._file_href(row, file_ref)

        return map_href

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

    def _summary_entry_links(self, row, resolver: FileReferenceResolver, entry: Mapping[str, object]) -> str:
        links: list[str] = []
        for key, label in (
            ("summary_path", "summary"),
            ("snapshot_path", "snapshot"),
            ("report_path", "report"),
            ("error_path", "error"),
        ):
            value = entry.get(key)
            if not isinstance(value, str) or not value:
                continue
            try:
                file_ref = resolver.run_ref(value, label=label)
            except UnsafePathError:
                links.append(f"{self._e(label)}: <span class=\"muted\">unsafe path</span>")
                continue
            links.append(f"<a href=\"{self._file_href(row, file_ref)}\">{self._e(label)}</a>")
        return " ".join(links) if links else ""

    def _append_file_group(self, lines: list[str], row, title: str, refs) -> None:
        lines.append(f"<h3>{self._e(title)}</h3>")
        if not refs:
            lines.append("<p>None found.</p>")
            return
        lines.append("<ul>")
        for file_ref in refs:
            label = file_ref.label or file_ref.status
            lines.append(
                f"<li>{self._e(label)}: <a href=\"{self._file_href(row, file_ref)}\">"
                f"{self._e(file_ref.scope)}:{self._e(file_ref.route_path)}</a></li>"
            )
        lines.append("</ul>")

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
            if status_filter and status_filter not in {
                row.persisted_status,
                row.display_status,
            }:
                continue
            if workflow_filter:
                haystack = f"{row.workflow_name or ''} {row.workflow_file or ''}".lower()
                if workflow_filter.lower() not in haystack:
                    continue
            if search_filter:
                haystack = " ".join(
                    [
                        row.run_dir_id,
                        row.state_run_id or "",
                        row.workflow_file or "",
                        row.workflow_name or "",
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
        if isinstance(row.state_mtime, (int, float)):
            return float(row.state_mtime)
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

    def _json_response(self, payload: Mapping[str, object], *, status: int = 200) -> DashboardResponse:
        return DashboardResponse(
            status=status,
            body=(json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8"),
            headers={
                "Content-Type": "application/json; charset=utf-8",
                "X-Content-Type-Options": "nosniff",
                "Content-Security-Policy": DASHBOARD_CSP,
            },
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

    def _str_or_none(self, value: object) -> Optional[str]:
        return value if isinstance(value, str) else None

    def _e(self, value: object) -> str:
        return html.escape(str(value), quote=True)

    def _format_availability(self, availability: Mapping[str, bool]) -> str:
        if not availability:
            return ""
        return ", ".join(
            f"{key}={'yes' if value else 'no'}"
            for key, value in sorted(availability.items())
        )

    def _format_timestamp(self, value: object) -> str:
        if not isinstance(value, (int, float)):
            return ""
        try:
            return datetime.fromtimestamp(value, timezone.utc).isoformat()
        except (OSError, ValueError):
            return str(value)

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
