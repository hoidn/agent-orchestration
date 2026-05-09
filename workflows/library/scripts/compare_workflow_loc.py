#!/usr/bin/env python3
"""Compare total workflow LOC between legacy and v2.14 file groups."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def _count_loc(path: Path) -> int:
    return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())


def _resolved_paths(values: list[str]) -> list[Path]:
    return [Path(value).resolve() for value in values]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--old", action="append", required=True, dest="old_files")
    parser.add_argument("--new", action="append", required=True, dest="new_files")
    parser.add_argument("--require-total-reduction-pct", type=float, default=None)
    args = parser.parse_args()

    old_files = _resolved_paths(args.old_files)
    new_files = _resolved_paths(args.new_files)

    old_counts = [{"path": path.as_posix(), "loc": _count_loc(path)} for path in old_files]
    new_counts = [{"path": path.as_posix(), "loc": _count_loc(path)} for path in new_files]

    old_total = sum(entry["loc"] for entry in old_counts)
    new_total = sum(entry["loc"] for entry in new_counts)
    absolute_delta = old_total - new_total
    percent_delta = 0.0 if old_total == 0 else round((absolute_delta / old_total) * 100.0, 2)

    payload = {
        "old_files": [entry["path"] for entry in old_counts],
        "new_files": [entry["path"] for entry in new_counts],
        "old_breakdown": old_counts,
        "new_breakdown": new_counts,
        "totals": {
            "old_loc": old_total,
            "new_loc": new_total,
            "absolute_delta": absolute_delta,
            "percent_delta": percent_delta,
        },
        "meets_threshold": True,
    }

    threshold = args.require_total_reduction_pct
    if threshold is not None:
        payload["required_total_reduction_pct"] = threshold
        payload["meets_threshold"] = percent_delta >= threshold

    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload["meets_threshold"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
