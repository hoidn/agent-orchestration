"""Validate whether a canonical phase bundle can be reused."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

from orchestrator.contracts.output_contract import (
    OutputContractError,
    validate_output_bundle,
    validate_variant_output_bundle,
)


HARD_FAILURE_CODES = {
    "resume_state_path_unsafe",
    "resume_state_pointer_authority_forbidden",
    "resume_state_contract_fingerprint_mismatch",
    "resume_state_bundle_schema_invalid",
    "resume_state_required_artifact_missing",
    "resume_state_contract_invalid",
}


def _load_payload(argv: list[str]) -> dict[str, object]:
    if len(argv) > 1:
        try:
            candidate = Path(argv[1])
            if candidate.is_file():
                return json.loads(candidate.read_text(encoding="utf-8"))
        except OSError:
            pass
        return json.loads(argv[1])
    raw = sys.stdin.read().strip()
    if not raw:
        return {}
    return json.loads(raw)


def _workspace_relpath(path_value: object) -> str:
    if not isinstance(path_value, str) or not path_value:
        raise ValueError("resume_state_contract_invalid")
    path = Path(path_value)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError("resume_state_path_unsafe")
    return path_value


def _load_bundle(bundle_path: Path) -> dict[str, object]:
    try:
        bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        if error.pos == 0:
            raise ValueError("resume_state_pointer_authority_forbidden") from error
        raise ValueError("resume_state_bundle_schema_invalid") from error
    if isinstance(bundle, str):
        raise ValueError("resume_state_pointer_authority_forbidden")
    if not isinstance(bundle, dict):
        raise ValueError("resume_state_bundle_schema_invalid")
    return bundle


def _structured_contract_payload(
    payload: dict[str, object],
) -> tuple[str, str, str, dict[str, object], str]:
    target_dsl_version = payload.get("target_dsl_version")
    return_type_name = payload.get("return_type_name")
    structured_contract_kind = payload.get("structured_contract_kind")
    structured_contract = payload.get("structured_contract")
    expected_contract_fingerprint = payload.get("expected_contract_fingerprint")
    if (
        not isinstance(target_dsl_version, str)
        or not target_dsl_version
        or not isinstance(return_type_name, str)
        or not return_type_name
        or structured_contract_kind not in {"record", "union"}
        or not isinstance(structured_contract, dict)
        or not isinstance(expected_contract_fingerprint, str)
        or not expected_contract_fingerprint
    ):
        raise ValueError("resume_state_contract_invalid")
    return (
        target_dsl_version,
        return_type_name,
        str(structured_contract_kind),
        structured_contract,
        expected_contract_fingerprint,
    )


def _validate_contract_fingerprint(
    *,
    target_dsl_version: str,
    return_type_name: str,
    structured_contract_kind: str,
    structured_contract: dict[str, object],
    expected_contract_fingerprint: str,
) -> None:
    parts = expected_contract_fingerprint.split(":", 3)
    if (
        len(parts) != 4
        or parts[0] != target_dsl_version
        or parts[1] != return_type_name
        or parts[2] != structured_contract_kind
    ):
        raise ValueError("resume_state_contract_fingerprint_mismatch")
    digest = hashlib.sha256(
        json.dumps(
            structured_contract,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    if parts[3] != digest:
        raise ValueError("resume_state_contract_fingerprint_mismatch")


def _validate_bundle_against_contract(
    *,
    bundle_path: Path,
    structured_contract_kind: str,
    structured_contract: dict[str, object],
) -> dict[str, object]:
    runtime_contract = {
        "path": bundle_path.as_posix(),
        **_relax_contract_artifact_existence(structured_contract_kind, structured_contract),
    }
    try:
        if structured_contract_kind == "record":
            return validate_output_bundle(runtime_contract, workspace=Path.cwd())
        return validate_variant_output_bundle(runtime_contract, workspace=Path.cwd())
    except OutputContractError as error:
        violation_types = {violation["type"] for violation in error.violations}
        if violation_types & {"path_escape", "outside_under_root", "invalid_under_root"}:
            raise ValueError("resume_state_path_unsafe") from error
        raise ValueError("resume_state_bundle_schema_invalid") from error


def _relax_contract_artifact_existence(
    structured_contract_kind: str,
    structured_contract: dict[str, object],
) -> dict[str, object]:
    relaxed = json.loads(json.dumps(structured_contract))
    if structured_contract_kind == "record":
        _relax_field_specs(relaxed.get("fields"))
        return relaxed

    _relax_field_specs(relaxed.get("shared_fields"))
    variants = relaxed.get("variants")
    if isinstance(variants, dict):
        for variant_spec in variants.values():
            if isinstance(variant_spec, dict):
                _relax_field_specs(variant_spec.get("fields"))
    return relaxed


def _relax_field_specs(field_specs: object) -> None:
    if not isinstance(field_specs, list):
        return
    for spec in field_specs:
        if isinstance(spec, dict) and spec.get("type") == "relpath":
            spec["must_exist_target"] = False


def _load_artifact_requirements(
    payload: dict[str, object],
) -> dict[str, tuple[tuple[tuple[str, ...], str], ...]]:
    raw_requirements = payload.get("artifact_requirements", {})
    if not isinstance(raw_requirements, dict):
        raise ValueError("resume_state_contract_invalid")
    requirements: dict[str, tuple[tuple[tuple[str, ...], str], ...]] = {}
    for key, entries in raw_requirements.items():
        if not isinstance(key, str) or not isinstance(entries, list):
            raise ValueError("resume_state_contract_invalid")
        parsed_entries: list[tuple[tuple[str, ...], str]] = []
        for entry in entries:
            if not isinstance(entry, dict):
                raise ValueError("resume_state_contract_invalid")
            field_path = entry.get("field_path")
            under = entry.get("under")
            if (
                not isinstance(field_path, list)
                or not field_path
                or any(not isinstance(part, str) or not part for part in field_path)
                or not isinstance(under, str)
                or not under
            ):
                raise ValueError("resume_state_contract_invalid")
            parsed_entries.append((tuple(field_path), under))
        requirements[key] = tuple(parsed_entries)
    return requirements


def _lookup_field_path(bundle: dict[str, object], field_path: tuple[str, ...]) -> object:
    current: object = bundle
    for part in field_path:
        if not isinstance(current, dict) or part not in current:
            raise ValueError("resume_state_bundle_schema_invalid")
        current = current[part]
    return current


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _validate_required_artifacts(
    *,
    bundle: dict[str, object],
    requirements: tuple[tuple[tuple[str, ...], str], ...],
) -> None:
    workspace = Path.cwd().resolve()
    for field_path, under in requirements:
        raw_value = _lookup_field_path(bundle, field_path)
        relpath = _workspace_relpath(raw_value)
        target = (workspace / relpath).resolve()
        if not _is_within(target, workspace):
            raise ValueError("resume_state_path_unsafe")
        under_root = (workspace / under).resolve()
        if not _is_within(under_root, workspace) or not _is_within(target, under_root):
            raise ValueError("resume_state_path_unsafe")
        if not target.exists():
            raise ValueError("resume_state_required_artifact_missing")


def _bundle_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main(argv: list[str] | None = None) -> int:
    """Validate whether a prior canonical phase bundle may be reused."""

    args = argv or sys.argv
    try:
        payload = _load_payload(args)
        resume_from = _workspace_relpath(payload.get("resume_from"))
        (
            target_dsl_version,
            return_type_name,
            structured_contract_kind,
            structured_contract,
            expected_contract_fingerprint,
        ) = _structured_contract_payload(payload)
        artifact_requirements = _load_artifact_requirements(payload)
        reusable_variants = {
            variant for variant in payload.get("reusable_variants", []) if isinstance(variant, str)
        }
        bundle_path = Path(resume_from)
        if not bundle_path.exists():
            json.dump({"variant": "START", "reason_code": "MISSING_BUNDLE"}, sys.stdout)
            sys.stdout.write("\n")
            return 0
        bundle = _load_bundle(bundle_path)
        _validate_contract_fingerprint(
            target_dsl_version=target_dsl_version,
            return_type_name=return_type_name,
            structured_contract_kind=structured_contract_kind,
            structured_contract=structured_contract,
            expected_contract_fingerprint=expected_contract_fingerprint,
        )
        _validate_bundle_against_contract(
            bundle_path=bundle_path,
            structured_contract_kind=structured_contract_kind,
            structured_contract=structured_contract,
        )
        matched_variant = None
        selected_requirements: tuple[tuple[tuple[str, ...], str], ...] = ()
        if structured_contract_kind == "union":
            variant = bundle.get("variant")
            if not isinstance(variant, str):
                raise ValueError("resume_state_bundle_schema_invalid")
            matched_variant = variant
            if variant not in reusable_variants:
                json.dump({"variant": "START", "reason_code": "VARIANT_NOT_REUSABLE"}, sys.stdout)
                sys.stdout.write("\n")
                return 0
            selected_requirements = artifact_requirements.get(variant, ())
        else:
            selected_requirements = artifact_requirements.get(return_type_name, ())
        _validate_required_artifacts(
            bundle=bundle,
            requirements=selected_requirements,
        )
        result: dict[str, Any] = {
            "variant": "REUSE",
            "source_bundle_path": resume_from,
            "source_bundle_sha256": _bundle_sha256(bundle_path),
        }
        if matched_variant is not None:
            result["matched_variant"] = matched_variant
        json.dump(result, sys.stdout)
        sys.stdout.write("\n")
        return 0
    except ValueError as error:
        code = str(error)
        if code in HARD_FAILURE_CODES:
            json.dump({"error": {"type": code}}, sys.stdout)
            sys.stdout.write("\n")
            return 1
        raise


if __name__ == "__main__":
    raise SystemExit(main())
