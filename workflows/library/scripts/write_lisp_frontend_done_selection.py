#!/usr/bin/env python3
"""Write a deterministic DONE selector bundle."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def _safe_state_path(value: str) -> Path:
    path = Path(str(value).strip())
    if not str(path) or path.is_absolute() or ".." in path.parts:
        raise SystemExit(f"Unsafe output path: {value}")
    if path.parts[:1] != ("state",):
        raise SystemExit(f"Output path must be under state: {value}")
    return path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument(
        "--reason",
        default="No selectable manifest work remains; requesting done review.",
    )
    args = parser.parse_args()

    output = _safe_state_path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(
            {
                "selection_status": "DONE",
                "selection_rationale": args.reason,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
