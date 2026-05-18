#!/usr/bin/env python3
"""Probe an orchestrator run and emit generic watchdog evidence."""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path.cwd()
RUN_ID_RE = re.compile(r"^[A-Za-z0-9_.:-]+$")
TERMINAL_OK = {"completed", "success", "succeeded"}
TERMINAL_BAD = {"failed", "error", "crashed", "cancelled", "canceled"}


def _safe_relpath(value: str, *, under: str | None = None) -> Path:
    path = Path(str(value).strip())
    if path.is_absolute() or ".." in path.parts or not str(path):
        raise SystemExit(f"Unsafe relative path: {value}")
    if under is not None and path.parts[: len(Path(under).parts)] != Path(under).parts:
        raise SystemExit(f"Path {value} is not under {under}")
    return path


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Malformed JSON: {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise SystemExit(f"Expected JSON object: {path}")
    return payload


def _parse_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _failed_steps(state: dict[str, Any]) -> list[dict[str, Any]]:
    failed: list[dict[str, Any]] = []
    steps = state.get("steps") or {}
    if not isinstance(steps, dict):
        return failed
    for name, step in steps.items():
        if not isinstance(step, dict) or step.get("status") != "failed":
            continue
        error = step.get("error") if isinstance(step.get("error"), dict) else {}
        outcome = step.get("outcome") if isinstance(step.get("outcome"), dict) else {}
        failed.append(
            {
                "name": str(name),
                "step_id": step.get("step_id"),
                "error_type": error.get("type"),
                "error_message": error.get("message"),
                "outcome_class": outcome.get("class"),
            }
        )
    return failed


def _running_steps(state: dict[str, Any]) -> list[str]:
    steps = state.get("steps") or {}
    if not isinstance(steps, dict):
        return []
    return [str(name) for name, step in steps.items() if isinstance(step, dict) and step.get("status") == "running"]


def _classify(state: dict[str, Any] | None, *, stale_seconds: int | None, max_stale_seconds: int) -> tuple[str, str]:
    if state is None:
        return "UNKNOWN", "INVESTIGATE"
    status = str(state.get("status") or "unknown").strip().lower()
    failed = _failed_steps(state)
    if status in TERMINAL_OK:
        return "COMPLETED", "NONE"
    if status in TERMINAL_BAD or failed:
        return "FAILED", "RESUME"
    if status == "running":
        if stale_seconds is not None and stale_seconds > max_stale_seconds:
            return "STALLED", "INVESTIGATE"
        return "RUNNING_OK", "NONE"
    return "UNKNOWN", "INVESTIGATE"


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--evidence-root", required=True)
    parser.add_argument("--repair-result-target-path", required=True)
    parser.add_argument("--max-stale-minutes", type=int, default=60)
    parser.add_argument("--policy-path", default="")
    args = parser.parse_args()

    run_id = str(args.run_id).strip()
    if not RUN_ID_RE.fullmatch(run_id):
        raise SystemExit(f"Unsafe run id: {run_id}")
    if args.max_stale_minutes < 1:
        raise SystemExit("--max-stale-minutes must be positive")

    state_path = REPO_ROOT / ".orchestrate/runs" / run_id / "state.json"
    state: dict[str, Any] | None
    state_load_error = ""
    try:
        state = _load_json(state_path)
    except FileNotFoundError:
        state = None
        state_load_error = f"Run state not found: {state_path}"

    now = datetime.now(timezone.utc)
    updated_at = _parse_timestamp(state.get("updated_at")) if state is not None else None
    stale_seconds = int((now - updated_at).total_seconds()) if updated_at is not None else None
    watch_status, recommended_recovery = _classify(
        state,
        stale_seconds=stale_seconds,
        max_stale_seconds=args.max_stale_minutes * 60,
    )
    repair_required = "YES" if watch_status in {"FAILED", "CRASHED", "STALLED", "UNKNOWN"} else "NO"

    evidence_root = REPO_ROOT / _safe_relpath(args.evidence_root, under="artifacts/work")
    evidence_path = evidence_root / f"{run_id}-evidence.json"
    output_rel = _safe_relpath(args.output, under="state")
    repair_result_target = _safe_relpath(args.repair_result_target_path, under="artifacts/work")
    policy_path = ""
    if args.policy_path:
        policy_rel = _safe_relpath(args.policy_path)
        policy_path = policy_rel.as_posix() if (REPO_ROOT / policy_rel).exists() else ""

    evidence = {
        "schema": "orchestrator_run_watchdog_evidence/v1",
        "target_run_id": run_id,
        "state_path": state_path.relative_to(REPO_ROOT).as_posix(),
        "state_load_error": state_load_error,
        "workflow_file": state.get("workflow_file") if state else "",
        "run_status": state.get("status") if state else "missing",
        "watch_status": watch_status,
        "recommended_recovery": recommended_recovery,
        "last_updated_at": state.get("updated_at") if state else "",
        "stale_seconds": stale_seconds,
        "failed_steps": _failed_steps(state or {}),
        "running_steps": _running_steps(state or {}),
        "policy_path": policy_path,
    }
    _write_json(evidence_path, evidence)

    watch = {
        "schema": "orchestrator_run_watch/v1",
        "target_run_id": run_id,
        "watch_status": watch_status,
        "repair_required": repair_required,
        "recommended_recovery": recommended_recovery,
        "state_path": state_path.relative_to(REPO_ROOT).as_posix(),
        "workflow_file": evidence["workflow_file"],
        "run_status": evidence["run_status"],
        "last_updated_at": evidence["last_updated_at"],
        "stale_seconds": stale_seconds if stale_seconds is not None else -1,
        "failed_step_count": len(evidence["failed_steps"]),
        "running_step_count": len(evidence["running_steps"]),
        "evidence_bundle_path": evidence_path.relative_to(REPO_ROOT).as_posix(),
        "repair_result_target_path": repair_result_target.as_posix(),
        "policy_path": policy_path,
    }
    _write_json(REPO_ROOT / output_rel, watch)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
