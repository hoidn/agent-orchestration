"""Artifact publish/consume bookkeeping helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Dict, Optional


class DataflowManager:
    """Maintain publish/consume lineage without owning executor control flow."""

    def __init__(
        self,
        *,
        workspace: Path,
        workflow: Dict[str, Any],
        uses_qualified_identities: Callable[[], bool],
        workflow_version_at_least: Callable[[str], bool],
        step_id_resolver: Callable[[Dict[str, Any]], str],
        contract_violation_result: Callable[[str, Dict[str, Any]], Dict[str, Any]],
        persist_state: Callable[[Dict[str, Any]], None],
        substitute_path_template: Callable[..., tuple[Optional[str], Optional[Dict[str, Any]]]],
        resolve_workspace_path: Callable[[str], Optional[Path]],
        current_step_index: Callable[[], int],
    ) -> None:
        self.workspace = workspace
        self.workflow = workflow
        self.uses_qualified_identities = uses_qualified_identities
        self.workflow_version_at_least = workflow_version_at_least
        self.step_id_resolver = step_id_resolver
        self.contract_violation_result = contract_violation_result
        self.persist_state = persist_state
        self.substitute_path_template = substitute_path_template
        self.resolve_workspace_path = resolve_workspace_path
        self.current_step_index = current_step_index

    def record_published_artifacts(
        self,
        step: Dict[str, Any],
        step_name: str,
        result: Dict[str, Any],
        state: Dict[str, Any],
        *,
        runtime_step_id: Optional[str] = None,
        additional_publishes: Optional[list[Dict[str, str]]] = None,
        persist: bool = True,
    ) -> Optional[Dict[str, Any]]:
        """Record artifact publications for successful steps."""
        publishes = step.get("publishes")
        if additional_publishes:
            base_publishes = publishes if isinstance(publishes, list) else []
            publishes = [*base_publishes, *additional_publishes]
        if not publishes:
            return None
        if result.get("exit_code", 0) != 0:
            return None
        if not isinstance(publishes, list):
            return self.contract_violation_result(
                "Publish contract invalid",
                {"step": step_name, "reason": "publishes_not_list"},
            )

        artifacts = result.get("artifacts")
        if not isinstance(artifacts, dict):
            return self.contract_violation_result(
                "Publish contract failed",
                {
                    "step": step_name,
                    "reason": "missing_result_artifacts",
                    "hint": "publishes requires expected_outputs artifacts persisted in step result",
                },
            )

        artifacts_registry = self.workflow.get("artifacts", {})
        if not isinstance(artifacts_registry, dict):
            artifacts_registry = {}

        artifact_versions = state.setdefault("artifact_versions", {})
        if not isinstance(artifact_versions, dict):
            artifact_versions = {}
            state["artifact_versions"] = artifact_versions

        producer_identity = runtime_step_id or result.get("step_id") or self.step_id_resolver(step)
        if not self.uses_qualified_identities():
            producer_identity = step_name

        for publish in publishes:
            if not isinstance(publish, dict):
                continue

            artifact_name = publish.get("artifact")
            output_name = publish.get("from")
            if not isinstance(artifact_name, str) or not isinstance(output_name, str):
                continue

            if output_name not in artifacts:
                return self.contract_violation_result(
                    "Publish contract failed",
                    {
                        "step": step_name,
                        "artifact": artifact_name,
                        "reason": "missing_artifact_output",
                        "from": output_name,
                    },
                )

            value = artifacts[output_name]
            artifact_spec = artifacts_registry.get(artifact_name, {})
            if isinstance(artifact_spec, dict) and artifact_spec.get("type") == "enum":
                allowed = artifact_spec.get("allowed")
                if (
                    not isinstance(value, str)
                    or not isinstance(allowed, list)
                    or value not in allowed
                ):
                    return self.contract_violation_result(
                        "Publish contract failed",
                        {
                            "step": step_name,
                            "artifact": artifact_name,
                            "reason": "invalid_enum_value",
                            "value": value,
                            "allowed": allowed if isinstance(allowed, list) else [],
                        },
                    )

            versions = artifact_versions.setdefault(artifact_name, [])
            if not isinstance(versions, list):
                versions = []
                artifact_versions[artifact_name] = versions

            max_version = 0
            for entry in versions:
                if isinstance(entry, dict):
                    entry_version = entry.get("version", 0)
                    if isinstance(entry_version, int) and entry_version > max_version:
                        max_version = entry_version

            entry = {
                "version": max_version + 1,
                "value": value,
                "producer": producer_identity,
                "producer_name": step_name,
                "step_index": self.current_step_index(),
            }
            debug_payload = result.get("debug")
            if isinstance(debug_payload, dict):
                call_debug = debug_payload.get("call")
                if isinstance(call_debug, dict):
                    export_sources = call_debug.get("exports")
                    if isinstance(export_sources, dict):
                        source = export_sources.get(output_name)
                        if isinstance(source, dict):
                            entry["source_provenance"] = source

            versions.append(entry)

        if persist:
            self.persist_state(state)
        return None

    def enforce_consumes_contract(
        self,
        step: Dict[str, Any],
        step_name: str,
        state: Dict[str, Any],
        *,
        runtime_step_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Resolve and enforce consumes contracts before step execution."""
        consumes = step.get("consumes")
        if not consumes:
            return None
        if not isinstance(consumes, list):
            return self.contract_violation_result(
                "Consume contract invalid",
                {"step": step_name, "reason": "consumes_not_list"},
            )

        artifacts_registry = self.workflow.get("artifacts", {})
        if not isinstance(artifacts_registry, dict):
            artifacts_registry = {}

        artifact_versions = state.setdefault("artifact_versions", {})
        if not isinstance(artifact_versions, dict):
            artifact_versions = {}
            state["artifact_versions"] = artifact_versions

        artifact_consumes = state.setdefault("artifact_consumes", {})
        if not isinstance(artifact_consumes, dict):
            artifact_consumes = {}
            state["artifact_consumes"] = artifact_consumes
        resolved_consumes = state.setdefault("_resolved_consumes", {})
        if not isinstance(resolved_consumes, dict):
            resolved_consumes = {}
            state["_resolved_consumes"] = resolved_consumes

        consumer_identity = runtime_step_id or self.step_id_resolver(step)
        if not self.uses_qualified_identities():
            consumer_identity = step_name

        step_consumes = artifact_consumes.setdefault(consumer_identity, {})
        if not isinstance(step_consumes, dict):
            step_consumes = {}
            artifact_consumes[consumer_identity] = step_consumes
        global_consumes = artifact_consumes.setdefault("__global__", {})
        if not isinstance(global_consumes, dict):
            global_consumes = {}
            artifact_consumes["__global__"] = global_consumes
        step_resolved_consumes: Dict[str, Any] = {}
        resolved_consumes[consumer_identity] = step_resolved_consumes
        workflow_version = self.workflow.get("version")
        materialize_relpath_consume_pointer = workflow_version in {"1.2", "1.3"}
        freshness_uses_step_scope = self.workflow_version_at_least("1.4")

        for consume in consumes:
            if not isinstance(consume, dict):
                continue

            artifact_name = consume.get("artifact")
            if not isinstance(artifact_name, str):
                continue

            candidates = artifact_versions.get(artifact_name, [])
            if not isinstance(candidates, list):
                candidates = []

            producers = consume.get("producers", [])
            if isinstance(producers, list) and producers:
                producer_set = {p for p in producers if isinstance(p, str)}
                candidates = [
                    c for c in candidates
                    if isinstance(c, dict) and (
                        c.get("producer") in producer_set or c.get("producer_name") in producer_set
                    )
                ]
            else:
                candidates = [c for c in candidates if isinstance(c, dict)]

            if not candidates:
                return self.contract_violation_result(
                    "Consume contract failed",
                    {
                        "step": step_name,
                        "artifact": artifact_name,
                        "reason": "no_published_versions",
                    },
                )

            selected = max(
                candidates,
                key=lambda entry: entry.get("version", 0) if isinstance(entry.get("version"), int) else 0,
            )
            selected_version = selected.get("version", 0)
            if not isinstance(selected_version, int):
                return self.contract_violation_result(
                    "Consume contract failed",
                    {
                        "step": step_name,
                        "artifact": artifact_name,
                        "reason": "invalid_selected_version",
                    },
                )

            freshness = consume.get("freshness", "any")
            if freshness_uses_step_scope:
                last_consumed = step_consumes.get(artifact_name, 0)
            else:
                last_consumed = global_consumes.get(artifact_name, 0)
            if not isinstance(last_consumed, int):
                last_consumed = 0

            if freshness == "since_last_consume" and selected_version <= last_consumed:
                return self.contract_violation_result(
                    "Consume contract failed",
                    {
                        "step": step_name,
                        "artifact": artifact_name,
                        "reason": "stale_artifact",
                        "selected_version": selected_version,
                        "last_consumed_version": last_consumed,
                    },
                )

            artifact_spec = artifacts_registry.get(artifact_name, {})
            artifact_kind = "relpath"
            artifact_type = None
            if isinstance(artifact_spec, dict):
                kind_value = artifact_spec.get("kind")
                if isinstance(kind_value, str) and kind_value:
                    artifact_kind = kind_value
                type_value = artifact_spec.get("type")
                if isinstance(type_value, str):
                    artifact_type = type_value
            selected_value = selected.get("value")
            if artifact_kind == "relpath":
                pointer = artifact_spec.get("pointer") if isinstance(artifact_spec, dict) else None
                if not isinstance(pointer, str) or not pointer:
                    return self.contract_violation_result(
                        "Consume contract failed",
                        {
                            "step": step_name,
                            "artifact": artifact_name,
                            "reason": "missing_registry_pointer",
                        },
                    )
                if not isinstance(selected_value, str):
                    return self.contract_violation_result(
                        "Consume contract failed",
                        {
                            "step": step_name,
                            "artifact": artifact_name,
                            "reason": "invalid_selected_value",
                        },
                    )
                if materialize_relpath_consume_pointer:
                    pointer_path = self.workspace / pointer
                    pointer_path.parent.mkdir(parents=True, exist_ok=True)
                    pointer_path.write_text(f"{selected_value}\n")
            elif artifact_kind == "scalar":
                valid_scalar_value = False
                if artifact_type == "integer":
                    valid_scalar_value = type(selected_value) is int
                elif artifact_type == "float":
                    valid_scalar_value = (
                        isinstance(selected_value, float)
                        or type(selected_value) is int
                    )
                elif artifact_type == "bool":
                    valid_scalar_value = isinstance(selected_value, bool)
                elif artifact_type == "enum":
                    allowed = artifact_spec.get("allowed") if isinstance(artifact_spec, dict) else None
                    valid_scalar_value = (
                        isinstance(selected_value, str)
                        and isinstance(allowed, list)
                        and selected_value in allowed
                    )
                elif artifact_type == "string":
                    valid_scalar_value = isinstance(selected_value, str)
                else:
                    valid_scalar_value = isinstance(selected_value, (int, float, bool, str))

                if not valid_scalar_value:
                    return self.contract_violation_result(
                        "Consume contract failed",
                        {
                            "step": step_name,
                            "artifact": artifact_name,
                            "reason": "invalid_selected_value",
                            "artifact_kind": artifact_kind,
                            "artifact_type": artifact_type,
                        },
                    )
            else:
                return self.contract_violation_result(
                    "Consume contract failed",
                    {
                        "step": step_name,
                        "artifact": artifact_name,
                        "reason": "unsupported_artifact_kind",
                        "artifact_kind": artifact_kind,
                    },
                )

            step_consumes[artifact_name] = selected_version
            global_consumes[artifact_name] = selected_version
            step_resolved_consumes[artifact_name] = selected_value

        consume_bundle = step.get("consume_bundle")
        if consume_bundle:
            reserved_artifact = None
            provider_session = step.get("provider_session")
            if isinstance(provider_session, dict) and provider_session.get("mode") == "resume":
                session_id_from = provider_session.get("session_id_from")
                if isinstance(session_id_from, str) and session_id_from:
                    reserved_artifact = session_id_from
            write_error = self.write_consume_bundle(
                consume_bundle=consume_bundle,
                step_name=step_name,
                state=state,
                resolved_values=step_resolved_consumes,
                reserved_artifact=reserved_artifact,
            )
            if write_error is not None:
                return write_error

        self.persist_state(state)
        return None

    def write_consume_bundle(
        self,
        *,
        consume_bundle: Any,
        step_name: str,
        state: Dict[str, Any],
        resolved_values: Dict[str, Any],
        reserved_artifact: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Materialize resolved consumes into a deterministic JSON bundle file."""
        if not isinstance(consume_bundle, dict):
            return self.contract_violation_result(
                "Consume contract failed",
                {
                    "step": step_name,
                    "reason": "invalid_consume_bundle",
                },
            )

        bundle_path_raw = consume_bundle.get("path")
        if not isinstance(bundle_path_raw, str) or not bundle_path_raw:
            return self.contract_violation_result(
                "Consume contract failed",
                {
                    "step": step_name,
                    "reason": "invalid_consume_bundle_path",
                },
            )

        bundle_path_raw, path_error = self.substitute_path_template(
            bundle_path_raw,
            state,
            step_name=step_name,
            field_name="consume_bundle.path",
        )
        if path_error is not None:
            return path_error
        assert bundle_path_raw is not None

        bundle_path = self.resolve_workspace_path(bundle_path_raw)
        if bundle_path is None:
            return self.contract_violation_result(
                "Consume contract failed",
                {
                    "step": step_name,
                    "reason": "consume_bundle_path_escape",
                    "path": bundle_path_raw,
                },
            )

        include = consume_bundle.get("include")
        selected_values: Dict[str, Any]
        if include is None:
            selected_values = {
                artifact_name: value
                for artifact_name, value in resolved_values.items()
                if artifact_name != reserved_artifact
            }
        elif isinstance(include, list):
            selected_values = {}
            for artifact_name in include:
                if not isinstance(artifact_name, str):
                    return self.contract_violation_result(
                        "Consume contract failed",
                        {
                            "step": step_name,
                            "reason": "invalid_consume_bundle_include",
                        },
                    )
                if reserved_artifact is not None and artifact_name == reserved_artifact:
                    return self.contract_violation_result(
                        "Consume contract failed",
                        {
                            "step": step_name,
                            "reason": "consume_bundle_include_reserved_artifact",
                            "artifact": artifact_name,
                        },
                    )
                if artifact_name not in resolved_values:
                    return self.contract_violation_result(
                        "Consume contract failed",
                        {
                            "step": step_name,
                            "reason": "consume_bundle_include_missing_artifact",
                            "artifact": artifact_name,
                        },
                    )
                selected_values[artifact_name] = resolved_values[artifact_name]
        else:
            return self.contract_violation_result(
                "Consume contract failed",
                {
                    "step": step_name,
                    "reason": "invalid_consume_bundle_include",
                },
            )

        try:
            bundle_path.parent.mkdir(parents=True, exist_ok=True)
            bundle_path.write_text(
                json.dumps(selected_values, sort_keys=True, ensure_ascii=True) + "\n",
                encoding="utf-8",
            )
        except OSError as exc:
            return self.contract_violation_result(
                "Consume contract failed",
                {
                    "step": step_name,
                    "reason": "consume_bundle_write_failed",
                    "path": bundle_path_raw,
                    "error": str(exc),
                },
            )

        return None
