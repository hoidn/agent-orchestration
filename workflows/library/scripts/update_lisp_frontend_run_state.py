#!/usr/bin/env python3
"""Maintain durable run state for the Lisp frontend autonomous drain."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _load(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {
            "schema": "lisp_frontend_autonomous_drain_run_state/v1",
            "completed_items": [],
            "completed_design_gaps": [],
            "blocked_items": {},
            "blocked_design_gaps": {},
            "history": [],
        }
    return json.loads(path.read_text(encoding="utf-8"))


def _save(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def _record_completed(state: dict[str, Any], *, item_id: str, source: str) -> None:
    key = "completed_design_gaps" if source == "DESIGN_GAP" else "completed_items"
    values = list(state.get(key, []))
    if item_id not in values:
        values.append(item_id)
    state[key] = values
    state.setdefault("history", []).append(
        {"event": "completed", "item_id": item_id, "source": source, "timestamp_utc": _timestamp()}
    )


def _record_blocked(state: dict[str, Any], *, item_id: str, source: str, reason: str) -> None:
    key = "blocked_design_gaps" if source == "DESIGN_GAP" else "blocked_items"
    blocked = dict(state.get(key, {}))
    blocked[item_id] = {"reason": reason, "timestamp_utc": _timestamp()}
    state[key] = blocked
    state.setdefault("history", []).append(
        {"event": "blocked", "item_id": item_id, "source": source, "reason": reason, "timestamp_utc": _timestamp()}
    )


def _record_design_revision(state: dict[str, Any], *, item_id: str, source: str, reason: str) -> None:
    key = "blocked_design_gaps" if source == "DESIGN_GAP" else "blocked_items"
    blocked = dict(state.get(key, {}))
    blocked.pop(item_id, None)
    state[key] = blocked
    state.setdefault("history", []).append(
        {
            "event": "design_revision",
            "item_id": item_id,
            "source": source,
            "reason": reason,
            "timestamp_utc": _timestamp(),
        }
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state-path", required=True)
    sub = parser.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init")
    init.add_argument("--run-id", required=True)
    complete = sub.add_parser("complete")
    complete.add_argument("--item-id", required=True)
    complete.add_argument("--source", required=True, choices=["BACKLOG_ITEM", "DESIGN_GAP", "RECOVERED_IN_PROGRESS"])
    complete.add_argument("--summary-path")
    complete.add_argument("--summary-pointer-path")
    complete.add_argument("--drain-status-path")
    blocked = sub.add_parser("blocked")
    blocked.add_argument("--item-id")
    blocked.add_argument("--selection-path")
    blocked.add_argument("--source", required=True, choices=["BACKLOG_ITEM", "DESIGN_GAP", "RECOVERED_IN_PROGRESS"])
    blocked.add_argument("--reason", required=True)
    blocked.add_argument("--summary-path")
    blocked.add_argument("--summary-pointer-path")
    blocked.add_argument("--drain-status-path")
    design_revision = sub.add_parser("design_revision")
    design_revision.add_argument("--item-id", required=True)
    design_revision.add_argument("--source", required=True, choices=["BACKLOG_ITEM", "DESIGN_GAP", "RECOVERED_IN_PROGRESS"])
    design_revision.add_argument("--reason", required=True)
    design_revision.add_argument("--summary-path")
    design_revision.add_argument("--summary-pointer-path")
    design_revision.add_argument("--drain-status-path")
    args = parser.parse_args()

    path = Path(args.state_path)
    state = _load(path)
    if args.command == "init":
        state["run_id"] = args.run_id
        state.setdefault("started_at_utc", _timestamp())
        state.setdefault("history", []).append({"event": "init", "run_id": args.run_id, "timestamp_utc": _timestamp()})
    elif args.command == "complete":
        _record_completed(state, item_id=args.item_id, source=args.source)
        if args.summary_path:
            summary_path = Path(args.summary_path)
            summary_path.parent.mkdir(parents=True, exist_ok=True)
            summary_path.write_text(
                json.dumps(
                    {
                        "work_item_id": args.item_id,
                        "work_item_source": args.source,
                        "item_status": "COMPLETED",
                        "run_state_path": path.as_posix(),
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            if args.summary_pointer_path:
                pointer_path = Path(args.summary_pointer_path)
                pointer_path.parent.mkdir(parents=True, exist_ok=True)
                pointer_path.write_text(summary_path.as_posix() + "\n", encoding="utf-8")
        if args.drain_status_path:
            status_path = Path(args.drain_status_path)
            status_path.parent.mkdir(parents=True, exist_ok=True)
            status_path.write_text("CONTINUE\n", encoding="utf-8")
    elif args.command == "blocked":
        item_id = args.item_id
        if not item_id and args.selection_path:
            selection = json.loads(Path(args.selection_path).read_text(encoding="utf-8"))
            if args.source == "DESIGN_GAP":
                item_id = str(selection.get("design_gap_id") or "").strip()
            else:
                item_id = str(selection.get("selected_item_id") or "").strip()
        if not item_id:
            raise SystemExit("blocked requires --item-id or --selection-path with an item id")
        _record_blocked(state, item_id=item_id, source=args.source, reason=args.reason)
        if args.summary_path:
            summary_path = Path(args.summary_path)
            summary_path.parent.mkdir(parents=True, exist_ok=True)
            summary_path.write_text(
                json.dumps(
                    {
                        "work_item_id": item_id,
                        "work_item_source": args.source,
                        "item_status": "BLOCKED",
                        "reason": args.reason,
                        "run_state_path": path.as_posix(),
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            if args.summary_pointer_path:
                pointer_path = Path(args.summary_pointer_path)
                pointer_path.parent.mkdir(parents=True, exist_ok=True)
                pointer_path.write_text(summary_path.as_posix() + "\n", encoding="utf-8")
        if args.drain_status_path:
            status_path = Path(args.drain_status_path)
            status_path.parent.mkdir(parents=True, exist_ok=True)
            status_path.write_text("BLOCKED\n", encoding="utf-8")
    elif args.command == "design_revision":
        _record_design_revision(state, item_id=args.item_id, source=args.source, reason=args.reason)
        if args.summary_path:
            summary_path = Path(args.summary_path)
            summary_path.parent.mkdir(parents=True, exist_ok=True)
            summary_path.write_text(
                json.dumps(
                    {
                        "work_item_id": args.item_id,
                        "work_item_source": args.source,
                        "item_status": "DESIGN_REVISED",
                        "reason": args.reason,
                        "run_state_path": path.as_posix(),
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            if args.summary_pointer_path:
                pointer_path = Path(args.summary_pointer_path)
                pointer_path.parent.mkdir(parents=True, exist_ok=True)
                pointer_path.write_text(summary_path.as_posix() + "\n", encoding="utf-8")
        if args.drain_status_path:
            status_path = Path(args.drain_status_path)
            status_path.parent.mkdir(parents=True, exist_ok=True)
            status_path.write_text("CONTINUE\n", encoding="utf-8")
    _save(path, state)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
