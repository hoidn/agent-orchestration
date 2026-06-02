"""Shared helpers for reusable phase-state writer and validator adapters."""

from __future__ import annotations

import hashlib
import json
import os
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from orchestrator.contracts.output_contract import (
    OutputContractError,
    validate_output_bundle,
    validate_variant_output_bundle,
)


def emit_error(error_type: str) -> int:
    json.dump({"error": {"type": error_type}}, sys.stdout)
    sys.stdout.write("\n")
    return 1


def emit_structured_result(payload: Mapping[str, object]) -> int:
    """Emit structured adapter output to the runtime-owned bundle path when set."""

    bundle_path_raw = os.environ.get("ORCHESTRATOR_OUTPUT_BUNDLE_PATH", "").strip()
    if bundle_path_raw:
        bundle_relpath = workspace_relpath(bundle_path_raw)
        bundle_path = Path(bundle_relpath)
        bundle_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = bundle_path.with_suffix(bundle_path.suffix + ".tmp")
        temp_path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
        temp_path.replace(bundle_path)
    json.dump(payload, sys.stdout)
    sys.stdout.write("\n")
    return 0


def load_payload(argv: list[str]) -> dict[str, object]:
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


def workspace_relpath(path_value: object) -> str:
    if not isinstance(path_value, str) or not path_value:
        raise ValueError("resume_state_contract_invalid")
    path = Path(path_value)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError("resume_state_path_unsafe")
    return path_value


def reusable_state_sidecar_path(bundle_relpath: str, sidecar_suffix: str) -> str:
    path = Path(bundle_relpath)
    if path.suffix:
        return path.with_suffix("").as_posix() + sidecar_suffix
    return path.as_posix() + sidecar_suffix


def load_bundle(bundle_path: Path) -> dict[str, object]:
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


def structured_contract_payload(payload: dict[str, object]) -> tuple[str, str, str, dict[str, object], str]:
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


def validate_contract_fingerprint(
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
        json.dumps(structured_contract, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    if parts[3] != digest:
        raise ValueError("resume_state_contract_fingerprint_mismatch")


def validate_bundle_against_contract(
    *,
    bundle_path: Path,
    structured_contract_kind: str,
    structured_contract: dict[str, object],
) -> None:
    runtime_contract = {
        "path": bundle_path.as_posix(),
        **relax_contract_artifact_existence(structured_contract_kind, structured_contract),
    }
    try:
        if structured_contract_kind == "record":
            validate_output_bundle(runtime_contract, workspace=Path.cwd())
        else:
            validate_variant_output_bundle(runtime_contract, workspace=Path.cwd())
    except OutputContractError as error:
        if is_unsafe_path_contract_error(error):
            raise ValueError("resume_state_path_unsafe") from error
        raise ValueError("resume_state_bundle_schema_invalid") from error


def is_unsafe_path_contract_error(error: OutputContractError) -> bool:
    violation_types = {violation["type"] for violation in error.violations}
    return bool(
        violation_types
        & {"invalid_bundle_path", "path_escape", "outside_under_root", "invalid_under_root"}
    )


def relax_contract_artifact_existence(
    structured_contract_kind: str,
    structured_contract: dict[str, object],
) -> dict[str, object]:
    relaxed = json.loads(json.dumps(structured_contract))
    if structured_contract_kind == "record":
        relax_field_specs(relaxed.get("fields"))
        return relaxed
    relax_field_specs(relaxed.get("shared_fields"))
    variants = relaxed.get("variants")
    if isinstance(variants, dict):
        for variant_spec in variants.values():
            if isinstance(variant_spec, dict):
                relax_field_specs(variant_spec.get("fields"))
    return relaxed


def relax_field_specs(field_specs: object) -> None:
    if not isinstance(field_specs, list):
        return
    for spec in field_specs:
        if isinstance(spec, dict) and spec.get("type") == "relpath":
            spec["must_exist_target"] = False


def load_artifact_requirements(
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


def lookup_field_path(bundle: dict[str, object], field_path: tuple[str, ...]) -> object:
    current: object = bundle
    for part in field_path:
        if not isinstance(current, dict) or part not in current:
            raise ValueError("resume_state_bundle_schema_invalid")
        current = current[part]
    return current


def is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def resolve_artifact_target(raw_value: object, under: str) -> tuple[str, Path]:
    relpath = workspace_relpath(raw_value)
    workspace = Path.cwd().resolve()
    target = (workspace / relpath).resolve()
    if not is_within(target, workspace):
        raise ValueError("resume_state_path_unsafe")
    under_root = (workspace / under).resolve()
    if not is_within(under_root, workspace) or not is_within(target, under_root):
        raise ValueError("resume_state_path_unsafe")
    return relpath, target


def sha256_path(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def compute_public_input_hash(public_inputs: Mapping[str, object], basis: tuple[str, ...]) -> str:
    selected = {name: public_inputs.get(name) for name in basis}
    return hashlib.sha256(
        json.dumps(selected, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def compute_producer_fingerprint(basis: Mapping[str, object]) -> str:
    return hashlib.sha256(
        json.dumps(basis, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def current_public_input_hash(payload: dict[str, object]) -> str:
    current_public_inputs = payload.get("current_public_inputs")
    public_input_hash_basis = payload.get("public_input_hash_basis")
    if not isinstance(current_public_inputs, dict) or not isinstance(public_input_hash_basis, list):
        raise ValueError("resume_state_contract_invalid")
    basis = tuple(
        name for name in public_input_hash_basis if isinstance(name, str) and name
    )
    if len(basis) != len(public_input_hash_basis):
        raise ValueError("resume_state_contract_invalid")
    return compute_public_input_hash(current_public_inputs, basis)


def current_producer_fingerprint(payload: dict[str, object]) -> str:
    producer_fingerprint_basis = payload.get("producer_fingerprint_basis")
    if not isinstance(producer_fingerprint_basis, dict):
        raise ValueError("resume_state_contract_invalid")
    return compute_producer_fingerprint(producer_fingerprint_basis)


def selected_requirements(
    *,
    bundle: dict[str, object],
    structured_contract_kind: str,
    return_type_name: str,
    reusable_variants: set[str],
    artifact_requirements: dict[str, tuple[tuple[tuple[str, ...], str], ...]],
) -> tuple[str | None, tuple[tuple[tuple[str, ...], str], ...], bool]:
    matched_variant = None
    if structured_contract_kind == "union":
        variant = bundle.get("variant")
        if not isinstance(variant, str):
            raise ValueError("resume_state_bundle_schema_invalid")
        matched_variant = variant
        return matched_variant, artifact_requirements.get(variant, ()), variant in reusable_variants
    return None, artifact_requirements.get(return_type_name, ()), True


def build_artifact_refs(
    *,
    bundle: dict[str, object],
    requirements: tuple[tuple[tuple[str, ...], str], ...],
) -> list[dict[str, object]]:
    refs: list[dict[str, object]] = []
    for field_path, under in requirements:
        relpath, target = resolve_artifact_target(lookup_field_path(bundle, field_path), under)
        if not target.exists():
            raise ValueError("resume_state_required_artifact_missing")
        refs.append(
            {
                "field_path": list(field_path),
                "relpath": relpath,
                "under": under,
                "sha256": sha256_path(target),
            }
        )
    return refs
