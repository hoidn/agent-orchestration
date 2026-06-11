#!/usr/bin/env python3
"""Write the terminal summary for the Lisp frontend autonomous drain."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any


def _load(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _write_output_bundle(summary_path: str) -> None:
    bundle_path = os.environ.get("ORCHESTRATOR_OUTPUT_BUNDLE_PATH", "").strip()
    if not bundle_path:
        return
    path = Path(bundle_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"summary": summary_path}, indent=2) + "\n", encoding="utf-8")


def _finalize(*, run_state_path: str, drain_status: str, summary_path: str, state_root: str) -> int:
    if drain_status not in {"CONTINUE", "DONE", "BLOCKED"}:
        raise SystemExit(f"Unexpected drain status: {drain_status}")
    run_state = _load(Path(run_state_path))
    summary_target = Path(summary_path)
    root = Path(state_root)
    summary = {
        "drain_status": drain_status,
        "run_state_path": Path(run_state_path).as_posix(),
        "completed_items": run_state.get("completed_items", []),
        "completed_design_gaps": run_state.get("completed_design_gaps", []),
        "blocked_items": run_state.get("blocked_items", {}),
        "blocked_design_gaps": run_state.get("blocked_design_gaps", {}),
        "history_count": len(run_state.get("history", [])),
    }
    summary_target.parent.mkdir(parents=True, exist_ok=True)
    summary_target.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    root.mkdir(parents=True, exist_ok=True)
    (root / "drain_summary_path.txt").write_text(summary_target.as_posix() + "\n", encoding="utf-8")
    (root / "final_run_state_path.txt").write_text(Path(run_state_path).as_posix() + "\n", encoding="utf-8")
    _write_output_bundle(summary_target.as_posix())
    return 0


def _run_adapter_payload(payload: dict[str, Any]) -> int:
    run_state_path = str(payload.get("run_state_path") or "").strip()
    drain_status = str(payload.get("drain_status") or "").strip()
    summary_path = str(payload.get("summary_path") or "").strip()
    state_root = str(payload.get("state_root") or "").strip()
    if not all((run_state_path, drain_status, summary_path, state_root)):
        raise SystemExit("adapter payload requires run_state_path, drain_status, summary_path, and state_root")
    return _finalize(
        run_state_path=run_state_path,
        drain_status=drain_status,
        summary_path=summary_path,
        state_root=state_root,
    )


def main() -> int:
    if len(sys.argv) == 2 and sys.argv[1].lstrip().startswith("{"):
        return _run_adapter_payload(json.loads(sys.argv[1]))

    parser = argparse.ArgumentParser()
    parser.add_argument("--run-state-path", required=True)
    parser.add_argument("--drain-status", required=True, choices=["CONTINUE", "DONE", "BLOCKED"])
    parser.add_argument("--summary-path", required=True)
    parser.add_argument("--state-root", required=True)
    args = parser.parse_args()

    return _finalize(
        run_state_path=args.run_state_path,
        drain_status=args.drain_status,
        summary_path=args.summary_path,
        state_root=args.state_root,
    )


if __name__ == "__main__":
    raise SystemExit(main())
