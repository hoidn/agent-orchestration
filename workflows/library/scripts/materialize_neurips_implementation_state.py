#!/usr/bin/env python3
"""Materialize NeurIPS implementation phase state from fresh report files."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


ALLOWED_BLOCKERS = {
    "missing_resource",
    "unavailable_hardware",
    "roadmap_conflict",
    "external_dependency_outside_authority",
    "user_decision_required",
    "unrecoverable_after_fix_attempt",
}


def _clean_marker(line: str) -> str:
    return line.strip().lstrip("#").strip().rstrip(":").strip().lower()


def _clean_value(line: str) -> str:
    value = line.strip().strip("-").strip().strip("`").strip()
    if ":" in value and _clean_marker(value.split(":", 1)[0]) == "blocker class":
        value = value.split(":", 1)[1].strip().strip("`").strip()
    return value


def parse_blocker_class(path: Path) -> str:
    lines = path.read_text(encoding="utf-8").splitlines()
    for index, raw_line in enumerate(lines):
        line = raw_line.strip()
        normalized = line.lstrip("#").strip()
        if normalized.lower().startswith("blocker class:"):
            return _validate_blocker(_clean_value(normalized))
        marker = _clean_marker(line)
        if marker == "blocker class":
            inline = _clean_value(line) if ":" in line else ""
            if inline:
                return _validate_blocker(inline)
            for next_line in lines[index + 1 :]:
                value = _clean_value(next_line)
                if not value:
                    continue
                return _validate_blocker(value)
    raise SystemExit("Blocked progress report is missing Blocker Class")


def _validate_blocker(value: str) -> str:
    if value in ALLOWED_BLOCKERS:
        return value
    raise SystemExit(f"Invalid Blocker Class: {value}")


def _is_fresh_report(path: Path, phase_started_at_ns: int) -> bool:
    return path.is_file() and path.stat().st_mtime_ns >= phase_started_at_ns


def materialize_state(
    *,
    bundle_path: Path,
    execution_report_target: Path,
    progress_report_target: Path,
    phase_started_at_ns_path: Path,
) -> dict[str, str]:
    phase_started_at_ns = int(phase_started_at_ns_path.read_text(encoding="utf-8").strip())
    has_execution_report = _is_fresh_report(execution_report_target, phase_started_at_ns)
    has_progress_report = _is_fresh_report(progress_report_target, phase_started_at_ns)

    if has_execution_report and has_progress_report:
        raise SystemExit("Current pass produced both execution and blocker reports")
    if has_execution_report:
        payload = {
            "implementation_state": "COMPLETED",
            "execution_report_path": execution_report_target.as_posix(),
        }
    elif has_progress_report:
        payload = {
            "implementation_state": "BLOCKED",
            "progress_report_path": progress_report_target.as_posix(),
            "blocker_class": parse_blocker_class(progress_report_target),
        }
    else:
        raise SystemExit("Current implementation pass produced neither execution report nor blocker report")

    bundle_path.parent.mkdir(parents=True, exist_ok=True)
    bundle_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle-path", required=True)
    parser.add_argument("--execution-report-target", required=True)
    parser.add_argument("--progress-report-target", required=True)
    parser.add_argument("--phase-started-at-ns-path", required=True)
    args = parser.parse_args()

    materialize_state(
        bundle_path=Path(args.bundle_path),
        execution_report_target=Path(args.execution_report_target),
        progress_report_target=Path(args.progress_report_target),
        phase_started_at_ns_path=Path(args.phase_started_at_ns_path),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
