from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
HARNESS_DIR = ROOT / "scripts" / "demo" / "nanobragg_entrypoint_reference"
BUILD = HARNESS_DIR / "build_harness.py"
RUN = HARNESS_DIR / "run_reference_case.py"
HARNESS_C = HARNESS_DIR / "reference_harness.c"
HARNESS_H = HARNESS_DIR / "reference_harness.h"


def test_entrypoint_reference_files_exist():
    assert BUILD.is_file()
    assert RUN.is_file()
    assert HARNESS_C.is_file()
    assert HARNESS_H.is_file()


def test_build_harness_produces_shared_library():
    result = subprocess.run(
        [sys.executable, str(BUILD)],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["artifact_path"].endswith(".so")
    assert Path(payload["artifact_path"]).is_file()
    assert payload["entrypoint"] == "nanobragg_run"


def test_run_reference_case_returns_tensor_payload(tmp_path: Path):
    fixture = tmp_path / "tiny_case.json"
    fixture.write_text(
        json.dumps(
            {
                "case_id": "tiny_case",
                "output_shape": [4, 4],
                "argv": [
                    "-cell",
                    "10",
                    "10",
                    "10",
                    "90",
                    "90",
                    "90",
                    "-default_F",
                    "1",
                    "-detpixels_x",
                    "4",
                    "-detpixels_y",
                    "4",
                    "-pixel",
                    "0.1",
                    "-distance",
                    "100",
                    "-lambda",
                    "1",
                    "-N",
                    "1",
                    "-oversample",
                    "1",
                ],
            }
        )
    )

    result = subprocess.run(
        [sys.executable, str(RUN), str(fixture)],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["case_id"] == "tiny_case"
    assert payload["shape"] == [4, 4]
    assert payload["dtype"] == "float32"
    assert len(payload["flat_data"]) == 16
