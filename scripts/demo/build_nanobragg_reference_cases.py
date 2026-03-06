#!/usr/bin/env python3
"""Build the hidden nanoBragg reference tensors from case metadata."""

from __future__ import annotations

import json
from pathlib import Path

import torch


ROOT = Path(__file__).resolve().parents[2]
FIXTURE_ROOT = ROOT / "orchestrator" / "demo" / "evaluators" / "fixtures" / "nanobragg_accumulation"
SEED_ROOT = ROOT / "examples" / "demo_task_nanobragg_accumulation_port"


REFERENCE_TENSORS = {
    "case_small": torch.full((2, 3), 1.25, dtype=torch.float64),
    "case_thickness": torch.tensor([[0.75, 1.0], [1.25, 1.5]], dtype=torch.float64),
    "case_mosaic": torch.tensor([[0.6, 0.7], [0.8, 0.9], [1.0, 1.1]], dtype=torch.float64),
}


def main() -> int:
    metadata = json.loads((FIXTURE_ROOT / "cases.json").read_text())
    for case in metadata["cases"]:
        input_path = SEED_ROOT / case["input_fixture_relpath"]
        if not input_path.is_file():
            raise FileNotFoundError(f"Missing visible input fixture: {input_path}")
        output_path = FIXTURE_ROOT / case["expected_tensor_relpath"]
        tensor = REFERENCE_TENSORS[case["case_id"]]
        torch.save(tensor, output_path)
        print(f"wrote {output_path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
