#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


SCHEMA = "major_project_phase_visits.v1"
ALLOWED_PHASES = {"big_design", "plan", "implementation"}
FINAL_DECISION_FILENAMES = {
    "big_design": "final_design_review_decision.txt",
    "plan": "final_plan_review_decision.txt",
    "implementation": "final_implementation_review_decision.txt",
}


def init_phase_visits(*, item_state_root: Path, output_bundle: Path | None = None) -> dict[str, str]:
    item_state_root.mkdir(parents=True, exist_ok=True)
    ledger_path = item_state_root / "phase_visit_ledger.json"
    if not ledger_path.exists():
        _write_json(ledger_path, _empty_ledger())
    payload = {"phase_visit_ledger_path": _as_posix(ledger_path)}
    _maybe_write_bundle(output_bundle, payload)
    return payload


def allocate_phase_visit(
    *,
    item_state_root: Path,
    phase: str,
    phase_state_root_base: Path,
    allocation_key: str,
    reason: str,
    source_context_path: Path | None = None,
    output_bundle: Path | None = None,
) -> dict[str, Any]:
    _require_phase(phase)
    if not allocation_key:
        raise ValueError("allocation_key must not be empty")
    if not reason:
        raise ValueError("reason must not be empty")

    init_phase_visits(item_state_root=item_state_root)
    ledger_path = item_state_root / "phase_visit_ledger.json"
    ledger = _read_json_object(ledger_path)

    source_context = _as_posix(source_context_path) if source_context_path is not None else None
    state_root_base = _as_posix(phase_state_root_base)
    existing = _find_visit(ledger, allocation_key=allocation_key)
    if existing is None:
        visit_index = _next_visit_index(ledger, phase)
        phase_state_root = phase_state_root_base / "visits" / f"{visit_index:04d}"
        phase_state_root.mkdir(parents=True, exist_ok=True)
        existing = {
            "phase": phase,
            "visit_index": visit_index,
            "allocation_key": allocation_key,
            "reason": reason,
            "state_root_base": state_root_base,
            "state_root": _as_posix(phase_state_root),
            "status": "allocated",
            "source_context_path": source_context,
        }
        visits = ledger.setdefault("visits", [])
        if not isinstance(visits, list):
            raise ValueError(f"Invalid phase visit ledger visits list: {ledger_path}")
        visits.append(existing)
    else:
        _require_same_payload(
            existing,
            phase=phase,
            reason=reason,
            state_root_base=state_root_base,
            source_context_path=source_context,
        )

    current = ledger.setdefault("current", {})
    if not isinstance(current, dict):
        raise ValueError(f"Invalid phase visit ledger current object: {ledger_path}")
    current_root_path = item_state_root / f"current_{phase}_phase_state_root.txt"
    current_root_path.write_text(str(existing["state_root"]) + "\n", encoding="utf-8")
    current[phase] = {
        "visit_index": int(existing["visit_index"]),
        "state_root": str(existing["state_root"]),
        "state_root_path": _as_posix(current_root_path),
    }
    _write_json(ledger_path, ledger)

    payload = {
        "phase": phase,
        "visit_index": int(existing["visit_index"]),
        "phase_state_root": str(existing["state_root"]),
        "current_phase_state_root_path": _as_posix(current_root_path),
        "phase_visit_ledger_path": _as_posix(ledger_path),
    }
    _maybe_write_bundle(output_bundle, payload)
    return payload


def prepare_phase_visit(
    *,
    item_state_root: Path,
    phase: str,
    phase_state_root_base: Path,
    reason: str,
    source_context_path: Path | None = None,
    output_bundle: Path | None = None,
) -> dict[str, Any]:
    _require_phase(phase)
    init_phase_visits(item_state_root=item_state_root)
    ledger_path = item_state_root / "phase_visit_ledger.json"
    ledger = _read_json_object(ledger_path)
    current = ledger.get("current", {})
    if not isinstance(current, dict):
        raise ValueError(f"Invalid phase visit ledger current object: {ledger_path}")
    current_phase = current.get(phase)
    if isinstance(current_phase, dict):
        current_root = Path(str(current_phase.get("state_root", "")))
        if current_root and not _phase_final_decision_path(phase, current_root).exists():
            visit = _find_visit_by_root(ledger, phase=phase, state_root=current_root.as_posix())
            if visit is not None:
                return _publish_current_visit(
                    item_state_root=item_state_root,
                    ledger_path=ledger_path,
                    ledger=ledger,
                    visit=visit,
                    output_bundle=output_bundle,
                )

    allocation_key = f"{reason}-{_next_visit_index(ledger, phase):04d}"
    return allocate_phase_visit(
        item_state_root=item_state_root,
        phase=phase,
        phase_state_root_base=phase_state_root_base,
        allocation_key=allocation_key,
        reason=reason,
        source_context_path=source_context_path,
        output_bundle=output_bundle,
    )


