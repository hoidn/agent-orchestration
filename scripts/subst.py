#!/usr/bin/env python3
"""
Lightweight template substitution utility for prompt files.

Usage:
  python3 scripts/subst.py --in <template> --out <output> KEY=VALUE [KEY=VALUE ...]

Replaces $KEY or ${KEY} tokens in the template with the provided values using
Python's string.Template.safe_substitute (unprovided tokens remain unchanged).

This keeps prompt file contents literal at provider time per specs/variables.md.
Generate a concrete prompt in a prior step, then reference it via input_file.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from string import Template


def parse_kv(pairs: list[str]) -> dict[str, str]:
    values: dict[str, str] = {}
    for pair in pairs:
        if "=" not in pair:
            print(f"Invalid KV (expected KEY=VALUE): {pair}", file=sys.stderr)
            sys.exit(2)
        k, v = pair.split("=", 1)
        if not k:
            print(f"Invalid KEY in pair: {pair}", file=sys.stderr)
            sys.exit(2)
        values[k] = v
    return values


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Substitute $KEY tokens in a template file")
    ap.add_argument("--in", dest="src", required=True, help="Path to template file")
    ap.add_argument("--out", dest="dst", required=True, help="Path to output file")
    ap.add_argument("kv", nargs="*", help="KEY=VALUE pairs used for substitution")
    args = ap.parse_args(argv)

    src_path = Path(args.src)
    dst_path = Path(args.dst)

    if not src_path.exists():
        print(f"Template not found: {src_path}", file=sys.stderr)
        return 2

    try:
        with src_path.open("r", encoding="utf-8") as f:
            text = f.read()
    except Exception as e:
        print(f"Failed to read template: {e}", file=sys.stderr)
        return 1

    values = parse_kv(args.kv)

    # Perform safe substitution (unprovided tokens remain as-is)
    try:
        rendered = Template(text).safe_substitute(values)
    except Exception as e:
        print(f"Substitution error: {e}", file=sys.stderr)
        return 1

    try:
        dst_path.parent.mkdir(parents=True, exist_ok=True)
        with dst_path.open("w", encoding="utf-8") as f:
            f.write(rendered)
    except Exception as e:
        print(f"Failed to write output: {e}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

