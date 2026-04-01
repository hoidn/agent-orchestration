from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
HARNESS_DIR = ROOT / "scripts" / "demo" / "nanobragg_reference"
EXTRACT_SCRIPT = HARNESS_DIR / "extract_accumulation_slice.py"
HARNESS_C = HARNESS_DIR / "reference_harness.c"
HARNESS_HEADER = HARNESS_DIR / "reference_types.h"
HARNESS_README = HARNESS_DIR / "README.md"


def test_reference_harness_scaffold_files_exist():
    assert EXTRACT_SCRIPT.is_file()
    assert HARNESS_C.is_file()
    assert HARNESS_HEADER.is_file()
    assert HARNESS_README.is_file()


def test_extract_accumulation_slice_reports_scoped_anchor_metadata():
    result = subprocess.run(
        [sys.executable, str(EXTRACT_SCRIPT)],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["source_path"].endswith("nanoBragg.c")
    assert payload["start_line"] <= 2839
    assert payload["end_line"] >= 3404
    assert payload["contains"]["omega_pixel"] is True
    assert payload["contains"]["capture_fraction"] is True
    assert payload["contains"]["floatimage"] is True


def test_reference_harness_supports_compile_check_mode():
    result = subprocess.run(
        [sys.executable, str(EXTRACT_SCRIPT), "--compile-check"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["compile_check"] == "not_attempted"
    assert payload["reason"] == "reference_harness_scaffold_only"
