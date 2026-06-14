"""Workflow Lisp observability-only typed terminal summary helpers."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from orchestrator.workflow.transition_executor import (
    read_transition_audit_rows,
    transition_audit_file_digest,
)

from .consumer_rendering_census import CONSUMER_RENDERING_CENSUS_SCHEMA_VERSION
DESIGN_DELTA_PARENT_DRAIN_TARGET_FAMILY = "lisp_frontend_design_delta_parent_drain"
DESIGN_DELTA_PARENT_DRAIN_WORKFLOW_SURFACE = "lisp_frontend_design_delta/drain::drain"
OBSERVABILITY_SUMMARY_SCHEMA_ID = "workflow_lisp_observability_summary.v1"
OBSERVABILITY_SUMMARY_REPORT_SCHEMA_ID = "workflow_lisp_observability_summary_report.v1"
SUMMARY_JSON_PATH = "summaries/typed-terminal-summary.json"
SUMMARY_MARKDOWN_PATH = "summaries/typed-terminal-summary.md"
SUMMARY_REPORT_PATH = "summaries/observability_summary_report.json"
SUMMARY_ENTRY_STEP_NAME = "workflow-terminal"
SUMMARY_ENTRY_KIND = "typed_terminal"
SUMMARY_ENTRY_PROFILE = "workflow-lisp-c2"
SUMMARY_ENTRY_AUTHORITY = "observability_only"


def select_observability_rows(
    manifest_path: Path,
    *,
    workflow_surface: str | None = None,
) -> list[dict[str, Any]]:
    """Return the checked C0 rows relevant to C2 human observability."""

    payload = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    if payload.get("schema_version") != CONSUMER_RENDERING_CENSUS_SCHEMA_VERSION:
        raise ValueError("observability_summary_c0_row_missing: invalid C0 manifest schema")
    rows = payload.get("rows")
    if not isinstance(rows, list):
        raise ValueError("observability_summary_c0_row_missing: checked C0 manifest rows missing")
    selected = [
        dict(row)
        for row in rows
        if isinstance(row, Mapping)
        and (
            row.get("consumer_lane") == "human_observability"
            or row.get("track_c_decision") == "RETIRE_TO_OBSERVABILITY"
        )
        and (
            workflow_surface is None
            or row.get("workflow_surface") == workflow_surface
        )
    ]
    selected.sort(key=lambda row: str(row.get("row_id", "")))
    if not selected:
        raise ValueError("observability_summary_c0_row_missing: no C2 rows selected from checked manifest")
    return selected


def normalize_terminal_value(
    state: Mapping[str, Any],
    *,
    validated_terminal_projection: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Normalize the authoritative typed terminal value from workflow state."""

    workflow_outputs = state.get("workflow_outputs")
    source = "state.workflow_outputs"
    terminal_value: Mapping[str, Any] | None = None
    if isinstance(workflow_outputs, Mapping) and workflow_outputs:
        terminal_value = workflow_outputs
    elif isinstance(validated_terminal_projection, Mapping) and validated_terminal_projection:
        terminal_value = validated_terminal_projection
        source = "validated_terminal_projection"
    if terminal_value is None:
        raise ValueError("observability_summary_terminal_value_missing")
    normalized_value = _json_clone(terminal_value, "observability_summary_terminal_value_invalid")
    digest = _sha256_json(normalized_value)
    return {
        "source": source,
        "value": normalized_value,
        "digest": digest,
    }


def project_transition_audit(audit_paths: Iterable[Path | str]) -> dict[str, Any]:
    """Project read-only transition-audit facts for observability rendering."""

    normalized_paths = [Path(path) for path in audit_paths]
    if not normalized_paths:
        return {"status": "missing", "row_count": 0, "audit_files": []}

    audit_files: list[dict[str, Any]] = []
    total_rows = 0
    for audit_path in normalized_paths:
        if not audit_path.exists():
            continue
        try:
            rows = read_transition_audit_rows(audit_path)
        except Exception as exc:
            raise ValueError("observability_summary_transition_audit_invalid") from exc
        total_rows += len(rows)
        audit_files.append(
            {
                "path": str(audit_path),
                "digest": transition_audit_file_digest(audit_path),
                "row_count": len(rows),
                "rows": _json_clone(rows, "observability_summary_transition_audit_invalid"),
            }
        )

    if not audit_files:
        return {"status": "missing", "row_count": 0, "audit_files": []}
    return {
        "status": "available",
        "row_count": total_rows,
        "audit_files": audit_files,
    }


