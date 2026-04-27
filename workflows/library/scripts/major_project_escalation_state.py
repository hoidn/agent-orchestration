#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


INACTIVE_UPSTREAM_CONTEXT: dict[str, Any] = {
    "active": False,
    "source_phase": None,
    "decision": None,
    "recommended_next_phase": None,
    "reason_summary": "",
    "must_change": [],
    "evidence_paths": {},
}

TERMINAL_RESOLUTIONS = {
    "consumed_by_plan",
    "consumed_by_redesign",
    "reset_on_design_approval",
    "tranche_completed",
    "tranche_blocked",
    "tranche_superseded",
}


def init_upstream(*, item_state_root: Path, output_bundle: Path | None = None) -> dict[str, str]:
    item_state_root.mkdir(parents=True, exist_ok=True)
    context_path = item_state_root / "upstream_escalation_context.json"
    archive_path = item_state_root / "upstream_escalation_context_archive.jsonl"
    if not context_path.exists():
        _write_json(context_path, INACTIVE_UPSTREAM_CONTEXT)
    archive_path.touch(exist_ok=True)
    payload = {
        "upstream_escalation_context_path": _as_posix(context_path),
        "upstream_escalation_context_archive_path": _as_posix(archive_path),
    }
    _maybe_write_bundle(output_bundle, payload)
    return payload


def activate_upstream(
    *,
    item_state_root: Path,
    source_context_path: Path,
    output_bundle: Path | None = None,
) -> dict[str, str]:
    init_upstream(item_state_root=item_state_root)
    source = _read_json_object(source_context_path)
    if source.get("active") is not True:
        raise ValueError(f"Source escalation context is not active: {source_context_path}")
    context_path = item_state_root / "upstream_escalation_context.json"
    archive_path = item_state_root / "upstream_escalation_context_archive.jsonl"
    current = _read_json_object(context_path)
    if current.get("active") is True:
        _append_archive(archive_path, current, "replaced_by_new_escalation")
    _write_json(context_path, source)
    payload = {"upstream_escalation_context_path": _as_posix(context_path)}
    _maybe_write_bundle(output_bundle, payload)
    return payload


def clear_upstream(
    *,
    item_state_root: Path,
    resolution: str,
    output_bundle: Path | None = None,
) -> dict[str, str]:
    _require_resolution(resolution)
    init_upstream(item_state_root=item_state_root)
    context_path = item_state_root / "upstream_escalation_context.json"
    archive_path = item_state_root / "upstream_escalation_context_archive.jsonl"
    current = _read_json_object(context_path)
    if current.get("active") is True:
        _append_archive(archive_path, current, resolution)
    _write_json(context_path, INACTIVE_UPSTREAM_CONTEXT)
    payload = {"upstream_escalation_context_path": _as_posix(context_path)}
    _maybe_write_bundle(output_bundle, payload)
    return payload


def write_implementation_iteration_context(
    *,
    implementation_phase_state_root: Path,
    phase_iteration_index: int,
    soft_threshold: int,
    max_phase_iterations: int,
    output_bundle: Path | None = None,
) -> dict[str, Any]:
    implementation_phase_state_root.mkdir(parents=True, exist_ok=True)
    ledger_path = implementation_phase_state_root / "implementation_iteration_ledger.json"
    ledger = _read_json_object(ledger_path) if ledger_path.exists() else _initial_ledger()
    cumulative = int(ledger.get("cumulative_review_iterations_since_design_approval", 0)) + 1
    ledger["cumulative_review_iterations_since_design_approval"] = cumulative
    _write_json(ledger_path, ledger)

    context_path = implementation_phase_state_root / "implementation_iteration_context.json"
    context = {
        "phase_iteration_index": phase_iteration_index,
        "phase_iteration_number": phase_iteration_index + 1,
        "cumulative_review_iterations_since_design_approval": cumulative,
        "soft_escalation_iteration_threshold": soft_threshold,
        "threshold_crossed": cumulative >= soft_threshold,
        "max_phase_iterations": max_phase_iterations,
    }
    _write_json(context_path, context)
    payload = {
        "implementation_iteration_ledger_path": _as_posix(ledger_path),
        "implementation_iteration_context_path": _as_posix(context_path),
        **context,
    }
    _maybe_write_bundle(output_bundle, payload)
    return payload


def reset_ledger_on_design_approval(
    *,
    implementation_phase_state_root: Path,
    output_bundle: Path | None = None,
) -> dict[str, Any]:
    implementation_phase_state_root.mkdir(parents=True, exist_ok=True)
    ledger_path = implementation_phase_state_root / "implementation_iteration_ledger.json"
    archive_path = implementation_phase_state_root / "implementation_iteration_ledger_archive.jsonl"
    ledger = _read_json_object(ledger_path) if ledger_path.exists() else _initial_ledger()
    _append_archive(archive_path, ledger, "reset_on_design_approval")
    next_epoch = int(ledger.get("design_epoch", 1)) + 1
    fresh = {
        "design_epoch": next_epoch,
        "cumulative_review_iterations_since_design_approval": 0,
    }
    _write_json(ledger_path, fresh)
    payload = {
        "implementation_iteration_ledger_path": _as_posix(ledger_path),
        "implementation_iteration_ledger_archive_path": _as_posix(archive_path),
        **fresh,
    }
    _maybe_write_bundle(output_bundle, payload)
    return payload


