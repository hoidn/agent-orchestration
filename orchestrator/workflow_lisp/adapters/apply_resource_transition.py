"""Apply one supported resource transition and emit a structured result."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


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


def _workspace_relpath(path_value: object) -> Path:
    if not isinstance(path_value, str) or not path_value:
        raise ValueError("resource_transition_invalid_result")
    path = Path(path_value)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError("resource_transition_path_escape")
    return path


def _resource_identifier(payload: dict[str, object], source_path: Path | None) -> str:
    resource_id = payload.get("resource_id")
    if isinstance(resource_id, str) and resource_id:
        return resource_id
    if source_path is not None:
        return source_path.name
    raise ValueError("resource_transition_invalid_result")


def _derived_destination(source_path: Path | None, destination_path: object, queue_to: str | None) -> Path:
    if destination_path is not None:
        return _workspace_relpath(destination_path)
    if source_path is None:
        raise ValueError("resource_transition_invalid_result")
    parent_parts = list(source_path.parent.parts)
    if parent_parts and queue_to:
        parent_parts[-1] = queue_to.replace(".", "_")
    return Path(*parent_parts) / source_path.name


def _append_ledger_event(ledger_path: Path, event: dict[str, object]) -> None:
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    with ledger_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, sort_keys=True))
        handle.write("\n")


def _emit_error(error_type: str) -> int:
    json.dump({"error": {"type": error_type}}, sys.stdout)
    sys.stdout.write("\n")
    return 1


def _write_output_bundle(result: dict[str, object]) -> None:
    bundle_path_raw = os.environ.get("ORCHESTRATOR_OUTPUT_BUNDLE_PATH", "").strip()
    if not bundle_path_raw:
        return
    bundle_path = _workspace_relpath(bundle_path_raw)
    bundle_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = bundle_path.with_suffix(bundle_path.suffix + ".tmp")
    temp_path.write_text(json.dumps(result, sort_keys=True), encoding="utf-8")
    temp_path.replace(bundle_path)


def main(argv: list[str] | None = None) -> int:
    """Run the adapter and emit a typed resource-transition result as JSON."""

    args = argv or sys.argv
    try:
        payload = _load_payload(args)
        source_path_value = payload.get("resource_path")
        source_path = _workspace_relpath(source_path_value) if source_path_value is not None else None
        if source_path is not None and not source_path.exists():
            raise ValueError("resource_transition_missing_source")
        ledger_path = _workspace_relpath(payload.get("ledger_path") or payload.get("ledger"))
        queue_from = payload.get("from")
        queue_to = payload.get("to")
        if queue_from is not None and not isinstance(queue_from, str):
            raise ValueError("resource_transition_invalid_result")
        if queue_to is not None and not isinstance(queue_to, str):
            raise ValueError("resource_transition_invalid_result")
        destination_path = _derived_destination(source_path, payload.get("destination_path"), queue_to)
        if destination_path.exists() and destination_path != source_path:
            raise ValueError("resource_transition_destination_conflict")
        resource_id = _resource_identifier(payload, source_path)
        if source_path is not None and destination_path != source_path:
            destination_path.parent.mkdir(parents=True, exist_ok=True)
            source_path.replace(destination_path)
        try:
            _append_ledger_event(
                ledger_path,
                {
                    "transition": payload.get("transition_name"),
                    "resource_id": resource_id,
                    "from": queue_from,
                    "to": queue_to,
                    "event": payload.get("event"),
                },
            )
        except OSError as error:
            raise ValueError("resource_transition_ledger_update_failed") from error
        result = {
            "resource-id": resource_id,
            "from": queue_from,
            "to": queue_to,
            "new-path": destination_path.as_posix(),
            "transition-id": f"{payload.get('transition_name', 'resource-transition')}::{resource_id}",
        }
        _write_output_bundle(result)
        json.dump(result, sys.stdout)
        sys.stdout.write("\n")
        return 0
    except ValueError as error:
        return _emit_error(str(error))


if __name__ == "__main__":
    raise SystemExit(main())
