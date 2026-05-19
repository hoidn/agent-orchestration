"""Load one canonical phase bundle and echo its structured payload."""

from __future__ import annotations

import json
import sys
from pathlib import Path


def _emit_error(error_type: str) -> int:
    json.dump({"error": {"type": error_type}}, sys.stdout)
    sys.stdout.write("\n")
    return 1


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


def _load_bundle(bundle_path: Path) -> dict[str, object] | None:
    try:
        bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    if not isinstance(bundle, dict):
        return None
    return bundle


def main(argv: list[str] | None = None) -> int:
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
    if not bundle_path.exists():
        return _emit_error("resume_state_loader_schema_invalid")
    bundle = _load_bundle(bundle_path)
    if bundle is None:
        return _emit_error("resume_state_loader_schema_invalid")
    json.dump(bundle, sys.stdout)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
