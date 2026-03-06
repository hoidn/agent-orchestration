from __future__ import annotations

import sys
from pathlib import Path

import torch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from torch_port.accumulation import accumulate_detector_image, load_visible_fixture

FIXTURE_DIR = PROJECT_ROOT / "fixtures" / "visible"


def test_case_small_matches_declared_shape():
    """Contract smoke: shape must match the visible fixture expectation."""
    fixture = load_visible_fixture(FIXTURE_DIR / "case_small.json")
    image = accumulate_detector_image(fixture)

    assert list(image.shape) == fixture["expected"]["shape"]
    torch.testing.assert_close(
        torch.tensor(list(image.shape), dtype=torch.int64),
        torch.tensor(fixture["expected"]["shape"], dtype=torch.int64),
    )


def test_case_thickness_outputs_are_finite():
    """Contract smoke: scoped outputs should remain finite on the visible thickness case."""
    fixture = load_visible_fixture(FIXTURE_DIR / "case_thickness.json")
    image = accumulate_detector_image(fixture)

    assert list(image.shape) == fixture["expected"]["shape"]
    assert torch.isfinite(image).all()
