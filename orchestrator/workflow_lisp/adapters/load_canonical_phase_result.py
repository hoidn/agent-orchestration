"""Load one canonical phase bundle and echo its structured payload."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

from orchestrator.contracts.output_contract import (
    OutputContractError,
    validate_output_bundle,
    validate_variant_output_bundle,
)


def _emit_error(error_type: str) -> int:
    json.dump({"error": {"type": error_type}}, sys.stdout)
    sys.stdout.write("\n")
    return 1


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


def _bundle_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_bundle(bundle_path: Path) -> dict[str, object] | None:
    try:
        bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    if isinstance(bundle, str) or not isinstance(bundle, dict):
        return None
    return bundle


def _validate_contract_fingerprint(
    *,
    target_dsl_version: str,
    return_type_name: str,
    structured_contract_kind: str,
    structured_contract: dict[str, object],
    expected_contract_fingerprint: str,
) -> bool:
    parts = expected_contract_fingerprint.split(":", 3)
    if (
        len(parts) != 4
        or parts[0] != target_dsl_version
        or parts[1] != return_type_name
        or parts[2] != structured_contract_kind
    ):
        return False
    digest = hashlib.sha256(
        json.dumps(
            structured_contract,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return parts[3] == digest


def main(argv: list[str] | None = None) -> int:
    """Load a reusable phase bundle and mirror it to stdout as JSON."""

    args = argv or sys.argv
    payload = _load_payload(args)
    bundle_path_value = payload.get("bundle_path")
    if bundle_path_value is None:
        bundle_path_value = payload.get("source_bundle_path")
    if not isinstance(bundle_path_value, str) or not bundle_path_value:
        return _emit_error("resume_state_loader_contract_invalid")
    bundle_path = Path(bundle_path_value)
    if bundle_path.is_absolute() or ".." in bundle_path.parts:
        return _emit_error("resume_state_path_unsafe")
    target_dsl_version = payload.get("target_dsl_version")
    return_type_name = payload.get("return_type_name")
    expected_contract_fingerprint = payload.get("expected_contract_fingerprint")
    structured_contract_kind = payload.get("structured_contract_kind")
    structured_contract = payload.get("structured_contract")
    source_bundle_sha256 = payload.get("source_bundle_sha256")
    if (
        not isinstance(target_dsl_version, str)
        or not target_dsl_version
        or not isinstance(return_type_name, str)
        or not return_type_name
        or not isinstance(expected_contract_fingerprint, str)
        or structured_contract_kind not in {"record", "union"}
        or not isinstance(structured_contract, dict)
        or not isinstance(source_bundle_sha256, str)
        or not source_bundle_sha256
    ):
        return _emit_error("resume_state_loader_contract_invalid")
    if not _validate_contract_fingerprint(
        target_dsl_version=target_dsl_version,
        return_type_name=return_type_name,
        structured_contract_kind=str(structured_contract_kind),
        structured_contract=structured_contract,
        expected_contract_fingerprint=expected_contract_fingerprint,
    ):
        return _emit_error("resume_state_contract_fingerprint_mismatch")
    if not bundle_path.exists():
        return _emit_error("resume_state_loader_schema_invalid")
    if _bundle_sha256(bundle_path) != source_bundle_sha256:
        return _emit_error("resume_state_bundle_mutated_before_load")
    bundle = _load_bundle(bundle_path)
    if bundle is None:
        return _emit_error("resume_state_loader_schema_invalid")
    runtime_contract = {"path": bundle_path.as_posix(), **structured_contract}
    try:
        if structured_contract_kind == "record":
            validate_output_bundle(runtime_contract, workspace=Path.cwd())
        else:
            validate_variant_output_bundle(runtime_contract, workspace=Path.cwd())
    except OutputContractError:
        return _emit_error("resume_state_loader_schema_invalid")
    json.dump(bundle, sys.stdout)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
