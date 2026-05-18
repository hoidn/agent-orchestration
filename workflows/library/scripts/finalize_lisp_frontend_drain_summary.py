#!/usr/bin/env python3
"""Write the terminal summary for the Lisp frontend autonomous drain."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _load(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-state-path", required=True)
    parser.add_argument("--drain-status", required=True, choices=["CONTINUE", "DONE", "BLOCKED"])
    parser.add_argument("--summary-path", required=True)
    parser.add_argument("--state-root", required=True)
    args = parser.parse_args()

    run_state_path = Path(args.run_state_path)
    summary_path = Path(args.summary_path)
    state_root = Path(args.state_root)
    run_state = _load(run_state_path)
    summary = {
        "drain_status": args.drain_status,
        "run_state_path": run_state_path.as_posix(),
        "completed_items": run_state.get("completed_items", []),
        "completed_design_gaps": run_state.get("completed_design_gaps", []),
        "blocked_items": run_state.get("blocked_items", {}),
        "blocked_design_gaps": run_state.get("blocked_design_gaps", {}),
        "history_count": len(run_state.get("history", [])),
    }
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    state_root.mkdir(parents=True, exist_ok=True)
    (state_root / "drain_summary_path.txt").write_text(summary_path.as_posix() + "\n", encoding="utf-8")
    (state_root / "final_run_state_path.txt").write_text(run_state_path.as_posix() + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
