#!/usr/bin/env python3
"""Write a validated Lisp frontend drain status scalar."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ALLOWED = {"CONTINUE", "DONE", "BLOCKED"}


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _load_run_state(path: Path) -> dict[str, Any]:
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


def _save_run_state(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def _record_drain_status(
    *,
    run_state_path: str,
    status: str,
    reason: str,
    summary_path: str,
) -> None:
    path = Path(run_state_path)
    state = _load_run_state(path)
    state["drain_status"] = status
    if reason:
        state["drain_status_reason"] = reason
    else:
        state.pop("drain_status_reason", None)
    state.setdefault("history", []).append(
        {
            "event": "drain_status",
            "status": status,
            "reason": reason,
            "summary_path": summary_path,
            "timestamp_utc": _timestamp(),
        }
    )
    _save_run_state(path, state)


def _write_status(
    *,
    status: str,
    output: str,
    run_state_path: str = "",
    summary_path: str = "",
    reason: str = "",
) -> None:
    if status not in ALLOWED:
        raise SystemExit(f"Unexpected drain status: {status}")
    target = Path(output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(status + "\n", encoding="utf-8")
    if run_state_path:
        _record_drain_status(
            run_state_path=run_state_path,
            status=status,
            reason=reason,
            summary_path=summary_path or output,
        )
    bundle_path = os.environ.get("ORCHESTRATOR_OUTPUT_BUNDLE_PATH", "").strip()
    if bundle_path:
        bundle = Path(bundle_path)
        bundle.parent.mkdir(parents=True, exist_ok=True)
        bundle.write_text(
            json.dumps(
                {
                    "run_state": run_state_path,
                    "summary": summary_path or output,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )


def _run_adapter_payload(payload: dict[str, Any]) -> int:
    status = str(payload.get("status") or "").strip()
    reason = str(payload.get("reason") or "").strip()
    summary_path = str(payload.get("summary_path") or "").strip()
    run_state_path = str(payload.get("run_state_path") or "").strip()
    if not all((status, summary_path, run_state_path)):
        raise SystemExit("adapter payload requires run_state_path, status, and summary_path")
    _write_status(
        status=status,
        output=summary_path,
        run_state_path=run_state_path,
        summary_path=summary_path,
        reason=reason,
    )
    return 0


def main() -> int:
    if len(sys.argv) == 2 and sys.argv[1].lstrip().startswith("{"):
        return _run_adapter_payload(json.loads(sys.argv[1]))

    parser = argparse.ArgumentParser()
    parser.add_argument("--status", required=True, choices=sorted(ALLOWED))
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    _write_status(status=args.status, output=args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
