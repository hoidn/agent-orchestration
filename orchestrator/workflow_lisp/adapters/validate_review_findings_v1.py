"""Validate the bounded ReviewFindings carrier and referenced JSON artifact."""

from __future__ import annotations

import json
import sys
from pathlib import Path


def _load_payload(argv: list[str]) -> dict[str, object]:
    if len(argv) > 2:
        return {
            "schema_version": argv[1],
            "items_path": argv[2],
        }
    if len(argv) > 1:
        candidate = Path(argv[1])
        if candidate.is_file():
            return json.loads(candidate.read_text(encoding="utf-8"))
        return json.loads(argv[1])
    raw = sys.stdin.read().strip()
    if not raw:
        return {}
    return json.loads(raw)


def _workspace_relpath(path_value: object) -> Path:
    if not isinstance(path_value, str) or not path_value:
        raise ValueError("review_findings_contract_invalid")
    path = Path(path_value)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError("review_findings_path_unsafe")
    if path.parts[:2] != ("artifacts", "work"):
        raise ValueError("review_findings_path_unsafe")
    return path


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _validated_findings_path(path: Path) -> Path:
    workspace = Path.cwd().resolve()
    target = (workspace / path).resolve()
    artifacts_root = (workspace / "artifacts" / "work").resolve()
    if not _is_within(target, workspace) or not _is_within(artifacts_root, workspace):
        raise ValueError("review_findings_path_unsafe")
    if not _is_within(target, artifacts_root):
        raise ValueError("review_findings_path_unsafe")
    return target


def _load_findings_json(path: Path) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise ValueError("review_findings_missing_artifact") from error
    except json.JSONDecodeError as error:
        raise ValueError("review_findings_bundle_schema_invalid") from error
    if isinstance(payload, str):
        raise ValueError("review_findings_pointer_authority_forbidden")
    if not isinstance(payload, dict):
        raise ValueError("review_findings_bundle_schema_invalid")
    return payload


def _emit_error(error_type: str) -> int:
    json.dump({"error": {"type": error_type}}, sys.stdout)
    sys.stdout.write("\n")
    return 1


def main(argv: list[str] | None = None) -> int:
    """Validate one ReviewFindings.v1 carrier and echo it on success."""

    args = argv or sys.argv
    try:
        payload = _load_payload(args)
        schema_version = payload.get("schema_version")
        if schema_version != "ReviewFindings.v1":
            raise ValueError("review_findings_contract_invalid")
        items_path = _workspace_relpath(payload.get("items_path"))
        findings_payload = _load_findings_json(_validated_findings_path(items_path))
        if "items" not in findings_payload:
            raise ValueError("review_findings_bundle_schema_invalid")
        json.dump(
            {
                "schema_version": schema_version,
                "items_path": items_path.as_posix(),
            },
            sys.stdout,
        )
        sys.stdout.write("\n")
        return 0
    except ValueError as error:
        return _emit_error(str(error))


if __name__ == "__main__":
    raise SystemExit(main())
