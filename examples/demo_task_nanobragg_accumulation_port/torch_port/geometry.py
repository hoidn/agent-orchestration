"""Geometry helpers for the bounded nanoBragg accumulation port."""

from __future__ import annotations

import torch

from .types import FixtureDict


def prepare_geometry_tensors(fixture: FixtureDict) -> dict[str, torch.Tensor]:
    """Convert the visible geometry section into a small tensor bundle."""
    raise NotImplementedError("geometry preparation is not implemented yet")
