#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
HARNESS_DIR = Path(__file__).resolve().parent
HARNESS_C = HARNESS_DIR / "reference_harness.c"
HARNESS_H = HARNESS_DIR / "reference_harness.h"
HARNESS_SO = HARNESS_DIR / "reference_harness.so"
REFERENCE_SOURCE = ROOT.parent / "nanoBragg" / "golden_suite_generator" / "nanoBragg.c"


def build_harness() -> Path:
    if HARNESS_SO.exists():
        so_mtime = HARNESS_SO.stat().st_mtime
        if so_mtime >= max(HARNESS_C.stat().st_mtime, HARNESS_H.stat().st_mtime, REFERENCE_SOURCE.stat().st_mtime):
            return HARNESS_SO

    subprocess.run(
        [
            "cc",
            "-shared",
            "-fPIC",
            "-O2",
            str(HARNESS_C),
            "-lm",
            "-o",
            str(HARNESS_SO),
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return HARNESS_SO


def main() -> int:
    artifact = build_harness()
    print(
        json.dumps(
            {
                "artifact_path": str(artifact),
                "entrypoint": "nanobragg_run",
                "reference_source": str(REFERENCE_SOURCE),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
