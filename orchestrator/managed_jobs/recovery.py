"""Read-only managed-job recovery and verification."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .audit import AuditEventError, read_events
from .models import ManagedJobOutcome


REQUIRED_JOB_STATE_KEYS = {"job_identity_hash", "state_root", "snapshot", "verify_files"}
FAILED_STATES = {"FAILED", "CANCELLED", "TIMEOUT"}
OUTSTANDING_STATES = {"PENDING", "RUNNING", "SUBMITTED"}


def recover_managed_jobs(audit_path: Path) -> dict[str, Any]:
    """Recover audited managed jobs without resubmitting them."""

    jobs: list[dict[str, Any]] = []
    try:
        events = read_events(audit_path)
    except AuditEventError as exc:
        return _summary(audit_path, ManagedJobOutcome.INVALID, [{"status": "INVALID", "error": str(exc)}])

    submitted = [
        event
        for event in events
        if event.get("event") == "job_submitted" and isinstance(event.get("job_state_path"), str)
    ]
    for event in submitted:
        jobs.append(_recover_one_job(event["job_state_path"]))

    if not jobs:
        return _summary(audit_path, ManagedJobOutcome.COMPLETE, [])
    if any(job.get("status") == "INVALID" for job in jobs):
        return _summary(audit_path, ManagedJobOutcome.INVALID, jobs)
    if any(job.get("status") == "FAILED" for job in jobs):
        return _summary(audit_path, ManagedJobOutcome.FAILED, jobs)
    if any(job.get("status") == "OUTSTANDING" for job in jobs):
        return _summary(audit_path, ManagedJobOutcome.OUTSTANDING, jobs)
    return _summary(audit_path, ManagedJobOutcome.COMPLETE, jobs)


def _recover_one_job(job_state_path: str) -> dict[str, Any]:
    path = Path(job_state_path)
    if not path.exists():
        return {"job_state_path": job_state_path, "status": "INVALID", "error": "job state is missing"}
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"job_state_path": job_state_path, "status": "INVALID", "error": str(exc)}
    if not isinstance(state, dict):
        return {"job_state_path": job_state_path, "status": "INVALID", "error": "job state must be an object"}

    missing = sorted(key for key in REQUIRED_JOB_STATE_KEYS if key not in state)
    snapshot = state.get("snapshot")
    if isinstance(snapshot, dict) and "manifest" not in snapshot:
        missing.append("snapshot.manifest")
    if missing:
        return {
            "job_state_path": job_state_path,
            "status": "INVALID",
            "error": "missing required metadata",
            "missing": missing,
        }

    status = str(state.get("status", "")).upper()
    if status == "COMPLETED":
        return {
            "job_state_path": job_state_path,
            "status": "VERIFIED",
            "terminal_state": "COMPLETED",
        }
    if status in FAILED_STATES:
        return {
            "job_state_path": job_state_path,
            "status": "FAILED",
            "terminal_state": status,
        }
    if status in OUTSTANDING_STATES:
        return {
            "job_state_path": job_state_path,
            "status": "OUTSTANDING",
            "terminal_state": status,
        }
    return {
        "job_state_path": job_state_path,
        "status": "INVALID",
        "error": f"unknown job status '{state.get('status')}'",
    }


def _summary(audit_path: Path, outcome: ManagedJobOutcome, jobs: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "managed_job_outcome": outcome.value,
        "recovery_status": outcome.value,
        "audit_path": str(audit_path),
        "jobs": jobs,
    }
