#!/usr/bin/env python3
"""Write a validated Lisp frontend blocked-recovery status scalar."""

from __future__ import annotations

import argparse
from pathlib import Path


ALLOWED = {"CONTINUE", "BLOCKED", "RUN_RECOVERED_GAP"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--status", required=True, choices=sorted(ALLOWED))
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(args.status + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
