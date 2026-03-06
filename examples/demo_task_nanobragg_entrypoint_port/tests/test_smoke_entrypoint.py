from __future__ import annotations

import sys
from pathlib import Path

import torch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from torch_port.entrypoint import load_visible_fixture, nanobragg_run

FIXTURE_DIR = PROJECT_ROOT / "fixtures" / "visible"


def test_case_basic_matches_declared_shape():
    fixture = load_visible_fixture(FIXTURE_DIR / "case_basic.json")
    image = nanobragg_run(fixture)

    assert list(image.shape) == fixture["output_shape"]


def test_case_basic_outputs_are_finite():
    fixture = load_visible_fixture(FIXTURE_DIR / "case_basic.json")
    image = nanobragg_run(fixture)

    assert torch.isfinite(image).all()
