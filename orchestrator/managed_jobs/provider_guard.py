"""Managed provider guard process."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

from .shims import managed_shim_environment, materialize_shims


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--policy", required=True)
    parser.add_argument("--audit-path", required=True)
    parser.add_argument("--state-root", required=True)
    parser.add_argument("--pending-policy", required=True)
    parser.add_argument("--backend", required=True)
    parser.add_argument("--shim-dir", required=True)
    parser.add_argument("--watch-root", action="append", default=[])
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    if args.command and args.command[0] == "--":
        args.command = args.command[1:]
    if not args.command:
        parser.error("inner provider command is required")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    shim_dir = Path(args.shim_dir)
    materialize_shims(shim_dir)
    env = managed_shim_environment(os.environ.copy(), shim_dir)
    env.update(
        {
            "MANAGED_JOB_POLICY": args.policy,
            "MANAGED_JOB_AUDIT_PATH": args.audit_path,
            "MANAGED_JOB_STATE_ROOT": args.state_root,
            "MANAGED_JOB_PENDING_POLICY": args.pending_policy,
            "MANAGED_JOB_BACKEND": args.backend,
            "MANAGED_JOB_WATCH_ROOTS": os.pathsep.join(args.watch_root),
        }
    )
    completed = subprocess.run(args.command, env=env)
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
