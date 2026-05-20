"""Validate whether a canonical phase bundle can be reused."""

from __future__ import annotations

import json
import sys
from pathlib import Path


HARD_FAILURE_CODES = {
    "resume_state_path_unsafe",
    "resume_state_pointer_authority_forbidden",
    "resume_state_bundle_schema_invalid",
    "resume_state_required_artifact_missing",
    "resume_state_contract_invalid",
}


def _load_payload(argv: list[str]) -> dict[str, object]:
    if len(argv) > 1:
        candidate = Path(argv[1])
        if candidate.is_file():
            return json.loads(candidate.read_text(encoding="utf-8"))
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
        # Pointer files are representations, not canonical state authority.
        if error.pos == 0:
            raise ValueError("resume_state_pointer_authority_forbidden") from error
        raise ValueError("resume_state_bundle_schema_invalid") from error
    if isinstance(bundle, str):
        raise ValueError("resume_state_pointer_authority_forbidden")
    if not isinstance(bundle, dict):
        raise ValueError("resume_state_bundle_schema_invalid")
    return bundle


def main(argv: list[str] | None = None) -> int:
    """Validate whether a prior canonical phase bundle may be reused."""

    args = argv or sys.argv
    try:
        payload = _load_payload(args)
        resume_from = _workspace_relpath(payload.get("resume_from"))
        expected_return_type = payload.get("expected_return_type")
        valid_variants = {
            variant for variant in payload.get("valid_variants", []) if isinstance(variant, str)
        }
        required_artifact_fields = payload.get("required_artifact_fields", {})
        bundle_path = Path(resume_from)
        if not bundle_path.exists():
            json.dump({"variant": "START", "reason_code": "MISSING_BUNDLE"}, sys.stdout)
            sys.stdout.write("\n")
            return 0
        bundle = _load_bundle(bundle_path)
        if valid_variants:
            variant = bundle.get("variant")
            if not isinstance(variant, str):
                raise ValueError("resume_state_bundle_schema_invalid")
            if variant not in valid_variants:
                json.dump({"variant": "START", "reason_code": "VARIANT_NOT_REUSABLE"}, sys.stdout)
                sys.stdout.write("\n")
                return 0
            required_fields = required_artifact_fields.get(variant, [])
        else:
            if not isinstance(expected_return_type, str) or not expected_return_type:
                raise ValueError("resume_state_contract_invalid")
            required_fields = required_artifact_fields.get(expected_return_type, [])
        for field_name in required_fields:
            artifact_relpath = _workspace_relpath(bundle.get(field_name))
            if not Path(artifact_relpath).exists():
                raise ValueError("resume_state_required_artifact_missing")
        json.dump({"variant": "REUSE", "source_bundle_path": resume_from}, sys.stdout)
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
