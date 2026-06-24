#!/usr/bin/env python3
"""Record a workflow step-back diagnosis outcome in run state."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


ALLOWED_ACTIONS = {
    "REDRAFT_PLAN",
    "REVISE_REQUIREMENTS",
    "SPLIT_WORK_ITEM",
    "DROP_OR_DEMOTE_WORK_ITEM",
    "FIX_WORKFLOW_MECHANICS",
    "CONTINUE_WITH_CURRENT_PLAN",
    "NEEDS_HUMAN_DECISION",
}


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise SystemExit(f"Missing required JSON file: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise SystemExit(f"JSON file must contain an object: {path}")
    return payload


def _save_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def _write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value + "\n", encoding="utf-8")


def record_step_back_outcome(
    *,
    state: dict[str, Any],
    decision: Mapping[str, Any],
    diagnosis: Mapping[str, Any],
    iteration: int,
) -> tuple[dict[str, Any], dict[str, Any], str]:
    action = str(diagnosis.get("action") or "").strip()
    if action not in ALLOWED_ACTIONS:
        raise SystemExit(f"Unsupported step-back action: {action}")
    rationale = str(diagnosis.get("rationale") or "").strip()
    trigger_codes = list(decision.get("trigger_codes") or [])
    failure_fingerprint = str(decision.get("failure_fingerprint") or "").strip()
    drain_status = "BLOCKED" if action == "NEEDS_HUMAN_DECISION" else "CONTINUE"

    event = {
        "event": "step_back",
        "run_id": str(state.get("run_id") or "").strip(),
        "iteration": iteration,
        "trigger_codes": trigger_codes,
        "failure_fingerprint": failure_fingerprint,
        "decision": str(decision.get("route") or "").strip(),
        "action": action,
        "rationale": rationale,
        "timestamp_utc": _timestamp(),
    }
    state.setdefault("history", []).append(event)
    state.setdefault("step_back_events", []).append(event)
    summary = {
        "schema": "workflow_step_back_outcome/v1",
        "record_status": "STEP_BACK_RECORDED",
        "run_id": event["run_id"],
        "iteration": iteration,
        "decision": event["decision"],
        "trigger_codes": trigger_codes,
        "failure_fingerprint": failure_fingerprint,
        "action": action,
        "rationale": rationale,
        "drain_status": drain_status,
    }
    return state, summary, drain_status


def _step_back_pre_selection_bundle(summary: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "pre_selection_route": "BLOCKED",
        "design_gap_id": "",
        "recovery_route": "TERMINAL_BLOCKED",
        "recovery_reason": str(summary.get("rationale") or "").strip(),
        "recovery_status": "STEP_BACK_RECORDED",
        "progress_report_path": "",
        "architecture_path": "",
        "plan_path": "",
        "architecture_copy_path": "",
        "plan_copy_path": "",
        "blocker_class": "workflow_non_progress",
        "block_reason": str(summary.get("failure_fingerprint") or "").strip(),
        "implementation_state_path": "",
        "recovery_event_id": str(summary.get("failure_fingerprint") or "").strip(),
        "step_back_action": str(summary.get("action") or "").strip(),
        "step_back_drain_status": str(summary.get("drain_status") or "").strip(),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state-path", required=True)
    parser.add_argument("--decision-path", required=True)
    parser.add_argument("--diagnosis-path", required=True)
    parser.add_argument("--summary-path", required=True)
    parser.add_argument("--drain-status-path", required=True)
    parser.add_argument("--pre-selection-output")
    parser.add_argument("--iteration", type=int, required=True)
    args = parser.parse_args()

    state_path = Path(args.state_path)
    state = _load_json(state_path)
    state, summary, drain_status = record_step_back_outcome(
        state=state,
        decision=_load_json(Path(args.decision_path)),
        diagnosis=_load_json(Path(args.diagnosis_path)),
        iteration=args.iteration,
    )
    _save_json(state_path, state)
    _save_json(Path(args.summary_path), summary)
    _write_text(Path(args.drain_status_path), drain_status)
    if args.pre_selection_output:
        _save_json(Path(args.pre_selection_output), _step_back_pre_selection_bundle(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
