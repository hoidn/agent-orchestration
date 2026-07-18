#!/usr/bin/env python3
"""Offline terminal validator for functional prompt-dependency evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from orchestrator.workflow.prompt_dependency_evidence import validate_terminal_evidence


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("aggregate_root", type=Path)
    parser.add_argument("--state-file", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    state_file = args.state_file or args.aggregate_root / "state.json"
    result = validate_terminal_evidence(args.aggregate_root, state_file)
    print(
        json.dumps(
            {
                "status": "passed",
                "index_path": str(result.path),
                "index_sha256": result.index["index_sha256"],
                "created": result.created,
                "initial_state_bytes": result.initial_state_bytes,
                "initial_state_sha256": result.initial_state_sha256,
            },
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
