#!/usr/bin/env python3
"""Report and validate the scoped nanoBragg accumulation slice anchors."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT.parent / "nanoBragg" / "golden_suite_generator" / "nanoBragg.c"
START_LINE = 2839
END_LINE = 3404


def _load_slice() -> tuple[list[str], str]:
    lines = SOURCE.read_text(encoding="utf-8").splitlines()
    snippet_lines = lines[START_LINE - 1 : END_LINE]
    return snippet_lines, "\n".join(snippet_lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--compile-check",
        action="store_true",
        help="Emit scaffold compile-check metadata without compiling anything.",
    )
    args = parser.parse_args(argv)

    snippet_lines, snippet_text = _load_slice()
    payload = {
        "source_path": str(SOURCE),
        "start_line": START_LINE,
        "end_line": END_LINE,
        "line_count": len(snippet_lines),
        "contains": {
            "omega_pixel": "omega_pixel" in snippet_text,
            "capture_fraction": "capture_fraction" in snippet_text,
            "floatimage": "floatimage" in snippet_text,
        },
    }

    if args.compile_check:
        payload["compile_check"] = "not_attempted"
        payload["reason"] = "reference_harness_scaffold_only"

    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
