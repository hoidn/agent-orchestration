"""Experiment configuration for structural search: mutable scope, condition and compile inputs.

Paths (`source_root`, `providers_file`, `command_boundaries_file`) are relative to a candidate root.
"""

import argparse
import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

CONDITIONS = ("topology-only", "prompt-only", "provider-only", "joint", "module")
INTERFACES = ("I1", "I2", "I3")


@dataclass(frozen=True)
class ExperimentConfig:
    mutable_files: tuple[str, ...]
    mutable_definitions: tuple[str, ...]
    condition: str
    interface: str
    entry_workflow: str
    source_root: str
    providers_file: str
    command_boundaries_file: str | None
    episode_wall_clock_sec: int
    criterion_sha256: str | None
    models: dict[str, list[str]] | None = None
    per_call_timeout_sec: float | None = None

    def __post_init__(self) -> None:
        if self.condition not in CONDITIONS:
            raise ValueError(f"condition must be one of {CONDITIONS}, got {self.condition!r}")
        if self.interface not in INTERFACES:
            raise ValueError(f"interface must be one of {INTERFACES}, got {self.interface!r}")
        if self.condition == "module":
            if not (isinstance(self.models, dict) and self.models and all(
                    isinstance(model, str) and model and isinstance(efforts, list) and efforts
                    and all(isinstance(effort, str) and effort for effort in efforts)
                    for model, efforts in self.models.items())):
                raise ValueError("module requires models mapping model IDs to nonempty effort lists")
            ceiling = self.per_call_timeout_sec
            if type(ceiling) not in (int, float) or not math.isfinite(ceiling) or ceiling <= 0:
                raise ValueError("module requires a finite positive per_call_timeout_sec")


def load_config(path: Path) -> ExperimentConfig:
    """Read an ExperimentConfig from JSON; a list field that is missing or not a JSON list raises ValueError
    naming the field, another unknown or missing key TypeError."""
    data = json.loads(path.read_text())
    for key in ("mutable_files", "mutable_definitions"):
        if not isinstance(data.get(key), list):
            raise ValueError(f"{path}: {key} must be a JSON list of strings, not {data.get(key)!r}")
        data[key] = tuple(data[key])
    return ExperimentConfig(**data)


def solution(text: str) -> tuple[str, str]:
    """A `--solution TASK=HASH` argument as (task, hash)."""
    task, sep, commit = text.partition("=")
    if not (task and sep and commit):
        raise argparse.ArgumentTypeError(f"expected TASK=HASH, not {text!r}")
    return task, commit


# These captured studies predate row hashes; successor studies must carry a hash on every source row.
HISTORICAL_CRITERIA = frozenset({
    "84ee6307ab39e74710154654133585e53aaa9b329e5c7f9918dc9ee2f055cc80",
    "f3fd229cc5bafa51cfdd3442f47af6a5edec0bb4fcd31c58f35c3546a6688e97",
    "d994f8daad608b76e342fa4bedcbc03f1e3c771f719877937331035eb0ae97ba",
})


def check_criterion_hashes(rows: Sequence[Mapping], expected: str) -> None:
    for row in rows:
        got = row.get("criterion_sha256")
        if got != expected and not (got is None and expected in HISTORICAL_CRITERIA):
            raise ValueError(f"{row.get('kind', 'record')} criterion_sha256 {got!r} differs from {expected}")
