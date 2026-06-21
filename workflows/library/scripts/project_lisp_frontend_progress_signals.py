#!/usr/bin/env python3
"""Project Lisp frontend drain run-state history into generic progress signals."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise SystemExit(f"Missing required JSON file: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise SystemExit(f"JSON file must contain an object: {path}")
    return payload


def _save_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _stable_fingerprint(parts: list[str]) -> str:
    normalized = "\x1f".join(str(part or "").strip() for part in parts)
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]
    return f"lisp-drain:{digest}"


def _dependency_edge_signal(entry: Mapping[str, Any]) -> tuple[str, str, int]:
    edge = entry.get("recovery_dependency_edge")
    if not isinstance(edge, Mapping):
        reason = str(entry.get("prerequisite_recovery_reason") or entry.get("recovery_reason") or "").strip()
        if reason == "selected_downstream_before_blocker_ready":
            return "downstream_before_blocker_ready", _stable_fingerprint([str(entry.get("item_id") or ""), reason]), 0
        return "", "", 0
    blocked = edge.get("blocked_work") if isinstance(edge.get("blocked_work"), Mapping) else {}
    blocker = edge.get("blocker_work") if isinstance(edge.get("blocker_work"), Mapping) else {}
    retry = edge.get("retry_target") if isinstance(edge.get("retry_target"), Mapping) else {}
    status = str(edge.get("status") or "").strip()
    reason = str(edge.get("reason") or "").strip()
    if status in {"invalid_cycle", "missing_evidence"}:
        event = "invalid"
    elif status in {"ready_to_retry", "completed"} or str(entry.get("recovery_status") or "").strip() == "RETRY_READY":
        event = "retry_ready"
    elif status == "waiting" or str(entry.get("recovery_status") or "").strip() == "PREREQUISITE_WORK_PENDING":
        event = "waiting"
    elif status:
        event = status
    else:
        event = "recorded"
    downstream = edge.get("downstream_work") if isinstance(edge.get("downstream_work"), list) else []
    fingerprint = _stable_fingerprint(
        [
            str(blocked.get("source") or ""),
            str(blocked.get("id") or ""),
            str(blocker.get("source") or ""),
            str(blocker.get("id") or ""),
            str(edge.get("relation") or ""),
            str(edge.get("reason_code") or reason),
            str(retry.get("source") or ""),
            str(retry.get("id") or ""),
        ]
    )
    return event, fingerprint, len(downstream) + (1 if blocker else 0)


def _event_iteration(index: int, event: Mapping[str, Any]) -> int:
    value = event.get("iteration")
    if value is not None:
        try:
            return int(value)
        except (TypeError, ValueError):
            pass
    return index


def project_progress_signals(
    *,
    run_id: str,
    run_state: Mapping[str, Any],
    current_iteration: int,
) -> dict[str, Any]:
    events: list[dict[str, Any]] = []
    for index, entry in enumerate(run_state.get("history") or []):
        if not isinstance(entry, dict):
            continue
        event_name = str(entry.get("event") or "").strip()
        if event_name not in {
            "blocked",
            "completed",
            "prerequisite_recovery_continues",
            "prerequisite_recovery_pending_on_blocked_prerequisite",
            "blocked_recovery_review_revise",
            "plan_revision",
            "gap_design_revision",
            "design_revision",
            "step_back",
        }:
            continue
        item_id = str(entry.get("item_id") or "").strip()
        source = str(entry.get("source") or "").strip()
        reason = str(entry.get("reason") or "").strip()
        recovery_route = str(entry.get("recovery_route") or "").strip()
        recovery_reason = str(entry.get("recovery_reason") or "").strip()
        recovery_status = str(entry.get("recovery_status") or "").strip()
        blocker_class = str(entry.get("blocker_class") or "").strip()
        prerequisite_generated = (
            recovery_route == "PREREQUISITE_GAP_REQUIRED"
            or recovery_status == "PREREQUISITE_WORK_PENDING"
            or event_name.startswith("prerequisite_recovery")
        )
        dependency_edge_event, dependency_edge_fingerprint, dependency_chain_depth = _dependency_edge_signal(entry)
        plan_revised = event_name in {"plan_revision", "gap_design_revision", "design_revision", "blocked_recovery_review_revise"}
        step_back_recorded = event_name == "step_back"
        accepted_change = (
            event_name == "completed"
            or plan_revised
            or step_back_recorded
            or dependency_edge_event == "retry_ready"
        )
        outcome = "completed" if event_name == "completed" else "changed" if accepted_change else "blocked"
        events.append(
            {
                "iteration": _event_iteration(index, entry),
                "work_item_id": item_id,
                "source": source,
                "phase": str(entry.get("phase") or "").strip() or "implementation",
                "outcome": outcome,
                "accepted_change": accepted_change,
                "commit_hash": str(entry.get("commit_hash") or "").strip(),
                "blocker_fingerprint": _stable_fingerprint(
                    [
                        item_id,
                        source,
                        reason,
                        recovery_route,
                        recovery_reason,
                        blocker_class,
                    ]
                )
                if not accepted_change
                else "",
                "review_finding_fingerprints": list(entry.get("review_finding_fingerprints") or []),
                "prerequisite_generated": prerequisite_generated,
                "plan_revised": plan_revised,
                "stale_artifact_detected": _stale_artifact_detected(run_id=run_id, current_iteration=current_iteration, entry=entry),
                "dependency_edge_event": dependency_edge_event,
                "dependency_edge_fingerprint": dependency_edge_fingerprint,
                "dependency_chain_depth": dependency_chain_depth,
            }
        )
    return {
        "schema": "workflow_progress_signals/v1",
        "run_id": run_id,
        "current_iteration": current_iteration,
        "event_count": len(events),
        "events": events,
    }


def _stale_artifact_detected(*, run_id: str, current_iteration: int, entry: Mapping[str, Any]) -> bool:
    entry_run = str(entry.get("run_id") or "").strip()
    if entry_run and entry_run != run_id:
        return True
    entry_iteration = entry.get("iteration")
    if entry_iteration is None:
        return False
    try:
        return int(entry_iteration) > current_iteration
    except (TypeError, ValueError):
        return True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--run-state-path", required=True)
    parser.add_argument("--current-iteration", type=int, required=True)
    parser.add_argument("--artifact-work-root", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    del args.artifact_work_root  # Artifact roots are not authority for this projection.
    payload = project_progress_signals(
        run_id=args.run_id,
        run_state=_load_json(Path(args.run_state_path)),
        current_iteration=args.current_iteration,
    )
    _save_json(Path(args.output), payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
