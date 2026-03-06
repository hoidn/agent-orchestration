#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import torch


ROOT = Path(__file__).resolve().parents[2]
VISIBLE_DIR = ROOT / "examples" / "demo_task_nanobragg_entrypoint_port" / "fixtures" / "visible"
HIDDEN_DIR = ROOT / "orchestrator" / "demo" / "evaluators" / "fixtures" / "nanobragg_entrypoint"
HIDDEN_INPUT_DIR = HIDDEN_DIR / "inputs"
RUN_REFERENCE = ROOT / "scripts" / "demo" / "nanobragg_entrypoint_reference" / "run_reference_case.py"

VISIBLE_CASES = [
    {
        "case_id": "case_basic",
        "output_shape": [4, 4],
        "argv": [
            "-cell", "10", "10", "10", "90", "90", "90",
            "-default_F", "1",
            "-detpixels_x", "4",
            "-detpixels_y", "4",
            "-pixel", "0.1",
            "-distance", "100",
            "-lambda", "1",
            "-N", "1",
            "-oversample", "1",
        ],
    },
    {
        "case_id": "case_thickness",
        "output_shape": [4, 4],
        "argv": [
            "-cell", "10", "10", "10", "90", "90", "90",
            "-default_F", "1",
            "-detpixels_x", "4",
            "-detpixels_y", "4",
            "-pixel", "0.1",
            "-distance", "100",
            "-lambda", "1",
            "-N", "1",
            "-oversample", "1",
            "-detector_abs", "200",
            "-detector_thick", "100",
            "-detector_thicksteps", "4",
            "-oversample_thick",
        ],
    },
    {
        "case_id": "case_mosaic",
        "output_shape": [4, 4],
        "argv": [
            "-cell", "10", "11", "12", "90", "90", "90",
            "-default_F", "1",
            "-detpixels_x", "4",
            "-detpixels_y", "4",
            "-pixel", "0.1",
            "-distance", "100",
            "-lambda", "1",
            "-N", "2",
            "-oversample", "1",
            "-mosaic", "0.2",
            "-mosaic_domains", "3",
            "-phisteps", "2",
            "-osc", "0.1",
        ],
    },
]

HIDDEN_CASES = [
    {
        "case_id": "hidden_rect_basic",
        "output_shape": [3, 5],
        "argv": [
            "-cell", "9", "10", "11", "90", "90", "90",
            "-default_F", "1",
            "-detpixels_x", "5",
            "-detpixels_y", "3",
            "-pixel", "0.08",
            "-distance", "120",
            "-lambda", "0.9",
            "-N", "1",
            "-oversample", "1",
        ],
    },
    {
        "case_id": "hidden_rect_large_n",
        "output_shape": [5, 6],
        "argv": [
            "-cell", "12", "13", "14", "90", "90", "90",
            "-default_F", "1",
            "-detpixels_x", "6",
            "-detpixels_y", "5",
            "-pixel", "0.09",
            "-distance", "110",
            "-lambda", "1.1",
            "-N", "3",
            "-oversample", "1",
        ],
    },
    {
        "case_id": "hidden_oversample2",
        "output_shape": [4, 4],
        "argv": [
            "-cell", "10", "10", "10", "90", "90", "90",
            "-default_F", "1",
            "-detpixels_x", "4",
            "-detpixels_y", "4",
            "-pixel", "0.1",
            "-distance", "100",
            "-lambda", "1",
            "-N", "1",
            "-oversample", "2",
        ],
    },
    {
        "case_id": "hidden_thickness_post",
        "output_shape": [4, 4],
        "argv": [
            "-cell", "10", "10", "10", "90", "90", "90",
            "-default_F", "1",
            "-detpixels_x", "4",
            "-detpixels_y", "4",
            "-pixel", "0.1",
            "-distance", "100",
            "-lambda", "1",
            "-N", "1",
            "-oversample", "1",
            "-detector_abs", "250",
            "-detector_thick", "120",
            "-detector_thicksteps", "4",
        ],
    },
    {
        "case_id": "hidden_thickness_rect",
        "output_shape": [3, 5],
        "argv": [
            "-cell", "9", "10", "11", "90", "90", "90",
            "-default_F", "1",
            "-detpixels_x", "5",
            "-detpixels_y", "3",
            "-pixel", "0.08",
            "-distance", "120",
            "-lambda", "0.95",
            "-N", "2",
            "-oversample", "1",
            "-detector_abs", "180",
            "-detector_thick", "90",
            "-detector_thicksteps", "3",
            "-oversample_thick",
        ],
    },
    {
        "case_id": "hidden_mosaic_small",
        "output_shape": [4, 4],
        "argv": [
            "-cell", "10", "11", "12", "90", "90", "90",
            "-default_F", "1",
            "-detpixels_x", "4",
            "-detpixels_y", "4",
            "-pixel", "0.1",
            "-distance", "100",
            "-lambda", "1",
            "-N", "2",
            "-oversample", "1",
            "-mosaic", "0.1",
            "-mosaic_domains", "2",
            "-phisteps", "2",
            "-osc", "0.05",
        ],
    },
    {
        "case_id": "hidden_mosaic_rect",
        "output_shape": [5, 6],
        "argv": [
            "-cell", "11", "12", "13", "90", "90", "90",
            "-default_F", "1",
            "-detpixels_x", "6",
            "-detpixels_y", "5",
            "-pixel", "0.09",
            "-distance", "110",
            "-lambda", "1.05",
            "-N", "2",
            "-oversample", "1",
            "-mosaic", "0.15",
            "-mosaic_domains", "4",
            "-phisteps", "3",
            "-osc", "0.2",
        ],
    },
    {
        "case_id": "hidden_distance_pixel",
        "output_shape": [4, 4],
        "argv": [
            "-cell", "10", "10", "10", "90", "90", "90",
            "-default_F", "1",
            "-detpixels_x", "4",
            "-detpixels_y", "4",
            "-pixel", "0.06",
            "-distance", "180",
            "-lambda", "1",
            "-N", "1",
            "-oversample", "1",
        ],
    },
    {
        "case_id": "hidden_lambda_n",
        "output_shape": [4, 4],
        "argv": [
            "-cell", "10", "11", "12", "90", "90", "90",
            "-default_F", "1",
            "-detpixels_x", "4",
            "-detpixels_y", "4",
            "-pixel", "0.1",
            "-distance", "100",
            "-lambda", "0.8",
            "-N", "3",
            "-oversample", "1",
        ],
    },
    {
        "case_id": "hidden_combo_all",
        "output_shape": [5, 6],
        "argv": [
            "-cell", "11", "13", "15", "90", "90", "90",
            "-default_F", "1",
            "-detpixels_x", "6",
            "-detpixels_y", "5",
            "-pixel", "0.07",
            "-distance", "140",
            "-lambda", "0.95",
            "-N", "2",
            "-oversample", "2",
            "-detector_abs", "220",
            "-detector_thick", "80",
            "-detector_thicksteps", "3",
            "-oversample_thick",
            "-mosaic", "0.12",
            "-mosaic_domains", "3",
            "-phisteps", "2",
            "-osc", "0.08",
        ],
    },
]


