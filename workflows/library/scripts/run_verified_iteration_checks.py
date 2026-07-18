#!/usr/bin/env python3
"""Run the fixed verified-iteration check suite and package the iteration diff.

Contract: docs/design/verified_iteration_drain.md (Component Contracts).
Verify status is data, not a process error: the script exits 0 for GREEN and
RED alike and reserves nonzero exits for setup failures.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path

REPO_ROOT = Path.cwd()


def _git(*argv: str) -> str:
    result = subprocess.run(["git", *argv], cwd=REPO_ROOT, text=True, capture_output=True)
    if result.returncode != 0:
        raise SystemExit(f"git {' '.join(argv)} failed: {result.stderr.strip()}")
    return result.stdout


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check-commands-path", required=True)
    parser.add_argument("--base-sha", required=True)
    parser.add_argument("--iteration-dir", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    try:
        commands = json.loads((REPO_ROOT / args.check_commands_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"Invalid check commands file {args.check_commands_path}: {exc}")
    if not isinstance(commands, list) or not commands or not all(isinstance(c, str) and c.strip() for c in commands):
        raise SystemExit(f"Check commands must be a non-empty JSON list of strings: {args.check_commands_path}")

    iteration_dir = REPO_ROOT / args.iteration_dir
    iteration_dir.mkdir(parents=True, exist_ok=True)

    verify_status = "GREEN"
    log_lines: list[str] = []
    for command in commands:
        result = subprocess.run(command, cwd=REPO_ROOT, shell=True, text=True, capture_output=True)
        log_lines.append(f"$ {command}\nexit {result.returncode}\n{result.stdout}{result.stderr}\n")
        if result.returncode != 0:
            verify_status = "RED"
    checks_log = iteration_dir / "checks-log.txt"
    checks_log.write_text("".join(log_lines), encoding="utf-8")

    head_sha = _git("rev-parse", "HEAD").strip()
    commits_landed = "false" if head_sha == args.base_sha else "true"
    commit_log = _git("log", "--oneline", f"{args.base_sha}..{head_sha}") if commits_landed == "true" else ""
    diff = _git("diff", f"{args.base_sha}..{head_sha}") if commits_landed == "true" else ""
    review_package = iteration_dir / "review-package.md"
    review_package.write_text(
        "## Commits\n\n" + commit_log + "\n## Diff\n\n```diff\n" + diff + "\n```\n",
        encoding="utf-8",
    )

    payload = {
        "verify_status": verify_status,
        "commits_landed": commits_landed,
        "head_sha": head_sha,
        "checks_log_path": checks_log.relative_to(REPO_ROOT).as_posix(),
        "review_package_path": review_package.relative_to(REPO_ROOT).as_posix(),
    }
    (REPO_ROOT / args.output).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    runtime_bundle_path = os.environ.get("ORCHESTRATOR_OUTPUT_BUNDLE_PATH")
    if runtime_bundle_path:
        runtime_bundle = REPO_ROOT / runtime_bundle_path
        runtime_bundle.parent.mkdir(parents=True, exist_ok=True)
        runtime_bundle.write_text(
            json.dumps(
                {
                    "verify_status": payload["verify_status"],
                    "commits_landed": payload["commits_landed"],
                    "checks_log_path": payload["checks_log_path"],
                    "review_package_path": payload["review_package_path"],
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