def build_observability_summary(
    *,
    run_root: Path,
    workflow_family: str,
    workflow_surface: str | None = None,
    state: Mapping[str, Any],
    manifest_path: Path,
    audit_paths: Iterable[Path | str] | None = None,
    old_writer_paths: Mapping[str, Path | str] | None = None,
    validated_terminal_projection: Mapping[str, Any] | None = None,
    workflow_bundle: Any | None = None,
    source_map_lineage: Mapping[str, Any] | None = None,
) -> tuple[dict[str, Any], str, dict[str, Any], dict[str, Any]]:
    """Build the C2 observability-only payloads without mutating runtime state."""

    del workflow_bundle
    selected_rows = select_observability_rows(
        Path(manifest_path),
        workflow_surface=workflow_surface,
    )
    participating_rows = _participating_rows_for_run(
        selected_rows=selected_rows,
        old_writer_paths=old_writer_paths or {},
    )
    workflow_family_value = str(workflow_family)
    if not workflow_family_value:
        raise ValueError("observability_summary_c0_row_missing: workflow family missing")

    terminal = normalize_terminal_value(
        state,
        validated_terminal_projection=validated_terminal_projection,
    )
    _reject_summary_as_authority(run_root=Path(run_root), terminal_value=terminal["value"])

    diagnostics_errors: list[dict[str, Any]] = []
    diagnostics_warnings: list[dict[str, Any]] = []

    if source_map_lineage is None:
        diagnostics_warnings.append(
            _diagnostic("observability_summary_source_map_missing", "source-map lineage not available")
        )

    try:
        transition_audit = project_transition_audit(audit_paths or ())
    except ValueError as exc:
        if str(exc) != "observability_summary_transition_audit_invalid":
            raise
        transition_audit = {"status": "invalid", "row_count": 0, "audit_files": []}
        diagnostics_errors.append(
            _diagnostic(
                "observability_summary_transition_audit_invalid",
                "transition audit evidence unreadable; emitting terminal summary with failing report",
            )
        )
    if transition_audit["status"] == "missing":
        diagnostics_warnings.append(
            _diagnostic(
                "observability_summary_transition_audit_missing",
                "transition audit evidence unavailable; emitting terminal-only summary",
            )
        )

    comparisons = _build_old_writer_comparisons(
        selected_rows=participating_rows,
        old_writer_paths=old_writer_paths or {},
        terminal_value=terminal["value"],
        diagnostics_errors=diagnostics_errors,
    )

    payload = {
        "schema_id": OBSERVABILITY_SUMMARY_SCHEMA_ID,
        "authority": SUMMARY_ENTRY_AUTHORITY,
        "workflow_family": workflow_family_value,
        "run_id": state.get("run_id"),
        "status": state.get("status"),
        "paths": {
            "json": SUMMARY_JSON_PATH,
            "markdown": SUMMARY_MARKDOWN_PATH,
            "report": SUMMARY_REPORT_PATH,
        },
        "selected_c0_row_ids": [str(row.get("row_id", "")) for row in participating_rows],
        "terminal_value": terminal["value"],
        "terminal_value_digest": terminal["digest"],
        "transition_audit": transition_audit,
        "source_map_lineage": _json_clone(source_map_lineage or {}, "observability_summary_source_map_missing"),
        "old_writer_comparisons": comparisons,
    }

    report = {
        "schema_id": OBSERVABILITY_SUMMARY_REPORT_SCHEMA_ID,
        "workflow_family": workflow_family_value,
        "status": "fail" if diagnostics_errors else "pass",
        "diagnostics": {
            "errors": diagnostics_errors,
            "warnings": diagnostics_warnings,
        },
        "paths": dict(payload["paths"]),
        "selected_c0_row_ids": list(payload["selected_c0_row_ids"]),
        "terminal_value_digest": payload["terminal_value_digest"],
        "transition_audit_digests": [
            audit_file["digest"]
            for audit_file in transition_audit.get("audit_files", [])
            if isinstance(audit_file, Mapping) and audit_file.get("digest")
        ],
        "old_writer_comparisons": comparisons,
    }

    markdown = _render_markdown(payload=payload, report=report)
    index_entry = {
        "step_name": SUMMARY_ENTRY_STEP_NAME,
        "kind": SUMMARY_ENTRY_KIND,
        "profile": SUMMARY_ENTRY_PROFILE,
        "authority": SUMMARY_ENTRY_AUTHORITY,
        "status": "completed",
        "snapshot_path": SUMMARY_JSON_PATH,
        "summary_path": SUMMARY_MARKDOWN_PATH,
        "report_path": SUMMARY_REPORT_PATH,
    }
    return payload, markdown, index_entry, report


def _participating_rows_for_run(
    *,
    selected_rows: list[dict[str, Any]],
    old_writer_paths: Mapping[str, Path | str],
) -> list[dict[str, Any]]:
    participating: list[dict[str, Any]] = []
    available_row_ids = {str(row_id) for row_id in old_writer_paths}
    for row in selected_rows:
        row_id = str(row.get("row_id", ""))
        if row.get("consumer_lane") == "human_observability" or row_id in available_row_ids:
            participating.append(row)
    return participating


