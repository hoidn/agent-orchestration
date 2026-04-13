#!/usr/bin/env python3
"""Build the hidden nanoBragg reference tensors from case metadata."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import torch


ROOT = Path(__file__).resolve().parents[2]
FIXTURE_ROOT = ROOT / "orchestrator" / "demo" / "evaluators" / "fixtures" / "nanobragg_accumulation"
SEED_ROOT = ROOT / "examples" / "demo_task_nanobragg_accumulation_port"
RUN_REFERENCE = ROOT / "scripts" / "demo" / "nanobragg_reference" / "run_reference_case.py"


def _run_reference(fixture_path: Path) -> dict[str, object]:
    result = subprocess.run(
        [sys.executable, str(RUN_REFERENCE), str(fixture_path)],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def _tensor_from_reference_payload(payload: dict[str, object]) -> torch.Tensor:
    dtype_name = payload.get("dtype")
    dtype = torch.float64 if dtype_name == "float64" else torch.float32
    return torch.tensor(payload["flat_data"], dtype=dtype).reshape(payload["shape"])


def _write_reference_tensor(fixture_path: Path, output_path: Path) -> dict[str, object]:
    payload = _run_reference(fixture_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    torch.save(_tensor_from_reference_payload(payload), output_path)
    return payload


def _case_by_id(case_id: str) -> dict[str, object]:
    metadata = json.loads((FIXTURE_ROOT / "cases.json").read_text())
    for case in metadata["cases"]:
        if case["case_id"] == case_id:
            return case
    raise KeyError(f"Unknown case id: {case_id}")


def _build_one(case: dict[str, object], *, fixture_path: Path | None = None, output_path: Path | None = None) -> None:
    input_path = fixture_path or SEED_ROOT / str(case["input_fixture_relpath"])
    if not input_path.is_file():
        raise FileNotFoundError(f"Missing visible input fixture: {input_path}")

    tensor_path = output_path or FIXTURE_ROOT / str(case["expected_tensor_relpath"])
    _write_reference_tensor(input_path, tensor_path)
    try:
        display_path = tensor_path.relative_to(ROOT)
    except ValueError:
        display_path = tensor_path
    print(f"wrote {display_path}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case-id")
    parser.add_argument("--output-path", type=Path)
    parser.add_argument("--fixture-path", type=Path)
    args = parser.parse_args(argv)

    if args.case_id:
        _build_one(
            _case_by_id(args.case_id),
            fixture_path=args.fixture_path,
            output_path=args.output_path,
        )
        return 0

    metadata = json.loads((FIXTURE_ROOT / "cases.json").read_text())
    for case in metadata["cases"]:
        _build_one(case)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