def _publish_current_visit(
    *,
    item_state_root: Path,
    ledger_path: Path,
    ledger: dict[str, Any],
    visit: dict[str, Any],
    output_bundle: Path | None,
) -> dict[str, Any]:
    phase = str(visit["phase"])
    current_root_path = item_state_root / f"current_{phase}_phase_state_root.txt"
    current_root_path.write_text(str(visit["state_root"]) + "\n", encoding="utf-8")
    current = ledger.setdefault("current", {})
    if not isinstance(current, dict):
        raise ValueError(f"Invalid phase visit ledger current object: {ledger_path}")
    current[phase] = {
        "visit_index": int(visit["visit_index"]),
        "state_root": str(visit["state_root"]),
        "state_root_path": _as_posix(current_root_path),
    }
    _write_json(ledger_path, ledger)
    payload = {
        "phase": phase,
        "visit_index": int(visit["visit_index"]),
        "phase_state_root": str(visit["state_root"]),
        "current_phase_state_root_path": _as_posix(current_root_path),
        "phase_visit_ledger_path": _as_posix(ledger_path),
    }
    _maybe_write_bundle(output_bundle, payload)
    return payload


def _empty_ledger() -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "visits": [],
        "current": {},
    }


def _find_visit(ledger: dict[str, Any], *, allocation_key: str) -> dict[str, Any] | None:
    visits = ledger.get("visits", [])
    if not isinstance(visits, list):
        raise ValueError("Invalid phase visit ledger visits list")
    for visit in visits:
        if not isinstance(visit, dict):
            raise ValueError("Invalid phase visit ledger row")
        if visit.get("allocation_key") == allocation_key:
            return visit
    return None


def _find_visit_by_root(ledger: dict[str, Any], *, phase: str, state_root: str) -> dict[str, Any] | None:
    visits = ledger.get("visits", [])
    if not isinstance(visits, list):
        raise ValueError("Invalid phase visit ledger visits list")
    for visit in visits:
        if not isinstance(visit, dict):
            raise ValueError("Invalid phase visit ledger row")
        if visit.get("phase") == phase and visit.get("state_root") == state_root:
            return visit
    return None


def _phase_final_decision_path(phase: str, phase_state_root: Path) -> Path:
    _require_phase(phase)
    return phase_state_root / FINAL_DECISION_FILENAMES[phase]


def _require_same_payload(
    visit: dict[str, Any],
    *,
    phase: str,
    reason: str,
    state_root_base: str,
    source_context_path: str | None,
) -> None:
    expected = {
        "phase": phase,
        "reason": reason,
        "state_root_base": state_root_base,
        "source_context_path": source_context_path,
    }
    actual = {key: visit.get(key) for key in expected}
    if actual != expected:
        raise ValueError(
            "Conflicting phase visit allocation for key "
            f"{visit.get('allocation_key')!r}: expected {expected}, found {actual}"
        )


def _next_visit_index(ledger: dict[str, Any], phase: str) -> int:
    visits = ledger.get("visits", [])
    if not isinstance(visits, list):
        raise ValueError("Invalid phase visit ledger visits list")
    phase_indexes = [
        int(visit["visit_index"])
        for visit in visits
        if isinstance(visit, dict) and visit.get("phase") == phase and "visit_index" in visit
    ]
    return max(phase_indexes, default=-1) + 1


def _require_phase(phase: str) -> None:
    if phase not in ALLOWED_PHASES:
        raise ValueError(f"Unsupported phase {phase!r}; expected one of {sorted(ALLOWED_PHASES)}")


def _read_json_object(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object: {path}")
    if data.get("schema") != SCHEMA:
        raise ValueError(f"Unsupported phase visit ledger schema in {path}: {data.get('schema')!r}")
    return data


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _maybe_write_bundle(path: Path | None, payload: dict[str, Any]) -> None:
    if path is None:
        return
    _write_json(path, payload)


def _as_posix(path: Path) -> str:
    return path.as_posix()


def main() -> int:
    parser = argparse.ArgumentParser(description="Manage major-project phase visit roots.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init")
    init_parser.add_argument("--item-state-root", type=Path, required=True)
    init_parser.add_argument("--output-bundle", type=Path)

    allocate_parser = subparsers.add_parser("allocate")
    allocate_parser.add_argument("--item-state-root", type=Path, required=True)
    allocate_parser.add_argument("--phase", choices=sorted(ALLOWED_PHASES), required=True)
    allocate_parser.add_argument("--phase-state-root-base", type=Path, required=True)
    allocate_parser.add_argument("--allocation-key", required=True)
    allocate_parser.add_argument("--reason", required=True)
    allocate_parser.add_argument("--source-context-path", type=Path)
    allocate_parser.add_argument("--output-bundle", type=Path)

    prepare_parser = subparsers.add_parser("prepare")
    prepare_parser.add_argument("--item-state-root", type=Path, required=True)
    prepare_parser.add_argument("--phase", choices=sorted(ALLOWED_PHASES), required=True)
    prepare_parser.add_argument("--phase-state-root-base", type=Path, required=True)
    prepare_parser.add_argument("--reason", required=True)
    prepare_parser.add_argument("--source-context-path", type=Path)
    prepare_parser.add_argument("--output-bundle", type=Path)

    args = parser.parse_args()
    if args.command == "init":
        init_phase_visits(item_state_root=args.item_state_root, output_bundle=args.output_bundle)
    elif args.command == "allocate":
        allocate_phase_visit(
            item_state_root=args.item_state_root,
            phase=args.phase,
            phase_state_root_base=args.phase_state_root_base,
            allocation_key=args.allocation_key,
            reason=args.reason,
            source_context_path=args.source_context_path,
            output_bundle=args.output_bundle,
        )
    elif args.command == "prepare":
        prepare_phase_visit(
            item_state_root=args.item_state_root,
            phase=args.phase,
            phase_state_root_base=args.phase_state_root_base,
            reason=args.reason,
            source_context_path=args.source_context_path,
            output_bundle=args.output_bundle,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
