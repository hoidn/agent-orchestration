"""Compiled-frontend provenance indexing and source-aware display.

This module owns persisted compiled-frontend source-trace parsing, lookup caches,
and rendering of provenance-backed step context.  It is a leaf relative to the
workflow executor: callers provide provenance and display settings explicitly,
and this module never imports or reads executor or execution state.
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, Mapping


# Preserve the established observability logger while moving its implementation.
logger = logging.getLogger("orchestrator.workflow.executor")
_DEFAULT_PROVENANCE = object()


class CompiledFrontendIndex:
    """Index one workflow bundle's persisted compiled-frontend provenance."""

    def __init__(self, provenance: Any) -> None:
        self._provenance = provenance
        self.frontend_kind = (
            provenance.frontend_kind if provenance is not None else None
        )
        self._source_trace_payload_cache: Dict[str, Mapping[str, Any]] = {}
        self.node_origins = self._load_node_origins()
        self.step_origins = self._load_step_origins()
        self.command_boundaries = self._load_command_boundaries()

    def _load_source_trace_payload(
        self,
        provenance: Any = _DEFAULT_PROVENANCE,
    ) -> Mapping[str, Any]:
        """Load the persisted compiled-frontend source-trace payload once."""
        selected_provenance = (
            self._provenance
            if provenance is _DEFAULT_PROVENANCE
            else provenance
        )
        source_trace_path = (
            selected_provenance.frontend_source_trace_path
            if selected_provenance is not None
            else None
        )
        if not isinstance(source_trace_path, Path) or not source_trace_path.exists():
            return {}
        cache_key = str(source_trace_path.resolve())
        if cache_key in self._source_trace_payload_cache:
            return self._source_trace_payload_cache[cache_key]
        try:
            payload = json.loads(source_trace_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.debug(
                "Failed to read compiled frontend source trace %s: %s",
                source_trace_path,
                exc,
            )
            return {}
        normalized = payload if isinstance(payload, Mapping) else {}
        self._source_trace_payload_cache[cache_key] = normalized
        return normalized

    def _load_step_origins(
        self,
        provenance: Any = _DEFAULT_PROVENANCE,
    ) -> Dict[str, Mapping[str, Any]]:
        """Load persisted frontend source-trace entries keyed by step identity."""
        payload = self._load_source_trace_payload(provenance)

        indexed: Dict[str, Mapping[str, Any]] = {}
        workflows = payload.get("workflows")
        if not isinstance(workflows, Mapping):
            return indexed
        for workflow_payload in workflows.values():
            if not isinstance(workflow_payload, Mapping):
                continue
            step_ids = workflow_payload.get("step_ids")
            if not isinstance(step_ids, Mapping):
                continue
            for key, origin in step_ids.items():
                if isinstance(key, str) and isinstance(origin, Mapping):
                    indexed.setdefault(key, origin)
        return indexed

    def _load_node_origins(
        self,
        provenance: Any = _DEFAULT_PROVENANCE,
    ) -> Dict[str, Mapping[str, Any]]:
        """Load persisted frontend source-trace entries keyed by node id."""
        payload = self._load_source_trace_payload(provenance)

        indexed: Dict[str, Mapping[str, Any]] = {}
        workflows = payload.get("workflows")
        if not isinstance(workflows, Mapping):
            return indexed
        for workflow_payload in workflows.values():
            if not isinstance(workflow_payload, Mapping):
                continue
            origins_by_key: Dict[str, Mapping[str, Any]] = {}
            for section in (
                "step_ids",
                "generated_inputs",
                "generated_outputs",
                "generated_paths",
                "generated_internal_inputs",
            ):
                entries = workflow_payload.get(section)
                if not isinstance(entries, Mapping):
                    continue
                for origin in entries.values():
                    if not isinstance(origin, Mapping):
                        continue
                    origin_key = origin.get("origin_key")
                    if isinstance(origin_key, str) and origin_key:
                        origins_by_key.setdefault(origin_key, origin)
            workflow_origin = workflow_payload.get("workflow_origin")
            if isinstance(workflow_origin, Mapping):
                origin_key = workflow_origin.get("origin_key")
                if isinstance(origin_key, str) and origin_key:
                    origins_by_key.setdefault(origin_key, workflow_origin)
            for node in workflow_payload.get("executable_nodes", ()):
                if not isinstance(node, Mapping):
                    continue
                node_id = node.get("node_id")
                origin_key = node.get("origin_key")
                if not isinstance(node_id, str) or not isinstance(origin_key, str):
                    continue
                origin = origins_by_key.get(origin_key)
                if origin is not None:
                    indexed.setdefault(node_id, origin)
        return indexed

    def _load_command_boundaries(
        self,
        provenance: Any = _DEFAULT_PROVENANCE,
    ) -> Dict[str, Mapping[str, Any]]:
        """Load persisted command-boundary lineage keyed by step id."""
        payload = self._load_source_trace_payload(provenance)

        indexed: Dict[str, Mapping[str, Any]] = {}
        workflows = payload.get("workflows")
        if not isinstance(workflows, Mapping):
            return indexed
        for workflow_payload in workflows.values():
            if not isinstance(workflow_payload, Mapping):
                continue
            for boundary in workflow_payload.get("command_boundaries", ()):
                if not isinstance(boundary, Mapping):
                    continue
                step_id = boundary.get("step_id")
                if isinstance(step_id, str) and step_id:
                    indexed.setdefault(step_id, boundary)
        return indexed

    def origin_for_step(
        self,
        step_name: str,
        step_id: str,
        *,
        node_id: str | None = None,
    ) -> Mapping[str, Any] | None:
        """Resolve one runtime step back to compiled frontend source metadata."""
        if isinstance(node_id, str) and node_id:
            origin = self.node_origins.get(node_id)
            if origin is not None:
                return origin
        candidate_keys = [step_name, step_id]
        if step_id.startswith("root."):
            candidate_keys.append(step_id[len("root."):])
        for candidate in candidate_keys:
            if not isinstance(candidate, str) or not candidate:
                continue
            origin = self.step_origins.get(candidate)
            if origin is not None:
                return origin
        return None

    def command_boundary_for_step(
        self,
        step_name: str,
        step_id: str,
        *,
        node_id: str | None = None,
    ) -> Mapping[str, Any] | None:
        """Resolve persisted command-boundary lineage for one runtime step."""
        for candidate in (step_id, step_name):
            if not isinstance(candidate, str) or not candidate:
                continue
            boundary = self.command_boundaries.get(candidate)
            if boundary is not None:
                return boundary
        return None

    def emit_step_display(
        self,
        step_name: str,
        step_id: str,
        *,
        node_id: str | None,
        stream_output: bool,
        debug: bool,
    ) -> None:
        """Emit provenance-backed observability lines for one runtime step."""
        self._emit_step_display_with_boundary(
            step_name,
            step_id,
            node_id=node_id,
            boundary=self.command_boundary_for_step(
                step_name,
                step_id,
                node_id=node_id,
            ),
            stream_output=stream_output,
            debug=debug,
        )

    def _emit_step_display_with_boundary(
        self,
        step_name: str,
        step_id: str,
        *,
        node_id: str | None,
        boundary: Mapping[str, Any] | None,
        stream_output: bool,
        debug: bool,
    ) -> None:
        """Render display metadata after the caller resolves any fallback."""
        # These settings are explicit so this index never reaches into an executor.
        # Current behavior logs this context independently of either setting.
        _ = stream_output, debug
        if self.frontend_kind != "workflow_lisp":
            return
        logger.info("Running step %s", step_name)
        origin = self.origin_for_step(step_name, step_id, node_id=node_id)
        if not isinstance(origin, Mapping):
            return
        path = origin.get("path")
        line = origin.get("line")
        column = origin.get("column")
        if isinstance(path, str) and isinstance(line, int):
            if isinstance(column, int):
                logger.info("  source: %s:%s:%s", path, line, column)
            else:
                logger.info("  source: %s:%s", path, line)
        form_path = origin.get("form_path")
        if isinstance(form_path, list) and form_path:
            logger.info("  form: %s", " > ".join(str(part) for part in form_path))
        if not isinstance(boundary, Mapping):
            return
        if boundary.get("boundary_kind") == "certified_adapter":
            adapter_name = boundary.get("adapter_name")
            if isinstance(adapter_name, str) and adapter_name:
                logger.info("  certified adapter: %s", adapter_name)
            source_map_behavior = boundary.get("source_map_behavior")
            if isinstance(source_map_behavior, str) and source_map_behavior:
                logger.info("  source-map behavior: %s", source_map_behavior)
