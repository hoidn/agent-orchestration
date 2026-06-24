"""Reference-family conformance profile aggregation for Design Delta evidence."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from . import migration_parity


SCHEMA_ID = "workflow_lisp_reference_family_conformance_profile.v1"
GOVERNING_SECTION_IDS = (
    "2.1 Reference-Family Conformance Profile",
    "13.3 Authoring Ergonomics Gate",
    "15. Success Criteria",
)
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
REQUIRED_TEXT_SECTION_HEADINGS = {
    "2.1 Reference-Family Conformance Profile": "### 2.1 Reference-Family Conformance Profile",
    "13.3 Authoring Ergonomics Gate": "### 13.3 Authoring Ergonomics Gate",
    "15. Success Criteria": "## 15. Success Criteria",
}


@dataclass(frozen=True)
class EvidenceInput:
    input_id: str
    input_kind: str
    path: str | None
    load_status: str
    sha256: str | None
    details: dict[str, object]


@dataclass(frozen=True)
class Diagnostic:
    code: str
    message: str
    details: dict[str, object]


def parse_parity_markdown_metadata(text: str) -> dict[str, object]:
    metadata: dict[str, object] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line.startswith("- Non-regressive: `") and line.endswith("`"):
            metadata["non_regressive"] = line.removeprefix("- Non-regressive: `").removesuffix("`") == "true"
        elif line.startswith("- Promotion eligible: `") and line.endswith("`"):
            metadata["promotion_eligible"] = (
                line.removeprefix("- Promotion eligible: `").removesuffix("`") == "true"
            )
        elif line.startswith("- Primary surface: `") and line.endswith("`"):
            metadata["primary_surface"] = line.removeprefix("- Primary surface: `").removesuffix("`")
    missing = sorted({"non_regressive", "promotion_eligible", "primary_surface"} - set(metadata))
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

    architecture_index = _load_text_input(
        evidence_inputs, "architecture_index", architecture_index_path
    )
    target_design = _load_text_input(evidence_inputs, "target_design", target_design_path)
    run_state = _load_json_input(evidence_inputs, "run_state", run_state_path)
    drain_summary = _load_json_input(evidence_inputs, "drain_summary", drain_summary_path)
    summary_inventory = _scan_summary_directory(
        evidence_inputs, "design_gap_summary_root", design_gap_summary_root
    )
    implementation_architectures = _scan_implementation_architectures(
        evidence_inputs,
        "implementation_architecture_root",
        implementation_architecture_root,
    )
    parity_targets = _load_json_input(evidence_inputs, "parity_targets", parity_targets_path)
    parity_report_json = _load_json_input(
        evidence_inputs, "parity_report_json", parity_report_json_path
    )
    parity_report_markdown = _load_text_input(
        evidence_inputs, "parity_report_markdown", parity_report_markdown_path
    )
    parity_index = _load_json_input(evidence_inputs, "parity_index", parity_index_path)
    checked_manifests = {
        input_id: _load_input_by_suffix(evidence_inputs, input_id, path)
        for input_id, path in sorted(checked_manifest_paths.items())
    }
    inline_owner_reports = {
        input_id: _record_inline_report_input(evidence_inputs, input_id, payload)
        for input_id, payload in sorted(owner_reports.items())
    }

    _require_loaded(
        diagnostics,
        architecture_index,
        message="reviewed architecture index is required for completed-gap discoverability",
    )
    _require_loaded(
        diagnostics,
        target_design,
        message="target design is required for governing source sections",
    )

    governing_sections = _extract_governing_sections(target_design, diagnostics)
    completed_gap_reconciliation = _reconcile_completed_gaps(
        run_state=run_state,
        drain_summary=drain_summary,
        summary_inventory=summary_inventory,
        implementation_architectures=implementation_architectures,
        architecture_index=architecture_index,
        repo_root=repo_root,
        diagnostics=diagnostics,
        governing_sections=governing_sections,
    )
    parity_surface_reconciliation = _reconcile_parity_surface(
        workflow_family=workflow_family,
        parity_targets_path=parity_targets_path,
        parity_report_json=parity_report_json,
        parity_report_markdown=parity_report_markdown,
        parity_index=parity_index,
        repo_root=repo_root,
        diagnostics=diagnostics,
        governing_sections=governing_sections,
    )
    surfaces = _build_surface_rows(
        workflow_family=workflow_family,
        checked_manifests=checked_manifests,
        owner_reports=inline_owner_reports,
        completed_gap_reconciliation=completed_gap_reconciliation,
        parity_surface_reconciliation=parity_surface_reconciliation,
        diagnostics=diagnostics,
    )
    profile_status = (
        "pass"
        if not diagnostics and all(row["status"] == "pass" for row in surfaces)
        else "fail"
    )
    return {
        "schema_id": SCHEMA_ID,
        "workflow_family": workflow_family,
        "profile_status": profile_status,
        "governing_source_sections": list(governing_sections),
        "evidence_inputs": [_evidence_input_to_json(item) for item in evidence_inputs],
        "completed_gap_reconciliation": completed_gap_reconciliation,
        "parity_surface_reconciliation": parity_surface_reconciliation,
        "surface_rows": surfaces,
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
        record = EvidenceInput(
            input_id=input_id,
            input_kind="json",
            path=str(path),
            load_status="invalid",
            sha256=_sha256_bytes(raw_bytes),
            details={"error": str(exc)},
        )
        payload = None
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
        record = EvidenceInput(
            input_id=input_id,
            input_kind="text",
            path=str(path),
            load_status="invalid",
            sha256=_sha256_bytes(raw_bytes),
            details={"error": str(exc)},
        )
        text = None
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
        return {"record": record, "files_by_gap_id": {}}
    files_by_gap_id = {
        file_path.name.removesuffix("-summary.json"): file_path
        for file_path in sorted(path.glob("*-summary.json"))
    }
    record = EvidenceInput(
        input_id=input_id,
        input_kind="directory",
        path=str(path),
        load_status="loaded",
        sha256=_sha256_directory(path, pattern="*-summary.json"),
        details={"file_count": len(files_by_gap_id)},
    )
    evidence_inputs.append(record)
    return {"record": record, "files_by_gap_id": files_by_gap_id}


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
    details: dict[str, object] = {"status": status}
    if load_status == "invalid":
        details["error"] = "inline owner report must include a string status"
    encoded = json.dumps(
        _json_compatible(payload), sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    record = EvidenceInput(
        input_id=input_id,
        input_kind="inline_report",
        path=str(payload.get("path")) if isinstance(payload.get("path"), str) else None,
        load_status=load_status,
        sha256=_sha256_bytes(encoded),
        details=details,
    )
    evidence_inputs.append(record)
    return {"record": record, "payload": payload}


def _extract_governing_sections(
    target_design: dict[str, object],
    diagnostics: list[Diagnostic],
) -> tuple[str, ...]:
    text = target_design.get("text")
    record = target_design["record"]
    if not isinstance(text, str):
        return ()
    found: list[str] = []
    for section_id, heading in REQUIRED_TEXT_SECTION_HEADINGS.items():
        if heading in text:
            found.append(section_id)
            continue
        diagnostics.append(
            Diagnostic(
                code="reference_family_target_design_section_missing",
                message=f"target design is missing governing section `{section_id}`",
                details={
                    "section_id": section_id,
                    "path": record.path,
                },
            )
        )
    return tuple(found)


def _reconcile_completed_gaps(
    *,
    run_state: dict[str, object],
    drain_summary: dict[str, object],
    summary_inventory: dict[str, object],
    implementation_architectures: dict[str, object],
    architecture_index: dict[str, object],
    repo_root: Path,
    diagnostics: list[Diagnostic],
    governing_sections: tuple[str, ...],
) -> dict[str, object]:
    run_state_payload = run_state.get("payload")
    drain_summary_payload = drain_summary.get("payload")
    if not isinstance(run_state_payload, dict) or not isinstance(drain_summary_payload, dict):
        return {
            "status": "fail",
            "run_state_completed_count": 0,
            "drain_summary_completed_count": 0,
            "missing_from_drain_summary": [],
            "extra_in_drain_summary": [],
            "ordered_list_matches": False,
            "missing_summary_artifacts": [],
            "missing_implementation_architectures": [],
            "missing_from_architecture_index": [],
        }
    run_completed = [
        str(item) for item in run_state_payload.get("completed_design_gaps", []) if isinstance(item, str)
    ]
    summary_completed = [
        str(item)
        for item in drain_summary_payload.get("completed_design_gaps", [])
        if isinstance(item, str)
    ]
    missing_from_summary = sorted(set(run_completed) - set(summary_completed))
    extra_in_summary = sorted(set(summary_completed) - set(run_completed))
    ordered_list_matches = run_completed == summary_completed
    if missing_from_summary or extra_in_summary or not ordered_list_matches:
        diagnostics.append(
            Diagnostic(
                code="reference_family_completed_gap_summary_mismatch",
                message="drain summary completed-gap inventory does not match run state",
                details={
                    "missing_gap_ids": missing_from_summary,
                    "extra_gap_ids": extra_in_summary,
                    "ordered_list_matches": ordered_list_matches,
                    "governing_sections": list(governing_sections),
                },
            )
        )
    summary_files = summary_inventory.get("files_by_gap_id", {})
    missing_summary_artifacts = sorted(
        gap_id for gap_id in run_completed if gap_id not in summary_files
    )
    if missing_summary_artifacts:
        diagnostics.append(
            Diagnostic(
                code="reference_family_completed_gap_artifact_missing",
                message="one or more completed gaps are missing checked summary artifacts",
                details={
                    "missing_gap_ids": missing_summary_artifacts,
                    "governing_sections": list(governing_sections),
                },
            )
        )
    implementation_paths = implementation_architectures.get("paths_by_gap_id", {})
    missing_implementation_architectures = sorted(
        gap_id
        for gap_id in run_completed
        if not isinstance(implementation_paths.get(gap_id), Path)
        or not implementation_paths[gap_id].is_file()
    )
    if missing_implementation_architectures:
        diagnostics.append(
            Diagnostic(
                code="reference_family_completed_gap_implementation_architecture_missing",
                message="one or more completed gaps are missing implementation architecture files",
                details={
                    "missing_gap_ids": missing_implementation_architectures,
                    "governing_sections": list(governing_sections),
                },
            )
        )
    architecture_index_text = architecture_index.get("text")
    missing_from_architecture_index: list[str] = []
    if isinstance(architecture_index_text, str):
        for gap_id in run_completed:
            expected_path = implementation_paths.get(gap_id)
            if isinstance(expected_path, Path):
                try:
                    relpath = str(expected_path.resolve().relative_to(repo_root.resolve()))
                except ValueError:
                    relpath = gap_id
            else:
                relpath = gap_id
            if relpath not in architecture_index_text and gap_id not in architecture_index_text:
                missing_from_architecture_index.append(gap_id)
    if missing_from_architecture_index:
        diagnostics.append(
            Diagnostic(
                code="reference_family_completed_gap_architecture_index_missing",
                message="reviewed architecture index does not list every completed gap architecture",
                details={
                    "missing_gap_ids": missing_from_architecture_index,
                    "governing_sections": list(governing_sections),
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
            or missing_implementation_architectures
            or missing_from_architecture_index
        )
        else "fail"
    )
    return {
        "status": status,
        "run_state_completed_count": len(run_completed),
        "drain_summary_completed_count": len(summary_completed),
        "missing_from_drain_summary": missing_from_summary,
        "extra_in_drain_summary": extra_in_summary,
        "ordered_list_matches": ordered_list_matches,
        "missing_summary_artifacts": missing_summary_artifacts,
        "missing_implementation_architectures": missing_implementation_architectures,
        "missing_from_architecture_index": missing_from_architecture_index,
    }


def _reconcile_parity_surface(
    *,
    workflow_family: str,
    parity_targets_path: Path,
    parity_report_json: dict[str, object],
    parity_report_markdown: dict[str, object],
    parity_index: dict[str, object],
    repo_root: Path,
    diagnostics: list[Diagnostic],
    governing_sections: tuple[str, ...],
) -> dict[str, object]:
    report_payload = parity_report_json.get("payload")
    parity_index_payload = parity_index.get("payload")
    if not isinstance(report_payload, dict):
        diagnostics.append(
            Diagnostic(
                code="reference_family_parity_report_invalid",
                message="checked parity JSON report is missing or invalid",
                details={"governing_sections": list(governing_sections)},
            )
        )
        return {
            "status": "fail",
            "non_regressive": None,
            "eligible_for_primary_surface": None,
            "derived_primary_surface": None,
            "markdown_primary_surface": None,
            "index_primary_surface": None,
        }
    try:
        targets = migration_parity.load_parity_targets(parity_targets_path)
        target = next(item for item in targets if item.workflow_family == workflow_family)
        gate_row = migration_parity.validate_report_for_target(
            report_payload,
            target=target,
            targets_file=parity_targets_path,
            repo_root=repo_root,
            today=date.today(),
        )
        non_regressive = gate_row.non_regressive
        eligible_for_primary_surface = gate_row.eligible_for_primary_surface
        derived_primary_surface = gate_row.primary_surface
    except (StopIteration, ValueError) as exc:
        diagnostics.append(
            Diagnostic(
                code="reference_family_parity_report_invalid",
                message=f"checked parity JSON report is invalid: {exc}",
                details={"governing_sections": list(governing_sections)},
            )
        )
        return {
            "status": "fail",
            "non_regressive": None,
            "eligible_for_primary_surface": None,
            "derived_primary_surface": None,
            "markdown_primary_surface": None,
            "index_primary_surface": None,
        }
    markdown_primary_surface = None
    markdown_non_regressive = None
    markdown_promotion_eligible = None
    markdown_text = parity_report_markdown.get("text")
    if isinstance(markdown_text, str):
        try:
            metadata = parse_parity_markdown_metadata(markdown_text)
        except ValueError as exc:
            diagnostics.append(
                Diagnostic(
                    code="reference_family_parity_report_invalid",
                    message=f"checked parity markdown metadata is invalid: {exc}",
                    details={"governing_sections": list(governing_sections)},
                )
            )
            return {
                "status": "fail",
                "non_regressive": None,
                "eligible_for_primary_surface": None,
                "derived_primary_surface": None,
                "markdown_primary_surface": None,
                "index_primary_surface": None,
            }
        markdown_primary_surface = metadata["primary_surface"]
        markdown_non_regressive = metadata["non_regressive"]
        markdown_promotion_eligible = metadata["promotion_eligible"]
    index_primary_surface = None
    index_non_regressive = None
    index_promotion_eligible = None
    if isinstance(parity_index_payload, dict):
        for row in parity_index_payload.get("targets", []):
            if not isinstance(row, dict) or row.get("workflow_family") != workflow_family:
                continue
            index_primary_surface = row.get("primary_surface")
            index_non_regressive = row.get("non_regressive")
            promotion = row.get("promotion_eligibility")
            if isinstance(promotion, dict):
                index_promotion_eligible = promotion.get("eligible_for_primary_surface")
            break
    mismatch = (
        markdown_primary_surface != derived_primary_surface
        or markdown_non_regressive != non_regressive
        or markdown_promotion_eligible != eligible_for_primary_surface
        or index_primary_surface != derived_primary_surface
        or index_non_regressive != non_regressive
        or index_promotion_eligible != eligible_for_primary_surface
    )
    if mismatch:
        diagnostics.append(
            Diagnostic(
                code="reference_family_parity_surface_mismatch",
                message="checked parity JSON, markdown metadata, and index row do not agree",
                details={
                    "derived_primary_surface": derived_primary_surface,
                    "markdown_primary_surface": markdown_primary_surface,
                    "index_primary_surface": index_primary_surface,
                    "governing_sections": list(governing_sections),
                },
            )
        )
    return {
        "status": "pass" if not mismatch else "fail",
        "non_regressive": non_regressive,
        "eligible_for_primary_surface": eligible_for_primary_surface,
        "derived_primary_surface": derived_primary_surface,
        "markdown_primary_surface": markdown_primary_surface,
        "index_primary_surface": index_primary_surface,
    }


def _build_surface_rows(
    *,
    workflow_family: str,
    checked_manifests: dict[str, dict[str, object]],
    owner_reports: dict[str, dict[str, object]],
    completed_gap_reconciliation: dict[str, object],
    parity_surface_reconciliation: dict[str, object],
    diagnostics: list[Diagnostic],
) -> list[dict[str, object]]:
    def owner_status(report_id: str) -> bool:
        report = owner_reports.get(report_id, {})
        payload = report.get("payload")
        record = report.get("record")
        if report_id == "boundary_authority_report":
            return (
                isinstance(record, EvidenceInput)
                and record.load_status == "loaded"
                and isinstance(payload, dict)
                and payload.get("workflow_family") == workflow_family
                and isinstance(payload.get("workflows"), list)
                and bool(payload.get("workflows"))
            )
        return (
            isinstance(record, EvidenceInput)
            and record.load_status == "loaded"
            and isinstance(payload, dict)
            and payload.get("status") == "pass"
        )

    def manifest_loaded(input_id: str) -> bool:
        record = checked_manifests.get(input_id, {}).get("record")
        return isinstance(record, EvidenceInput) and record.load_status == "loaded"

    surfaces: list[dict[str, object]] = []
    for surface_id in SURFACE_IDS:
        status = "fail"
        if surface_id == "parent_callable_orc_route":
            status = "pass" if parity_surface_reconciliation["status"] == "pass" else "fail"
        elif surface_id == "public_private_boundary":
            status = "pass" if manifest_loaded("boundary_authority_manifest") and owner_status("boundary_authority_report") else "fail"
        elif surface_id == "hidden_compatibility_bridge_carriage":
            status = "pass" if manifest_loaded("compatibility_bridges_manifest") and owner_status("compatibility_bridge_report") else "fail"
        elif surface_id == "hidden_compatibility_bridge_evidence_alignment":
            status = "pass" if manifest_loaded("resume_plumbing_retirement_manifest") and owner_status("resume_plumbing_retirement_report") else "fail"
        elif surface_id == "observability_old_writer_retirement":
            status = "pass" if manifest_loaded("observability_old_writer_comparisons") and owner_status("observability_summary_report") and owner_status("rendering_cleanup_report") else "fail"
        elif surface_id == "provider_inputs":
            status = "pass" if owner_status("typed_prompt_input_report") else "fail"
        elif surface_id == "provider_write_targets":
            status = "pass" if owner_status("typed_prompt_input_report") and owner_status("rendering_ergonomics_report") else "fail"
        elif surface_id == "body_renderings":
            status = "pass" if manifest_loaded("consumer_rendering_census") and owner_status("rendering_cleanup_report") else "fail"
        elif surface_id == "compatibility_files":
            status = "pass" if owner_status("compatibility_bridge_report") else "fail"
        elif surface_id == "deterministic_helpers":
            status = "pass" if manifest_loaded("command_boundaries_manifest") else "fail"
        elif surface_id == "durable_state_changes":
            status = "pass" if owner_status("transition_authoring_report") else "fail"
        elif surface_id == "source_shape_gate":
            status = "pass" if owner_status("parent_drain_census_alignment_report") else "fail"
        elif surface_id == "completion_inventory":
            status = str(completed_gap_reconciliation.get("status", "fail"))
        elif surface_id == "migration_parity_surface":
            status = str(parity_surface_reconciliation.get("status", "fail"))
        surfaces.append(
            {
                "surface_id": surface_id,
                "workflow_family": workflow_family,
                "status": status,
            }
        )
    if any(row["status"] == "fail" for row in surfaces) and not diagnostics:
        diagnostics.append(
            Diagnostic(
                code="reference_family_surface_incomplete",
                message="one or more conformance surfaces are missing required evidence inputs or passing owner-lane status",
                details={"failed_surface_ids": [row["surface_id"] for row in surfaces if row["status"] == "fail"]},
            )
        )
    return surfaces


def _require_loaded(
    diagnostics: list[Diagnostic],
    loaded_input: dict[str, object],
    *,
    message: str,
) -> None:
    record = loaded_input["record"]
    if record.load_status == "loaded":
        return
    diagnostics.append(
        Diagnostic(
            code="reference_family_evidence_input_missing",
            message=message,
            details={
                "input_id": record.input_id,
                "path": record.path,
            },
        )
    )


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
        **dict(item.details),
    }


def _json_compatible(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_compatible(item) for key, item in value.items()}
    if hasattr(value, "items"):
        return {
            str(key): _json_compatible(item) for key, item in value.items()
        }
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_json_compatible(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    return value
