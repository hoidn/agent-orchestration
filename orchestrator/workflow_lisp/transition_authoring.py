"""Checked transition-authoring evidence for the Design Delta parent family."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any


TRANSITION_AUTHORING_SCHEMA_VERSION = "workflow_lisp_transition_authoring.v1"
TRANSITION_AUTHORING_REPORT_SCHEMA_VERSION = (
    "workflow_lisp_transition_authoring_report.v1"
)
ALLOWED_CLASSIFICATIONS = frozenset(
    {
        "low_level_library",
        "fixture",
        "compatibility_bridge",
        "ordinary_body_violation",
    }
)
HIGH_LEVEL_TRANSITION_MODULES = frozenset(
    {
        "lisp_frontend_design_delta/drain",
        "lisp_frontend_design_delta/work_item",
    }
)
INLINE_HELPER_TRANSITION_MARKER = "__lisp_frontend_design_delta_transitions_"


def load_transition_authoring_manifest(path: Path) -> dict[str, Any]:
    """Load and fail-closed validate the checked transition-authoring manifest."""

    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError(
            "transition_authoring_manifest_schema_invalid: manifest must be a JSON object"
        )
    if payload.get("schema_version") != TRANSITION_AUTHORING_SCHEMA_VERSION:
        raise ValueError(
            "transition_authoring_manifest_schema_invalid: expected schema_version "
            f"{TRANSITION_AUTHORING_SCHEMA_VERSION}"
        )
    workflow_family = payload.get("workflow_family")
    if not isinstance(workflow_family, str) or not workflow_family:
        raise ValueError(
            "transition_authoring_manifest_schema_invalid: workflow_family must be a non-empty string"
        )

    raw_allowed_origins = payload.get("allowed_origins")
    if not isinstance(raw_allowed_origins, list) or not raw_allowed_origins:
        raise ValueError(
            "transition_authoring_manifest_schema_invalid: allowed_origins must be a non-empty list"
        )
    seen_row_ids: set[str] = set()
    normalized_allowed_origins: list[dict[str, Any]] = []
    for index, raw_row in enumerate(raw_allowed_origins):
        if not isinstance(raw_row, Mapping):
            raise ValueError(
                "transition_authoring_manifest_schema_invalid: "
                f"allowed_origins[{index}] must be an object"
            )
        row_id = _require_string(raw_row, "row_id")
        if row_id in seen_row_ids:
            raise ValueError(
                "transition_authoring_manifest_schema_invalid: "
                f"duplicate row_id `{row_id}`"
            )
        seen_row_ids.add(row_id)
        classification = _require_string(raw_row, "classification")
        if classification not in ALLOWED_CLASSIFICATIONS:
            raise ValueError(
                "transition_authoring_manifest_schema_invalid: "
                f"row `{row_id}` uses unknown classification `{classification}`"
            )
        workflow_name = _optional_string(raw_row, "workflow_name")
        module_name = _optional_string(raw_row, "module_name")
        step_kind = _optional_string(raw_row, "step_kind")
        step_id_contains = _optional_string(raw_row, "step_id_contains")
        if _targets_high_level_module(
            workflow_name=workflow_name,
            module_name=module_name,
        ):
            raise ValueError(
                "transition_authoring_manifest_schema_invalid: "
                f"row `{row_id}` targets high-level modules; high-level modules may not appear in allowed_origins"
            )
        if workflow_name is None and module_name is None and step_id_contains is None:
            raise ValueError(
                "transition_authoring_manifest_schema_invalid: "
                f"row `{row_id}` must constrain at least one stable field"
            )
        normalized_allowed_origins.append(
            {
                "row_id": row_id,
                "classification": classification,
                "workflow_name": workflow_name,
                "module_name": module_name,
                "step_kind": step_kind,
                "step_id_contains": step_id_contains,
            }
        )

    raw_assertions = payload.get("source_shape_assertions")
    if not isinstance(raw_assertions, list) or not raw_assertions:
        raise ValueError(
            "transition_authoring_manifest_schema_invalid: source_shape_assertions must be a non-empty list"
        )
    seen_modules: set[str] = set()
    normalized_assertions: list[dict[str, Any]] = []
    for index, raw_assertion in enumerate(raw_assertions):
        if not isinstance(raw_assertion, Mapping):
            raise ValueError(
                "transition_authoring_manifest_schema_invalid: "
                f"source_shape_assertions[{index}] must be an object"
            )
        module_name = _require_string(raw_assertion, "module_name")
        if module_name in seen_modules:
            raise ValueError(
                "transition_authoring_manifest_schema_invalid: "
                f"duplicate source-shape module `{module_name}`"
            )
        seen_modules.add(module_name)
        forbidden_substrings = _require_non_empty_string_list(
            raw_assertion, "forbidden_substrings"
        )
        normalized_assertions.append(
            {
                "module_name": module_name,
                "forbidden_substrings": forbidden_substrings,
            }
        )

    return {
        "schema_version": TRANSITION_AUTHORING_SCHEMA_VERSION,
        "workflow_family": workflow_family,
        "allowed_origins": normalized_allowed_origins,
        "source_shape_assertions": normalized_assertions,
        "__manifest_path__": str(path.resolve()),
        "__manifest_sha256__": _sha256_file(path.resolve()),
    }


def build_transition_authoring_report(
    *,
    workflow_family: str,
    checked_manifest: Mapping[str, Any],
    source_map_payload: Mapping[str, Any],
) -> dict[str, Any]:
    """Classify transition authoring origins and validate source-shape rules."""

    raw_workflows = source_map_payload.get("workflows")
    if not isinstance(raw_workflows, Mapping):
        raise ValueError("transition_authoring_source_map_invalid: missing workflows mapping")

    allowed_rows = [
        dict(row)
        for row in checked_manifest.get("allowed_origins", [])
        if isinstance(row, Mapping)
    ]
    module_paths = _module_paths_by_name(raw_workflows)
    compiled_origins: list[dict[str, Any]] = []
    ordinary_body_violations: list[dict[str, Any]] = []
    extra_origins: list[dict[str, Any]] = []
    matched_row_ids: set[str] = set()

    for workflow_name, raw_row in raw_workflows.items():
        if not isinstance(workflow_name, str) or not isinstance(raw_row, Mapping):
            continue
        workflow_origin = raw_row.get("workflow_origin")
        if not isinstance(workflow_origin, Mapping):
            continue
        workflow_module_name = _optional_string(workflow_origin, "module_name")
        workflow_path = _optional_string(workflow_origin, "path")
        workflow_line = workflow_origin.get("line")
        core_nodes = raw_row.get("core_nodes")
        step_ids = raw_row.get("step_ids")
        if not isinstance(core_nodes, list):
            continue
        for node in core_nodes:
            if not isinstance(node, Mapping):
                continue
            step_id = _optional_string(node, "step_id")
            step_origin = _step_origin_for_id(step_ids=step_ids, step_id=step_id)
            module_name = _authored_module_name(
                step_origin=step_origin,
                workflow_module_name=workflow_module_name,
            )
            path = _optional_string(step_origin, "path") or workflow_path
            line = step_origin.get("line") if isinstance(step_origin, Mapping) else workflow_line
            candidate = _candidate_origin(
                workflow_name=workflow_name,
                module_name=module_name,
                path=path,
                line=line,
                node=node,
                allowed_rows=allowed_rows,
            )
            if candidate is None:
                continue
            compiled_origins.append(candidate)
            matched_row_id = candidate.get("matched_row_id")
            if isinstance(matched_row_id, str):
                matched_row_ids.add(matched_row_id)
            classification = candidate["classification"]
            if classification == "ordinary_body_violation":
                ordinary_body_violations.append(candidate)
            elif matched_row_id is None:
                extra_origins.append(
                    {
                        "workflow_name": workflow_name,
                        "module_name": module_name,
                        "step_kind": candidate["step_kind"],
                        "step_id": candidate["step_id"],
                        "classification": classification,
                    }
                )

    stale_allowed_origins = [
        {
            "row_id": row["row_id"],
            "workflow_name": row.get("workflow_name"),
            "module_name": row.get("module_name"),
            "step_kind": row.get("step_kind"),
            "step_id_contains": row.get("step_id_contains"),
            "classification": row["classification"],
        }
        for row in allowed_rows
        if row["row_id"] not in matched_row_ids
    ]
    source_shape_violations = _source_shape_violations(
        assertions=checked_manifest.get("source_shape_assertions", []),
        module_paths=module_paths,
    )

    compiled_origins.sort(
        key=lambda row: (
            str(row.get("module_name", "")),
            str(row.get("workflow_name", "")),
            str(row.get("step_id", "")),
        )
    )
    ordinary_body_violations.sort(
        key=lambda row: (
            str(row.get("module_name", "")),
            str(row.get("workflow_name", "")),
            str(row.get("step_id", "")),
        )
    )
    extra_origins.sort(
        key=lambda row: (
            str(row.get("module_name", "")),
            str(row.get("workflow_name", "")),
            str(row.get("step_id", "")),
        )
    )
    source_shape_violations.sort(
        key=lambda row: (str(row.get("module_name", "")), str(row.get("substring", "")))
    )

    status = (
        "fail"
        if (
            ordinary_body_violations
            or extra_origins
            or stale_allowed_origins
            or source_shape_violations
        )
        else "pass"
    )
    return {
        "schema_version": TRANSITION_AUTHORING_REPORT_SCHEMA_VERSION,
        "workflow_family": workflow_family,
        "status": status,
        "checked_manifest_path": checked_manifest.get("__manifest_path__"),
        "checked_manifest_sha256": checked_manifest.get("__manifest_sha256__"),
        "compiled_origins": compiled_origins,
        "ordinary_body_violations": ordinary_body_violations,
        "extra_origins": extra_origins,
        "stale_allowed_origins": stale_allowed_origins,
        "invalid_allowed_origins": [],
        "source_shape_violations": source_shape_violations,
    }


def _candidate_origin(
    *,
    workflow_name: str,
    module_name: str | None,
    path: str | None,
    line: object,
    node: Mapping[str, Any],
    allowed_rows: list[dict[str, Any]],
) -> dict[str, Any] | None:
    step_kind = _optional_string(node, "step_kind")
    step_id = _optional_string(node, "step_id")
    if step_kind is None or step_id is None:
        return None
    if not _is_transition_candidate(
        module_name=module_name,
        step_kind=step_kind,
        step_id=step_id,
    ):
        return None
    matched_row = _match_allowed_origin(
        allowed_rows,
        workflow_name=workflow_name,
        module_name=module_name,
        step_kind=step_kind,
        step_id=step_id,
    )
    if matched_row is not None:
        classification = matched_row["classification"]
    else:
        classification = _classify_unmatched_origin(
            module_name=module_name,
            workflow_name=workflow_name,
            step_kind=step_kind,
        )
    return {
        "workflow_name": workflow_name,
        "module_name": module_name,
        "path": path,
        "line": line,
        "step_kind": step_kind,
        "step_id": step_id,
        "classification": classification,
        "matched_row_id": matched_row.get("row_id") if matched_row is not None else None,
    }


def _is_transition_candidate(
    *,
    module_name: str | None,
    step_kind: str,
    step_id: str,
) -> bool:
    if module_name == "lisp_frontend_design_delta/transitions":
        return step_kind in {"resource_transition", "step"} and (
            step_kind == "resource_transition"
            or (
                "lisp_frontend_design_delta_transitions_" in step_id
                and step_id.endswith("__transition_result")
            )
        )
    if step_kind != "resource_transition":
        return False
    return INLINE_HELPER_TRANSITION_MARKER not in step_id


def _match_allowed_origin(
    allowed_rows: list[dict[str, Any]],
    *,
    workflow_name: str,
    module_name: str | None,
    step_kind: str,
    step_id: str,
) -> dict[str, Any] | None:
    for row in allowed_rows:
        row_workflow_name = row.get("workflow_name")
        if isinstance(row_workflow_name, str) and row_workflow_name != workflow_name:
            continue
        row_module_name = row.get("module_name")
        if isinstance(row_module_name, str) and row_module_name != module_name:
            continue
        row_step_kind = row.get("step_kind")
        if isinstance(row_step_kind, str) and row_step_kind != step_kind:
            continue
        row_step_id_contains = row.get("step_id_contains")
        if isinstance(row_step_id_contains, str) and row_step_id_contains not in step_id:
            continue
        return row
    return None


def _classify_unmatched_origin(
    *,
    module_name: str | None,
    workflow_name: str,
    step_kind: str,
) -> str:
    lane = f"{module_name or ''} {workflow_name}".lower()
    if "fixture" in lane:
        return "fixture"
    if "compatibility" in lane or "bridge" in lane:
        return "compatibility_bridge"
    if module_name == "lisp_frontend_design_delta/transitions" and step_kind == "resource_transition":
        return "low_level_library"
    return "ordinary_body_violation"


def _targets_high_level_module(
    *,
    workflow_name: str | None,
    module_name: str | None,
) -> bool:
    if module_name in HIGH_LEVEL_TRANSITION_MODULES:
        return True
    if workflow_name is None:
        return False
    return any(
        workflow_name.startswith(f"{module_name}::")
        for module_name in HIGH_LEVEL_TRANSITION_MODULES
    )


def _step_origin_for_id(
    *,
    step_ids: object,
    step_id: str | None,
) -> Mapping[str, Any]:
    if not isinstance(step_ids, Mapping) or step_id is None:
        return {}
    raw_origin = step_ids.get(step_id)
    return raw_origin if isinstance(raw_origin, Mapping) else {}


def _authored_module_name(
    *,
    step_origin: Mapping[str, Any],
    workflow_module_name: str | None,
) -> str | None:
    path = _optional_string(step_origin, "path")
    if path:
        module_name = _module_name_from_path(Path(path))
        if module_name is not None:
            return module_name
    return workflow_module_name


def _module_name_from_path(path: Path) -> str | None:
    stem = path.stem
    if stem not in {"drain", "work_item", "transitions"}:
        return None
    if "lisp_frontend_design_delta" not in path.parts:
        return None
    return f"lisp_frontend_design_delta/{stem}"


def _module_paths_by_name(
    workflows: Mapping[str, Any],
) -> dict[str, Path]:
    paths: dict[str, Path] = {}
    for raw_row in workflows.values():
        if not isinstance(raw_row, Mapping):
            continue
        workflow_origin = raw_row.get("workflow_origin")
        if not isinstance(workflow_origin, Mapping):
            continue
        module_name = _optional_string(workflow_origin, "module_name")
        path = _optional_string(workflow_origin, "path")
        if module_name and path:
            paths.setdefault(module_name, Path(path))
    return paths


def _source_shape_violations(
    *,
    assertions: object,
    module_paths: Mapping[str, Path],
) -> list[dict[str, Any]]:
    if not isinstance(assertions, list):
        return []
    violations: list[dict[str, Any]] = []
    for assertion in assertions:
        if not isinstance(assertion, Mapping):
            continue
        module_name = _optional_string(assertion, "module_name")
        if module_name is None:
            continue
        module_path = module_paths.get(module_name)
        if module_path is None:
            violations.append(
                {
                    "module_name": module_name,
                    "substring": None,
                    "reason": "module path missing from compiled source map",
                }
            )
            continue
        source = module_path.read_text(encoding="utf-8")
        for substring in assertion.get("forbidden_substrings", []):
            if isinstance(substring, str) and substring in source:
                violations.append(
                    {
                        "module_name": module_name,
                        "substring": substring,
                        "path": str(module_path),
                        "reason": "forbidden low-level transition authoring text is still present",
                    }
                )
    return violations


def _sha256_file(path: Path) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def _optional_string(payload: Mapping[str, Any], key: str) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise ValueError(
            f"transition_authoring_manifest_schema_invalid: `{key}` must be a non-empty string"
        )
    return value


def _require_string(payload: Mapping[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(
            f"transition_authoring_manifest_schema_invalid: `{key}` must be a non-empty string"
        )
    return value


def _require_non_empty_string_list(
    payload: Mapping[str, Any], key: str
) -> list[str]:
    value = payload.get(key)
    if not isinstance(value, list) or not value:
        raise ValueError(
            f"transition_authoring_manifest_schema_invalid: `{key}` must be a non-empty list"
        )
    if not all(isinstance(item, str) and item for item in value):
        raise ValueError(
            "transition_authoring_manifest_schema_invalid: "
            f"`{key}` must contain only non-empty strings"
        )
    return list(value)