def _default_probe_sites(shape: list[int]) -> list[list[int]]:
    rows, cols = shape
    candidates = {
        (0, 0),
        (0, max(0, cols - 1)),
        (max(0, rows - 1), 0),
        (max(0, rows - 1), max(0, cols - 1)),
        (rows // 2, cols // 2),
    }
    return [[row, col] for row, col in sorted(candidates)]


def _run_reference(fixture_path: Path) -> dict[str, object]:
    result = subprocess.run(
        [sys.executable, str(RUN_REFERENCE), str(fixture_path)],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def _materialize_case(case: dict[str, object], *, fixture_path: Path) -> dict[str, object]:
    fixture_path.write_text(json.dumps(case, indent=2) + "\n")
    payload = _run_reference(fixture_path)
    tensor = torch.tensor(payload["flat_data"], dtype=torch.float32).reshape(payload["shape"])
    expected_path = HIDDEN_DIR / f"expected_{case['case_id']}.pt"
    torch.save(tensor, expected_path)
    return {
        "case_id": case["case_id"],
        "expected_output_path": str(expected_path.relative_to(ROOT)),
        "output_shape": payload["shape"],
        "probe_sites": _default_probe_sites(payload["shape"]),
        "reference_method": payload["reference_method"],
        "reference_source": payload["reference_source"],
    }


def main() -> int:
    VISIBLE_DIR.mkdir(parents=True, exist_ok=True)
    HIDDEN_DIR.mkdir(parents=True, exist_ok=True)
    HIDDEN_INPUT_DIR.mkdir(parents=True, exist_ok=True)

    hidden_cases: list[dict[str, object]] = []

    for case in VISIBLE_CASES:
        fixture_path = VISIBLE_DIR / f"{case['case_id']}.json"
        record = _materialize_case(case, fixture_path=fixture_path)
        hidden_cases.append(
            {
                **record,
                "input_fixture_origin": "workspace",
                "input_fixture_relpath": f"fixtures/visible/{case['case_id']}.json",
            }
        )

    for case in HIDDEN_CASES:
        fixture_path = HIDDEN_INPUT_DIR / f"{case['case_id']}.json"
        record = _materialize_case(case, fixture_path=fixture_path)
        hidden_cases.append(
            {
                **record,
                "input_fixture_origin": "evaluator_fixture_root",
                "input_fixture_relpath": f"inputs/{case['case_id']}.json",
            }
        )

    (HIDDEN_DIR / "cases.json").write_text(
        json.dumps(
            {
                "entrypoint": "nanobragg_run",
                "reference_method": "nanobragg_main_wrapper",
                "cases": hidden_cases,
            },
            indent=2,
        )
        + "\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
