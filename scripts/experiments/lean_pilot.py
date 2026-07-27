#!/usr/bin/env python3
"""Thin command-line entry point for the bounded lean-pilot utilities."""

from __future__ import annotations

import argparse
from dataclasses import asdict
from pathlib import Path
from typing import Sequence

from orchestrator.experiments.contracts import (
    canonical_json_bytes,
    canonical_sha256,
    load_record,
)
from orchestrator.experiments.runner import run_block
from orchestrator.experiments.workspace import freeze_product


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)

    validate = commands.add_parser("validate-lock")
    validate.add_argument("--lock", type=Path, required=True)

    run = commands.add_parser("run-block")
    run.add_argument("--lock", type=Path, required=True)
    run.add_argument("--block-id", required=True)
    run.add_argument("--work-root", type=Path, required=True)
    run.add_argument("--evidence-root", type=Path, required=True)

    freeze = commands.add_parser("freeze-product")
    freeze.add_argument("--root", type=Path, required=True)
    freeze.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "validate-lock":
        lock = load_record(args.lock, expected_kind="pilot_lock.v1")
        print(canonical_sha256(lock))
        return 0
    if args.command == "run-block":
        lock = load_record(args.lock, expected_kind="pilot_lock.v1")
        attempt = run_block(
            lock=lock,
            block_id=args.block_id,
            work_root=args.work_root,
            evidence_root=args.evidence_root,
        )
        print(canonical_json_bytes(attempt.record).decode("utf-8"))
        return 0

    manifest = freeze_product(args.root, ())
    output = {
        "digest": manifest.digest,
        "entries": [asdict(entry) for entry in manifest.entries],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(canonical_json_bytes(output))
    print(manifest.digest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
