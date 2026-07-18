#!/usr/bin/env python3
"""Derive one verified-iteration status from measured outcomes and record it.

Contract: docs/design/verified_iteration_drain.md (status table and loop
control). Status is a pure function of measurements; this script never
rewrites prior ledger lines or status tokens, and never mutates the tree.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

REPO_ROOT = Path.cwd()

STALL_STATUSES = {"NO_CHANGE", "CHECKS_RED", "FINDINGS"}


def _read_token(path_value: str, *, default: str = "SKIPPED") -> str:
    path = REPO_ROOT / path_value
    if not path.is_file():
        return default
    return path.read_text(encoding="utf-8").strip() or default


# Branch order is normative: the status rows are not mutually exclusive, so
# evaluation order disambiguates (see docs/design/verified_iteration_drain.md,
# "Iteration status" — precedence CHECKS_RED > FINDINGS > DONE >
# BLOCKED_ON_USER > ACCEPTED > NO_CHANGE).
def _derive_status(
    *,
    verify: str,
    commits: str,
    verdict: str,
    review: str,
    done_review: str,
    has_blocked_notes: bool,
) -> str:
    if verify == "RED":
        return "CHECKS_RED"
    if review == "FINDINGS":
        return "FINDINGS"
    if verdict == "DONE":
        return "DONE" if done_review == "APPROVE" else "FINDINGS"
    if verdict == "BLOCKED_ON_USER" and has_blocked_notes:
        return "BLOCKED_ON_USER"
    if commits == "true" and review == "APPROVE":
        return "ACCEPTED"
    return "NO_CHANGE"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--iteration", required=True)
    parser.add_argument("--base-sha", required=True)
    parser.add_argument("--checks-result-path", required=True)
    parser.add_argument("--review-decision-path", required=True)
    parser.add_argument("--done-review-decision-path", required=True)
    parser.add_argument("--worker-verdict-path", required=True)
    parser.add_argument("--worker-note-path", required=True)
    parser.add_argument("--blocked-notes-dir", required=True)
    parser.add_argument("--ledger-path", required=True)
    parser.add_argument("--statuses-path", required=True)
    parser.add_argument("--stall-limit", required=True)
    parser.add_argument("--summary-path", required=True)
    parser.add_argument("--drain-status-path", required=True)
    args = parser.parse_args()

    checks = json.loads((REPO_ROOT / args.checks_result_path).read_text(encoding="utf-8"))
    verdict = _read_token(args.worker_verdict_path, default="")
    if verdict not in {"CONTINUE", "DONE", "BLOCKED_ON_USER"}:
        raise SystemExit(f"Invalid or missing worker verdict: {verdict!r}")
    try:
        stall_limit = int(args.stall_limit)
    except ValueError:
        stall_limit = 0
    if stall_limit < 1:
        raise SystemExit(f"--stall-limit must be a positive integer, got {args.stall_limit!r}")
    note = _read_token(args.worker_note_path, default="")
    blocked_dir = REPO_ROOT / args.blocked_notes_dir
    has_blocked_notes = blocked_dir.is_dir() and any(blocked_dir.glob("BLOCKED-*.md"))

    status = _derive_status(
        verify=str(checks.get("verify_status") or ""),
        commits=str(checks.get("commits_landed") or ""),
        verdict=verdict,
        review=_read_token(args.review_decision_path),
        done_review=_read_token(args.done_review_decision_path),
        has_blocked_notes=has_blocked_notes,
    )

    statuses_path = REPO_ROOT / args.statuses_path
    statuses_path.parent.mkdir(parents=True, exist_ok=True)
    tokens = statuses_path.read_text(encoding="utf-8").split() if statuses_path.is_file() else []

    head_sha = str(checks.get("head_sha") or "")
    ledger_path = REPO_ROOT / args.ledger_path
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    ledger_lines = [
        line for line in ledger_path.read_text(encoding="utf-8").splitlines() if line.strip()
    ] if ledger_path.is_file() else []

    # orchestrator resume re-runs the first non-terminal step of an iteration,
    # so Record may be re-invoked for an iteration whose ledger line and
    # status token already landed; detect that and skip re-appending so a
    # resumed run cannot double-record the same iteration.
    already_recorded = bool(ledger_lines) and ledger_lines[-1].startswith(f"iter {args.iteration} | ")
    if already_recorded:
        status = tokens[-1] if tokens else status
    else:
        tokens.append(status)
        with statuses_path.open("a", encoding="utf-8") as handle:
            handle.write(status + "\n")
        with ledger_path.open("a", encoding="utf-8") as handle:
            handle.write(f"iter {args.iteration} | {status} | {args.base_sha[:7]}..{head_sha[:7]} | {note}\n")

    if status == "DONE":
        drain_status = "DONE"
    elif status == "BLOCKED_ON_USER":
        drain_status = "BLOCKED_ON_USER"
    elif len(tokens) >= stall_limit and all(token in STALL_STATUSES for token in tokens[-stall_limit:]):
        drain_status = "STALLED"
    else:
        drain_status = "CONTINUE"

    summary = {
        "schema": "verified_iteration_drain_summary/v1",
        "drain_status": drain_status,
        "iterations": len(tokens),
        "statuses": tokens,
        "accepted_count": sum(1 for token in tokens if token in {"ACCEPTED", "DONE"}),
        "blocked_notes": sorted(path.name for path in blocked_dir.glob("BLOCKED-*.md")) if blocked_dir.is_dir() else [],
        "last_note": note,
    }
    summary_path = REPO_ROOT / args.summary_path
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")

    drain_status_path = REPO_ROOT / args.drain_status_path
    drain_status_path.parent.mkdir(parents=True, exist_ok=True)
    drain_status_path.write_text(drain_status + "\n", encoding="utf-8")
    runtime_bundle_path = os.environ.get("ORCHESTRATOR_OUTPUT_BUNDLE_PATH")
    if runtime_bundle_path:
        runtime_bundle = REPO_ROOT / runtime_bundle_path
        runtime_bundle.parent.mkdir(parents=True, exist_ok=True)
        runtime_bundle.write_text(
            json.dumps(
                {
                    "drain_status": drain_status,
                    "drain_summary_path": args.summary_path,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
