"""Validate whether a canonical phase bundle can be reused via sidecar summary."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

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


HARD_FAILURE_CODES = {
    "resume_state_path_unsafe",
    "resume_state_pointer_authority_forbidden",
    "resume_state_contract_fingerprint_mismatch",
    "resume_state_bundle_schema_invalid",
    "resume_state_contract_invalid",
}


def _emit_variant(variant: str, **fields: Any) -> int:
    return emit_structured_result({"variant": variant, **fields})


def _load_summary(summary_path: Path) -> dict[str, object] | None:
    try:
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    if isinstance(summary, dict):
        return summary
    return None


def _summary_variant(
    summary: dict[str, object],
    *,
    expected_schema: str,
    expected_summary_version: str,
    expected_dsl_version: str,
) -> str | None:
    schema = summary.get("schema")
    if not isinstance(schema, str) or not schema:
        return "SCHEMA_MISMATCH"
    if schema != expected_schema:
        if schema.startswith("ReusablePhaseState."):
            return "UNSUPPORTED_VERSION"
        return "SCHEMA_MISMATCH"
    summary_version = summary.get("summary_version")
    if not isinstance(summary_version, str) or not summary_version:
        return "SCHEMA_MISMATCH"
    if summary_version != expected_summary_version:
        return "UNSUPPORTED_VERSION"
    compatibility = summary.get("compatibility")
    if not isinstance(compatibility, dict):
        return "SCHEMA_MISMATCH"
    dsl_version = compatibility.get("dsl_version")
    state_schema_version = compatibility.get("state_schema_version")
    if (
        not isinstance(dsl_version, str)
        or not dsl_version
        or not isinstance(state_schema_version, str)
        or not state_schema_version
    ):
        return "SCHEMA_MISMATCH"
    if dsl_version != expected_dsl_version or state_schema_version != expected_summary_version:
        return "UNSUPPORTED_VERSION"
    return None


def main(argv: list[str] | None = None) -> int:
    """Validate whether a prior canonical phase bundle may be reused."""

    args = argv or sys.argv
    try:
        payload = load_payload(args)
        resume_from = workspace_relpath(payload.get("resume_from"))
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
        artifact_requirements = load_artifact_requirements(payload)
        reusable_variants = {
            variant for variant in payload.get("reusable_variants", []) if isinstance(variant, str)
        }
        sidecar_suffix = payload.get("sidecar_suffix")
        summary_schema = payload.get("summary_schema")
        summary_version = payload.get("summary_version")
        canonical_bundle_digest_field = payload.get("canonical_bundle_digest_field")
        if (
            not isinstance(sidecar_suffix, str)
            or not sidecar_suffix
            or not isinstance(summary_schema, str)
            or not summary_schema
            or not isinstance(summary_version, str)
            or not summary_version
            or not isinstance(canonical_bundle_digest_field, str)
            or not canonical_bundle_digest_field
        ):
            raise ValueError("resume_state_contract_invalid")
        bundle_path = Path(resume_from)
        summary_relpath = reusable_state_sidecar_path(resume_from, sidecar_suffix)
        summary_path = Path(summary_relpath)
        if not bundle_path.exists() and not summary_path.exists():
            return _emit_variant("START")
        if not bundle_path.exists() or not summary_path.exists():
            return _emit_variant("FAILED_PRIOR_STATE")
        bundle = load_bundle(bundle_path)
        validate_bundle_against_contract(
            bundle_path=bundle_path,
            structured_contract_kind=structured_contract_kind,
            structured_contract=structured_contract,
        )
        summary = _load_summary(summary_path)
        if summary is None:
            return _emit_variant("SCHEMA_MISMATCH")
        summary_result = _summary_variant(
            summary,
            expected_schema=summary_schema,
            expected_summary_version=summary_version,
            expected_dsl_version=target_dsl_version,
        )
        if summary_result is not None:
            return _emit_variant(summary_result)
        matched_variant, requirements, reusable_terminal = selected_requirements(
            bundle=bundle,
            structured_contract_kind=structured_contract_kind,
            return_type_name=return_type_name,
            reusable_variants=reusable_variants,
            artifact_requirements=artifact_requirements,
        )
        if not reusable_terminal:
            return _emit_variant("FAILED_PRIOR_STATE")
        if summary.get("result_type") != return_type_name:
            return _emit_variant("STALE")
        if summary.get("workflow_checksum") != expected_contract_fingerprint:
            return _emit_variant("STALE")
        if summary.get(canonical_bundle_digest_field) != sha256_path(bundle_path):
            return _emit_variant("STALE")
        if summary.get("source_inputs_hash") != current_public_input_hash(payload):
            return _emit_variant("STALE")
        if summary.get("producer_fingerprint") != current_producer_fingerprint(payload):
            return _emit_variant("STALE")
        terminal = summary.get("terminal")
        if not isinstance(terminal, dict) or terminal.get("variant") != (matched_variant or return_type_name):
            return _emit_variant("STALE")
        summary_artifact_refs = summary.get("artifact_refs")
        if not isinstance(summary_artifact_refs, list):
            return _emit_variant("SCHEMA_MISMATCH")
        current_artifact_refs = build_artifact_refs(bundle=bundle, requirements=requirements)
        for index, current_ref in enumerate(current_artifact_refs):
            if index >= len(summary_artifact_refs):
                return _emit_variant("SCHEMA_MISMATCH")
            summary_ref = summary_artifact_refs[index]
            if not isinstance(summary_ref, dict):
                return _emit_variant("SCHEMA_MISMATCH")
            if summary_ref.get("relpath") != current_ref["relpath"] or summary_ref.get("under") != current_ref["under"]:
                return _emit_variant("STALE")
            if summary_ref.get("sha256") != current_ref["sha256"]:
                target = Path(current_ref["relpath"])
                if not target.exists():
                    return _emit_variant("MISSING_ARTIFACT")
                return _emit_variant("STALE")
        if len(summary_artifact_refs) != len(current_artifact_refs):
            return _emit_variant("SCHEMA_MISMATCH")
        result: dict[str, Any] = {
            "variant": "REUSABLE",
            "source_bundle_path": resume_from,
            "source_bundle_sha256": sha256_path(bundle_path),
        }
        if matched_variant is not None:
            result["matched_variant"] = matched_variant
        return emit_structured_result(result)
    except ValueError as error:
        code = str(error)
        if code == "resume_state_required_artifact_missing":
            return _emit_variant("MISSING_ARTIFACT")
        if code in HARD_FAILURE_CODES:
            return emit_error(code)
        raise


if __name__ == "__main__":
    raise SystemExit(main())
