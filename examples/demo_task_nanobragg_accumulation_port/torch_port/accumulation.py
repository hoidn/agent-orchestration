"""Visible smoke-harness helpers for the bounded nanoBragg accumulation task."""

from __future__ import annotations

import json
from pathlib import Path

import torch

from .geometry import prepare_geometry_tensors
from .types import FixtureDict


def load_visible_fixture(path: str | Path) -> FixtureDict:
    """Load one visible JSON smoke fixture."""
    fixture_path = Path(path)
    return json.loads(fixture_path.read_text())


def accumulate_detector_image(fixture: FixtureDict) -> torch.Tensor:
    """Compute the bounded detector image tensor for one fixture."""
    _geometry = prepare_geometry_tensors(fixture)
    raise NotImplementedError("detector accumulation is not implemented yet")
