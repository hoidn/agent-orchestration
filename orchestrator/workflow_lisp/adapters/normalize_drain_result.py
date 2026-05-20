"""Normalize one drain loop accumulator into a structured DrainResult."""

from __future__ import annotations

import json
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
        raise ValueError("drain_result_invalid")
    path = Path(path_value)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError("drain_result_invalid")
    return path


def _count_selected_events(ledger_path: Path) -> int:
    if not ledger_path.exists():
        return 0
    count = 0
    for line in ledger_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        event = json.loads(line)
        if event.get("event") == "SELECTED":
            count += 1
    return count


def _emit_error(error_type: str) -> int:
    json.dump({"error": {"type": error_type}}, sys.stdout)
    sys.stdout.write("\n")
    return 1


def main(argv: list[str] | None = None) -> int:
    """Normalize a drain accumulator payload into the public DrainResult shape."""

    args = argv or sys.argv
    try:
        payload = _load_payload(args)
        terminal_status = payload.get("terminal_status")
        if terminal_status not in {"EMPTY", "BLOCKED"}:
            raise ValueError("drain_result_invalid")
        ledger_path = _workspace_relpath(payload.get("ledger_path"))
        selected_count = _count_selected_events(ledger_path)
        if terminal_status == "BLOCKED":
            result = {
                "variant": "BLOCKED",
                "progress-report-path": payload.get("progress_report_path"),
                "blocker-class": payload.get("blocker_class"),
            }
        else:
            run_state_path = payload.get("run_state_path")
            if not isinstance(run_state_path, str) or not run_state_path:
                raise ValueError("drain_result_invalid")
            result = {
                "variant": "COMPLETED" if selected_count > 0 else "EMPTY",
                "run-state": run_state_path,
            }
            if selected_count > 0:
                result["items-processed"] = selected_count
        json.dump(result, sys.stdout)
        sys.stdout.write("\n")
        return 0
    except (ValueError, json.JSONDecodeError, OSError):
        return _emit_error("drain_result_invalid")


if __name__ == "__main__":
    raise SystemExit(main())
