from __future__ import annotations

import json
from pathlib import Path

import torch

from .types import Fixture


def load_visible_fixture(path: str | Path) -> Fixture:
    return json.loads(Path(path).read_text())


def nanobragg_run(fixture: Fixture) -> torch.Tensor:
    shape = fixture["output_shape"]
    return torch.zeros(shape, dtype=torch.float32)
