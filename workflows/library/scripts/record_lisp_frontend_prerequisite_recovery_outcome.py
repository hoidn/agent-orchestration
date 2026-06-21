#!/usr/bin/env python3
"""Record prerequisite recovery satisfaction for a blocked design gap."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from workflows.library.scripts.workflow_recovery_dependencies import (
        WorkRef,
        edge_from_blocked_entry,
        edge_to_json,
        normalize_edge,
    )
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from workflows.library.scripts.workflow_recovery_dependencies import (
        WorkRef,
        edge_from_blocked_entry,
        edge_to_json,
        normalize_edge,
    )


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise SystemExit(f"Missing required JSON file: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _save_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def _write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value + "\n", encoding="utf-8")


def _read_status(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8").strip()


def _selected_work(selection: dict[str, Any]) -> tuple[str, str]:
    status = str(selection.get("selection_status") or "").strip()
    if status == "DRAFT_DESIGN_GAP":
        return "DESIGN_GAP", str(selection.get("design_gap_id") or "").strip()
    if status == "SELECT_BACKLOG_ITEM":
        return "BACKLOG_ITEM", str(selection.get("selected_item_id") or "").strip()
    return "", ""


def _is_completed(state: dict[str, Any], *, source: str, item_id: str) -> bool:
    if source == "DESIGN_GAP":
        return item_id in set(state.get("completed_design_gaps") or [])
    if source == "BACKLOG_ITEM":
        return item_id in set(state.get("completed_items") or [])
    return False


def _completed_waiting_prerequisite(state: dict[str, Any], *, original_gap_id: str) -> tuple[str, str]:
    original = dict((state.get("blocked_design_gaps") or {}).get(original_gap_id) or {})
    edge = edge_from_blocked_entry(WorkRef(source="DESIGN_GAP", id=original_gap_id), original)
    if edge is not None and edge.blocker_work is not None:
        prerequisite_id = edge.blocker_work.id
        source = edge.blocker_work.source
    else:
        prerequisite_id = str(original.get("waiting_on_prerequisite_gap_id") or "").strip()
        source = str(original.get("waiting_on_prerequisite_source") or "DESIGN_GAP").strip()
    if not prerequisite_id:
        return "", ""
    if _is_completed(state, source=source, item_id=prerequisite_id):
        return source, prerequisite_id
    return "", ""


def _original_entry(state: dict[str, Any], *, original_gap_id: str) -> dict[str, Any]:
    return dict((state.get("blocked_design_gaps") or {}).get(original_gap_id) or {})


def _is_blocked(state: dict[str, Any], *, source: str, item_id: str) -> bool:
    if source == "DESIGN_GAP":
        return item_id in (state.get("blocked_design_gaps") or {})
    if source == "BACKLOG_ITEM":
        return item_id in (state.get("blocked_items") or {})
    return False


def _blocked_entry(state: dict[str, Any], *, source: str, item_id: str) -> dict[str, Any]:
    if source == "DESIGN_GAP":
        return dict((state.get("blocked_design_gaps") or {}).get(item_id) or {})
    if source == "BACKLOG_ITEM":
        return dict((state.get("blocked_items") or {}).get(item_id) or {})
    return {}


def _is_recoverable_blocked_entry(entry: dict[str, Any]) -> bool:
    if not entry:
        return False
    if str(entry.get("reason") or "").strip() != "implementation_blocked":
        return False
    route = str(entry.get("recovery_route") or "").strip()
    if not route or route == "TERMINAL_BLOCKED":
        return False
    if not str(entry.get("recovery_reason") or "").strip():
        return False
    if not str(entry.get("recovery_event_id") or "").strip():
        return False
    return True


def _record_original(
    state: dict[str, Any],
    *,
    original_gap_id: str,
    selection_path: Path,
    selected_source: str,
    selected_id: str,
    status: str,
    prerequisite_status: str,
    reason: str,
    event: str | None = None,
) -> None:
    blocked = dict(state.get("blocked_design_gaps") or {})
    entry = dict(blocked.get(original_gap_id) or {})
    if not entry:
        raise SystemExit(f"Original blocked design gap is missing from run state: {original_gap_id}")
    entry["recovery_status"] = status
    entry["prerequisite_recovery_status"] = prerequisite_status
    if selected_id:
        entry["waiting_on_prerequisite_gap_id"] = selected_id
        entry["waiting_on_prerequisite_source"] = selected_source
    entry["prerequisite_selection_bundle_path"] = selection_path.as_posix()
    entry["original_blocked_gap_id"] = original_gap_id
    entry["prerequisite_recovery_reason"] = reason
    entry["prerequisite_recovery_recorded_at_utc"] = _timestamp()
    edge = edge_from_blocked_entry(WorkRef(source="DESIGN_GAP", id=original_gap_id), entry)
    if edge is None and selected_id:
        edge = normalize_edge(
            {
                "blocked_work": {"source": "DESIGN_GAP", "id": original_gap_id},
                "blocker_work": {"source": selected_source, "id": selected_id},
                "relation": "requires_completion",
                "reason_code": reason or "prerequisite_required",
                "ready_when": {"kind": "completed", "source": selected_source, "id": selected_id},
                "retry_target": {"source": "DESIGN_GAP", "id": original_gap_id},
            }
        )
    if edge is not None:
        edge_json = edge_to_json(edge)
        if status == "RETRY_READY":
            edge_json["status"] = "ready_to_retry"
        elif prerequisite_status == "COMPLETED":
            edge_json["status"] = "completed"
        elif prerequisite_status == "BLOCKED_RECOVERABLE":
            edge_json["status"] = "blocked"
        entry["recovery_dependency_edge"] = edge_json
    blocked[original_gap_id] = entry
    state["blocked_design_gaps"] = blocked
    event_name = event or (
        "prerequisite_recovery_satisfied" if status == "RETRY_READY" else "prerequisite_recovery_blocked"
    )
    state.setdefault("history", []).append(
        {
            "event": event_name,
            "item_id": original_gap_id,
            "source": "DESIGN_GAP",
            "reason": reason,
            "recovery_status": status,
            "prerequisite_recovery_status": prerequisite_status,
            "waiting_on_prerequisite_gap_id": selected_id,
            "waiting_on_prerequisite_source": selected_source,
            "timestamp_utc": _timestamp(),
        }
    )


def _record_recovery_continues(
    state: dict[str, Any],
    *,
    original_gap_id: str,
    selection_path: Path,
    selected_source: str,
    selected_id: str,
    reason: str,
) -> None:
    _record_original(
        state,
        original_gap_id=original_gap_id,
        selection_path=selection_path,
        selected_source=selected_source,
        selected_id=selected_id,
        status="PREREQUISITE_WORK_PENDING",
        prerequisite_status="RECOVERY_CONTINUES",
        reason=reason,
        event="prerequisite_recovery_continues",
    )


def _record_original_completed(
    state: dict[str, Any],
    *,
    original_gap_id: str,
    selected_source: str,
    selected_id: str,
    reason: str,
) -> None:
    state.setdefault("history", []).append(
        {
            "event": "prerequisite_recovery_satisfied",
            "item_id": original_gap_id,
            "source": "DESIGN_GAP",
            "reason": reason,
            "recovery_status": "RETRY_READY",
            "prerequisite_recovery_status": "COMPLETED",
            "waiting_on_prerequisite_gap_id": selected_id,
            "waiting_on_prerequisite_source": selected_source,
            "timestamp_utc": _timestamp(),
        }
    )


def _finish(
    *,
    state_path: Path,
    state: dict[str, Any],
    summary_path: Path,
    drain_status_path: Path,
    summary: dict[str, Any],
    drain_status: str,
) -> int:
    summary = dict(summary)
    summary["drain_status"] = drain_status
    _save_json(state_path, state)
    _save_json(summary_path, summary)
    _write_text(drain_status_path, drain_status)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pre-selection-bundle-path", required=True)
    parser.add_argument("--selection-bundle-path", required=True)
    parser.add_argument("--selected-work-status-path", required=True)
    parser.add_argument("--run-state-path", required=True)
    parser.add_argument("--summary-path", required=True)
    parser.add_argument("--drain-status-path", required=True)
    args = parser.parse_args()

    pre_selection = _load_json(Path(args.pre_selection_bundle_path))
    selection_path = Path(args.selection_bundle_path)
    selection = _load_json(selection_path)
    state_path = Path(args.run_state_path)
    state = _load_json(state_path)

    if str(pre_selection.get("pre_selection_route") or "").strip() != "SELECT_PREREQUISITE_WORK":
        raise SystemExit("Prerequisite recovery recorder requires SELECT_PREREQUISITE_WORK")
    original_gap_id = str(pre_selection.get("design_gap_id") or "").strip()
    if not original_gap_id:
        raise SystemExit("Missing original blocked design_gap_id")
    if str(pre_selection.get("recovery_route") or "").strip() != "PREREQUISITE_GAP_REQUIRED":
        raise SystemExit("Prerequisite recovery recorder requires PREREQUISITE_GAP_REQUIRED")

    selected_status = _read_status(Path(args.selected_work_status_path))
    selected_source, selected_id = _selected_work(selection)
    relation = str(selection.get("prerequisite_relation") or "").strip()
    original = _original_entry(state, original_gap_id=original_gap_id)
    original_edge = edge_from_blocked_entry(WorkRef(source="DESIGN_GAP", id=original_gap_id), original)

    completed_source, completed_id = _completed_waiting_prerequisite(state, original_gap_id=original_gap_id)
    if completed_id:
        _record_original(
            state,
            original_gap_id=original_gap_id,
            selection_path=selection_path,
            selected_source=completed_source,
            selected_id=completed_id,
            status="RETRY_READY",
            prerequisite_status="COMPLETED",
            reason="prerequisite_completed",
        )
        return _finish(
            state_path=state_path,
            state=state,
            summary_path=Path(args.summary_path),
            drain_status_path=Path(args.drain_status_path),
            summary={
                "record_status": "RETRY_READY",
                "original_blocked_gap_id": original_gap_id,
                "selected_prerequisite_id": completed_id,
                "selected_prerequisite_source": completed_source,
                "reason": "prerequisite_completed",
            },
            drain_status="CONTINUE",
        )

    if (
        original_edge is not None
        and original_edge.blocker_work is not None
        and any(ref.source == selected_source and ref.id == selected_id for ref in original_edge.downstream_work)
        and not _is_completed(state, source=original_edge.blocker_work.source, item_id=original_edge.blocker_work.id)
    ):
        reason = "selected_downstream_before_blocker_ready"
        _record_original(
            state,
            original_gap_id=original_gap_id,
            selection_path=selection_path,
            selected_source=original_edge.blocker_work.source,
            selected_id=original_edge.blocker_work.id,
            status="PREREQUISITE_WORK_PENDING",
            prerequisite_status="WAITING_ON_PREREQUISITE",
            reason=reason,
            event="prerequisite_recovery_continues",
        )
        return _finish(
            state_path=state_path,
            state=state,
            summary_path=Path(args.summary_path),
            drain_status_path=Path(args.drain_status_path),
            summary={
                "record_status": "RECOVERY_CONTINUES",
                "original_blocked_gap_id": original_gap_id,
                "selected_prerequisite_id": original_edge.blocker_work.id,
                "selected_prerequisite_source": original_edge.blocker_work.source,
                "reason": reason,
            },
            drain_status="CONTINUE",
        )

    reason = ""
    if not selected_source or not selected_id:
        reason = "prerequisite_selector_declined"
    elif not relation:
        reason = "missing_prerequisite_relation"
    elif selected_source == "DESIGN_GAP" and selected_id == original_gap_id:
        if _is_completed(state, source=selected_source, item_id=selected_id):
            _record_original_completed(
                state,
                original_gap_id=original_gap_id,
                selected_source=selected_source,
                selected_id=selected_id,
                reason="original_gap_completed",
            )
            return _finish(
                state_path=state_path,
                state=state,
                summary_path=Path(args.summary_path),
                drain_status_path=Path(args.drain_status_path),
                summary={
                    "record_status": "RETRY_READY",
                    "original_blocked_gap_id": original_gap_id,
                    "selected_prerequisite_id": selected_id,
                    "selected_prerequisite_source": selected_source,
                    "reason": "original_gap_completed",
                },
                drain_status="CONTINUE",
            )
        reason = "circular_prerequisite_relation"
    elif _is_completed(state, source=selected_source, item_id=selected_id):
        _record_original(
            state,
            original_gap_id=original_gap_id,
            selection_path=selection_path,
            selected_source=selected_source,
            selected_id=selected_id,
            status="RETRY_READY",
            prerequisite_status="COMPLETED",
            reason="prerequisite_completed",
        )
        return _finish(
            state_path=state_path,
            state=state,
            summary_path=Path(args.summary_path),
            drain_status_path=Path(args.drain_status_path),
            summary={
                "record_status": "RETRY_READY",
                "original_blocked_gap_id": original_gap_id,
                "selected_prerequisite_id": selected_id,
                "selected_prerequisite_source": selected_source,
                "reason": "prerequisite_completed",
            },
            drain_status="CONTINUE",
        )
    elif _is_blocked(state, source=selected_source, item_id=selected_id):
        entry = _blocked_entry(state, source=selected_source, item_id=selected_id)
        if _is_recoverable_blocked_entry(entry):
            reason = "selected_prerequisite_blocked_recoverable"
            _record_original(
                state,
                original_gap_id=original_gap_id,
                selection_path=selection_path,
                selected_source=selected_source,
                selected_id=selected_id,
                status="PREREQUISITE_WORK_PENDING",
                prerequisite_status="BLOCKED_RECOVERABLE",
                reason=reason,
                event="prerequisite_recovery_pending_on_blocked_prerequisite",
            )
            return _finish(
                state_path=state_path,
                state=state,
                summary_path=Path(args.summary_path),
                drain_status_path=Path(args.drain_status_path),
                summary={
                    "record_status": "WAITING_ON_RECOVERABLE_PREREQUISITE",
                    "original_blocked_gap_id": original_gap_id,
                    "selected_prerequisite_id": selected_id,
                    "selected_prerequisite_source": selected_source,
                    "reason": reason,
                    "selected_prerequisite_recovery_route": str(entry.get("recovery_route") or "").strip(),
                    "selected_prerequisite_recovery_reason": str(entry.get("recovery_reason") or "").strip(),
                },
                drain_status="CONTINUE",
            )
        if str(entry.get("recovery_route") or "").strip() == "TERMINAL_BLOCKED":
            if str(entry.get("recovery_reason") or "").strip() == "user_decision_required":
                reason = "selected_prerequisite_user_input_required"
            else:
                reason = "selected_prerequisite_needs_recovery"
        else:
            reason = "selected_prerequisite_blocked_without_recoverable_metadata"
    elif selected_status != "CONTINUE":
        reason = f"selected_prerequisite_status_{selected_status.lower() or 'missing'}"
    else:
        reason = "selected_prerequisite_completion_evidence_missing"

    _record_recovery_continues(
        state,
        original_gap_id=original_gap_id,
        selection_path=selection_path,
        selected_source=selected_source,
        selected_id=selected_id,
        reason=reason,
    )
    return _finish(
        state_path=state_path,
        state=state,
        summary_path=Path(args.summary_path),
        drain_status_path=Path(args.drain_status_path),
        summary={
            "record_status": "RECOVERY_CONTINUES",
            "original_blocked_gap_id": original_gap_id,
            "selected_prerequisite_id": selected_id,
            "selected_prerequisite_source": selected_source,
            "reason": reason,
        },
        drain_status="CONTINUE",
    )


if __name__ == "__main__":
    raise SystemExit(main())