def terminal_cleanup(
    *,
    item_state_root: Path,
    implementation_phase_state_root: Path,
    resolution: str,
    output_bundle: Path | None = None,
) -> dict[str, str]:
    _require_resolution(resolution)
    clear_upstream(item_state_root=item_state_root, resolution=resolution)
    implementation_phase_state_root.mkdir(parents=True, exist_ok=True)
    ledger_path = implementation_phase_state_root / "implementation_iteration_ledger.json"
    archive_path = implementation_phase_state_root / "implementation_iteration_ledger_archive.jsonl"
    if ledger_path.exists():
        _append_archive(archive_path, _read_json_object(ledger_path), resolution)
    payload = {
        "upstream_escalation_context_path": _as_posix(item_state_root / "upstream_escalation_context.json"),
        "implementation_iteration_ledger_path": _as_posix(ledger_path),
    }
    _maybe_write_bundle(output_bundle, payload)
    return payload


def _initial_ledger() -> dict[str, int]:
    return {
        "design_epoch": 1,
        "cumulative_review_iterations_since_design_approval": 0,
    }


def _read_json_object(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return data


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _append_archive(path: Path, payload: dict[str, Any], resolution: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "archived_at": datetime.now(timezone.utc).isoformat(),
        "resolution": resolution,
        "payload": payload,
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, sort_keys=True) + "\n")


def _maybe_write_bundle(path: Path | None, payload: dict[str, Any]) -> None:
    if path is None:
        return
    _write_json(path, payload)


def _require_resolution(resolution: str) -> None:
    if resolution not in TERMINAL_RESOLUTIONS:
        raise ValueError(f"Unsupported resolution {resolution!r}; expected one of {sorted(TERMINAL_RESOLUTIONS)}")


def _as_posix(path: Path) -> str:
    return path.as_posix()


def main() -> int:
    parser = argparse.ArgumentParser(description="Manage major-project escalation state.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init-upstream")
    init_parser.add_argument("--item-state-root", type=Path, required=True)
    init_parser.add_argument("--output-bundle", type=Path)

    activate_parser = subparsers.add_parser("activate-upstream")
    activate_parser.add_argument("--item-state-root", type=Path, required=True)
    activate_parser.add_argument("--source-context-path", type=Path, required=True)
    activate_parser.add_argument("--output-bundle", type=Path)

    clear_parser = subparsers.add_parser("clear-upstream")
    clear_parser.add_argument("--item-state-root", type=Path, required=True)
    clear_parser.add_argument("--resolution", required=True)
    clear_parser.add_argument("--output-bundle", type=Path)

    write_parser = subparsers.add_parser("write-implementation-iteration-context")
    write_parser.add_argument("--implementation-phase-state-root", type=Path, required=True)
    write_parser.add_argument("--phase-iteration-index", type=int, required=True)
    write_parser.add_argument("--soft-threshold", type=int, required=True)
    write_parser.add_argument("--max-phase-iterations", type=int, required=True)
    write_parser.add_argument("--output-bundle", type=Path)

    reset_parser = subparsers.add_parser("reset-ledger-on-design-approval")
    reset_parser.add_argument("--implementation-phase-state-root", type=Path, required=True)
    reset_parser.add_argument("--output-bundle", type=Path)

    terminal_parser = subparsers.add_parser("terminal-cleanup")
    terminal_parser.add_argument("--item-state-root", type=Path, required=True)
    terminal_parser.add_argument("--implementation-phase-state-root", type=Path, required=True)
    terminal_parser.add_argument("--resolution", required=True)
    terminal_parser.add_argument("--output-bundle", type=Path)

    args = parser.parse_args()
    if args.command == "init-upstream":
        init_upstream(item_state_root=args.item_state_root, output_bundle=args.output_bundle)
    elif args.command == "activate-upstream":
        activate_upstream(
            item_state_root=args.item_state_root,
            source_context_path=args.source_context_path,
            output_bundle=args.output_bundle,
        )
    elif args.command == "clear-upstream":
        clear_upstream(
            item_state_root=args.item_state_root,
            resolution=args.resolution,
            output_bundle=args.output_bundle,
        )
    elif args.command == "write-implementation-iteration-context":
        write_implementation_iteration_context(
            implementation_phase_state_root=args.implementation_phase_state_root,
            phase_iteration_index=args.phase_iteration_index,
            soft_threshold=args.soft_threshold,
            max_phase_iterations=args.max_phase_iterations,
            output_bundle=args.output_bundle,
        )
    elif args.command == "reset-ledger-on-design-approval":
        reset_ledger_on_design_approval(
            implementation_phase_state_root=args.implementation_phase_state_root,
            output_bundle=args.output_bundle,
        )
    elif args.command == "terminal-cleanup":
        terminal_cleanup(
            item_state_root=args.item_state_root,
            implementation_phase_state_root=args.implementation_phase_state_root,
            resolution=args.resolution,
            output_bundle=args.output_bundle,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
