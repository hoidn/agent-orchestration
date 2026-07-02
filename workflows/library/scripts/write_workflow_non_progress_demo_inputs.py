#!/usr/bin/env python3
"""Write deterministic inputs for the non-progress step-back demo workflow."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping


def _save_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _write_signals(*, output: Path, state_output: Path, run_id: str) -> None:
    _save_json(
        output,
        {
            "schema": "workflow_progress_signals/v1",
            "run_id": run_id,
            "current_iteration": 2,
            "event_count": 2,
            "events": [
                {
                    "iteration": 1,
                    "work_item_id": "demo-item",
                    "phase": "implementation",
                    "outcome": "blocked",
                    "accepted_change": False,
                    "commit_hash": "",
                    "blocker_fingerprint": "demo:blocker",
                    "review_finding_fingerprints": [],
                    "prerequisite_generated": False,
                    "plan_revised": False,
                    "stale_artifact_detected": False,
                },
                {
                    "iteration": 2,
                    "work_item_id": "demo-item",
                    "phase": "implementation",
                    "outcome": "blocked",
                    "accepted_change": False,
                    "commit_hash": "",
                    "blocker_fingerprint": "demo:blocker",
                    "review_finding_fingerprints": [],
                    "prerequisite_generated": False,
                    "plan_revised": False,
                    "stale_artifact_detected": False,
                },
            ],
        },
    )
    _save_json(state_output, {"run_id": run_id, "history": []})


def _write_diagnosis(output: Path) -> None:
    _save_json(
        output,
        {
            "action": "STOP_FOR_EXTERNAL_REVIEW",
            "rationale": "The demo intentionally repeats a blocker to prove step-back recording continues the workflow.",
        },
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    signals = subparsers.add_parser("signals")
    signals.add_argument("--output", required=True)
    signals.add_argument("--state-output", required=True)
    signals.add_argument("--run-id", required=True)
    diagnosis = subparsers.add_parser("diagnosis")
    diagnosis.add_argument("--output", required=True)
    args = parser.parse_args()

    if args.command == "signals":
        _write_signals(output=Path(args.output), state_output=Path(args.state_output), run_id=args.run_id)
    else:
        _write_diagnosis(Path(args.output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
