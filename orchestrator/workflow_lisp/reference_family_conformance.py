"""Reference-family conformance profile aggregation for Design Delta evidence."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from . import migration_parity


SCHEMA_VERSION = "workflow_lisp_reference_family_conformance_profile.v1"
SURFACE_IDS = (
    "parent_callable_orc_route",
    "public_private_boundary",
    "hidden_compatibility_bridge_carriage",
    "hidden_compatibility_bridge_evidence_alignment",
    "observability_old_writer_retirement",
    "provider_inputs",
    "provider_write_targets",
    "body_renderings",
    "compatibility_files",
    "deterministic_helpers",
    "durable_state_changes",
    "source_shape_gate",
    "completion_inventory",
    "migration_parity_surface",
)
SURFACE_QUESTIONS = {
    "parent_callable_orc_route": "Does the parent family compile and smoke through WCC as one family?",
    "public_private_boundary": "Are public inputs limited to authored values and labeled compatibility bridges?",
    "hidden_compatibility_bridge_carriage": "Does retained compatibility bridge carriage stay scoped without widening authored signatures?",
    "hidden_compatibility_bridge_evidence_alignment": "Do compiled and checked bridge evidence lanes stay fingerprint-aligned?",
    "observability_old_writer_retirement": "Does observability retirement evidence stay aligned across the checked and compiled lanes?",
    "provider_inputs": "Do nontrivial provider calls use typed prompt-subject records?",
    "provider_write_targets": "Are write targets classified separately from prompt facts?",
    "body_renderings": "Are remaining body renderings limited to justified publications or compatibility seams?",
    "compatibility_files": "Are compatibility files generated from typed values with clear ownership metadata?",
    "deterministic_helpers": "Are deterministic helpers retired to typed projection or certified command boundaries?",
    "durable_state_changes": "Do durable state changes use typed transitions or certified transition adapters?",
    "source_shape_gate": "Does the reference family preserve the approved source-shape evidence lane?",
    "completion_inventory": "Does the checked completed-gap inventory match canonical run-state evidence?",
    "migration_parity_surface": "Do checked migration parity artifacts agree with validated gate-derived results?",
}
SURFACE_OWNER_LANES = {
    "parent_callable_orc_route": ("migration_parity",),
    "public_private_boundary": (
        "workflow-lisp-runtime-native-drain-design-delta-parent-drain-public-boundary-and-terminal-compat-retirement",
    ),
    "hidden_compatibility_bridge_carriage": (
        "workflow-lisp-runtime-native-drain-shared-hidden-compatibility-bridge-carriage-over-fixed-run-item",
    ),
    "hidden_compatibility_bridge_evidence_alignment": (
        "workflow-lisp-runtime-native-drain-resume-plumbing-retirement-evidence-alignment-for-hidden-run-item-compatibility-bridge",
    ),
    "observability_old_writer_retirement": (
        "workflow-lisp-runtime-native-drain-observability-summary-old-writer-comparison-for-implementation-phase-checks-report",
    ),
    "provider_inputs": (
        "workflow-lisp-runtime-native-drain-typed-provider-request-records",
    ),
    "provider_write_targets": (
        "workflow-lisp-runtime-native-drain-entry-boundary-publication-adoption",
    ),
    "body_renderings": (
        "workflow-lisp-runtime-native-drain-consumed-artifact-prompt-rendering-modes",
    ),
    "compatibility_files": (
        "workflow-lisp-runtime-native-drain-shared-hidden-carried-compatibility-bridge-prompt-request-rendering",
    ),
    "deterministic_helpers": (
        "workflow-lisp-runtime-native-drain-projection-retirement-parity-evidence-reconciliation",
    ),
    "durable_state_changes": (
        "workflow-lisp-runtime-native-drain-domain-transition-operations",
    ),
    "source_shape_gate": (
        "workflow-lisp-runtime-native-drain-reference-family-conformance-profile-reconciliation",
    ),
    "completion_inventory": (
        "workflow-lisp-runtime-native-drain-reference-family-conformance-profile-reconciliation",
    ),
    "migration_parity_surface": (
        "workflow-lisp-runtime-native-drain-reference-family-conformance-profile-reconciliation",
    ),
}
CHECKED_MANIFEST_INPUT_IDS = {
    "boundary_authority_manifest": "boundary_authority",
    "command_boundaries_manifest": "command_boundaries",
    "value_flow_census": "value_flow_census",
    "consumer_rendering_census": "consumer_rendering_census",
    "compatibility_bridges_manifest": "compatibility_bridges",
    "rendering_cleanup_manifest": "rendering_cleanup",
    "rendering_ergonomics_manifest": "rendering_ergonomics",
    "transition_authoring_manifest": "transition_authoring",
    "resume_plumbing_retirement_manifest": "resume_plumbing_retirement",
    "observability_old_writer_comparisons": "observability_old_writer_comparisons",
}
LEGACY_GATE_OWNED_REPORT_FIELDS = frozenset(
    {"primary_surface", "report_valid", "evidence_complete"}
)


@dataclass(frozen=True)
class EvidenceInput:
    input_id: str
    input_kind: str
    path: str | None
    load_status: str
    sha256: str | None
    details: Mapping[str, object]


@dataclass(frozen=True)
class Diagnostic:
    code: str
    message: str
    severity: str
    details: Mapping[str, object]


def parse_parity_markdown_metadata(text: str) -> dict[str, object]:
    metadata: dict[str, object] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line.startswith("- Non-regressive: `") and line.endswith("`"):
            metadata["non_regressive"] = (
                line.removeprefix("- Non-regressive: `").removesuffix("`") == "true"
            )
        elif line.startswith("- Promotion eligible: `") and line.endswith("`"):
            metadata["promotion_eligible"] = (
                line.removeprefix("- Promotion eligible: `").removesuffix("`")
                == "true"
            )
        elif line.startswith("- Primary surface: `") and line.endswith("`"):
            metadata["primary_surface"] = (
                line.removeprefix("- Primary surface: `").removesuffix("`")
            )
    missing = sorted(
        {"non_regressive", "promotion_eligible", "primary_surface"} - set(metadata)
    )
    if missing:
        raise ValueError("parity markdown is missing metadata bullets: " + ", ".join(missing))
    return metadata


def build_reference_family_conformance_profile(
    *,
    workflow_family: str,
    run_state_path: Path,
    drain_summary_path: Path,
    design_gap_summary_root: Path,
    implementation_architecture_root: Path,
    architecture_index_path: Path,
    target_design_path: Path,
    baseline_design_path: Path,
    command_adapter_contract_path: Path,
    parity_targets_path: Path,
    parity_report_json_path: Path,
    parity_report_markdown_path: Path,
    parity_index_path: Path,
    checked_manifest_paths: dict[str, Path],
    owner_reports: dict[str, dict[str, object]],
    repo_root: Path,
) -> dict[str, object]:
    diagnostics: list[Diagnostic] = []
    evidence_inputs: list[EvidenceInput] = []
    generated_at = _iso8601_now()

    run_state = _load_json_input(evidence_inputs, "run_state", run_state_path)
    drain_summary = _load_json_input(evidence_inputs, "drain_summary", drain_summary_path)
    summary_inventory = _scan_summary_directory(
        evidence_inputs,
        "design_gap_summary_directory",
        design_gap_summary_root,
    )
    implementation_architectures = _scan_implementation_architectures(
        evidence_inputs,
        "implementation_architecture_directory",
        implementation_architecture_root,
    )
    architecture_index = _load_text_input(
        evidence_inputs, "architecture_index", architecture_index_path
    )
    target_design = _load_text_input(evidence_inputs, "target_design", target_design_path)
    baseline_design = _load_text_input(
        evidence_inputs, "baseline_design", baseline_design_path
    )
    command_adapter_contract = _load_text_input(
        evidence_inputs,
        "command_adapter_contract",
        command_adapter_contract_path,
    )
    parity_targets = _load_json_input(
        evidence_inputs,
        "parity_targets",
        parity_targets_path,
    )
    parity_report_json = _load_json_input(
        evidence_inputs,
        "parity_json_report",
        parity_report_json_path,
    )
    parity_report_markdown = _load_text_input(
        evidence_inputs,
        "parity_markdown_report",
        parity_report_markdown_path,
    )
    parity_index = _load_json_input(evidence_inputs, "parity_index", parity_index_path)
    checked_manifests = {
        CHECKED_MANIFEST_INPUT_IDS.get(input_id, input_id): _load_input_by_suffix(
            evidence_inputs,
            CHECKED_MANIFEST_INPUT_IDS.get(input_id, input_id),
            path,
        )
        for input_id, path in sorted(checked_manifest_paths.items())
    }
    inline_owner_reports = {
        input_id: _record_inline_report_input(evidence_inputs, input_id, payload)
        for input_id, payload in sorted(owner_reports.items())
    }

    for required_input in (
        run_state,
        drain_summary,
        summary_inventory,
        implementation_architectures,
        architecture_index,
        target_design,
        baseline_design,
        command_adapter_contract,
        parity_targets,
    ):
        _require_loaded(diagnostics, required_input)

    completed_gap_reconciliation = _reconcile_completed_gaps(
        run_state=run_state,
        drain_summary=drain_summary,
        summary_inventory=summary_inventory,
        implementation_architectures=implementation_architectures,
        architecture_index=architecture_index,
        repo_root=repo_root,
        diagnostics=diagnostics,
    )
    parity_surface_reconciliation = _reconcile_parity_surface(
        workflow_family=workflow_family,
        parity_targets_path=parity_targets_path,
        parity_targets=parity_targets,
        parity_report_json=parity_report_json,
        parity_report_markdown=parity_report_markdown,
        parity_index=parity_index,
        repo_root=repo_root,
        diagnostics=diagnostics,
    )
    conformance_surfaces = _build_conformance_surfaces(
        workflow_family=workflow_family,
        checked_manifests=checked_manifests,
        owner_reports=inline_owner_reports,
        completed_gap_reconciliation=completed_gap_reconciliation,
        parity_surface_reconciliation=parity_surface_reconciliation,
        diagnostics=diagnostics,
    )
    profile_status = (
        "pass"
        if not diagnostics and all(row["status"] == "pass" for row in conformance_surfaces)
        else "fail"
    )

    return {
        "schema_version": SCHEMA_VERSION,
        "workflow_family": workflow_family,
        "generated_at": generated_at,
        "profile_status": profile_status,
        "target_design": _relative_or_absolute_path(target_design_path, repo_root),
        "baseline_design": _relative_or_absolute_path(baseline_design_path, repo_root),
        "evidence_inputs": [_evidence_input_to_json(item) for item in evidence_inputs],
        "completed_gap_reconciliation": completed_gap_reconciliation,
        "conformance_surfaces": conformance_surfaces,
        "parity_surface_reconciliation": parity_surface_reconciliation,
        "diagnostics": [_diagnostic_to_json(item) for item in diagnostics],
    }


def _load_input_by_suffix(
    evidence_inputs: list[EvidenceInput],
    input_id: str,
    path: Path,
) -> dict[str, object]:
    if path.suffix == ".md":
        return _load_text_input(evidence_inputs, input_id, path)
    return _load_json_input(evidence_inputs, input_id, path)


def _load_json_input(
    evidence_inputs: list[EvidenceInput],
    input_id: str,
    path: Path,
) -> dict[str, object]:
    try:
        raw_bytes = path.read_bytes()
    except FileNotFoundError:
        record = EvidenceInput(
            input_id=input_id,
            input_kind="json",
            path=str(path),
            load_status="missing",
            sha256=None,
            details={},
        )
        evidence_inputs.append(record)
        return {"record": record, "payload": None}
    try:
        payload = json.loads(raw_bytes.decode("utf-8"))
        record = EvidenceInput(
            input_id=input_id,
            input_kind="json",
            path=str(path),
            load_status="loaded",
            sha256=_sha256_bytes(raw_bytes),
            details={},
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        payload = None
        record = EvidenceInput(
            input_id=input_id,
            input_kind="json",
            path=str(path),
            load_status="invalid",
            sha256=_sha256_bytes(raw_bytes),
            details={"error": str(exc)},
        )
    evidence_inputs.append(record)
    return {"record": record, "payload": payload}


def _load_text_input(
    evidence_inputs: list[EvidenceInput],
    input_id: str,
    path: Path,
) -> dict[str, object]:
    try:
        raw_bytes = path.read_bytes()
    except FileNotFoundError:
        record = EvidenceInput(
            input_id=input_id,
            input_kind="text",
            path=str(path),
            load_status="missing",
            sha256=None,
            details={},
        )
        evidence_inputs.append(record)
        return {"record": record, "text": None}
    try:
        text = raw_bytes.decode("utf-8")
        record = EvidenceInput(
            input_id=input_id,
            input_kind="text",
            path=str(path),
            load_status="loaded",
            sha256=_sha256_bytes(raw_bytes),
            details={},
        )
    except UnicodeDecodeError as exc:
        text = None
        record = EvidenceInput(
            input_id=input_id,
            input_kind="text",
            path=str(path),
            load_status="invalid",
            sha256=_sha256_bytes(raw_bytes),
            details={"error": str(exc)},
        )
    evidence_inputs.append(record)
    return {"record": record, "text": text}


def _scan_summary_directory(
    evidence_inputs: list[EvidenceInput],
    input_id: str,
    path: Path,
) -> dict[str, object]:
    if not path.is_dir():
        record = EvidenceInput(
            input_id=input_id,
            input_kind="directory",
            path=str(path),
            load_status="missing",
            sha256=None,
            details={},
        )
        evidence_inputs.append(record)
        return {"record": record, "files_by_gap_id": {}, "payloads_by_gap_id": {}}
    files_by_gap_id: dict[str, Path] = {}
    payloads_by_gap_id: dict[str, object] = {}
    for child in sorted(path.glob("*-summary.json")):
        if not child.is_file():
            continue
        gap_id = child.name.removesuffix("-summary.json")
        files_by_gap_id[gap_id] = child
        try:
            payloads_by_gap_id[gap_id] = json.loads(child.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            payloads_by_gap_id[gap_id] = None
    record = EvidenceInput(
        input_id=input_id,
        input_kind="directory",
        path=str(path),
        load_status="loaded",
        sha256=_sha256_directory(path, pattern="*-summary.json"),
        details={"file_count": len(files_by_gap_id)},
    )
    evidence_inputs.append(record)
    return {
        "record": record,
        "files_by_gap_id": files_by_gap_id,
        "payloads_by_gap_id": payloads_by_gap_id,
    }


def _scan_implementation_architectures(
    evidence_inputs: list[EvidenceInput],
    input_id: str,
    path: Path,
) -> dict[str, object]:
    if not path.is_dir():
        record = EvidenceInput(
            input_id=input_id,
            input_kind="directory",
            path=str(path),
            load_status="missing",
            sha256=None,
            details={},
        )
        evidence_inputs.append(record)
        return {"record": record, "paths_by_gap_id": {}}
    paths_by_gap_id = {
        child.name: child / "implementation_architecture.md"
        for child in sorted(path.iterdir())
        if child.is_dir()
    }
    record = EvidenceInput(
        input_id=input_id,
        input_kind="directory",
        path=str(path),
        load_status="loaded",
        sha256=_sha256_directory(path, pattern="*/implementation_architecture.md"),
        details={"file_count": len(paths_by_gap_id)},
    )
    evidence_inputs.append(record)
    return {"record": record, "paths_by_gap_id": paths_by_gap_id}


def _record_inline_report_input(
    evidence_inputs: list[EvidenceInput],
    input_id: str,
    payload: dict[str, object],
) -> dict[str, object]:
    status = payload.get("status") if isinstance(payload.get("status"), str) else None
    is_boundary_authority_report = (
        input_id == "boundary_authority_report"
        and isinstance(payload.get("workflow_family"), str)
        and isinstance(payload.get("workflows"), list)
        and bool(payload.get("workflows"))
    )
    load_status = "loaded" if status is not None or is_boundary_authority_report else "invalid"
    encoded = json.dumps(
        _json_compatible(payload),
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    record = EvidenceInput(
        input_id=input_id,
        input_kind="inline_report",
        path=str(payload.get("path")) if isinstance(payload.get("path"), str) else None,
        load_status=load_status,
        sha256=_sha256_bytes(encoded),
        details={"status": status},
    )
    evidence_inputs.append(record)
    return {"record": record, "payload": payload}


def _require_loaded(
    diagnostics: list[Diagnostic],
    loaded_input: dict[str, object],
) -> None:
    record = loaded_input["record"]
    if record.load_status == "loaded":
        return
    code = (
        "reference_family_conformance_input_missing"
        if record.load_status == "missing"
        else "reference_family_conformance_input_invalid"
    )
    message = (
        f"required evidence input `{record.input_id}` is missing"
        if record.load_status == "missing"
        else f"required evidence input `{record.input_id}` is invalid"
    )
    diagnostics.append(
        Diagnostic(
            code=code,
            message=message,
            severity="error",
            details={
                "input_id": record.input_id,
                "evidence_path": record.path,
            },
        )
    )


def _reconcile_completed_gaps(
    *,
    run_state: dict[str, object],
    drain_summary: dict[str, object],
    summary_inventory: dict[str, object],
    implementation_architectures: dict[str, object],
    architecture_index: dict[str, object],
    repo_root: Path,
    diagnostics: list[Diagnostic],
) -> dict[str, object]:
    run_state_payload = run_state.get("payload")
    drain_summary_payload = drain_summary.get("payload")
    if not isinstance(run_state_payload, dict) or not isinstance(drain_summary_payload, dict):
        return {
            "run_state_count": 0,
            "drain_summary_count": 0,
            "missing_from_drain_summary": [],
            "extra_in_drain_summary": [],
            "ordered_list_matches": False,
            "missing_summary_artifacts": [],
            "missing_architecture_files": [],
            "missing_from_architecture_index": [],
            "evidence_paths": [],
            "status": "fail",
        }

    run_completed = _normalize_string_list(run_state_payload.get("completed_design_gaps"))
    summary_completed = _normalize_string_list(
        drain_summary_payload.get("completed_design_gaps")
    )
    summary_completed_set = set(summary_completed)
    run_completed_set = set(run_completed)
    missing_from_summary = [
        gap_id for gap_id in run_completed if gap_id not in summary_completed_set
    ]
    extra_in_summary = [
        gap_id for gap_id in summary_completed if gap_id not in run_completed_set
    ]
    ordered_list_matches = run_completed == summary_completed

    summary_files = summary_inventory.get("files_by_gap_id", {})
    summary_payloads = summary_inventory.get("payloads_by_gap_id", {})
    missing_summary_artifacts = sorted(
        gap_id for gap_id in run_completed if gap_id not in summary_files
    )
    expected_run_state_path = (
        _relative_or_absolute_path(Path(str(run_state["record"].path)), repo_root)
        if run_state["record"].path
        else None
    )
    stale_summary_metadata = sorted(
        gap_id
        for gap_id in run_completed
        if gap_id not in missing_summary_artifacts
        and (
            not isinstance(summary_payloads.get(gap_id), dict)
            or summary_payloads[gap_id].get("item_status") != "COMPLETED"
            or (
                isinstance(expected_run_state_path, str)
                and summary_payloads[gap_id].get("run_state_path")
                != expected_run_state_path
            )
        )
    )
    implementation_paths = implementation_architectures.get("paths_by_gap_id", {})
    missing_architecture_files = sorted(
        gap_id
        for gap_id in run_completed
        if not isinstance(implementation_paths.get(gap_id), Path)
        or not implementation_paths[gap_id].is_file()
    )

    missing_from_architecture_index: list[str] = []
    architecture_index_text = architecture_index.get("text")
    if isinstance(architecture_index_text, str):
        for gap_id in run_completed:
            expected_path = implementation_paths.get(gap_id)
            relpath = gap_id
            if isinstance(expected_path, Path):
                relpath = _relative_or_absolute_path(expected_path, repo_root)
            if gap_id not in architecture_index_text and relpath not in architecture_index_text:
                missing_from_architecture_index.append(gap_id)

    if missing_from_summary or extra_in_summary or not ordered_list_matches:
        diagnostics.append(
            Diagnostic(
                code="reference_family_completed_gap_summary_mismatch",
                message="drain summary completed-gap inventory does not match run state",
                severity="error",
                details={
                    "evidence_path": run_state["record"].path,
                    "comparison_path": drain_summary["record"].path,
                    "json_pointer": "/completed_design_gaps",
                    "expected_value": f"{len(run_completed)} completed gaps from run_state",
                    "actual_value": f"{len(summary_completed)} completed gaps",
                    "missing_from_drain_summary": missing_from_summary,
                    "extra_in_drain_summary": extra_in_summary,
                    "ordered_list_matches": ordered_list_matches,
                    "related_surface_id": "completion_inventory",
                    "suggested_owner_lane": "reference-family conformance profile reconciliation",
                },
            )
        )

    if (
        missing_summary_artifacts
        or stale_summary_metadata
        or missing_architecture_files
        or missing_from_architecture_index
    ):
        diagnostics.append(
            Diagnostic(
                code="reference_family_completed_gap_artifact_missing",
                message="one or more completed gaps are missing or stale in checked evidence artifacts",
                severity="error",
                details={
                    "evidence_path": implementation_architectures["record"].path,
                    "comparison_path": summary_inventory["record"].path,
                    "architecture_index_path": architecture_index["record"].path,
                    "missing_summary_artifacts": missing_summary_artifacts,
                    "stale_summary_metadata": stale_summary_metadata,
                    "expected_run_state_path": expected_run_state_path,
                    "missing_architecture_files": missing_architecture_files,
                    "missing_from_architecture_index": missing_from_architecture_index,
                    "related_surface_id": "completion_inventory",
                    "suggested_owner_lane": "reference-family conformance profile reconciliation",
                },
            )
        )

    status = (
        "pass"
        if not (
            missing_from_summary
            or extra_in_summary
            or not ordered_list_matches
            or missing_summary_artifacts
            or stale_summary_metadata
            or missing_architecture_files
            or missing_from_architecture_index
        )
        else "fail"
    )
    return {
        "run_state_count": len(run_completed),
        "drain_summary_count": len(summary_completed),
        "missing_from_drain_summary": missing_from_summary,
        "extra_in_drain_summary": extra_in_summary,
        "ordered_list_matches": ordered_list_matches,
        "missing_summary_artifacts": missing_summary_artifacts,
        "stale_summary_metadata": stale_summary_metadata,
        "missing_architecture_files": missing_architecture_files,
        "missing_from_architecture_index": missing_from_architecture_index,
        "evidence_paths": sorted(
            {
                path
                for path in (
                    run_state["record"].path,
                    drain_summary["record"].path,
                    summary_inventory["record"].path,
                    implementation_architectures["record"].path,
                    architecture_index["record"].path,
                )
                if isinstance(path, str) and path
            }
        ),
        "status": status,
    }


def _reconcile_parity_surface(
    *,
    workflow_family: str,
    parity_targets_path: Path,
    parity_targets: dict[str, object],
    parity_report_json: dict[str, object],
    parity_report_markdown: dict[str, object],
    parity_index: dict[str, object],
    repo_root: Path,
    diagnostics: list[Diagnostic],
) -> dict[str, object]:
    report_payload = parity_report_json.get("payload")
    index_payload = parity_index.get("payload")
    result = {
        "workflow_family": workflow_family,
        "json_report": _relative_or_absolute_path(parity_report_json_path := Path(str(parity_report_json["record"].path)), repo_root)
        if parity_report_json["record"].path
        else None,
        "markdown_report": _relative_or_absolute_path(parity_markdown_path := Path(str(parity_report_markdown["record"].path)), repo_root)
        if parity_report_markdown["record"].path
        else None,
        "index_report": _relative_or_absolute_path(parity_index_path := Path(str(parity_index["record"].path)), repo_root)
        if parity_index["record"].path
        else None,
        "json_non_regressive": None,
        "json_eligible_for_primary_surface": None,
        "derived_primary_surface": None,
        "markdown_primary_surface": None,
        "index_primary_surface": None,
        "evidence_paths": sorted(
            {
                path
                for path in (
                    _relative_or_absolute_path(parity_targets_path, repo_root),
                    _relative_or_absolute_path(
                        Path(str(parity_report_json["record"].path)),
                        repo_root,
                    )
                    if parity_report_json["record"].path
                    else None,
                    _relative_or_absolute_path(
                        Path(str(parity_report_markdown["record"].path)),
                        repo_root,
                    )
                    if parity_report_markdown["record"].path
                    else None,
                    _relative_or_absolute_path(
                        Path(str(parity_index["record"].path)),
                        repo_root,
                    )
                    if parity_index["record"].path
                    else None,
                )
                if isinstance(path, str) and path
            }
        ),
        "status": "fail",
    }

    targets = _load_validated_parity_targets(
        parity_targets_path=parity_targets_path,
        parity_targets=parity_targets,
        diagnostics=diagnostics,
    )
    if targets is None:
        return result

    for evidence_input, code_missing, code_invalid in (
        (
            parity_report_json,
            "reference_family_parity_report_missing",
            "reference_family_parity_report_invalid",
        ),
        (
            parity_report_markdown,
            "reference_family_parity_report_missing",
            "reference_family_parity_report_invalid",
        ),
        (
            parity_index,
            "reference_family_parity_report_missing",
            "reference_family_parity_report_invalid",
        ),
    ):
        record = evidence_input["record"]
        if record.load_status == "loaded":
            continue
        diagnostics.append(
            Diagnostic(
                code=code_missing if record.load_status == "missing" else code_invalid,
                message=(
                    f"required parity evidence `{record.input_id}` is missing"
                    if record.load_status == "missing"
                    else f"required parity evidence `{record.input_id}` is invalid"
                ),
                severity="error",
                details={
                    "input_id": record.input_id,
                    "evidence_path": record.path,
                    "related_surface_id": "migration_parity_surface",
                },
            )
        )
        return result

    if not isinstance(report_payload, Mapping):
        return result
    if not isinstance(index_payload, Mapping):
        return result

    if LEGACY_GATE_OWNED_REPORT_FIELDS & set(report_payload):
        diagnostics.append(
            Diagnostic(
                code="reference_family_primary_surface_authored",
                message="parity report must not author gate-owned primary-surface fields",
                severity="error",
                details={
                    "evidence_path": parity_report_json["record"].path,
                    "authored_fields": sorted(
                        LEGACY_GATE_OWNED_REPORT_FIELDS & set(report_payload)
                    ),
                    "related_surface_id": "migration_parity_surface",
                },
            )
        )
        return result

    try:
        target = next(item for item in targets if item.workflow_family == workflow_family)
        gate_row = migration_parity.validate_report_for_target(
            report_payload,
            target=target,
            targets_file=parity_targets_path,
            repo_root=repo_root,
            today=date.today(),
        )
    except (StopIteration, ValueError) as exc:
        diagnostics.append(
            Diagnostic(
                code="reference_family_parity_report_invalid",
                message=f"checked parity JSON report is invalid: {exc}",
                severity="error",
                details={
                    "evidence_path": parity_report_json["record"].path,
                    "related_surface_id": "migration_parity_surface",
                },
            )
        )
        return result

    derived_primary_surface = migration_parity.derive_primary_surface(
        non_regressive=gate_row.non_regressive,
        eligible_for_primary_surface=gate_row.eligible_for_primary_surface,
    )
    result["json_non_regressive"] = gate_row.non_regressive
    result["json_eligible_for_primary_surface"] = gate_row.eligible_for_primary_surface
    result["derived_primary_surface"] = derived_primary_surface

    markdown_text = parity_report_markdown.get("text")
    if not isinstance(markdown_text, str):
        return result
    try:
        metadata = parse_parity_markdown_metadata(markdown_text)
    except ValueError as exc:
        diagnostics.append(
            Diagnostic(
                code="reference_family_parity_report_invalid",
                message=f"checked parity markdown metadata is invalid: {exc}",
                severity="error",
                details={
                    "evidence_path": parity_report_markdown["record"].path,
                    "related_surface_id": "migration_parity_surface",
                },
            )
        )
        return result

    result["markdown_primary_surface"] = metadata["primary_surface"]

    index_primary_surface = None
    index_non_regressive = None
    index_eligible = None
    targets_payload = index_payload.get("targets")
    if isinstance(targets_payload, list):
        for row in targets_payload:
            if not isinstance(row, Mapping) or row.get("workflow_family") != workflow_family:
                continue
            index_primary_surface = row.get("primary_surface")
            index_non_regressive = row.get("non_regressive")
            promotion = row.get("promotion_eligibility")
            if isinstance(promotion, Mapping):
                index_eligible = promotion.get("eligible_for_primary_surface")
            break
    result["index_primary_surface"] = index_primary_surface

    mismatch = any(
        (
            metadata["non_regressive"] != gate_row.non_regressive,
            metadata["promotion_eligible"] != gate_row.eligible_for_primary_surface,
            metadata["primary_surface"] != derived_primary_surface,
            index_non_regressive != gate_row.non_regressive,
            index_eligible != gate_row.eligible_for_primary_surface,
            index_primary_surface != derived_primary_surface,
        )
    )
    if mismatch:
        diagnostics.append(
            Diagnostic(
                code="reference_family_parity_surface_mismatch",
                message="checked parity JSON, markdown metadata, and index row do not agree",
                severity="error",
                details={
                    "evidence_path": parity_report_json["record"].path,
                    "markdown_path": parity_report_markdown["record"].path,
                    "index_path": parity_index["record"].path,
                    "derived_primary_surface": derived_primary_surface,
                    "markdown_primary_surface": metadata["primary_surface"],
                    "index_primary_surface": index_primary_surface,
                    "related_surface_id": "migration_parity_surface",
                    "suggested_owner_lane": "reference-family conformance profile reconciliation",
                },
            )
        )
        return result

    result["status"] = "pass"
    return result


def _load_validated_parity_targets(
    *,
    parity_targets_path: Path,
    parity_targets: dict[str, object],
    diagnostics: list[Diagnostic],
) -> list[migration_parity.ParityTarget] | None:
    if parity_targets["record"].load_status != "loaded":
        return None
    try:
        return migration_parity.load_parity_targets(parity_targets_path)
    except ValueError as exc:
        diagnostics.append(
            Diagnostic(
                code="reference_family_conformance_input_invalid",
                message=f"required evidence input `parity_targets` is invalid: {exc}",
                severity="error",
                details={
                    "input_id": "parity_targets",
                    "evidence_path": parity_targets["record"].path,
                },
            )
        )
        return None


def _build_conformance_surfaces(
    *,
    workflow_family: str,
    checked_manifests: dict[str, dict[str, object]],
    owner_reports: dict[str, dict[str, object]],
    completed_gap_reconciliation: dict[str, object],
    parity_surface_reconciliation: dict[str, object],
    diagnostics: list[Diagnostic],
) -> list[dict[str, object]]:
    surfaces: list[dict[str, object]] = []

    for surface_id in SURFACE_IDS:
        failures: list[str] = []
        missing_evidence: list[str] = []
        evidence_paths: list[str] = []

        def require_manifest(input_id: str) -> bool:
            loaded = checked_manifests.get(input_id, {})
            record = loaded.get("record")
            if isinstance(record, EvidenceInput) and record.path:
                evidence_paths.append(record.path)
            if isinstance(record, EvidenceInput) and record.load_status == "loaded":
                return True
            missing_evidence.append(input_id)
            return False

        def require_owner_report(report_id: str) -> bool:
            report = owner_reports.get(report_id, {})
            record = report.get("record")
            payload = report.get("payload")
            if isinstance(record, EvidenceInput) and record.path:
                evidence_paths.append(record.path)
            if not isinstance(record, EvidenceInput):
                failures.append(report_id)
                return False
            if report_id == "boundary_authority_report":
                passed = (
                    record.load_status == "loaded"
                    and isinstance(payload, Mapping)
                    and payload.get("workflow_family") == workflow_family
                    and isinstance(payload.get("workflows"), list)
                    and bool(payload.get("workflows"))
                )
            else:
                passed = (
                    record.load_status == "loaded"
                    and isinstance(payload, Mapping)
                    and payload.get("status") == "pass"
                )
            if not passed:
                failures.append(report_id)
            return passed

        passed = False
        if surface_id == "parent_callable_orc_route":
            evidence_paths.extend(
                path
                for path in parity_surface_reconciliation.get("evidence_paths", [])
                if isinstance(path, str)
            )
            passed = parity_surface_reconciliation.get("status") == "pass"
        elif surface_id == "public_private_boundary":
            passed = require_manifest("boundary_authority") and require_owner_report(
                "boundary_authority_report"
            )
        elif surface_id == "hidden_compatibility_bridge_carriage":
            passed = require_manifest("compatibility_bridges") and require_owner_report(
                "compatibility_bridge_report"
            )
        elif surface_id == "hidden_compatibility_bridge_evidence_alignment":
            passed = require_manifest("resume_plumbing_retirement") and require_owner_report(
                "resume_plumbing_retirement_report"
            )
        elif surface_id == "observability_old_writer_retirement":
            passed = (
                require_manifest("observability_old_writer_comparisons")
                and require_owner_report("observability_summary_report")
                and require_owner_report("rendering_cleanup_report")
            )
        elif surface_id == "provider_inputs":
            passed = require_owner_report("typed_prompt_input_report")
        elif surface_id == "provider_write_targets":
            passed = require_owner_report("typed_prompt_input_report") and require_owner_report(
                "rendering_ergonomics_report"
            )
        elif surface_id == "body_renderings":
            passed = require_manifest("consumer_rendering_census") and require_owner_report(
                "rendering_cleanup_report"
            )
        elif surface_id == "compatibility_files":
            passed = require_manifest("compatibility_bridges") and require_owner_report(
                "compatibility_bridge_report"
            )
        elif surface_id == "deterministic_helpers":
            passed = require_manifest("command_boundaries")
            if passed and not _command_boundaries_are_certified(
                checked_manifests.get("command_boundaries", {}).get("payload")
            ):
                diagnostics.append(
                    Diagnostic(
                        code="reference_family_command_boundary_uncertified",
                        message="deterministic helper evidence includes uncertified command boundary rows",
                        severity="error",
                        details={
                            "related_surface_id": surface_id,
                            "suggested_owner_lane": "reference-family conformance profile reconciliation",
                        },
                    )
                )
                passed = False
                failures.append("command_boundaries")
        elif surface_id == "durable_state_changes":
            passed = require_manifest("transition_authoring") and require_owner_report(
                "transition_authoring_report"
            )
        elif surface_id == "source_shape_gate":
            passed = require_manifest("value_flow_census") and require_owner_report(
                "parent_drain_census_alignment_report"
            )
        elif surface_id == "completion_inventory":
            evidence_paths.extend(
                path
                for path in completed_gap_reconciliation.get("evidence_paths", [])
                if isinstance(path, str)
            )
            passed = completed_gap_reconciliation.get("status") == "pass"
        elif surface_id == "migration_parity_surface":
            evidence_paths.extend(
                path
                for path in parity_surface_reconciliation.get("evidence_paths", [])
                if isinstance(path, str)
            )
            passed = parity_surface_reconciliation.get("status") == "pass"

        if not passed:
            if missing_evidence:
                diagnostics.append(
                    Diagnostic(
                        code="reference_family_conformance_surface_missing",
                        message="required conformance surface evidence is missing",
                        severity="error",
                        details={
                            "related_surface_id": surface_id,
                            "missing_evidence_inputs": sorted(set(missing_evidence)),
                            "suggested_owner_lane": "reference-family conformance profile reconciliation",
                        },
                    )
                )
            elif surface_id not in {"completion_inventory", "migration_parity_surface"}:
                diagnostics.append(
                    Diagnostic(
                        code="reference_family_conformance_surface_failed",
                        message="required conformance surface evidence did not pass",
                        severity="error",
                        details={
                            "related_surface_id": surface_id,
                            "failed_evidence_inputs": sorted(set(failures)),
                            "suggested_owner_lane": "reference-family conformance profile reconciliation",
                        },
                    )
                )

        surfaces.append(
            {
                "surface_id": surface_id,
                "question": SURFACE_QUESTIONS[surface_id],
                "owner_lanes": list(SURFACE_OWNER_LANES[surface_id]),
                "status": "pass" if passed else "fail",
                "evidence_paths": sorted(
                    {
                        _normalize_surface_path(path)
                        for path in evidence_paths
                        if isinstance(path, str) and path
                    }
                ),
                "diagnostics": [
                    diag.code
                    for diag in diagnostics
                    if diag.details.get("related_surface_id") == surface_id
                ],
            }
        )

    return surfaces


def _command_boundaries_are_certified(payload: object) -> bool:
    if not isinstance(payload, Mapping):
        return False
    for row in payload.values():
        if not isinstance(row, Mapping):
            return False
        if not isinstance(row.get("stable_command"), list):
            return False
    return True


def _normalize_string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def _iso8601_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _sha256_bytes(payload: bytes) -> str:
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def _sha256_directory(path: Path, *, pattern: str) -> str:
    digest = hashlib.sha256()
    for child in sorted(path.glob(pattern)):
        if not child.is_file():
            continue
        digest.update(str(child.relative_to(path)).encode("utf-8"))
        digest.update(b"\0")
        digest.update(hashlib.sha256(child.read_bytes()).digest())
    return f"sha256:{digest.hexdigest()}"


def _relative_or_absolute_path(path: Path, repo_root: Path) -> str:
    try:
        return str(path.resolve().relative_to(repo_root.resolve()))
    except ValueError:
        return str(path)


def _normalize_surface_path(path: str) -> str:
    return str(Path(path))


def _evidence_input_to_json(item: EvidenceInput) -> dict[str, object]:
    return {
        "input_id": item.input_id,
        "input_kind": item.input_kind,
        "path": item.path,
        "load_status": item.load_status,
        "sha256": item.sha256,
        "details": dict(item.details),
    }


def _diagnostic_to_json(item: Diagnostic) -> dict[str, object]:
    return {
        "code": item.code,
        "message": item.message,
        "severity": item.severity,
        **dict(item.details),
    }


def _json_compatible(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_compatible(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_json_compatible(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    return value
