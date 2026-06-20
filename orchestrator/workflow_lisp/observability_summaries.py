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
DESIGN_DELTA_IMPLEMENTATION_PHASE_CHECKS_REPORT_PRIMARY_ROW_ID = (
    "c0.implementation_phase_materialized_return_checks_report"
)
DESIGN_DELTA_IMPLEMENTATION_PHASE_CHECKS_REPORT_MIRROR_ROW_ID = (
    "c0.implementation_phase_materialized_return_checks_report_compiled_boundary"
)
DESIGN_DELTA_IMPLEMENTATION_PHASE_CHECKS_REPORT_WORKFLOW_SURFACE = (
    "lisp_frontend_design_delta/implementation_phase::implementation-phase"
)
DESIGN_DELTA_IMPLEMENTATION_PHASE_CHECKS_REPORT_STEP_SUFFIX = (
    "__materialize_view__blocked_implementation_checks_report"
)
OBSERVABILITY_SUMMARY_SCHEMA_ID = "workflow_lisp_observability_summary.v1"
OBSERVABILITY_SUMMARY_REPORT_SCHEMA_ID = "workflow_lisp_observability_summary_report.v1"
OBSERVABILITY_OLD_WRITER_PAIR_SCHEMA_ID = (
    "workflow_lisp_observability_old_writer_comparisons.v1"
)
_BLOCKED_IMPLEMENTATION_COMPAT_FIELDS = frozenset(
    {
        "status",
        "progress_report",
        "blocker_class",
    }
)
SUMMARY_JSON_PATH = "summaries/typed-terminal-summary.json"
SUMMARY_MARKDOWN_PATH = "summaries/typed-terminal-summary.md"
SUMMARY_REPORT_PATH = "summaries/observability_summary_report.json"
SUMMARY_ENTRY_STEP_NAME = "workflow-terminal"
SUMMARY_ENTRY_KIND = "typed_terminal"
SUMMARY_ENTRY_PROFILE = "workflow-lisp-c2"
SUMMARY_ENTRY_AUTHORITY = "observability_only"
_OLD_WRITER_CONTRACT_CONSUMER_LANES = frozenset(
    {
        "public_output",
        "public_publication",
        "compatibility_bridge",
        "legacy_compatibility",
    }
)
_OLD_WRITER_CONTRACT_DURABILITY = frozenset(
    {
        "durable_publication",
        "public_artifact",
    }
)


def row_requires_old_writer_contract_evidence(row: Mapping[str, Any]) -> bool:
    """Return whether a retired writer row protects a public/bridge contract."""

    bridge = row.get("bridge")
    if isinstance(bridge, Mapping) and bridge:
        return True
    consumer_lane = str(row.get("consumer_lane", ""))
    if consumer_lane in _OLD_WRITER_CONTRACT_CONSUMER_LANES:
        return True
    durability = str(row.get("durability", ""))
    if durability in _OLD_WRITER_CONTRACT_DURABILITY:
        return True
    authority_class = str(row.get("authority_class", ""))
    return authority_class in {"public_artifact", "compatibility_bridge"}


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
        diagnostics_warnings=diagnostics_warnings,
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