def _build_old_writer_comparisons(
    *,
    selected_rows: list[dict[str, Any]],
    old_writer_paths: Mapping[str, Path | str],
    terminal_value: Mapping[str, Any],
    diagnostics_errors: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    comparisons: list[dict[str, Any]] = []
    for row in selected_rows:
        row_id = str(row.get("row_id", ""))
        if row.get("track_c_decision") != "RETIRE_TO_OBSERVABILITY":
            continue
        path_value = old_writer_paths.get(row_id)
        if path_value is None:
            diagnostics_errors.append(
                _diagnostic(
                    "observability_summary_old_writer_comparison_missing",
                    f"old-writer comparison missing for retirement row `{row_id}`",
                    row_id=row_id,
                )
            )
            continue
        old_writer_path = Path(path_value)
        if not old_writer_path.exists():
            diagnostics_errors.append(
                _diagnostic(
                    "observability_summary_old_writer_comparison_missing",
                    f"old-writer file missing for retirement row `{row_id}`",
                    row_id=row_id,
                    path=str(old_writer_path),
                )
            )
            continue
        old_writer_payload = _load_old_writer_payload(old_writer_path)
        old_writer_digest = _sha256_json(old_writer_payload)
        terminal_digest = _sha256_json(terminal_value)
        comparisons.append(
            {
                "row_id": row_id,
                "path": str(old_writer_path),
                "status": "match" if old_writer_digest == terminal_digest else "different",
                "old_writer_digest": old_writer_digest,
                "terminal_value_digest": terminal_digest,
            }
        )
    return comparisons


def _load_old_writer_payload(path: Path) -> Mapping[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"raw_text_digest": _sha256_bytes(path.read_bytes())}
    if not isinstance(payload, Mapping):
        return {"raw_payload_digest": _sha256_json(payload)}
    return _json_clone(payload, "observability_summary_old_writer_comparison_missing")


def _reject_summary_as_authority(*, run_root: Path, terminal_value: Mapping[str, Any]) -> None:
    summaries_root = (run_root / "summaries").resolve()
    for value in _walk_values(terminal_value):
        if not isinstance(value, str) or not value:
            continue
        if "summaries/" in value.replace("\\", "/"):
            raise ValueError("observability_summary_used_as_state")
        candidate = Path(value)
        if not candidate.is_absolute():
            continue
        try:
            if candidate.resolve().is_relative_to(summaries_root):
                raise ValueError("observability_summary_used_as_state")
        except FileNotFoundError:
            if str(candidate).startswith(str(summaries_root)):
                raise ValueError("observability_summary_used_as_state")


def _render_markdown(*, payload: Mapping[str, Any], report: Mapping[str, Any]) -> str:
    terminal_value = payload.get("terminal_value", {})
    transition_audit = payload.get("transition_audit", {})
    lines = [
        "# Typed Terminal Summary",
        "",
        "observability-only view. This summary must not be used as workflow state or control input.",
        "",
        f"- workflow_family: `{payload.get('workflow_family')}`",
        f"- authority: `{payload.get('authority')}`",
        f"- terminal_value_digest: `{payload.get('terminal_value_digest')}`",
        f"- transition_audit_status: `{transition_audit.get('status')}`",
        f"- transition_audit_rows: `{transition_audit.get('row_count', 0)}`",
    ]
    if isinstance(terminal_value, Mapping):
        for field_name in ("status", "selected_item", "blocker_class", "reason"):
            value = terminal_value.get(field_name)
            if value is not None:
                lines.append(f"- {field_name}: `{value}`")
    warnings = report.get("diagnostics", {}).get("warnings", [])
    if isinstance(warnings, list) and warnings:
        lines.extend(["", "## Warnings"])
        for warning in warnings:
            if isinstance(warning, Mapping):
                lines.append(f"- `{warning.get('code')}`: {warning.get('message')}")
    errors = report.get("diagnostics", {}).get("errors", [])
    if isinstance(errors, list) and errors:
        lines.extend(["", "## Errors"])
        for error in errors:
            if isinstance(error, Mapping):
                lines.append(f"- `{error.get('code')}`: {error.get('message')}")
    return "\n".join(lines) + "\n"


def _walk_values(value: Any) -> Iterable[Any]:
    if isinstance(value, Mapping):
        for item in value.values():
            yield from _walk_values(item)
        return
    if isinstance(value, list):
        for item in value:
            yield from _walk_values(item)
        return
    yield value


def _diagnostic(code: str, message: str, **extra: Any) -> dict[str, Any]:
    payload = {"code": code, "message": message}
    payload.update({key: value for key, value in extra.items() if value is not None})
    return payload


def _json_clone(value: Any, error_code: str) -> Any:
    try:
        rendered = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    except (TypeError, ValueError) as exc:
        raise ValueError(error_code) from exc
    return json.loads(rendered)


def _sha256_json(value: Any) -> str:
    rendered = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return f"sha256:{hashlib.sha256(rendered.encode('utf-8')).hexdigest()}"


def _sha256_bytes(payload: bytes) -> str:
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"
