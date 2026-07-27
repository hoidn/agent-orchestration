from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--mode",
        choices=(
            "success",
            "nonzero",
            "timeout",
            "spawn-child",
            "prelaunch-fail",
        ),
        default="success",
    )
    parser.add_argument("--result-file", type=Path, required=True)
    parser.add_argument("--provider-call-count", type=int, required=True)
    parser.add_argument("--terminal-outcome", default="COMPLETED")
    parser.add_argument("--apparatus-root", type=Path, required=True)
    parser.add_argument("--task-path", type=Path, required=True)
    parser.add_argument("--provider-config", type=Path, required=True)
    parser.add_argument("--prompt-config", type=Path, required=True)
    parser.add_argument("--command-config", type=Path, required=True)
    parser.add_argument(
        "--result-fault",
        choices=(
            "none",
            "unknown",
            "duplicate",
            "missing",
            "missing-terminal",
            "wrong-type",
        ),
        default="none",
    )
    parser.add_argument("--wait-seconds", type=int, default=300)
    args = parser.parse_args()

    if args.mode == "prelaunch-fail":
        return 23

    source = Path("README.md").read_bytes()
    apparatus_root = args.apparatus_root.resolve(strict=True)
    apparatus_assets = {}
    for role, path in (
        ("task", args.task_path),
        ("provider_config", args.provider_config),
        ("prompt_config", args.prompt_config),
        ("command_config", args.command_config),
    ):
        resolved = path.resolve(strict=True)
        if not resolved.is_relative_to(apparatus_root):
            raise SystemExit(f"{role} is outside the staged apparatus root")
        apparatus_assets[role] = {
            "path": resolved.relative_to(apparatus_root).as_posix(),
            "sha256": hashlib.sha256(resolved.read_bytes()).hexdigest(),
        }
    launch_environment = {
        item.split(b"=", 1)[0].decode("utf-8")
        for item in Path("/proc/self/environ").read_bytes().split(b"\0")
        if item
    }
    print(
        json.dumps(
            {
                "fixture_event": "started",
                "started_monotonic_ns": time.monotonic_ns(),
                "process_group_id": os.getpgrp(),
                "cwd": str(Path.cwd()),
                "argv": sys.argv,
                "source_sha256": hashlib.sha256(source).hexdigest(),
                "apparatus_root": apparatus_root.as_posix(),
                "apparatus_assets": apparatus_assets,
                "environment_key_presence": [
                    {"name": name, "present": True}
                    for name in sorted(launch_environment)
                ],
            },
            sort_keys=True,
        ),
        flush=True,
    )
    Path("fixture-product.txt").write_text("lean pilot fixture\n", encoding="utf-8")
    runtime = Path(".pilot/runtime")
    runtime.mkdir(parents=True, exist_ok=True)
    (runtime / "volatile.txt").write_text(
        str(Path.cwd().resolve()),
        encoding="utf-8",
    )
    args.result_file.parent.mkdir(parents=True, exist_ok=True)
    result = {
        "terminal_outcome": args.terminal_outcome,
        "provider_call_count": args.provider_call_count,
        "token_counts": {"input": 0, "output": 0},
        "cost": {"cost_microunits": 0, "currency": "USD"},
    }
    if args.result_fault == "unknown":
        result["unexpected"] = True
    elif args.result_fault == "missing":
        del result["provider_call_count"]
    elif args.result_fault == "missing-terminal":
        del result["terminal_outcome"]
    elif args.result_fault == "wrong-type":
        result["provider_call_count"] = str(args.provider_call_count)

    if args.result_fault == "duplicate":
        result_text = (
            '{"cost":{"cost_microunits":0,"currency":"USD"},'
            f'"provider_call_count":{args.provider_call_count},'
            '"provider_call_count":999,'
            f'"terminal_outcome":"{args.terminal_outcome}",'
            '"token_counts":{"input":0,"output":0}}'
        )
    else:
        result_text = json.dumps(result, sort_keys=True)
    args.result_file.write_text(result_text, encoding="utf-8")

    if args.mode == "nonzero":
        return 17
    if args.mode == "timeout":
        time.sleep(args.wait_seconds)
    elif args.mode == "spawn-child":
        child = subprocess.Popen(
            [
                sys.executable,
                "-c",
                f"import time; time.sleep({args.wait_seconds})",
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        print(
            json.dumps(
                {
                    "fixture_event": "spawned-child",
                    "child_pid": child.pid,
                    "process_group_id": os.getpgrp(),
                },
                sort_keys=True,
            ),
            flush=True,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