def load_old_writer_pair_manifest(
    path: Path,
    *,
    consumer_rendering_manifest_path: Path | None = None,
    consumer_rendering_census: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError(
            "observability_summary_old_writer_evidence_stale: pair manifest must be a JSON object"
        )
    if payload.get("schema_version") != OBSERVABILITY_OLD_WRITER_PAIR_SCHEMA_ID:
        raise ValueError(
            "observability_summary_old_writer_evidence_stale: invalid pair manifest schema"
        )
    if payload.get("target_family") != DESIGN_DELTA_PARENT_DRAIN_TARGET_FAMILY:
        raise ValueError(
            "observability_summary_old_writer_evidence_stale: unexpected target family"
        )
    raw_pairs = payload.get("row_pairs")
    if not isinstance(raw_pairs, list) or not raw_pairs:
        raise ValueError(
            "observability_summary_old_writer_evidence_stale: row_pairs must be a non-empty array"
        )
    consumer_payload = _consumer_rendering_payload(
        consumer_rendering_manifest_path=consumer_rendering_manifest_path,
        consumer_rendering_census=consumer_rendering_census,
    )
    consumer_rows = {
        str(row.get("row_id", "")): row
        for row in consumer_payload.get("rows", [])
        if isinstance(row, Mapping) and isinstance(row.get("row_id"), str)
    }
    normalized_pairs = [
        _normalize_old_writer_pair(
            raw_pair,
            consumer_rows=consumer_rows,
            manifest_path=Path(path),
        )
        for raw_pair in raw_pairs
    ]
    normalized_pairs.sort(key=lambda row: str(row["primary_row_id"]))
    return {
        **dict(payload),
        "row_pairs": normalized_pairs,
        "__manifest_path__": str(Path(path).resolve()),
        "__manifest_sha256__": _sha256_bytes(Path(path).read_bytes()).removeprefix(
            "sha256:"
        ),
    }


def build_observability_pair_report(
    *,
    consumer_rendering_census: Mapping[str, Any],
    pair_manifest: Mapping[str, Any],
    materialize_view_effects: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    consumer_rows = {
        str(row.get("row_id", "")): row
        for row in consumer_rendering_census.get("rows", [])
        if isinstance(row, Mapping) and isinstance(row.get("row_id"), str)
    }
    selected_c0_row_ids: list[str] = []
    diagnostics_errors: list[dict[str, Any]] = []
    pair_results: list[dict[str, Any]] = []
    for raw_pair in pair_manifest.get("row_pairs", []):
        if not isinstance(raw_pair, Mapping):
            continue
        primary_row_id = str(raw_pair.get("primary_row_id", ""))
        mirror_row_id = str(raw_pair.get("mirror_row_id", ""))
        primary_row = consumer_rows.get(primary_row_id)
        mirror_row = consumer_rows.get(mirror_row_id)
        if primary_row is None or mirror_row is None:
            diagnostics_errors.append(
                _diagnostic(
                    "observability_summary_old_writer_mirror_missing",
                    "pair rows are missing from the checked consumer rendering census",
                    c0_row_id=primary_row_id or mirror_row_id,
                )
            )
            continue
        old_writer = raw_pair.get("old_writer")
        replacement = raw_pair.get("replacement")
        if not isinstance(old_writer, Mapping) or not isinstance(replacement, Mapping):
            diagnostics_errors.append(
                _diagnostic(
                    "observability_summary_old_writer_evidence_stale",
                    "pair manifest is missing normalized old-writer metadata",
                    c0_row_id=primary_row_id,
                )
            )
            continue
        effect_live = _old_writer_effect_live(
            workflow_surface=str(raw_pair.get("workflow_surface", "")),
            step_suffix=str(old_writer.get("step_id_suffix", "")),
            materialize_view_effects=materialize_view_effects,
        )
        pair_diagnostics = _validate_observability_pair_state(
            primary_row_id=primary_row_id,
            pair_manifest_row=raw_pair,
            effect_live=effect_live,
        )
        diagnostics_errors.extend(pair_diagnostics)
        pair_results.append(
            {
                "primary_row_id": primary_row_id,
                "mirror_row_id": mirror_row_id,
                "workflow_surface": str(raw_pair.get("workflow_surface", "")),
                "old_writer_effect_live": effect_live,
                "comparison_status": (
                    "validated"
                    if not any(
                        diagnostic.get("code")
                        == "observability_summary_old_writer_evidence_stale"
                        for diagnostic in pair_diagnostics
                    )
                    else "mismatch"
                ),
                "comparison_digest_kind": str(
                    replacement.get("comparison_digest_kind", "sha256")
                ),
                "typed_summary_digest": str(
                    replacement.get("typed_summary_digest", "")
                ),
                "old_writer_payload_digest": str(
                    replacement.get("old_writer_payload_digest", "")
                ),
                "status": "pass" if not pair_diagnostics else "fail",
                "diagnostics": pair_diagnostics,
            }
        )
        if not pair_diagnostics:
            selected_c0_row_ids.extend((primary_row_id, mirror_row_id))
    return {
        "schema_id": OBSERVABILITY_SUMMARY_REPORT_SCHEMA_ID,
        "workflow_family": "design_delta_parent_drain",
        "status": "fail" if diagnostics_errors else "pass",
        "selected_c0_row_ids": sorted(set(selected_c0_row_ids)),
        "diagnostics": {
            "errors": diagnostics_errors,
            "warnings": [],
        },
        "pair_results": pair_results,
        "pair_manifest_provenance": _pair_manifest_provenance(pair_manifest),
    }


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


def _consumer_rendering_payload(
    *,
    consumer_rendering_manifest_path: Path | None,
    consumer_rendering_census: Mapping[str, Any] | None,
) -> Mapping[str, Any]:
    if consumer_rendering_census is not None:
        return consumer_rendering_census
    if consumer_rendering_manifest_path is None:
        raise ValueError(
            "observability_summary_old_writer_evidence_stale: missing consumer rendering census"
        )
    payload = json.loads(Path(consumer_rendering_manifest_path).read_text(encoding="utf-8"))
    if payload.get("schema_version") != CONSUMER_RENDERING_CENSUS_SCHEMA_VERSION:
        raise ValueError(
            "observability_summary_old_writer_evidence_stale: invalid consumer rendering census schema"
        )
    return payload


def _normalize_old_writer_pair(
    raw_pair: Any,
    *,
    consumer_rows: Mapping[str, Mapping[str, Any]],
    manifest_path: Path,
) -> dict[str, Any]:
    if not isinstance(raw_pair, Mapping):
        raise ValueError(
            "observability_summary_old_writer_evidence_stale: row_pairs entries must be objects"
        )
    primary_row_id = _require_string(
        raw_pair,
        "primary_row_id",
        code="observability_summary_old_writer_evidence_stale",
    )
    mirror_row_id = _require_string(
        raw_pair,
        "mirror_row_id",
        code="observability_summary_old_writer_mirror_missing",
    )
    workflow_surface = _require_string(
        raw_pair,
        "workflow_surface",
        code="observability_summary_old_writer_evidence_stale",
    )
    comparison_inputs = raw_pair.get("comparison_inputs")
    if not isinstance(comparison_inputs, Mapping):
        raise ValueError(
            "observability_summary_old_writer_evidence_stale: comparison_inputs must be an object"
        )
    old_writer_payload = _json_clone(
        comparison_inputs.get("old_writer_payload"),
        "observability_summary_old_writer_evidence_stale",
    )
    replacement_payload = _json_clone(
        comparison_inputs.get("replacement_typed_summary_payload"),
        "observability_summary_old_writer_evidence_stale",
    )
    old_writer = raw_pair.get("old_writer")
    replacement = raw_pair.get("replacement")
    if not isinstance(old_writer, Mapping) or not isinstance(replacement, Mapping):
        raise ValueError(
            "observability_summary_old_writer_evidence_stale: old_writer and replacement must be objects"
        )
    step_id_suffix = _require_string(
        old_writer,
        "step_id_suffix",
        code="observability_summary_old_writer_evidence_stale",
    )
    renderer_id = _require_string(
        old_writer,
        "renderer_id",
        code="observability_summary_old_writer_evidence_stale",
    )
    renderer_version = old_writer.get("renderer_version")
    if not isinstance(renderer_version, int):
        raise ValueError(
            "observability_summary_old_writer_evidence_stale: renderer_version must be an integer"
        )
    source_evidence = raw_pair.get("source_evidence")
    if not isinstance(source_evidence, list):
        raise ValueError(
            "observability_summary_old_writer_evidence_stale: source_evidence must be an array"
        )
    legacy_source = _find_source_evidence(
        source_evidence,
        kind="legacy_writer_payload_source",
        code="observability_summary_old_writer_evidence_stale",
    )
    typed_summary_contract = _find_source_evidence(
        source_evidence,
        kind="typed_summary_contract",
        code="observability_summary_old_writer_evidence_stale",
    )
    legacy_source_path = _resolve_manifest_relative_path(
        manifest_path,
        _require_string(
            legacy_source,
            "path",
            code="observability_summary_old_writer_evidence_stale",
        ),
    )
    if legacy_source_path.resolve() == manifest_path.resolve():
        raise ValueError(
            "observability_summary_old_writer_used_as_state: pair manifest cannot self-authenticate legacy payload bytes"
        )
    if legacy_source.get("authority_lane") != "design_delta_migration_inputs":
        raise ValueError(
            "observability_summary_old_writer_evidence_stale: legacy payload source must remain in the checked migration-input lane"
        )
    if not legacy_source_path.is_file():
        raise ValueError(
            "observability_summary_old_writer_evidence_stale: legacy payload source file is missing"
        )
    authoritative_old_writer_payload = _json_clone(
        json.loads(legacy_source_path.read_text(encoding="utf-8")),
        "observability_summary_old_writer_evidence_stale",
    )
    if authoritative_old_writer_payload != old_writer_payload:
        raise ValueError(
            "observability_summary_old_writer_evidence_stale: inline old-writer payload drifted from its checked source"
        )
    _validate_old_writer_payload_contract(
        primary_row_id=primary_row_id,
        mirror_row_id=mirror_row_id,
        old_writer_payload=old_writer_payload,
    )
    _validate_typed_summary_contract(
        primary_row_id=primary_row_id,
        mirror_row_id=mirror_row_id,
        typed_summary_contract=typed_summary_contract,
        replacement_payload=replacement_payload,
    )
    _validate_pair_rows_against_consumer_rows(
        primary_row_id=primary_row_id,
        mirror_row_id=mirror_row_id,
        workflow_surface=workflow_surface,
        step_id_suffix=step_id_suffix,
        renderer_id=renderer_id,
        renderer_version=renderer_version,
        consumer_rows=consumer_rows,
    )
    comparison_digest_kind = _require_string(
        replacement,
        "comparison_digest_kind",
        code="observability_summary_old_writer_evidence_stale",
    )
    evidence_kind = _require_string(
        replacement,
        "evidence_kind",
        code="observability_summary_old_writer_evidence_stale",
    )
    if evidence_kind not in {"old_writer_comparison", "accepted_absence"}:
        raise ValueError(
            "observability_summary_old_writer_evidence_stale: unsupported replacement evidence_kind"
        )
    accepted_absence_reason = ""
    if evidence_kind == "accepted_absence":
        accepted_absence_reason = _require_string(
            replacement,
            "accepted_absence_reason",
            code="observability_summary_old_writer_evidence_stale",
        )
    typed_summary_digest = _require_string(
        replacement,
        "typed_summary_digest",
        code="observability_summary_old_writer_evidence_stale",
    )
    old_writer_payload_digest = _require_string(
        replacement,
        "old_writer_payload_digest",
        code="observability_summary_old_writer_evidence_stale",
    )
    if comparison_digest_kind != "sha256":
        raise ValueError(
            "observability_summary_old_writer_evidence_stale: only sha256 comparison digests are supported"
        )
    if typed_summary_digest != _sha256_json(replacement_payload):
        raise ValueError(
            "observability_summary_old_writer_evidence_stale: typed summary digest does not match inline payload"
        )
    if old_writer_payload_digest != _sha256_json(old_writer_payload):
        raise ValueError(
            "observability_summary_old_writer_evidence_stale: old-writer payload digest does not match inline payload"
        )
    pair_status = _require_string(
        raw_pair,
        "status",
        code="observability_summary_old_writer_evidence_stale",
    )
    if pair_status not in {"live_old_writer", "retired_to_observability"}:
        raise ValueError(
            "observability_summary_old_writer_evidence_stale: unsupported pair status"
        )
    return {
        "primary_row_id": primary_row_id,
        "mirror_row_id": mirror_row_id,
        "workflow_surface": workflow_surface,
        "comparison_inputs": {
            "old_writer_payload": old_writer_payload,
            "replacement_typed_summary_payload": replacement_payload,
        },
        "old_writer": {
            "step_id_suffix": step_id_suffix,
            "renderer_id": renderer_id,
            "renderer_version": renderer_version,
            "payload_source": str(old_writer.get("payload_source", "")),
        },
        "replacement": {
            "evidence_kind": evidence_kind,
            "authority_surface": str(replacement.get("authority_surface", "")),
            "authority_path": str(replacement.get("authority_path", "")),
            "contract_profile": str(replacement.get("contract_profile", "")),
            "payload_source": str(replacement.get("payload_source", "")),
            "comparison_digest_kind": comparison_digest_kind,
            "typed_summary_digest": typed_summary_digest,
            "old_writer_payload_digest": old_writer_payload_digest,
            "accepted_absence_reason": accepted_absence_reason,
        },
        "status": pair_status,
        "source_evidence": _json_clone(
            source_evidence,
            "observability_summary_old_writer_evidence_stale",
        ),
        "legacy_payload_source": {
            "path": str(legacy_source_path),
            "sha256": _sha256_bytes(legacy_source_path.read_bytes()),
        },
        "typed_summary_contract": {
            "authority_surface": str(typed_summary_contract.get("authority_surface", "")),
            "path": str(typed_summary_contract.get("path", "")),
            "contract_profile": str(typed_summary_contract.get("contract_profile", "")),
        },
    }


def _find_source_evidence(
    source_evidence: list[Any],
    *,
    kind: str,
    code: str,
) -> Mapping[str, Any]:
    for item in source_evidence:
        if isinstance(item, Mapping) and item.get("kind") == kind:
            return item
    raise ValueError(f"{code}: source_evidence missing `{kind}`")


def _validate_typed_summary_contract(
    *,
    primary_row_id: str,
    mirror_row_id: str,
    typed_summary_contract: Mapping[str, Any],
    replacement_payload: Any,
) -> None:
    if typed_summary_contract.get("authority_surface") != OBSERVABILITY_SUMMARY_SCHEMA_ID:
        raise ValueError(
            "observability_summary_old_writer_evidence_stale: replacement side must cite the existing C2 authority surface"
        )
    if typed_summary_contract.get("path") != "RUN_ROOT/summaries/typed-terminal-summary.json":
        raise ValueError(
            "observability_summary_old_writer_evidence_stale: replacement side must cite the run-local typed summary path"
        )
    if typed_summary_contract.get("contract_profile") != "terminal_value":
        raise ValueError(
            "observability_summary_old_writer_evidence_stale: replacement side must cite the declared terminal_value profile"
        )
    if not isinstance(replacement_payload, Mapping):
        raise ValueError(
            "observability_summary_old_writer_evidence_stale: replacement typed summary fragment must be an object"
        )
    if _is_checks_report_pair(primary_row_id=primary_row_id, mirror_row_id=mirror_row_id):
        _validate_blocked_implementation_compat_payload(
            payload=replacement_payload,
            payload_label="replacement typed summary fragment",
        )
        return
    status = replacement_payload.get("status")
    if not isinstance(status, str) or not status:
        raise ValueError(
            "observability_summary_old_writer_evidence_stale: replacement typed summary fragment must carry a string status"
        )


def _validate_old_writer_payload_contract(
    *,
    primary_row_id: str,
    mirror_row_id: str,
    old_writer_payload: Any,
) -> None:
    if _is_checks_report_pair(primary_row_id=primary_row_id, mirror_row_id=mirror_row_id):
        _validate_blocked_implementation_compat_payload(
            payload=old_writer_payload,
            payload_label="legacy old-writer payload",
        )


def _is_checks_report_pair(*, primary_row_id: str, mirror_row_id: str) -> bool:
    return (
        primary_row_id
        == DESIGN_DELTA_IMPLEMENTATION_PHASE_CHECKS_REPORT_PRIMARY_ROW_ID
        and mirror_row_id
        == DESIGN_DELTA_IMPLEMENTATION_PHASE_CHECKS_REPORT_MIRROR_ROW_ID
    )


def _validate_blocked_implementation_compat_payload(
    *,
    payload: Any,
    payload_label: str,
) -> None:
    if not isinstance(payload, Mapping):
        raise ValueError(
            f"observability_summary_old_writer_evidence_stale: {payload_label} must be an object"
        )
    payload_keys = {str(key) for key in payload}
    if payload_keys != _BLOCKED_IMPLEMENTATION_COMPAT_FIELDS:
        raise ValueError(
            "observability_summary_old_writer_evidence_stale: "
            f"{payload_label} must match the BlockedImplementationCompatValue seam"
        )
    for field_name in sorted(_BLOCKED_IMPLEMENTATION_COMPAT_FIELDS):
        field_value = payload.get(field_name)
        if not isinstance(field_value, str) or not field_value:
            raise ValueError(
                "observability_summary_old_writer_evidence_stale: "
                f"{payload_label} field `{field_name}` must be a non-empty string"
            )


def _validate_pair_rows_against_consumer_rows(
    *,
    primary_row_id: str,
    mirror_row_id: str,
    workflow_surface: str,
    step_id_suffix: str,
    renderer_id: str,
    renderer_version: int,
    consumer_rows: Mapping[str, Mapping[str, Any]],
) -> None:
    primary_row = consumer_rows.get(primary_row_id)
    mirror_row = consumer_rows.get(mirror_row_id)
    if primary_row is None or mirror_row is None:
        raise ValueError(
            "observability_summary_old_writer_mirror_missing: checked consumer rendering census is missing the target pair rows"
        )
    if primary_row.get("workflow_surface") != workflow_surface or mirror_row.get(
        "workflow_surface"
    ) != workflow_surface:
        raise ValueError(
            "observability_summary_old_writer_evidence_stale: workflow_surface drifted from checked C0 rows"
        )
    primary_suffix = _compiled_suffix(primary_row)
    if primary_suffix != step_id_suffix:
        raise ValueError(
            "observability_summary_old_writer_evidence_stale: step_id_suffix drifted from checked C0 row"
        )
    primary_renderer = primary_row.get("renderer")
    mirror_renderer = mirror_row.get("renderer")
    for renderer in (primary_renderer, mirror_renderer):
        if not isinstance(renderer, Mapping):
            raise ValueError(
                "observability_summary_old_writer_evidence_stale: checked C0 row is missing renderer metadata"
            )
        if renderer.get("renderer_id") != renderer_id or renderer.get("renderer_version") != renderer_version:
            raise ValueError(
                "observability_summary_old_writer_evidence_stale: renderer metadata drifted from checked C0 row"
            )


def _compiled_suffix(row: Mapping[str, Any]) -> str | None:
    compiled_effect = row.get("compiled_effect_match")
    if not isinstance(compiled_effect, Mapping):
        return None
    suffix = compiled_effect.get("step_id_suffix")
    return suffix if isinstance(suffix, str) and suffix else None


def _old_writer_effect_live(
    *,
    workflow_surface: str,
    step_suffix: str,
    materialize_view_effects: Iterable[Mapping[str, Any]],
) -> bool:
    return any(
        isinstance(effect.get("step_id"), str)
        and effect.get("workflow_surface") == workflow_surface
        and str(effect.get("authority_class", "materialized_view"))
        == "materialized_view"
        and str(effect.get("step_id", "")).endswith(step_suffix)
        for effect in materialize_view_effects
    )


def _validate_observability_pair_state(
    *,
    primary_row_id: str,
    pair_manifest_row: Mapping[str, Any],
    effect_live: bool,
) -> list[dict[str, Any]]:
    diagnostics: list[dict[str, Any]] = []
    comparison_inputs = pair_manifest_row.get("comparison_inputs")
    replacement = pair_manifest_row.get("replacement")
    if not isinstance(comparison_inputs, Mapping) or not isinstance(replacement, Mapping):
        return [
            _diagnostic(
                "observability_summary_old_writer_evidence_stale",
                "pair manifest is missing comparison inputs",
                c0_row_id=primary_row_id,
            )
        ]
    semantic_differences = _semantic_payload_differences(
        old_writer_payload=comparison_inputs.get("old_writer_payload"),
        replacement_payload=comparison_inputs.get("replacement_typed_summary_payload"),
    )
    if semantic_differences:
        diagnostics.append(
            _diagnostic(
                "observability_summary_old_writer_evidence_stale",
                "replacement typed-summary fragment drifted from the legacy writer payload",
                c0_row_id=primary_row_id,
                differing_fields=semantic_differences,
            )
        )
    evidence_kind = str(replacement.get("evidence_kind", ""))
    pair_status = str(pair_manifest_row.get("status", ""))
    if effect_live and (
        evidence_kind != "old_writer_comparison" or pair_status != "live_old_writer"
    ):
        diagnostics.append(
            _diagnostic(
                "observability_summary_old_writer_effect_still_live",
                "old-writer materialize_view effect is still live, so the pair cannot be treated as retired or accepted absence",
                c0_row_id=primary_row_id,
            )
        )
    return diagnostics


def _semantic_payload_differences(
    *,
    old_writer_payload: Any,
    replacement_payload: Any,
) -> list[str]:
    if not isinstance(old_writer_payload, Mapping) or not isinstance(replacement_payload, Mapping):
        return ["payload_shape"]
    differing_fields: list[str] = []
    for field_name in (
        "status",
        "progress_report",
        "selected_item",
        "blocker_class",
        "reason",
        "variant",
    ):
        old_present = field_name in old_writer_payload
        replacement_present = field_name in replacement_payload
        if not old_present and not replacement_present:
            continue
        if old_present != replacement_present or old_writer_payload.get(field_name) != replacement_payload.get(
            field_name
        ):
            differing_fields.append(field_name)
    return differing_fields


def _pair_manifest_provenance(pair_manifest: Mapping[str, Any]) -> dict[str, Any]:
    legacy_sources = [
        row.get("legacy_payload_source", {})
        for row in pair_manifest.get("row_pairs", [])
        if isinstance(row, Mapping)
    ]
    return {
        "path": str(pair_manifest.get("__manifest_path__", "")),
        "sha256": (
            f"sha256:{pair_manifest.get('__manifest_sha256__', '')}"
            if pair_manifest.get("__manifest_sha256__")
            else ""
        ),
        "schema_version": str(pair_manifest.get("schema_version", "")),
        "legacy_payload_sources": legacy_sources,
    }


def _build_old_writer_comparisons(
    *,
    selected_rows: list[dict[str, Any]],
    old_writer_paths: Mapping[str, Path | str],
    terminal_value: Mapping[str, Any],
    diagnostics_errors: list[dict[str, Any]],
    diagnostics_warnings: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    comparisons: list[dict[str, Any]] = []
    for row in selected_rows:
        row_id = str(row.get("row_id", ""))
        if row.get("track_c_decision") != "RETIRE_TO_OBSERVABILITY":
            continue
        path_value = old_writer_paths.get(row_id)
        if path_value is None:
            diagnostic = _diagnostic(
                "observability_summary_old_writer_comparison_missing",
                f"old-writer comparison missing for retirement row `{row_id}`",
                row_id=row_id,
            )
            if row_requires_old_writer_contract_evidence(row):
                diagnostics_errors.append(diagnostic)
            else:
                diagnostics_warnings.append(
                    {
                        **diagnostic,
                        "code": "observability_summary_old_writer_mechanics_not_contract",
                    }
                )
            continue
        old_writer_path = Path(path_value)
        if not old_writer_path.exists():
            diagnostic = _diagnostic(
                "observability_summary_old_writer_comparison_missing",
                f"old-writer file missing for retirement row `{row_id}`",
                row_id=row_id,
                path=str(old_writer_path),
            )
            if row_requires_old_writer_contract_evidence(row):
                diagnostics_errors.append(diagnostic)
            else:
                diagnostics_warnings.append(
                    {
                        **diagnostic,
                        "code": "observability_summary_old_writer_mechanics_not_contract",
                    }
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


def _resolve_manifest_relative_path(manifest_path: Path, entry_path: str) -> Path:
    candidate = Path(entry_path)
    if candidate.is_absolute():
        return candidate.resolve()
    manifest_path = manifest_path.resolve()
    for root in manifest_path.parents:
        resolved = (root / candidate).resolve()
        if resolved.exists():
            return resolved
    return (manifest_path.parent / candidate).resolve()


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


def _require_string(
    payload: Mapping[str, Any],
    field_name: str,
    *,
    code: str,
) -> str:
    value = payload.get(field_name)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{code}: missing `{field_name}`")
    return value
