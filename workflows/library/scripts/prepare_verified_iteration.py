#!/usr/bin/env python3
"""Prepare one verified-iteration: snapshot the git base and regenerate the work order.

Contract: docs/design/verified_iteration_drain.md (Component Contracts).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import subprocess
import tempfile
from pathlib import Path

REPO_ROOT = Path.cwd()


def _git_head() -> str:
    result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, text=True, capture_output=True)
    if result.returncode != 0:
        raise SystemExit(f"Workspace is not a git repository with commits: {result.stderr.strip()}")
    return result.stdout.strip()


def _require_equal_regular_file(path: Path, raw: bytes) -> None:
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except OSError as exc:
        raise SystemExit(f"Refusing unreadable or unsafe ledger input {path}: {exc}") from exc
    if not stat.S_ISREG(os.fstat(fd).st_mode):
        os.close(fd)
        raise SystemExit(f"Refusing non-regular ledger input {path}")
    with os.fdopen(fd, "rb") as handle:
        if handle.read() != raw:
            raise SystemExit(f"Refusing ledger input {path}: existing bytes differ")


def _publish_ledger_input(raw: bytes, inputs_dir: Path) -> Path:
    final = inputs_dir / f"{hashlib.sha256(raw).hexdigest()}.md"
    inputs_dir.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=inputs_dir, prefix=".ledger-input-", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(raw)
        try:
            os.link(temporary, final)
        except FileExistsError:
            _require_equal_regular_file(final, raw)
    finally:
        os.unlink(temporary)
    return final


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--drain-state-root", required=True)
    parser.add_argument("--artifact-work-root", required=True)
    parser.add_argument("--target-design-path", required=True)
    parser.add_argument("--check-commands-path", required=True)
    parser.add_argument("--iteration", type=int, required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    if not (REPO_ROOT / args.target_design_path).is_file():
        raise SystemExit(f"Missing target design: {args.target_design_path}")
    if not (REPO_ROOT / args.check_commands_path).is_file():
        raise SystemExit(f"Missing check commands file: {args.check_commands_path}")

    state_root = REPO_ROOT / args.drain_state_root
    work_root = REPO_ROOT / args.artifact_work_root
    iteration_dir = state_root / "iterations" / str(args.iteration)
    iteration_dir.mkdir(parents=True, exist_ok=True)
    blocked_dir = work_root / "blocked"
    blocked_dir.mkdir(parents=True, exist_ok=True)
    ledger_path = work_root / "ledger.md"
    if not ledger_path.exists():
        ledger_path.write_text("# Verified-iteration drain ledger\n\n", encoding="utf-8")
    ledger_input_path = _publish_ledger_input(ledger_path.read_bytes(), work_root / "ledger-inputs")

    def _rel(path: Path) -> str:
        return path.relative_to(REPO_ROOT).as_posix()

    previous_dir = state_root / "iterations" / str(args.iteration - 1)
    previous_findings = previous_dir / "review-findings.md"
    previous_checks_log = previous_dir / "checks-log.txt"

    order = {
        "iteration": str(args.iteration),
        "base_sha": _git_head(),
        "target_design_path": args.target_design_path,
        "check_commands_path": args.check_commands_path,
        "ledger_path": _rel(ledger_path),
        "ledger_input_path": _rel(ledger_input_path),
        "blocked_notes_dir": _rel(blocked_dir),
        "worker_verdict_path": _rel(iteration_dir / "worker-verdict.txt"),
        "worker_note_path": _rel(iteration_dir / "worker-note.txt"),
        "review_decision_path": _rel(iteration_dir / "review-decision.txt"),
        "review_findings_path": _rel(iteration_dir / "review-findings.md"),
        "done_review_decision_path": _rel(iteration_dir / "done-review-decision.txt"),
        "previous_review_findings_path": _rel(previous_findings) if previous_findings.is_file() else "",
        "previous_checks_log_path": _rel(previous_checks_log) if previous_checks_log.is_file() else "",
        "work_order_path": _rel(iteration_dir / "work-order.json"),
    }
    output = REPO_ROOT / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(order, indent=2) + "\n", encoding="utf-8")
    runtime_bundle_path = os.environ.get("ORCHESTRATOR_OUTPUT_BUNDLE_PATH")
    if runtime_bundle_path:
        runtime_bundle = REPO_ROOT / runtime_bundle_path
        runtime_bundle.parent.mkdir(parents=True, exist_ok=True)
        runtime_bundle.write_text(
            json.dumps(
                {
                    "base_sha": order["base_sha"],
                    "ledger_path": order["ledger_path"],
                    "ledger_input_path": order["ledger_input_path"],
                    "work_order_path": order["work_order_path"],
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
