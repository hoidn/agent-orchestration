"""Write a derived `ReusablePhaseState.v1` sidecar next to a canonical bundle."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from orchestrator.workflow_lisp.contracts import derive_reusable_phase_state_compatibility

from .reusable_phase_state_common import (
    build_artifact_refs,
    current_producer_fingerprint,
    current_public_input_hash,
    emit_error,
    emit_structured_result,
    load_artifact_requirements,
    load_bundle,
    load_payload,
    reusable_state_sidecar_path,
    selected_requirements,
    sha256_path,
    structured_contract_payload,
    validate_bundle_against_contract,
    validate_contract_fingerprint,
    workspace_relpath,
)


def _emit_ack(*, bundle_path: str, summary_path: str, schema: str) -> int:
    return emit_structured_result(
        {
            "status": "OK",
            "bundle_path": bundle_path,
            "summary_path": summary_path,
            "schema": schema,
        }
    )


def main(argv: list[str] | None = None) -> int:
    """Write the reusable-state sidecar for one canonical bundle."""

    args = argv or sys.argv
    try:
        payload = load_payload(args)
        bundle_relpath = workspace_relpath(payload.get("bundle_path"))
        bundle_path = Path(bundle_relpath)
        if not bundle_path.exists():
            return emit_error("resume_state_bundle_schema_invalid")
        (
            target_dsl_version,
            return_type_name,
            structured_contract_kind,
            structured_contract,
            expected_contract_fingerprint,
        ) = structured_contract_payload(payload)
        validate_contract_fingerprint(
            target_dsl_version=target_dsl_version,
            return_type_name=return_type_name,
            structured_contract_kind=structured_contract_kind,
            structured_contract=structured_contract,
            expected_contract_fingerprint=expected_contract_fingerprint,
        )
        bundle = load_bundle(bundle_path)
        validate_bundle_against_contract(
            bundle_path=bundle_path,
            structured_contract_kind=structured_contract_kind,
            structured_contract=structured_contract,
        )
        artifact_requirements = load_artifact_requirements(payload)
        reusable_variants = {
            variant for variant in payload.get("reusable_variants", []) if isinstance(variant, str)
        }
        matched_variant, requirements, reusable_terminal = selected_requirements(
            bundle=bundle,
            structured_contract_kind=structured_contract_kind,
            return_type_name=return_type_name,
            reusable_variants=reusable_variants,
            artifact_requirements=artifact_requirements,
        )
        artifact_refs = build_artifact_refs(bundle=bundle, requirements=requirements)
        summary_schema = payload.get("summary_schema")
        summary_version = payload.get("summary_version")
        if (
            not isinstance(summary_schema, str)
            or not summary_schema
            or not isinstance(summary_version, str)
            or not summary_version
        ):
            raise ValueError("resume_state_contract_invalid")
        source_run_id = payload.get("source_run_id")
        source_step_id = payload.get("source_step_id")
        source_call_frame_id = payload.get("source_call_frame_id")
        phase_id = payload.get("phase_id")
        created_at = payload.get("created_at")
        if not all(isinstance(value, str) and value for value in (source_run_id, source_step_id, source_call_frame_id, phase_id, created_at)):
            raise ValueError("resume_state_contract_invalid")
        producer_fingerprint_basis = payload.get("producer_fingerprint_basis")
        if not isinstance(producer_fingerprint_basis, dict):
            raise ValueError("resume_state_contract_invalid")
        sidecar_suffix = payload.get("sidecar_suffix")
        if not isinstance(sidecar_suffix, str) or not sidecar_suffix:
            raise ValueError("resume_state_contract_invalid")
        canonical_bundle_digest_field = payload.get("canonical_bundle_digest_field")
        if not isinstance(canonical_bundle_digest_field, str) or not canonical_bundle_digest_field:
            raise ValueError("resume_state_contract_invalid")
        compatibility = {
            **derive_reusable_phase_state_compatibility(
                target_dsl_version=target_dsl_version,
                summary_version=summary_version,
            ),
            "reusable": reusable_terminal,
            "status": "REUSABLE" if reusable_terminal else "FAILED_PRIOR_STATE",
        }
        summary = {
            "schema": summary_schema,
            "summary_version": summary_version,
            "source_run_id": source_run_id,
            "source_step_id": source_step_id,
            "source_call_frame_id": source_call_frame_id,
            "workflow_checksum": expected_contract_fingerprint,
            "phase_id": phase_id,
            "producer_workflow": producer_fingerprint_basis.get("workflow_name", ""),
            "producer_compiler": producer_fingerprint_basis.get("compiler_version", ""),
            "terminal": {
                "variant": matched_variant or return_type_name,
                "reusable": reusable_terminal,
            },
            "source_inputs_hash": current_public_input_hash(payload),
            "producer_fingerprint": current_producer_fingerprint(payload),
            "result_type": return_type_name,
            "artifact_refs": artifact_refs,
            "created_at": created_at,
            "compatibility": compatibility,
            canonical_bundle_digest_field: sha256_path(bundle_path),
        }
        summary_relpath = reusable_state_sidecar_path(bundle_relpath, sidecar_suffix)
        summary_path = Path(summary_relpath)
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = summary_path.with_suffix(summary_path.suffix + ".tmp")
        temp_path.write_text(json.dumps(summary, sort_keys=True), encoding="utf-8")
        temp_path.replace(summary_path)
        return _emit_ack(bundle_path=bundle_relpath, summary_path=summary_relpath, schema=summary_schema)
    except ValueError as error:
        return emit_error(str(error))


if __name__ == "__main__":
    raise SystemExit(main())
