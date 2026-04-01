from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import torch


ROOT = Path(__file__).resolve().parent.parent
RUN_REFERENCE = ROOT / "scripts" / "demo" / "nanobragg_reference" / "run_reference_case.py"
BUILDER = ROOT / "scripts" / "demo" / "build_nanobragg_reference_cases.py"
FIXTURE_ROOT = ROOT / "orchestrator" / "demo" / "evaluators" / "fixtures" / "nanobragg_accumulation"


def test_run_reference_case_returns_tensor_payload_for_visible_fixture(tmp_path: Path):
    fixture = ROOT / "examples" / "demo_task_nanobragg_accumulation_port" / "fixtures" / "visible" / "case_small.json"

    result = subprocess.run(
        [sys.executable, str(RUN_REFERENCE), str(fixture)],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["shape"] == [2, 3]
    assert payload["dtype"] == "float64"
    assert payload["reference_method"] == "offline_reference_harness"
    assert payload["reference_source"].endswith("nanoBragg.c")
    assert len(payload["flat_data"]) == 6


def test_builder_generates_expected_tensor_from_reference_backend(tmp_path: Path):
    output_path = tmp_path / "expected_case_small.pt"
    fixture = ROOT / "examples" / "demo_task_nanobragg_accumulation_port" / "fixtures" / "visible" / "case_small.json"

    result = subprocess.run(
        [
            sys.executable,
            str(BUILDER),
            "--case-id",
            "case_small",
            "--output-path",
            str(output_path),
            "--fixture-path",
            str(fixture),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert output_path.is_file()
    tensor = torch.load(output_path, map_location="cpu")
    assert tuple(tensor.shape) == (2, 3)
    assert torch.isfinite(tensor).all()


def test_hidden_case_metadata_provenance_matches_reference_backend():
    payload = json.loads((FIXTURE_ROOT / "cases.json").read_text())
    case_small = next(case for case in payload["cases"] if case["case_id"] == "case_small")

    assert case_small["reference_method"] == "offline_reference_harness"
    assert case_small["reference_source"].endswith("nanoBragg.c")
